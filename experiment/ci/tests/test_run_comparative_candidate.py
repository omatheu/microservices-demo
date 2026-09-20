import json
import os
import pathlib
import subprocess
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "run-comparative-candidate.sh"
CANDIDATE_PATH = (
    REPO_ROOT
    / "experiment"
    / "pdt"
    / "candidates"
    / "engineering-artifact-binding-v2.json"
)


class ComparativeCandidateRunnerTests(unittest.TestCase):
    def test_cloud_execution_is_fail_closed_before_cluster_access(self):
        candidate = json.loads(CANDIDATE_PATH.read_text(encoding="utf-8"))
        environment = os.environ.copy()
        environment.update(
            {
                "MODE": "engineering",
                "CANDIDATE_ID": candidate["candidate_id"],
                "CANDIDATE_DEFINITION": str(CANDIDATE_PATH),
                "ARTIFACT_REGISTRY_PREFIX": "us-central1-docker.pkg.dev/test/repository",
                "ALLOW_EXPERIMENTAL_CLOUD_EXECUTION": "false",
                "COST_REVIEW_ACKNOWLEDGED": "false",
            }
        )

        result = subprocess.run(
            [str(SCRIPT_PATH)],
            cwd=REPO_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("can publish images and start billable GKE workloads", result.stderr)
        self.assertNotIn("Namespace staging contains active pods", result.stderr)


if __name__ == "__main__":
    unittest.main()
