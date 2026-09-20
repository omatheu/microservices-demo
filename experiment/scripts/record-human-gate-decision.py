#!/usr/bin/env python3

"""Record a human gate decision without authorizing cloud or operational writes."""

import argparse
import datetime
import hashlib
import json
import pathlib


def load(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record(gate, action, decision, actor, recorded_at, gate_sha256, action_sha256):
    if not actor.strip():
        raise ValueError("human reviewer identity is required")
    if gate.get("candidate_id") != action.get("candidate_id"):
        raise ValueError("deployment gate and action candidate identifiers differ")
    if gate.get("gate_state") != "awaiting-human-confirmation":
        raise ValueError("human review requires a gate awaiting confirmation")
    if gate.get("human_confirmation", {}).get("status") != "pending":
        raise ValueError("deployment gate is not pending human confirmation")
    if action.get("status") != "prepared-awaiting-human-confirmation":
        raise ValueError("deployment action is not ready for human review")
    if action.get("scope") != "isolated-oracle-validation":
        raise ValueError("human gate may authorize only isolated oracle validation")
    if action.get("bindings", {}).get("deployment_gate_sha256") != gate_sha256:
        raise ValueError("deployment action is not bound to this gate")
    if action.get("rollback_plan", {}).get("required") is not True:
        raise ValueError("human approval requires a rollback plan")
    if action.get("cloud_execution_authorized") is not False:
        raise ValueError("action must not pre-authorize cloud execution")
    if action.get("operational_mutation_authorized") is not False:
        raise ValueError("action must not authorize operational mutation")
    if decision not in {"approve-isolated-validation", "reject"}:
        raise ValueError("human decision must approve isolated validation or reject")

    approved = decision == "approve-isolated-validation"
    return {
        "schema_version": "1.0.0",
        "candidate_id": gate["candidate_id"],
        "scope": "isolated-oracle-validation",
        "decision": decision,
        "status": "approved" if approved else "rejected",
        "actor": actor.strip(),
        "recorded_at": recorded_at,
        "bindings": {
            "deployment_gate_sha256": gate_sha256,
            "deployment_action_sha256": action_sha256,
        },
        "selected_alternative": action.get("selected_alternative"),
        "rollback_plan_verified": True,
        "next_action": (
            "request-separate-cost-and-cloud-authorization"
            if approved
            else "do-not-run-isolated-validation"
        ),
        "cloud_execution_authorized": False,
        "operational_mutation_authorized": False,
        "operational_mutation_performed": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deployment-gate", type=pathlib.Path, required=True)
    parser.add_argument("--deployment-action", type=pathlib.Path, required=True)
    parser.add_argument(
        "--decision", choices=("approve-isolated-validation", "reject"), required=True
    )
    parser.add_argument("--actor", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    recorded_at = datetime.datetime.now(datetime.timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    try:
        result = record(
            load(args.deployment_gate),
            load(args.deployment_action),
            args.decision,
            args.actor,
            recorded_at,
            sha256_file(args.deployment_gate),
            sha256_file(args.deployment_action),
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"human gate decision failed: {error}") from error
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
