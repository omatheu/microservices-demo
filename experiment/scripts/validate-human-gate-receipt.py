#!/usr/bin/env python3

"""Verify the protected human decision before isolated oracle execution."""

import argparse
import hashlib
import json
import pathlib
import re


SHA256 = re.compile(r"^[0-9a-f]{64}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def load(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(paths, review_environment):
    documents = {name: load(path) for name, path in paths.items()}
    hashes = {name: sha256_file(path) for name, path in paths.items()}
    candidate = documents["candidate_definition"]
    snapshot = documents["snapshot"]
    control = documents["conventional_decision"]
    pdt = documents["pdt_decision"]
    gate = documents["deployment_gate"]
    action = documents["deployment_action"]
    receipt = documents["human_gate_decision"]
    approval_history = documents["github_approval_history"]

    candidate_id = candidate.get("candidate_id")
    require(candidate_id, "candidate identifier is required")
    require(
        candidate.get("twin_object") == "checkoutservice",
        "human gate must remain scoped to checkoutservice",
    )
    require(
        all(
            value == candidate_id
            for value in (
                control.get("candidate_id"),
                pdt.get("candidate"),
                gate.get("candidate_id"),
                action.get("candidate_id"),
                receipt.get("candidate_id"),
            )
        ),
        "candidate identifiers differ across the sealed decision chain",
    )
    require(
        control.get("mechanism") == "conventional-ci-cd-with-staging"
        and control.get("decision") == "approve"
        and control.get("control_decision_sealed") is True,
        "human-approved oracle action requires a sealed conventional approval",
    )
    require(
        pdt.get("snapshot_id") == snapshot.get("snapshot_id"),
        "PDT decision and operational snapshot differ",
    )
    require(
        snapshot.get("binding", {}).get("source_namespace") == "operational"
        and snapshot.get("binding", {}).get("twin_object")
        == {"kind": "Deployment", "name": "checkoutservice"},
        "snapshot is not bound to operational/checkoutservice",
    )

    pdt_decision = pdt.get("decision")
    selected = pdt.get("selected_alternative")
    require(
        pdt_decision in {"approve", "reconfigure"} and selected,
        "PDT decision is not eligible for human-approved validation",
    )
    require(
        gate.get("gate_state") == "awaiting-human-confirmation"
        and gate.get("human_confirmation", {}).get("status") == "pending"
        and gate.get("pdt", {}).get("decision") == pdt_decision
        and gate.get("pdt", {}).get("selected_alternative") == selected,
        "deployment gate does not represent the selected PDT action",
    )

    require(
        action.get("status") == "prepared-awaiting-human-confirmation"
        and action.get("scope") == "isolated-oracle-validation"
        and action.get("selected_alternative") == selected,
        "deployment action is not the selected isolated validation action",
    )
    require(
        action.get("target")
        == {
            "namespace": "oracle",
            "kind": "Deployment",
            "name": "checkoutservice",
            "publicly_exposed": False,
        },
        "deployment action target must be the private oracle checkoutservice",
    )
    require(
        action.get("rollback_plan", {}).get("required") is True
        and action.get("rollback_plan", {}).get("namespace") == "oracle"
        and action.get("rollback_plan", {}).get("preserves_operational_namespace")
        is True,
        "deployment action lacks the required isolated rollback plan",
    )
    require(
        action.get("cloud_execution_authorized") is False
        and action.get("operational_mutation_authorized") is False
        and action.get("operational_mutation_performed") is False,
        "deployment action must not pre-authorize cloud or operational mutation",
    )

    expected_action_bindings = {
        "candidate_definition_sha256": hashes["candidate_definition"],
        "snapshot_sha256": hashes["snapshot"],
        "conventional_decision_sha256": hashes["conventional_decision"],
        "pdt_decision_sha256": hashes["pdt_decision"],
        "deployment_gate_sha256": hashes["deployment_gate"],
    }
    require(
        action.get("bindings") == expected_action_bindings,
        "deployment action bindings do not match the supplied decision chain",
    )

    require(
        receipt.get("scope") == "isolated-oracle-validation"
        and receipt.get("decision") == "approve-isolated-validation"
        and receipt.get("status") == "approved"
        and receipt.get("selected_alternative") == selected,
        "human receipt does not approve the selected isolated validation",
    )
    require(
        receipt.get("rollback_plan_verified") is True
        and receipt.get("next_action")
        == "request-separate-cost-and-cloud-authorization",
        "human receipt does not preserve rollback and separate cost authorization",
    )
    require(
        receipt.get("cloud_execution_authorized") is False
        and receipt.get("operational_mutation_authorized") is False
        and receipt.get("operational_mutation_performed") is False,
        "human receipt must not itself authorize cloud or operational mutation",
    )
    receipt_bindings = receipt.get("bindings", {})
    require(
        receipt_bindings.get("deployment_gate_sha256")
        == hashes["deployment_gate"]
        and receipt_bindings.get("deployment_action_sha256")
        == hashes["deployment_action"]
        and receipt_bindings.get("github_approval_history_sha256")
        == hashes["github_approval_history"],
        "human receipt bindings do not match gate, action and approval history",
    )

    evidence = receipt.get("human_review_evidence", {})
    actor = receipt.get("actor")
    require(
        evidence.get("source") == "github-environment-protection"
        and evidence.get("state") == "approved"
        and evidence.get("environment") == review_environment
        and evidence.get("reviewer") == actor
        and evidence.get("approval_history_sha256")
        == hashes["github_approval_history"],
        "receipt lacks a matching protected GitHub environment approval",
    )
    require(
        isinstance(actor, str) and actor.strip(),
        "protected human reviewer identity is required",
    )
    require(
        isinstance(evidence.get("repository"), str)
        and REPOSITORY.fullmatch(evidence["repository"]),
        "protected review repository is invalid",
    )
    require(
        isinstance(evidence.get("workflow_run_id"), int)
        and evidence["workflow_run_id"] > 0,
        "protected review workflow run identifier is invalid",
    )
    require(
        isinstance(approval_history, list),
        "GitHub approval history must be a list",
    )
    matching_reviews = [
        review
        for review in approval_history
        if isinstance(review, dict)
        and review.get("state") == "approved"
        and review.get("user", {}).get("login") == actor
        and any(
            isinstance(environment, dict)
            and environment.get("name") == review_environment
            for environment in review.get("environments", [])
        )
    ]
    require(
        matching_reviews,
        "raw GitHub history has no matching protected environment approval",
    )
    require(
        evidence.get("comment") == (matching_reviews[-1].get("comment") or ""),
        "receipt review comment differs from the GitHub approval history",
    )
    require(
        all(SHA256.fullmatch(value) for value in receipt_bindings.values()),
        "human receipt contains an invalid SHA-256 binding",
    )

    return {
        "schema_version": "1.0.0",
        "validated": True,
        "candidate_id": candidate_id,
        "selected_alternative": selected,
        "reviewer": actor,
        "review_environment": review_environment,
        "repository": evidence["repository"],
        "workflow_run_id": evidence["workflow_run_id"],
        "bindings": {
            "deployment_gate_sha256": hashes["deployment_gate"],
            "deployment_action_sha256": hashes["deployment_action"],
            "human_gate_decision_sha256": hashes["human_gate_decision"],
            "github_approval_history_sha256": hashes["github_approval_history"],
        },
        "cloud_execution_authorized_by_receipt": False,
        "operational_mutation_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-definition", type=pathlib.Path, required=True)
    parser.add_argument("--snapshot", type=pathlib.Path, required=True)
    parser.add_argument("--conventional-decision", type=pathlib.Path, required=True)
    parser.add_argument("--pdt-decision", type=pathlib.Path, required=True)
    parser.add_argument("--deployment-gate", type=pathlib.Path, required=True)
    parser.add_argument("--deployment-action", type=pathlib.Path, required=True)
    parser.add_argument("--human-gate-decision", type=pathlib.Path, required=True)
    parser.add_argument("--github-approval-history", type=pathlib.Path, required=True)
    parser.add_argument(
        "--review-environment", default="tcc-deployment-approval"
    )
    args = parser.parse_args()
    paths = {
        "candidate_definition": args.candidate_definition,
        "snapshot": args.snapshot,
        "conventional_decision": args.conventional_decision,
        "pdt_decision": args.pdt_decision,
        "deployment_gate": args.deployment_gate,
        "deployment_action": args.deployment_action,
        "human_gate_decision": args.human_gate_decision,
        "github_approval_history": args.github_approval_history,
    }
    try:
        result = validate(paths, args.review_environment)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"human gate validation failed: {error}") from error
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
