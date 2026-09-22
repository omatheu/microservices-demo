#!/usr/bin/env python3

"""Compare one sealed PDT prediction with its post-decision oracle observation."""

import argparse
import datetime
import hashlib
import importlib.util
import json
import math
import os
import pathlib
import re
import sys


DIGEST = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_METRICS = (
    "checkout_success_rate",
    "checkout_latency_p95_ms",
    "checkout_latency_p99_ms",
    "checkoutservice_unavailable",
    "checkoutservice_restart_increase",
)


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


def require_nonnegative(value, label):
    if not finite_number(value) or value < 0:
        raise ValueError(f"{label} must be a finite non-negative number")
    return value


def validate_policy(policy, oracle_policy):
    if policy.get("schema_version") != "1.0.0":
        raise ValueError("fidelity policy schema is invalid")
    if policy.get("status") not in {"pre-registration-candidate", "frozen"}:
        raise ValueError("fidelity policy status is invalid")
    if policy.get("twin_object") != "checkoutservice":
        raise ValueError("fidelity policy must target checkoutservice")
    if policy.get("oracle_policy_id") != oracle_policy.get("policy_id"):
        raise ValueError("fidelity and oracle policies differ")
    metric_ids = [item.get("id") for item in policy.get("metrics", [])]
    if metric_ids != list(EXPECTED_METRICS):
        raise ValueError("fidelity metric set or order is invalid")
    controls = policy.get("controls")
    if (
        not isinstance(controls, dict)
        or controls.get("post_decision_only") is not True
        or controls.get("oracle_intended_label_is_not_an_input") is not True
        or controls.get("model_mutation_allowed") is not False
        or controls.get("confirmatory_corpus_recalibration_allowed") is not False
    ):
        raise ValueError("fidelity anti-leakage controls are invalid")
    if policy.get("oracle_profile_id") not in {
        item.get("id")
        for item in oracle_policy.get("performance_profiles", [])
        if item.get("required") is True
    }:
        raise ValueError("fidelity policy references a non-required oracle profile")


def load_oracle_evaluator():
    path = pathlib.Path(__file__).with_name("adjudicate-oracle.py")
    spec = importlib.util.spec_from_file_location("pdt_fidelity_oracle", path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise ValueError("could not load independent oracle evaluator")
    spec.loader.exec_module(module)
    return module


def extract_values(policy, prediction, observation):
    checkout = prediction.get("checkout")
    if not isinstance(checkout, dict):
        raise ValueError("PDT prediction lacks checkout metrics")
    tests = checkout.get("tests")
    successes = checkout.get("successes")
    if (
        not isinstance(tests, int)
        or isinstance(tests, bool)
        or tests <= 0
        or not isinstance(successes, int)
        or isinstance(successes, bool)
        or successes < 0
        or successes > tests
    ):
        raise ValueError("PDT checkout sample accounting is invalid")

    profile_id = policy["oracle_profile_id"]
    profiles = [
        item
        for item in observation.get("performance_profiles", [])
        if isinstance(item, dict) and item.get("id") == profile_id
    ]
    if len(profiles) != 1:
        raise ValueError("oracle observation lacks one fidelity profile")
    profile = profiles[0]
    health = observation.get("health")
    if not isinstance(health, dict):
        raise ValueError("oracle observation lacks health metrics")

    predicted = {
        "checkout_success_rate": successes / tests,
        "checkout_latency_p95_ms": checkout.get("latency_p95_ms"),
        "checkout_latency_p99_ms": checkout.get("latency_p99_ms"),
        "checkoutservice_unavailable": checkout.get("unavailable"),
        "checkoutservice_restart_increase": checkout.get("restart_increase"),
    }
    observed = {
        "checkout_success_rate": profile.get("success_rate"),
        "checkout_latency_p95_ms": profile.get("checkout_latency_p95_ms"),
        "checkout_latency_p99_ms": profile.get("checkout_latency_p99_ms"),
        "checkoutservice_unavailable": health.get("checkoutservice_unavailable"),
        "checkoutservice_restart_increase": health.get(
            "checkoutservice_restart_increase"
        ),
    }
    for metric_id in EXPECTED_METRICS:
        require_nonnegative(predicted[metric_id], f"predicted {metric_id}")
        require_nonnegative(observed[metric_id], f"observed {metric_id}")
    for values, label in ((predicted, "predicted"), (observed, "observed")):
        if values["checkout_success_rate"] > 1:
            raise ValueError(f"{label} checkout success rate exceeds one")
    return predicted, observed


def metric_results(policy, predicted, observed):
    by_id = {item["id"]: item for item in policy["metrics"]}
    results = []
    relative_errors = []
    for metric_id in EXPECTED_METRICS:
        predicted_value = predicted[metric_id]
        observed_value = observed[metric_id]
        signed = predicted_value - observed_value
        absolute = abs(signed)
        relative = absolute / abs(observed_value) if observed_value != 0 else None
        if relative is not None:
            relative_errors.append(relative)
        results.append(
            {
                "id": metric_id,
                "unit": by_id[metric_id]["unit"],
                "predicted": predicted_value,
                "observed": observed_value,
                "signed_error": signed,
                "absolute_error": absolute,
                "relative_error": relative,
                "relative_error_defined": relative is not None,
            }
        )
    return results, relative_errors


def calculate(policy, oracle_policy, pdt, observation):
    validate_policy(policy, oracle_policy)
    candidate_id = pdt.get("candidate")
    alternative_id = observation.get("alternative_id")
    repetition = pdt.get("repetition")
    mode = pdt.get("execution_mode")
    if (
        not isinstance(candidate_id, str)
        or not candidate_id
        or observation.get("candidate_id") != candidate_id
    ):
        raise ValueError("PDT and oracle candidate identities differ")
    if (
        not isinstance(repetition, int)
        or isinstance(repetition, bool)
        or repetition <= 0
        or observation.get("repetition") != repetition
    ):
        raise ValueError("PDT and oracle repetitions differ")
    if mode not in {"engineering", "confirmatory"} or observation.get("mode") != mode:
        raise ValueError("PDT and oracle execution modes differ")
    if pdt.get("operational_mutation_performed") is not False:
        raise ValueError("PDT prediction must precede operational mutation")
    binding = pdt.get("artifact_binding")
    if (
        not isinstance(binding, dict)
        or not DIGEST.fullmatch(str(binding.get("conventional_decision_sha256", "")))
        or not DIGEST.fullmatch(str(binding.get("candidate_definition_sha256", "")))
        or not isinstance(binding.get("immutable_artifacts"), list)
    ):
        raise ValueError("PDT prediction is not bound to sealed inputs")
    if observation.get("execution_valid") is not True:
        raise ValueError("infrastructure-invalid oracle evidence cannot measure fidelity")

    alternatives = [
        item
        for item in pdt.get("alternatives_evaluated", [])
        if isinstance(item, dict) and item.get("id") == alternative_id
    ]
    if len(alternatives) != 1 or alternatives[0].get("action") != "deploy":
        raise ValueError("oracle alternative was not evaluated as a PDT deployment")
    alternative = alternatives[0]
    if not isinstance(alternative.get("safe"), bool):
        raise ValueError("PDT alternative lacks a safety prediction")
    confidence = alternative.get("confidence")
    if not finite_number(confidence) or confidence < 0 or confidence > 1:
        raise ValueError("PDT confidence is invalid")
    prediction = alternative.get("predicted_metrics")
    if not isinstance(prediction, dict):
        raise ValueError("PDT alternative lacks predicted metrics")

    oracle = load_oracle_evaluator()
    evaluation = oracle.evaluate_repetition(
        observation, oracle_policy, candidate_id, alternative_id
    )
    if evaluation.get("valid") is not True:
        raise ValueError("oracle repetition is invalid: " + ";".join(evaluation["invalid_reasons"]))

    predicted, observed = extract_values(policy, prediction, observation)
    metrics, relative_errors = metric_results(policy, predicted, observed)
    predicted_label = "safe" if alternative["safe"] else "harmful"
    observed_label = evaluation["label"]
    confirmatory = (
        mode == "confirmatory"
        and policy.get("status") == "frozen"
        and bool(policy.get("frozen_at"))
        and oracle_policy.get("status") == "frozen"
        and bool(oracle_policy.get("frozen_at"))
    )
    if mode == "confirmatory" and not confirmatory:
        raise ValueError("confirmatory fidelity requires both policies frozen with timestamps")
    return {
        "schema_version": "1.0.0",
        "mechanism": "pdt-post-decision-fidelity",
        "policy_id": policy["policy_id"],
        "policy_status": policy["status"],
        "candidate_id": candidate_id,
        "alternative_id": alternative_id,
        "repetition": repetition,
        "twin_object": policy["twin_object"],
        "execution_mode": mode,
        "confirmatory_eligible": confirmatory,
        "prediction": {
            "label": predicted_label,
            "confidence": confidence,
            "snapshot_id": pdt.get("snapshot_id"),
        },
        "sealed_input_bindings": {
            "candidate_definition_sha256": binding[
                "candidate_definition_sha256"
            ],
            "conventional_decision_sha256": binding[
                "conventional_decision_sha256"
            ],
            "immutable_artifacts": binding["immutable_artifacts"],
        },
        "observation": {
            "label": observed_label,
            "violations": evaluation["violations"],
            "profile_id": policy["oracle_profile_id"],
        },
        "classification_agreement": predicted_label == observed_label,
        "metrics": metrics,
        "aggregate": {
            "metric_count": len(metrics),
            "relative_error_defined_count": len(relative_errors),
            "mean_absolute_relative_error": (
                sum(relative_errors) / len(relative_errors)
                if relative_errors
                else None
            ),
        },
        "controls": {
            "post_decision_only": True,
            "oracle_intended_label_used": False,
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
    parser.add_argument("--policy", type=pathlib.Path, required=True)
    parser.add_argument("--oracle-policy", type=pathlib.Path, required=True)
    parser.add_argument("--pdt-decision", type=pathlib.Path, required=True)
    parser.add_argument("--oracle-observation", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        result = calculate(
            load(args.policy),
            load(args.oracle_policy),
            load(args.pdt_decision),
            load(args.oracle_observation),
        )
        result["generated_at"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat().replace("+00:00", "Z")
        result["input_sha256"] = {
            "fidelity_policy": sha256_file(args.policy),
            "oracle_policy": sha256_file(args.oracle_policy),
            "pdt_decision": sha256_file(args.pdt_decision),
            "oracle_observation": sha256_file(args.oracle_observation),
        }
        write_json_exclusive(args.output, result)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"PDT fidelity calculation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(args.output)


if __name__ == "__main__":
    main()
