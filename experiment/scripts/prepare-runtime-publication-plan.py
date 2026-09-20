#!/usr/bin/env python3

"""Validate CI runtime-image evidence and prepare a non-authorizing publish plan."""

import argparse
import json
import pathlib
import re
import sys


COMMIT_PATTERN = re.compile(r"^[a-f0-9]{40}$")
IMAGE_ID_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")
EXPECTED_IMAGES = {
    "checkout-pdt-controller",
    "oracle-harness",
    "currency-reference",
}
DEFAULT_FREE_TIER_BYTES = 500_000_000


def load(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def prepare_plan(
    summary,
    expected_commit,
    existing_repository_bytes,
    registry_prefix,
    free_tier_bytes=DEFAULT_FREE_TIER_BYTES,
    billing_account_other_storage_bytes=None,
    detailed_cost_data_available=False,
    workflow_artifact_id=None,
):
    require(summary.get("schema_version") == "1.1.0", "unsupported summary schema")
    require(summary.get("published_to_registry") is False, "CI evidence must be pre-publication")
    require(summary.get("build_platform") == "linux/amd64", "unexpected build platform")
    require(COMMIT_PATTERN.fullmatch(expected_commit or ""), "expected commit must be a full Git SHA")
    require(isinstance(existing_repository_bytes, int) and existing_repository_bytes >= 0, "invalid existing repository size")
    require(isinstance(free_tier_bytes, int) and free_tier_bytes > 0, "invalid free-tier allowance")
    require(registry_prefix and not registry_prefix.endswith("/"), "invalid registry prefix")

    source = summary.get("source", {})
    require(source.get("commit") == expected_commit, "CI evidence does not match the expected commit")
    require(COMMIT_PATTERN.fullmatch(source.get("tree", "")), "CI evidence lacks a full source-tree SHA")
    require(isinstance(source.get("pull_request_number"), int) and source["pull_request_number"] > 0, "invalid pull request number")
    require(bool(source.get("repository")), "missing source repository")
    require(bool(source.get("workflow_run_id")), "missing workflow run id")

    images = summary.get("images")
    require(isinstance(images, list), "images must be a list")
    require({item.get("name") for item in images} == EXPECTED_IMAGES, "runtime image set is incomplete or unexpected")
    require(len(images) == len(EXPECTED_IMAGES), "runtime image names must be unique")

    planned_images = []
    total_uncompressed_bytes = 0
    for image in sorted(images, key=lambda item: item["name"]):
        name = image["name"]
        require(IMAGE_ID_PATTERN.fullmatch(image.get("image_id", "")), f"{name}: invalid local image id")
        require(image.get("sbom") == "pass", f"{name}: SBOM did not pass")
        require(image.get("scan") == "pass", f"{name}: vulnerability scan did not pass")
        require(isinstance(image.get("size_bytes"), int) and image["size_bytes"] > 0, f"{name}: invalid size")
        require(image.get("local_tag") == f"online-boutique/{name}:pr-{expected_commit}", f"{name}: source tag mismatch")
        total_uncompressed_bytes += image["size_bytes"]
        target_tag = f"{registry_prefix}/{name}:git-{expected_commit}"
        planned_images.append(
            {
                "name": name,
                "validated_local_image_id": image["image_id"],
                "uncompressed_size_bytes": image["size_bytes"],
                "target_tag": target_tag,
                "required_post_publish_binding": f"{registry_prefix}/{name}@sha256:<registry-manifest-digest>",
            }
        )

    projected_repository_upper_bound = existing_repository_bytes + total_uncompressed_bytes
    fits_unshared_allowance = projected_repository_upper_bound <= free_tier_bytes
    account_usage_known = isinstance(billing_account_other_storage_bytes, int) and billing_account_other_storage_bytes >= 0
    projected_account_upper_bound = None
    fits_account_allowance = None
    if account_usage_known:
        projected_account_upper_bound = billing_account_other_storage_bytes + projected_repository_upper_bound
        fits_account_allowance = projected_account_upper_bound <= free_tier_bytes

    blockers = ["explicit cloud publication authorization is absent"]
    if not detailed_cost_data_available:
        blockers.append("detailed current billing cost is unavailable")
    if not account_usage_known:
        blockers.append("billing-account-wide Artifact Registry storage is unavailable")
    if not fits_unshared_allowance:
        blockers.append("projected repository storage exceeds the unshared free-tier allowance")
    if fits_account_allowance is False:
        blockers.append("projected billing-account storage exceeds the free-tier allowance")

    return {
        "schema_version": "1.0.0",
        "decision": "review-required-no-publication-authorized",
        "cloud_execution_authorized": False,
        "source": source,
        "workflow_artifact_id": workflow_artifact_id,
        "registry_prefix": registry_prefix,
        "images": planned_images,
        "storage_assessment": {
            "measurement_kind": "conservative upper bound from uncompressed Docker image sizes",
            "existing_repository_bytes": existing_repository_bytes,
            "additional_uncompressed_upper_bound_bytes": total_uncompressed_bytes,
            "projected_repository_upper_bound_bytes": projected_repository_upper_bound,
            "free_tier_allowance_bytes": free_tier_bytes,
            "fits_if_allowance_is_unshared": fits_unshared_allowance,
            "billing_account_other_storage_bytes": billing_account_other_storage_bytes,
            "projected_billing_account_upper_bound_bytes": projected_account_upper_bound,
            "fits_billing_account_allowance": fits_account_allowance,
        },
        "detailed_cost_data_available": bool(detailed_cost_data_available),
        "review_blockers": blockers,
        "publication_requirements": [
            "rebuild the exact source commit in the protected publication job",
            "scan the exact images that will be pushed",
            "record the registry manifest digests after push",
            "bind those immutable digests into the PDT and oracle manifests",
            "do not treat this plan as financial or cloud-execution authorization",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=pathlib.Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--existing-repository-bytes", type=int, required=True)
    parser.add_argument("--registry-prefix", required=True)
    parser.add_argument("--free-tier-bytes", type=int, default=DEFAULT_FREE_TIER_BYTES)
    parser.add_argument("--billing-account-other-storage-bytes", type=int)
    parser.add_argument("--detailed-cost-data-available", action="store_true")
    parser.add_argument("--workflow-artifact-id")
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    try:
        plan = prepare_plan(
            load(args.summary),
            args.expected_commit,
            args.existing_repository_bytes,
            args.registry_prefix,
            args.free_tier_bytes,
            args.billing_account_other_storage_bytes,
            args.detailed_cost_data_available,
            args.workflow_artifact_id,
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"publication plan rejected: {error}", file=sys.stderr)
        return 1

    rendered = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
