#!/usr/bin/env python3

import argparse
import hashlib
import json
import pathlib
import re


DIGEST_PATTERN = re.compile(r"^[a-f0-9]{64}$")
REQUIRED_INPUTS = {
    "ci_policy",
    "staging_thresholds",
    "pdt_model_policy",
    "mutation_registry",
    "oracle_suite_manifest",
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


def validate(repo_root, protocol):
    inputs = protocol.get("frozen_inputs")
    if not isinstance(inputs, dict) or set(inputs) != REQUIRED_INPUTS:
        raise ValueError("protocol frozen input set is incomplete or unexpected")
    paths = []
    for name, binding in inputs.items():
        if not isinstance(binding, dict):
            raise ValueError(f"protocol input binding is invalid: {name}")
        relative = pathlib.PurePosixPath(binding.get("path", ""))
        if not relative.parts or relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"protocol input path is unsafe: {name}")
        expected = binding.get("sha256")
        if not isinstance(expected, str) or not DIGEST_PATTERN.fullmatch(expected):
            raise ValueError(f"protocol input digest is invalid: {name}")
        actual = sha256_file(pathlib.Path(repo_root) / relative)
        if actual != expected:
            raise ValueError(f"protocol input hash differs: {name}")
        paths.append(str(relative))
    if len(paths) != len(set(paths)):
        raise ValueError("protocol input paths are duplicated")
    return {
        "protocol_id": protocol.get("protocol_id"),
        "protocol_status": protocol.get("status"),
        "input_count": len(inputs),
        "all_hashes_match": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=pathlib.Path, required=True)
    parser.add_argument("--protocol", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        result = validate(args.repo_root.resolve(), load(args.protocol))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"protocol input validation failed: {error}") from error
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
