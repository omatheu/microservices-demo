import importlib.util
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "evaluate-oracle-health.py"
SPEC = importlib.util.spec_from_file_location("evaluate_oracle_health", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def deployments(desired=1, available=1):
    return {
        "items": [
            {
                "metadata": {"name": "checkoutservice"},
                "spec": {"replicas": desired},
                "status": {"availableReplicas": available},
            }
        ]
    }


def pods(restarts=0, app="checkoutservice"):
    return {
        "items": [
            {
                "metadata": {"labels": {"app": app}},
                "status": {"containerStatuses": [{"restartCount": restarts}]},
            }
        ]
    }


class EvaluateOracleHealthTests(unittest.TestCase):
    def test_healthy_checkout_has_no_health_violation(self):
        result = MODULE.evaluate("cand-test", "deploy-as-is", 1, pods(), pods(), deployments())

        self.assertTrue(result["execution_valid"])
        self.assertEqual(result["checkoutservice_unavailable"], 0)
        self.assertEqual(result["checkoutservice_restart_increase"], 0)

    def test_zero_replicas_is_service_unavailability(self):
        result = MODULE.evaluate(
            "cand-test", "deploy-as-is", 1, {"items": []}, {"items": []},
            deployments(desired=0, available=0),
        )

        self.assertEqual(result["checkoutservice_unavailable"], 1)

    def test_missing_capacity_and_restart_delta_are_reported(self):
        result = MODULE.evaluate(
            "cand-test", "capacity-safe", 2, pods(1), pods(4),
            deployments(desired=2, available=1),
        )

        self.assertEqual(result["checkoutservice_unavailable"], 1)
        self.assertEqual(result["checkoutservice_restart_increase"], 3)

    def test_missing_checkout_deployment_is_invalid_input(self):
        with self.assertRaisesRegex(ValueError, "exactly one checkoutservice"):
            MODULE.evaluate(
                "cand-test", "deploy-as-is", 1, pods(), pods(), {"items": []}
            )


if __name__ == "__main__":
    unittest.main()
