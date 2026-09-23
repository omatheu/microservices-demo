#!/usr/bin/env python3

"""Bind a staging overlay to the immutable artifacts approved by local CI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import sys
from typing import Any


SCHEMA_VERSION = "1.0.0"
REMOTE_REFERENCE = re.compile(
    r"^(?P<repository>[a-z0-9.-]+/[a-z0-9._-]+/[a-z0-9._/-]+)/"
    r"(?P<package>[a-z0-9._-]+)@(?P<digest>sha256:[0-9a-f]{64})$"
)


def load_json(path: pathlib.Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare(
    local_ci: dict[str, Any],
    candidate_id: str,
    base_kustomization: pathlib.Path,
    mode: str,
    local_ci_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if mode not in {"engineering", "confirmatory"}:
        raise ValueError("mode must be engineering or confirmatory")
    if local_ci.get("candidate_id") != candidate_id:
        raise ValueError("staging and local CI candidate IDs differ")
    if local_ci.get("scope") != "local-pre-staging-ci":
        raise ValueError("local CI decision has an unexpected scope")
    if local_ci.get("local_decision") != "pass":
        raise ValueError("staging requires a passing local CI decision")
    if local_ci.get("eligible_for_staging") is not True:
        raise ValueError("local CI did not mark the candidate eligible for staging")
    if mode == "confirmatory" and local_ci.get("confirmatory_eligible") is not True:
        raise ValueError("confirmatory staging requires confirmatory-eligible local CI")
    if mode == "confirmatory" and local_ci.get("git", {}).get("dirty") is not False:
        raise ValueError("confirmatory staging requires a clean candidate tree")

    expected_components = local_ci.get("component_selection", {}).get(
        "affected_service_components"
    )
    if not isinstance(expected_components, list) or any(
        not isinstance(component, str) for component in expected_components
    ):
        raise ValueError("local CI decision lacks affected_service_components")
    if len(expected_components) != len(set(expected_components)):
        raise ValueError("affected_service_components contains duplicates")

    artifacts = local_ci.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("local CI decision lacks artifact evidence")
    artifacts_by_component: dict[str, dict[str, Any]] = {}
    images: list[dict[str, str]] = []
    bound_artifacts: list[dict[str, str]] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValueError("artifact evidence entries must be objects")
        component = artifact.get("component")
        if not isinstance(component, str) or not component:
            raise ValueError("artifact evidence is missing a component")
        if component in artifacts_by_component:
            raise ValueError(f"duplicate artifact for component {component}")
        artifacts_by_component[component] = artifact
        source_image_name = artifact.get("source_image_name")
        if not isinstance(source_image_name, str) or "/" not in source_image_name:
            raise ValueError(f"{component} lacks its source image name")

        for status_name in ("build_status", "sbom_status", "image_scan_status"):
            if artifact.get(status_name) != "pass":
                raise ValueError(f"{component} has non-passing {status_name}")
        if artifact.get("publication_status") != "pass":
            raise ValueError(f"{component} was not published by the validated CI run")
        remote_reference = artifact.get("remote_reference")
        manifest_digest = artifact.get("manifest_digest")
        if not isinstance(remote_reference, str):
            raise ValueError(f"{component} lacks an immutable remote reference")
        match = REMOTE_REFERENCE.fullmatch(remote_reference)
        if match is None:
            raise ValueError(f"invalid immutable remote reference for {component}")
        if match.group("package") != component:
            raise ValueError(f"artifact package does not match component {component}")
        if match.group("digest") != manifest_digest:
            raise ValueError(f"artifact digest mismatch for {component}")

        new_name, digest = remote_reference.rsplit("@", maxsplit=1)
        images.append({"name": source_image_name, "newName": new_name, "digest": digest})
        bound_artifacts.append(
            {
                "component": component,
                "source_image_name": source_image_name,
                "remote_reference": remote_reference,
                "manifest_digest": digest,
            }
        )

    if set(artifacts_by_component) != set(expected_components):
        raise ValueError(
            "artifact set differs from affected services: "
            f"expected={sorted(expected_components)} actual={sorted(artifacts_by_component)}"
        )

    images.sort(key=lambda image: image["name"])
    bound_artifacts.sort(key=lambda artifact: artifact["component"])
    overlay = {
        "apiVersion": "kustomize.config.k8s.io/v1beta1",
        "kind": "Kustomization",
        "resources": [str(base_kustomization.resolve())],
        "images": images,
    }
    binding = {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "mode": mode,
        "git_commit": local_ci.get("git", {}).get("commit"),
        "local_ci_run_id": local_ci.get("run_id"),
        "local_ci_decision_sha256": local_ci_sha256,
        "base_kustomization": str(base_kustomization.resolve()),
        "artifacts": bound_artifacts,
        "decision": "bound",
    }
    return overlay, binding


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-ci-decision", type=pathlib.Path, required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--base-kustomization", type=pathlib.Path, required=True)
    parser.add_argument("--mode", choices=("engineering", "confirmatory"), required=True)
    parser.add_argument("--output-directory", type=pathlib.Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        local_ci = load_json(args.local_ci_decision)
        if not args.base_kustomization.is_dir():
            raise ValueError("base kustomization directory does not exist")
        overlay, binding = prepare(
            local_ci,
            args.candidate_id,
            args.base_kustomization,
            args.mode,
            sha256_file(args.local_ci_decision),
        )
        args.output_directory.mkdir(parents=True, exist_ok=True)
        overlay["resources"] = [
            os.path.relpath(
                args.base_kustomization.resolve(),
                start=args.output_directory.resolve(),
            )
        ]
        (args.output_directory / "kustomization.yaml").write_text(
            json.dumps(overlay, indent=2) + "\n", encoding="utf-8"
        )
        (args.output_directory / "candidate-binding.json").write_text(
            json.dumps(binding, indent=2) + "\n", encoding="utf-8"
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"candidate binding failed: {error}", file=sys.stderr)
        return 1
    print(args.output_directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
