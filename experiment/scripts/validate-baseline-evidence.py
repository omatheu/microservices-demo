#!/usr/bin/env python3

"""Validate Phase 1 raw evidence and bind it to the tracked aggregates."""

import argparse
import csv
import datetime
import hashlib
import json
import math
import pathlib
import re
import statistics


RUN_ID = re.compile(r"^baseline-[0-9]{8}T[0-9]{6}Z$")
BATCH_ID = re.compile(r"^checkout-baseline-[0-9]{8}T[0-9]{6}Z$")
DIGEST = re.compile(r"^[0-9a-f]{40}$")
OPERATIONAL_ARTIFACTS = {
    "raw_http_samples",
    "workload_configuration",
    "pod_metrics_start",
    "pod_metrics_end",
    "deployments_start",
    "deployments_end",
    "pods_start",
    "pods_end",
    "services",
    "quotas",
    "events_start",
    "events_end",
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


def parse_timestamp(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} timestamp is missing")
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} timestamp is invalid") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{label} timestamp lacks a timezone")
    return parsed


def number(value, label, *, integer=False):
    expected = int if integer else (int, float)
    if (
        not isinstance(value, expected)
        or isinstance(value, bool)
        or value < 0
        or (not integer and not math.isfinite(value))
    ):
        raise ValueError(f"{label} must be a finite non-negative number")
    return value


def close(actual, expected, label, tolerance=1e-9):
    if not math.isclose(actual, expected, rel_tol=tolerance, abs_tol=tolerance):
        raise ValueError(f"{label} differs: {actual} != {expected}")


def nearest_rank(values, percentile):
    ordered = sorted(values)
    rank = max(1, min(len(ordered), math.ceil(percentile * len(ordered))))
    return ordered[rank - 1]


def stats(values):
    return {
        "min": min(values),
        "mean": statistics.fmean(values),
        "max": max(values),
        "standard_deviation": statistics.pstdev(values),
    }


def validate_stats(document, values, label):
    if not isinstance(document, dict) or set(document) != {
        "min",
        "mean",
        "max",
        "standard_deviation",
    }:
        raise ValueError(f"{label} aggregate has an invalid schema")
    expected = stats(values)
    for name, value in expected.items():
        number(document.get(name), f"{label}.{name}")
        close(document[name], value, f"{label}.{name}")


def require_file(directory, relative, label):
    candidate = pathlib.PurePosixPath(relative) if isinstance(relative, str) else None
    if (
        candidate is None
        or not candidate.parts
        or candidate.is_absolute()
        or ".." in candidate.parts
    ):
        raise ValueError(f"{label} has an unsafe relative path")
    path = directory / candidate
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"{label} is missing or empty")
    return path


def validate_deployments(path, label):
    document = load(path)
    items = document.get("items") if isinstance(document, dict) else None
    if not isinstance(items, list) or not items:
        raise ValueError(f"{label} contains no deployments")
    names = []
    for item in items:
        metadata = item.get("metadata", {}) if isinstance(item, dict) else {}
        spec = item.get("spec", {}) if isinstance(item, dict) else {}
        status = item.get("status", {}) if isinstance(item, dict) else {}
        name = metadata.get("name")
        desired = spec.get("replicas", 0)
        available = status.get("availableReplicas", 0)
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(desired, int)
            or isinstance(desired, bool)
            or desired < 0
            or available != desired
        ):
            raise ValueError(f"{label} contains an unavailable or invalid deployment")
        names.append(name)
    if len(names) != len(set(names)) or "checkoutservice" not in names:
        raise ValueError(f"{label} lacks a unique checkoutservice deployment")
    return sorted(names)


def validate_operational_run(baseline_dir, run_id):
    if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
        raise ValueError("operational aggregate contains an invalid run ID")
    run_dir = baseline_dir / run_id
    status_path = run_dir / "status.json"
    metadata_path = run_dir / "metadata.json"
    summary_path = run_dir / "summary.json"
    for path in (status_path, metadata_path, summary_path):
        if not path.is_file():
            raise ValueError(f"{run_id} lacks {path.name}")

    status = load(status_path)
    metadata = load(metadata_path)
    summary = load(summary_path)
    if status != {
        "run_id": run_id,
        "state": "completed",
        "updated_at": status.get("updated_at"),
    }:
        raise ValueError(f"{run_id} status is not a completed, matching run")
    status_time = parse_timestamp(status.get("updated_at"), f"{run_id} status")
    if (
        metadata.get("run_id") != run_id
        or metadata.get("namespace") != "operational"
        or not isinstance(metadata.get("project_id"), str)
        or not metadata["project_id"]
        or not isinstance(metadata.get("cluster_context"), str)
        or not metadata["cluster_context"]
        or not DIGEST.fullmatch(metadata.get("git", {}).get("commit", ""))
        or not all(metadata.get("tools", {}).get(name) for name in ("kubectl", "terraform"))
    ):
        raise ValueError(f"{run_id} metadata is incomplete or inconsistent")
    captured_at = parse_timestamp(metadata.get("captured_at"), f"{run_id} metadata")

    if (
        summary.get("schema_version") != "1.0.0"
        or summary.get("run_id") != run_id
        or summary.get("environment") != "operational"
        or summary.get("namespace") != "operational"
    ):
        raise ValueError(f"{run_id} summary identity is invalid")
    measurement = summary.get("measurement")
    if not isinstance(measurement, dict):
        raise ValueError(f"{run_id} measurement is missing")
    started_at = parse_timestamp(measurement.get("started_at"), f"{run_id} start")
    ended_at = parse_timestamp(measurement.get("ended_at"), f"{run_id} end")
    if not started_at < ended_at <= captured_at <= status_time:
        raise ValueError(f"{run_id} timestamps are not monotonic")
    number(measurement.get("warmup_seconds"), f"{run_id} warmup", integer=True)

    probe = measurement.get("probe")
    if not isinstance(probe, dict) or not isinstance(probe.get("url"), str):
        raise ValueError(f"{run_id} probe metadata is invalid")
    samples = number(probe.get("samples"), f"{run_id} samples", integer=True)
    successes = number(probe.get("successes"), f"{run_id} successes", integer=True)
    failures = number(probe.get("failures"), f"{run_id} failures", integer=True)
    if samples <= 0 or successes + failures != samples:
        raise ValueError(f"{run_id} probe counts are inconsistent")
    number(probe.get("success_rate"), f"{run_id} success rate")
    close(probe.get("success_rate"), successes / samples, f"{run_id} success rate")

    latency = probe.get("latency_ms")
    if not isinstance(latency, dict) or set(latency) != {
        "min",
        "mean",
        "p50",
        "p95",
        "p99",
        "max",
    }:
        raise ValueError(f"{run_id} latency summary has an invalid schema")
    for name, value in latency.items():
        number(value, f"{run_id} latency {name}")
    if not (
        latency["min"] <= latency["p50"] <= latency["p95"]
        <= latency["p99"] <= latency["max"]
        and latency["min"] <= latency["mean"] <= latency["max"]
    ):
        raise ValueError(f"{run_id} latency quantiles are not monotonic")

    locust = measurement.get("locust")
    if not isinstance(locust, dict):
        raise ValueError(f"{run_id} Locust counts are missing")
    locust_requests = number(
        locust.get("requests_during_window"), f"{run_id} Locust requests", integer=True
    )
    locust_failures = number(
        locust.get("failures_during_window"), f"{run_id} Locust failures", integer=True
    )
    if locust_failures > locust_requests:
        raise ValueError(f"{run_id} Locust failures exceed requests")

    artifacts = summary.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != OPERATIONAL_ARTIFACTS:
        raise ValueError(f"{run_id} artifact manifest is incomplete")
    artifact_paths = {
        name: require_file(run_dir, relative, f"{run_id} {name}")
        for name, relative in artifacts.items()
    }

    with artifact_paths["raw_http_samples"].open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    required_columns = {
        "sequence",
        "timestamp_utc",
        "http_status",
        "latency_seconds",
        "latency_ms",
        "success",
    }
    if len(rows) != samples or not rows or set(rows[0]) != required_columns:
        raise ValueError(f"{run_id} raw HTTP sample shape differs from its summary")
    raw_latencies = []
    raw_successes = 0
    for index, row in enumerate(rows, start=1):
        if int(row["sequence"]) != index or row["success"] not in {"true", "false"}:
            raise ValueError(f"{run_id} raw HTTP sequence or success value is invalid")
        parse_timestamp(row["timestamp_utc"], f"{run_id} HTTP sample")
        raw_latencies.append(float(row["latency_ms"]))
        raw_successes += row["success"] == "true"
    if raw_successes != successes:
        raise ValueError(f"{run_id} raw HTTP successes differ from the summary")
    expected_latency = {
        "min": min(raw_latencies),
        "mean": statistics.fmean(raw_latencies),
        "p50": nearest_rank(raw_latencies, 0.50),
        "p95": nearest_rank(raw_latencies, 0.95),
        "p99": nearest_rank(raw_latencies, 0.99),
        "max": max(raw_latencies),
    }
    for name, value in expected_latency.items():
        close(latency[name], value, f"{run_id} raw latency {name}", tolerance=0.001)

    deployment_start = validate_deployments(
        artifact_paths["deployments_start"], f"{run_id} deployment start"
    )
    deployment_end = validate_deployments(
        artifact_paths["deployments_end"], f"{run_id} deployment end"
    )
    if deployment_start != deployment_end:
        raise ValueError(f"{run_id} deployment set changed during the baseline")

    workload_configuration = load(artifact_paths["workload_configuration"])
    workload_names = (
        sorted(item.get("name") for item in workload_configuration)
        if isinstance(workload_configuration, list)
        and all(isinstance(item, dict) and isinstance(item.get("name"), str) for item in workload_configuration)
        else []
    )
    if workload_names != deployment_start:
        raise ValueError(f"{run_id} workload configuration differs from deployments")

    evidence_paths = {
        "status.json": status_path,
        "metadata.json": metadata_path,
        "summary.json": summary_path,
        **{artifacts[name]: path for name, path in artifact_paths.items()},
    }
    return {
        "run_id": run_id,
        "project_id": metadata["project_id"],
        "cluster_context": metadata["cluster_context"],
        "deployment_count": len(deployment_start),
        "samples": samples,
        "successes": successes,
        "failures": failures,
        "locust_requests": locust_requests,
        "locust_failures": locust_failures,
        "latency_ms": latency,
        "evidence_sha256": {
            name: sha256_file(path) for name, path in sorted(evidence_paths.items())
        },
    }


def validate_operational_baseline(baseline_dir, aggregate_path, minimum_repetitions):
    aggregate = load(aggregate_path)
    run_ids = aggregate.get("run_ids")
    if (
        aggregate.get("schema_version") != "1.0.0"
        or not isinstance(run_ids, list)
        or aggregate.get("completed_runs") != len(run_ids)
        or len(run_ids) < minimum_repetitions
        or len(run_ids) != len(set(run_ids))
    ):
        raise ValueError("operational aggregate does not declare enough unique completed runs")
    parse_timestamp(aggregate.get("generated_at"), "operational aggregate")
    runs = [validate_operational_run(baseline_dir, run_id) for run_id in run_ids]
    if len({(run["project_id"], run["cluster_context"]) for run in runs}) != 1:
        raise ValueError("operational runs do not share one project and cluster instance")

    probe = aggregate.get("probe", {})
    expected_samples = sum(run["samples"] for run in runs)
    expected_successes = sum(run["successes"] for run in runs)
    expected_failures = sum(run["failures"] for run in runs)
    if (
        probe.get("total_samples") != expected_samples
        or probe.get("total_successes") != expected_successes
        or probe.get("total_failures") != expected_failures
    ):
        raise ValueError("operational aggregate probe counts differ from raw runs")
    number(probe.get("success_rate"), "operational aggregate success rate")
    close(
        probe.get("success_rate"),
        expected_successes / expected_samples,
        "operational aggregate success rate",
    )
    latency_aggregate = probe.get("latency_ms_across_runs", {})
    for name in ("mean", "p50", "p95", "p99", "max"):
        validate_stats(
            latency_aggregate.get(name),
            [run["latency_ms"][name] for run in runs],
            f"operational aggregate latency {name}",
        )
    locust = aggregate.get("locust", {})
    if (
        locust.get("total_requests_during_windows")
        != sum(run["locust_requests"] for run in runs)
        or locust.get("total_failures_during_windows")
        != sum(run["locust_failures"] for run in runs)
    ):
        raise ValueError("operational aggregate Locust counts differ from raw runs")
    return {
        "aggregate_sha256": sha256_file(aggregate_path),
        "completed_runs": len(runs),
        "total_samples": expected_samples,
        "total_successes": expected_successes,
        "total_failures": expected_failures,
        "total_locust_requests": sum(run["locust_requests"] for run in runs),
        "total_locust_failures": sum(run["locust_failures"] for run in runs),
        "runs": runs,
    }


def comparable_aggregate(document):
    if not isinstance(document, dict):
        return None
    result = document.copy()
    result.pop("generated_at", None)
    return result


def validate_checkout_repetition(repetition_dir, repetition):
    summary_path = repetition_dir / "summary.json"
    csv_path = repetition_dir / "checkout-tests.csv"
    if not summary_path.is_file() or not csv_path.is_file():
        raise ValueError(f"checkout repetition {repetition} lacks raw evidence")
    summary = load(summary_path)
    if summary.get("repetition") != repetition:
        raise ValueError(f"checkout repetition {repetition} identity differs")
    tests = number(summary.get("tests"), f"checkout repetition {repetition} tests", integer=True)
    successes = number(
        summary.get("successes"), f"checkout repetition {repetition} successes", integer=True
    )
    failures = number(
        summary.get("failures"), f"checkout repetition {repetition} failures", integer=True
    )
    if tests <= 0 or successes + failures != tests:
        raise ValueError(f"checkout repetition {repetition} counts are inconsistent")
    with csv_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    columns = {
        "sequence",
        "timestamp_utc",
        "http_status",
        "latency_ms",
        "confirmation_marker",
        "success",
    }
    if len(rows) != tests or not rows or set(rows[0]) != columns:
        raise ValueError(f"checkout repetition {repetition} raw sample shape differs")
    raw_latencies = []
    raw_successes = 0
    for index, row in enumerate(rows, start=1):
        if (
            int(row["sequence"]) != index
            or row["confirmation_marker"] not in {"true", "false"}
            or row["success"] not in {"true", "false"}
        ):
            raise ValueError(f"checkout repetition {repetition} raw row is invalid")
        parse_timestamp(row["timestamp_utc"], f"checkout repetition {repetition}")
        raw_latencies.append(float(row["latency_ms"]))
        raw_successes += row["success"] == "true"
    if raw_successes != successes:
        raise ValueError(f"checkout repetition {repetition} success count differs")
    latency = summary.get("latency_ms")
    if not isinstance(latency, dict) or set(latency) != {"p50", "p95", "p99"}:
        raise ValueError(f"checkout repetition {repetition} latency schema is invalid")
    for name, percentile in (("p50", 0.50), ("p95", 0.95), ("p99", 0.99)):
        close(
            latency[name],
            nearest_rank(raw_latencies, percentile),
            f"checkout repetition {repetition} {name}",
            tolerance=0.001,
        )
    return {
        "repetition": repetition,
        "tests": tests,
        "successes": successes,
        "failures": failures,
        "latency_ms": latency,
        "summary_sha256": sha256_file(summary_path),
        "raw_samples_sha256": sha256_file(csv_path),
    }


def validate_checkout_baseline(checkout_dir, aggregate_path, minimum_repetitions):
    tracked = load(aggregate_path)
    if tracked.get("schema_version") != "1.0.0":
        raise ValueError("checkout aggregate schema is invalid")
    parse_timestamp(tracked.get("generated_at"), "checkout aggregate")
    matches = []
    for candidate in sorted(checkout_dir.glob("checkout-baseline-*")):
        raw_aggregate = candidate / "aggregate-summary.json"
        status_path = candidate / "status.json"
        if not candidate.is_dir() or not raw_aggregate.is_file() or not status_path.is_file():
            continue
        if comparable_aggregate(load(raw_aggregate)) == comparable_aggregate(tracked):
            matches.append((candidate, raw_aggregate, status_path))
    if len(matches) != 1:
        raise ValueError("checkout aggregate must match exactly one completed raw batch")
    batch_dir, raw_aggregate_path, status_path = matches[0]
    batch_id = batch_dir.name
    status = load(status_path)
    if (
        not BATCH_ID.fullmatch(batch_id)
        or status.get("batch_id") != batch_id
        or status.get("state") != "completed"
    ):
        raise ValueError("checkout raw batch identity or state is invalid")
    parse_timestamp(status.get("updated_at"), "checkout batch status")

    repetitions = tracked.get("repetitions")
    if (
        not isinstance(repetitions, int)
        or isinstance(repetitions, bool)
        or repetitions < minimum_repetitions
    ):
        raise ValueError("checkout aggregate declares too few repetitions")
    items = [
        validate_checkout_repetition(batch_dir / f"repetition-{index}", index)
        for index in range(1, repetitions + 1)
    ]
    expected_tests = sum(item["tests"] for item in items)
    expected_successes = sum(item["successes"] for item in items)
    expected_failures = sum(item["failures"] for item in items)
    if (
        tracked.get("total_tests") != expected_tests
        or tracked.get("total_successes") != expected_successes
        or tracked.get("total_failures") != expected_failures
    ):
        raise ValueError("checkout aggregate counts differ from raw repetitions")
    for name in ("p50", "p95", "p99"):
        validate_stats(
            tracked.get("latency_ms", {}).get(name),
            [item["latency_ms"][name] for item in items],
            f"checkout aggregate latency {name}",
        )
    return {
        "aggregate_sha256": sha256_file(aggregate_path),
        "batch_id": batch_id,
        "raw_aggregate_sha256": sha256_file(raw_aggregate_path),
        "status_sha256": sha256_file(status_path),
        "repetitions": repetitions,
        "total_tests": expected_tests,
        "total_successes": expected_successes,
        "total_failures": expected_failures,
        "repetition_evidence": items,
    }


def validate(repo_root, minimum_repetitions=3):
    repo_root = pathlib.Path(repo_root).resolve()
    baseline_dir = repo_root / "experiment/evidence/baseline"
    checkout_dir = repo_root / "experiment/evidence/checkout-baseline"
    operational = validate_operational_baseline(
        baseline_dir,
        baseline_dir / "aggregate-summary.json",
        minimum_repetitions,
    )
    checkout = validate_checkout_baseline(
        checkout_dir,
        checkout_dir / "aggregate-summary.json",
        minimum_repetitions,
    )
    return {
        "schema_version": "1.0.0",
        "all_valid": True,
        "phase": "phase-1-operational-baseline",
        "minimum_repetitions": minimum_repetitions,
        "operational": operational,
        "checkout": checkout,
        "exit_criteria": {
            "timestamped_runs": True,
            "versioned_schema": True,
            "raw_samples_match_aggregates": True,
            "resources_and_configuration_captured": True,
            "natural_variation_repeated": True,
            "functional_checkout_repeated": True,
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=pathlib.Path, required=True)
    parser.add_argument("--minimum-repetitions", type=int, default=3)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    try:
        if args.minimum_repetitions <= 0:
            raise ValueError("minimum repetitions must be positive")
        result = validate(args.repo_root, args.minimum_repetitions)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"baseline evidence validation failed: {error}") from error
    result["validated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    serialized = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(serialized)
    else:
        print(serialized, end="")


if __name__ == "__main__":
    main()
