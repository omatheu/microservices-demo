import copy
import importlib.util
import json
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "compose-oracle-observation.py"
POLICY_PATH = REPO_ROOT / "experiment" / "oracle" / "policy-v1.json"
SPEC = importlib.util.spec_from_file_location("compose_oracle_observation", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


CANDIDATE_ID = "cand-abcdefghijklmnop"
ALTERNATIVE_ID = "deploy-as-is"


def policy():
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def functional(bound=True):
    value = policy()
    return {
        "policy_id": value["policy_id"],
        "valid": True,
        "invalid_reasons": [],
        "evidence_binding_verified": bound,
        "candidate_id": CANDIDATE_ID,
        "alternative_id": ALTERNATIVE_ID,
        "repetition": 1,
        "functional_assertions": [
            {"id": assertion, "passed": True}
            for assertion in value["functional_assertions"]
        ],
    }


def profiles(mode="confirmatory"):
    return [
        {
            "candidate_id": CANDIDATE_ID,
            "alternative_id": ALTERNATIVE_ID,
            "repetition": 1,
            "id": item["id"],
            "mode": mode,
            "confirmatory_eligible": mode == "confirmatory",
            "success_rate": 1.0,
            "latency_p95_ms": 500,
            "latency_p99_ms": 700,
            "checkout_latency_p95_ms": 500,
            "checkout_latency_p99_ms": 700,
            "order_side_effect_excess": 0,
        }
        for item in policy()["performance_profiles"]
        if item["required"]
    ]


def health(valid=True):
    return {
        "candidate_id": CANDIDATE_ID,
        "alternative_id": ALTERNATIVE_ID,
        "repetition": 1,
        "execution_valid": valid,
        "invalid_reason": None if valid else "cluster-control-plane-error",
        "checkoutservice_unavailable": 0,
        "checkoutservice_restart_increase": 0,
    }


class ComposeOracleObservationTests(unittest.TestCase):
    def test_confirmatory_inputs_compose_adjudicator_observation(self):
        result = MODULE.compose(
            policy(), CANDIDATE_ID, ALTERNATIVE_ID, 1, "confirmatory",
            functional(), profiles(), health(),
        )

        self.assertTrue(result["execution_valid"])
        self.assertEqual(result["health"]["order_side_effect_duplicates"], 0)
        self.assertEqual(
            {item["id"] for item in result["performance_profiles"]},
            {"baseline", "peak", "dependency-tail"},
        )

    def test_confirmatory_mode_rejects_unbound_functional_evidence(self):
        with self.assertRaisesRegex(ValueError, "not manifest-bound"):
            MODULE.compose(
                policy(), CANDIDATE_ID, ALTERNATIVE_ID, 1, "confirmatory",
                functional(bound=False), profiles(), health(),
            )

    def test_missing_profile_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "required profile set"):
            MODULE.compose(
                policy(), CANDIDATE_ID, ALTERNATIVE_ID, 1, "engineering",
                functional(bound=False), profiles(mode="engineering")[:-1], health(),
            )

    def test_infrastructure_failure_produces_invalid_repetition(self):
        result = MODULE.compose(
            policy(), CANDIDATE_ID, ALTERNATIVE_ID, 1, "engineering",
            functional(bound=False), profiles(mode="engineering"), health(valid=False),
        )

        self.assertFalse(result["execution_valid"])
        self.assertIn("cluster-control-plane-error", result["invalid_reason"])

    def test_inputs_are_not_mutated(self):
        functional_input = functional()
        profile_input = profiles()
        health_input = health()
        before = copy.deepcopy((functional_input, profile_input, health_input))

        MODULE.compose(
            policy(), CANDIDATE_ID, ALTERNATIVE_ID, 1, "confirmatory",
            functional_input, profile_input, health_input,
        )

        self.assertEqual((functional_input, profile_input, health_input), before)


if __name__ == "__main__":
    unittest.main()
