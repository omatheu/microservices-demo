#!/usr/bin/env python3

import argparse
import concurrent.futures
import csv
import datetime
import json
import math
import os
import pathlib
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


IDENTIFIER = re.compile(r"^[A-Za-z0-9._-]+$")


def load(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def validate_endpoint(endpoint):
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("oracle harness endpoint must be a localhost HTTP port-forward")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("oracle harness endpoint must not contain a path, query or fragment")


def post_json(url, value, timeout=70):
    request = urllib.request.Request(
        url,
        data=json.dumps(value).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise ValueError(f"oracle harness returned HTTP {response.status}")
        return json.loads(response.read())


def get_json(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        if response.status != 200:
            raise ValueError(f"oracle harness returned HTTP {response.status}")
        return json.loads(response.read())


def percentile(values, probability):
    if not values:
        raise ValueError("cannot calculate a percentile without values")
    ordered = sorted(values)
    rank = max(1, math.ceil(probability * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def phases_for(profile, engineering_duration=None):
    configured = profile.get("fault_phases", [])
    if configured:
        phases = [dict(item) for item in configured]
        if sum(item["duration_seconds"] for item in phases) != profile["duration_seconds"]:
            raise ValueError("fault phase durations differ from profile duration")
    else:
        phases = [
            {
                "fault": "",
                "delay_ms": 0,
                "duration_seconds": profile["duration_seconds"],
            }
        ]
    if engineering_duration is not None:
        if engineering_duration < len(phases):
            raise ValueError("engineering duration must allow at least one second per phase")
        base = engineering_duration // len(phases)
        remainder = engineering_duration % len(phases)
        for index, phase in enumerate(phases):
            phase["duration_seconds"] = base + (1 if index < remainder else 0)
    return phases


def execute_profile(
    endpoint,
    profile,
    candidate_id,
    alternative_id,
    repetition,
    users_override=None,
    engineering_duration=None,
):
    if profile.get("workload") != "direct-checkout-orders-v1":
        raise ValueError("unsupported oracle performance workload")
    users = users_override if users_override is not None else profile["users"]
    if users <= 0:
        raise ValueError("profile users must be positive")
    spawn_rate = profile["spawn_rate"]
    if spawn_rate <= 0:
        raise ValueError("profile spawn rate must be positive")
    think_time = profile["think_time_seconds"]
    phases = phases_for(profile, engineering_duration)
    samples = []
    samples_lock = threading.Lock()
    sequence_lock = threading.Lock()
    sequence = 0

    def worker(worker_id, deadline, phase_id):
        nonlocal sequence
        while time.monotonic() < deadline:
            with sequence_lock:
                sequence += 1
                request_sequence = sequence
            request_value = {
                "user_id": (
                    f"load-{candidate_id}-{alternative_id}-r{repetition}-"
                    f"p{phase_id}-w{worker_id}-n{request_sequence}"
                ),
                "currency": "USD",
                "items": [
                    {"product_id": "sku-1", "quantity": 1},
                    {"product_id": "sku-2", "quantity": 1},
                ],
                "timeout_ms": 30_000,
            }
            started_at = datetime.datetime.now(datetime.timezone.utc)
            started = time.monotonic()
            try:
                output = post_json(
                    endpoint.rstrip("/") + "/load-order", request_value, timeout=35
                )
                transport_success = True
                grpc_code = output.get("grpc_code")
                latency_ms = float(output.get("latency_ms"))
                error = output.get("error")
            except (OSError, ValueError, TypeError, urllib.error.URLError) as call_error:
                transport_success = False
                grpc_code = "TRANSPORT_ERROR"
                latency_ms = (time.monotonic() - started) * 1000
                error = str(call_error)
            sample = {
                "sequence": request_sequence,
                "phase": phase_id,
                "worker": worker_id,
                "started_at": started_at.isoformat().replace("+00:00", "Z"),
                "latency_ms": latency_ms,
                "grpc_code": grpc_code,
                "success": transport_success and grpc_code == "OK",
                "error": error,
            }
            with samples_lock:
                samples.append(sample)
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(think_time, remaining))

    reset = True
    phase_summaries = []
    for phase_index, phase in enumerate(phases, start=1):
        post_json(
            endpoint.rstrip("/") + "/load-config",
            {
                "fault": phase["fault"],
                "delay_ms": phase["delay_ms"],
                "reset_counters": reset,
            },
            timeout=10,
        )
        reset = False
        phase_started = time.monotonic()
        deadline = phase_started + phase["duration_seconds"]
        futures = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=users) as executor:
            for worker_id in range(1, users + 1):
                if time.monotonic() >= deadline:
                    break
                futures.append(executor.submit(worker, worker_id, deadline, phase_index))
                if worker_id < users:
                    time.sleep(min(1 / spawn_rate, max(0, deadline - time.monotonic())))
            for future in futures:
                future.result()
        phase_samples = [item for item in samples if item["phase"] == phase_index]
        phase_summaries.append(
            {
                "id": phase_index,
                "fault": phase["fault"],
                "delay_ms": phase["delay_ms"],
                "duration_seconds": phase["duration_seconds"],
                "sample_count": len(phase_samples),
            }
        )

    post_json(
        endpoint.rstrip("/") + "/load-config",
        {"fault": "", "delay_ms": 0, "reset_counters": False},
        timeout=10,
    )
    counter_state = get_json(endpoint.rstrip("/") + "/load-config")["counters"]
    if not samples:
        raise ValueError("performance profile produced no samples")
    latencies = [item["latency_ms"] for item in samples]
    successes = sum(1 for item in samples if item["success"])
    success_rate = successes / len(samples)
    side_effect_excess = max(
        0, int(counter_state["charge_successes"]) - int(counter_state["load_successes"])
    )
    return {
        "schema_version": "1.0.0",
        "candidate_id": candidate_id,
        "alternative_id": alternative_id,
        "repetition": repetition,
        "id": profile["id"],
        "success_rate": success_rate,
        "latency_p95_ms": percentile(latencies, 0.95),
        "latency_p99_ms": percentile(latencies, 0.99),
        "checkout_latency_p95_ms": percentile(latencies, 0.95),
        "checkout_latency_p99_ms": percentile(latencies, 0.99),
        "sample_count": len(samples),
        "successes": successes,
        "failures": len(samples) - successes,
        "users": users,
        "spawn_rate": spawn_rate,
        "think_time_seconds": think_time,
        "phases": phase_summaries,
        "counters": counter_state,
        "order_side_effect_excess": side_effect_excess,
        "samples": sorted(samples, key=lambda item: item["sequence"]),
    }


def write_outputs(output, samples_output, value):
    output = pathlib.Path(output)
    samples_output = pathlib.Path(samples_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    samples_output.parent.mkdir(parents=True, exist_ok=True)
    output_descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(output_descriptor, "w", encoding="utf-8") as stream:
            summary = dict(value)
            summary.pop("samples")
            json.dump(summary, stream, indent=2)
            stream.write("\n")
        samples_descriptor = os.open(
            samples_output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644
        )
        try:
            with os.fdopen(samples_descriptor, "w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=(
                        "sequence",
                        "phase",
                        "worker",
                        "started_at",
                        "latency_ms",
                        "grpc_code",
                        "success",
                        "error",
                    ),
                )
                writer.writeheader()
                writer.writerows(value["samples"])
        except Exception:
            samples_output.unlink(missing_ok=True)
            raise
    except Exception:
        output.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=pathlib.Path, required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--alternative-id", required=True)
    parser.add_argument("--repetition", type=int, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--mode", choices=("engineering", "confirmatory"), required=True)
    parser.add_argument("--engineering-duration-seconds", type=int)
    parser.add_argument("--engineering-users", type=int)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--samples-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        for value in (args.candidate_id, args.alternative_id, args.profile_id):
            if not IDENTIFIER.fullmatch(value):
                raise ValueError("candidate, alternative and profile IDs must be safe identifiers")
        if args.repetition <= 0:
            raise ValueError("repetition must be positive")
        validate_endpoint(args.endpoint)
        if args.mode == "confirmatory" and (
            args.engineering_duration_seconds is not None
            or args.engineering_users is not None
        ):
            raise ValueError("confirmatory profiles do not accept engineering overrides")
        policy = load(args.policy)
        matches = [
            item for item in policy["performance_profiles"] if item["id"] == args.profile_id
        ]
        if len(matches) != 1 or matches[0].get("required") is not True:
            raise ValueError("profile must identify exactly one required policy profile")
        if matches[0]["users"] > policy["execution_limits"]["maximum_users"]:
            raise ValueError("profile exceeds oracle maximum users")
        result = execute_profile(
            args.endpoint,
            matches[0],
            args.candidate_id,
            args.alternative_id,
            args.repetition,
            users_override=args.engineering_users,
            engineering_duration=args.engineering_duration_seconds,
        )
        result["mode"] = args.mode
        result["confirmatory_eligible"] = args.mode == "confirmatory"
        result["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
        write_outputs(args.output, args.samples_output, result)
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
        urllib.error.URLError,
    ) as error:
        print(f"oracle performance profile failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(args.output)


if __name__ == "__main__":
    main()
