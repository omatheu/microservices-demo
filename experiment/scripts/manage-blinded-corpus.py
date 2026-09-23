#!/usr/bin/env python3

import argparse
import base64
import datetime
import hashlib
import hmac
import json
import os
import random
import re
import secrets
import stat
import sys
from collections import Counter
from pathlib import Path


FORBIDDEN_PUBLIC_KEYS = {
    "context_dependency",
    "expected_label",
    "intended_label",
    "mutation",
    "operator",
    "operator_id",
    "parameters",
    "stratum",
    "target_component",
}
CANDIDATE_ID_PATTERN = re.compile(r"^cand-[a-z2-7]{16}$")


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def write_json_exclusive(path, value, mode):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
    except Exception:
        path.unlink(missing_ok=True)
        raise


def validate_protocol(protocol):
    if protocol.get("schema_version") != "1.0.0":
        raise ValueError("unsupported protocol schema version")
    if protocol.get("status") not in {"pre-registration-candidate", "frozen"}:
        raise ValueError("protocol status must be pre-registration-candidate or frozen")
    if protocol.get("status") == "frozen" and not protocol.get("frozen_at"):
        raise ValueError("a frozen protocol must record frozen_at")

    design = protocol.get("research_design", {})
    candidate_count = design.get("candidate_count")
    repetitions = design.get("technical_repetitions_per_candidate")
    block_size = design.get("block_size")
    block_count = design.get("block_count")
    if not all(isinstance(value, int) and value > 0 for value in (candidate_count, repetitions, block_size, block_count)):
        raise ValueError("candidate, repetition and block counts must be positive integers")
    if candidate_count != block_size * block_count:
        raise ValueError("candidate_count must equal block_size times block_count")

    operators = protocol.get("operators")
    if not isinstance(operators, list) or not operators:
        raise ValueError("protocol must define mutation operators")
    operator_ids = [operator.get("id") for operator in operators]
    if any(not isinstance(operator_id, str) or not operator_id for operator_id in operator_ids):
        raise ValueError("each operator must have an ID")
    if len(operator_ids) != len(set(operator_ids)):
        raise ValueError("operator IDs must be unique")
    if sum(operator.get("count", 0) for operator in operators) != candidate_count:
        raise ValueError("operator counts must equal candidate_count")
    for operator in operators:
        if not isinstance(operator.get("count"), int) or operator["count"] <= 0:
            raise ValueError(f"operator {operator['id']} must have a positive count")
        if operator.get("intended_label") not in {"safe", "harmful"}:
            raise ValueError(f"operator {operator['id']} has an invalid intended label")
        parameter_space = operator.get("parameter_space")
        if not isinstance(parameter_space, dict) or not parameter_space:
            raise ValueError(f"operator {operator['id']} must have a parameter space")
        for name, choices in parameter_space.items():
            if not isinstance(name, str) or not isinstance(choices, list) or not choices:
                raise ValueError(f"operator {operator['id']} has an invalid parameter space")


def derive(key, protocol, purpose):
    context = (
        f"{protocol['protocol_id']}|{protocol['randomization']['public_seed_label']}|{purpose}"
    )
    return hmac.new(key, context.encode("utf-8"), hashlib.sha256).digest()


def keyed_random(key, protocol, purpose):
    return random.Random(int.from_bytes(derive(key, protocol, purpose), "big"))


def opaque_candidate_id(key, protocol, operator_id, instance_index):
    digest = derive(key, protocol, f"candidate-id|{operator_id}|{instance_index}")
    token = base64.b32encode(digest[:10]).decode("ascii").lower().rstrip("=")
    return f"cand-{token}"


def recursively_find_forbidden_keys(value, path="$public"):
    findings = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in FORBIDDEN_PUBLIC_KEYS:
                findings.append(f"{path}.{key}")
            findings.extend(recursively_find_forbidden_keys(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(recursively_find_forbidden_keys(child, f"{path}[{index}]"))
    return findings


def build_corpus(protocol, protocol_sha256, key, generated_at):
    validate_protocol(protocol)
    minimum_key_bytes = protocol["randomization"]["blinding_key_minimum_bytes"]
    if len(key) < minimum_key_bytes:
        raise ValueError(f"blinding key must contain at least {minimum_key_bytes} bytes")

    repetitions = protocol["research_design"]["technical_repetitions_per_candidate"]
    oracle_candidates = []
    seen_ids = set()
    for operator in protocol["operators"]:
        for instance_index in range(1, operator["count"] + 1):
            candidate_id = opaque_candidate_id(key, protocol, operator["id"], instance_index)
            if candidate_id in seen_ids:
                raise ValueError("opaque candidate ID collision")
            seen_ids.add(candidate_id)
            parameter_rng = keyed_random(
                key, protocol, f"parameters|{operator['id']}|{instance_index}"
            )
            parameters = {
                name: choices[parameter_rng.randrange(len(choices))]
                for name, choices in sorted(operator["parameter_space"].items())
            }
            oracle_candidates.append(
                {
                    "candidate_id": candidate_id,
                    "operator_id": operator["id"],
                    "operator_instance": instance_index,
                    "stratum": operator["stratum"],
                    "intended_label": operator["intended_label"],
                    "target_component": operator["target_component"],
                    "context_dependency": operator["context_dependency"],
                    "parameters": parameters,
                    "implementation_status": "not-generated",
                    "oracle_adjudication": None,
                }
            )

    ordered_candidates = list(oracle_candidates)
    keyed_random(key, protocol, "execution-order").shuffle(ordered_candidates)
    execution_order = [
        {
            "sequence": index,
            "candidate_id": candidate["candidate_id"],
            "repetitions": list(range(1, repetitions + 1)),
        }
        for index, candidate in enumerate(ordered_candidates, start=1)
    ]
    block_size = protocol["research_design"]["block_size"]
    blocks = [
        {
            "block": block_index + 1,
            "candidate_ids": [item["candidate_id"] for item in execution_order[offset : offset + block_size]],
            "cost_review_required_after_block": True,
        }
        for block_index, offset in enumerate(range(0, len(execution_order), block_size))
    ]

    commitment_salt = derive(key, protocol, "oracle-commitment-salt").hex()
    candidates_for_commitment = sorted(oracle_candidates, key=lambda item: item["candidate_id"])
    oracle_commitment = sha256_bytes(
        canonical_bytes({"salt": commitment_salt, "candidates": candidates_for_commitment})
    )
    corpus_token = base64.b32encode(derive(key, protocol, "corpus-id")[:8]).decode(
        "ascii"
    ).lower().rstrip("=")
    corpus_id = f"corpus-{corpus_token}"
    confirmatory_eligible = bool(
        protocol["status"] == "frozen" and protocol.get("confirmatory_collection_allowed") is True
    )

    public = {
        "schema_version": "1.0.0",
        "corpus_id": corpus_id,
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": protocol_sha256,
        "generated_at": generated_at,
        "confirmatory_eligible": confirmatory_eligible,
        "candidate_count": len(execution_order),
        "technical_repetitions_per_candidate": repetitions,
        "oracle_manifest_commitment_sha256": oracle_commitment,
        "execution_order": execution_order,
        "blocks": blocks,
        "mechanism_visibility": {
            "opaque_candidate_ids_only": True,
            "oracle_manifest_available": False,
            "operator_and_label_available": False,
        },
    }
    oracle = {
        "schema_version": "1.0.0",
        "corpus_id": corpus_id,
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": protocol_sha256,
        "generated_at": generated_at,
        "confirmatory_eligible": confirmatory_eligible,
        "blinding_key_sha256": sha256_bytes(key),
        "commitment_salt": commitment_salt,
        "oracle_manifest_commitment_sha256": oracle_commitment,
        "execution_order": [item["candidate_id"] for item in execution_order],
        "candidates": candidates_for_commitment,
    }
    return public, oracle


def validate_corpus(protocol, protocol_sha256, key, public, oracle):
    expected_public, expected_oracle = build_corpus(
        protocol, protocol_sha256, key, public.get("generated_at")
    )
    if public != expected_public:
        raise ValueError("public corpus differs from deterministic protocol output")
    if oracle != expected_oracle:
        raise ValueError("oracle manifest differs from deterministic protocol output")
    findings = recursively_find_forbidden_keys(public)
    if findings:
        raise ValueError("public corpus leaks oracle fields: " + ", ".join(findings))
    public_ids = [item["candidate_id"] for item in public["execution_order"]]
    if len(public_ids) != len(set(public_ids)):
        raise ValueError("public corpus contains duplicate candidate IDs")
    if any(not CANDIDATE_ID_PATTERN.fullmatch(candidate_id) for candidate_id in public_ids):
        raise ValueError("public corpus contains a malformed candidate ID")
    expected_operator_counts = Counter(
        {operator["id"]: operator["count"] for operator in protocol["operators"]}
    )
    observed_operator_counts = Counter(item["operator_id"] for item in oracle["candidates"])
    if observed_operator_counts != expected_operator_counts:
        raise ValueError("oracle manifest operator counts differ from protocol")
    return {
        "corpus_id": public["corpus_id"],
        "candidate_count": len(public_ids),
        "confirmatory_eligible": public["confirmatory_eligible"],
        "protocol_sha256": protocol_sha256,
        "oracle_manifest_commitment_sha256": public[
            "oracle_manifest_commitment_sha256"
        ],
    }


def read_key(path):
    key = Path(path).read_bytes().strip()
    if not key:
        raise ValueError("blinding key file is empty")
    return key


def ensure_private_file(path):
    mode = stat.S_IMODE(Path(path).stat().st_mode)
    if mode & 0o077:
        raise ValueError(f"private file permissions must not grant group/other access: {path}")


def keygen_command(args):
    output = Path(args.output)
    if output.exists():
        raise ValueError(f"refusing to overwrite existing key: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(secrets.token_bytes(args.bytes))
    print(json.dumps({"key_created": str(output), "bytes": args.bytes}))


def generate_command(args):
    protocol_path = Path(args.protocol)
    protocol = load_json(protocol_path)
    validate_protocol(protocol)
    if protocol["status"] != "frozen" and not args.allow_draft:
        raise ValueError("draft protocol corpus generation requires --allow-draft")
    key = read_key(args.key)
    ensure_private_file(args.key)
    generated_at = datetime.datetime.now(datetime.timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    protocol_sha256 = sha256_file(protocol_path)
    public, oracle = build_corpus(protocol, protocol_sha256, key, generated_at)
    if protocol["status"] != "frozen" and public["confirmatory_eligible"]:
        raise ValueError("a draft corpus cannot be confirmatory-eligible")
    write_json_exclusive(args.public_output, public, 0o644)
    try:
        write_json_exclusive(args.oracle_output, oracle, 0o600)
    except Exception:
        Path(args.public_output).unlink(missing_ok=True)
        raise
    summary = validate_corpus(protocol, protocol_sha256, key, public, oracle)
    summary.update(
        {
            "public_output": str(Path(args.public_output)),
            "oracle_output": str(Path(args.oracle_output)),
        }
    )
    print(json.dumps(summary, sort_keys=True))


def validate_command(args):
    protocol_path = Path(args.protocol)
    protocol = load_json(protocol_path)
    key = read_key(args.key)
    ensure_private_file(args.key)
    ensure_private_file(args.oracle)
    summary = validate_corpus(
        protocol,
        sha256_file(protocol_path),
        key,
        load_json(args.public),
        load_json(args.oracle),
    )
    print(json.dumps(summary, sort_keys=True))


def parse_args():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    keygen = subparsers.add_parser("keygen")
    keygen.add_argument("--output", required=True)
    keygen.add_argument("--bytes", type=int, default=32)
    keygen.set_defaults(handler=keygen_command)

    generate = subparsers.add_parser("generate")
    generate.add_argument("--protocol", required=True)
    generate.add_argument("--key", required=True)
    generate.add_argument("--public-output", required=True)
    generate.add_argument("--oracle-output", required=True)
    generate.add_argument("--allow-draft", action="store_true")
    generate.set_defaults(handler=generate_command)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--protocol", required=True)
    validate.add_argument("--key", required=True)
    validate.add_argument("--public", required=True)
    validate.add_argument("--oracle", required=True)
    validate.set_defaults(handler=validate_command)
    return parser.parse_args()


def main():
    args = parse_args()
    if args.command == "keygen" and args.bytes < 32:
        raise SystemExit("blinding key must contain at least 32 bytes")
    try:
        args.handler(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"corpus operation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
