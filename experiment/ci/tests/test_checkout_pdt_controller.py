import copy
import hashlib
import importlib.util
import json
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
CONTROLLER_PATH = REPO_ROOT / "experiment/pdt/controller/checkout_pdt_controller.py"
CANDIDATE_PATH = REPO_ROOT / "experiment/pdt/candidates/engineering-artifact-binding-v2.json"
SNAPSHOT_PATH = REPO_ROOT / "experiment/ci/fixtures/pdt-input-state.json"
THRESHOLDS_PATH = REPO_ROOT / "experiment/staging/safety-thresholds.json"
MODEL_POLICY_PATH = REPO_ROOT / "experiment/pdt/model-policy.json"
SPEC = importlib.util.spec_from_file_location("checkout_pdt_controller", CONTROLLER_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def conventional(candidate_sha):
    return {
        "mechanism": "conventional-ci-cd-with-staging",
        "candidate_id": "engineering-artifact-binding-v2",
        "decision": "approve",
        "control_decision_sealed": True,
        "candidate_definition_sha256": candidate_sha,
        "immutable_artifacts": [
            {
                "component": "checkoutservice",
                "remote_reference": "us-central1-docker.pkg.dev/project/repository/checkoutservice@sha256:" + "a" * 64,
            }
        ],
    }


class CheckoutPdtControllerTests(unittest.TestCase):
    def build(self, candidate=None, control=None):
        candidate = candidate or load(CANDIDATE_PATH)
        candidate_sha = sha(CANDIDATE_PATH)
        control = control or conventional(candidate_sha)
        return MODULE.build_execution_plan(
            candidate,
            candidate_sha,
            control,
            "b" * 64,
            load(SNAPSHOT_PATH),
            load(THRESHOLDS_PATH),
            sha(THRESHOLDS_PATH),
            load(MODEL_POLICY_PATH),
            sha(MODEL_POLICY_PATH),
            1,
        )

    def test_plan_binds_state_artifacts_and_counterfactuals(self):
        result = self.build()

        self.assertEqual(result["controller_id"], "checkout-pdt-controller-v1")
        self.assertEqual(result["twin_object"], "checkoutservice")
        self.assertEqual(result["source_binding"]["target_namespace"], "pdt")
        self.assertEqual(len(result["counterfactuals"]), 3)
        self.assertFalse(result["execution"]["operational_mutation_allowed"])
        self.assertTrue(result["decision_contract"]["human_confirmation_required"])

    def test_plan_rejects_oracle_metadata_leak(self):
        candidate = load(CANDIDATE_PATH)
        candidate["operator_id"] = "INF-CPU-01"

        with self.assertRaisesRegex(ValueError, "forbidden oracle keys"):
            self.build(candidate=candidate)

    def test_plan_rejects_reconfiguration_outside_twin_boundary(self):
        candidate = load(CANDIDATE_PATH)
        candidate["alternatives"][1]["configuration_changes"][0]["deployment"] = "paymentservice"

        with self.assertRaisesRegex(ValueError, "limited to checkoutservice"):
            self.build(candidate=candidate)

    def test_plan_rejects_unsealed_control(self):
        control = conventional(sha(CANDIDATE_PATH))
        control["control_decision_sealed"] = False

        with self.assertRaisesRegex(ValueError, "sealed conventional approval"):
            self.build(control=control)


if __name__ == "__main__":
    unittest.main()
