#!/usr/bin/env python3

"""Produce a frozen protocol proposal after every pre-freeze gate passes."""

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import sys


DIGEST = re.compile(r"^[a-f0-9]{64}$")
RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
PROTOCOL_PATH = "experiment/protocol/protocol-v1.json"
COMPONENT_PATHS = {
    "experiment/ci/policy.json",
    "experiment/staging/safety-thresholds.json",
    "experiment/pdt/model-policy.json",
    "experiment/pdt/fidelity-policy.json",
    "experiment/oracle/policy-v1.json",
    "experiment/pdt/runtime-manifest.json",
    "experiment/oracle/suite-manifest.json",
}
REQUIRED_AUDIT_CHECKS = {
    "protocol-structure",
    "collection-locked-before-freeze",
    "frozen-input-hashes",
    "mutation-operators-implemented",
    "ci-policy-frozen",
    "staging-thresholds-frozen",
    "pdt-model-policy-frozen",
    "pdt-fidelity-policy-frozen",
    "oracle-policy-frozen",
    "pdt-runtime-file-hashes",
    "pdt-controller-image-bound",
    "pdt-runtime-frozen",
    "oracle-file-hashes",
    "oracle-images-bound",
    "oracle-suite-frozen",
    "researcher-approval",
    "financial-review",
}


def load(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def render(value):
    return (json.dumps(value, indent=2) + "\n").encode()


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_binding(binding, label):
    require(
        isinstance(binding, dict)
        and set(binding) == {"path", "sha256"}
        and isinstance(binding.get("path"), str)
        and binding["path"]
        and not pathlib.PurePosixPath(binding["path"]).is_absolute()
        and ".." not in pathlib.PurePosixPath(binding["path"]).parts
        and isinstance(binding.get("sha256"), str)
        and DIGEST.fullmatch(binding["sha256"]),
        f"{label} binding is invalid",
    )


def validate_audit(audit_result, protocol_id, candidate_protocol_sha256):
    checks = audit_result.get("checks") if isinstance(audit_result, dict) else None
    check_ids = (
        [item.get("id") for item in checks if isinstance(item, dict)]
        if isinstance(checks, list)
        else []
    )
    require(
        isinstance(audit_result, dict)
        and audit_result.get("protocol_id") == protocol_id
        and audit_result.get("protocol_sha256") == candidate_protocol_sha256
        and audit_result.get("ready_to_freeze") is True
        and audit_result.get("blocking_requirements") == []
        and set(check_ids) == REQUIRED_AUDIT_CHECKS
        and len(check_ids) == len(REQUIRED_AUDIT_CHECKS)
        and all(item.get("passed") is True for item in checks)
        and audit_result.get("passed_count") == len(REQUIRED_AUDIT_CHECKS)
        and audit_result.get("check_count") == len(REQUIRED_AUDIT_CHECKS),
        "pre-freeze audit is incomplete or not ready",
    )


def finalize(
    protocol,
    candidate_protocol_sha256,
    audit_result,
    researcher_approval,
    researcher_binding,
    cost_review,
    cost_binding,
    component_frozen_at,
    frozen_at,
):
    require(
        isinstance(candidate_protocol_sha256, str)
        and DIGEST.fullmatch(candidate_protocol_sha256),
        "candidate protocol digest is invalid",
    )
    require(
        protocol.get("status") == "pre-registration-candidate"
        and protocol.get("frozen_at") is None
        and protocol.get("confirmatory_collection_allowed") is False,
        "only a locked pre-registration candidate can be finalized",
    )
    require(
        protocol.get("execution_limits", {}).get("cloud_execution_authorization")
        == "explicit-user-authorization-required-after-freeze",
        "frozen protocol must retain the independent cloud authorization gate",
    )
    validate_audit(
        audit_result, protocol.get("protocol_id"), candidate_protocol_sha256
    )
    validate_binding(researcher_binding, "researcher approval")
    validate_binding(cost_binding, "financial review")
    require(
        researcher_binding["path"]
        == "experiment/protocol/approvals/researcher-approval-v1.json",
        "researcher approval must use the canonical protocol path",
    )
    require(
        cost_binding["path"]
        == "experiment/protocol/approvals/cost-review-v1.json",
        "financial review must use the canonical protocol path",
    )
    require(
        isinstance(researcher_approval, dict)
        and researcher_approval.get("schema_version") == "1.0.0"
        and researcher_approval.get("protocol_id") == protocol.get("protocol_id")
        and researcher_approval.get("candidate_protocol_sha256")
        == candidate_protocol_sha256
        and researcher_approval.get("decision") == "approve-protocol-freeze"
        and researcher_approval.get("cloud_execution_authorized") is False
        and isinstance(researcher_approval.get("approved_by"), str)
        and bool(researcher_approval["approved_by"].strip())
        and isinstance(researcher_approval.get("approved_at"), str)
        and RFC3339.fullmatch(researcher_approval["approved_at"])
        and all(
            researcher_approval.get("acknowledgements", {}).get(name) is True
            for name in (
                "protocol_reviewed",
                "no_confirmatory_outcomes_observed",
                "changes_require_new_protocol_version",
            )
        ),
        "researcher approval does not bind the candidate protocol",
    )
    require(
        isinstance(cost_review, dict)
        and cost_review.get("schema_version") == "1.0.0"
        and cost_review.get("protocol_id") == protocol.get("protocol_id")
        and cost_review.get("project_id") == "microservices-demo-tcc"
        and cost_review.get("decision") == "approved-for-protocol-freeze"
        and cost_review.get("cost_data_available") is True
        and cost_review.get("cloud_execution_authorized") is False
        and isinstance(cost_review.get("reviewed_at"), str)
        and RFC3339.fullmatch(cost_review["reviewed_at"]),
        "financial review is not an approved non-authorizing review",
    )
    require(
        isinstance(component_frozen_at, dict)
        and set(component_frozen_at) == COMPONENT_PATHS
        and all(
            isinstance(value, str) and RFC3339.fullmatch(value)
            for value in component_frozen_at.values()
        ),
        "component freeze timestamps are incomplete",
    )
    require(
        isinstance(frozen_at, str) and RFC3339.fullmatch(frozen_at),
        "frozen-at must be an RFC3339 UTC timestamp",
    )
    prerequisite_times = list(component_frozen_at.values()) + [
        researcher_approval["approved_at"],
        cost_review["reviewed_at"],
    ]
    require(
        frozen_at >= max(prerequisite_times),
        "protocol frozen-at cannot precede a policy, runtime or approval",
    )

    frozen_protocol = copy.deepcopy(protocol)
    frozen_protocol["status"] = "frozen"
    frozen_protocol["frozen_at"] = frozen_at
    frozen_protocol["confirmatory_collection_allowed"] = True
    frozen_content = render(frozen_protocol)
    audit_content = render(audit_result)
    receipt = {
        "schema_version": "1.0.0",
        "mechanism": "protocol-freeze-finalization",
        "status": "proposed-frozen-protocol-requires-application",
        "protocol_id": protocol["protocol_id"],
        "candidate_protocol_sha256": candidate_protocol_sha256,
        "frozen_protocol_sha256": sha256_bytes(frozen_content),
        "frozen_at": frozen_at,
        "component_frozen_at": dict(sorted(component_frozen_at.items())),
        "pre_freeze_audit_sha256": sha256_bytes(audit_content),
        "pre_freeze_audit": {
            "passed_count": audit_result["passed_count"],
            "check_count": audit_result["check_count"],
            "blocking_requirements": [],
        },
        "researcher_approval": copy.deepcopy(researcher_binding),
        "financial_review": copy.deepcopy(cost_binding),
        "confirmatory_collection_allowed": True,
        "cloud_execution_authorized": False,
        "cloud_mutation_performed": False,
        "active_repository_files_modified": False,
    }
    return frozen_content, audit_content, receipt


def repository_binding(repo_root, path, label):
    repo_root = pathlib.Path(repo_root).resolve()
    path = pathlib.Path(path).resolve()
    try:
        relative = path.relative_to(repo_root)
    except ValueError as error:
        raise ValueError(f"{label} must be inside the repository") from error
    require(path.is_file(), f"{label} does not exist")
    return {"path": relative.as_posix(), "sha256": sha256_file(path)}


def load_sealed_auditor(repo_root, protocol):
    binding = protocol.get("frozen_inputs", {}).get("protocol_freeze_auditor")
    validate_binding(binding, "protocol freeze auditor")
    path = pathlib.Path(repo_root) / binding["path"]
    require(
        path.is_file() and sha256_file(path) == binding["sha256"],
        "protocol freeze auditor hash differs",
    )
    spec = importlib.util.spec_from_file_location("sealed_protocol_freeze_auditor", path)
    require(spec is not None and spec.loader is not None, "cannot load sealed auditor")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_exclusive(path, content):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=pathlib.Path, required=True)
    parser.add_argument(
        "--protocol", type=pathlib.Path, default=pathlib.Path(PROTOCOL_PATH)
    )
    parser.add_argument("--researcher-approval", type=pathlib.Path, required=True)
    parser.add_argument("--cost-review", type=pathlib.Path, required=True)
    parser.add_argument("--frozen-at", required=True)
    parser.add_argument("--output-directory", type=pathlib.Path, required=True)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    protocol_path = (repo_root / args.protocol).resolve()
    try:
        protocol = load(protocol_path)
        researcher_path = (repo_root / args.researcher_approval).resolve()
        cost_path = (repo_root / args.cost_review).resolve()
        researcher_approval = load(researcher_path)
        cost_review = load(cost_path)
        auditor = load_sealed_auditor(repo_root, protocol)
        audit_result = auditor.audit(
            repo_root, protocol, researcher_approval, cost_review
        )
        component_frozen_at = {
            relative: load(repo_root / relative).get("frozen_at")
            for relative in COMPONENT_PATHS
        }
        frozen_content, audit_content, receipt = finalize(
            protocol,
            sha256_file(protocol_path),
            audit_result,
            researcher_approval,
            repository_binding(repo_root, researcher_path, "researcher approval"),
            cost_review,
            repository_binding(repo_root, cost_path, "financial review"),
            component_frozen_at,
            args.frozen_at,
        )
        write_exclusive(
            args.output_directory / "proposed" / PROTOCOL_PATH, frozen_content
        )
        write_exclusive(args.output_directory / "pre-freeze-audit.json", audit_content)
        receipt_content = render(receipt)
        write_exclusive(
            args.output_directory / "protocol-freeze-receipt.json", receipt_content
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"protocol freeze finalization rejected: {error}", file=sys.stderr)
        return 1
    print(receipt_content.decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
