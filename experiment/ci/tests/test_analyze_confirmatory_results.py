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
        "research_design": {
            "candidate_count": 4,
            "technical_repetitions_per_candidate": 3,
        },
        "aggregation": {"minimum_valid_repetitions": 2},
    }


def protocol_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def summary(value, count=6):
    return {
        "count": count,
        "mean": value,
        "median": value,
        "sample_standard_deviation": 0.0 if count > 1 else None,
        "minimum": value,
        "maximum": value,
    }


def fidelity(identifier, proto, value, agreements):
    confirmatory = (
        proto.get("status") == "frozen"
        and proto.get("confirmatory_collection_allowed") is True
        and bool(proto.get("frozen_at"))
    )
    agreement_counts = {
        "deploy-as-is": min(3, agreements),
        "capacity-safe": max(0, agreements - 3),
    }
    metrics = {}
    for metric_id, unit in MODULE.FIDELITY_METRICS.items():
        undefined = metric_id in {
            "checkoutservice_unavailable",
            "checkoutservice_restart_increase",
        }
        metrics[metric_id] = {
            "unit": unit,
            "report_count": 6,
            "signed_error": summary(value),
            "absolute_error": summary(value),
            "relative_error": None if undefined else summary(value / 10),
            "undefined_relative_error_count": 6 if undefined else 0,
        }
    return {
        "schema_version": "1.0.0",
        "mechanism": "candidate-level-pdt-fidelity",
        "protocol_id": proto["protocol_id"],
        "protocol_sha256": protocol_hash(proto),
        "policy_id": "checkout-pdt-fidelity-v1",
        "policy_sha256": "f" * 64,
        "candidate_id": identifier,
        "candidate_definition_sha256": "a" * 64,
        "immutable_artifacts": [
            {
                "component": "checkoutservice",
                "remote_reference": "image@sha256:" + "b" * 64,
            }
        ],
        "unit_of_analysis": "candidate",
        "execution_mode": "confirmatory" if confirmatory else "engineering",
        "confirmatory_eligible": confirmatory,
        "coverage": {
            "deployable_alternatives": ["capacity-safe", "deploy-as-is"],
            "repetitions": [1, 2, 3],
            "expected_reports": 6,
            "observed_reports": 6,
            "complete": True,
        },
        "classification": {
            "agreements": agreements,
            "comparisons": 6,
            "agreement_rate": agreements / 6,
            "by_alternative": {
                alternative_id: {
                    "agreements": count,
                    "comparisons": 3,
                    "agreement_rate": count / 3,
                }
                for alternative_id, count in agreement_counts.items()
            },
        },
        "metrics": metrics,
        "report_index": [
            {
                "alternative_id": alternative_id,
                "repetition": repetition,
                "classification_agreement": repetition <= agreement_counts[alternative_id],
            }
            for alternative_id in ("capacity-safe", "deploy-as-is")
            for repetition in (1, 2, 3)
        ],
        "controls": {
            "complete_matrix_required": True,
            "model_mutation_performed": False,
            "recalibration_allowed": False,
            "confirmatory_reports_are_evaluation_only": True,
        },
    }


def candidate(identifier, actual, control, treatment, proto, value, agreements):
    alternative = "deploy-as-is" if treatment == "approve" else "block"
    oracle_selected = "block" if actual == "harmful" else "deploy-as-is"
    return {
        "candidate_id": identifier,
        "repetitions": [1, 2, 3],
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
            "fidelity": (
                fidelity(identifier, proto, value, agreements)
                if control == "approve"
                else None
            ),
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
    confirmatory = (
        proto.get("status") == "frozen"
        and proto.get("confirmatory_collection_allowed") is True
        and bool(proto.get("frozen_at"))
    )
    return {
        "protocol_id": proto["protocol_id"],
        "protocol_sha256": protocol_hash(proto),
        "collection_complete": True,
        "confirmatory_eligible": confirmatory,
        "composition_mode": "confirmatory" if confirmatory else "engineering-dry-run",
        "collection_flow": {
            "declared_candidates": 4,
            "candidate_records": 4,
            "complete_decision_pairs": 4,
            "pdt_fidelity_candidates": 4,
            "pdt_fidelity_not_applicable_control_blocked": 0,
            "manifest_exclusions": [],
            "silently_missing_candidates": 0,
        },
        "candidates": [
            candidate("cand-0001", "harmful", "approve", "block", proto, 1.0, 6),
            candidate("cand-0002", "harmful", "approve", "approve", proto, 2.0, 3),
            candidate("cand-0003", "safe", "approve", "approve", proto, 3.0, 4),
            candidate("cand-0004", "safe", "approve", "block", proto, 4.0, 5),
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

    def test_prediction_fidelity_is_summarized_at_candidate_level(self):
        result = self.analyze()
        fidelity_result = result["prediction_fidelity"]
        self.assertEqual("candidate", fidelity_result["unit_of_analysis"])
        self.assertTrue(
            fidelity_result["repetitions_used_only_within_candidate_aggregates"]
        )
        self.assertEqual(4, fidelity_result["candidates_with_pdt_prediction"])
        self.assertEqual(
            4,
            fidelity_result["classification_agreement"]["candidate_rate_summary"][
                "count"
            ],
        )
        self.assertEqual(
            0.75,
            fidelity_result["classification_agreement"]["candidate_rate_summary"][
                "median"
            ],
        )
        self.assertEqual(
            0.25,
            fidelity_result["classification_agreement"][
                "perfect_candidate_agreement"
            ]["rate"],
        )
        self.assertEqual(
            2.5,
            fidelity_result["metrics"]["checkout_latency_p95_ms"][
                "candidate_median_absolute_error"
            ]["median"],
        )
        self.assertIsNone(
            fidelity_result["metrics"]["checkoutservice_unavailable"][
                "candidate_median_relative_error"
            ]
        )
        self.assertEqual(
            4,
            fidelity_result["metrics"]["checkoutservice_unavailable"][
                "candidates_with_undefined_relative_error"
            ],
        )
        self.assertEqual(
            1.0,
            result["candidate_results"][0]["pdt_fidelity"][
                "classification_agreement_rate"
            ],
        )

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
        value["candidates"][0]["oracle"]["alternatives"][0]["label"] = "inconclusive"
        value["candidates"][0]["oracle"]["alternatives"][0]["aggregate"] = {
            "reason": "insufficient-valid-repetitions",
            "valid_repetitions": 1,
            "harmful_repetitions": 1,
            "safe_repetitions": 0,
            "invalid_repetitions": 2,
        }
        result = MODULE.analyze(proto, protocol_hash(proto), value, allow_draft=True)
        self.assertEqual(3, result["eligibility"]["analyzed_candidates"])
        self.assertEqual(
            "insufficient-valid-repetitions",
            result["eligibility"]["excluded_candidates"][0]["reason_code"],
        )
        self.assertEqual(
            "oracle-adjudication",
            result["eligibility"]["excluded_candidates"][0]["source"],
        )

    def test_confirmatory_inconclusive_oracle_is_transparently_excluded(self):
        proto = protocol()
        proto["status"] = "frozen"
        proto["frozen_at"] = "2026-09-21T00:00:00Z"
        proto["confirmatory_collection_allowed"] = True
        value = dataset(proto)
        for item in value["candidates"]:
            item["oracle"]["eligible_for_primary_analysis"] = True
        oracle = value["candidates"][0]["oracle"]
        oracle["eligible_for_primary_analysis"] = False
        oracle["observed_deploy_as_is_label"] = "inconclusive"
        oracle["alternatives"][0]["label"] = "inconclusive"
        oracle["alternatives"][0]["aggregate"] = {
            "reason": "split-valid-repetitions",
            "valid_repetitions": 2,
            "harmful_repetitions": 1,
            "safe_repetitions": 1,
            "invalid_repetitions": 1,
        }

        result = MODULE.analyze(proto, protocol_hash(proto), value)

        self.assertTrue(result["confirmatory_eligible"])
        self.assertEqual(3, result["eligibility"]["analyzed_candidates"])
        self.assertEqual(
            {"oracle-adjudication": 1},
            result["eligibility"]["exclusion_counts_by_source"],
        )

    def test_valid_manifest_exclusion_is_reported_in_flow(self):
        proto = protocol()
        value = dataset(proto)
        exclusion = {
            "reason_code": "insufficient-valid-repetitions",
            "reason": "two repetitions remained infrastructure-invalid",
            "decided_before_oracle_label": True,
            "label_revealed": False,
            "valid_repetitions": [1],
            "invalid_repetitions": [2, 3],
            "replacement_attempted": True,
            "evidence": {"path": "exclusion.json", "sha256": "a" * 64},
        }
        value["candidates"][0] = {
            "candidate_id": "cand-0001",
            "repetitions": [1, 2, 3],
            "exclusion": exclusion,
        }
        value["collection_flow"]["complete_decision_pairs"] = 3
        value["collection_flow"]["pdt_fidelity_candidates"] = 3
        value["collection_flow"]["manifest_exclusions"] = [
            {"candidate_id": "cand-0001", **exclusion}
        ]

        result = MODULE.analyze(proto, protocol_hash(proto), value, allow_draft=True)

        self.assertEqual(3, result["eligibility"]["analyzed_candidates"])
        self.assertEqual(0.75, result["eligibility"]["complete_decision_pair_rate"])
        self.assertEqual(0.75, result["eligibility"]["primary_analysis_rate"])
        self.assertEqual(
            {"collection-manifest": 1},
            result["eligibility"]["exclusion_counts_by_source"],
        )

    def test_inconsistent_collection_flow_is_rejected(self):
        proto = protocol()
        value = dataset(proto)
        value["collection_flow"]["silently_missing_candidates"] = 1

        with self.assertRaisesRegex(ValueError, "collection flow"):
            MODULE.analyze(proto, protocol_hash(proto), value, allow_draft=True)

    def test_control_approval_requires_complete_candidate_fidelity(self):
        proto = protocol()
        value = dataset(proto)
        value["candidates"][0]["treatment"]["fidelity"] = None

        with self.assertRaisesRegex(ValueError, "not protocol-bound"):
            MODULE.analyze(proto, protocol_hash(proto), value, allow_draft=True)

        value = dataset(proto)
        value["candidates"][0]["treatment"]["fidelity"]["report_index"].pop()
        with self.assertRaisesRegex(ValueError, "report index is incomplete"):
            MODULE.analyze(proto, protocol_hash(proto), value, allow_draft=True)

    def test_control_blocked_candidate_cannot_claim_pdt_fidelity(self):
        proto = protocol()
        value = dataset(proto)
        value["candidates"][0]["control"]["decision"] = "block"
        value["candidates"][0]["control"]["selected_alternative"] = "block"
        value["collection_flow"]["pdt_fidelity_candidates"] = 3
        value["collection_flow"]["pdt_fidelity_not_applicable_control_blocked"] = 1

        with self.assertRaisesRegex(ValueError, "must not contain PDT fidelity"):
            MODULE.analyze(proto, protocol_hash(proto), value, allow_draft=True)

    def test_control_blocked_candidate_is_explicitly_not_applicable_to_fidelity(self):
        proto = protocol()
        value = dataset(proto)
        record = value["candidates"][0]
        record["control"]["decision"] = "block"
        record["control"]["selected_alternative"] = "block"
        record["treatment"]["decision"] = "block"
        record["treatment"]["selected_alternative"] = "block"
        record["treatment"]["fidelity"] = None
        value["collection_flow"]["pdt_fidelity_candidates"] = 3
        value["collection_flow"]["pdt_fidelity_not_applicable_control_blocked"] = 1

        result = MODULE.analyze(
            proto, protocol_hash(proto), value, allow_draft=True
        )

        self.assertEqual(3, result["prediction_fidelity"]["candidates_with_pdt_prediction"])
        self.assertEqual(
            1,
            result["prediction_fidelity"][
                "not_applicable_control_blocked_candidates"
            ],
        )
        self.assertIsNone(result["candidate_results"][0]["pdt_fidelity"])

    def test_confirmatory_fidelity_cannot_claim_engineering_mode(self):
        proto = protocol()
        proto["status"] = "frozen"
        proto["frozen_at"] = "2026-09-21T00:00:00Z"
        proto["confirmatory_collection_allowed"] = True
        value = dataset(proto)
        for item in value["candidates"]:
            item["oracle"]["eligible_for_primary_analysis"] = True
        value["candidates"][0]["treatment"]["fidelity"][
            "execution_mode"
        ] = "engineering"

        with self.assertRaisesRegex(ValueError, "not protocol-bound"):
            MODULE.analyze(proto, protocol_hash(proto), value)

    def test_dataset_cannot_claim_a_different_composition_mode(self):
        proto = protocol()
        value = dataset(proto)
        value["confirmatory_eligible"] = True

        with self.assertRaisesRegex(ValueError, "composition mode"):
            MODULE.analyze(proto, protocol_hash(proto), value, allow_draft=True)

    def test_inconclusive_repetition_accounting_is_fail_closed(self):
        proto = protocol()
        value = dataset(proto)
        oracle = value["candidates"][0]["oracle"]
        oracle["observed_deploy_as_is_label"] = "inconclusive"
        oracle["alternatives"][0]["label"] = "inconclusive"
        oracle["alternatives"][0]["aggregate"] = {
            "reason": "insufficient-valid-repetitions",
            "valid_repetitions": 2,
            "harmful_repetitions": 1,
            "safe_repetitions": 1,
            "invalid_repetitions": 1,
        }

        with self.assertRaisesRegex(ValueError, "valid reason"):
            MODULE.analyze(proto, protocol_hash(proto), value, allow_draft=True)

    def test_excluded_candidate_cannot_carry_decision_or_oracle_evidence(self):
        proto = protocol()
        value = dataset(proto)
        exclusion = {
            "reason_code": "insufficient-valid-repetitions",
            "reason": "two repetitions remained infrastructure-invalid",
            "decided_before_oracle_label": True,
            "label_revealed": False,
            "valid_repetitions": [1],
            "invalid_repetitions": [2, 3],
            "replacement_attempted": True,
            "evidence": {"path": "exclusion.json", "sha256": "a" * 64},
        }
        value["candidates"][0]["exclusion"] = exclusion
        value["collection_flow"]["complete_decision_pairs"] = 3
        value["collection_flow"]["pdt_fidelity_candidates"] = 3
        value["collection_flow"]["manifest_exclusions"] = [
            {"candidate_id": "cand-0001", **exclusion}
        ]

        with self.assertRaisesRegex(ValueError, "must not contain decision"):
            MODULE.analyze(proto, protocol_hash(proto), value, allow_draft=True)

    def test_input_is_not_mutated(self):
        proto = protocol()
        value = dataset(proto)
        before = copy.deepcopy(value)
        MODULE.analyze(proto, protocol_hash(proto), value, allow_draft=True)
        self.assertEqual(before, value)


if __name__ == "__main__":
    unittest.main()
