#!/usr/bin/env python3

"""Validate the terminal outcome of the pull-request conventional CI workflow."""

import argparse
import hashlib
import json
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


def validate_pass(local, runner_exit_code, conventional):
    if runner_exit_code != 0:
        raise ValueError("passing local CI must exit with status zero")
    if conventional is not None:
        raise ValueError("passing local CI must not contain a pre-staging control block")

    change_class = local.get("change_class")
    eligible = local.get("eligible_for_staging")
    if change_class == "release-relevant" and eligible is True:
        return "release-progression"
    if change_class == "documentation-only" and eligible is False:
        return "documentation-only"
    raise ValueError("passing local CI has an inconsistent change classification")


def validate_experimental_block(local, runner_exit_code, conventional, local_sha256):
    if runner_exit_code != 1:
        raise ValueError("a local CI block must exit with the canonical status one")
    if local.get("eligible_for_staging") is not False:
        raise ValueError("a local CI block must not be eligible for staging")
    failed = local.get("failed_required_gates")
    if not isinstance(failed, int) or isinstance(failed, bool) or failed < 1:
        raise ValueError("a local CI block must identify at least one failed required gate")
    if not isinstance(conventional, dict):
        raise ValueError("an experimental local CI block requires a sealed control decision")

    candidate_id = local.get("candidate_id")
    candidate_definition_sha256 = conventional.get("candidate_definition_sha256")
    local_evidence = conventional.get("evidence", {}).get("local_ci_decision", {})
    if (
        conventional.get("schema_version") != "1.0.0"
        or conventional.get("mechanism") != "conventional-ci-cd-with-staging"
        or conventional.get("candidate_id") != candidate_id
        or conventional.get("decision") != "block"
        or conventional.get("control_decision_sealed") is not True
        or conventional.get("staging", {}).get("executed") is not False
        or conventional.get("staging", {}).get("decision") != "NOT_RUN"
        or conventional.get("immutable_artifacts") != []
        or conventional.get("pdt_consulted") is not False
        or conventional.get("operational_mutation_performed") is not False
        or conventional.get("local_ci", {}).get("decision") != "block"
        or conventional.get("local_ci", {}).get("failed_required_gates") != failed
        or not isinstance(candidate_definition_sha256, str)
        or not DIGEST.fullmatch(candidate_definition_sha256)
        or local_evidence.get("sha256") != local_sha256
    ):
        raise ValueError("experimental local CI block is not completely sealed")
    return "sealed-preartifact-block"


def validate(local, runner_exit_code, experimental_cloud_eligible, conventional, local_sha256):
    if local.get("scope") != "local-pre-staging-ci":
        raise ValueError("local CI decision has an unexpected scope")
    if not isinstance(local.get("candidate_id"), str) or not local["candidate_id"]:
        raise ValueError("local CI decision is missing candidate_id")

    decision = local.get("local_decision")
    if decision == "pass":
        return validate_pass(local, runner_exit_code, conventional)
    if decision != "block":
        raise ValueError("local CI decision must be pass or block")
    if not experimental_cloud_eligible:
        raise ValueError("a non-experimental pull request cannot convert a CI block into success")
    return validate_experimental_block(
        local, runner_exit_code, conventional, local_sha256
    )


def parse_bool(value):
    if value == "true":
        return True
    if value == "false":
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-decision", type=pathlib.Path, required=True)
    parser.add_argument("--runner-exit-code", type=int, required=True)
    parser.add_argument(
        "--experimental-cloud-eligible", type=parse_bool, required=True
    )
    parser.add_argument("--conventional-decision", type=pathlib.Path)
    args = parser.parse_args()

    try:
        local = load(args.local_decision)
        conventional = (
            load(args.conventional_decision) if args.conventional_decision else None
        )
        outcome = validate(
            local,
            args.runner_exit_code,
            args.experimental_cloud_eligible,
            conventional,
            sha256_file(args.local_decision),
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"conventional workflow outcome rejected: {error}", file=sys.stderr)
        raise SystemExit(1) from error

    print(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "candidate_id": local["candidate_id"],
                "local_decision": local["local_decision"],
                "workflow_outcome": outcome,
                "experimental_cloud_eligible": args.experimental_cloud_eligible,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
