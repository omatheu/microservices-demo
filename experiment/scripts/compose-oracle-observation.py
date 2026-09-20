#!/usr/bin/env python3

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import sys


def load(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compose(policy, candidate_id, alternative_id, repetition, mode, functional, profiles, health):
    if mode not in {"engineering", "confirmatory"}:
        raise ValueError("mode must be engineering or confirmatory")
    if repetition <= 0:
        raise ValueError("repetition must be positive")
    if functional.get("policy_id") != policy.get("policy_id"):
        raise ValueError("functional report uses a different oracle policy")
    if mode == "confirmatory" and functional.get("evidence_binding_verified") is not True:
        raise ValueError("confirmatory functional evidence is not manifest-bound")
    if functional.get("evidence_binding_verified") is True:
        if (
            functional.get("candidate_id") != candidate_id
            or functional.get("alternative_id") != alternative_id
            or functional.get("repetition") != repetition
        ):
            raise ValueError("functional evidence identity mismatch")

    expected_profiles = {
        item["id"] for item in policy["performance_profiles"] if item.get("required") is True
    }
    profile_ids = [item.get("id") for item in profiles]
    if len(profile_ids) != len(set(profile_ids)) or set(profile_ids) != expected_profiles:
        raise ValueError("performance evidence does not cover the required profile set")
    for profile in profiles:
        if (
            profile.get("candidate_id") != candidate_id
            or profile.get("alternative_id") != alternative_id
            or profile.get("repetition") != repetition
        ):
            raise ValueError("performance evidence identity mismatch")
        if mode == "confirmatory" and (
            profile.get("mode") != "confirmatory"
            or profile.get("confirmatory_eligible") is not True
        ):
            raise ValueError("engineering performance evidence cannot enter a confirmatory observation")

    if (
        health.get("candidate_id") != candidate_id
        or health.get("alternative_id") != alternative_id
        or health.get("repetition") != repetition
    ):
        raise ValueError("health evidence identity mismatch")
    for metric in (
        "checkoutservice_unavailable",
        "checkoutservice_restart_increase",
    ):
        if not isinstance(health.get(metric), int) or isinstance(health.get(metric), bool):
            raise ValueError(f"health evidence has invalid {metric}")

    execution_valid = functional.get("valid") is True and health.get("execution_valid") is True
    invalid_reasons = []
    if functional.get("valid") is not True:
        invalid_reasons.extend(functional.get("invalid_reasons", ["functional-suite-invalid"]))
    if health.get("execution_valid") is not True:
        invalid_reasons.append(health.get("invalid_reason", "infrastructure-health-invalid"))

    projected_profiles = []
    side_effect_excess = 0
    for profile in sorted(profiles, key=lambda item: item["id"]):
        projected_profiles.append(
            {
                "id": profile["id"],
                "success_rate": profile["success_rate"],
                "latency_p95_ms": profile["latency_p95_ms"],
                "latency_p99_ms": profile["latency_p99_ms"],
                "checkout_latency_p95_ms": profile["checkout_latency_p95_ms"],
                "checkout_latency_p99_ms": profile["checkout_latency_p99_ms"],
            }
        )
        side_effect_excess = max(
            side_effect_excess, int(profile.get("order_side_effect_excess", 0))
        )

    return {
        "schema_version": "1.0.0",
        "candidate_id": candidate_id,
        "alternative_id": alternative_id,
        "repetition": repetition,
        "mode": mode,
        "execution_valid": execution_valid,
        "invalid_reason": ";".join(sorted(set(invalid_reasons))) if invalid_reasons else None,
        "functional_assertions": functional["functional_assertions"],
        "performance_profiles": projected_profiles,
        "health": {
            "checkoutservice_unavailable": health["checkoutservice_unavailable"],
            "checkoutservice_restart_increase": health[
                "checkoutservice_restart_increase"
            ],
            "order_side_effect_duplicates": side_effect_excess,
        },
    }


def write_json_exclusive(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
    except Exception:
        path.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=pathlib.Path, required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--alternative-id", required=True)
    parser.add_argument("--repetition", type=int, required=True)
    parser.add_argument("--mode", choices=("engineering", "confirmatory"), required=True)
    parser.add_argument("--functional-report", type=pathlib.Path, required=True)
    parser.add_argument("--performance-profile", type=pathlib.Path, action="append", required=True)
    parser.add_argument("--health", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        observation = compose(
            load(args.policy),
            args.candidate_id,
            args.alternative_id,
            args.repetition,
            args.mode,
            load(args.functional_report),
            [load(path) for path in args.performance_profile],
            load(args.health),
        )
        observation["generated_at"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat().replace("+00:00", "Z")
        observation["evidence"] = {
            "functional_report_sha256": sha256_file(args.functional_report),
            "performance_profile_sha256": {
                path.name: sha256_file(path) for path in args.performance_profile
            },
            "health_sha256": sha256_file(args.health),
            "oracle_policy_sha256": sha256_file(args.policy),
        }
        write_json_exclusive(args.output, observation)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"oracle observation composition failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(args.output)


if __name__ == "__main__":
    main()
