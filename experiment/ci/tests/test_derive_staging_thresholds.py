import importlib.util
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "derive-staging-thresholds.py"
SPEC = importlib.util.spec_from_file_location("derive_staging_thresholds", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def decision(repetition, p95, p99, checkout_p95, checkout_p99):
    return {
        "run_id": f"run-{repetition}",
        "candidate_id": "safe",
        "mode": "engineering",
        "repetition": repetition,
        "observed": {
            "success_rate": 1.0,
            "latency_ms": {"p95": p95, "p99": p99},
            "checkout": {
                "failures": 0,
                "latency_p95_ms": checkout_p95,
                "latency_p99_ms": checkout_p99,
                "negative_paths": {"failures": 0},
            },
        },
    }


class DeriveStagingThresholdTests(unittest.TestCase):
    def setUp(self):
        self.plan = {
            "safe_candidate_id": "safe",
            "required_repetitions": 3,
            "included_repetitions": [1, 2, 3],
            "performance_rule": {
                "safety_margin_fraction": 0.25,
                "round_up_increment_ms": 50,
            },
            "eligibility": {
                "required_mode": "engineering",
                "required_http_success_rate": 1.0,
                "required_checkout_failures": 0,
                "required_negative_path_failures": 0,
            },
        }
        self.base = {"thresholds": {"maximum_functional_failures": 0}}

    def test_predeclared_margin_and_rounding(self):
        decisions = [
            (decision(1, 700, 1000, 600, 700), "one", "a"),
            (decision(2, 790, 1190, 755, 755), "two", "b"),
            (decision(3, 720, 1100, 650, 720), "three", "c"),
        ]

        result = MODULE.derive(self.plan, self.base, decisions)

        self.assertEqual(result["thresholds"]["maximum_latency_p95_ms"], 1000)
        self.assertEqual(result["thresholds"]["maximum_latency_p99_ms"], 1500)
        self.assertEqual(result["thresholds"]["maximum_checkout_latency_p95_ms"], 950)
        self.assertEqual(result["thresholds"]["maximum_checkout_latency_p99_ms"], 950)

    def test_missing_repetition_is_blocked(self):
        decisions = [
            (decision(1, 1, 1, 1, 1), "one", "a"),
            (decision(2, 1, 1, 1, 1), "two", "b"),
        ]

        with self.assertRaisesRegex(ValueError, "expected 3"):
            MODULE.derive(self.plan, self.base, decisions)

    def test_functional_failure_is_not_absorbed_into_calibration(self):
        unsafe = decision(3, 1, 1, 1, 1)
        unsafe["observed"]["checkout"]["negative_paths"]["failures"] = 1
        decisions = [
            (decision(1, 1, 1, 1, 1), "one", "a"),
            (decision(2, 1, 1, 1, 1), "two", "b"),
            (unsafe, "three", "c"),
        ]

        with self.assertRaisesRegex(ValueError, "negative-path failures"):
            MODULE.derive(self.plan, self.base, decisions)


if __name__ == "__main__":
    unittest.main()
