import importlib.util
import hashlib
import json
import pathlib
import subprocess
import tempfile
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

    def test_github_environment_review_selects_the_protected_approval(self):
        history = [
            {
                "state": "approved",
                "comment": "cost window approved",
                "environments": [{"name": "tcc-experiment"}],
                "user": {"login": "cost-reviewer"},
            },
            {
                "state": "approved",
                "comment": "PDT action reviewed",
                "environments": [{"name": "tcc-deployment-approval"}],
                "user": {"login": "researcher"},
            },
        ]
        reviewer, evidence = MODULE.github_environment_review(
            history,
            "tcc-deployment-approval",
            "owner/repository",
            "1234",
            "c" * 64,
        )

        self.assertEqual("researcher", reviewer)
        self.assertEqual("PDT action reviewed", evidence["comment"])
        result = MODULE.record(
            gate(),
            action(),
            "approve-isolated-validation",
            reviewer,
            "2026-09-21T00:00:00Z",
            GATE_SHA,
            ACTION_SHA,
            evidence,
        )
        self.assertEqual(
            "github-environment-protection",
            result["human_review_evidence"]["source"],
        )
        self.assertEqual(
            "c" * 64, result["bindings"]["github_approval_history_sha256"]
        )

    def test_github_review_rejects_an_unapproved_environment(self):
        with self.assertRaisesRegex(ValueError, "no approved review"):
            MODULE.github_environment_review(
                [
                    {
                        "state": "approved",
                        "environments": [{"name": "different-environment"}],
                        "user": {"login": "researcher"},
                    }
                ],
                "tcc-deployment-approval",
                "owner/repository",
                "1234",
                "c" * 64,
            )

    def test_cli_derives_actor_from_github_review_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            gate_path = root / "gate.json"
            action_path = root / "action.json"
            history_path = root / "approvals.json"
            output_path = root / "receipt.json"
            gate_path.write_text(json.dumps(gate()), encoding="utf-8")
            gate_sha = hashlib.sha256(gate_path.read_bytes()).hexdigest()
            action_value = action()
            action_value["bindings"]["deployment_gate_sha256"] = gate_sha
            action_path.write_text(json.dumps(action_value), encoding="utf-8")
            history_path.write_text(
                json.dumps(
                    [
                        {
                            "state": "approved",
                            "comment": "reviewed in GitHub",
                            "environments": [
                                {"name": "tcc-deployment-approval"}
                            ],
                            "user": {"login": "omatheu"},
                        }
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    str(SCRIPT),
                    "--deployment-gate",
                    str(gate_path),
                    "--deployment-action",
                    str(action_path),
                    "--decision",
                    "approve-isolated-validation",
                    "--github-approval-history",
                    str(history_path),
                    "--github-environment",
                    "tcc-deployment-approval",
                    "--github-repository",
                    "omatheu/microservices-demo",
                    "--github-workflow-run-id",
                    "1234",
                    "--output",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            receipt = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("omatheu", receipt["actor"])
            self.assertEqual(
                "tcc-deployment-approval",
                receipt["human_review_evidence"]["environment"],
            )
            self.assertFalse(receipt["cloud_execution_authorized"])


if __name__ == "__main__":
    unittest.main()
