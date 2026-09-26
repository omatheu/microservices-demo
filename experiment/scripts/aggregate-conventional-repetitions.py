#!/usr/bin/env python3

"""Aggregate repeated staging decisions into one sealed control decision."""

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import sys


DIGEST = re.compile(r"^[0-9a-f]{64}$")


def load(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_single_repetition_composer():
    path = pathlib.Path(__file__).with_name("compose-conventional-decision.py")
    spec = importlib.util.spec_from_file_location("compose_conventional_decision", path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise ValueError("could not load the single-repetition decision composer")
    spec.loader.exec_module(module)
    return module


SINGLE_REPETITION = load_single_repetition_composer()


def validate_design(protocol, allow_draft):
    design = protocol.get("research_design")
    aggregation = protocol.get("aggregation")
    rule = (
        aggregation.get("mechanism_repetition_rule")
        if isinstance(aggregation, dict)
        else None
    )
    required = (
        design.get("technical_repetitions_per_candidate")
        if isinstance(design, dict)
        else None
    )
    if (
        not isinstance(required, int)
        or isinstance(required, bool)
        or required < 2
        or not isinstance(rule, dict)
        or rule.get("planned_repetitions") != required
        or rule.get("minimum_valid_repetitions")
        != aggregation.get("minimum_valid_repetitions")
        or not isinstance(rule.get("minimum_valid_repetitions"), int)
        or isinstance(rule.get("minimum_valid_repetitions"), bool)
        or not 2 <= rule["minimum_valid_repetitions"] <= required
        or not isinstance(rule.get("safe_votes_to_approve"), int)
        or isinstance(rule.get("safe_votes_to_approve"), bool)
        or not (required // 2 < rule["safe_votes_to_approve"] <= required)
        or rule.get("applies_symmetrically_to_control_and_treatment") is not True
        or rule.get("incomplete_outcome")
        != "retry-once-before-label-then-exclude-or-block"
    ):
        raise ValueError("protocol mechanism repetition rule is invalid")
    confirmatory = (
        protocol.get("status") == "frozen"
        and protocol.get("confirmatory_collection_allowed") is True
        and isinstance(protocol.get("frozen_at"), str)
        and bool(protocol["frozen_at"])
    )
    if not confirmatory and not allow_draft:
        raise ValueError("repetition aggregation requires a frozen protocol")
    return (
        required,
        rule["minimum_valid_repetitions"],
        rule["safe_votes_to_approve"],
        confirmatory,
    )


def validate_invalid_repetition_ledger(
    ledger, candidate_id, planned_repetitions, valid_repetitions
):
    expected = list(range(1, planned_repetitions + 1))
    invalid_repetitions = sorted(set(expected) - set(valid_repetitions))
    if not invalid_repetitions:
        if ledger is not None:
            raise ValueError("complete repetition coverage must not include an invalid ledger")
        return []
    required_keys = {
        "schema_version",
        "candidate_id",
        "classification",
        "label_revealed",
        "planned_repetitions",
        "valid_repetitions",
        "invalid_repetitions",
    }
    entries = ledger.get("invalid_repetitions") if isinstance(ledger, dict) else None
    if (
        not isinstance(ledger, dict)
        or set(ledger) != required_keys
        or ledger.get("schema_version") != "1.0.0"
        or ledger.get("candidate_id") != candidate_id
        or ledger.get("classification") != "infrastructure-invalid"
        or ledger.get("label_revealed") is not False
        or ledger.get("planned_repetitions") != expected
        or ledger.get("valid_repetitions") != valid_repetitions
        or not isinstance(entries, list)
        or len(entries) != len(invalid_repetitions)
    ):
        raise ValueError("infrastructure-invalid repetition ledger is incomplete")
    for repetition, entry in zip(invalid_repetitions, entries):
        if (
            not isinstance(entry, dict)
            or set(entry) != {"repetition", "attempts", "reasons"}
            or entry.get("repetition") != repetition
            or entry.get("attempts") != 2
            or not isinstance(entry.get("reasons"), list)
            or len(entry["reasons"]) != 2
            or not all(
                isinstance(reason, str) and reason.strip()
                for reason in entry["reasons"]
            )
        ):
            raise ValueError(
                "invalid repetition lacks the original and replacement failure"
            )
    return invalid_repetitions


def aggregate(
    protocol,
    local_ci,
    staging_decisions,
    local_ci_sha256,
    candidate_definition_sha256,
    invalid_repetition_ledger=None,
    allow_draft=False,
):
    (
        planned,
        minimum_valid,
        safe_votes_to_approve,
        confirmatory,
    ) = validate_design(protocol, allow_draft)
    if not isinstance(local_ci_sha256, str) or not DIGEST.fullmatch(local_ci_sha256):
        raise ValueError("local CI decision digest is invalid")
    if not isinstance(candidate_definition_sha256, str) or not DIGEST.fullmatch(
        candidate_definition_sha256
    ):
        raise ValueError("candidate definition digest is invalid")
    if not isinstance(staging_decisions, list):
        raise ValueError("staging decisions must be a list")

    local_result = local_ci.get("local_decision")
    if local_result == "block":
        if staging_decisions or invalid_repetition_ledger is not None:
            raise ValueError(
                "local-CI-blocked candidate must not contain staging repetition evidence"
            )
        result = SINGLE_REPETITION.compose(
            local_ci,
            local_ci_sha256=local_ci_sha256,
            candidate_definition_sha256=candidate_definition_sha256,
        )
        result.update(
            {
                "protocol_id": protocol.get("protocol_id"),
                "execution_mode": "confirmatory" if confirmatory else "engineering-dry-run",
                "repetition_aggregation": {
                    "rule": "majority-safe-vote",
                    "planned_repetitions": planned,
                    "minimum_valid_repetitions": minimum_valid,
                    "safe_votes_to_approve": safe_votes_to_approve,
                    "observed_valid_repetitions": 0,
                    "safe_votes": 0,
                    "unsafe_votes": 0,
                    "outcome": "local-ci-block",
                },
            }
        )
        return result
    if local_result != "pass":
        raise ValueError("local CI decision must be pass or block")
    if not minimum_valid <= len(staging_decisions) <= planned:
        raise ValueError("staging decisions do not contain enough valid repetitions")

    repetitions = [item.get("repetition") for item in staging_decisions]
    expected_repetitions = list(range(1, planned + 1))
    if (
        any(not isinstance(value, int) or isinstance(value, bool) for value in repetitions)
        or len(repetitions) != len(set(repetitions))
        or not set(repetitions).issubset(expected_repetitions)
    ):
        raise ValueError("staging repetition identities are incomplete or duplicated")

    ordered = sorted(staging_decisions, key=lambda item: item["repetition"])
    valid_repetitions = [item["repetition"] for item in ordered]
    invalid_repetitions = validate_invalid_repetition_ledger(
        invalid_repetition_ledger,
        local_ci.get("candidate_id"),
        planned,
        valid_repetitions,
    )
    expected_mode = "confirmatory" if confirmatory else "engineering"
    if any(item.get("mode") != expected_mode for item in ordered):
        raise ValueError(
            f"protocol state requires {expected_mode} staging repetitions"
        )

    repetition_results = []
    immutable_artifacts = None
    for staging in ordered:
        per_repetition = SINGLE_REPETITION.compose(
            local_ci,
            staging,
            local_ci_sha256=local_ci_sha256,
            candidate_definition_sha256=candidate_definition_sha256,
        )
        artifacts = per_repetition["immutable_artifacts"]
        if immutable_artifacts is None:
            immutable_artifacts = artifacts
        elif artifacts != immutable_artifacts:
            raise ValueError("staging repetitions do not share one immutable artifact set")
        repetition_results.append(
            {
                "repetition": staging["repetition"],
                "run_id": staging.get("run_id"),
                "decision": staging["decision"],
                "rationale": staging.get("rationale", []),
            }
        )

    safe_votes = sum(item["decision"] == "PASS" for item in repetition_results)
    unsafe_votes = len(repetition_results) - safe_votes
    approved = safe_votes >= safe_votes_to_approve
    decision = "approve" if approved else "block"
    reasons = [] if approved else ["traditional-staging-majority-did-not-pass"]

    return {
        "schema_version": "1.0.0",
        "mechanism": "conventional-ci-cd-with-staging",
        "candidate_id": local_ci.get("candidate_id"),
        "protocol_id": protocol.get("protocol_id"),
        "execution_mode": "confirmatory" if confirmatory else "engineering-dry-run",
        "decision": decision,
        "reasons": reasons,
        "local_ci": {
            "run_id": local_ci.get("run_id"),
            "decision": local_result,
            "failed_required_gates": local_ci.get("failed_required_gates"),
            "executed_once_per_candidate": True,
        },
        "staging": {
            "executed": True,
            "decision": "PASS" if approved else "FAIL",
            "aggregation_rule": "majority-safe-vote",
            "planned_repetitions": planned,
            "minimum_valid_repetitions": minimum_valid,
            "safe_votes_to_approve": safe_votes_to_approve,
            "safe_votes": safe_votes,
            "unsafe_votes": unsafe_votes,
            "valid_repetitions": valid_repetitions,
            "invalid_repetitions": invalid_repetitions,
            "repetition_results": repetition_results,
            "artifact_binding_verified": True,
            "candidate_definition_sha256": candidate_definition_sha256,
        },
        "repetition_aggregation": {
            "rule": "majority-safe-vote",
            "planned_repetitions": planned,
            "minimum_valid_repetitions": minimum_valid,
            "safe_votes_to_approve": safe_votes_to_approve,
            "observed_valid_repetitions": len(repetition_results),
            "safe_votes": safe_votes,
            "unsafe_votes": unsafe_votes,
            "valid_repetitions": valid_repetitions,
            "invalid_repetitions": invalid_repetitions,
            "outcome": decision,
        },
        "immutable_artifacts": immutable_artifacts or [],
        "candidate_definition_sha256": candidate_definition_sha256,
        "pdt_consulted": False,
        "control_decision_sealed": True,
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
    parser.add_argument("--local-ci-decision", type=pathlib.Path, required=True)
    parser.add_argument("--candidate-definition", type=pathlib.Path, required=True)
    parser.add_argument(
        "--staging-decision", type=pathlib.Path, action="append", default=[]
    )
    parser.add_argument("--infrastructure-invalid-ledger", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--allow-draft", action="store_true")
    args = parser.parse_args()

    try:
        protocol = load(args.protocol)
        local_ci = load(args.local_ci_decision)
        candidate = load(args.candidate_definition)
        if candidate.get("candidate_id") != local_ci.get("candidate_id"):
            raise ValueError("candidate definition and local CI candidate differ")
        confirmatory = protocol.get("status") == "frozen"
        if confirmatory and candidate.get("confirmatory_eligibility") is not True:
            raise ValueError("confirmatory aggregation requires an eligible candidate")
        staging_decisions = [load(path) for path in args.staging_decision]
        invalid_ledger = (
            load(args.infrastructure_invalid_ledger)
            if args.infrastructure_invalid_ledger
            else None
        )
        result = aggregate(
            protocol,
            local_ci,
            staging_decisions,
            sha256_file(args.local_ci_decision),
            sha256_file(args.candidate_definition),
            invalid_repetition_ledger=invalid_ledger,
            allow_draft=args.allow_draft,
        )
        result["protocol_sha256"] = sha256_file(args.protocol)
        result["sealed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
        result["evidence"] = {
            "protocol": {
                "path": str(args.protocol),
                "sha256": result["protocol_sha256"],
            },
            "local_ci_decision": {
                "path": str(args.local_ci_decision),
                "sha256": sha256_file(args.local_ci_decision),
            },
            "candidate_definition": {
                "path": str(args.candidate_definition),
                "sha256": sha256_file(args.candidate_definition),
            },
            "staging_decisions": [
                {
                    "path": str(path),
                    "sha256": sha256_file(path),
                    "repetition": decision.get("repetition"),
                }
                for path, decision in zip(args.staging_decision, staging_decisions)
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
        raise SystemExit(f"conventional repetition aggregation failed: {error}") from error
    print(args.output)


if __name__ == "__main__":
    main()
