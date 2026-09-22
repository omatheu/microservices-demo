import copy
import importlib.util
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = (
    REPO_ROOT
    / "experiment"
    / "scripts"
    / "validate-runtime-publication-terraform-plan.py"
)
SPEC = importlib.util.spec_from_file_location(
    "validate_runtime_publication_terraform_plan", SCRIPT
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def resource(address, resource_type, after):
    return {
        "address": address,
        "mode": "managed",
        "type": resource_type,
        "change": {
            "actions": ["create"],
            "before": None,
            "after": after,
        },
    }


def plan():
    return {
        "terraform_version": "1.16.3",
        "configuration": {
            "root_module": {
                "resources": [
                    {
                        "address": "google_service_account_iam_member.github_runtime_publisher_federation",
                        "expressions": {
                            "service_account_id": {
                                "references": [
                                    "google_service_account.github_runtime_publisher[0].name"
                                ]
                            },
                            "member": {
                                "references": [
                                    "google_iam_workload_identity_pool.github_experiment[0].name",
                                    "var.github_repository_id",
                                ]
                            },
                        },
                    },
                    {
                        "address": "google_artifact_registry_repository_iam_member.github_runtime_publisher_writer",
                        "expressions": {
                            "member": {
                                "references": [
                                    "google_service_account.github_runtime_publisher[0].email"
                                ]
                            },
                            "repository": {
                                "references": [
                                    "google_artifact_registry_repository.experiment[0].repository_id"
                                ]
                            },
                            "location": {
                                "references": [
                                    "google_artifact_registry_repository.experiment[0].location"
                                ]
                            },
                        },
                    },
                ]
            }
        },
        "resource_changes": [
            resource(
                "google_service_account.github_runtime_publisher[0]",
                "google_service_account",
                {
                    "account_id": "github-tcc-runtime-publisher",
                    "project": MODULE.PROJECT_ID,
                    "email": MODULE.PUBLISHER_EMAIL,
                    "disabled": False,
                },
            ),
            resource(
                "google_service_account_iam_member.github_runtime_publisher_federation[0]",
                "google_service_account_iam_member",
                {
                    "role": "roles/iam.workloadIdentityUser",
                    "member": MODULE.REPOSITORY_PRINCIPAL,
                },
            ),
            resource(
                "google_artifact_registry_repository_iam_member.github_runtime_publisher_writer[0]",
                "google_artifact_registry_repository_iam_member",
                {
                    "project": MODULE.PROJECT_ID,
                    "location": MODULE.REGION,
                    "repository": MODULE.REGISTRY_REPOSITORY,
                    "role": "roles/artifactregistry.writer",
                    "member": MODULE.PUBLISHER_MEMBER,
                },
            ),
            {
                "address": "google_container_cluster.experiment",
                "mode": "managed",
                "type": "google_container_cluster",
                "change": {"actions": ["no-op"], "before": {}, "after": {}},
            },
        ],
    }


class ValidateRuntimePublicationTerraformPlanTests(unittest.TestCase):
    def test_exact_three_create_plan_passes_without_authorizing_apply(self):
        result = MODULE.validate(plan(), "1" * 64)

        self.assertEqual(9, result["check_count"])
        self.assertEqual(9, result["passed_count"])
        self.assertTrue(result["plan_matches_approved_scope"])
        self.assertEqual([], result["blocking_requirements"])
        self.assertFalse(result["terraform_apply_performed"])
        self.assertFalse(result["apply_authorized"])
        self.assertFalse(result["cost_authorized"])

    def test_additional_compute_resource_is_rejected(self):
        value = plan()
        value["resource_changes"].append(
            resource("google_compute_instance.unexpected", "google_compute_instance", {})
        )

        result = MODULE.validate(value, "2" * 64)

        self.assertIn(
            "exact-runtime-publisher-change-set", result["blocking_requirements"]
        )
        self.assertIn(
            "no-compute-storage-or-network-resource-change",
            result["blocking_requirements"],
        )

    def test_update_destroy_or_wrong_binding_is_rejected(self):
        value = plan()
        value["resource_changes"][0]["change"]["actions"] = ["delete", "create"]
        value["resource_changes"][0]["change"]["before"] = {"id": "existing"}
        value["resource_changes"][1]["change"]["after"]["member"] = (
            "principalSet://iam.googleapis.com/untrusted"
        )
        value["resource_changes"][2]["change"]["after"]["role"] = "roles/owner"

        result = MODULE.validate(value, "3" * 64)

        self.assertIn("create-only-no-update-or-destroy", result["blocking_requirements"])
        self.assertIn(
            "repository-scoped-workload-identity", result["blocking_requirements"]
        )
        self.assertIn(
            "artifact-registry-repository-writer-only",
            result["blocking_requirements"],
        )

    def test_wrong_service_account_reference_or_malformed_entry_is_rejected(self):
        value = plan()
        value["configuration"]["root_module"]["resources"][0]["expressions"][
            "service_account_id"
        ]["references"] = ["google_service_account.github_experiment[0].name"]
        value["resource_changes"].append({"address": "malformed"})

        result = MODULE.validate(value, "5" * 64)

        self.assertIn("terraform-plan-json-structure", result["blocking_requirements"])
        self.assertIn(
            "isolated-runtime-publisher-reference-graph",
            result["blocking_requirements"],
        )

    def test_input_plan_is_not_mutated(self):
        value = plan()
        before = copy.deepcopy(value)

        MODULE.validate(value, "4" * 64)

        self.assertEqual(before, value)


if __name__ == "__main__":
    unittest.main()
