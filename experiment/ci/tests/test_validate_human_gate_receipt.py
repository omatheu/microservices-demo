import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "validate-human-gate-receipt.py"
SPEC = importlib.util.spec_from_file_location("validate_human_gate_receipt", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decision_chain(root):
    paths = {
        name: root / f"{name.replace('_', '-')}.json"
        for name in (
            "candidate_definition",
            "snapshot",
            "conventional_decision",
            "pdt_decision",
            "deployment_gate",
            "deployment_action",
            "human_gate_decision",
            "github_approval_history",
        )
    }
    candidate_sha = write_json(
        paths["candidate_definition"],
        {
            "candidate_id": "opaque-001",
            "twin_object": "checkoutservice",
            "alternatives": [
                {
                    "id": "deploy-as-is",
                    "action": "deploy",
                    "configuration_changes": [],
                }
            ],
        },
    )
    snapshot_sha = write_json(
        paths["snapshot"],
        {
            "snapshot_id": "snapshot-001",
            "binding": {
                "source_namespace": "operational",
                "twin_object": {
                    "kind": "Deployment",
                    "name": "checkoutservice",
                },
            },
        },
    )
    artifacts = [
        {
            "component": "checkoutservice",
            "remote_reference": "registry/repository/checkout@sha256:" + "a" * 64,
        }
    ]
    control_sha = write_json(
        paths["conventional_decision"],
        {
            "mechanism": "conventional-ci-cd-with-staging",
            "candidate_id": "opaque-001",
            "decision": "approve",
            "control_decision_sealed": True,
            "candidate_definition_sha256": candidate_sha,
            "immutable_artifacts": artifacts,
        },
    )
    pdt_sha = write_json(
        paths["pdt_decision"],
        {
            "candidate": "opaque-001",
            "snapshot_id": "snapshot-001",
            "decision": "approve",
            "selected_alternative": "deploy-as-is",
            "artifact_binding": {"immutable_artifacts": artifacts},
        },
    )
    gate_sha = write_json(
        paths["deployment_gate"],
        {
            "candidate_id": "opaque-001",
            "gate_state": "awaiting-human-confirmation",
            "human_confirmation": {"status": "pending"},
            "pdt": {
                "decision": "approve",
                "selected_alternative": "deploy-as-is",
            },
        },
    )
    action_sha = write_json(
        paths["deployment_action"],
        {
            "candidate_id": "opaque-001",
            "status": "prepared-awaiting-human-confirmation",
            "scope": "isolated-oracle-validation",
            "selected_alternative": "deploy-as-is",
            "target": {
                "namespace": "oracle",
                "kind": "Deployment",
                "name": "checkoutservice",
                "publicly_exposed": False,
            },
            "forward_action": {"immutable_artifacts": artifacts},
            "rollback_plan": {
                "required": True,
                "namespace": "oracle",
                "preserves_operational_namespace": True,
            },
            "bindings": {
                "candidate_definition_sha256": candidate_sha,
                "snapshot_sha256": snapshot_sha,
                "conventional_decision_sha256": control_sha,
                "pdt_decision_sha256": pdt_sha,
                "deployment_gate_sha256": gate_sha,
            },
            "cloud_execution_authorized": False,
            "operational_mutation_authorized": False,
            "operational_mutation_performed": False,
        },
    )
    approval_sha = write_json(
        paths["github_approval_history"],
        [
            {
                "state": "approved",
                "comment": "validated for isolated oracle execution",
                "environments": [{"name": "tcc-deployment-approval"}],
                "user": {"login": "researcher"},
            }
        ],
    )
    write_json(
        paths["human_gate_decision"],
        {
            "candidate_id": "opaque-001",
            "scope": "isolated-oracle-validation",
            "decision": "approve-isolated-validation",
            "status": "approved",
            "actor": "researcher",
            "selected_alternative": "deploy-as-is",
            "rollback_plan_verified": True,
            "next_action": "request-separate-cost-and-cloud-authorization",
            "bindings": {
                "deployment_gate_sha256": gate_sha,
                "deployment_action_sha256": action_sha,
                "github_approval_history_sha256": approval_sha,
            },
            "human_review_evidence": {
                "source": "github-environment-protection",
                "repository": "owner/repository",
                "workflow_run_id": 1234,
                "environment": "tcc-deployment-approval",
                "state": "approved",
                "reviewer": "researcher",
                "comment": "validated for isolated oracle execution",
                "approval_history_sha256": approval_sha,
            },
            "cloud_execution_authorized": False,
            "operational_mutation_authorized": False,
            "operational_mutation_performed": False,
        },
    )
    return paths


class ValidateHumanGateReceiptTests(unittest.TestCase):
    def test_valid_protected_review_closes_the_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            result = MODULE.validate(
                decision_chain(pathlib.Path(directory)),
                "tcc-deployment-approval",
            )

        self.assertTrue(result["validated"])
        self.assertEqual("researcher", result["reviewer"])
        self.assertEqual("deploy-as-is", result["selected_alternative"])
        self.assertFalse(result["cloud_execution_authorized_by_receipt"])
        self.assertFalse(result["operational_mutation_authorized"])

    def test_tampered_action_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = decision_chain(pathlib.Path(directory))
            action = json.loads(paths["deployment_action"].read_text(encoding="utf-8"))
            action["rollback_plan"]["namespace"] = "operational"
            write_json(paths["deployment_action"], action)

            with self.assertRaisesRegex(ValueError, "rollback plan"):
                MODULE.validate(paths, "tcc-deployment-approval")

    def test_receipt_without_protected_environment_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = decision_chain(pathlib.Path(directory))
            receipt = json.loads(
                paths["human_gate_decision"].read_text(encoding="utf-8")
            )
            receipt["human_review_evidence"]["source"] = "manual-cli"
            write_json(paths["human_gate_decision"], receipt)

            with self.assertRaisesRegex(ValueError, "protected GitHub"):
                MODULE.validate(paths, "tcc-deployment-approval")

    def test_tampered_approval_history_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = decision_chain(pathlib.Path(directory))
            history = json.loads(
                paths["github_approval_history"].read_text(encoding="utf-8")
            )
            history[0]["user"]["login"] = "different-reviewer"
            write_json(paths["github_approval_history"], history)

            with self.assertRaisesRegex(ValueError, "approval history"):
                MODULE.validate(paths, "tcc-deployment-approval")


if __name__ == "__main__":
    unittest.main()
