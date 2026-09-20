#!/usr/bin/env python3

import argparse
import datetime
import json
from pathlib import Path


def load(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def safety_violations(observed, thresholds):
    violations = []
    if observed["success_rate"] < thresholds["minimum_success_rate"]:
        violations.append("success_rate_below_threshold")
    if observed["locust"]["success_rate"] < thresholds["minimum_success_rate"]:
        violations.append("locust_success_rate_below_threshold")
    if observed["latency_ms"]["p95"] > thresholds["maximum_latency_p95_ms"]:
        violations.append("latency_p95_above_threshold")
    if observed["latency_ms"]["p99"] > thresholds["maximum_latency_p99_ms"]:
        violations.append("latency_p99_above_threshold")
    if observed["checkout"]["latency_p95_ms"] > thresholds["maximum_checkout_latency_p95_ms"]:
        violations.append("checkout_latency_p95_above_threshold")
    if observed["checkout"]["latency_p99_ms"] > thresholds["maximum_checkout_latency_p99_ms"]:
        violations.append("checkout_latency_p99_above_threshold")
    functional_failures = (
        observed["failures"],
        observed["checkout"]["failures"],
        observed["checkout"]["negative_paths"]["failures"],
    )
    if any(value > thresholds["maximum_functional_failures"] for value in functional_failures):
        violations.append("functional_failures_above_threshold")
    if observed["checkout"]["unavailable"] > thresholds["maximum_unavailable_deployments"]:
        violations.append("checkoutservice_unavailable_above_threshold")
    if observed["checkout"]["restart_increase"] > thresholds["maximum_restart_increase"]:
        violations.append("checkoutservice_restart_increase_above_threshold")
    return violations


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--thresholds", required=True)
    parser.add_argument("--model-policy", required=True)
    parser.add_argument("--alternatives-dir", required=True)
    parser.add_argument("--repetition", type=int, default=1)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    candidate = load(args.candidate)
    snapshot = load(args.snapshot)
    thresholds = load(args.thresholds)["thresholds"]
    model_policy = load(args.model_policy)
    alternatives = []

    for definition in candidate["alternatives"]:
        result = {
            "id": definition["id"],
            "action": definition["action"],
            "configuration_changes": definition["configuration_changes"],
            "change_cost": definition["change_cost"],
        }
        if definition["action"] == "block":
            result.update({"safe": True, "predicted_metrics": None, "confidence": 1.0, "violations": []})
        else:
            alternative_dir = Path(args.alternatives_dir) / definition["id"]
            summary = load(alternative_dir / "summary.json")
            observed = summary["observed"]
            if "unavailable" not in observed["checkout"]:
                deployments_end = load(alternative_dir / "deployments-end.json")
                checkout_deployment = next(
                    item for item in deployments_end["items"] if item["metadata"]["name"] == "checkoutservice"
                )
                desired = checkout_deployment["spec"].get("replicas", 0)
                available = checkout_deployment.get("status", {}).get("availableReplicas", 0)
                observed["checkout"]["unavailable"] = int(desired != available)
                pods_start = load(alternative_dir / "pods-start.json")
                pods_end = load(alternative_dir / "pods-end.json")

                def checkout_restarts(pods):
                    return sum(
                        container.get("restartCount", 0)
                        for pod in pods["items"]
                        if pod["metadata"].get("labels", {}).get("app") == "checkoutservice"
                        for container in pod.get("status", {}).get("containerStatuses", [])
                    )

                observed["checkout"]["restart_increase"] = checkout_restarts(pods_end) - checkout_restarts(pods_start)
                observed["context"] = {
                    "unavailable_deployments": observed.pop("unavailable_deployments"),
                    "restart_increase": observed.pop("restart_increase"),
                }
            violations = safety_violations(observed, thresholds)

            confidence_config = model_policy["confidence"]
            coverage = min(1.0, observed["samples"] / confidence_config["sample_target"])
            confidence = confidence_config["base"] + (
                confidence_config["maximum"] - confidence_config["base"]
            ) * coverage
            confidence -= observed["checkout"]["restart_increase"] * confidence_config["penalty_per_restart"]
            confidence = round(max(0.0, min(confidence_config["maximum"], confidence)), 3)
            result.update({
                "safe": not violations,
                "predicted_metrics": observed,
                "confidence": confidence,
                "violations": violations,
                "evidence": f"alternatives/{definition['id']}/summary.json",
            })
        alternatives.append(result)

    as_is = next(item for item in alternatives if item["id"] == "deploy-as-is")
    safe_changed = [item for item in alternatives if item["action"] == "deploy" and item["id"] != "deploy-as-is" and item["safe"]]
    if as_is["safe"]:
        selected = as_is
        decision = "approve"
        rationale = ["deploy-as-is satisfies every configured safety threshold"]
    elif safe_changed:
        selected = sorted(safe_changed, key=lambda item: (item["change_cost"], item["predicted_metrics"]["latency_ms"]["p95"]))[0]
        decision = "reconfigure"
        rationale = ["deploy-as-is violates safety thresholds", "a counterfactual reconfiguration satisfies every threshold"]
    else:
        selected = next(item for item in alternatives if item["action"] == "block")
        decision = "block"
        rationale = ["no deployable counterfactual satisfies every configured safety threshold"]

    output = {
        "schema_version": "1.0.0",
        "model_id": model_policy["model_id"],
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "candidate": candidate["candidate_id"],
        "repetition": args.repetition,
        "snapshot_id": snapshot["snapshot_id"],
        "alternatives_evaluated": alternatives,
        "decision": decision,
        "selected_alternative": selected["id"],
        "recommended_configuration": selected["configuration_changes"],
        "predicted_metrics": selected["predicted_metrics"],
        "confidence": selected["confidence"],
        "rationale": rationale,
        "human_confirmation_required": True,
    }
    Path(args.output).write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
