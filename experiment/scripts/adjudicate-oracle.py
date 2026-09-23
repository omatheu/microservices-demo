#!/usr/bin/env python3

import argparse
import collections
import datetime
import json
import os
import pathlib
import statistics
import sys


def load(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def evaluate_repetition(observation, policy, candidate_id, alternative_id):
    repetition = observation.get("repetition")
    result = {
        "repetition": repetition,
        "valid": False,
        "label": "invalid",
        "violations": [],
        "invalid_reasons": [],
    }
    if observation.get("candidate_id") != candidate_id:
        result["invalid_reasons"].append("candidate-id-mismatch")
    if observation.get("alternative_id") != alternative_id:
        result["invalid_reasons"].append("alternative-id-mismatch")
    if not isinstance(repetition, int) or repetition <= 0:
        result["invalid_reasons"].append("invalid-repetition")
    if observation.get("execution_valid") is not True:
        result["invalid_reasons"].append(
            "execution-invalid:" + str(observation.get("invalid_reason", "unspecified"))
        )
    if result["invalid_reasons"]:
        return result

    required_assertions = set(policy["functional_assertions"])
    assertions = observation.get("functional_assertions")
    if not isinstance(assertions, list):
        result["invalid_reasons"].append("functional-assertions-missing")
    else:
        assertion_ids = [item.get("id") for item in assertions if isinstance(item, dict)]
        if len(assertion_ids) != len(set(assertion_ids)):
            result["invalid_reasons"].append("functional-assertions-duplicated")
        if set(assertion_ids) != required_assertions:
            result["invalid_reasons"].append("functional-assertion-set-mismatch")
        for assertion in assertions:
            if not isinstance(assertion, dict) or not isinstance(assertion.get("passed"), bool):
                result["invalid_reasons"].append("functional-assertion-result-invalid")
                continue
            if assertion["passed"] is False:
                result["violations"].append(f"functional:{assertion.get('id')}")

    expected_profiles = {
        item["id"]: item
        for item in policy["performance_profiles"]
        if item.get("required") is True
    }
    profiles = observation.get("performance_profiles")
    if not isinstance(profiles, list):
        result["invalid_reasons"].append("performance-profiles-missing")
    else:
        profile_ids = [item.get("id") for item in profiles if isinstance(item, dict)]
        if len(profile_ids) != len(set(profile_ids)):
            result["invalid_reasons"].append("performance-profiles-duplicated")
        if set(profile_ids) != set(expected_profiles):
            result["invalid_reasons"].append("performance-profile-set-mismatch")
        for profile in profiles:
            profile_id = profile.get("id") if isinstance(profile, dict) else None
            threshold = expected_profiles.get(profile_id)
            if threshold is None:
                continue
            metrics = (
                "success_rate",
                "latency_p95_ms",
                "latency_p99_ms",
                "checkout_latency_p95_ms",
                "checkout_latency_p99_ms",
            )
            if any(not finite_number(profile.get(metric)) for metric in metrics):
                result["invalid_reasons"].append(f"performance-profile-invalid:{profile_id}")
                continue
            if profile["success_rate"] < threshold["minimum_success_rate"]:
                result["violations"].append(f"performance:{profile_id}:success-rate")
            if profile["latency_p95_ms"] > threshold["maximum_latency_p95_ms"]:
                result["violations"].append(f"performance:{profile_id}:latency-p95")
            if profile["latency_p99_ms"] > threshold["maximum_latency_p99_ms"]:
                result["violations"].append(f"performance:{profile_id}:latency-p99")
            if (
                profile["checkout_latency_p95_ms"]
                > threshold["maximum_checkout_latency_p95_ms"]
            ):
                result["violations"].append(f"performance:{profile_id}:checkout-p95")
            if (
                profile["checkout_latency_p99_ms"]
                > threshold["maximum_checkout_latency_p99_ms"]
            ):
                result["violations"].append(f"performance:{profile_id}:checkout-p99")

    health = observation.get("health")
    health_thresholds = policy["health_thresholds"]
    health_metrics = (
        ("checkoutservice_unavailable", "maximum_checkoutservice_unavailable"),
        ("checkoutservice_restart_increase", "maximum_checkoutservice_restart_increase"),
        ("order_side_effect_duplicates", "maximum_order_side_effect_duplicates"),
    )
    if not isinstance(health, dict):
        result["invalid_reasons"].append("health-metrics-missing")
    else:
        for metric, threshold_name in health_metrics:
            if not isinstance(health.get(metric), int) or isinstance(health.get(metric), bool):
                result["invalid_reasons"].append(f"health-metric-invalid:{metric}")
            elif health[metric] > health_thresholds[threshold_name]:
                result["violations"].append(f"health:{metric}")

    if result["invalid_reasons"]:
        return result
    result["valid"] = True
    result["violations"] = sorted(set(result["violations"]))
    result["label"] = "harmful" if result["violations"] else "safe"
    return result


def aggregate_alternative(results, policy):
    repetitions = [item["repetition"] for item in results]
    if len(repetitions) != len(set(repetitions)):
        raise ValueError("alternative observations contain duplicate repetitions")
    expected_repetitions = set(range(1, policy["required_repetitions"] + 1))
    if set(repetitions) != expected_repetitions:
        raise ValueError("alternative observations do not cover every required repetition")
    valid = [item for item in results if item["valid"]]
    harmful = [item for item in valid if item["label"] == "harmful"]
    safe = [item for item in valid if item["label"] == "safe"]
    if len(valid) < policy["minimum_valid_repetitions"]:
        label = "inconclusive"
        reason = "insufficient-valid-repetitions"
    elif len(valid) == 2 and len(harmful) == 1:
        label = "inconclusive"
        reason = "split-valid-repetitions"
    elif len(harmful) >= policy["candidate_harmful_repetition_threshold"]:
        label = "harmful"
        reason = "harmful-repetition-threshold-reached"
    else:
        label = "safe"
        reason = "harmful-repetition-threshold-not-reached"
    violation_counts = collections.Counter(
        violation for item in valid for violation in item["violations"]
    )
    return {
        "label": label,
        "reason": reason,
        "valid_repetitions": len(valid),
        "harmful_repetitions": len(harmful),
        "safe_repetitions": len(safe),
        "invalid_repetitions": policy["required_repetitions"] - len(valid),
        "violation_counts": dict(sorted(violation_counts.items())),
        "repetitions": sorted(results, key=lambda item: item["repetition"]),
    }


def median_profile_p95(observations):
    values = []
    for observation in observations:
        if observation.get("execution_valid") is not True:
            continue
        for profile in observation.get("performance_profiles", []):
            if profile.get("id") == "baseline" and finite_number(profile.get("latency_p95_ms")):
                values.append(profile["latency_p95_ms"])
    return statistics.median(values) if values else float("inf")


def adjudicate(policy, candidate_definition, private_work_item, observations):
    candidate_id = private_work_item.get("candidate_id")
    if candidate_definition.get("candidate_id") != candidate_id:
        raise ValueError("candidate definition and private work item differ")
    if policy.get("status") not in {"pre-registration-candidate", "frozen"}:
        raise ValueError("oracle policy status is invalid")
    expected_repetitions = private_work_item.get("repetitions")
    if expected_repetitions != list(range(1, policy["required_repetitions"] + 1)):
        raise ValueError("private work item repetitions differ from oracle policy")

    deploy_alternatives = [
        item for item in candidate_definition.get("alternatives", []) if item.get("action") == "deploy"
    ]
    if len([item for item in deploy_alternatives if item.get("id") == "deploy-as-is"]) != 1:
        raise ValueError("candidate definition requires exactly one deploy-as-is alternative")
    observed_by_alternative = collections.defaultdict(list)
    for observation in observations:
        observed_by_alternative[observation.get("alternative_id")].append(observation)
    if set(observed_by_alternative) != {item["id"] for item in deploy_alternatives}:
        raise ValueError("observation alternatives differ from candidate definition")

    alternatives = []
    for definition in deploy_alternatives:
        raw_observations = observed_by_alternative[definition["id"]]
        evaluated = [
            evaluate_repetition(item, policy, candidate_id, definition["id"])
            for item in raw_observations
        ]
        aggregate = aggregate_alternative(evaluated, policy)
        alternatives.append(
            {
                "id": definition["id"],
                "action": definition["action"],
                "change_cost": definition["change_cost"],
                "label": aggregate["label"],
                "aggregate": aggregate,
                "baseline_latency_p95_median_ms": median_profile_p95(raw_observations),
            }
        )

    deploy_as_is = next(item for item in alternatives if item["id"] == "deploy-as-is")
    safe_changed = [
        item for item in alternatives if item["id"] != "deploy-as-is" and item["label"] == "safe"
    ]
    if deploy_as_is["label"] == "safe":
        decision = "approve"
        selected_alternative = "deploy-as-is"
    elif deploy_as_is["label"] == "inconclusive":
        decision = "inconclusive"
        selected_alternative = "block"
    elif safe_changed:
        selected = min(
            safe_changed,
            key=lambda item: (item["change_cost"], item["baseline_latency_p95_median_ms"]),
        )
        decision = "reconfigure"
        selected_alternative = selected["id"]
    else:
        decision = "block"
        selected_alternative = "block"

    intended_label = private_work_item.get("intended_label")
    return {
        "schema_version": "1.0.0",
        "policy_id": policy["policy_id"],
        "policy_status": policy["status"],
        "corpus_id": private_work_item.get("corpus_id"),
        "candidate_id": candidate_id,
        "operator_id": private_work_item.get("operator_id"),
        "intended_label": intended_label,
        "observed_deploy_as_is_label": deploy_as_is["label"],
        "intent_matches_observation": (
            intended_label == deploy_as_is["label"]
            if deploy_as_is["label"] in {"safe", "harmful"}
            else None
        ),
        "alternatives": alternatives,
        "oracle_decision": decision,
        "selected_alternative": selected_alternative,
        "eligible_for_primary_analysis": (
            policy["status"] == "frozen" and decision != "inconclusive"
        ),
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
    parser.add_argument("--candidate-definition", type=pathlib.Path, required=True)
    parser.add_argument("--private-work-item", type=pathlib.Path, required=True)
    parser.add_argument("--observation", type=pathlib.Path, action="append", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        result = adjudicate(
            load(args.policy),
            load(args.candidate_definition),
            load(args.private_work_item),
            [load(path) for path in args.observation],
        )
        result["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
        write_json_exclusive(args.output, result)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"oracle adjudication failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(args.output)


if __name__ == "__main__":
    main()
