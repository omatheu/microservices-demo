import importlib.util
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "decide-pdt.py"
SPEC = importlib.util.spec_from_file_location("decide_pdt", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def thresholds():
    return {
        "minimum_success_rate": 0.99,
        "maximum_latency_p95_ms": 1200,
        "maximum_latency_p99_ms": 1550,
        "maximum_checkout_latency_p95_ms": 1150,
        "maximum_checkout_latency_p99_ms": 1150,
        "maximum_functional_failures": 0,
        "maximum_unavailable_deployments": 0,
        "maximum_restart_increase": 0,
    }


def observed():
    return {
        "samples": 120,
        "successes": 120,
        "failures": 0,
        "success_rate": 1.0,
        "latency_ms": {"p50": 300, "p95": 700, "p99": 900},
        "checkout": {
            "tests": 10,
            "successes": 10,
            "failures": 0,
            "latency_p95_ms": 800,
            "latency_p99_ms": 850,
            "negative_paths": {"tests": 2, "successes": 2, "failures": 0},
            "unavailable": 0,
            "restart_increase": 0,
        },
        "locust": {"requests": 300, "failures": 0, "success_rate": 1.0},
    }


class DecidePdtTests(unittest.TestCase):
    def test_safe_observation_has_no_violations(self):
        self.assertEqual(MODULE.safety_violations(observed(), thresholds()), [])

    def test_locust_failure_rate_blocks_candidate(self):
        result = observed()
        result["locust"]["success_rate"] = 0.98

        self.assertIn(
            "locust_success_rate_below_threshold",
            MODULE.safety_violations(result, thresholds()),
        )

    def test_negative_checkout_path_failure_blocks_candidate(self):
        result = observed()
        result["checkout"]["negative_paths"]["failures"] = 1

        self.assertIn(
            "functional_failures_above_threshold",
            MODULE.safety_violations(result, thresholds()),
        )


if __name__ == "__main__":
    unittest.main()
