import importlib.util
import json
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = (
    REPO_ROOT / "experiment" / "scripts" / "run-oracle-performance-profile.py"
)
POLICY_PATH = REPO_ROOT / "experiment" / "oracle" / "policy-v1.json"
SPEC = importlib.util.spec_from_file_location("run_oracle_performance_profile", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class RunOraclePerformanceProfileTests(unittest.TestCase):
    def test_nearest_rank_percentile(self):
        self.assertEqual(MODULE.percentile([40, 10, 30, 20], 0.50), 20)
        self.assertEqual(MODULE.percentile([40, 10, 30, 20], 0.95), 40)

    def test_dependency_tail_profile_has_two_equal_phases(self):
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        profile = next(
            item for item in policy["performance_profiles"] if item["id"] == "dependency-tail"
        )

        phases = MODULE.phases_for(profile)

        self.assertEqual(
            [item["fault"] for item in phases],
            ["payment-tail-latency", "shipping-tail-latency"],
        )
        self.assertEqual(sum(item["duration_seconds"] for item in phases), 120)

    def test_engineering_duration_is_distributed_across_phases(self):
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        profile = next(
            item for item in policy["performance_profiles"] if item["id"] == "dependency-tail"
        )

        phases = MODULE.phases_for(profile, engineering_duration=5)

        self.assertEqual([item["duration_seconds"] for item in phases], [3, 2])

    def test_non_local_endpoint_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "localhost"):
            MODULE.validate_endpoint("http://oracle.example:8080")


if __name__ == "__main__":
    unittest.main()
