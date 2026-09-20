import copy
import hashlib
import importlib.util
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "analyze-confirmatory-results.py"
SPEC = importlib.util.spec_from_file_location("analyze_confirmatory_results", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def protocol():
    return {
        "protocol_id": "test-protocol",
        "status": "pre-registration-candidate",
        "frozen_at": None,
        "confirmatory_collection_allowed": False,
        "research_design": {"candidate_count": 4},
    }


def protocol_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def candidate(identifier, actual, control, treatment):
    alternative = "deploy-as-is" if treatment == "approve" else "block"
    oracle_selected = "block" if actual == "harmful" else "deploy-as-is"
    return {
        "candidate_id": identifier,
        "exclusion": None,
        "control": {
            "decision": control,
            "selected_alternative": "deploy-as-is" if control == "approve" else "block",
            "continuous_metrics": {"duration_seconds": 10.0},
        },
        "treatment": {
            "decision": treatment,
            "selected_alternative": alternative,
            "continuous_metrics": {"duration_seconds": 12.0},
        },
        "oracle": {
            "candidate_id": identifier,
            "observed_deploy_as_is_label": actual,
            "eligible_for_primary_analysis": False,
            "selected_alternative": oracle_selected,
            "alternatives": [
                {"id": "deploy-as-is", "label": actual, "change_cost": 0},
                {"id": "capacity-safe", "label": "safe", "change_cost": 2},
            ],
        },
    }


def dataset(proto):
    return {
        "protocol_id": proto["protocol_id"],
        "protocol_sha256": protocol_hash(proto),
        "collection_complete": True,
        "candidates": [
            candidate("cand-0001", "harmful", "approve", "block"),
            candidate("cand-0002", "harmful", "approve", "approve"),
            candidate("cand-0003", "safe", "approve", "approve"),
            candidate("cand-0004", "safe", "approve", "block"),
        ],
    }


class AnalyzeConfirmatoryResultsTests(unittest.TestCase):
    def analyze(self):
        proto = protocol()
        return MODULE.analyze(proto, protocol_hash(proto), dataset(proto), allow_draft=True)

    def test_primary_candidate_level_paired_metrics(self):
        result = self.analyze()
        primary = result["primary_outcome"]
        self.assertEqual(1.0, primary["control_unsafe_approval_rate"]["rate"])
        self.assertEqual(0.5, primary["treatment_unsafe_approval_rate"]["rate"])
        self.assertEqual(-0.5, primary["paired_risk_difference_treatment_minus_control"])
        self.assertEqual(0.5, primary["absolute_risk_reduction_control_minus_treatment"])
        self.assertEqual(1, primary["discordant_pairs"]["control_only_unsafe"])
        self.assertEqual(0, primary["discordant_pairs"]["treatment_only_unsafe"])
        self.assertEqual(1.0, primary["exact_mcnemar_two_sided_p_value"])

    def test_classification_and_incremental_utility(self):
        result = self.analyze()
        self.assertEqual(0.0, result["classification"]["control"]["sensitivity"])
        self.assertEqual(1.0, result["classification"]["control"]["specificity"])
        self.assertEqual(0.5, result["classification"]["treatment"]["sensitivity"])
        self.assertEqual(0.5, result["classification"]["treatment"]["specificity"])
        self.assertEqual(1, result["incremental_utility"]["prevented_by_pdt"])
        self.assertEqual(1, result["incremental_utility"]["safe_candidates_blocked_by_pdt"])

    def test_exact_interval_handles_boundary_counts(self):
        zero = MODULE.exact_binomial_interval(0, 1)
        one = MODULE.exact_binomial_interval(1, 1)
        self.assertAlmostEqual(0.0, zero[0])
        self.assertAlmostEqual(0.975, zero[1], places=10)
        self.assertAlmostEqual(0.025, one[0], places=10)
        self.assertAlmostEqual(1.0, one[1])

    def test_draft_protocol_is_fail_closed_without_explicit_test_flag(self):
        proto = protocol()
        with self.assertRaisesRegex(ValueError, "frozen protocol"):
            MODULE.analyze(proto, protocol_hash(proto), dataset(proto))

    def test_dataset_must_bind_exact_protocol(self):
        proto = protocol()
        value = dataset(proto)
        value["protocol_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "not bound"):
            MODULE.analyze(proto, protocol_hash(proto), value, allow_draft=True)

    def test_candidate_count_and_identity_are_strict(self):
        proto = protocol()
        value = dataset(proto)
        value["candidates"].pop()
        with self.assertRaisesRegex(ValueError, "candidate count"):
            MODULE.analyze(proto, protocol_hash(proto), value, allow_draft=True)
        value = dataset(proto)
        value["candidates"][0]["candidate_id"] = "engineering-pilot"
        with self.assertRaisesRegex(ValueError, "non-opaque"):
            MODULE.analyze(proto, protocol_hash(proto), value, allow_draft=True)

    def test_inconclusive_candidate_is_reported_as_excluded(self):
        proto = protocol()
        value = dataset(proto)
        value["candidates"][0]["oracle"]["observed_deploy_as_is_label"] = "inconclusive"
        result = MODULE.analyze(proto, protocol_hash(proto), value, allow_draft=True)
        self.assertEqual(3, result["eligibility"]["analyzed_candidates"])
        self.assertEqual("oracle-inconclusive", result["eligibility"]["excluded_candidates"][0]["reason"])

    def test_input_is_not_mutated(self):
        proto = protocol()
        value = dataset(proto)
        before = copy.deepcopy(value)
        MODULE.analyze(proto, protocol_hash(proto), value, allow_draft=True)
        self.assertEqual(before, value)


if __name__ == "__main__":
    unittest.main()
