import copy
import hashlib
import importlib.util
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "experiment" / "scripts" / "audit-runtime-publication-readiness.py"
SPEC = importlib.util.spec_from_file_location("audit_runtime_publication_readiness", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def snapshot():
    publisher_member = f"serviceAccount:{MODULE.RUNTIME_PUBLISHER_EMAIL}"
    workflow_sha256 = hashlib.sha256(
        (REPO_ROOT / MODULE.WORKFLOW_PATH).read_bytes()
    ).hexdigest()
    return {
        "repository": {"default_branch": "main"},
        "labels": [{"name": name} for name in sorted(MODULE.REQUIRED_LABELS)],
        "environment": {
            "protection_rules": [
                {
                    "type": "required_reviewers",
                    "reviewers": [
                        {
                            "type": "User",
                            "reviewer": {"login": MODULE.REQUIRED_REVIEWER_LOGIN},
                        }
                    ],
                }
            ],
            "deployment_branch_policy": {
                "protected_branches": False,
                "custom_branch_policies": True,
            },
        },
        "environment_branch_policies": {
            "branch_policies": [{"name": MODULE.REQUIRED_DEPLOYMENT_BRANCH}]
        },
        "environment_secrets": {
            "secrets": [{"name": name} for name in sorted(MODULE.REQUIRED_SECRETS)]
        },
        "environment_variables": {
            "variables": [
                {"name": name, "value": value}
                for name, value in sorted(MODULE.REQUIRED_DISABLED_VARIABLES.items())
            ]
        },
        "workflow_on_default_branch": {
            "path": MODULE.WORKFLOW_PATH,
            "sha": "1" * 40,
        },
        "workflow_on_default_branch_sha256": workflow_sha256,
        "reviewed_local_workflow_sha256": workflow_sha256,
        "pull_request": {
            "number": 1,
            "state": "open",
            "draft": False,
            "head": {"repo": {"full_name": MODULE.REPOSITORY}},
            "labels": [],
        },
        "runtime_publisher_service_account": {
            "email": MODULE.RUNTIME_PUBLISHER_EMAIL,
            "disabled": False,
        },
        "runtime_publisher_service_account_policy": {
            "bindings": [
                {
                    "role": "roles/iam.workloadIdentityUser",
                    "members": [MODULE.REPOSITORY_PRINCIPAL],
                }
            ]
        },
        "runtime_publisher_user_managed_keys": [],
        "artifact_registry_policy": {
            "bindings": [
                {"role": "roles/artifactregistry.writer", "members": [publisher_member]}
            ]
        },
        "project_policy": {"bindings": []},
        "collection_errors": {},
    }


class AuditRuntimePublicationReadinessTests(unittest.TestCase):
    def test_ready_state_is_safe_and_does_not_authorize_publication(self):
        result = MODULE.audit(snapshot(), 1)

        self.assertEqual(13, result["check_count"])
        self.assertEqual(13, result["passed_count"])
        self.assertTrue(result["ready_for_controlled_enablement"])
        self.assertEqual([], result["blocking_requirements"])
        self.assertTrue(result["read_only"])
        self.assertFalse(result["cloud_mutation_performed"])
        self.assertFalse(result["github_mutation_performed"])
        self.assertFalse(result["publication_authorized"])

    def test_missing_identity_label_secret_and_variable_fail_closed(self):
        value = snapshot()
        value["labels"] = [
            item for item in value["labels"] if item["name"] != "tcc-runtime-publication"
        ]
        value["environment_secrets"]["secrets"] = [
            item
            for item in value["environment_secrets"]["secrets"]
            if item["name"] != "GCP_RUNTIME_PUBLISHER_SERVICE_ACCOUNT"
        ]
        value["environment_variables"]["variables"] = [
            item
            for item in value["environment_variables"]["variables"]
            if item["name"] != "TCC_RUNTIME_PUBLICATION_ACKNOWLEDGED"
        ]
        value["runtime_publisher_service_account"] = None
        value["runtime_publisher_user_managed_keys"] = None
        value["runtime_publisher_service_account_policy"] = None
        value["artifact_registry_policy"] = {"bindings": []}

        result = MODULE.audit(value, 1)

        for blocker in (
            "required-labels-defined",
            "protected-environment-secrets",
            "financial-kill-switches-disabled",
            "runtime-publisher-service-account",
            "runtime-publisher-no-user-managed-keys",
            "runtime-publisher-repository-writer",
            "runtime-publisher-workload-identity",
        ):
            self.assertIn(blocker, result["blocking_requirements"])
        self.assertFalse(result["ready_for_controlled_enablement"])

    def test_armed_pull_request_or_project_role_is_rejected(self):
        value = snapshot()
        value["pull_request"]["labels"] = [{"name": "tcc-runtime-publication"}]
        publisher_member = f"serviceAccount:{MODULE.RUNTIME_PUBLISHER_EMAIL}"
        value["project_policy"] = {
            "bindings": [{"role": "roles/viewer", "members": [publisher_member]}]
        }

        result = MODULE.audit(value, 1)

        self.assertIn(
            "pull-request-safe-disarmed-state", result["blocking_requirements"]
        )
        self.assertIn("runtime-publisher-no-project-role", result["blocking_requirements"])

    def test_unreadable_project_policy_fails_closed(self):
        value = snapshot()
        value["project_policy"] = None

        result = MODULE.audit(value, 1)

        self.assertIn("runtime-publisher-no-project-role", result["blocking_requirements"])

    def test_stale_workflow_or_broad_environment_branch_is_rejected(self):
        value = snapshot()
        value["workflow_on_default_branch_sha256"] = "0" * 64
        value["environment_branch_policies"]["branch_policies"].append(
            {"name": "feature/*"}
        )

        result = MODULE.audit(value, 1)

        self.assertIn(
            "workflow-installed-on-default-branch", result["blocking_requirements"]
        )
        self.assertIn(
            "protected-environment-branch-policy", result["blocking_requirements"]
        )

    def test_input_snapshot_is_not_mutated(self):
        value = snapshot()
        before = copy.deepcopy(value)

        MODULE.audit(value, 1)

        self.assertEqual(before, value)


if __name__ == "__main__":
    unittest.main()
