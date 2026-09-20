#!/usr/bin/env python3

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


IDENTIFIER = re.compile(r"^[A-Za-z0-9._-]+$")


def load(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def build_cases(policy, candidate_id, alternative_id, repetition):
    matrix = policy["input_matrix"]
    cases = []
    sequence = 0
    for currency in matrix["currencies"]:
        for item_count in matrix["cart_item_counts"]:
            for quantity in matrix["quantities"]:
                sequence += 1
                cases.append(
                    {
                        "case_id": f"success-{sequence:03d}",
                        "request": {
                            "user_id": (
                                f"oracle-{candidate_id}-{alternative_id}-r{repetition}-s{sequence:03d}"
                            ),
                            "currency": currency,
                            "items": [
                                {"product_id": f"sku-{index + 1}", "quantity": quantity}
                                for index in range(item_count)
                            ],
                            "card_case": "valid",
                            "expected_case": "success",
                        },
                    }
                )

    for card_case in matrix["negative_cards"]:
        cases.append(
            {
                "case_id": card_case,
                "request": {
                    "user_id": f"oracle-{candidate_id}-{alternative_id}-r{repetition}-{card_case}",
                    "currency": "USD",
                    "items": [{"product_id": "sku-1", "quantity": 1}],
                    "card_case": card_case,
                    "expected_case": card_case,
                },
            }
        )
    for dependency in ("payment", "shipping"):
        cases.append(
            {
                "case_id": f"{dependency}-failure",
                "request": {
                    "user_id": (
                        f"oracle-{candidate_id}-{alternative_id}-r{repetition}-{dependency}-failure"
                    ),
                    "currency": "USD",
                    "items": [{"product_id": "sku-1", "quantity": 1}],
                    "card_case": "valid",
                    "fault": f"{dependency}-unavailable",
                    "expected_case": f"{dependency}-failure",
                },
            }
        )
    return cases


def sha256_file(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_exclusive(path, value, mode=0o644):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
    except Exception:
        path.unlink(missing_ok=True)
        raise


def invoke(endpoint, request_value):
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/exercise",
        data=json.dumps(request_value).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=70) as response:
        if response.status != 200:
            raise ValueError(f"oracle harness returned HTTP {response.status}")
        return json.loads(response.read())


def validate_endpoint(endpoint):
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("oracle harness endpoint must be a localhost HTTP port-forward")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("oracle harness endpoint must not contain a path, query or fragment")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=pathlib.Path, required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--alternative-id", required=True)
    parser.add_argument("--repetition", type=int, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--output-directory", type=pathlib.Path, required=True)
    args = parser.parse_args()

    try:
        for value in (args.candidate_id, args.alternative_id):
            if not IDENTIFIER.fullmatch(value):
                raise ValueError("candidate and alternative IDs contain invalid characters")
        if args.repetition <= 0:
            raise ValueError("repetition must be positive")
        validate_endpoint(args.endpoint)
        policy = load(args.policy)
        cases = build_cases(
            policy, args.candidate_id, args.alternative_id, args.repetition
        )
        args.output_directory.mkdir(parents=True, exist_ok=False)
        evidence = []
        for case in cases:
            output_path = args.output_directory / f"{case['case_id']}.json"
            result = invoke(args.endpoint, case["request"])
            write_json_exclusive(output_path, result)
            evidence.append(
                {
                    "case_id": case["case_id"],
                    "path": output_path.name,
                    "sha256": sha256_file(output_path),
                }
            )
        manifest = {
            "schema_version": "1.0.0",
            "policy_id": policy["policy_id"],
            "candidate_id": args.candidate_id,
            "alternative_id": args.alternative_id,
            "repetition": args.repetition,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace(
                "+00:00", "Z"
            ),
            "case_count": len(evidence),
            "cases": evidence,
        }
        write_json_exclusive(args.output_directory / "manifest.json", manifest)
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
        urllib.error.URLError,
    ) as error:
        print(f"oracle functional suite failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(args.output_directory)


if __name__ == "__main__":
    main()
