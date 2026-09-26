import json
import os
import pathlib
import subprocess
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "run-repeated-comparative-candidate.sh"
CANDIDATE_PATH = REPO_ROOT / "experiment" / "pdt" / "candidates" / "engineering-artifact-binding-v2.json"


class RepeatedComparativeCandidateRunnerTests(unittest.TestCase):
    def environment(self, cloud="false", cost="false"):
        candidate = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
        environment = os.environ.copy()
        environment.update(
            {
                "CANDIDATE_ID": candidate["candidate_id"],
                "CANDIDATE_DEFINITION": str(CANDIDATE_PATH),
                "CANDIDATE_BASE_REF": "a" * 40,
                "ARTIFACT_REGISTRY_PREFIX": "us-central1-docker.pkg.dev/test/repository",
                "PDT_CONTROLLER_IMAGE": "us-central1-docker.pkg.dev/microservices-demo-tcc/online-boutique-experiment/checkout-pdt-controller@sha256:"
                + "b" * 64,
                "ALLOW_EXPERIMENTAL_CLOUD_EXECUTION": cloud,
                "COST_REVIEW_ACKNOWLEDGED": cost,
            }
        )
        return environment

    def test_cloud_execution_is_fail_closed_before_cluster_access(self):
        result = subprocess.run(
            [str(SCRIPT_PATH)],
            cwd=REPO_ROOT,
            env=self.environment(),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("starts billable GKE workloads", result.stderr)
        self.assertNotIn("contains active pods", result.stderr)

    def test_draft_protocol_blocks_even_when_process_gates_are_true(self):
        result = subprocess.run(
            [str(SCRIPT_PATH)],
            cwd=REPO_ROOT,
            env=self.environment(cloud="true", cost="true"),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires the frozen three-repetition protocol", result.stderr)
        self.assertNotIn("contains active pods", result.stderr)

    def test_runner_seals_control_before_repeated_pdt_and_human_gate(self):
        rendered = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertEqual(rendered.count("run-conventional-ci-local.sh"), 1)
        self.assertIn("for repetition in 1 2 3", rendered)
        self.assertIn("run-traditional-staging.sh", rendered)
        self.assertIn("aggregate-conventional-repetitions.py", rendered)
        self.assertIn("capture-pdt-source-state.sh", rendered)
        self.assertIn("run-pdt-cycle.sh", rendered)
        self.assertIn("aggregate-pdt-repetitions.py", rendered)
        self.assertIn("evaluate-deployment-gate.py", rendered)
        self.assertIn("prepare-deployment-action.py", rendered)
        self.assertIn("cleanup-experimental-workloads.sh", rendered)
        self.assertIn("oracle-binding-snapshot.json", rendered)
        self.assertIn(
            'if (( ${#valid_pdt_repetitions[@]} < 2 )); then', rendered
        )
        self.assertNotIn(
            'reason: "paired-PDT-repetition-remained-infrastructure-invalid-after-retry"',
            rendered,
        )
        self.assertLess(
            rendered.index("aggregate-conventional-repetitions.py"),
            rendered.index("run-pdt-cycle.sh"),
        )
        self.assertLess(
            rendered.index("aggregate-pdt-repetitions.py"),
            rendered.index("evaluate-deployment-gate.py"),
        )
        self.assertIn('oracle_label_revealed: false', rendered)


if __name__ == "__main__":
    unittest.main()
