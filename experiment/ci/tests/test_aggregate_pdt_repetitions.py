import importlib.util
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "aggregate-pdt-repetitions.py"
SPEC = importlib.util.spec_from_file_location("aggregate_pdt_repetitions", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

GATE_PATH = REPO_ROOT / "experiment" / "scripts" / "evaluate-deployment-gate.py"
GATE_SPEC = importlib.util.spec_from_file_location("evaluate_deployment_gate", GATE_PATH)
GATE = importlib.util.module_from_spec(GATE_SPEC)
assert GATE_SPEC.loader is not None
GATE_SPEC.loader.exec_module(GATE)

ACTION_PATH = REPO_ROOT / "experiment" / "scripts" / "prepare-deployment-action.py"
ACTION_SPEC = importlib.util.spec_from_file_location("prepare_deployment_action", ACTION_PATH)
ACTION = importlib.util.module_from_spec(ACTION_SPEC)
assert ACTION_SPEC.loader is not None
ACTION_SPEC.loader.exec_module(ACTION)


CANDIDATE_SHA = "b" * 64
CONTROL_SHA = "a" * 64
ARTIFACTS = [
    {
        "component": "checkoutservice",
        "remote_reference": "registry.example/checkout@sha256:" + "c" * 64,
    }
]


def protocol(frozen=False):
    return {
        "protocol_id": "checkout-pdt-comparison-v1",
        "status": "frozen" if frozen else "pre-registration-candidate",
        "confirmatory_collection_allowed": frozen,
        "frozen_at": "2026-09-25T00:00:00Z" if frozen else None,
        "research_design": {"technical_repetitions_per_candidate": 3},
        "aggregation": {
            "minimum_valid_repetitions": 2,
            "mechanism_repetition_rule": {
                "planned_repetitions": 3,
                "minimum_valid_repetitions": 2,
                "safe_votes_to_approve": 2,
                "applies_symmetrically_to_control_and_treatment": True,
                "incomplete_outcome": "retry-once-before-label-then-exclude-or-block",
                "pdt_metric_aggregation": "median",
                "pdt_confidence_aggregation": "minimum",
                "pdt_action_snapshot": "latest-valid-repetition",
            },
        },
    }


def candidate(eligible=False):
    return {
        "candidate_id": "cand-opaque",
        "twin_object": "checkoutservice",
        "confirmatory_eligibility": eligible,
        "alternatives": [
            {
                "id": "deploy-as-is",
                "action": "deploy",
                "configuration_changes": [],
                "change_cost": 0,
            },
            {
                "id": "capacity-safe",
                "action": "deploy",
                "configuration_changes": [
                    {"deployment": "checkoutservice", "patch": {"spec": {"replicas": 2}}}
                ],
                "change_cost": 2,
            },
            {
                "id": "block",
                "action": "block",
                "configuration_changes": [],
                "change_cost": 10,
            },
        ],
    }


def control():
    return {
        "mechanism": "conventional-ci-cd-with-staging",
        "candidate_id": "cand-opaque",
        "protocol_id": "checkout-pdt-comparison-v1",
        "execution_mode": "engineering-dry-run",
        "decision": "approve",
        "control_decision_sealed": True,
        "candidate_definition_sha256": CANDIDATE_SHA,
        "immutable_artifacts": ARTIFACTS,
        "local_ci": {"run_id": "ci-cand-opaque", "decision": "pass"},
        "staging": {
            "executed": True,
            "decision": "PASS",
            "artifact_binding_verified": True,
        },
        "repetition_aggregation": {
            "outcome": "approve",
            "safe_votes": 2,
            "safe_votes_to_approve": 2,
        },
    }


def metrics(repetition, p95=700):
    return {
        "samples": 120,
        "successes": 120,
        "failures": 0,
        "success_rate": 1.0,
        "latency_ms": {"p50": 500 + repetition, "p95": p95, "p99": p95 + 100},
        "checkout": {
            "tests": 10,
            "successes": 10,
            "failures": 0,
            "latency_p95_ms": p95 + 20,
            "latency_p99_ms": p95 + 30,
            "unavailable": 0,
            "restart_increase": 0,
        },
    }


def pdt(repetition, deploy_safe=True, capacity_safe=True, mode="engineering"):
    definitions = candidate()["alternatives"]
    safe = {"deploy-as-is": deploy_safe, "capacity-safe": capacity_safe, "block": True}
    results = []
    for definition in definitions:
        deployable = definition["action"] == "deploy"
        results.append(
            {
                **definition,
                "safe": safe[definition["id"]],
                "predicted_metrics": metrics(
                    repetition, 700 if definition["id"] == "deploy-as-is" else 650
                )
                if deployable
                else None,
                "confidence": 0.9 - repetition * 0.1 if deployable else 1.0,
            }
        )
    return {
        "candidate": "cand-opaque",
        "repetition": repetition,
        "execution_mode": mode,
        "model_id": "empirical-counterfactual-v1",
        "snapshot_id": f"snapshot-{repetition}",
        "alternatives_evaluated": results,
        "artifact_binding": {
            "conventional_decision_sha256": CONTROL_SHA,
            "candidate_definition_sha256": CANDIDATE_SHA,
            "staging_binding_verified": True,
            "immutable_artifacts": ARTIFACTS,
        },
        "operational_mutation_performed": False,
    }


def invalid_ledger():
    return {
        "schema_version": "1.0.0",
        "candidate_id": "cand-opaque",
        "classification": "infrastructure-invalid",
        "label_revealed": False,
        "planned_repetitions": [1, 2, 3],
        "valid_repetitions": [1, 2],
        "invalid_repetitions": [
            {
                "repetition": 3,
                "attempts": 2,
                "reasons": ["cluster-timeout", "replacement-cluster-timeout"],
            }
        ],
    }


def aggregate(decisions, **kwargs):
    return MODULE.aggregate(
        kwargs.get("protocol_value", protocol()),
        kwargs.get("candidate_value", candidate()),
        CANDIDATE_SHA,
        kwargs.get("control_value", control()),
        CONTROL_SHA,
        decisions,
        invalid_repetition_ledger=kwargs.get("invalid_repetition_ledger"),
        allow_draft=kwargs.get("allow_draft", True),
    )


class AggregatePdtRepetitionsTests(unittest.TestCase):
    def test_deploy_as_is_majority_approves(self):
        result = aggregate([pdt(1), pdt(2), pdt(3, deploy_safe=False)])

        self.assertEqual(result["decision"], "approve")
        self.assertEqual(result["selected_alternative"], "deploy-as-is")
        self.assertEqual(result["confidence"], 0.6)
        self.assertEqual(result["snapshot_id"], "snapshot-3")
        self.assertEqual(
            result["predicted_metrics"]["aggregation"],
            "median-of-valid-repetitions",
        )

    def test_candidate_level_output_is_consumed_by_gate_and_action_preparer(self):
        control_value = control()
        result = aggregate([pdt(1), pdt(2), pdt(3)])
        gate = GATE.evaluate(control_value, result)
        self.assertEqual(gate["gate_state"], "awaiting-human-confirmation")

        snapshot = {
            "snapshot_id": "snapshot-3",
            "binding": {
                "source_namespace": "operational",
                "twin_object": {"kind": "Deployment", "name": "checkoutservice"},
            },
            "synchronized_state": {
                "workloads": [
                    {
                        "name": "checkoutservice",
                        "uid": "uid-1",
                        "generation": 1,
                        "resource_version": "7",
                    }
                ]
            },
        }
        action = ACTION.prepare(
            candidate(),
            snapshot,
            control_value,
            result,
            gate,
            {
                "candidate_definition_sha256": CANDIDATE_SHA,
                "snapshot_sha256": "d" * 64,
                "conventional_decision_sha256": CONTROL_SHA,
                "pdt_decision_sha256": "e" * 64,
                "deployment_gate_sha256": "f" * 64,
            },
        )
        self.assertEqual(action["status"], "prepared-awaiting-human-confirmation")
        self.assertEqual(action["selected_alternative"], "deploy-as-is")

    def test_unsafe_deploy_as_is_selects_majority_safe_reconfiguration(self):
        result = aggregate(
            [
                pdt(1, deploy_safe=False),
                pdt(2, deploy_safe=False),
                pdt(3, deploy_safe=True),
            ]
        )

        self.assertEqual(result["decision"], "reconfigure")
        self.assertEqual(result["selected_alternative"], "capacity-safe")
        self.assertTrue(result["recommended_configuration"])

    def test_no_majority_safe_deployment_blocks(self):
        result = aggregate(
            [
                pdt(1, False, False),
                pdt(2, False, False),
                pdt(3, True, True),
            ]
        )

        self.assertEqual(result["decision"], "block")
        self.assertEqual(result["selected_alternative"], "block")
        self.assertIsNone(result["predicted_metrics"])

    def test_two_valid_repetitions_need_the_same_prelabel_ledger(self):
        with self.assertRaisesRegex(ValueError, "ledger is incomplete"):
            aggregate([pdt(1), pdt(2)])

        result = aggregate(
            [pdt(1), pdt(2)], invalid_repetition_ledger=invalid_ledger()
        )
        self.assertEqual(result["decision"], "approve")
        self.assertEqual(result["repetition_aggregation"]["invalid_repetitions"], [3])

    def test_split_two_valid_votes_blocks(self):
        result = aggregate(
            [pdt(1), pdt(2, deploy_safe=False, capacity_safe=False)],
            invalid_repetition_ledger=invalid_ledger(),
        )
        self.assertEqual(result["decision"], "block")

    def test_artifact_or_candidate_alternative_substitution_is_rejected(self):
        changed = pdt(3)
        changed["artifact_binding"]["immutable_artifacts"] = []
        with self.assertRaisesRegex(ValueError, "artifact binding differs"):
            aggregate([pdt(1), pdt(2), changed])

        changed = pdt(3)
        changed["alternatives_evaluated"][1]["configuration_changes"] = []
        with self.assertRaisesRegex(ValueError, "metadata differ"):
            aggregate([pdt(1), pdt(2), changed])

    def test_duplicate_or_wrong_mode_repetition_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicated"):
            aggregate([pdt(1), pdt(1), pdt(3)])

        with self.assertRaisesRegex(ValueError, "identity, mode"):
            aggregate(
                [pdt(1), pdt(2), pdt(3, mode="confirmatory")]
            )

    def test_frozen_protocol_requires_confirmatory_eligible_inputs(self):
        value = protocol(frozen=True)
        with self.assertRaisesRegex(ValueError, "eligible candidate"):
            aggregate(
                [pdt(1), pdt(2), pdt(3)],
                protocol_value=value,
                allow_draft=False,
            )

        result = aggregate(
            [
                pdt(1, mode="confirmatory"),
                pdt(2, mode="confirmatory"),
                pdt(3, mode="confirmatory"),
            ],
            protocol_value=value,
            candidate_value=candidate(eligible=True),
            control_value={**control(), "execution_mode": "confirmatory"},
            allow_draft=False,
        )
        self.assertEqual(result["execution_mode"], "confirmatory")

    def test_pdt_rule_must_be_predeclared(self):
        value = protocol()
        del value["aggregation"]["mechanism_repetition_rule"][
            "pdt_confidence_aggregation"
        ]
        with self.assertRaisesRegex(ValueError, "rule is incomplete"):
            aggregate([pdt(1), pdt(2), pdt(3)], protocol_value=value)


if __name__ == "__main__":
    unittest.main()
