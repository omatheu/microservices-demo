#!/usr/bin/env python3

"""Bind an attested runtime publication to reviewable PDT/oracle manifests."""

import argparse
import copy
import hashlib
import json
import os
import pathlib
import re
import sys


DIGEST = re.compile(r"^[a-f0-9]{64}$")
COMMIT = re.compile(r"^[a-f0-9]{40}$")
IMAGE_ID = re.compile(r"^sha256:[a-f0-9]{64}$")
RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
POSITIVE_INTEGER = re.compile(r"^[1-9][0-9]*$")
REPOSITORY = "omatheu/microservices-demo"
REGISTRY_PREFIX = (
    "us-central1-docker.pkg.dev/"
    "microservices-demo-tcc/online-boutique-experiment"
)
IMAGE_NAMES = {
    "checkout-pdt-controller",
    "oracle-harness",
    "currency-reference",
}


def load(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


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


def validate_inventory(repo_root, manifest, label):
    require(
        manifest.get("status") == "pre-registration-candidate",
        f"{label} must remain a pre-registration candidate while images are bound",
    )
    require(manifest.get("frozen_at") is None, f"{label} already has a freeze timestamp")
    entries = manifest.get("files")
    require(isinstance(entries, list) and entries, f"{label} file inventory is empty")
    paths = [item.get("path") for item in entries if isinstance(item, dict)]
    require(
        len(paths) == len(entries) and len(paths) == len(set(paths)),
        f"{label} file inventory is invalid or duplicated",
    )
    for item in entries:
        relative = pathlib.PurePosixPath(item["path"])
        expected = item.get("sha256")
        require(
            relative.parts and not relative.is_absolute() and ".." not in relative.parts,
            f"{label} contains an unsafe path",
        )
        require(
            isinstance(expected, str) and DIGEST.fullmatch(expected),
            f"{label} contains an invalid file digest",
        )
        require(
            sha256_file(pathlib.Path(repo_root) / relative) == expected,
            f"{label} file hash differs: {item['path']}",
        )
    require(
        manifest.get("publication_binding") is None,
        f"{label} already contains a publication binding",
    )


def validate_summary(summary, expected_commit, expected_tree):
    require(summary.get("schema_version") == "1.0.0", "unsupported publication schema")
    require(summary.get("published_to_registry") is True, "runtime images were not published")
    require(summary.get("build_platform") == "linux/amd64", "unexpected build platform")
    require(COMMIT.fullmatch(expected_commit or ""), "expected commit must be a full Git SHA")
    require(COMMIT.fullmatch(expected_tree or ""), "expected tree must be a full Git tree SHA")

    source = summary.get("source")
    require(isinstance(source, dict), "publication source is absent")
    require(source.get("repository") == REPOSITORY, "publication repository differs")
    require(source.get("commit") == expected_commit, "publication commit differs")
    require(source.get("tree") == expected_tree, "publication tree differs")
    require(
        isinstance(source.get("pull_request_number"), int)
        and not isinstance(source["pull_request_number"], bool)
        and source["pull_request_number"] > 0,
        "publication pull request is invalid",
    )
    workflow_run_id = source.get("workflow_run_id")
    require(
        isinstance(workflow_run_id, str) and POSITIVE_INTEGER.fullmatch(workflow_run_id),
        "publication workflow run is invalid",
    )
    require(
        isinstance(summary.get("published_at"), str)
        and RFC3339.fullmatch(summary["published_at"]),
        "publication timestamp is invalid",
    )

    authorization = summary.get("authorization")
    require(
        isinstance(authorization, dict)
        and authorization.get("protected_environment") == "tcc-experiment"
        and authorization.get("explicit_cloud_gate") is True
        and authorization.get("cost_review_acknowledged") is True,
        "publication authorization evidence is incomplete",
    )

    images = summary.get("images")
    require(isinstance(images, list), "publication images must be a list")
    names = [item.get("name") for item in images if isinstance(item, dict)]
    require(
        len(names) == len(images)
        and len(names) == len(set(names))
        and set(names) == IMAGE_NAMES,
        "publication image set is incomplete or unexpected",
    )
    normalized = {}
    for item in images:
        name = item["name"]
        registry_digest = item.get("registry_digest")
        immutable_reference = item.get("immutable_reference")
        require(
            isinstance(registry_digest, str) and IMAGE_ID.fullmatch(registry_digest),
            f"{name}: registry digest is invalid",
        )
        require(
            immutable_reference
            == f"{REGISTRY_PREFIX}/{name}@{registry_digest}",
            f"{name}: immutable reference differs from the reviewed registry",
        )
        require(
            item.get("source_tag")
            == f"{REGISTRY_PREFIX}/{name}:git-{expected_commit}",
            f"{name}: source tag differs from the expected commit",
        )
        require(
            isinstance(item.get("local_image_id"), str)
            and IMAGE_ID.fullmatch(item["local_image_id"]),
            f"{name}: local image ID is invalid",
        )
        require(
            isinstance(item.get("uncompressed_size_bytes"), int)
            and not isinstance(item["uncompressed_size_bytes"], bool)
            and item["uncompressed_size_bytes"] > 0,
            f"{name}: image size is invalid",
        )
        require(item.get("sbom") == "pass", f"{name}: SBOM did not pass")
        require(
            item.get("vulnerability_scan") == "pass",
            f"{name}: vulnerability scan did not pass",
        )
        require(item.get("published") is True, f"{name}: publication flag is absent")
        normalized[name] = immutable_reference
    return source, authorization, normalized


def bind(
    repo_root,
    summary,
    summary_sha256,
    pdt_manifest,
    oracle_manifest,
    expected_commit,
    expected_tree,
):
    require(
        isinstance(summary_sha256, str) and DIGEST.fullmatch(summary_sha256),
        "publication summary digest is invalid",
    )
    require(
        pdt_manifest.get("runtime_id") == "checkout-pdt-controller-v1",
        "PDT runtime identity is invalid",
    )
    require(
        oracle_manifest.get("suite_id") == "checkout-independent-oracle-v1",
        "oracle suite identity is invalid",
    )
    validate_inventory(repo_root, pdt_manifest, "PDT runtime manifest")
    validate_inventory(repo_root, oracle_manifest, "oracle suite manifest")
    require(
        pdt_manifest.get("controller_image") is None,
        "PDT runtime already contains a controller image",
    )
    require(
        oracle_manifest.get("images")
        == {"oracle_harness": None, "currency_reference": None},
        "oracle suite already contains image bindings",
    )
    source, authorization, images = validate_summary(
        summary, expected_commit, expected_tree
    )
    binding = {
        "schema_version": "1.0.0",
        "publication_summary_sha256": summary_sha256,
        "repository": source["repository"],
        "source_commit": source["commit"],
        "source_tree": source["tree"],
        "pull_request_number": source["pull_request_number"],
        "workflow_run_id": source["workflow_run_id"],
        "published_at": summary["published_at"],
        "build_platform": summary["build_platform"],
        "protected_environment": authorization["protected_environment"],
        "explicit_cloud_gate": True,
        "cost_review_acknowledged": True,
    }

    pdt_bound = copy.deepcopy(pdt_manifest)
    pdt_bound["controller_image"] = images["checkout-pdt-controller"]
    pdt_bound["publication_binding"] = copy.deepcopy(binding)
    oracle_bound = copy.deepcopy(oracle_manifest)
    oracle_bound["images"] = {
        "oracle_harness": images["oracle-harness"],
        "currency_reference": images["currency-reference"],
    }
    oracle_bound["publication_binding"] = copy.deepcopy(binding)
    receipt = {
        "schema_version": "1.0.0",
        "mechanism": "runtime-publication-manifest-binding",
        "publication_binding": binding,
        "immutable_images": {
            name: images[name] for name in sorted(images)
        },
        "status": "proposed-manifests-require-review",
        "cloud_mutation_performed": False,
        "protocol_frozen": False,
    }
    return pdt_bound, oracle_bound, receipt


def render(value):
    return (json.dumps(value, indent=2) + "\n").encode()


def write_exclusive(path, content):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=pathlib.Path, required=True)
    parser.add_argument("--publication-summary", type=pathlib.Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-tree", required=True)
    parser.add_argument(
        "--pdt-manifest",
        type=pathlib.Path,
        default=pathlib.Path("experiment/pdt/runtime-manifest.json"),
    )
    parser.add_argument(
        "--oracle-manifest",
        type=pathlib.Path,
        default=pathlib.Path("experiment/oracle/suite-manifest.json"),
    )
    parser.add_argument("--output-directory", type=pathlib.Path, required=True)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    try:
        summary_path = args.publication_summary.resolve()
        pdt_bound, oracle_bound, receipt = bind(
            repo_root,
            load(summary_path),
            sha256_file(summary_path),
            load(repo_root / args.pdt_manifest),
            load(repo_root / args.oracle_manifest),
            args.expected_commit,
            args.expected_tree,
        )
        pdt_content = render(pdt_bound)
        oracle_content = render(oracle_bound)
        receipt["proposed_manifests"] = {
            "pdt_runtime_manifest_sha256": sha256_bytes(pdt_content),
            "oracle_suite_manifest_sha256": sha256_bytes(oracle_content),
        }
        write_exclusive(
            args.output_directory / "pdt-runtime-manifest.bound.json", pdt_content
        )
        write_exclusive(
            args.output_directory / "oracle-suite-manifest.bound.json", oracle_content
        )
        receipt_content = render(receipt)
        write_exclusive(args.output_directory / "binding-receipt.json", receipt_content)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"runtime publication binding rejected: {error}", file=sys.stderr)
        return 1
    print(receipt_content.decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
