#!/usr/bin/env python3

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import stat
import sys


FORBIDDEN_RECEIPT_KEYS = {
    "context_dependency",
    "intended_label",
    "operator_id",
    "parameters",
    "stratum",
    "target_component",
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


def private_file(path):
    mode = stat.S_IMODE(pathlib.Path(path).stat().st_mode)
    return mode & 0o077 == 0


def recursively_find_keys(value, forbidden):
    findings = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in forbidden:
                findings.append(key)
            findings.extend(recursively_find_keys(child, forbidden))
    elif isinstance(value, list):
        for child in value:
            findings.extend(recursively_find_keys(child, forbidden))
    return findings


def find_public_candidate(public, candidate_id):
    matches = [
        item for item in public.get("execution_order", []) if item.get("candidate_id") == candidate_id
    ]
    if len(matches) != 1:
        raise ValueError("candidate must occur exactly once in the public corpus")
    return matches[0]


def find_oracle_candidate(oracle, candidate_id):
    matches = [
        item for item in oracle.get("candidates", []) if item.get("candidate_id") == candidate_id
    ]
    if len(matches) != 1:
        raise ValueError("candidate must occur exactly once in the oracle manifest")
    return matches[0]


def unlock(public, oracle, candidate_id, control, pdt=None, gate=None, allow_draft=False):
    public_candidate = find_public_candidate(public, candidate_id)
    oracle_candidate = find_oracle_candidate(oracle, candidate_id)
    if public.get("corpus_id") != oracle.get("corpus_id"):
        raise ValueError("public corpus and oracle manifest corpus IDs differ")
    if public.get("protocol_sha256") != oracle.get("protocol_sha256"):
        raise ValueError("public corpus and oracle manifest protocol hashes differ")
    if public.get("oracle_manifest_commitment_sha256") != oracle.get(
        "oracle_manifest_commitment_sha256"
    ):
        raise ValueError("oracle manifest commitment mismatch")
    if not public.get("confirmatory_eligible") and not allow_draft:
        raise ValueError("oracle unlock requires a confirmatory-eligible corpus")
    if control.get("candidate_id") != candidate_id:
        raise ValueError("conventional decision candidate mismatch")
    if control.get("mechanism") != "conventional-ci-cd-with-staging":
        raise ValueError("oracle unlock requires a conventional CI/CD decision")
    if control.get("control_decision_sealed") is not True:
        raise ValueError("conventional decision must be sealed before oracle unlock")
    if control.get("decision") not in {"approve", "block"}:
        raise ValueError("conventional decision must be approve or block")

    treatment = {"decision": "block", "source": "inherited-control-block"}
    if control["decision"] == "approve":
        if pdt is None or gate is None:
            raise ValueError("approved control requires sealed PDT and deployment-gate decisions")
        if pdt.get("candidate") != candidate_id or gate.get("candidate_id") != candidate_id:
            raise ValueError("PDT or gate candidate mismatch")
        if pdt.get("decision") not in {"approve", "block", "reconfigure"}:
            raise ValueError("PDT decision is not sealed")
        if gate.get("operational_mutation_performed") is not False:
            raise ValueError("oracle unlock must occur before operational mutation")
        if gate.get("gate_state") not in {"awaiting-human-confirmation", "blocked"}:
            raise ValueError("deployment gate is not terminal for isolated validation")
        if pdt.get("artifact_binding", {}).get("immutable_artifacts") != control.get(
            "immutable_artifacts", []
        ):
            raise ValueError("PDT and control artifact bindings differ")
        if pdt.get("artifact_binding", {}).get(
            "candidate_definition_sha256"
        ) != control.get("candidate_definition_sha256"):
            raise ValueError("PDT and control candidate definitions differ")
        treatment = {"decision": pdt["decision"], "source": "pdt"}

    private_work_item = {
        "schema_version": "1.0.0",
        "corpus_id": public["corpus_id"],
        "protocol_sha256": public["protocol_sha256"],
        "candidate_id": candidate_id,
        "sequence": public_candidate["sequence"],
        "repetitions": public_candidate["repetitions"],
        "operator_id": oracle_candidate["operator_id"],
        "operator_instance": oracle_candidate["operator_instance"],
        "stratum": oracle_candidate["stratum"],
        "intended_label": oracle_candidate["intended_label"],
        "target_component": oracle_candidate["target_component"],
        "context_dependency": oracle_candidate["context_dependency"],
        "parameters": oracle_candidate["parameters"],
        "candidate_definition_sha256": control.get("candidate_definition_sha256"),
        "control_decision": control["decision"],
        "treatment_decision": treatment,
    }
    receipt = {
        "schema_version": "1.0.0",
        "corpus_id": public["corpus_id"],
        "candidate_id": candidate_id,
        "sequence": public_candidate["sequence"],
        "repetitions": public_candidate["repetitions"],
        "oracle_manifest_commitment_sha256": public[
            "oracle_manifest_commitment_sha256"
        ],
        "control_decision": control["decision"],
        "treatment_decision": treatment["decision"],
        "candidate_definition_sha256": control.get("candidate_definition_sha256"),
        "operational_mutation_performed": False,
        "oracle_metadata_released": True,
    }
    leaked = recursively_find_keys(receipt, FORBIDDEN_RECEIPT_KEYS)
    if leaked:
        raise ValueError("public unlock receipt leaks oracle metadata")
    return private_work_item, receipt


def write_json_exclusive(path, value, mode):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
    except Exception:
        path.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-corpus", type=pathlib.Path, required=True)
    parser.add_argument("--oracle-manifest", type=pathlib.Path, required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--conventional-decision", type=pathlib.Path, required=True)
    parser.add_argument("--pdt-decision", type=pathlib.Path)
    parser.add_argument("--deployment-gate", type=pathlib.Path)
    parser.add_argument("--private-work-item", type=pathlib.Path, required=True)
    parser.add_argument("--public-receipt", type=pathlib.Path, required=True)
    parser.add_argument("--allow-draft", action="store_true")
    args = parser.parse_args()

    try:
        if not private_file(args.oracle_manifest):
            raise ValueError("oracle manifest must have private file permissions")
        pdt = load(args.pdt_decision) if args.pdt_decision else None
        gate = load(args.deployment_gate) if args.deployment_gate else None
        private_work_item, receipt = unlock(
            load(args.public_corpus),
            load(args.oracle_manifest),
            args.candidate_id,
            load(args.conventional_decision),
            pdt,
            gate,
            args.allow_draft,
        )
        now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
        private_work_item["unlocked_at"] = now
        receipt["unlocked_at"] = now
        receipt["evidence_sha256"] = {
            "conventional_decision": sha256_file(args.conventional_decision),
            "pdt_decision": sha256_file(args.pdt_decision) if args.pdt_decision else None,
            "deployment_gate": (
                sha256_file(args.deployment_gate) if args.deployment_gate else None
            ),
        }
        write_json_exclusive(args.private_work_item, private_work_item, 0o600)
        try:
            write_json_exclusive(args.public_receipt, receipt, 0o644)
        except Exception:
            args.private_work_item.unlink(missing_ok=True)
            raise
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"oracle unlock failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(
        json.dumps(
            {
                "candidate_id": args.candidate_id,
                "private_work_item": str(args.private_work_item),
                "public_receipt": str(args.public_receipt),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
