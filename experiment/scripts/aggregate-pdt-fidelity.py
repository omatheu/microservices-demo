#!/usr/bin/env python3

"""Aggregate hash-bound PDT fidelity reports at the candidate level."""

import argparse
import datetime
import hashlib
import json
import math
import os
import pathlib
import re
import statistics
import sys


DIGEST = re.compile(r"^[0-9a-f]{64}$")


def load(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def finite_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def close(left, right):
    return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12)


def continuous_summary(values):
    if not values:
        return None
    if any(not finite_number(value) for value in values):
        raise ValueError("fidelity summary contains a non-finite value")
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "sample_standard_deviation": (
            statistics.stdev(values) if len(values) > 1 else None
        ),
        "minimum": min(values),
        "maximum": max(values),
    }


def validate_design(protocol, policy, candidate, allow_draft):
    if (
        policy.get("schema_version") != "1.0.0"
        or policy.get("policy_id") != "checkout-pdt-fidelity-v1"
        or policy.get("status") not in {"pre-registration-candidate", "frozen"}
    ):
        raise ValueError("fidelity policy identity or status is invalid")
    if protocol.get("research_design", {}).get("unit_of_analysis") != (
        "candidate after aggregation of technical repetitions"
    ):
        raise ValueError("protocol does not define candidate-level aggregation")
    repetitions = protocol.get("research_design", {}).get(
        "technical_repetitions_per_candidate"
    )
    if not isinstance(repetitions, int) or isinstance(repetitions, bool) or repetitions < 2:
        raise ValueError("protocol repetition count is invalid")
    metric_entries = policy.get("metrics")
    if not isinstance(metric_entries, list) or not metric_entries:
        raise ValueError("fidelity policy metric inventory is empty")
    metric_ids = [item.get("id") for item in metric_entries if isinstance(item, dict)]
    if len(metric_ids) != len(metric_entries) or len(metric_ids) != len(set(metric_ids)):
        raise ValueError("fidelity policy metric inventory is invalid")
    controls = policy.get("controls")
    if (
        policy.get("twin_object") != "checkoutservice"
        or not isinstance(controls, dict)
        or controls.get("post_decision_only") is not True
        or controls.get("model_mutation_allowed") is not False
        or controls.get("confirmatory_corpus_recalibration_allowed") is not False
    ):
        raise ValueError("fidelity policy anti-leakage controls are invalid")
    candidate_id = candidate.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id:
        raise ValueError("candidate definition lacks an identifier")
    alternatives = [
        item.get("id")
        for item in candidate.get("alternatives", [])
        if isinstance(item, dict) and item.get("action") == "deploy"
    ]
    if (
        not alternatives
        or len(alternatives) != len(set(alternatives))
        or alternatives.count("deploy-as-is") != 1
    ):
        raise ValueError("candidate deployable alternative inventory is invalid")
    confirmatory = (
        protocol.get("status") == "frozen"
        and protocol.get("confirmatory_collection_allowed") is True
        and bool(protocol.get("frozen_at"))
        and policy.get("status") == "frozen"
        and bool(policy.get("frozen_at"))
        and candidate.get("confirmatory_eligibility") is True
    )
    if not confirmatory and not allow_draft:
        raise ValueError("candidate fidelity aggregation requires a frozen design")
    return candidate_id, sorted(alternatives), list(range(1, repetitions + 1)), metric_entries, confirmatory


def validate_metric(item, expected):
    expected_id = expected["id"]
    if (
        not isinstance(item, dict)
        or item.get("id") != expected_id
        or item.get("unit") != expected.get("unit")
    ):
        raise ValueError("fidelity report metric inventory differs from policy")
    predicted = item.get("predicted")
    observed = item.get("observed")
    signed = item.get("signed_error")
    absolute = item.get("absolute_error")
    relative = item.get("relative_error")
    relative_defined = item.get("relative_error_defined")
    if any(not finite_number(value) for value in (predicted, observed, signed, absolute)):
        raise ValueError(f"fidelity metric {expected_id} contains non-finite values")
    expected_signed = predicted - observed
    expected_absolute = abs(expected_signed)
    if not close(signed, expected_signed) or not close(absolute, expected_absolute):
        raise ValueError(f"fidelity metric {expected_id} error arithmetic differs")
    if observed == 0:
        if relative is not None or relative_defined is not False:
            raise ValueError(f"fidelity metric {expected_id} must preserve undefined relative error")
    else:
        expected_relative = expected_absolute / abs(observed)
        if (
            not finite_number(relative)
            or relative_defined is not True
            or not close(relative, expected_relative)
        ):
            raise ValueError(f"fidelity metric {expected_id} relative error differs")
    return {
        "signed_error": signed,
        "absolute_error": absolute,
        "relative_error": relative,
    }


def validate_report(
    report,
    policy,
    policy_sha256,
    candidate_id,
    candidate_sha256,
    alternatives,
    repetitions,
    metric_entries,
):
    alternative_id = report.get("alternative_id")
    repetition = report.get("repetition")
    if (
        report.get("schema_version") != "1.0.0"
        or report.get("mechanism") != "pdt-post-decision-fidelity"
        or report.get("policy_id") != policy.get("policy_id")
        or report.get("policy_status") != policy.get("status")
        or report.get("candidate_id") != candidate_id
        or report.get("twin_object") != "checkoutservice"
        or alternative_id not in alternatives
        or repetition not in repetitions
        or report.get("execution_mode") not in {"engineering", "confirmatory"}
    ):
        raise ValueError("fidelity report identity or mode is invalid")
    input_sha256 = report.get("input_sha256")
    if (
        not isinstance(input_sha256, dict)
        or input_sha256.get("fidelity_policy") != policy_sha256
        or any(
            not isinstance(value, str) or not DIGEST.fullmatch(value)
            for value in input_sha256.values()
        )
    ):
        raise ValueError("fidelity report input bindings are invalid")
    controls = report.get("controls")
    if (
        not isinstance(controls, dict)
        or controls.get("post_decision_only") is not True
        or controls.get("oracle_intended_label_used") is not False
        or controls.get("model_mutation_performed") is not False
        or controls.get("recalibration_allowed") is not False
        or controls.get("confirmatory_reports_are_evaluation_only") is not True
    ):
        raise ValueError("fidelity report anti-leakage controls are invalid")
    bindings = report.get("sealed_input_bindings")
    if (
        not isinstance(bindings, dict)
        or bindings.get("candidate_definition_sha256") != candidate_sha256
        or not isinstance(bindings.get("conventional_decision_sha256"), str)
        or not DIGEST.fullmatch(bindings["conventional_decision_sha256"])
        or not isinstance(bindings.get("immutable_artifacts"), list)
    ):
        raise ValueError("fidelity report candidate or artifact bindings differ")
    prediction = report.get("prediction")
    observation = report.get("observation")
    if (
        not isinstance(prediction, dict)
        or prediction.get("label") not in {"safe", "harmful"}
        or not isinstance(observation, dict)
        or observation.get("label") not in {"safe", "harmful"}
        or not isinstance(report.get("classification_agreement"), bool)
        or report["classification_agreement"]
        != (prediction["label"] == observation["label"])
    ):
        raise ValueError("fidelity classification accounting is invalid")
    metrics = report.get("metrics")
    metric_ids = [item["id"] for item in metric_entries]
    if not isinstance(metrics, list) or len(metrics) != len(metric_ids):
        raise ValueError("fidelity report metric count differs from policy")
    normalized = {
        metric_id: validate_metric(item, expected)
        for metric_id, expected, item in zip(metric_ids, metric_entries, metrics)
    }
    return {
        "candidate_id": candidate_id,
        "alternative_id": alternative_id,
        "repetition": repetition,
        "execution_mode": report["execution_mode"],
        "confirmatory_eligible": report.get("confirmatory_eligible") is True,
        "classification_agreement": report["classification_agreement"],
        "immutable_artifacts": bindings["immutable_artifacts"],
        "metrics": normalized,
    }


def aggregate(
    protocol,
    protocol_sha256,
    policy,
    policy_sha256,
    candidate,
    candidate_sha256,
    reports,
    allow_draft=False,
):
    (
        candidate_id,
        alternatives,
        repetitions,
        metric_entries,
        confirmatory,
    ) = validate_design(protocol, policy, candidate, allow_draft)
    normalized = [
        validate_report(
            report,
            policy,
            policy_sha256,
            candidate_id,
            candidate_sha256,
            alternatives,
            repetitions,
            metric_entries,
        )
        for report in reports
    ]
    identities = [
        (item["alternative_id"], item["repetition"]) for item in normalized
    ]
    expected = [
        (alternative_id, repetition)
        for alternative_id in alternatives
        for repetition in repetitions
    ]
    if len(identities) != len(set(identities)):
        raise ValueError("fidelity reports contain a duplicate alternative/repetition")
    if set(identities) != set(expected):
        raise ValueError("fidelity reports do not cover the complete candidate matrix")
    artifact_bindings = [item["immutable_artifacts"] for item in normalized]
    if any(binding != artifact_bindings[0] for binding in artifact_bindings[1:]):
        raise ValueError("fidelity reports do not share one immutable artifact set")
    modes = {item["execution_mode"] for item in normalized}
    if len(modes) != 1:
        raise ValueError("fidelity reports mix execution modes")
    mode = next(iter(modes))
    if confirmatory and (
        mode != "confirmatory"
        or not all(item["confirmatory_eligible"] for item in normalized)
    ):
        raise ValueError("confirmatory fidelity matrix contains ineligible evidence")
    if not confirmatory and any(item["confirmatory_eligible"] for item in normalized):
        raise ValueError("draft fidelity matrix claims confirmatory eligibility")

    metric_results = {}
    for metric in metric_entries:
        metric_id = metric["id"]
        signed = [item["metrics"][metric_id]["signed_error"] for item in normalized]
        absolute = [item["metrics"][metric_id]["absolute_error"] for item in normalized]
        relative = [
            item["metrics"][metric_id]["relative_error"]
            for item in normalized
            if item["metrics"][metric_id]["relative_error"] is not None
        ]
        metric_results[metric_id] = {
            "unit": metric.get("unit"),
            "report_count": len(normalized),
            "signed_error": continuous_summary(signed),
            "absolute_error": continuous_summary(absolute),
            "relative_error": continuous_summary(relative),
            "undefined_relative_error_count": len(normalized) - len(relative),
        }

    by_alternative = {}
    for alternative_id in alternatives:
        entries = [
            item for item in normalized if item["alternative_id"] == alternative_id
        ]
        agreements = sum(item["classification_agreement"] for item in entries)
        by_alternative[alternative_id] = {
            "agreements": agreements,
            "comparisons": len(entries),
            "agreement_rate": agreements / len(entries),
        }
    agreements = sum(item["classification_agreement"] for item in normalized)
    return {
        "schema_version": "1.0.0",
        "mechanism": "candidate-level-pdt-fidelity",
        "protocol_id": protocol.get("protocol_id"),
        "protocol_sha256": protocol_sha256,
        "policy_id": policy.get("policy_id"),
        "policy_sha256": policy_sha256,
        "candidate_id": candidate_id,
        "candidate_definition_sha256": candidate_sha256,
        "immutable_artifacts": artifact_bindings[0],
        "unit_of_analysis": "candidate",
        "execution_mode": mode,
        "confirmatory_eligible": confirmatory,
        "coverage": {
            "deployable_alternatives": alternatives,
            "repetitions": repetitions,
            "expected_reports": len(expected),
            "observed_reports": len(normalized),
            "complete": True,
        },
        "classification": {
            "agreements": agreements,
            "comparisons": len(normalized),
            "agreement_rate": agreements / len(normalized),
            "by_alternative": by_alternative,
        },
        "metrics": metric_results,
        "report_index": [
            {
                "alternative_id": item["alternative_id"],
                "repetition": item["repetition"],
                "classification_agreement": item["classification_agreement"],
            }
            for item in sorted(
                normalized, key=lambda item: (item["alternative_id"], item["repetition"])
            )
        ],
        "controls": {
            "complete_matrix_required": True,
            "model_mutation_performed": False,
            "recalibration_allowed": False,
            "confirmatory_reports_are_evaluation_only": True,
        },
    }


def write_json_exclusive(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
    except Exception:
        path.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", type=pathlib.Path, required=True)
    parser.add_argument("--policy", type=pathlib.Path, required=True)
    parser.add_argument("--candidate-definition", type=pathlib.Path, required=True)
    parser.add_argument("--report", type=pathlib.Path, action="append", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--allow-draft", action="store_true")
    args = parser.parse_args()
    try:
        result = aggregate(
            load(args.protocol),
            sha256_file(args.protocol),
            load(args.policy),
            sha256_file(args.policy),
            load(args.candidate_definition),
            sha256_file(args.candidate_definition),
            [load(path) for path in args.report],
            allow_draft=args.allow_draft,
        )
        result["generated_at"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat().replace("+00:00", "Z")
        result["input_reports"] = [
            {"path": str(path), "sha256": sha256_file(path)} for path in args.report
        ]
        write_json_exclusive(args.output, result)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"PDT fidelity aggregation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(args.output)


if __name__ == "__main__":
    main()
