#!/usr/bin/env python3

"""Aggregate repeated PDT predictions into one candidate-level action."""

import argparse
import copy
import datetime
import hashlib
import importlib.util
import json
import math
import os
import pathlib
import statistics


def load(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_conventional_aggregator():
    path = pathlib.Path(__file__).with_name("aggregate-conventional-repetitions.py")
    spec = importlib.util.spec_from_file_location("aggregate_conventional_repetitions", path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise ValueError("could not load the shared repetition controls")
    spec.loader.exec_module(module)
    return module


SHARED = load_conventional_aggregator()


def finite_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def metric(metrics, path, label):
    value = metrics
    for name in path:
        if not isinstance(value, dict) or name not in value:
            raise ValueError(f"PDT prediction lacks {label}")
        value = value[name]
    if not finite_number(value) or value < 0:
        raise ValueError(f"PDT prediction contains invalid {label}")
    return value


def summarize_predictions(predictions, repetitions):
    paths = {
        "success_rate": ("success_rate",),
        "latency_p50_ms": ("latency_ms", "p50"),
        "latency_p95_ms": ("latency_ms", "p95"),
        "latency_p99_ms": ("latency_ms", "p99"),
        "checkout_latency_p95_ms": ("checkout", "latency_p95_ms"),
        "checkout_latency_p99_ms": ("checkout", "latency_p99_ms"),
        "checkoutservice_unavailable": ("checkout", "unavailable"),
        "checkoutservice_restart_increase": ("checkout", "restart_increase"),
    }
    medians = {
        name: statistics.median(
            metric(prediction, path, name) for prediction in predictions
        )
        for name, path in paths.items()
    }
    return {
        "aggregation": "median-of-valid-repetitions",
        "valid_repetitions": repetitions.copy(),
        "medians": medians,
    }


def candidate_alternatives(candidate):
    alternatives = candidate.get("alternatives")
    if not isinstance(alternatives, list) or not alternatives:
        raise ValueError("candidate alternative inventory is empty")
    by_id = {}
    for alternative in alternatives:
        alternative_id = alternative.get("id") if isinstance(alternative, dict) else None
        if (
            not isinstance(alternative_id, str)
            or not alternative_id
            or alternative_id in by_id
            or alternative.get("action") not in {"deploy", "block"}
            or not isinstance(alternative.get("configuration_changes"), list)
            or not finite_number(alternative.get("change_cost"))
            or alternative["change_cost"] < 0
        ):
            raise ValueError("candidate alternative inventory is invalid")
        by_id[alternative_id] = copy.deepcopy(alternative)
    if (
        "deploy-as-is" not in by_id
        or by_id["deploy-as-is"]["action"] != "deploy"
        or len([item for item in by_id.values() if item["action"] == "block"]) != 1
    ):
        raise ValueError("candidate must contain deploy-as-is and one block alternative")
    return by_id


def validate_control(
    control, candidate_id, candidate_sha256, protocol_id, expected_execution_mode
):
    aggregation = control.get("repetition_aggregation")
    local_ci = control.get("local_ci")
    staging = control.get("staging")
    if (
        control.get("mechanism") != "conventional-ci-cd-with-staging"
        or control.get("candidate_id") != candidate_id
        or control.get("protocol_id") != protocol_id
        or control.get("execution_mode") != expected_execution_mode
        or control.get("decision") != "approve"
        or control.get("control_decision_sealed") is not True
        or control.get("candidate_definition_sha256") != candidate_sha256
        or not isinstance(control.get("immutable_artifacts"), list)
        or not control["immutable_artifacts"]
        or not isinstance(local_ci, dict)
        or local_ci.get("decision") != "pass"
        or not isinstance(staging, dict)
        or staging.get("executed") is not True
        or staging.get("decision") != "PASS"
        or staging.get("artifact_binding_verified") is not True
        or not isinstance(aggregation, dict)
        or aggregation.get("outcome") != "approve"
        or aggregation.get("safe_votes", 0)
        < aggregation.get("safe_votes_to_approve", 1)
    ):
        raise ValueError("PDT repetition aggregation requires a candidate-level control approval")


def validate_pdt_repetition(
    decision,
    candidate_id,
    expected_mode,
    alternatives,
    artifacts,
    candidate_sha256,
    control_sha256,
):
    if (
        decision.get("candidate") != candidate_id
        or decision.get("execution_mode") != expected_mode
        or decision.get("operational_mutation_performed") is not False
        or not isinstance(decision.get("model_id"), str)
        or not decision["model_id"]
        or not isinstance(decision.get("snapshot_id"), str)
        or not decision["snapshot_id"]
    ):
        raise ValueError("PDT repetition identity, mode or mutation state is invalid")
    binding = decision.get("artifact_binding")
    if (
        not isinstance(binding, dict)
        or binding.get("conventional_decision_sha256") != control_sha256
        or binding.get("candidate_definition_sha256") != candidate_sha256
        or binding.get("staging_binding_verified") is not True
        or binding.get("immutable_artifacts") != artifacts
    ):
        raise ValueError("PDT repetition artifact binding differs")
    evaluated = decision.get("alternatives_evaluated")
    if not isinstance(evaluated, list) or len(evaluated) != len(alternatives):
        raise ValueError("PDT repetition alternative inventory is incomplete")
    by_id = {}
    for result in evaluated:
        alternative_id = result.get("id") if isinstance(result, dict) else None
        definition = alternatives.get(alternative_id)
        if (
            definition is None
            or alternative_id in by_id
            or result.get("action") != definition["action"]
            or result.get("configuration_changes")
            != definition["configuration_changes"]
            or result.get("change_cost") != definition["change_cost"]
            or not isinstance(result.get("safe"), bool)
            or not finite_number(result.get("confidence"))
            or not 0 <= result["confidence"] <= 1
        ):
            raise ValueError("PDT repetition changes or alternative metadata differ")
        if definition["action"] == "deploy":
            if not isinstance(result.get("predicted_metrics"), dict):
                raise ValueError("deployable PDT alternative lacks predicted metrics")
            metric(result["predicted_metrics"], ("latency_ms", "p95"), "latency p95")
        elif result.get("predicted_metrics") is not None:
            raise ValueError("block alternative must not contain predicted metrics")
        by_id[alternative_id] = result
    if set(by_id) != set(alternatives):
        raise ValueError("PDT repetition alternative set differs")
    return by_id


def aggregate(
    protocol,
    candidate,
    candidate_sha256,
    control,
    control_sha256,
    pdt_decisions,
    invalid_repetition_ledger=None,
    allow_draft=False,
):
    planned, minimum_valid, safe_votes_to_approve, confirmatory = SHARED.validate_design(
        protocol, allow_draft
    )
    rule = protocol["aggregation"]["mechanism_repetition_rule"]
    if (
        rule.get("pdt_metric_aggregation") != "median"
        or rule.get("pdt_confidence_aggregation") != "minimum"
        or rule.get("pdt_action_snapshot") != "latest-valid-repetition"
    ):
        raise ValueError("protocol PDT repetition aggregation rule is incomplete")
    candidate_id = candidate.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id:
        raise ValueError("candidate identifier is invalid")
    if candidate.get("twin_object") != "checkoutservice":
        raise ValueError("PDT candidate must target checkoutservice")
    if confirmatory and candidate.get("confirmatory_eligibility") is not True:
        raise ValueError("confirmatory PDT aggregation requires an eligible candidate")
    expected_mode = "confirmatory" if confirmatory else "engineering"
    expected_control_mode = "confirmatory" if confirmatory else "engineering-dry-run"
    validate_control(
        control,
        candidate_id,
        candidate_sha256,
        protocol.get("protocol_id"),
        expected_control_mode,
    )
    if not minimum_valid <= len(pdt_decisions) <= planned:
        raise ValueError("PDT decisions do not contain enough valid repetitions")
    repetitions = [item.get("repetition") for item in pdt_decisions]
    expected = list(range(1, planned + 1))
    if (
        any(not isinstance(value, int) or isinstance(value, bool) for value in repetitions)
        or len(repetitions) != len(set(repetitions))
        or not set(repetitions).issubset(expected)
    ):
        raise ValueError("PDT repetition identities are incomplete or duplicated")
    ordered = sorted(pdt_decisions, key=lambda item: item["repetition"])
    valid_repetitions = [item["repetition"] for item in ordered]
    invalid_repetitions = SHARED.validate_invalid_repetition_ledger(
        invalid_repetition_ledger, candidate_id, planned, valid_repetitions
    )
    alternatives = candidate_alternatives(candidate)
    artifacts = control["immutable_artifacts"]
    evaluated_by_repetition = []
    for decision in ordered:
        evaluated_by_repetition.append(
            validate_pdt_repetition(
                decision,
                candidate_id,
                expected_mode,
                alternatives,
                artifacts,
                candidate_sha256,
                control_sha256,
            )
        )
    if len({item.get("model_id") for item in ordered}) != 1:
        raise ValueError("PDT repetitions use different model identities")

    aggregated_alternatives = []
    safe_deployable = []
    for alternative_id, definition in alternatives.items():
        results = [items[alternative_id] for items in evaluated_by_repetition]
        safe_votes = sum(item["safe"] is True for item in results)
        aggregate_safe = (
            definition["action"] == "block" or safe_votes >= safe_votes_to_approve
        )
        predictions = [
            item["predicted_metrics"]
            for item in results
            if definition["action"] == "deploy"
        ]
        prediction_summary = (
            summarize_predictions(predictions, valid_repetitions)
            if predictions
            else None
        )
        confidence = min(item["confidence"] for item in results)
        aggregated = {
            "id": alternative_id,
            "action": definition["action"],
            "configuration_changes": copy.deepcopy(
                definition["configuration_changes"]
            ),
            "change_cost": definition["change_cost"],
            "safe": aggregate_safe,
            "safe_votes": safe_votes,
            "unsafe_votes": len(results) - safe_votes,
            "predicted_metrics": prediction_summary,
            "confidence": confidence,
            "repetitions": valid_repetitions.copy(),
        }
        aggregated_alternatives.append(aggregated)
        if definition["action"] == "deploy" and aggregate_safe:
            safe_deployable.append(aggregated)

    by_id = {item["id"]: item for item in aggregated_alternatives}
    if by_id["deploy-as-is"]["safe"]:
        selected = by_id["deploy-as-is"]
        decision = "approve"
        rationale = ["deploy-as-is received the required safe-vote majority"]
    elif safe_deployable:
        selected = min(
            safe_deployable,
            key=lambda item: (
                item["change_cost"],
                item["predicted_metrics"]["medians"]["latency_p95_ms"],
                item["id"],
            ),
        )
        decision = "reconfigure"
        rationale = [
            "deploy-as-is lacked a safe-vote majority",
            "selected the lowest-cost majority-safe counterfactual",
        ]
    else:
        selected = next(
            item for item in aggregated_alternatives if item["action"] == "block"
        )
        decision = "block"
        rationale = ["no deployable counterfactual received a safe-vote majority"]

    latest = ordered[-1]
    return {
        "schema_version": "1.0.0",
        "mechanism": "candidate-level-pdt-decision",
        "model_id": latest["model_id"],
        "candidate": candidate_id,
        "protocol_id": protocol.get("protocol_id"),
        "execution_mode": expected_mode if confirmatory else "engineering-dry-run",
        "repetition": None,
        "snapshot_id": latest["snapshot_id"],
        "snapshot_ids": [item["snapshot_id"] for item in ordered],
        "action_snapshot_rule": "latest-valid-repetition",
        "alternatives_evaluated": aggregated_alternatives,
        "decision": decision,
        "selected_alternative": selected["id"],
        "recommended_configuration": copy.deepcopy(
            selected["configuration_changes"]
        ),
        "predicted_metrics": copy.deepcopy(selected["predicted_metrics"]),
        "confidence": selected["confidence"],
        "rationale": rationale,
        "repetition_aggregation": {
            "rule": "majority-safe-vote",
            "planned_repetitions": planned,
            "minimum_valid_repetitions": minimum_valid,
            "safe_votes_to_approve": safe_votes_to_approve,
            "valid_repetitions": valid_repetitions,
            "invalid_repetitions": invalid_repetitions,
            "votes_by_alternative": {
                item["id"]: {
                    "safe": item["safe_votes"],
                    "unsafe": item["unsafe_votes"],
                }
                for item in aggregated_alternatives
            },
        },
        "artifact_binding": {
            "conventional_decision_sha256": control_sha256,
            "candidate_definition_sha256": candidate_sha256,
            "staging_binding_verified": True,
            "immutable_artifacts": copy.deepcopy(artifacts),
        },
        "human_confirmation_required": True,
        "operational_mutation_performed": False,
    }


def write_json_exclusive(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
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
    parser.add_argument("--candidate-definition", type=pathlib.Path, required=True)
    parser.add_argument("--conventional-decision", type=pathlib.Path, required=True)
    parser.add_argument("--pdt-decision", type=pathlib.Path, action="append", required=True)
    parser.add_argument("--infrastructure-invalid-ledger", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--allow-draft", action="store_true")
    args = parser.parse_args()
    try:
        protocol = load(args.protocol)
        candidate = load(args.candidate_definition)
        control = load(args.conventional_decision)
        pdt_decisions = [load(path) for path in args.pdt_decision]
        invalid_ledger = (
            load(args.infrastructure_invalid_ledger)
            if args.infrastructure_invalid_ledger
            else None
        )
        result = aggregate(
            protocol,
            candidate,
            sha256_file(args.candidate_definition),
            control,
            sha256_file(args.conventional_decision),
            pdt_decisions,
            invalid_repetition_ledger=invalid_ledger,
            allow_draft=args.allow_draft,
        )
        result["protocol_sha256"] = sha256_file(args.protocol)
        result["sealed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
        result["evidence"] = {
            "protocol": {"path": str(args.protocol), "sha256": result["protocol_sha256"]},
            "candidate_definition": {
                "path": str(args.candidate_definition),
                "sha256": sha256_file(args.candidate_definition),
            },
            "conventional_decision": {
                "path": str(args.conventional_decision),
                "sha256": sha256_file(args.conventional_decision),
            },
            "pdt_decisions": [
                {
                    "path": str(path),
                    "sha256": sha256_file(path),
                    "repetition": decision.get("repetition"),
                }
                for path, decision in zip(args.pdt_decision, pdt_decisions)
            ],
            "infrastructure_invalid_ledger": (
                {
                    "path": str(args.infrastructure_invalid_ledger),
                    "sha256": sha256_file(args.infrastructure_invalid_ledger),
                }
                if args.infrastructure_invalid_ledger
                else None
            ),
        }
        write_json_exclusive(args.output, result)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"PDT repetition aggregation failed: {error}") from error
    print(args.output)


if __name__ == "__main__":
    main()
