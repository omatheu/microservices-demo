import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
FEDERATION = REPO_ROOT / "infra" / "terraform" / "github-actions.tf"
VARIABLES = REPO_ROOT / "infra" / "terraform" / "variables.tf"


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

    def test_cloud_identity_can_mutate_only_staging_and_pdt(self):
        federation = FEDERATION.read_text(encoding="utf-8")

        mutable = federation.split(
            "github_mutable_namespaces = toset([", 1
        )[1].split("])", 1)[0]
        self.assertIn('"staging"', mutable)
        self.assertIn('"pdt"', mutable)
        self.assertNotIn('"operational"', mutable)
        self.assertNotIn('"oracle"', mutable)
        self.assertIn("github_experiment_operational_reader", federation)

    def test_project_roles_remain_the_declared_minimum(self):
        federation = FEDERATION.read_text(encoding="utf-8")
        roles = federation.split("github_project_roles = toset([", 1)[1].split("])", 1)[0]

        self.assertIn('"roles/container.clusterViewer"', roles)
        self.assertIn('"roles/monitoring.viewer"', roles)
        self.assertIn('"roles/serviceusage.serviceUsageConsumer"', roles)
        self.assertNotIn("roles/editor", roles)
        self.assertNotIn("roles/owner", roles)


if __name__ == "__main__":
    unittest.main()
