import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment/scripts/prepare-pdt-controller-job.py"
CANDIDATE_PATH = REPO_ROOT / "experiment/pdt/candidates/engineering-artifact-binding-v2.json"
SNAPSHOT_PATH = REPO_ROOT / "experiment/ci/fixtures/pdt-input-state.json"
THRESHOLDS_PATH = REPO_ROOT / "experiment/staging/safety-thresholds.json"
MODEL_POLICY_PATH = REPO_ROOT / "experiment/pdt/model-policy.json"
IMAGE = "us-central1-docker.pkg.dev/project/repository/checkout-pdt-controller@sha256:" + "c" * 64
SPEC = importlib.util.spec_from_file_location("prepare_pdt_controller_job", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resource(result, kind):
    return next(item for item in result["items"] if item["kind"] == kind)


class PreparePdtControllerJobTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.control_path = pathlib.Path(self.temporary.name) / "control.json"
        self.control_path.write_text(
            json.dumps(
                {
                    "mechanism": "conventional-ci-cd-with-staging",
                    "candidate_id": "engineering-artifact-binding-v2",
                    "decision": "approve",
                    "control_decision_sealed": True,
                    "candidate_definition_sha256": sha(CANDIDATE_PATH),
                    "immutable_artifacts": [
                        {
                            "component": "checkoutservice",
                            "remote_reference": "us-central1-docker.pkg.dev/project/repository/checkoutservice@sha256:" + "a" * 64,
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def prepare(self, image=IMAGE):
        return MODULE.prepare(
            image,
            CANDIDATE_PATH,
            self.control_path,
            SNAPSHOT_PATH,
            THRESHOLDS_PATH,
            MODEL_POLICY_PATH,
            1,
        )

    def test_job_is_on_demand_isolated_and_has_no_cluster_token(self):
        result = self.prepare()
        job = resource(result, "Job")
        pod = job["spec"]["template"]["spec"]
        container = pod["containers"][0]

        self.assertEqual(job["metadata"]["namespace"], "pdt-system")
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(container["image"], IMAGE)
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertEqual(job["spec"]["backoffLimit"], 0)
        self.assertEqual(resource(result, "NetworkPolicy")["spec"]["policyTypes"], ["Ingress", "Egress"])

    def test_config_map_contains_expected_bound_plan(self):
        result = self.prepare()
        config = resource(result, "ConfigMap")
        plan = json.loads(config["data"]["expected-plan.json"])

        self.assertTrue(config["immutable"])
        self.assertEqual(plan["controller_id"], "checkout-pdt-controller-v1")
        self.assertEqual(plan["sealed_inputs"]["candidate_definition_sha256"], sha(CANDIDATE_PATH))
        self.assertFalse(plan["execution"]["operational_mutation_allowed"])

    def test_mutable_controller_image_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "immutable registry digest"):
            self.prepare("registry/controller:latest")


if __name__ == "__main__":
    unittest.main()
