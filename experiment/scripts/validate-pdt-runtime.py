#!/usr/bin/env python3

import argparse
import hashlib
import json
import pathlib
import re


DIGEST_PATTERN = re.compile(r"^[a-f0-9]{64}$")
IMAGE_PATTERN = re.compile(
    r"^us-central1-docker\.pkg\.dev/microservices-demo-tcc/"
    r"online-boutique-experiment/checkout-pdt-controller@sha256:[a-f0-9]{64}$"
)
COMMIT_PATTERN = re.compile(r"^[a-f0-9]{40}$")
RFC3339_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
PUBLICATION_BINDING_KEYS = {
    "schema_version",
    "publication_summary_sha256",
    "repository",
    "source_commit",
    "source_tree",
    "pull_request_number",
    "workflow_run_id",
    "published_at",
    "build_platform",
    "protected_environment",
    "explicit_cloud_gate",
    "cost_review_acknowledged",
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


def validate_publication_binding(binding):
    return (
        isinstance(binding, dict)
        and set(binding) == PUBLICATION_BINDING_KEYS
        and binding.get("schema_version") == "1.0.0"
        and isinstance(binding.get("publication_summary_sha256"), str)
        and bool(DIGEST_PATTERN.fullmatch(binding["publication_summary_sha256"]))
        and binding.get("repository") == "omatheu/microservices-demo"
        and isinstance(binding.get("source_commit"), str)
        and bool(COMMIT_PATTERN.fullmatch(binding["source_commit"]))
        and isinstance(binding.get("source_tree"), str)
        and bool(COMMIT_PATTERN.fullmatch(binding["source_tree"]))
        and isinstance(binding.get("pull_request_number"), int)
        and not isinstance(binding["pull_request_number"], bool)
        and binding["pull_request_number"] > 0
        and isinstance(binding.get("workflow_run_id"), str)
        and binding["workflow_run_id"].isdigit()
        and int(binding["workflow_run_id"]) > 0
        and isinstance(binding.get("published_at"), str)
        and bool(RFC3339_PATTERN.fullmatch(binding["published_at"]))
        and binding.get("build_platform") == "linux/amd64"
        and binding.get("protected_environment") == "tcc-experiment"
        and binding.get("explicit_cloud_gate") is True
        and binding.get("cost_review_acknowledged") is True
    )


def validate(repo_root, manifest, require_frozen=False):
    if manifest.get("runtime_id") != "checkout-pdt-controller-v1":
        raise ValueError("PDT runtime ID is invalid")
    if manifest.get("status") not in {"pre-registration-candidate", "frozen"}:
        raise ValueError("PDT runtime status is invalid")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise ValueError("PDT runtime file inventory is empty")
    paths = [entry.get("path") for entry in entries if isinstance(entry, dict)]
    if len(paths) != len(entries) or len(paths) != len(set(paths)):
        raise ValueError("PDT runtime file paths are invalid or duplicated")
    for entry in entries:
        relative = pathlib.PurePosixPath(entry["path"])
        expected = entry.get("sha256")
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"PDT runtime path is unsafe: {entry['path']}")
        if not isinstance(expected, str) or not DIGEST_PATTERN.fullmatch(expected):
            raise ValueError(f"PDT runtime digest is invalid: {entry['path']}")
        if sha256_file(pathlib.Path(repo_root) / relative) != expected:
            raise ValueError(f"PDT runtime hash differs: {entry['path']}")
    image = manifest.get("controller_image")
    image_ready = isinstance(image, str) and bool(IMAGE_PATTERN.fullmatch(image))
    publication_binding = manifest.get("publication_binding")
    publication_bound = validate_publication_binding(publication_binding)
    if image_ready and not publication_bound:
        raise ValueError("PDT runtime image lacks an attested publication binding")
    if not image_ready and publication_binding is not None:
        raise ValueError("PDT runtime publication binding exists without an image")
    if manifest["status"] == "frozen" and not image_ready:
        raise ValueError("frozen PDT runtime requires an immutable controller image digest")
    if manifest["status"] == "frozen" and not (
        isinstance(manifest.get("frozen_at"), str)
        and RFC3339_PATTERN.fullmatch(manifest["frozen_at"])
    ):
        raise ValueError("frozen PDT runtime requires a freeze timestamp")
    if manifest["status"] == "pre-registration-candidate" and manifest.get("frozen_at") is not None:
        raise ValueError("candidate PDT runtime cannot have a freeze timestamp")
    if require_frozen and (
        manifest["status"] != "frozen" or not image_ready or not publication_bound
    ):
        raise ValueError("PDT runtime is not frozen")
    return {
        "runtime_id": manifest["runtime_id"],
        "status": manifest["status"],
        "file_count": len(entries),
        "image_ready": image_ready,
        "publication_bound": publication_bound,
        "frozen": manifest["status"] == "frozen" and image_ready and publication_bound,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--require-frozen", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(args.repo_root.resolve(), load(args.manifest), args.require_frozen)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"PDT runtime validation failed: {error}") from error
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
