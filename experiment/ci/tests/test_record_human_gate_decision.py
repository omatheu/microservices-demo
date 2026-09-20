import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "record-human-gate-decision.py"
SPEC = importlib.util.spec_from_file_location("record_human_gate_decision", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

GATE_SHA = "a" * 64
ACTION_SHA = "b" * 64


def gate():
    return {
        "candidate_id": "opaque-001",
        "gate_state": "awaiting-human-confirmation",
        "human_confirmation": {"status": "pending"},
    }


def action():
    return {
        "candidate_id": "opaque-001",
        "status": "prepared-awaiting-human-confirmation",
        "scope": "isolated-oracle-validation",
        "selected_alternative": "capacity-safe",
        "bindings": {"deployment_gate_sha256": GATE_SHA},
        "rollback_plan": {"required": True},
        "cloud_execution_authorized": False,
        "operational_mutation_authorized": False,
    }


class RecordHumanGateDecisionTests(unittest.TestCase):
    def record(self, decision="approve-isolated-validation"):
        return MODULE.record(
            gate(), action(), decision, "researcher@example.com", "2026-09-20T23:00:00Z", GATE_SHA, ACTION_SHA
        )

    def test_approval_is_scoped_and_does_not_authorize_cloud(self):
        result = self.record()
        self.assertEqual("approved", result["status"])
        self.assertEqual("isolated-oracle-validation", result["scope"])
        self.assertFalse(result["cloud_execution_authorized"])
        self.assertFalse(result["operational_mutation_authorized"])
        self.assertEqual("request-separate-cost-and-cloud-authorization", result["next_action"])

    def test_rejection_stops_validation(self):
        result = self.record("reject")
        self.assertEqual("rejected", result["status"])
        self.assertEqual("do-not-run-isolated-validation", result["next_action"])

    def test_action_must_be_bound_to_gate(self):
        value = action()
        value["bindings"]["deployment_gate_sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "not bound"):
            MODULE.record(gate(), value, "reject", "researcher", "now", GATE_SHA, ACTION_SHA)

    def test_review_requires_rollback_plan(self):
        value = action()
        value["rollback_plan"]["required"] = False
        with self.assertRaisesRegex(ValueError, "rollback"):
            MODULE.record(gate(), value, "approve-isolated-validation", "researcher", "now", GATE_SHA, ACTION_SHA)

    def test_blank_reviewer_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "reviewer"):
            MODULE.record(gate(), action(), "reject", " ", "now", GATE_SHA, ACTION_SHA)


if __name__ == "__main__":
    unittest.main()
