#!/usr/bin/env python3

import argparse
import json
import pathlib
import re
import subprocess


CANDIDATE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
FORBIDDEN_PUBLIC_KEYS = {
    "context_dependency",
    "intended_label",
    "operator_id",
    "parameters",
    "stratum",
}


def recursively_find_keys(value, forbidden):
    findings = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in forbidden:
                findings.append(key)
            findings.extend(recursively_find_keys(child, forbidden))
    elif isinstance(value, list):
        for child in value:
            findings.extend(recursively_find_keys(child, forbidden))
    return findings


def validate_definition(repo_root, relative_path):
    relative = pathlib.PurePosixPath(relative_path)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or len(relative.parts) != 4
        or relative.parts[:3] != ("experiment", "pdt", "candidates")
        or relative.suffix != ".json"
    ):
        raise ValueError("candidate definition path is outside the public candidate directory")
    path = pathlib.Path(repo_root) / relative
    with path.open(encoding="utf-8") as stream:
        definition = json.load(stream)
    candidate_id = definition.get("candidate_id")
    if not isinstance(candidate_id, str) or not CANDIDATE_ID_PATTERN.fullmatch(candidate_id):
        raise ValueError("candidate definition has an invalid candidate_id")
    if relative.name != f"{candidate_id}.json":
        raise ValueError("candidate definition filename and candidate_id differ")
    leaked = sorted(set(recursively_find_keys(definition, FORBIDDEN_PUBLIC_KEYS)))
    if leaked:
        raise ValueError("candidate definition leaks private keys: " + ", ".join(leaked))
    alternatives = definition.get("alternatives")
    if not isinstance(alternatives, list):
        raise ValueError("candidate definition alternatives are missing")
    deploy_as_is = [
        item
        for item in alternatives
        if isinstance(item, dict)
        and item.get("id") == "deploy-as-is"
        and item.get("action") == "deploy"
    ]
    if len(deploy_as_is) != 1:
        raise ValueError("candidate definition requires exactly one deploy-as-is alternative")
    return candidate_id


def regular_pull_request_identity(pull_request_number, head_sha, reason):
    if not re.fullmatch(r"[1-9][0-9]*", str(pull_request_number)):
        raise ValueError("pull request number is invalid")
    if not re.fullmatch(r"[a-fA-F0-9]{12,64}", head_sha):
        raise ValueError("pull request head SHA is invalid")
    return {
        "candidate_id": f"pr-{pull_request_number}-{head_sha[:12].lower()}",
        "candidate_definition": None,
        "experimental_cloud_eligible": False,
        "experimental_cloud_ineligibility_reason": reason,
    }


def resolve(repo_root, changed_paths, pull_request_number, head_sha):
    candidate_paths = sorted(
        path
        for path in set(changed_paths)
        if pathlib.PurePosixPath(path).match("experiment/pdt/candidates/*.json")
    )
    if len(candidate_paths) > 1:
        return regular_pull_request_identity(
            pull_request_number,
            head_sha,
            "multiple-candidate-definitions",
        )
    if candidate_paths:
        candidate_id = validate_definition(repo_root, candidate_paths[0])
        return {
            "candidate_id": candidate_id,
            "candidate_definition": candidate_paths[0],
            "experimental_cloud_eligible": True,
            "experimental_cloud_ineligibility_reason": None,
        }
    return regular_pull_request_identity(
        pull_request_number,
        head_sha,
        "no-candidate-definition",
    )


def changed_paths(repo_root, base_ref, head_ref):
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "diff",
            "--diff-filter=AM",
            "--name-only",
            f"{base_ref}..{head_ref}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.splitlines()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=pathlib.Path, required=True)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--head-ref", required=True)
    parser.add_argument("--pull-request-number", required=True)
    args = parser.parse_args()
    try:
        result = resolve(
            args.repo_root.resolve(),
            changed_paths(args.repo_root, args.base_ref, args.head_ref),
            args.pull_request_number,
            args.head_ref,
        )
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"pull request candidate resolution failed: {error}") from error
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
