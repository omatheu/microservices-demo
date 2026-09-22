import copy
import importlib.util
import json
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment/scripts/calculate-pdt-fidelity.py"
FIDELITY_POLICY_PATH = REPO_ROOT / "experiment/pdt/fidelity-policy.json"
ORACLE_POLICY_PATH = REPO_ROOT / "experiment/oracle/policy-v1.json"
SPEC = importlib.util.spec_from_file_location("calculate_pdt_fidelity", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


CANDIDATE_ID = "cand-abcdefghijklmnop"
ALTERNATIVE_ID = "deploy-as-is"


def fidelity_policy():
    return json.loads(FIDELITY_POLICY_PATH.read_text(encoding="utf-8"))


def oracle_policy():
    return json.loads(ORACLE_POLICY_PATH.read_text(encoding="utf-8"))


def pdt_decision():
    return {
        "candidate": CANDIDATE_ID,
        "repetition": 1,
        "execution_mode": "engineering",
        "snapshot_id": "snapshot-test",
        "operational_mutation_performed": False,
        "artifact_binding": {
            "conventional_decision_sha256": "a" * 64,
            "candidate_definition_sha256": "b" * 64,
            "immutable_artifacts": [],
        },
        "alternatives_evaluated": [
            {
                "id": ALTERNATIVE_ID,
                "action": "deploy",
                "safe": True,
                "confidence": 0.8,
                "predicted_metrics": {
                    "checkout": {
                        "tests": 10,
                        "successes": 9,
                        "latency_p95_ms": 800,
                        "latency_p99_ms": 900,
                        "unavailable": 0,
                        "restart_increase": 0,
                    }
                },
            }
        ],
    }


def oracle_observation():
    policy = oracle_policy()
    return {
        "candidate_id": CANDIDATE_ID,
        "alternative_id": ALTERNATIVE_ID,
        "repetition": 1,
        "mode": "engineering",
        "execution_valid": True,
        "functional_assertions": [
            {"id": identifier, "passed": True}
            for identifier in policy["functional_assertions"]
        ],
        "performance_profiles": [
            {
                "id": profile["id"],
                "success_rate": 1.0,
                "latency_p95_ms": 900,
                "latency_p99_ms": 1300,
                "checkout_latency_p95_ms": 1000,
                "checkout_latency_p99_ms": 1100,
            }
            for profile in policy["performance_profiles"]
            if profile["required"]
        ],
        "health": {
            "checkoutservice_unavailable": 0,
            "checkoutservice_restart_increase": 0,
            "order_side_effect_duplicates": 0,
        },
    }


class CalculatePdtFidelityTests(unittest.TestCase):
    def calculate(self):
        return MODULE.calculate(
            fidelity_policy(), oracle_policy(), pdt_decision(), oracle_observation()
        )

    def test_compares_prediction_and_observation_per_metric(self):
        result = self.calculate()
        by_id = {item["id"]: item for item in result["metrics"]}

        self.assertAlmostEqual(
            0.1, by_id["checkout_success_rate"]["absolute_error"]
        )
        self.assertEqual(
            -200, by_id["checkout_latency_p95_ms"]["signed_error"]
        )
        self.assertEqual(
            200, by_id["checkout_latency_p95_ms"]["absolute_error"]
        )
        self.assertEqual(
            0.2, by_id["checkout_latency_p95_ms"]["relative_error"]
        )
        self.assertIsNone(
            by_id["checkoutservice_unavailable"]["relative_error"]
        )
        self.assertTrue(result["classification_agreement"])
        self.assertFalse(result["controls"]["recalibration_allowed"])
        self.assertFalse(result["confirmatory_eligible"])
        self.assertEqual(
            "b" * 64,
            result["sealed_input_bindings"]["candidate_definition_sha256"],
        )

    def test_oracle_intended_label_does_not_change_fidelity(self):
        first = oracle_observation()
        first["intended_label"] = "harmful"
        second = copy.deepcopy(first)
        second["intended_label"] = "safe"

        result_one = MODULE.calculate(
            fidelity_policy(), oracle_policy(), pdt_decision(), first
        )
        result_two = MODULE.calculate(
            fidelity_policy(), oracle_policy(), pdt_decision(), second
        )

        self.assertEqual(result_one, result_two)

    def test_candidate_repetition_and_mode_must_match(self):
        for field, value, message in (
            ("candidate_id", "cand-other", "candidate identities"),
            ("repetition", 2, "repetitions"),
            ("mode", "confirmatory", "execution modes"),
        ):
            observation = oracle_observation()
            observation[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                MODULE.calculate(
                    fidelity_policy(), oracle_policy(), pdt_decision(), observation
                )

    def test_invalid_oracle_execution_cannot_measure_fidelity(self):
        observation = oracle_observation()
        observation["execution_valid"] = False
        observation["invalid_reason"] = "cluster-control-plane-error"

        with self.assertRaisesRegex(ValueError, "infrastructure-invalid"):
            MODULE.calculate(
                fidelity_policy(), oracle_policy(), pdt_decision(), observation
            )

    def test_unsealed_or_unobserved_prediction_is_rejected(self):
        decision = pdt_decision()
        decision["artifact_binding"]["conventional_decision_sha256"] = "bad"
        with self.assertRaisesRegex(ValueError, "sealed inputs"):
            MODULE.calculate(
                fidelity_policy(), oracle_policy(), decision, oracle_observation()
            )

        decision = pdt_decision()
        decision["alternatives_evaluated"][0]["id"] = "capacity-safe"
        with self.assertRaisesRegex(ValueError, "not evaluated"):
            MODULE.calculate(
                fidelity_policy(), oracle_policy(), decision, oracle_observation()
            )

    def test_policy_cannot_enable_confirmatory_recalibration(self):
        policy = fidelity_policy()
        policy["controls"]["confirmatory_corpus_recalibration_allowed"] = True

        with self.assertRaisesRegex(ValueError, "anti-leakage"):
            MODULE.calculate(
                policy, oracle_policy(), pdt_decision(), oracle_observation()
            )

    def test_confirmatory_eligibility_requires_both_frozen_policies(self):
        policy = fidelity_policy()
        policy["status"] = "frozen"
        policy["frozen_at"] = "2026-09-21T00:00:00Z"
        oracle = oracle_policy()
        oracle["status"] = "frozen"
        oracle["frozen_at"] = "2026-09-21T00:00:00Z"
        decision = pdt_decision()
        decision["execution_mode"] = "confirmatory"
        observation = oracle_observation()
        observation["mode"] = "confirmatory"

        result = MODULE.calculate(policy, oracle, decision, observation)

        self.assertTrue(result["confirmatory_eligible"])
        self.assertFalse(result["controls"]["recalibration_allowed"])

    def test_confirmatory_mode_fails_closed_with_draft_policy(self):
        decision = pdt_decision()
        decision["execution_mode"] = "confirmatory"
        observation = oracle_observation()
        observation["mode"] = "confirmatory"

        with self.assertRaisesRegex(ValueError, "both policies frozen"):
            MODULE.calculate(
                fidelity_policy(), oracle_policy(), decision, observation
            )


if __name__ == "__main__":
    unittest.main()
