#!/usr/bin/env python3

import argparse
import datetime
import hashlib
import json
import re
from pathlib import Path


def load_json(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_references(entries):
    if not isinstance(entries, list):
        raise ValueError("Artifact evidence must be a list.")
    references = {}
    for entry in entries:
        component = entry.get("component")
        reference = entry.get("remote_reference")
        if not component or not reference:
            raise ValueError("Artifact evidence must contain immutable component references.")
        if component in references:
            raise ValueError(f"Duplicate artifact evidence for {component}.")
        references[component] = reference
    return references


def compose(
    local_ci,
    staging=None,
    local_ci_sha256=None,
    candidate_definition_sha256=None,
):
    candidate_id = local_ci.get("candidate_id")
    if not candidate_id:
        raise ValueError("Local CI decision is missing candidate_id.")
    if local_ci.get("scope") != "local-pre-staging-ci":
        raise ValueError("Local CI decision has an unexpected scope.")
    if local_ci.get("local_decision") not in {"pass", "block"}:
        raise ValueError("Local CI decision must be pass or block.")

    reasons = []
    immutable_artifacts = []
    if local_ci["local_decision"] == "block":
        reasons.append("local-ci-did-not-pass")
        decision = "block"
        staging_summary = {
            "executed": False,
            "run_id": None,
            "decision": "NOT_RUN",
            "rationale": ["local-ci-blocked-progression"],
        }
    else:
        if staging is None:
            raise ValueError("A passing local CI decision requires a staging decision.")
        if staging.get("candidate_id") != candidate_id:
            raise ValueError("Local CI and staging must evaluate the same candidate.")
        if staging.get("decision") not in {"PASS", "FAIL"}:
            raise ValueError("Staging decision must be PASS or FAIL.")
        artifact_binding = staging.get("artifact_binding")
        if not isinstance(artifact_binding, dict) or artifact_binding.get("decision") != "bound":
            raise ValueError("Staging decision lacks a valid immutable artifact binding.")
        if artifact_binding.get("candidate_id") != candidate_id:
            raise ValueError("Staging artifact binding refers to a different candidate.")
        if artifact_binding.get("local_ci_run_id") != local_ci.get("run_id"):
            raise ValueError("Staging artifact binding refers to a different local CI run.")
        staging_candidate_definition_sha256 = artifact_binding.get(
            "candidate_definition_sha256"
        )
        if staging_candidate_definition_sha256 is not None and not re.fullmatch(
            r"[0-9a-f]{64}", staging_candidate_definition_sha256
        ):
            raise ValueError("Staging candidate definition hash is invalid.")
        if staging.get("mode") == "confirmatory" and staging_candidate_definition_sha256 is None:
            raise ValueError("Confirmatory staging lacks a candidate definition hash.")
        if (
            candidate_definition_sha256 is not None
            and staging_candidate_definition_sha256 != candidate_definition_sha256
        ):
            raise ValueError("Staging evaluated a different candidate definition.")
        candidate_definition_sha256 = staging_candidate_definition_sha256
        if (
            local_ci_sha256 is not None
            and artifact_binding.get("local_ci_decision_sha256") != local_ci_sha256
        ):
            raise ValueError("Staging artifact binding does not match the local CI decision hash.")
        local_artifacts = artifact_references(local_ci.get("artifacts", []))
        staging_artifacts = artifact_references(artifact_binding.get("artifacts", []))
        if local_artifacts != staging_artifacts:
            raise ValueError("Staging did not evaluate the artifacts published by local CI.")
        immutable_artifacts = [
            {"component": component, "remote_reference": reference}
            for component, reference in sorted(local_artifacts.items())
        ]

        staging_summary = {
            "executed": True,
            "run_id": staging.get("run_id"),
            "decision": staging["decision"],
            "rationale": staging.get("rationale", []),
            "artifact_binding_verified": True,
            "candidate_definition_sha256": candidate_definition_sha256,
        }
        if staging["decision"] == "PASS":
            decision = "approve"
        else:
            decision = "block"
            reasons.append("traditional-staging-did-not-pass")

    failed_gates = [
        gate.get("id")
        for gate in local_ci.get("gates", [])
        if gate.get("required") is True and gate.get("status") != "pass"
    ]
    reasons.extend(f"local-gate-failed:{gate_id}" for gate_id in failed_gates)

    return {
        "schema_version": "1.0.0",
        "mechanism": "conventional-ci-cd-with-staging",
        "candidate_id": candidate_id,
        "decision": decision,
        "reasons": reasons,
        "local_ci": {
            "run_id": local_ci.get("run_id"),
            "decision": local_ci["local_decision"],
            "failed_required_gates": local_ci.get("failed_required_gates"),
        },
        "staging": staging_summary,
        "immutable_artifacts": immutable_artifacts,
        "candidate_definition_sha256": candidate_definition_sha256,
        "pdt_consulted": False,
        "control_decision_sealed": True,
        "operational_mutation_performed": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-ci-decision", required=True)
    parser.add_argument("--staging-decision")
    parser.add_argument("--candidate-definition")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    local_path = Path(args.local_ci_decision)
    staging_path = Path(args.staging_decision) if args.staging_decision else None
    local_ci = load_json(local_path)
    staging = load_json(staging_path) if staging_path else None
    candidate_path = Path(args.candidate_definition) if args.candidate_definition else None
    candidate_definition_sha256 = None
    if candidate_path:
        candidate = load_json(candidate_path)
        if candidate.get("candidate_id") != local_ci.get("candidate_id"):
            raise SystemExit("Candidate definition and local CI candidate differ.")
        candidate_definition_sha256 = sha256_file(candidate_path)

    try:
        output = compose(
            local_ci,
            staging,
            sha256_file(local_path),
            candidate_definition_sha256,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error

    now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    output["sealed_at"] = now
    output["evidence"] = {
        "local_ci_decision": {
            "path": str(local_path),
            "sha256": sha256_file(local_path),
        },
        "staging_decision": (
            {
                "path": str(staging_path),
                "sha256": sha256_file(staging_path),
            }
            if staging_path
            else None
        ),
        "candidate_definition": (
            {"path": str(candidate_path), "sha256": candidate_definition_sha256}
            if candidate_path
            else None
        ),
    }
    Path(args.output).write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
