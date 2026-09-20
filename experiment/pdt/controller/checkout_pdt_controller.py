#!/usr/bin/env python3

import argparse
import datetime
import hashlib
import json
import pathlib
import re


CONTROLLER_ID = "checkout-pdt-controller-v1"
IMAGE_PATTERN = re.compile(r"^[a-z0-9.-]+/[a-z0-9._/-]+@sha256:[a-f0-9]{64}$")
FORBIDDEN_CANDIDATE_KEYS = {
    "operator",
    "operator_id",
    "parameters",
    "intended_label",
    "expected_label",
    "stratum",
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


def write_json(value, output):
    rendered = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if str(output) == "-":
        print(rendered, end="")
    else:
        pathlib.Path(output).write_text(rendered, encoding="utf-8")


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def nested_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from nested_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from nested_keys(child)


def build_execution_plan(
    candidate,
    candidate_sha256,
    conventional_decision,
    conventional_decision_sha256,
    snapshot,
    thresholds_document,
    thresholds_sha256,
    model_policy,
    model_policy_sha256,
    repetition,
):
    candidate_id = candidate.get("candidate_id")
    if not isinstance(candidate_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", candidate_id):
        raise ValueError("candidate ID is missing or invalid")
    if candidate.get("twin_object") != "checkoutservice":
        raise ValueError("candidate twin object must be checkoutservice")
    leaked_keys = sorted(set(nested_keys(candidate)) & FORBIDDEN_CANDIDATE_KEYS)
    if leaked_keys:
        raise ValueError(f"public candidate contains forbidden oracle keys: {', '.join(leaked_keys)}")

    alternatives = candidate.get("alternatives")
    if not isinstance(alternatives, list) or not 2 <= len(alternatives) <= 3:
        raise ValueError("candidate must contain two or three counterfactual alternatives")
    alternative_ids = [item.get("id") for item in alternatives if isinstance(item, dict)]
    if len(alternative_ids) != len(alternatives) or len(set(alternative_ids)) != len(alternative_ids):
        raise ValueError("candidate alternative IDs are invalid or duplicated")
    deploy_as_is = [item for item in alternatives if item.get("id") == "deploy-as-is" and item.get("action") == "deploy"]
    blocks = [item for item in alternatives if item.get("action") == "block"]
    deployable = [item for item in alternatives if item.get("action") == "deploy"]
    if len(deploy_as_is) != 1 or len(blocks) != 1 or len(deployable) > 2:
        raise ValueError("candidate alternatives must include deploy-as-is, block and at most one reconfiguration")
    for item in alternatives:
        if item.get("action") not in {"deploy", "block"}:
            raise ValueError("candidate alternative action is invalid")
        if not isinstance(item.get("configuration_changes"), list):
            raise ValueError("candidate configuration changes must be a list")
        for change in item["configuration_changes"]:
            if change.get("deployment") != "checkoutservice":
                raise ValueError("PDT reconfiguration is limited to checkoutservice")

    if (
        conventional_decision.get("mechanism") != "conventional-ci-cd-with-staging"
        or conventional_decision.get("candidate_id") != candidate_id
        or conventional_decision.get("decision") != "approve"
        or conventional_decision.get("control_decision_sealed") is not True
        or conventional_decision.get("candidate_definition_sha256") != candidate_sha256
    ):
        raise ValueError("controller requires the matching sealed conventional approval")
    artifacts = conventional_decision.get("immutable_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("sealed conventional decision has no immutable artifacts")
    if any(not IMAGE_PATTERN.fullmatch(item.get("remote_reference", "")) for item in artifacts):
        raise ValueError("sealed conventional artifact is not an immutable registry digest")

    binding = snapshot.get("binding", {})
    if (
        binding.get("twin_object") != {"kind": "Deployment", "name": "checkoutservice"}
        or binding.get("relationship") != "observes-and-simulates"
        or binding.get("target_namespace") != "pdt"
        or not binding.get("source_namespace_uid")
    ):
        raise ValueError("snapshot is not bound to the checkoutservice PDT")
    workloads = snapshot.get("synchronized_state", {}).get("workloads", [])
    if sum(item.get("name") == "checkoutservice" for item in workloads) != 1:
        raise ValueError("snapshot must contain exactly one checkoutservice workload")
    if not snapshot.get("snapshot_id"):
        raise ValueError("snapshot ID is missing")

    thresholds = thresholds_document.get("thresholds")
    if not isinstance(thresholds, dict) or thresholds.get("minimum_success_rate", 0) <= 0:
        raise ValueError("safety thresholds are invalid")
    if model_policy.get("model_id") != "empirical-counterfactual-v1":
        raise ValueError("PDT model policy is invalid")
    if not isinstance(repetition, int) or repetition < 1:
        raise ValueError("repetition must be a positive integer")

    return {
        "schema_version": "1.0.0",
        "controller_id": CONTROLLER_ID,
        "generated_at": utc_now(),
        "candidate_id": candidate_id,
        "repetition": repetition,
        "twin_object": "checkoutservice",
        "source_binding": {
            "snapshot_id": snapshot["snapshot_id"],
            "project_id": binding.get("project_id"),
            "cluster_name": binding.get("cluster_name"),
            "source_namespace": binding.get("source_namespace"),
            "source_namespace_uid": binding["source_namespace_uid"],
            "target_namespace": "pdt",
            "relationship": "observes-and-simulates",
        },
        "sealed_inputs": {
            "candidate_definition_sha256": candidate_sha256,
            "conventional_decision_sha256": conventional_decision_sha256,
            "thresholds_sha256": thresholds_sha256,
            "model_policy_sha256": model_policy_sha256,
            "immutable_artifacts": artifacts,
        },
        "counterfactuals": [
            {
                "id": item["id"],
                "action": item["action"],
                "configuration_changes": item["configuration_changes"],
                "change_cost": item["change_cost"],
            }
            for item in alternatives
        ],
        "execution": {
            "mode": "sequential",
            "namespace": "pdt",
            "maximum_deployable_alternatives": 2,
            "operational_mutation_allowed": False,
            "cleanup_required_between_alternatives": True,
        },
        "decision_contract": {
            "model_id": model_policy["model_id"],
            "allowed_decisions": ["approve", "block", "reconfigure"],
            "human_confirmation_required": True,
        },
    }


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


def normalize_observed(observed, alternative_dir):
    if "unavailable" in observed["checkout"]:
        return observed
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
    return observed


def decide(candidate, snapshot, thresholds_document, model_policy, alternatives_dir, repetition):
    thresholds = thresholds_document["thresholds"]
    alternatives = []
    alternatives_dir = pathlib.Path(alternatives_dir)
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
            alternative_dir = alternatives_dir / definition["id"]
            observed = normalize_observed(load(alternative_dir / "summary.json")["observed"], alternative_dir)
            violations = safety_violations(observed, thresholds)
            confidence_config = model_policy["confidence"]
            coverage = min(1.0, observed["samples"] / confidence_config["sample_target"])
            confidence = confidence_config["base"] + (
                confidence_config["maximum"] - confidence_config["base"]
            ) * coverage
            confidence -= observed["checkout"]["restart_increase"] * confidence_config["penalty_per_restart"]
            confidence = round(max(0.0, min(confidence_config["maximum"], confidence)), 3)
            result.update(
                {
                    "safe": not violations,
                    "predicted_metrics": observed,
                    "confidence": confidence,
                    "violations": violations,
                    "evidence": f"alternatives/{definition['id']}/summary.json",
                }
            )
        alternatives.append(result)

    as_is = next(item for item in alternatives if item["id"] == "deploy-as-is")
    safe_changed = [
        item
        for item in alternatives
        if item["action"] == "deploy" and item["id"] != "deploy-as-is" and item["safe"]
    ]
    if as_is["safe"]:
        selected, decision_value = as_is, "approve"
        rationale = ["deploy-as-is satisfies every configured safety threshold"]
    elif safe_changed:
        selected = sorted(
            safe_changed,
            key=lambda item: (item["change_cost"], item["predicted_metrics"]["latency_ms"]["p95"]),
        )[0]
        decision_value = "reconfigure"
        rationale = [
            "deploy-as-is violates safety thresholds",
            "a counterfactual reconfiguration satisfies every threshold",
        ]
    else:
        selected = next(item for item in alternatives if item["action"] == "block")
        decision_value = "block"
        rationale = ["no deployable counterfactual satisfies every configured safety threshold"]

    return {
        "schema_version": "1.0.0",
        "controller_id": CONTROLLER_ID,
        "model_id": model_policy["model_id"],
        "generated_at": utc_now(),
        "candidate": candidate["candidate_id"],
        "repetition": repetition,
        "snapshot_id": snapshot["snapshot_id"],
        "alternatives_evaluated": alternatives,
        "decision": decision_value,
        "selected_alternative": selected["id"],
        "recommended_configuration": selected["configuration_changes"],
        "predicted_metrics": selected["predicted_metrics"],
        "confidence": selected["confidence"],
        "rationale": rationale,
        "human_confirmation_required": True,
        "operational_mutation_performed": False,
    }


def build_parser():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("plan", "decide"):
        child = subparsers.add_parser(command)
        child.add_argument("--candidate", required=True)
        child.add_argument("--snapshot", required=True)
        child.add_argument("--thresholds", required=True)
        child.add_argument("--model-policy", required=True)
        child.add_argument("--repetition", type=int, default=1)
        child.add_argument("--output", required=True)
        if command == "plan":
            child.add_argument("--conventional-decision", required=True)
        else:
            child.add_argument("--alternatives-dir", required=True)
    return parser


def main():
    args = build_parser().parse_args()
    try:
        candidate = load(args.candidate)
        snapshot = load(args.snapshot)
        thresholds = load(args.thresholds)
        model_policy = load(args.model_policy)
        if args.command == "plan":
            conventional = load(args.conventional_decision)
            result = build_execution_plan(
                candidate,
                sha256_file(args.candidate),
                conventional,
                sha256_file(args.conventional_decision),
                snapshot,
                thresholds,
                sha256_file(args.thresholds),
                model_policy,
                sha256_file(args.model_policy),
                args.repetition,
            )
        else:
            result = decide(
                candidate,
                snapshot,
                thresholds,
                model_policy,
                args.alternatives_dir,
                args.repetition,
            )
    except (OSError, KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"checkout-pdt-controller failed: {error}") from error
    write_json(result, args.output)


if __name__ == "__main__":
    main()
