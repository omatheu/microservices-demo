import copy
import importlib.util
import json
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment/scripts/aggregate-pdt-fidelity.py"
POLICY_PATH = REPO_ROOT / "experiment/pdt/fidelity-policy.json"
SPEC = importlib.util.spec_from_file_location("aggregate_pdt_fidelity", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


CANDIDATE_ID = "cand-abcdefghijklmnop"
PROTOCOL_SHA256 = "e" * 64
POLICY_SHA256 = "f" * 64
CANDIDATE_SHA256 = "d" * 64


def protocol():
    return {
        "protocol_id": "checkout-pdt-comparison-v1",
        "status": "pre-registration-candidate",
        "frozen_at": None,
        "confirmatory_collection_allowed": False,
        "research_design": {
            "technical_repetitions_per_candidate": 3,
            "unit_of_analysis": "candidate after aggregation of technical repetitions",
        },
    }


def policy():
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def candidate():
    return {
        "candidate_id": CANDIDATE_ID,
        "confirmatory_eligibility": False,
        "alternatives": [
            {"id": "deploy-as-is", "action": "deploy"},
            {"id": "capacity-safe", "action": "deploy"},
            {"id": "block", "action": "block"},
        ],
    }


def metric(identifier, unit, predicted, observed):
    signed = predicted - observed
    absolute = abs(signed)
    relative = absolute / abs(observed) if observed != 0 else None
    return {
        "id": identifier,
        "unit": unit,
        "predicted": predicted,
        "observed": observed,
        "signed_error": signed,
        "absolute_error": absolute,
        "relative_error": relative,
        "relative_error_defined": relative is not None,
    }


def report(alternative_id, repetition, agreement=True):
    return {
        "schema_version": "1.0.0",
        "mechanism": "pdt-post-decision-fidelity",
        "policy_id": "checkout-pdt-fidelity-v1",
        "policy_status": "pre-registration-candidate",
        "candidate_id": CANDIDATE_ID,
        "alternative_id": alternative_id,
        "repetition": repetition,
        "twin_object": "checkoutservice",
        "execution_mode": "engineering",
        "confirmatory_eligible": False,
        "prediction": {
            "label": "safe",
            "confidence": 0.8,
            "snapshot_id": f"snapshot-{repetition}",
        },
        "sealed_input_bindings": {
            "candidate_definition_sha256": CANDIDATE_SHA256,
            "conventional_decision_sha256": "9" * 64,
            "immutable_artifacts": [
                {
                    "component": "checkoutservice",
                    "remote_reference": "registry/checkoutservice@sha256:" + "8" * 64,
                }
            ],
        },
        "observation": {
            "label": "safe" if agreement else "harmful",
            "violations": [] if agreement else ["performance:baseline:latency-p95"],
            "profile_id": "baseline",
        },
        "classification_agreement": agreement,
        "metrics": [
            metric("checkout_success_rate", "ratio", 0.9, 1.0),
            metric(
                "checkout_latency_p95_ms",
                "milliseconds",
                700 + repetition * 10,
                1000,
            ),
            metric("checkout_latency_p99_ms", "milliseconds", 900, 1100),
            metric("checkoutservice_unavailable", "deployments", 0, 0),
            metric("checkoutservice_restart_increase", "restarts", 0, 0),
        ],
        "aggregate": {
            "metric_count": 5,
            "relative_error_defined_count": 3,
            "mean_absolute_relative_error": 0.1,
        },
        "controls": {
            "post_decision_only": True,
            "oracle_intended_label_used": False,
            "model_mutation_performed": False,
            "recalibration_allowed": False,
            "confirmatory_reports_are_evaluation_only": True,
        },
        "input_sha256": {
            "fidelity_policy": POLICY_SHA256,
            "oracle_policy": "a" * 64,
            "pdt_decision": "b" * 64,
            "oracle_observation": "c" * 64,
        },
    }


def reports():
    return [
        report(alternative_id, repetition, agreement=not (
            alternative_id == "deploy-as-is" and repetition == 3
        ))
        for alternative_id in ("deploy-as-is", "capacity-safe")
        for repetition in (1, 2, 3)
    ]


class AggregatePdtFidelityTests(unittest.TestCase):
    def aggregate(self, values=None):
        return MODULE.aggregate(
            protocol(),
            PROTOCOL_SHA256,
            policy(),
            POLICY_SHA256,
            candidate(),
            CANDIDATE_SHA256,
            reports() if values is None else values,
            allow_draft=True,
        )

    def test_aggregates_complete_candidate_matrix(self):
        result = self.aggregate()

        self.assertEqual("candidate", result["unit_of_analysis"])
        self.assertTrue(result["coverage"]["complete"])
        self.assertEqual(6, result["coverage"]["expected_reports"])
        self.assertEqual(5, result["classification"]["agreements"])
        self.assertEqual(5 / 6, result["classification"]["agreement_rate"])
        self.assertEqual(
            6,
            result["metrics"]["checkout_latency_p95_ms"]["absolute_error"]["count"],
        )
        self.assertEqual(
            6,
            result["metrics"]["checkoutservice_unavailable"][
                "undefined_relative_error_count"
            ],
        )
        self.assertFalse(result["controls"]["recalibration_allowed"])

    def test_missing_or_duplicate_report_is_rejected(self):
        values = reports()
        with self.assertRaisesRegex(ValueError, "complete candidate matrix"):
            self.aggregate(values[:-1])

        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.aggregate(values + [copy.deepcopy(values[0])])

    def test_tampered_error_arithmetic_is_rejected(self):
        values = reports()
        values[0]["metrics"][1]["absolute_error"] = 1

        with self.assertRaisesRegex(ValueError, "error arithmetic"):
            self.aggregate(values)

    def test_policy_hash_and_metric_inventory_are_bound(self):
        values = reports()
        values[0]["input_sha256"]["fidelity_policy"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "input bindings"):
            self.aggregate(values)

        values = reports()
        values[0]["metrics"][0]["unit"] = "percent"
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.aggregate(values)

    def test_candidate_definition_and_artifact_set_are_bound(self):
        values = reports()
        values[0]["sealed_input_bindings"]["candidate_definition_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "candidate or artifact bindings"):
            self.aggregate(values)

        values = reports()
        values[0]["sealed_input_bindings"]["immutable_artifacts"] = []
        with self.assertRaisesRegex(ValueError, "immutable artifact set"):
            self.aggregate(values)

    def test_mixed_execution_modes_and_draft_eligibility_are_rejected(self):
        values = reports()
        values[0]["execution_mode"] = "confirmatory"
        with self.assertRaisesRegex(ValueError, "mix execution modes"):
            self.aggregate(values)

        values = reports()
        values[0]["confirmatory_eligible"] = True
        with self.assertRaisesRegex(ValueError, "claims confirmatory eligibility"):
            self.aggregate(values)

    def test_confirmatory_matrix_requires_every_frozen_binding(self):
        proto = protocol()
        proto.update(
            {
                "status": "frozen",
                "frozen_at": "2026-09-21T00:00:00Z",
                "confirmatory_collection_allowed": True,
            }
        )
        fidelity = policy()
        fidelity["status"] = "frozen"
        fidelity["frozen_at"] = "2026-09-21T00:00:00Z"
        definition = candidate()
        definition["confirmatory_eligibility"] = True
        values = reports()
        for item in values:
            item["policy_status"] = "frozen"
            item["execution_mode"] = "confirmatory"
            item["confirmatory_eligible"] = True

        result = MODULE.aggregate(
            proto,
            PROTOCOL_SHA256,
            fidelity,
            POLICY_SHA256,
            definition,
            CANDIDATE_SHA256,
            values,
        )

        self.assertTrue(result["confirmatory_eligible"])
        self.assertEqual("confirmatory", result["execution_mode"])

    def test_frozen_design_rejects_one_ineligible_report(self):
        proto = protocol()
        proto.update(
            {
                "status": "frozen",
                "frozen_at": "2026-09-21T00:00:00Z",
                "confirmatory_collection_allowed": True,
            }
        )
        fidelity = policy()
        fidelity["status"] = "frozen"
        fidelity["frozen_at"] = "2026-09-21T00:00:00Z"
        definition = candidate()
        definition["confirmatory_eligibility"] = True
        values = reports()
        for item in values:
            item["policy_status"] = "frozen"
            item["execution_mode"] = "confirmatory"
            item["confirmatory_eligible"] = True
        values[-1]["confirmatory_eligible"] = False

        with self.assertRaisesRegex(ValueError, "ineligible evidence"):
            MODULE.aggregate(
                proto,
                PROTOCOL_SHA256,
                fidelity,
                POLICY_SHA256,
                definition,
                CANDIDATE_SHA256,
                values,
            )


if __name__ == "__main__":
    unittest.main()
