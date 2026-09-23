#!/usr/bin/env python3

"""Select and validate components affected by a release candidate."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import pathlib
import subprocess
import sys
from typing import Any, Iterable


SCHEMA_VERSION = "1.0.0"


def normalize_path(raw_path: str) -> str:
    path = raw_path.strip().replace("\\", "/")
    pure = pathlib.PurePosixPath(path)
    if not path or pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"invalid repository-relative path: {raw_path!r}")
    normalized = pure.as_posix()
    if normalized == ".":
        raise ValueError(f"invalid repository-relative path: {raw_path!r}")
    return normalized


def path_matches(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def load_matrix(path: pathlib.Path) -> dict[str, Any]:
    matrix = json.loads(path.read_text(encoding="utf-8"))
    if matrix.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported component matrix schema")

    components = matrix.get("components")
    if not isinstance(components, dict) or not components:
        raise ValueError("component matrix must define components")

    for name, component in components.items():
        if component.get("validation_status") not in {"implemented", "planned"}:
            raise ValueError(f"invalid validation status for component {name}")
        if not component.get("paths") or not component.get("validation_profile"):
            raise ValueError(f"incomplete component definition for {name}")
        if component.get("kind") == "service" and not component.get("docker_context"):
            raise ValueError(f"service component {name} is missing docker_context")
        if component.get("kind") == "service" and not component.get("source_image_name"):
            raise ValueError(f"service component {name} is missing source_image_name")

    for rule in matrix.get("shared_path_rules", []):
        unknown = sorted(set(rule.get("components", [])) - set(components))
        if unknown:
            raise ValueError(
                f"shared rule {rule.get('id', '<unknown>')} references unknown components: {unknown}"
            )
    return matrix


def select_components(matrix: dict[str, Any], raw_paths: Iterable[str], source: str) -> dict[str, Any]:
    changed_files = sorted({normalize_path(path) for path in raw_paths})
    components = matrix["components"]
    affected: set[str] = set()
    matched_paths: dict[str, set[str]] = {name: set() for name in components}
    ignored: list[str] = []
    unclassified: list[str] = []
    unknown_critical: list[str] = []

    for path in changed_files:
        matched = False
        for name, component in components.items():
            if path_matches(path, component["paths"]):
                affected.add(name)
                matched_paths[name].add(path)
                matched = True

        for rule in matrix.get("shared_path_rules", []):
            if path_matches(path, rule.get("paths", [])):
                for name in rule["components"]:
                    affected.add(name)
                    matched_paths[name].add(path)
                matched = True

        if matched:
            continue
        if path_matches(path, matrix.get("ignored_patterns", [])):
            ignored.append(path)
            continue

        unclassified.append(path)
        if any(path.startswith(prefix) for prefix in matrix.get("critical_prefixes", [])):
            unknown_critical.append(path)

    affected_components = []
    incomplete_components = []
    for name in sorted(affected):
        component = components[name]
        entry = {
            "name": name,
            "kind": component["kind"],
            "role": component["role"],
            "validation_profile": component["validation_profile"],
            "validation_status": component["validation_status"],
            "docker_context": component.get("docker_context"),
            "source_image_name": component.get("source_image_name"),
            "matched_paths": sorted(matched_paths[name]),
        }
        affected_components.append(entry)
        if component["validation_status"] != "implemented":
            incomplete_components.append(name)

    reasons = []
    if not changed_files:
        reasons.append("candidate has no changed files")
    elif not affected_components:
        reasons.append("candidate has no release-relevant component changes")
    if incomplete_components:
        reasons.append(
            "validation adapters are not implemented for: " + ", ".join(incomplete_components)
        )
    if unknown_critical:
        reasons.append("unclassified critical paths: " + ", ".join(unknown_critical))

    changed_files_sha256 = hashlib.sha256(
        ("\n".join(changed_files) + ("\n" if changed_files else "")).encode("utf-8")
    ).hexdigest()

    return {
        "schema_version": SCHEMA_VERSION,
        "selection_source": source,
        "matrix_scope": matrix["scope"],
        "changed_files": changed_files,
        "changed_files_sha256": changed_files_sha256,
        "affected_components": affected_components,
        "ignored_files": ignored,
        "unclassified_noncritical_files": sorted(set(unclassified) - set(unknown_critical)),
        "unknown_critical_paths": sorted(unknown_critical),
        "incomplete_validation_components": incomplete_components,
        "decision": "pass" if not reasons else "block",
        "reasons": reasons,
    }


def git_paths(repo_root: pathlib.Path, base_ref: str | None, head_ref: str) -> tuple[list[str], str]:
    if base_ref:
        command = ["git", "-C", str(repo_root), "diff", "--name-only", f"{base_ref}..{head_ref}"]
        source = f"git-range:{base_ref}..{head_ref}"
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        return result.stdout.splitlines(), source

    tracked = subprocess.run(
        ["git", "-C", str(repo_root), "diff", "--name-only", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    untracked = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "--others", "--exclude-standard"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    return tracked + untracked, "git-working-tree"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=pathlib.Path, required=True)
    parser.add_argument("--matrix", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--base-ref")
    parser.add_argument("--head-ref", default="HEAD")
    parser.add_argument("--changed-file", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        matrix = load_matrix(args.matrix)
        if args.changed_file:
            if args.base_ref:
                raise ValueError("--changed-file and --base-ref are mutually exclusive")
            paths = args.changed_file
            source = "explicit-paths"
        else:
            paths, source = git_paths(args.repo_root, args.base_ref, args.head_ref)
        result = select_components(matrix, paths, source)
    except (ValueError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"component selection failed: {error}", file=sys.stderr)
        return 2

    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if result["decision"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
