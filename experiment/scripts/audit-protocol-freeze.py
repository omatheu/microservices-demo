#!/usr/bin/env python3

import argparse
import hashlib
import json
import pathlib
import re


DIGEST_PATTERN = re.compile(r"^[a-f0-9]{64}$")
IMAGE_PATTERN = re.compile(r"^[^\s@:]+(?:/[^\s@:]+)+@sha256:[a-f0-9]{64}$")
RFC3339_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
COMMIT_PATTERN = re.compile(r"^[a-f0-9]{40}$")


def load(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_check(checks, check_id, passed, detail):
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def load_optional(path):
    try:
        return load(path)
    except FileNotFoundError:
        return None


def audit(repo_root, protocol, researcher_approval=None, cost_review=None):
    repo_root = pathlib.Path(repo_root)
    checks = []
    protocol_path = repo_root / "experiment/protocol/protocol-v1.json"

    operator_count = sum(item.get("count", 0) for item in protocol.get("operators", []))
    design = protocol.get("research_design", {})
    limits = protocol.get("execution_limits", {})
    add_check(
        checks,
        "protocol-structure",
        design.get("candidate_count") == operator_count
        and design.get("block_count", 0) * design.get("block_size", 0) == operator_count
        and limits.get("candidate_block_size") == design.get("block_size")
        and design.get("technical_repetitions_per_candidate", 0) >= 2,
        f"declared={design.get('candidate_count')}, operators={operator_count}",
    )
    add_check(
        checks,
        "collection-locked-before-freeze",
        protocol.get("status") == "pre-registration-candidate"
        and protocol.get("confirmatory_collection_allowed") is False
        and protocol.get("frozen_at") is None,
        "draft protocol must keep confirmatory collection disabled",
    )

    frozen_inputs = protocol.get("frozen_inputs", {})
    input_hashes_match = bool(frozen_inputs)
    for binding in frozen_inputs.values():
        relative = pathlib.PurePosixPath(binding.get("path", ""))
        expected = binding.get("sha256")
        if (
            not relative.parts
            or relative.is_absolute()
            or ".." in relative.parts
            or not isinstance(expected, str)
            or not DIGEST_PATTERN.fullmatch(expected)
            or sha256_file(repo_root / relative) != expected
        ):
            input_hashes_match = False
            break
    add_check(
        checks,
        "frozen-input-hashes",
        input_hashes_match,
        f"verified {len(frozen_inputs)} protocol input bindings",
    )

    registry = load(repo_root / "experiment/mutations/registry.json")
    registry_ids = {item.get("id") for item in registry.get("operators", [])}
    protocol_ids = {item.get("id") for item in protocol.get("operators", [])}
    materializer = registry.get("materializer", {})
    materializer_path = repo_root / materializer.get("path", "")
    operators_ready = (
        registry.get("protocol_id") == protocol.get("protocol_id")
        and registry_ids == protocol_ids
        and all(item.get("status") == "implemented" for item in registry.get("operators", []))
        and materializer_path.is_file()
        and sha256_file(materializer_path) == materializer.get("sha256")
    )
    add_check(
        checks,
        "mutation-operators-implemented",
        operators_ready,
        f"implemented={sum(item.get('status') == 'implemented' for item in registry.get('operators', []))}/{len(protocol_ids)}",
    )

    policy_requirements = [
        ("ci-policy-frozen", "experiment/ci/policy.json"),
        ("staging-thresholds-frozen", "experiment/staging/safety-thresholds.json"),
        ("pdt-model-policy-frozen", "experiment/pdt/model-policy.json"),
        ("oracle-policy-frozen", "experiment/oracle/policy-v1.json"),
    ]
    for check_id, relative in policy_requirements:
        value = load(repo_root / relative)
        frozen = value.get("status") == "frozen" and bool(
            RFC3339_PATTERN.fullmatch(value.get("frozen_at", ""))
        )
        add_check(checks, check_id, frozen, f"status={value.get('status', 'missing')}")

    pdt_runtime = load(repo_root / "experiment/pdt/runtime-manifest.json")
    pdt_runtime_hashes_match = True
    for entry in pdt_runtime.get("files", []):
        expected = entry.get("sha256")
        path = repo_root / entry.get("path", "")
        if (
            not path.is_file()
            or not isinstance(expected, str)
            or not DIGEST_PATTERN.fullmatch(expected)
            or sha256_file(path) != expected
        ):
            pdt_runtime_hashes_match = False
            break
    add_check(
        checks,
        "pdt-runtime-file-hashes",
        pdt_runtime_hashes_match and bool(pdt_runtime.get("files")),
        f"verified {len(pdt_runtime.get('files', []))} PDT runtime files",
    )
    controller_image = pdt_runtime.get("controller_image")
    controller_image_ready = isinstance(controller_image, str) and bool(
        IMAGE_PATTERN.fullmatch(controller_image)
    )
    add_check(
        checks,
        "pdt-controller-image-bound",
        controller_image_ready,
        "controller image requires an immutable digest",
    )
    add_check(
        checks,
        "pdt-runtime-frozen",
        pdt_runtime.get("status") == "frozen" and controller_image_ready,
        f"status={pdt_runtime.get('status', 'missing')}",
    )

    oracle_manifest = load(repo_root / "experiment/oracle/suite-manifest.json")
    oracle_hashes_match = True
    for entry in oracle_manifest.get("files", []):
        expected = entry.get("sha256")
        path = repo_root / entry.get("path", "")
        if (
            not path.is_file()
            or not isinstance(expected, str)
            or not DIGEST_PATTERN.fullmatch(expected)
            or sha256_file(path) != expected
        ):
            oracle_hashes_match = False
            break
    add_check(
        checks,
        "oracle-file-hashes",
        oracle_hashes_match and bool(oracle_manifest.get("files")),
        f"verified {len(oracle_manifest.get('files', []))} oracle files",
    )
    oracle_images = oracle_manifest.get("images", {})
    images_ready = set(oracle_images) == {"oracle_harness", "currency_reference"} and all(
        isinstance(value, str) and IMAGE_PATTERN.fullmatch(value)
        for value in oracle_images.values()
    )
    add_check(checks, "oracle-images-bound", images_ready, "both images require immutable digests")
    add_check(
        checks,
        "oracle-suite-frozen",
        oracle_manifest.get("status") == "frozen" and images_ready,
        f"status={oracle_manifest.get('status', 'missing')}",
    )

    protocol_sha256 = sha256_file(protocol_path)
    approval_ok = (
        isinstance(researcher_approval, dict)
        and researcher_approval.get("schema_version") == "1.0.0"
        and researcher_approval.get("protocol_id") == protocol.get("protocol_id")
        and researcher_approval.get("candidate_protocol_sha256") == protocol_sha256
        and researcher_approval.get("decision") == "approve-protocol-freeze"
        and researcher_approval.get("cloud_execution_authorized") is False
        and bool(researcher_approval.get("approved_by"))
        and bool(RFC3339_PATTERN.fullmatch(researcher_approval.get("approved_at", "")))
        and all(
            researcher_approval.get("acknowledgements", {}).get(item) is True
            for item in (
                "protocol_reviewed",
                "no_confirmatory_outcomes_observed",
                "changes_require_new_protocol_version",
            )
        )
    )
    add_check(
        checks,
        "researcher-approval",
        approval_ok,
        "explicit protocol approval is required and does not authorize cloud execution",
    )

    ceiling = limits.get("proposed_incremental_spend_ceiling_brl")
    review_at = limits.get("mandatory_cost_review_at_brl")
    cost_review_ok = (
        isinstance(cost_review, dict)
        and cost_review.get("schema_version") == "1.0.0"
        and cost_review.get("protocol_id") == protocol.get("protocol_id")
        and cost_review.get("project_id") == "microservices-demo-tcc"
        and cost_review.get("decision") == "approved-for-protocol-freeze"
        and cost_review.get("cloud_execution_authorized") is False
        and cost_review.get("cost_data_available") is True
        and cost_review.get("approved_incremental_spend_ceiling_brl") == ceiling
        and cost_review.get("mandatory_review_at_brl") == review_at
        and isinstance(cost_review.get("confirmatory_incremental_spend_brl"), (int, float))
        and 0 <= cost_review["confirmatory_incremental_spend_brl"] < review_at
        and bool(RFC3339_PATTERN.fullmatch(cost_review.get("reviewed_at", "")))
        and bool(RFC3339_PATTERN.fullmatch(cost_review.get("billing_data_as_of", "")))
        and bool(cost_review.get("evidence_reference"))
    )
    add_check(
        checks,
        "financial-review",
        cost_review_ok,
        f"ceiling=R${ceiling}, mandatory review=R${review_at}",
    )

    failed = [item["id"] for item in checks if not item["passed"]]
    return {
        "protocol_id": protocol.get("protocol_id"),
        "protocol_sha256": protocol_sha256,
        "ready_to_freeze": not failed,
        "passed_count": len(checks) - len(failed),
        "check_count": len(checks),
        "blocking_requirements": failed,
        "checks": checks,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=pathlib.Path, required=True)
    parser.add_argument(
        "--protocol",
        type=pathlib.Path,
        default=pathlib.Path("experiment/protocol/protocol-v1.json"),
    )
    parser.add_argument(
        "--researcher-approval",
        type=pathlib.Path,
        default=pathlib.Path("experiment/protocol/approvals/researcher-approval-v1.json"),
    )
    parser.add_argument(
        "--cost-review",
        type=pathlib.Path,
        default=pathlib.Path("experiment/protocol/approvals/cost-review-v1.json"),
    )
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    try:
        result = audit(
            repo_root,
            load(repo_root / args.protocol),
            load_optional(repo_root / args.researcher_approval),
            load_optional(repo_root / args.cost_review),
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"protocol freeze audit failed: {error}") from error
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.require_ready and not result["ready_to_freeze"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
