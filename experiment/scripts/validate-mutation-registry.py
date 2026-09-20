#!/usr/bin/env python3

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


def load(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_materializer(path):
    spec = importlib.util.spec_from_file_location("candidate_materializer", path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise ValueError("could not load candidate materializer")
    spec.loader.exec_module(module)
    return module


def validate(repo_root, protocol, registry):
    if registry.get("protocol_id") != protocol.get("protocol_id"):
        raise ValueError("mutation registry protocol ID mismatch")
    protocol_ids = [item["id"] for item in protocol.get("operators", [])]
    registry_ids = [item["id"] for item in registry.get("operators", [])]
    if len(registry_ids) != len(set(registry_ids)):
        raise ValueError("mutation registry contains duplicate operators")
    if set(protocol_ids) != set(registry_ids):
        raise ValueError("mutation registry operator set differs from protocol")
    materializer_path = Path(repo_root) / registry["materializer"]["path"]
    actual_sha256 = sha256_file(materializer_path)
    if actual_sha256 != registry["materializer"]["sha256"]:
        raise ValueError("candidate materializer hash differs from mutation registry")
    materializer = load_materializer(materializer_path)
    implemented_registry = {
        item["id"] for item in registry["operators"] if item.get("status") == "implemented"
    }
    pending_registry = {
        item["id"] for item in registry["operators"] if item.get("status") == "pending"
    }
    if implemented_registry | pending_registry != set(registry_ids):
        raise ValueError("each mutation operator must be implemented or pending")
    if implemented_registry != set(materializer.IMPLEMENTED_OPERATORS):
        raise ValueError("implemented operator set differs from materializer")
    pending_without_reason = [
        item["id"]
        for item in registry["operators"]
        if item.get("status") == "pending" and not item.get("reason")
    ]
    if pending_without_reason:
        raise ValueError("pending mutation operators require reasons")
    return {
        "protocol_id": protocol["protocol_id"],
        "operator_count": len(registry_ids),
        "implemented_count": len(implemented_registry),
        "pending_count": len(pending_registry),
        "all_implemented": not pending_registry,
        "materializer_sha256": actual_sha256,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--require-all-implemented", action="store_true")
    args = parser.parse_args()
    try:
        summary = validate(
            args.repo_root.resolve(), load(args.protocol), load(args.registry)
        )
        if args.require_all_implemented and not summary["all_implemented"]:
            raise ValueError(
                f"{summary['pending_count']} mutation operators remain pending"
            )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"mutation registry validation failed: {error}") from error
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
