import copy
import importlib.util
import json
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "adjudicate-oracle.py"
POLICY_PATH = REPO_ROOT / "experiment" / "oracle" / "policy-v1.json"
SPEC = importlib.util.spec_from_file_location("adjudicate_oracle", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


CANDIDATE_ID = "cand-abcdefghijklmnop"


def policy():
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def definition():
    return {
        "candidate_id": CANDIDATE_ID,
        "alternatives": [
            {
                "id": "deploy-as-is",
                "action": "deploy",
                "configuration_changes": [],
                "change_cost": 0,
            },
            {
                "id": "restore",
                "action": "deploy",
                "configuration_changes": [],
                "change_cost": 1,
            },
            {
                "id": "block",
                "action": "block",
                "configuration_changes": [],
                "change_cost": 10,
            },
        ],
    }


def work_item(intended_label="harmful"):
    return {
        "corpus_id": "corpus-test",
        "candidate_id": CANDIDATE_ID,
        "operator_id": "INF-CPU-01",
        "intended_label": intended_label,
        "repetitions": [1, 2, 3],
    }


def observation(alternative_id, repetition):
    value = policy()
    return {
        "candidate_id": CANDIDATE_ID,
        "alternative_id": alternative_id,
        "repetition": repetition,
        "execution_valid": True,
        "functional_assertions": [
            {"id": assertion_id, "passed": True}
            for assertion_id in value["functional_assertions"]
        ],
        "performance_profiles": [
            {
                "id": profile["id"],
                "success_rate": 1.0,
                "latency_p95_ms": 500,
                "latency_p99_ms": 700,
                "checkout_latency_p95_ms": 600,
                "checkout_latency_p99_ms": 700,
            }
            for profile in value["performance_profiles"]
            if profile["required"]
        ],
        "health": {
            "checkoutservice_unavailable": 0,
            "checkoutservice_restart_increase": 0,
            "order_side_effect_duplicates": 0,
        },
    }


def observations():
    return [
        observation(alternative_id, repetition)
        for alternative_id in ("deploy-as-is", "restore")
        for repetition in (1, 2, 3)
    ]


def select(values, alternative_id, repetition):
    return next(
        item
        for item in values
        if item["alternative_id"] == alternative_id and item["repetition"] == repetition
    )


class AdjudicateOracleTests(unittest.TestCase):
    def test_safe_deploy_as_is_is_approved_without_using_intent_as_label(self):
        result = MODULE.adjudicate(policy(), definition(), work_item("harmful"), observations())

        self.assertEqual(result["observed_deploy_as_is_label"], "safe")
        self.assertEqual(result["oracle_decision"], "approve")
        self.assertFalse(result["intent_matches_observation"])
        self.assertFalse(result["eligible_for_primary_analysis"])

    def test_harmful_deploy_as_is_with_safe_alternative_is_reconfigured(self):
        values = observations()
        for repetition in (1, 2):
            baseline = select(values, "deploy-as-is", repetition)["performance_profiles"][0]
            baseline["latency_p95_ms"] = 2000

        result = MODULE.adjudicate(policy(), definition(), work_item(), values)

        self.assertEqual(result["observed_deploy_as_is_label"], "harmful")
        self.assertEqual(result["oracle_decision"], "reconfigure")
        self.assertEqual(result["selected_alternative"], "restore")

    def test_no_safe_deployable_alternative_is_blocked(self):
        values = observations()
        for alternative_id in ("deploy-as-is", "restore"):
            for repetition in (1, 2):
                assertion = select(values, alternative_id, repetition)[
                    "functional_assertions"
                ][0]
                assertion["passed"] = False

        result = MODULE.adjudicate(policy(), definition(), work_item(), values)

        self.assertEqual(result["oracle_decision"], "block")
        self.assertEqual(result["selected_alternative"], "block")

    def test_split_two_valid_repetitions_is_inconclusive(self):
        values = observations()
        select(values, "deploy-as-is", 1)["functional_assertions"][0]["passed"] = False
        invalid = select(values, "deploy-as-is", 3)
        invalid["execution_valid"] = False
        invalid["invalid_reason"] = "cluster-control-plane-error"

        result = MODULE.adjudicate(policy(), definition(), work_item(), values)

        self.assertEqual(result["observed_deploy_as_is_label"], "inconclusive")
        self.assertEqual(result["oracle_decision"], "inconclusive")

    def test_missing_required_profile_invalidates_repetition(self):
        value = observation("deploy-as-is", 1)
        value["performance_profiles"] = value["performance_profiles"][:-1]

        result = MODULE.evaluate_repetition(
            value, policy(), CANDIDATE_ID, "deploy-as-is"
        )

        self.assertFalse(result["valid"])
        self.assertIn("performance-profile-set-mismatch", result["invalid_reasons"])

    def test_observation_input_is_not_mutated(self):
        values = observations()
        before = copy.deepcopy(values)

        MODULE.adjudicate(policy(), definition(), work_item(), values)

        self.assertEqual(values, before)


if __name__ == "__main__":
    unittest.main()
