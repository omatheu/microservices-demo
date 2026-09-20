import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "prepare-deployment-action.py"
SPEC = importlib.util.spec_from_file_location("prepare_deployment_action", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

DIGEST = "registry.example/project/repository/checkoutservice@sha256:" + "a" * 64
DEFINITION_SHA = "b" * 64


def resource_change(cpu="400m"):
    return [
        {
            "deployment": "checkoutservice",
            "patch": {
                "spec": {
                    "replicas": 2,
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": "server",
                                    "resources": {
                                        "requests": {"cpu": "200m"},
                                        "limits": {"cpu": cpu},
                                    },
                                }
                            ]
                        }
                    },
                }
            },
        }
    ]


def candidate():
    return {
        "candidate_id": "opaque-001",
        "twin_object": "checkoutservice",
        "alternatives": [
            {
                "id": "deploy-as-is",
                "action": "deploy",
                "configuration_changes": [],
            },
            {
                "id": "capacity-safe",
                "action": "deploy",
                "configuration_changes": resource_change(),
            },
            {"id": "block", "action": "block", "configuration_changes": []},
        ],
    }


def snapshot():
    return {
        "snapshot_id": "snapshot-001",
        "binding": {
            "source_namespace": "operational",
            "twin_object": {"kind": "Deployment", "name": "checkoutservice"},
        },
        "synchronized_state": {
            "workloads": [
                {
                    "name": "checkoutservice",
                    "uid": "uid-001",
                    "generation": 2,
                    "resource_version": "42",
                }
            ]
        },
    }


def control():
    return {
        "candidate_id": "opaque-001",
        "mechanism": "conventional-ci-cd-with-staging",
        "decision": "approve",
        "control_decision_sealed": True,
        "candidate_definition_sha256": DEFINITION_SHA,
        "immutable_artifacts": [
            {"component": "checkoutservice", "remote_reference": DIGEST}
        ],
    }


def pdt(decision="approve"):
    alternative = "deploy-as-is" if decision == "approve" else "capacity-safe"
    changes = [] if decision == "approve" else resource_change()
    return {
        "candidate": "opaque-001",
        "snapshot_id": "snapshot-001",
        "decision": decision,
        "selected_alternative": alternative,
        "recommended_configuration": changes,
        "artifact_binding": {
            "immutable_artifacts": [
                {"component": "checkoutservice", "remote_reference": DIGEST}
            ],
            "candidate_definition_sha256": DEFINITION_SHA,
        },
    }


def gate(decision="approve"):
    alternative = "deploy-as-is" if decision == "approve" else "capacity-safe"
    return {
        "candidate_id": "opaque-001",
        "gate_state": "awaiting-human-confirmation",
        "pdt": {"decision": decision, "selected_alternative": alternative},
        "human_confirmation": {"status": "pending"},
        "operational_mutation_performed": False,
        "rollback_plan_required_before_mutation": True,
    }


class PrepareDeploymentActionTests(unittest.TestCase):
    def prepare(self, decision="approve"):
        return MODULE.prepare(
            candidate(), snapshot(), control(), pdt(decision), gate(decision), {"x": "y"}
        )

    def test_approve_prepares_deploy_as_is_without_authorization(self):
        result = self.prepare()
        self.assertEqual("isolated-oracle-validation", result["scope"])
        self.assertEqual("deploy-as-is", result["selected_alternative"])
        self.assertFalse(result["cloud_execution_authorized"])
        self.assertFalse(result["operational_mutation_authorized"])

    def test_reconfigure_prepares_selected_configuration_and_cleanup(self):
        result = self.prepare("reconfigure")
        self.assertEqual(resource_change(), result["forward_action"]["configuration_changes"])
        self.assertEqual(
            "delete-ephemeral-runtime-and-verify-empty",
            result["rollback_plan"]["strategy"],
        )

    def test_block_does_not_produce_deployable_action(self):
        value = pdt("approve")
        value["decision"] = "block"
        with self.assertRaisesRegex(ValueError, "approve or reconfigure"):
            MODULE.prepare(candidate(), snapshot(), control(), value, gate(), {})

    def test_recommendation_must_equal_selected_alternative(self):
        value = pdt("reconfigure")
        value["recommended_configuration"] = []
        with self.assertRaisesRegex(ValueError, "recommendation differs"):
            MODULE.prepare(candidate(), snapshot(), control(), value, gate("reconfigure"), {})

    def test_changes_cannot_escape_checkoutservice_boundary(self):
        value = candidate()
        value["alternatives"][1]["configuration_changes"][0]["deployment"] = "paymentservice"
        with self.assertRaisesRegex(ValueError, "only checkoutservice"):
            MODULE.prepare(value, snapshot(), control(), pdt("reconfigure"), gate("reconfigure"), {})

    def test_gate_must_precede_operational_mutation(self):
        value = gate()
        value["operational_mutation_performed"] = True
        with self.assertRaisesRegex(ValueError, "before operational mutation"):
            MODULE.prepare(candidate(), snapshot(), control(), pdt(), value, {})

    def test_snapshot_must_match_pdt_decision(self):
        value = snapshot()
        value["snapshot_id"] = "snapshot-002"
        with self.assertRaisesRegex(ValueError, "snapshot differ"):
            MODULE.prepare(candidate(), value, control(), pdt(), gate(), {})


if __name__ == "__main__":
    unittest.main()
