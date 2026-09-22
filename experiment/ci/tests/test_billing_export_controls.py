import pathlib
import json
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
STACK = REPO_ROOT / "infra" / "terraform-billing-export"
TERRAFORM = STACK / "main.tf"
VARIABLES = STACK / "variables.tf"
MAIN = STACK / "main.tf"
QUERY = REPO_ROOT / "experiment" / "scripts" / "query-billing-cost-window.sh"
CI_RUNNER = REPO_ROOT / "experiment" / "scripts" / "run-conventional-ci-local.sh"
LATEST_READINESS = (
    REPO_ROOT
    / "experiment/evidence/finance/protocol-freeze-readiness-20260922T013315Z.json"
)


class BillingExportControlsTests(unittest.TestCase):
    def test_dataset_has_an_independent_disabled_by_default_gate(self):
        variables = VARIABLES.read_text(encoding="utf-8")
        declaration = variables.split('variable "enable_billing_export_dataset"', 1)[1].split(
            "variable ", 1
        )[0]

        self.assertIn("default     = false", declaration)
        self.assertIn("enable_billing_export_dataset", MAIN.read_text(encoding="utf-8"))
        self.assertIn('"bigquery.googleapis.com"', MAIN.read_text(encoding="utf-8"))

    def test_stack_is_independent_from_cluster_resources(self):
        rendered = "\n".join(
            path.read_text(encoding="utf-8") for path in STACK.glob("*.tf")
        )

        self.assertNotIn("google_container_cluster", rendered)
        self.assertNotIn("kubernetes_", rendered)
        self.assertNotIn("google_artifact_registry", rendered)
        self.assertNotIn("google_billing_budget", rendered)

    def test_dataset_is_us_only_and_protected_from_destroy(self):
        terraform = TERRAFORM.read_text(encoding="utf-8")
        variables = VARIABLES.read_text(encoding="utf-8")

        self.assertIn("location                   = var.billing_export_dataset_location", terraform)
        self.assertIn('var.billing_export_dataset_location == "US"', variables)
        self.assertIn("delete_contents_on_destroy = false", terraform)
        self.assertIn("prevent_destroy = true", terraform)
        self.assertNotIn("default_table_expiration_ms", terraform)

    def test_cost_query_is_project_scoped_and_has_a_100_mb_guard(self):
        rendered = QUERY.read_text(encoding="utf-8")

        self.assertIn("project.id = @project_id", rendered)
        self.assertIn("MAXIMUM_BYTES_BILLED:-100000000", rendered)
        self.assertIn("maximum_bytes_billed > 100000000", rendered)
        self.assertIn('--maximum_bytes_billed="$maximum_bytes_billed"', rendered)
        self.assertIn('startswith("gcp_billing_export_v1_")', rendered)
        self.assertIn("cloud_execution_authorized: false", rendered)

    def test_conventional_ci_validates_the_isolated_stack(self):
        rendered = CI_RUNNER.read_text(encoding="utf-8")

        self.assertIn('infra/terraform-billing-export', rendered)
        self.assertIn('terraform -chdir="${terraform_directory}" validate', rendered)

    def test_latest_readiness_snapshot_preserves_the_financial_blocker(self):
        value = json.loads(LATEST_READINESS.read_text(encoding="utf-8"))

        self.assertEqual("read-only-metadata-only", value["collection_mode"])
        self.assertTrue(value["billing_export"]["dataset_found"])
        self.assertEqual(0, value["billing_export"]["table_count"])
        self.assertFalse(value["billing_export"]["current_spend_query_available"])
        self.assertFalse(value["billing_export"]["billable_query_executed"])
        self.assertFalse(value["protocol_financial_review"]["approved"])
        self.assertFalse(value["mutations_performed"])
        self.assertFalse(value["cloud_resources_changed"])
        self.assertFalse(value["billable_data_queries_executed"])
        self.assertEqual(12, value["runtime"]["operational_deployments"])
        self.assertEqual(12, value["runtime"]["operational_available_deployments"])
        self.assertFalse(
            value["artifact_registry"]["experiment_runtime_images_published"]
        )


if __name__ == "__main__":
    unittest.main()
