#!/usr/bin/env python3

"""Prepare the canonical researcher approval for an exact protocol candidate."""

import argparse
import datetime
import hashlib
import importlib.util
import json
import pathlib
import sys


PROTOCOL_PATH = pathlib.PurePosixPath("experiment/protocol/protocol-v1.json")
COST_REVIEW_PATH = pathlib.PurePosixPath(
    "experiment/protocol/approvals/cost-review-v1.json"
)
CANONICAL_APPROVAL_PATH = pathlib.PurePosixPath(
    "experiment/protocol/approvals/researcher-approval-v1.json"
)
ACKNOWLEDGEMENT = "APPROVE_RESEARCHER_PROTOCOL_FREEZE"
AUDITOR_PATH = pathlib.Path(__file__).with_name("audit-protocol-freeze.py")
AUDITOR_SPEC = importlib.util.spec_from_file_location(
    "audit_protocol_freeze_for_researcher_approval", AUDITOR_PATH
)
AUDITOR = importlib.util.module_from_spec(AUDITOR_SPEC)
assert AUDITOR_SPEC.loader is not None
AUDITOR_SPEC.loader.exec_module(AUDITOR)


class ApprovalError(RuntimeError):
    """Researcher-approval preparation failed closed."""


def load(path):
    try:
        with pathlib.Path(path).open(encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise ApprovalError(f"cannot load valid JSON from {path}") from error


def load_optional(path):
    try:
        return load(path)
    except ApprovalError as error:
        if isinstance(error.__cause__, FileNotFoundError):
            return None
        raise


def sha256_file(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now():
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def audit_is_ready_for_researcher(audit_result):
    checks = audit_result.get("checks", []) if isinstance(audit_result, dict) else []
    check_ids = [
        check.get("id")
        for check in checks
        if isinstance(check, dict) and isinstance(check.get("id"), str)
    ]
    return bool(
        isinstance(audit_result, dict)
        and len(checks) == 17
        and len(check_ids) == 17
        and len(set(check_ids)) == 17
        and audit_result.get("check_count") == 17
        and audit_result.get("passed_count") == 16
        and audit_result.get("ready_to_freeze") is False
        and audit_result.get("blocking_requirements") == ["researcher-approval"]
        and sum(
            1
            for check in checks
            if isinstance(check, dict)
            and check.get("id") == "researcher-approval"
            and check.get("passed") is False
        )
        == 1
        and all(
            check.get("passed") is True
            for check in checks
            if isinstance(check, dict) and check.get("id") != "researcher-approval"
        )
    )


def build_approval(protocol, protocol_sha256, approved_by, approved_at):
    return {
        "schema_version": "1.0.0",
        "protocol_id": protocol.get("protocol_id"),
        "candidate_protocol_sha256": protocol_sha256,
        "decision": "approve-protocol-freeze",
        "approved_by": approved_by.strip(),
        "approved_at": approved_at,
        "cloud_execution_authorized": False,
        "acknowledgements": {
            "protocol_reviewed": True,
            "no_confirmatory_outcomes_observed": True,
            "changes_require_new_protocol_version": True,
        },
    }


def prepare(
    repo_root,
    approve=False,
    acknowledgement=None,
    approved_by=None,
):
    if approve and acknowledgement != ACKNOWLEDGEMENT:
        raise ApprovalError(f"--approve requires --acknowledge {ACKNOWLEDGEMENT}")
    if approve and (not isinstance(approved_by, str) or not approved_by.strip()):
        raise ApprovalError("--approve requires a non-empty --approved-by")

    root = pathlib.Path(repo_root).resolve()
    protocol_path = root / PROTOCOL_PATH
    protocol = load(protocol_path)
    cost_review = load_optional(root / COST_REVIEW_PATH)
    protocol_sha256 = sha256_file(protocol_path)
    audit_result = AUDITOR.audit(root, protocol, None, cost_review)
    audit_digest_matches = audit_result.get("protocol_sha256") == protocol_sha256
    eligible = audit_digest_matches and audit_is_ready_for_researcher(audit_result)
    approved_at = utc_now()

    if approve:
        if not eligible:
            raise ApprovalError(
                "protocol is not ready for researcher approval; all other 16 checks must pass"
            )
        return build_approval(
            protocol,
            protocol_sha256,
            approved_by,
            approved_at,
        )

    return {
        "schema_version": "1.0.0",
        "captured_at": approved_at,
        "mechanism": "researcher-approval-preparer",
        "mode": "read-only-eligibility",
        "protocol_id": protocol.get("protocol_id"),
        "candidate_protocol_sha256": protocol_sha256,
        "audit_protocol_sha256_matches": audit_digest_matches,
        "checks_passed": audit_result.get("passed_count"),
        "check_count": audit_result.get("check_count"),
        "blocking_requirements": audit_result.get("blocking_requirements", []),
        "eligible_for_researcher_approval": eligible,
        "approval_generated": False,
        "cloud_execution_authorized": False,
        "gcp_mutation_performed": False,
        "github_mutation_performed": False,
    }


def write_json(path, document):
    output = pathlib.Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=pathlib.Path, default=pathlib.Path("."))
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--acknowledge")
    parser.add_argument("--approved-by")
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--require-eligible", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    root = args.repo_root.resolve()
    output_path = None
    if args.output is not None:
        output_path = (
            args.output.resolve()
            if args.output.is_absolute()
            else (root / args.output).resolve()
        )
    if args.approve:
        if output_path is None:
            print("error: --approve requires --output", file=sys.stderr)
            return 2
        try:
            relative_output = output_path.relative_to(root)
        except ValueError:
            print("error: approval output must remain inside the repository", file=sys.stderr)
            return 2
        if pathlib.PurePosixPath(*relative_output.parts) != CANONICAL_APPROVAL_PATH:
            print(
                f"error: approval output must be {CANONICAL_APPROVAL_PATH}",
                file=sys.stderr,
            )
            return 2
        if output_path.exists():
            print("error: refusing to overwrite an existing approval", file=sys.stderr)
            return 2
    try:
        result = prepare(
            root,
            approve=args.approve,
            acknowledgement=args.acknowledge,
            approved_by=args.approved_by,
        )
    except ApprovalError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.require_eligible and not args.approve and not result[
        "eligible_for_researcher_approval"
    ]:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1
    if output_path:
        write_json(output_path, result)
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
