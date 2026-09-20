#!/usr/bin/env python3

import argparse
import hashlib
import json
import pathlib
import re


DIGEST_PATTERN = re.compile(r"^[a-f0-9]{64}$")
IMAGE_PATTERN = re.compile(r"^[^\s@:]+(?:/[^\s@:]+)+@sha256:[a-f0-9]{64}$")


def load(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(repo_root, manifest, require_frozen=False):
    if manifest.get("status") not in {"pre-registration-candidate", "frozen"}:
        raise ValueError("oracle suite status is invalid")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise ValueError("oracle suite file inventory is empty")
    paths = [entry.get("path") for entry in entries if isinstance(entry, dict)]
    if len(paths) != len(entries) or len(paths) != len(set(paths)):
        raise ValueError("oracle suite file paths are invalid or duplicated")
    for entry in entries:
        relative = pathlib.PurePosixPath(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"oracle suite path is unsafe: {entry['path']}")
        expected = entry.get("sha256")
        if not isinstance(expected, str) or not DIGEST_PATTERN.fullmatch(expected):
            raise ValueError(f"oracle suite digest is invalid: {entry['path']}")
        actual = sha256_file(pathlib.Path(repo_root) / relative)
        if actual != expected:
            raise ValueError(f"oracle suite hash differs: {entry['path']}")

    images = manifest.get("images", {})
    required_images = {"oracle_harness", "currency_reference"}
    if set(images) != required_images:
        raise ValueError("oracle suite image set is invalid")
    images_ready = all(
        isinstance(value, str) and IMAGE_PATTERN.fullmatch(value)
        for value in images.values()
    )
    if manifest["status"] == "frozen" and not images_ready:
        raise ValueError("frozen oracle suite requires immutable image digests")
    if require_frozen and manifest["status"] != "frozen":
        raise ValueError("oracle suite is not frozen")
    return {
        "suite_id": manifest.get("suite_id"),
        "status": manifest["status"],
        "file_count": len(entries),
        "images_ready": images_ready,
        "frozen": manifest["status"] == "frozen" and images_ready,
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
        raise SystemExit(f"oracle suite validation failed: {error}") from error
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
