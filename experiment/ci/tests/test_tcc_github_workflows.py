import pathlib
import unittest

import yaml


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "tcc-pr-ci.yaml"
CLOUD_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "tcc-pr-experiment.yaml"


def load(path):
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


class TccGithubWorkflowTests(unittest.TestCase):
    def test_pull_request_workflow_has_no_cloud_identity_permission(self):
        workflow = load(CI_WORKFLOW)

        self.assertIn("pull_request", workflow["on"])
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        job = workflow["jobs"]["conventional-ci"]
        self.assertNotIn("id-token", job.get("permissions", {}))
        rendered = CI_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("run-conventional-ci-local.sh", rendered)
        self.assertIn("compose-conventional-decision.py", rendered)

    def test_pull_request_builds_runtime_images_without_publishing(self):
        workflow = load(CI_WORKFLOW)
        rendered = CI_WORKFLOW.read_text(encoding="utf-8")
        job = workflow["jobs"]["runtime-images"]

        self.assertEqual(job["permissions"], {"contents": "read"})
        self.assertNotIn("id-token", job["permissions"])
        self.assertIn("experiment/pdt/controller/Dockerfile", rendered)
        self.assertIn("experiment/oracle/harness/Dockerfile", rendered)
        self.assertIn("src/currencyservice/Dockerfile", rendered)
        self.assertIn("published_to_registry:false", rendered)
        self.assertNotIn("docker push", rendered)

    def test_cloud_workflow_is_chained_and_protected(self):
        workflow = load(CLOUD_WORKFLOW)
        rendered = CLOUD_WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("workflow_run", workflow["on"])
        job = workflow["jobs"]["paired-experiment"]
        self.assertEqual(job["environment"], "tcc-experiment")
        self.assertEqual(job["permissions"]["id-token"], "write")
        self.assertEqual(job["concurrency"]["cancel-in-progress"], "false")
        self.assertIn("tcc-experiment-cloud", rendered)
        self.assertIn("tcc-cost-reviewed", rendered)
        self.assertIn("TCC_COST_REVIEW_ACKNOWLEDGED", rendered)
        self.assertIn("run-comparative-candidate.sh", rendered)

    def test_cloud_auth_is_after_financial_and_candidate_guards(self):
        rendered = CLOUD_WORKFLOW.read_text(encoding="utf-8")

        financial = rendered.index("Require the per-block financial kill switch")
        candidate = rendered.index("Resolve and require one public experimental candidate")
        cloud_auth = rendered.index("Authenticate with Google Cloud")
        self.assertLess(financial, cloud_auth)
        self.assertLess(candidate, cloud_auth)


if __name__ == "__main__":
    unittest.main()
