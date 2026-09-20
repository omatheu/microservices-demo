#!/usr/bin/env python3

"""Derive latency thresholds from predeclared safe staging calibration runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import sys
from typing import Any


def load_json(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rounded_limit(value: float, margin: float, increment: int) -> int:
    if value < 0 or margin < 0 or increment <= 0:
        raise ValueError("invalid threshold derivation parameters")
    return int(math.ceil((value * (1 + margin)) / increment) * increment)


def derive(
    plan: dict[str, Any],
    base: dict[str, Any],
    decisions: list[tuple[dict[str, Any], str, str]],
) -> dict[str, Any]:
    required = plan["required_repetitions"]
    if len(decisions) != required:
        raise ValueError(f"expected {required} calibration decisions, got {len(decisions)}")
    expected_candidate = plan["safe_candidate_id"]
    expected_repetitions = set(plan["included_repetitions"])
    actual_repetitions: set[int] = set()

    metrics = {
        "latency_p95_ms": [],
        "latency_p99_ms": [],
        "checkout_latency_p95_ms": [],
        "checkout_latency_p99_ms": [],
    }
    evidence = []
    for decision, path, digest in decisions:
        if decision.get("candidate_id") != expected_candidate:
            raise ValueError("calibration decision candidate mismatch")
        if decision.get("mode") != plan["eligibility"]["required_mode"]:
            raise ValueError("calibration decision mode mismatch")
        repetition = decision.get("repetition")
        if not isinstance(repetition, int) or repetition in actual_repetitions:
            raise ValueError("calibration repetitions must be unique integers")
        actual_repetitions.add(repetition)
        observed = decision.get("observed", {})
        checkout = observed.get("checkout", {})
        negative = checkout.get("negative_paths")
        if observed.get("success_rate") != plan["eligibility"]["required_http_success_rate"]:
            raise ValueError("safe calibration run has HTTP failures")
        if checkout.get("failures") != plan["eligibility"]["required_checkout_failures"]:
            raise ValueError("safe calibration run has checkout failures")
        if negative is not None and negative.get("failures") != plan["eligibility"]["required_negative_path_failures"]:
            raise ValueError("safe calibration run has negative-path failures")

        metrics["latency_p95_ms"].append(float(observed["latency_ms"]["p95"]))
        metrics["latency_p99_ms"].append(float(observed["latency_ms"]["p99"]))
        metrics["checkout_latency_p95_ms"].append(float(checkout["latency_p95_ms"]))
        metrics["checkout_latency_p99_ms"].append(float(checkout["latency_p99_ms"]))
        evidence.append(
            {
                "run_id": decision.get("run_id"),
                "repetition": repetition,
                "path": path,
                "sha256": digest,
            }
        )

    if actual_repetitions != expected_repetitions:
        raise ValueError(
            f"calibration repetitions differ: expected={sorted(expected_repetitions)} "
            f"actual={sorted(actual_repetitions)}"
        )

    margin = float(plan["performance_rule"]["safety_margin_fraction"])
    increment = int(plan["performance_rule"]["round_up_increment_ms"])
    thresholds = dict(base["thresholds"])
    thresholds.update(
        {
            "maximum_latency_p95_ms": rounded_limit(max(metrics["latency_p95_ms"]), margin, increment),
            "maximum_latency_p99_ms": rounded_limit(max(metrics["latency_p99_ms"]), margin, increment),
            "maximum_checkout_latency_p95_ms": rounded_limit(
                max(metrics["checkout_latency_p95_ms"]), margin, increment
            ),
            "maximum_checkout_latency_p99_ms": rounded_limit(
                max(metrics["checkout_latency_p99_ms"]), margin, increment
            ),
        }
    )
    result = dict(base)
    result.pop("frozen_at", None)
    result["status"] = "engineering-calibrated"
    result["method"] = "predeclared-safe-staging-calibration"
    result["thresholds"] = thresholds
    result["calibration"] = {
        "candidate_id": expected_candidate,
        "rule": plan["performance_rule"],
        "observed_maxima_ms": {name: max(values) for name, values in metrics.items()},
        "evidence": sorted(evidence, key=lambda item: item["repetition"]),
        "confirmatory_eligible": False,
    }
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=pathlib.Path, required=True)
    parser.add_argument("--base-thresholds", type=pathlib.Path, required=True)
    parser.add_argument("--decision", type=pathlib.Path, action="append", required=True)
    parser.add_argument("--output", type=pathlib.Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        decisions = [
            (load_json(path), str(path), sha256_file(path)) for path in args.decision
        ]
        result = derive(load_json(args.plan), load_json(args.base_thresholds), decisions)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"threshold derivation failed: {error}", file=sys.stderr)
        return 1
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
