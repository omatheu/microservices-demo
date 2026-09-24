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
        self.assertIn('schema_version:"1.1.0"', rendered)
        self.assertIn('source_commit', rendered)
        self.assertIn('source_tree', rendered)
        self.assertIn('PR_HEAD_SHA: ${{ github.event.pull_request.head.sha }}', rendered)
        self.assertIn('pr-${PR_HEAD_SHA}', rendered)
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
        self.assertIn("publish-experiment-runtimes.sh", rendered)
        self.assertIn("bind-runtime-publication.py", rendered)
        self.assertIn("manifest-bindings", rendered)
        self.assertIn("PDT_CONTROLLER_IMAGE", rendered)
        self.assertIn("published-experiment-runtimes-pr-", rendered)
        self.assertIn("validate-pdt-runtime.py", rendered)
        self.assertIn("--require-frozen", rendered)
        self.assertIn("run-comparative-candidate.sh", rendered)
        self.assertIn("cleanup-experimental-workloads.sh", rendered)

        human_gate = workflow["jobs"]["human-gate-receipt"]
        self.assertEqual(human_gate["environment"], "tcc-deployment-approval")
        self.assertEqual(
            human_gate["permissions"], {"actions": "read", "contents": "read"}
        )
        self.assertNotIn("id-token", human_gate["permissions"])
        self.assertIn("record-human-gate-decision.py", rendered)
        self.assertIn("/actions/runs/${GITHUB_RUN_ID}/approvals", rendered)
        self.assertIn("human-gate-receipt-pr-", rendered)

    def test_runtime_publication_is_separate_and_has_no_cluster_access_path(self):
        workflow = load(CLOUD_WORKFLOW)
        rendered = CLOUD_WORKFLOW.read_text(encoding="utf-8")
        job = workflow["jobs"]["runtime-publication"]
        job_rendered = str(job)

        self.assertEqual(job["environment"], "tcc-experiment")
        self.assertEqual(job["permissions"], {"contents": "read", "id-token": "write"})
        self.assertEqual(job["concurrency"]["cancel-in-progress"], "false")
        self.assertEqual(
            job["if"],
            "needs.authorize.outputs.runtime_publication_authorized == 'true'",
        )
        self.assertIn("tcc-runtime-publication", rendered)
        self.assertIn("GCP_RUNTIME_PUBLISHER_SERVICE_ACCOUNT", job_rendered)
        self.assertIn("TCC_RUNTIME_PUBLICATION_ACKNOWLEDGED", job_rendered)
        self.assertNotIn("TCC_COST_REVIEW_ACKNOWLEDGED", job_rendered)
        self.assertIn("ALLOW_RUNTIME_PUBLICATION", job_rendered)
        self.assertNotIn("ALLOW_EXPERIMENTAL_CLOUD_EXECUTION", job_rendered)
        self.assertIn("publish-experiment-runtimes.sh", job_rendered)
        self.assertIn("bind-runtime-publication.py", job_rendered)
        self.assertNotIn("get-credentials", job_rendered)
        self.assertNotIn("gke-gcloud-auth-plugin", job_rendered)
        self.assertNotIn("kubectl", job_rendered)
        self.assertNotIn("run-comparative-candidate.sh", job_rendered)
        self.assertNotIn("GCP_EXPERIMENT_SERVICE_ACCOUNT", job_rendered)
        self.assertIn(
            'if [[ "${experiment_label}" == "${runtime_publication_label}" ]]',
            rendered,
        )

    def test_cloud_auth_is_after_financial_and_candidate_guards(self):
        workflow = load(CLOUD_WORKFLOW)
        steps = workflow["jobs"]["paired-experiment"]["steps"]
        names = [step["name"] for step in steps]
        job_rendered = str(workflow["jobs"]["paired-experiment"])

        financial = names.index("Require the per-block financial kill switch")
        candidate = names.index("Resolve and require one public experimental candidate")
        cloud_auth = names.index("Authenticate with Google Cloud through Workload Identity Federation")
        publication_step = names.index("Publish and attest the exact engineering runtime images")
        publication = job_rendered.index("publish-experiment-runtimes.sh")
        binding = job_rendered.index("bind-runtime-publication.py")
        self.assertLess(financial, cloud_auth)
        self.assertLess(candidate, cloud_auth)
        self.assertLess(cloud_auth, publication_step)
        self.assertLess(publication, binding)

        cleanup = names.index("Enforce cleanup of billable experimental workloads")
        paired = names.index("Run the paired conventional and PDT pipeline")
        evidence = names.index("Upload paired experimental evidence")
        self.assertLess(paired, cleanup)
        self.assertLess(cleanup, evidence)
        self.assertEqual(steps[paired]["timeout-minutes"], "105")
        self.assertEqual(steps[cleanup]["timeout-minutes"], "15")
        self.assertEqual(
            steps[cleanup]["if"],
            "always() && steps.cluster.outputs.connected == 'true'",
        )
        self.assertEqual(
            steps[cleanup]["env"]["ALLOW_EXPERIMENTAL_CLEANUP"], "true"
        )
        cleanup_rendered = str(steps[cleanup])
        self.assertNotIn("operational", cleanup_rendered)
        self.assertNotIn("oracle", cleanup_rendered)

        publication_steps = workflow["jobs"]["runtime-publication"]["steps"]
        publication_names = [step["name"] for step in publication_steps]
        self.assertLess(
            publication_names.index("Require the publication financial kill switch"),
            publication_names.index("Authenticate the Artifact Registry-only identity"),
        )
        self.assertLess(
            publication_names.index("Require the locked pre-freeze protocol state"),
            publication_names.index("Authenticate the Artifact Registry-only identity"),
        )


if __name__ == "__main__":
    unittest.main()
