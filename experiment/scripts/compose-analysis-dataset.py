#!/usr/bin/env python3

"""Compose the candidate-level analysis dataset from hash-bound evidence."""

import argparse
import copy
import datetime
import hashlib
import json
import math
import pathlib
import re


DIGEST = re.compile(r"^[0-9a-f]{64}$")
FIDELITY_METRICS = {
    "checkout_success_rate": "ratio",
    "checkout_latency_p95_ms": "milliseconds",
    "checkout_latency_p99_ms": "milliseconds",
    "checkoutservice_unavailable": "deployments",
    "checkoutservice_restart_increase": "restarts",
}


def load(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_binding(repo_root, binding, label):
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise ValueError(f"{label} must contain only path and sha256")
    relative = pathlib.PurePosixPath(binding.get("path", ""))
    expected = binding.get("sha256")
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{label} contains an unsafe evidence path")
    if not isinstance(expected, str) or not DIGEST.fullmatch(expected):
        raise ValueError(f"{label} contains an invalid evidence digest")
    path = pathlib.Path(repo_root) / relative
    if not path.is_file() or sha256_file(path) != expected:
        raise ValueError(f"{label} evidence hash differs")
    return load(path)


def validate_metrics(metrics, label):
    if metrics is None:
        return {}
    if not isinstance(metrics, dict):
        raise ValueError(f"{label} continuous metrics must be an object")
    return metrics.copy()


def finite_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def validate_fidelity_summary(summary, label, allow_empty=False, nonnegative=False):
    if summary is None and allow_empty:
        return
    required = {
        "count",
        "mean",
        "median",
        "sample_standard_deviation",
        "minimum",
        "maximum",
    }
    if not isinstance(summary, dict) or set(summary) != required:
        raise ValueError(f"{label} summary schema is invalid")
    count = summary["count"]
    values = [summary[name] for name in ("mean", "median", "minimum", "maximum")]
    deviation = summary["sample_standard_deviation"]
    if (
        not isinstance(count, int)
        or isinstance(count, bool)
        or count <= 0
        or any(not finite_number(value) for value in values)
        or (count == 1 and deviation is not None)
        or (count > 1 and (not finite_number(deviation) or deviation < 0))
        or summary["minimum"] > summary["median"]
        or summary["median"] > summary["maximum"]
        or summary["minimum"] > summary["mean"]
        or summary["mean"] > summary["maximum"]
        or (nonnegative and summary["minimum"] < 0)
    ):
        raise ValueError(f"{label} summary values are invalid")


def validate_fidelity(
    fidelity,
    protocol,
    protocol_sha256,
    candidate_id,
    planned_repetitions,
    control,
    confirmatory,
):
    coverage = fidelity.get("coverage") if isinstance(fidelity, dict) else None
    classification = fidelity.get("classification") if isinstance(fidelity, dict) else None
    controls = fidelity.get("controls") if isinstance(fidelity, dict) else None
    artifacts = fidelity.get("immutable_artifacts") if isinstance(fidelity, dict) else None
    candidate_definition_sha256 = (
        fidelity.get("candidate_definition_sha256")
        if isinstance(fidelity, dict)
        else None
    )
    minimum_valid_repetitions = protocol.get("aggregation", {}).get(
        "minimum_valid_repetitions"
    )
    valid_repetitions = (
        coverage.get("valid_repetitions") if isinstance(coverage, dict) else None
    )
    invalid_repetitions = (
        coverage.get("invalid_repetitions") if isinstance(coverage, dict) else None
    )
    if (
        not isinstance(fidelity, dict)
        or fidelity.get("schema_version") != "1.0.0"
        or fidelity.get("mechanism") != "candidate-level-pdt-fidelity"
        or fidelity.get("protocol_id") != protocol.get("protocol_id")
        or fidelity.get("protocol_sha256") != protocol_sha256
        or fidelity.get("policy_id") != "checkout-pdt-fidelity-v1"
        or not isinstance(fidelity.get("policy_sha256"), str)
        or not DIGEST.fullmatch(fidelity["policy_sha256"])
        or fidelity.get("candidate_id") != candidate_id
        or not isinstance(candidate_definition_sha256, str)
        or not DIGEST.fullmatch(candidate_definition_sha256)
        or candidate_definition_sha256 != control.get("candidate_definition_sha256")
        or not isinstance(artifacts, list)
        or artifacts != control.get("immutable_artifacts")
        or fidelity.get("unit_of_analysis") != "candidate"
        or fidelity.get("execution_mode")
        != ("confirmatory" if confirmatory else "engineering")
        or fidelity.get("confirmatory_eligible") is not confirmatory
    ):
        raise ValueError(f"{candidate_id} fidelity aggregate is not protocol-bound")
    if (
        not isinstance(coverage, dict)
        or coverage.get("complete") is not True
        or coverage.get("repetitions") != planned_repetitions
        or coverage.get("minimum_valid_repetitions") != minimum_valid_repetitions
        or not isinstance(valid_repetitions, list)
        or not all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in valid_repetitions
        )
        or valid_repetitions != sorted(set(valid_repetitions))
        or not isinstance(invalid_repetitions, list)
        or not all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in invalid_repetitions
        )
        or invalid_repetitions != sorted(set(invalid_repetitions))
        or sorted(valid_repetitions + invalid_repetitions) != planned_repetitions
        or not isinstance(minimum_valid_repetitions, int)
        or isinstance(minimum_valid_repetitions, bool)
        or len(valid_repetitions) < minimum_valid_repetitions
        or not isinstance(coverage.get("deployable_alternatives"), list)
        or not coverage["deployable_alternatives"]
        or len(coverage["deployable_alternatives"])
        != len(set(coverage["deployable_alternatives"]))
        or "deploy-as-is" not in coverage["deployable_alternatives"]
        or not isinstance(coverage.get("expected_reports"), int)
        or isinstance(coverage.get("expected_reports"), bool)
        or coverage["expected_reports"] <= 0
        or not isinstance(coverage.get("observed_reports"), int)
        or isinstance(coverage.get("observed_reports"), bool)
        or coverage.get("observed_reports") != coverage["expected_reports"]
        or coverage["expected_reports"]
        != len(coverage["deployable_alternatives"]) * len(valid_repetitions)
    ):
        raise ValueError(f"{candidate_id} fidelity coverage is incomplete")
    agreements = classification.get("agreements") if isinstance(classification, dict) else None
    comparisons = classification.get("comparisons") if isinstance(classification, dict) else None
    agreement_rate = classification.get("agreement_rate") if isinstance(classification, dict) else None
    by_alternative = classification.get("by_alternative") if isinstance(classification, dict) else None
    if (
        not isinstance(agreements, int)
        or isinstance(agreements, bool)
        or not isinstance(comparisons, int)
        or isinstance(comparisons, bool)
        or comparisons != coverage["expected_reports"]
        or agreements < 0
        or agreements > comparisons
        or not finite_number(agreement_rate)
        or not math.isclose(
            agreement_rate, agreements / comparisons, rel_tol=1e-12, abs_tol=1e-12
        )
        or not isinstance(by_alternative, dict)
        or set(by_alternative) != set(coverage["deployable_alternatives"])
    ):
        raise ValueError(f"{candidate_id} fidelity classification is inconsistent")
    for alternative_id, item in by_alternative.items():
        expected_comparisons = len(valid_repetitions)
        if (
            not isinstance(item, dict)
            or set(item) != {"agreements", "comparisons", "agreement_rate"}
            or not isinstance(item["agreements"], int)
            or isinstance(item["agreements"], bool)
            or not isinstance(item["comparisons"], int)
            or isinstance(item["comparisons"], bool)
            or item["comparisons"] != expected_comparisons
            or item["agreements"] < 0
            or item["agreements"] > expected_comparisons
            or not finite_number(item["agreement_rate"])
            or not math.isclose(
                item["agreement_rate"],
                item["agreements"] / expected_comparisons,
                rel_tol=1e-12,
                abs_tol=1e-12,
            )
        ):
            raise ValueError(
                f"{candidate_id} fidelity classification for {alternative_id} is inconsistent"
            )
    metric_results = fidelity.get("metrics")
    if not isinstance(metric_results, dict) or set(metric_results) != set(FIDELITY_METRICS):
        raise ValueError(f"{candidate_id} fidelity metric set is invalid")
    for metric_id, unit in FIDELITY_METRICS.items():
        metric = metric_results[metric_id]
        if (
            not isinstance(metric, dict)
            or set(metric)
            != {
                "unit",
                "report_count",
                "signed_error",
                "absolute_error",
                "relative_error",
                "undefined_relative_error_count",
            }
            or metric.get("unit") != unit
            or not isinstance(metric.get("report_count"), int)
            or isinstance(metric.get("report_count"), bool)
            or metric.get("report_count") != coverage["expected_reports"]
            or not isinstance(metric.get("undefined_relative_error_count"), int)
            or isinstance(metric.get("undefined_relative_error_count"), bool)
            or not 0 <= metric["undefined_relative_error_count"] <= metric["report_count"]
        ):
            raise ValueError(f"{candidate_id} fidelity metric {metric_id} is invalid")
        validate_fidelity_summary(metric["signed_error"], f"{candidate_id} {metric_id} signed")
        validate_fidelity_summary(
            metric["absolute_error"], f"{candidate_id} {metric_id} absolute", nonnegative=True
        )
        validate_fidelity_summary(
            metric["relative_error"],
            f"{candidate_id} {metric_id} relative",
            allow_empty=metric["undefined_relative_error_count"] == metric["report_count"],
            nonnegative=True,
        )
        relative_count = (
            metric["relative_error"]["count"] if metric["relative_error"] is not None else 0
        )
        if relative_count + metric["undefined_relative_error_count"] != metric["report_count"]:
            raise ValueError(f"{candidate_id} fidelity relative-error accounting differs")
    report_index = fidelity.get("report_index")
    expected_identities = {
        (alternative_id, repetition)
        for alternative_id in coverage["deployable_alternatives"]
        for repetition in valid_repetitions
    }
    if not isinstance(report_index, list) or len(report_index) != len(expected_identities):
        raise ValueError(f"{candidate_id} fidelity report index is incomplete")
    indexed_identities = []
    indexed_agreements = 0
    indexed_by_alternative = {
        alternative_id: 0 for alternative_id in coverage["deployable_alternatives"]
    }
    for item in report_index:
        if (
            not isinstance(item, dict)
            or set(item)
            != {"alternative_id", "repetition", "classification_agreement"}
            or not isinstance(item.get("classification_agreement"), bool)
        ):
            raise ValueError(f"{candidate_id} fidelity report index is invalid")
        identity = (item.get("alternative_id"), item.get("repetition"))
        indexed_identities.append(identity)
        indexed_agreements += item["classification_agreement"]
        if item.get("alternative_id") in indexed_by_alternative:
            indexed_by_alternative[item["alternative_id"]] += item[
                "classification_agreement"
            ]
    if (
        len(indexed_identities) != len(set(indexed_identities))
        or set(indexed_identities) != expected_identities
        or indexed_agreements != agreements
        or any(
            indexed_by_alternative[alternative_id]
            != by_alternative[alternative_id]["agreements"]
            for alternative_id in indexed_by_alternative
        )
    ):
        raise ValueError(f"{candidate_id} fidelity report index is inconsistent")
    if (
        not isinstance(controls, dict)
        or controls.get("complete_matrix_required") is not True
        or controls.get("complete_valid_repetition_matrix_required") is not True
        or controls.get("missing_repetitions_require_prelabel_ledger") is not True
        or controls.get("model_mutation_performed") is not False
        or controls.get("recalibration_allowed") is not False
        or controls.get("confirmatory_reports_are_evaluation_only") is not True
    ):
        raise ValueError(f"{candidate_id} fidelity controls are invalid")
    return copy.deepcopy(fidelity)


def validate_exclusion(repo_root, candidate_id, planned_repetitions, exclusion, protocol):
    required_keys = {
        "reason_code",
        "reason",
        "decided_before_oracle_label",
        "label_revealed",
        "valid_repetitions",
        "invalid_repetitions",
        "replacement_attempted",
        "evidence",
    }
    if not isinstance(exclusion, dict) or set(exclusion) != required_keys:
        raise ValueError("candidate exclusion has an incomplete or unexpected schema")
    minimum_valid = protocol.get("aggregation", {}).get("minimum_valid_repetitions")
    if exclusion.get("reason_code") != "insufficient-valid-repetitions":
        raise ValueError("candidate exclusion reason code is not protocol-authorized")
    if not isinstance(exclusion.get("reason"), str) or not exclusion["reason"].strip():
        raise ValueError("candidate exclusion must contain a non-empty reason")
    if (
        exclusion.get("decided_before_oracle_label") is not True
        or exclusion.get("label_revealed") is not False
    ):
        raise ValueError("candidate exclusion must be decided before oracle label release")
    if exclusion.get("replacement_attempted") is not True:
        raise ValueError("candidate exclusion requires the protocol replacement attempt")
    valid = exclusion.get("valid_repetitions")
    invalid = exclusion.get("invalid_repetitions")
    if (
        not isinstance(valid, list)
        or not isinstance(invalid, list)
        or any(not isinstance(item, int) or isinstance(item, bool) for item in valid + invalid)
        or len(valid) != len(set(valid))
        or len(invalid) != len(set(invalid))
        or valid != sorted(valid)
        or invalid != sorted(invalid)
        or set(valid) & set(invalid)
        or set(valid) | set(invalid) != set(planned_repetitions)
        or not isinstance(minimum_valid, int)
        or isinstance(minimum_valid, bool)
        or minimum_valid <= 0
        or minimum_valid > len(planned_repetitions)
        or len(valid) >= minimum_valid
    ):
        raise ValueError("candidate exclusion repetition accounting is invalid")

    evidence = resolve_binding(
        repo_root, exclusion.get("evidence"), f"{candidate_id} exclusion ledger"
    )
    invalid_attempts = (
        evidence.get("invalid_repetitions") if isinstance(evidence, dict) else None
    )
    evidence_keys = {
        "schema_version",
        "candidate_id",
        "classification",
        "label_revealed",
        "planned_repetitions",
        "valid_repetitions",
        "invalid_repetitions",
    }
    if (
        not isinstance(evidence, dict)
        or set(evidence) != evidence_keys
        or evidence.get("schema_version") != "1.0.0"
        or evidence.get("candidate_id") != candidate_id
        or evidence.get("classification") != "infrastructure-invalid"
        or evidence.get("label_revealed") is not False
        or evidence.get("planned_repetitions") != planned_repetitions
        or evidence.get("valid_repetitions") != valid
        or not isinstance(invalid_attempts, list)
        or len(invalid_attempts) != len(invalid)
    ):
        raise ValueError("candidate exclusion ledger differs from the declared repetitions")
    for expected_repetition, item in zip(invalid, invalid_attempts):
        if (
            not isinstance(item, dict)
            or set(item) != {"repetition", "attempts", "reasons"}
            or item.get("repetition") != expected_repetition
            or item.get("attempts") != 2
            or not isinstance(item.get("reasons"), list)
            or len(item["reasons"]) != 2
            or not all(
                isinstance(reason, str) and reason.strip() for reason in item["reasons"]
            )
        ):
            raise ValueError("excluded repetition lacks both infrastructure-invalid attempts")
    return {
        "reason_code": exclusion["reason_code"],
        "reason": exclusion["reason"].strip(),
        "decided_before_oracle_label": True,
        "label_revealed": False,
        "valid_repetitions": valid.copy(),
        "invalid_repetitions": invalid.copy(),
        "replacement_attempted": True,
        "evidence": exclusion["evidence"].copy(),
    }


def compose(protocol, protocol_sha256, public, public_sha256, manifest, repo_root, allow_draft=False):
    confirmatory = (
        protocol.get("status") == "frozen"
        and protocol.get("confirmatory_collection_allowed") is True
        and bool(protocol.get("frozen_at"))
    )
    if not confirmatory and not allow_draft:
        raise ValueError("candidate dataset composition requires a frozen protocol")
    if (
        public.get("protocol_id") != protocol.get("protocol_id")
        or public.get("protocol_sha256") != protocol_sha256
    ):
        raise ValueError("public corpus is not bound to the supplied protocol")
    if confirmatory and public.get("confirmatory_eligible") is not True:
        raise ValueError("confirmatory composition requires an eligible public corpus")
    if (
        manifest.get("protocol_id") != protocol.get("protocol_id")
        or manifest.get("protocol_sha256") != protocol_sha256
        or manifest.get("public_corpus_sha256") != public_sha256
    ):
        raise ValueError("collection manifest bindings differ from protocol or corpus")
    if manifest.get("collection_complete") is not True:
        raise ValueError("collection manifest must be explicitly complete")

    public_entries = public.get("execution_order")
    manifest_entries = manifest.get("candidates")
    declared_count = protocol.get("research_design", {}).get("candidate_count")
    if (
        not isinstance(public_entries, list)
        or not isinstance(manifest_entries, list)
        or len(public_entries) != declared_count
        or len(manifest_entries) != declared_count
    ):
        raise ValueError("corpus or manifest candidate count differs from the protocol")
    public_ids = [item.get("candidate_id") for item in public_entries]
    manifest_ids = [item.get("candidate_id") for item in manifest_entries]
    if len(set(public_ids)) != len(public_ids) or set(public_ids) != set(manifest_ids):
        raise ValueError("collection manifest candidate set differs from the public corpus")
    by_id = {item["candidate_id"]: item for item in manifest_entries}

    candidates = []
    manifest_exclusions = []
    fidelity_candidates = 0
    fidelity_not_applicable = 0
    for public_entry in public_entries:
        candidate_id = public_entry["candidate_id"]
        planned_repetitions = public_entry.get("repetitions")
        required_repetitions = protocol.get("research_design", {}).get(
            "technical_repetitions_per_candidate"
        )
        if (
            not isinstance(required_repetitions, int)
            or required_repetitions <= 0
            or planned_repetitions != list(range(1, required_repetitions + 1))
        ):
            raise ValueError("public corpus repetition plan differs from the protocol")
        item = by_id[candidate_id]
        exclusion = item.get("exclusion")
        if exclusion is not None:
            normalized = validate_exclusion(
                repo_root,
                candidate_id,
                planned_repetitions,
                exclusion,
                protocol,
            )
            if any(
                item.get(field) is not None
                for field in (
                    "conventional_decision",
                    "pdt_decision",
                    "deployment_gate",
                    "pdt_fidelity",
                    "oracle_adjudication",
                    "control_continuous_metrics",
                    "treatment_continuous_metrics",
                )
            ):
                raise ValueError(
                    f"{candidate_id} excluded candidate must not contain decision or oracle evidence"
                )
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "sequence": public_entry.get("sequence"),
                    "repetitions": public_entry.get("repetitions"),
                    "exclusion": normalized,
                }
            )
            manifest_exclusions.append(
                {"candidate_id": candidate_id, **normalized}
            )
            continue

        control = resolve_binding(
            repo_root, item.get("conventional_decision"), f"{candidate_id} conventional decision"
        )
        oracle = resolve_binding(
            repo_root, item.get("oracle_adjudication"), f"{candidate_id} oracle adjudication"
        )
        if (
            control.get("candidate_id") != candidate_id
            or control.get("mechanism") != "conventional-ci-cd-with-staging"
            or control.get("control_decision_sealed") is not True
            or control.get("decision") not in {"approve", "block"}
            or control.get("operational_mutation_performed") is not False
        ):
            raise ValueError(f"{candidate_id} conventional decision is invalid or unsealed")
        if oracle.get("candidate_id") != candidate_id:
            raise ValueError(f"{candidate_id} oracle adjudication belongs to another candidate")
        if confirmatory:
            actual = oracle.get("observed_deploy_as_is_label")
            eligible = oracle.get("eligible_for_primary_analysis")
            if actual == "inconclusive" and eligible is not False:
                raise ValueError(
                    f"{candidate_id} inconclusive oracle adjudication must be analysis-ineligible"
                )
            if actual != "inconclusive" and eligible is not True:
                raise ValueError(f"{candidate_id} oracle adjudication is not analysis-eligible")

        control_result = {
            "decision": control["decision"],
            "selected_alternative": (
                "deploy-as-is" if control["decision"] == "approve" else "block"
            ),
            "continuous_metrics": validate_metrics(
                item.get("control_continuous_metrics"), f"{candidate_id} control"
            ),
        }
        if control["decision"] == "approve":
            pdt = resolve_binding(repo_root, item.get("pdt_decision"), f"{candidate_id} PDT decision")
            gate = resolve_binding(
                repo_root, item.get("deployment_gate"), f"{candidate_id} deployment gate"
            )
            if (
                pdt.get("candidate") != candidate_id
                or pdt.get("decision") not in {"approve", "block", "reconfigure"}
                or not pdt.get("selected_alternative")
                or pdt.get("artifact_binding", {}).get("immutable_artifacts")
                != control.get("immutable_artifacts")
                or pdt.get("artifact_binding", {}).get("candidate_definition_sha256")
                != control.get("candidate_definition_sha256")
            ):
                raise ValueError(f"{candidate_id} PDT decision is invalid or not control-bound")
            expected_gate = (
                "blocked" if pdt["decision"] == "block" else "awaiting-human-confirmation"
            )
            if (
                gate.get("candidate_id") != candidate_id
                or gate.get("gate_state") != expected_gate
                or gate.get("operational_mutation_performed") is not False
            ):
                raise ValueError(f"{candidate_id} deployment gate is inconsistent")
            fidelity = resolve_binding(
                repo_root,
                item.get("pdt_fidelity"),
                f"{candidate_id} PDT fidelity aggregate",
            )
            fidelity = validate_fidelity(
                fidelity,
                protocol,
                protocol_sha256,
                candidate_id,
                planned_repetitions,
                control,
                confirmatory,
            )
            treatment_result = {
                "decision": pdt["decision"],
                "selected_alternative": pdt["selected_alternative"],
                "continuous_metrics": validate_metrics(
                    item.get("treatment_continuous_metrics"), f"{candidate_id} treatment"
                ),
                "fidelity": fidelity,
            }
            fidelity_candidates += 1
        else:
            if (
                item.get("pdt_decision") is not None
                or item.get("deployment_gate") is not None
                or item.get("pdt_fidelity") is not None
            ):
                raise ValueError(f"{candidate_id} control-blocked candidate must not contain PDT evidence")
            treatment_result = {
                "decision": "block",
                "selected_alternative": "block",
                "continuous_metrics": validate_metrics(
                    item.get("treatment_continuous_metrics"), f"{candidate_id} treatment"
                ),
                "fidelity": None,
            }
            fidelity_not_applicable += 1

        candidates.append(
            {
                "candidate_id": candidate_id,
                "sequence": public_entry.get("sequence"),
                "repetitions": public_entry.get("repetitions"),
                "exclusion": None,
                "control": control_result,
                "treatment": treatment_result,
                "oracle": oracle,
            }
        )

    return {
        "schema_version": "1.0.0",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": protocol_sha256,
        "corpus_id": public.get("corpus_id"),
        "public_corpus_sha256": public_sha256,
        "collection_complete": True,
        "confirmatory_eligible": confirmatory and not allow_draft,
        "composition_mode": "confirmatory" if confirmatory and not allow_draft else "engineering-dry-run",
        "collection_flow": {
            "declared_candidates": declared_count,
            "candidate_records": len(candidates),
            "complete_decision_pairs": declared_count - len(manifest_exclusions),
            "pdt_fidelity_candidates": fidelity_candidates,
            "pdt_fidelity_not_applicable_control_blocked": fidelity_not_applicable,
            "manifest_exclusions": manifest_exclusions,
            "silently_missing_candidates": 0,
        },
        "candidates": candidates,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=pathlib.Path, required=True)
    parser.add_argument("--protocol", type=pathlib.Path, required=True)
    parser.add_argument("--public-corpus", type=pathlib.Path, required=True)
    parser.add_argument("--collection-manifest", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--allow-draft", action="store_true")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    try:
        result = compose(
            load(args.protocol),
            sha256_file(args.protocol),
            load(args.public_corpus),
            sha256_file(args.public_corpus),
            load(args.collection_manifest),
            repo_root,
            allow_draft=args.allow_draft,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"analysis dataset composition failed: {error}") from error
    result["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    result["inputs"] = {
        "protocol": str(args.protocol),
        "public_corpus": str(args.public_corpus),
        "collection_manifest": str(args.collection_manifest),
        "collection_manifest_sha256": sha256_file(args.collection_manifest),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
