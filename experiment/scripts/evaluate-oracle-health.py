#!/usr/bin/env python3

import argparse
import datetime
import json
import os
import pathlib
import re
import sys


IDENTIFIER = re.compile(r"^[A-Za-z0-9._-]+$")


def load(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def checkout_deployment(deployments):
    matches = [
        item
        for item in deployments.get("items", [])
        if item.get("metadata", {}).get("name") == "checkoutservice"
    ]
    if len(matches) != 1:
        raise ValueError("deployment snapshot must contain exactly one checkoutservice")
    return matches[0]


def checkout_restarts(pods):
    total = 0
    for pod in pods.get("items", []):
        if pod.get("metadata", {}).get("labels", {}).get("app") != "checkoutservice":
            continue
        for status in pod.get("status", {}).get("containerStatuses", []) or []:
            value = status.get("restartCount", 0)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError("pod snapshot contains an invalid restart count")
            total += value
    return total


def evaluate(candidate_id, alternative_id, repetition, pods_start, pods_end, deployments_end):
    if not IDENTIFIER.fullmatch(candidate_id) or not IDENTIFIER.fullmatch(alternative_id):
        raise ValueError("candidate and alternative IDs must be safe identifiers")
    if repetition <= 0:
        raise ValueError("repetition must be positive")

    checkout = checkout_deployment(deployments_end)
    desired = checkout.get("spec", {}).get("replicas", 1)
    available = checkout.get("status", {}).get("availableReplicas", 0)
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value < 0
        for value in (desired, available)
    ):
        raise ValueError("checkout deployment has invalid replica counts")

    # A Deployment intentionally scaled to zero has met its Kubernetes desired
    # state, but the checkout capability is unavailable. The oracle measures
    # service capacity, not rollout convergence.
    unavailable = 1 if desired == 0 else max(0, desired - available)
    restart_increase = max(0, checkout_restarts(pods_end) - checkout_restarts(pods_start))

    return {
        "schema_version": "1.0.0",
        "candidate_id": candidate_id,
        "alternative_id": alternative_id,
        "repetition": repetition,
        "execution_valid": True,
        "invalid_reason": None,
        "checkoutservice_unavailable": unavailable,
        "checkoutservice_restart_increase": restart_increase,
    }


def write_json_exclusive(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
    except Exception:
        path.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--alternative-id", required=True)
    parser.add_argument("--repetition", type=int, required=True)
    parser.add_argument("--pods-start", type=pathlib.Path, required=True)
    parser.add_argument("--pods-end", type=pathlib.Path, required=True)
    parser.add_argument("--deployments-end", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        result = evaluate(
            args.candidate_id,
            args.alternative_id,
            args.repetition,
            load(args.pods_start),
            load(args.pods_end),
            load(args.deployments_end),
        )
        result["generated_at"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat().replace("+00:00", "Z")
        write_json_exclusive(args.output, result)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(f"oracle health evaluation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(args.output)


if __name__ == "__main__":
    main()
