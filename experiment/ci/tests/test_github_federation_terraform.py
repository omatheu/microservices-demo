import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
FEDERATION = REPO_ROOT / "infra" / "terraform" / "github-actions.tf"
VARIABLES = REPO_ROOT / "infra" / "terraform" / "variables.tf"
OUTPUTS = REPO_ROOT / "infra" / "terraform" / "outputs.tf"


class GithubFederationTerraformTests(unittest.TestCase):
    def test_federation_is_disabled_by_default_and_never_creates_a_key(self):
        variables = VARIABLES.read_text(encoding="utf-8")
        federation = FEDERATION.read_text(encoding="utf-8")

        declaration = variables.split(
            'variable "enable_github_actions_federation"', 1
        )[1].split("variable ", 1)[0]
        self.assertIn("default     = false", declaration)
        self.assertNotIn("google_service_account_key", federation)

    def test_oidc_trust_uses_immutable_ids_and_protected_context(self):
        federation = FEDERATION.read_text(encoding="utf-8")

        for claim in (
            "repository_id",
            "repository_owner_id",
            "environment",
            "event_name",
            "workflow_ref",
        ):
            self.assertIn(f"assertion.{claim}", federation)
        self.assertIn("assertion.event_name == 'workflow_run'", federation)

    def test_cloud_identity_has_general_mutation_only_in_staging_and_pdt(self):
        federation = FEDERATION.read_text(encoding="utf-8")

        mutable = federation.split(
            "github_mutable_namespaces = toset([", 1
        )[1].split("])", 1)[0]
        self.assertIn('"staging"', mutable)
        self.assertIn('"pdt"', mutable)
        self.assertNotIn('"operational"', mutable)
        self.assertNotIn('"oracle"', mutable)
        self.assertIn("github_experiment_operational_reader", federation)

    def test_pdt_system_permission_is_limited_to_on_demand_controller_jobs(self):
        federation = FEDERATION.read_text(encoding="utf-8")
        controller = federation.split(
            'resource "kubernetes_role_v1" "github_experiment_pdt_controller"', 1
        )[1].split('resource "kubernetes_role_binding_v1"', 1)[0]

        self.assertIn('["batch"]', controller)
        self.assertIn('["jobs"]', controller)
        self.assertIn('["configmaps", "serviceaccounts"]', controller)
        self.assertIn('["networkpolicies"]', controller)
        self.assertIn('["pods/log"]', controller)
        self.assertNotIn('["deployments"]', controller)
        self.assertNotIn('["services"]', controller)
        self.assertNotIn('["secrets"]', controller)

    def test_oracle_permission_is_namespaced_and_excludes_secrets(self):
        federation = FEDERATION.read_text(encoding="utf-8")
        oracle = federation.split(
            'resource "kubernetes_role_v1" "github_experiment_oracle_runner"', 1
        )[1].split(
            'resource "kubernetes_role_binding_v1" "github_experiment_oracle_runner"',
            1,
        )[0]

        self.assertIn('experiment["oracle"]', oracle)
        self.assertIn('["serviceaccounts", "services"]', oracle)
        self.assertIn('["deployments"]', oracle)
        self.assertIn('["networkpolicies"]', oracle)
        self.assertIn('["pods/portforward"]', oracle)
        self.assertNotIn('["secrets"]', oracle)
        self.assertNotIn('["configmaps"]', oracle)
        self.assertNotIn('["jobs"]', oracle)
        self.assertNotIn("persistentvolume", oracle.lower())

    def test_project_roles_remain_the_declared_minimum(self):
        federation = FEDERATION.read_text(encoding="utf-8")
        roles = federation.split("github_project_roles = toset([", 1)[1].split("])", 1)[0]

        self.assertIn('"roles/container.clusterViewer"', roles)
        self.assertIn('"roles/monitoring.viewer"', roles)
        self.assertIn('"roles/serviceusage.serviceUsageConsumer"', roles)
        self.assertNotIn("roles/editor", roles)
        self.assertNotIn("roles/owner", roles)

    def test_runtime_publisher_is_keyless_and_artifact_registry_only(self):
        federation = FEDERATION.read_text(encoding="utf-8")
        variables = VARIABLES.read_text(encoding="utf-8")
        outputs = OUTPUTS.read_text(encoding="utf-8")

        self.assertIn('resource "google_service_account" "github_runtime_publisher"', federation)
        self.assertIn(
            'resource "google_service_account_iam_member" "github_runtime_publisher_federation"',
            federation,
        )
        publisher_writer = federation.split(
            'resource "google_artifact_registry_repository_iam_member" "github_runtime_publisher_writer"',
            1,
        )[1].split('resource "kubernetes_', 1)[0]
        self.assertIn('role       = "roles/artifactregistry.writer"', publisher_writer)
        self.assertIn("google_service_account.github_runtime_publisher", publisher_writer)

        project_roles = federation.split(
            'resource "google_project_iam_member" "github_experiment"', 1
        )[1].split(
            'resource "google_artifact_registry_repository_iam_member"', 1
        )[0]
        kubernetes_resources = federation.split('resource "kubernetes_', 1)[1]
        self.assertNotIn("github_runtime_publisher", project_roles)
        self.assertNotIn("github_runtime_publisher", kubernetes_resources)
        self.assertNotIn("google_service_account_key", federation)
        self.assertIn("github_runtime_publisher_service_account_id", variables)
        self.assertIn("runtime_publisher_service_account", outputs)


if __name__ == "__main__":
    unittest.main()
