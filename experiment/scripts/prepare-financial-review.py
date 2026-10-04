#!/usr/bin/env python3

"""Prepare a hash-bound financial review without authorizing cloud execution."""

import argparse
import datetime
import hashlib
import importlib.util
import json
import pathlib
import sys


PROJECT_ID = "microservices-demo-tcc"
PROTOCOL_PATH = pathlib.PurePosixPath("experiment/protocol/protocol-v1.json")
CANONICAL_APPROVAL_PATH = pathlib.PurePosixPath(
    "experiment/protocol/approvals/cost-review-v1.json"
)
FINANCE_EVIDENCE_PREFIX = ("experiment", "evidence", "finance")
ACKNOWLEDGEMENT = "APPROVE_FINANCIAL_REVIEW_FOR_PROTOCOL_FREEZE"
AUDITOR_PATH = pathlib.Path(__file__).with_name("audit-protocol-freeze.py")
AUDITOR_SPEC = importlib.util.spec_from_file_location(
    "audit_protocol_freeze_for_financial_review", AUDITOR_PATH
)
AUDITOR = importlib.util.module_from_spec(AUDITOR_SPEC)
assert AUDITOR_SPEC.loader is not None
AUDITOR_SPEC.loader.exec_module(AUDITOR)


class ReviewError(RuntimeError):
    """Financial-review preparation failed closed."""


def load(path):
    try:
        with pathlib.Path(path).open(encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise ReviewError(f"cannot load valid JSON from {path}") from error


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


def safe_relative_path(repo_root, path, expected_prefix):
    root = pathlib.Path(repo_root).resolve()
    candidate = pathlib.Path(path)
    absolute = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        relative = absolute.relative_to(root)
    except ValueError as error:
        raise ReviewError("path must remain inside the repository") from error
    if relative.parts[: len(expected_prefix)] != expected_prefix:
        raise ReviewError(
            "cost evidence must be under experiment/evidence/finance"
        )
    if not absolute.is_file():
        raise ReviewError("cost evidence file is unavailable")
    return absolute, pathlib.PurePosixPath(*relative.parts)


def build_review(repo_root, evidence_path, reviewed_at):
    root = pathlib.Path(repo_root).resolve()
    protocol_file = root / PROTOCOL_PATH
    protocol = load(protocol_file)
    evidence_file, relative = safe_relative_path(
        root, evidence_path, FINANCE_EVIDENCE_PREFIX
    )
    evidence = load(evidence_file)
    limits = protocol.get("execution_limits", {})
    observed_gross = evidence.get("gross_cost_brl")
    incremental_ceiling = limits.get("proposed_incremental_spend_ceiling_brl")
    projected_gross = (
        observed_gross + incremental_ceiling
        if isinstance(observed_gross, (int, float))
        and not isinstance(observed_gross, bool)
        and isinstance(incremental_ceiling, (int, float))
        and not isinstance(incremental_ceiling, bool)
        else None
    )
    review = {
        "schema_version": "1.1.0",
        "protocol_id": protocol.get("protocol_id"),
        "project_id": PROJECT_ID,
        "decision": "approved-for-protocol-freeze",
        "reviewed_at": reviewed_at,
        "billing_data_as_of": evidence.get("billing_data_as_of"),
        "cost_data_available": True,
        "project_gross_cost_observed_brl": observed_gross,
        "approved_incremental_spend_ceiling_brl": incremental_ceiling,
        "projected_project_gross_cost_ceiling_brl": projected_gross,
        "project_gross_cost_budget_brl": limits.get(
            "project_gross_cost_budget_brl"
        ),
        "mandatory_incremental_review_at_brl": limits.get(
            "mandatory_cost_review_at_brl"
        ),
        "evidence": {
            "path": relative.as_posix(),
            "sha256": sha256_file(evidence_file),
        },
        "cloud_execution_authorized": False,
    }
    eligible = AUDITOR.validate_cost_review(root, protocol, review)
    return protocol, evidence, review, eligible


def prepare(repo_root, evidence_path, approve=False, acknowledgement=None):
    if approve and acknowledgement != ACKNOWLEDGEMENT:
        raise ReviewError(f"--approve requires --acknowledge {ACKNOWLEDGEMENT}")

    reviewed_at = utc_now()
    protocol, evidence, review, eligible = build_review(
        repo_root, evidence_path, reviewed_at
    )
    if approve:
        if not eligible:
            raise ReviewError("financial evidence is not eligible for approval")
        return review

    limits = protocol.get("execution_limits", {})
    observed_gross = evidence.get("gross_cost_brl")
    incremental_ceiling = limits.get("proposed_incremental_spend_ceiling_brl")
    projected_gross = (
        observed_gross + incremental_ceiling
        if isinstance(observed_gross, (int, float))
        and not isinstance(observed_gross, bool)
        and isinstance(incremental_ceiling, (int, float))
        and not isinstance(incremental_ceiling, bool)
        else None
    )
    project_budget = limits.get("project_gross_cost_budget_brl")
    return {
        "schema_version": "1.1.0",
        "captured_at": reviewed_at,
        "mechanism": "financial-review-preparer",
        "mode": "read-only-eligibility",
        "protocol_id": protocol.get("protocol_id"),
        "project_id": PROJECT_ID,
        "billing_data_as_of": evidence.get("billing_data_as_of"),
        "observed_project_gross_cost_brl": observed_gross,
        "approved_incremental_spend_ceiling_brl": incremental_ceiling,
        "projected_project_gross_cost_ceiling_brl": projected_gross,
        "project_gross_cost_budget_brl": project_budget,
        "remaining_project_gross_budget_after_approved_ceiling_brl": (
            project_budget - projected_gross
            if isinstance(project_budget, (int, float))
            and not isinstance(project_budget, bool)
            and isinstance(projected_gross, (int, float))
            else None
        ),
        "mandatory_incremental_review_at_brl": limits.get(
            "mandatory_cost_review_at_brl"
        ),
        "evidence": review["evidence"],
        "eligible_for_human_approval": eligible,
        "blocking_requirements": []
        if eligible
        else ["cost-evidence-or-protocol-limits-invalid"],
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
    parser.add_argument("--cost-evidence", type=pathlib.Path, required=True)
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--acknowledge")
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
            args.cost_evidence,
            approve=args.approve,
            acknowledgement=args.acknowledge,
        )
    except ReviewError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.require_eligible and not args.approve and not result[
        "eligible_for_human_approval"
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
