#!/usr/bin/env python3

"""Prepare, but never execute, the PDT-selected isolated validation action."""

import argparse
import copy
import datetime
import hashlib
import json
import pathlib
import re


IMMUTABLE_IMAGE = re.compile(r"^[a-z0-9.-]+/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$")


def load(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checkout_workload(snapshot):
    matches = [
        item
        for item in snapshot.get("synchronized_state", {}).get("workloads", [])
        if item.get("name") == "checkoutservice"
    ]
    if len(matches) != 1:
        raise ValueError("snapshot must contain exactly one checkoutservice workload")
    return matches[0]


def validate_resource_map(value, label):
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{label} must be a non-empty resource map")
    if not set(value).issubset({"cpu", "memory", "ephemeral-storage"}):
        raise ValueError(f"{label} contains an unsupported resource")
    if not all(isinstance(item, str) and item for item in value.values()):
        raise ValueError(f"{label} resource quantities must be non-empty strings")


def validate_patch(patch):
    if not isinstance(patch, dict) or set(patch) != {"spec"}:
        raise ValueError("configuration patch may contain only spec")
    spec = patch["spec"]
    if not isinstance(spec, dict) or not spec or not set(spec).issubset(
        {"replicas", "template"}
    ):
        raise ValueError("configuration patch contains an unsupported spec field")
    if "replicas" in spec and (
        not isinstance(spec["replicas"], int) or isinstance(spec["replicas"], bool)
        or spec["replicas"] < 0
        or spec["replicas"] > 3
    ):
        raise ValueError("checkoutservice replicas must be an integer between 0 and 3")
    if "template" not in spec:
        return
    template = spec["template"]
    if not isinstance(template, dict) or set(template) != {"spec"}:
        raise ValueError("configuration template may contain only spec")
    pod_spec = template["spec"]
    if not isinstance(pod_spec, dict) or set(pod_spec) != {"containers"}:
        raise ValueError("configuration pod spec may contain only containers")
    containers = pod_spec["containers"]
    if not isinstance(containers, list) or len(containers) != 1:
        raise ValueError("configuration patch must target exactly one container")
    container = containers[0]
    if not isinstance(container, dict) or set(container) != {"name", "resources"}:
        raise ValueError("configuration container may contain only name and resources")
    if container.get("name") != "server":
        raise ValueError("configuration patch may target only the server container")
    resources = container["resources"]
    if not isinstance(resources, dict) or not resources or not set(resources).issubset(
        {"requests", "limits"}
    ):
        raise ValueError("configuration contains an unsupported resources field")
    for key, value in resources.items():
        validate_resource_map(value, f"resources.{key}")


def validate_changes(changes):
    if not isinstance(changes, list):
        raise ValueError("selected alternative configuration must be a list")
    result = copy.deepcopy(changes)
    for change in result:
        if not isinstance(change, dict) or set(change) != {"deployment", "patch"}:
            raise ValueError("configuration change must contain deployment and patch")
        if change.get("deployment") != "checkoutservice":
            raise ValueError("PDT actions may configure only checkoutservice")
        validate_patch(change.get("patch"))
    return result


def artifact_list(control, pdt):
    artifacts = control.get("immutable_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("approved control must contain immutable artifacts")
    if artifacts != pdt.get("artifact_binding", {}).get("immutable_artifacts"):
        raise ValueError("control and PDT immutable artifact bindings differ")
    for artifact in artifacts:
        if (
            not isinstance(artifact, dict)
            or not artifact.get("component")
            or not IMMUTABLE_IMAGE.fullmatch(str(artifact.get("remote_reference")))
        ):
            raise ValueError("action contains an invalid immutable artifact")
    return copy.deepcopy(artifacts)


def prepare(candidate, snapshot, control, pdt, gate, bindings):
    candidate_id = candidate.get("candidate_id")
    if not candidate_id or candidate.get("twin_object") != "checkoutservice":
        raise ValueError("candidate must identify checkoutservice as the twin object")
    if any(
        value != candidate_id
        for value in (
            control.get("candidate_id"),
            pdt.get("candidate"),
            gate.get("candidate_id"),
        )
    ):
        raise ValueError("candidate, control, PDT and gate identifiers differ")
    if (
        control.get("mechanism") != "conventional-ci-cd-with-staging"
        or control.get("control_decision_sealed") is not True
        or control.get("decision") != "approve"
    ):
        raise ValueError("deployment action requires a sealed conventional approval")
    if gate.get("gate_state") != "awaiting-human-confirmation":
        raise ValueError("deployment action requires a gate awaiting human confirmation")
    if gate.get("operational_mutation_performed") is not False:
        raise ValueError("deployment action must be prepared before operational mutation")
    if gate.get("rollback_plan_required_before_mutation") is not True:
        raise ValueError("deployment gate must require a rollback plan")
    if gate.get("human_confirmation", {}).get("status") != "pending":
        raise ValueError("deployment gate human confirmation must still be pending")

    decision = pdt.get("decision")
    selected_id = pdt.get("selected_alternative")
    if decision not in {"approve", "reconfigure"}:
        raise ValueError("only approve or reconfigure produces a deployable action")
    alternatives = [
        item for item in candidate.get("alternatives", []) if item.get("id") == selected_id
    ]
    if len(alternatives) != 1 or alternatives[0].get("action") != "deploy":
        raise ValueError("selected PDT alternative must be uniquely deployable")
    alternative = alternatives[0]
    changes = validate_changes(alternative.get("configuration_changes"))
    if pdt.get("recommended_configuration") != changes:
        raise ValueError("PDT recommendation differs from the selected alternative")
    if decision == "approve" and selected_id != "deploy-as-is":
        raise ValueError("PDT approval must select deploy-as-is")
    if decision == "reconfigure" and (selected_id == "deploy-as-is" or not changes):
        raise ValueError("PDT reconfiguration must select a changed deployable alternative")
    if gate.get("pdt", {}).get("decision") != decision or gate.get("pdt", {}).get(
        "selected_alternative"
    ) != selected_id:
        raise ValueError("deployment gate and PDT selected action differ")
    if pdt.get("snapshot_id") != snapshot.get("snapshot_id"):
        raise ValueError("PDT decision and operational snapshot differ")
    binding = snapshot.get("binding", {})
    if (
        binding.get("source_namespace") != "operational"
        or binding.get("twin_object")
        != {"kind": "Deployment", "name": "checkoutservice"}
    ):
        raise ValueError("snapshot is not bound to the operational checkoutservice")
    source = checkout_workload(snapshot)
    artifacts = artifact_list(control, pdt)
    if pdt.get("artifact_binding", {}).get("candidate_definition_sha256") != control.get(
        "candidate_definition_sha256"
    ):
        raise ValueError("control and PDT candidate definition bindings differ")

    return {
        "schema_version": "1.0.0",
        "candidate_id": candidate_id,
        "status": "prepared-awaiting-human-confirmation",
        "scope": "isolated-oracle-validation",
        "pdt_decision": decision,
        "selected_alternative": selected_id,
        "target": {
            "namespace": "oracle",
            "kind": "Deployment",
            "name": "checkoutservice",
            "publicly_exposed": False,
        },
        "forward_action": {
            "immutable_artifacts": artifacts,
            "configuration_changes": changes,
        },
        "source_snapshot": {
            "snapshot_id": snapshot["snapshot_id"],
            "namespace": "operational",
            "checkoutservice_uid": source.get("uid"),
            "checkoutservice_generation": source.get("generation"),
            "checkoutservice_resource_version": source.get("resource_version"),
        },
        "preconditions": {
            "human_confirmation_required": True,
            "separate_cloud_execution_authorization_required": True,
            "cost_review_required": True,
            "oracle_namespace_must_be_empty": True,
        },
        "rollback_plan": {
            "required": True,
            "strategy": "delete-ephemeral-runtime-and-verify-empty",
            "namespace": "oracle",
            "selector": "experiment-role=oracle-runtime",
            "preserves_operational_namespace": True,
        },
        "bindings": copy.deepcopy(bindings),
        "human_confirmation": {"status": "pending", "actor": None, "recorded_at": None},
        "cloud_execution_authorized": False,
        "operational_mutation_authorized": False,
        "operational_mutation_performed": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-definition", type=pathlib.Path, required=True)
    parser.add_argument("--snapshot", type=pathlib.Path, required=True)
    parser.add_argument("--conventional-decision", type=pathlib.Path, required=True)
    parser.add_argument("--pdt-decision", type=pathlib.Path, required=True)
    parser.add_argument("--deployment-gate", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    paths = {
        "candidate_definition": args.candidate_definition,
        "snapshot": args.snapshot,
        "conventional_decision": args.conventional_decision,
        "pdt_decision": args.pdt_decision,
        "deployment_gate": args.deployment_gate,
    }
    bindings = {f"{name}_sha256": sha256_file(path) for name, path in paths.items()}
    try:
        result = prepare(
            load(args.candidate_definition),
            load(args.snapshot),
            load(args.conventional_decision),
            load(args.pdt_decision),
            load(args.deployment_gate),
            bindings,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"deployment action preparation failed: {error}") from error
    result["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    result["evidence"] = {name: str(path) for name, path in paths.items()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
