import copy
import csv
import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "validate-baseline-evidence.py"
SPEC = importlib.util.spec_from_file_location("validate_baseline_evidence", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def single_stats(value):
    return {
        "min": value,
        "mean": value,
        "max": value,
        "standard_deviation": 0.0,
    }


class ValidateBaselineEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.baseline_dir = self.root / "experiment/evidence/baseline"
        self.checkout_dir = self.root / "experiment/evidence/checkout-baseline"
        self.run_id = "baseline-20260920T000000Z"
        self.run_dir = self.baseline_dir / self.run_id
        self.run_dir.mkdir(parents=True)
        self.create_operational_fixture()
        self.create_checkout_fixture()

    def create_operational_fixture(self):
        deployment = {
            "items": [
                {
                    "metadata": {"name": "checkoutservice"},
                    "spec": {"replicas": 1},
                    "status": {"availableReplicas": 1},
                }
            ]
        }
        artifacts = {
            "raw_http_samples": "http-samples.csv",
            "workload_configuration": "workload-configuration.json",
            "pod_metrics_start": "pod-metrics-start.tsv",
            "pod_metrics_end": "pod-metrics-end.tsv",
            "deployments_start": "deployments-start.json",
            "deployments_end": "deployments-end.json",
            "pods_start": "pods-start.json",
            "pods_end": "pods-end.json",
            "services": "services.json",
            "quotas": "resourcequotas.json",
            "events_start": "events-start.json",
            "events_end": "events-end.json",
        }
        write_csv(
            self.run_dir / "http-samples.csv",
            [
                "sequence",
                "timestamp_utc",
                "http_status",
                "latency_seconds",
                "latency_ms",
                "success",
            ],
            [
                {
                    "sequence": 1,
                    "timestamp_utc": "2026-09-20T00:00:01Z",
                    "http_status": 200,
                    "latency_seconds": "0.100",
                    "latency_ms": "100.000",
                    "success": "true",
                },
                {
                    "sequence": 2,
                    "timestamp_utc": "2026-09-20T00:00:02Z",
                    "http_status": 200,
                    "latency_seconds": "0.200",
                    "latency_ms": "200.000",
                    "success": "true",
                },
            ],
        )
        write_json(self.run_dir / "workload-configuration.json", [{"name": "checkoutservice"}])
        write_json(self.run_dir / "deployments-start.json", deployment)
        write_json(self.run_dir / "deployments-end.json", deployment)
        for name in (
            "pods-start.json",
            "pods-end.json",
            "services.json",
            "resourcequotas.json",
            "events-start.json",
            "events-end.json",
        ):
            write_json(self.run_dir / name, {"items": []})
        for name in ("pod-metrics-start.tsv", "pod-metrics-end.tsv"):
            (self.run_dir / name).write_text("checkoutservice 1m 1Mi\n", encoding="utf-8")
        write_json(
            self.run_dir / "status.json",
            {
                "run_id": self.run_id,
                "state": "completed",
                "updated_at": "2026-09-20T00:00:05Z",
            },
        )
        write_json(
            self.run_dir / "metadata.json",
            {
                "run_id": self.run_id,
                "captured_at": "2026-09-20T00:00:04Z",
                "project_id": "test-project",
                "cluster_context": "test-cluster",
                "namespace": "operational",
                "git": {"commit": "a" * 40, "branch": "main"},
                "tools": {"kubectl": "v1", "terraform": "v1"},
            },
        )
        write_json(
            self.run_dir / "summary.json",
            {
                "schema_version": "1.0.0",
                "run_id": self.run_id,
                "environment": "operational",
                "namespace": "operational",
                "measurement": {
                    "started_at": "2026-09-20T00:00:00Z",
                    "ended_at": "2026-09-20T00:00:03Z",
                    "warmup_seconds": 0,
                    "probe": {
                        "url": "http://example.test/",
                        "samples": 2,
                        "successes": 2,
                        "failures": 0,
                        "success_rate": 1.0,
                        "latency_ms": {
                            "min": 100.0,
                            "mean": 150.0,
                            "p50": 100.0,
                            "p95": 200.0,
                            "p99": 200.0,
                            "max": 200.0,
                        },
                    },
                    "locust": {"requests_during_window": 10, "failures_during_window": 0},
                },
                "artifacts": artifacts,
            },
        )
        write_json(
            self.baseline_dir / "aggregate-summary.json",
            {
                "schema_version": "1.0.0",
                "generated_at": "2026-09-20T00:00:06Z",
                "completed_runs": 1,
                "run_ids": [self.run_id],
                "probe": {
                    "total_samples": 2,
                    "total_successes": 2,
                    "total_failures": 0,
                    "success_rate": 1.0,
                    "latency_ms_across_runs": {
                        "mean": single_stats(150.0),
                        "p50": single_stats(100.0),
                        "p95": single_stats(200.0),
                        "p99": single_stats(200.0),
                        "max": single_stats(200.0),
                    },
                },
                "locust": {
                    "total_requests_during_windows": 10,
                    "total_failures_during_windows": 0,
                },
            },
        )

    def create_checkout_fixture(self):
        batch_id = "checkout-baseline-20260920T010000Z"
        batch_dir = self.checkout_dir / batch_id
        repetition_dir = batch_dir / "repetition-1"
        write_csv(
            repetition_dir / "checkout-tests.csv",
            [
                "sequence",
                "timestamp_utc",
                "http_status",
                "latency_ms",
                "confirmation_marker",
                "success",
            ],
            [
                {
                    "sequence": 1,
                    "timestamp_utc": "2026-09-20T01:00:01Z",
                    "http_status": 200,
                    "latency_ms": "100.000",
                    "confirmation_marker": "true",
                    "success": "true",
                },
                {
                    "sequence": 2,
                    "timestamp_utc": "2026-09-20T01:00:02Z",
                    "http_status": 200,
                    "latency_ms": "200.000",
                    "confirmation_marker": "true",
                    "success": "true",
                },
            ],
        )
        write_json(
            repetition_dir / "summary.json",
            {
                "repetition": 1,
                "tests": 2,
                "successes": 2,
                "failures": 0,
                "latency_ms": {"p50": 100.0, "p95": 200.0, "p99": 200.0},
            },
        )
        aggregate = {
            "schema_version": "1.0.0",
            "generated_at": "2026-09-20T01:00:03Z",
            "repetitions": 1,
            "total_tests": 2,
            "total_successes": 2,
            "total_failures": 0,
            "latency_ms": {
                "p50": single_stats(100.0),
                "p95": single_stats(200.0),
                "p99": single_stats(200.0),
            },
        }
        write_json(batch_dir / "aggregate-summary.json", aggregate)
        write_json(
            batch_dir / "status.json",
            {
                "batch_id": batch_id,
                "state": "completed",
                "updated_at": "2026-09-20T01:00:04Z",
            },
        )
        write_json(self.checkout_dir / "aggregate-summary.json", copy.deepcopy(aggregate))

    def test_valid_raw_evidence_matches_both_tracked_aggregates(self):
        result = MODULE.validate(self.root, minimum_repetitions=1)
        self.assertTrue(result["all_valid"])
        self.assertEqual(2, result["operational"]["total_samples"])
        self.assertEqual(2, result["checkout"]["total_tests"])
        self.assertTrue(result["exit_criteria"]["raw_samples_match_aggregates"])

    def test_tampered_operational_sample_is_rejected(self):
        path = self.run_dir / "http-samples.csv"
        path.write_text(path.read_text(encoding="utf-8").replace("200.000", "900.000"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "raw latency"):
            MODULE.validate(self.root, minimum_repetitions=1)

    def test_missing_resource_artifact_is_rejected(self):
        (self.run_dir / "pod-metrics-end.tsv").unlink()
        with self.assertRaisesRegex(ValueError, "missing or empty"):
            MODULE.validate(self.root, minimum_repetitions=1)

    def test_tampered_checkout_aggregate_is_rejected(self):
        path = self.checkout_dir / "aggregate-summary.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["total_successes"] = 1
        write_json(path, value)
        with self.assertRaisesRegex(ValueError, "exactly one completed raw batch"):
            MODULE.validate(self.root, minimum_repetitions=1)


if __name__ == "__main__":
    unittest.main()
