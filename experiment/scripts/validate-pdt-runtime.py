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
    if manifest["status"] == "frozen" and not image_ready:
        raise ValueError("frozen PDT runtime requires an immutable controller image digest")
    if require_frozen and (manifest["status"] != "frozen" or not image_ready):
        raise ValueError("PDT runtime is not frozen")
    return {
        "runtime_id": manifest["runtime_id"],
        "status": manifest["status"],
        "file_count": len(entries),
        "image_ready": image_ready,
        "frozen": manifest["status"] == "frozen" and image_ready,
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
