import importlib.util
import pathlib
import unittest


CANDIDATE_DEFINITION_SHA256 = "e" * 64

SCRIPT = pathlib.Path(__file__).parents[2] / "scripts" / "evaluate-deployment-gate.py"
SPEC = importlib.util.spec_from_file_location("evaluate_deployment_gate", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def control_decision(decision="approve", candidate_id="opaque-001"):
    return {
        "mechanism": "conventional-ci-cd-with-staging",
        "candidate_id": candidate_id,
        "decision": decision,
        "reasons": [],
        "control_decision_sealed": True,
        "local_ci": {"decision": "pass"},
        "staging": {
            "executed": True,
            "decision": "PASS",
            "artifact_binding_verified": True,
        },
        "immutable_artifacts": [],
        "candidate_definition_sha256": CANDIDATE_DEFINITION_SHA256,
    }


def pdt_decision(decision="approve", candidate_id="opaque-001"):
    return {
        "candidate": candidate_id,
        "decision": decision,
        "snapshot_id": "snapshot-001",
        "model_id": "model-001",
        "selected_alternative": "deploy-as-is",
        "recommended_configuration": {},
        "confidence": 0.8,
        "artifact_binding": {
            "staging_binding_verified": True,
            "immutable_artifacts": [],
            "candidate_definition_sha256": CANDIDATE_DEFINITION_SHA256,
        },
    }


class EvaluateDeploymentGateTests(unittest.TestCase):
    def test_control_and_pdt_approval_waits_for_human(self):
        result = MODULE.evaluate(control_decision(), pdt_decision())
        self.assertEqual("awaiting-human-confirmation", result["gate_state"])
        self.assertTrue(result["human_confirmation"]["required"])

    def test_control_block_cannot_be_overridden_by_pdt(self):
        result = MODULE.evaluate(control_decision("block"), pdt_decision())
        self.assertEqual("blocked", result["gate_state"])
        self.assertIn("conventional-ci-cd-did-not-approve", result["reasons"])

    def test_pdt_block_stops_approved_control(self):
        result = MODULE.evaluate(control_decision(), pdt_decision("block"))
        self.assertEqual("blocked", result["gate_state"])
        self.assertIn("pdt-prescriptive-decision-is-block", result["reasons"])

    def test_reconfigure_still_requires_human(self):
        result = MODULE.evaluate(control_decision(), pdt_decision("reconfigure"))
        self.assertEqual("awaiting-human-confirmation", result["gate_state"])

    def test_candidate_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "same candidate"):
            MODULE.evaluate(control_decision(), pdt_decision(candidate_id="opaque-002"))

    def test_unsealed_control_is_rejected(self):
        control = control_decision()
        control["control_decision_sealed"] = False

        with self.assertRaisesRegex(ValueError, "must be sealed"):
            MODULE.evaluate(control, pdt_decision())

    def test_artifact_substitution_between_control_and_pdt_is_rejected(self):
        control = control_decision()
        control["immutable_artifacts"] = [{"component": "checkoutservice", "remote_reference": "image@sha256:" + "a" * 64}]

        with self.assertRaisesRegex(ValueError, "same immutable artifacts"):
            MODULE.evaluate(control, pdt_decision())

    def test_candidate_definition_substitution_is_rejected(self):
        pdt = pdt_decision()
        pdt["artifact_binding"]["candidate_definition_sha256"] = "f" * 64

        with self.assertRaisesRegex(ValueError, "same candidate definition"):
            MODULE.evaluate(control_decision(), pdt)


if __name__ == "__main__":
    unittest.main()
