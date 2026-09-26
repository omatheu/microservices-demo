import copy
import importlib.util
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = (
    REPO_ROOT
    / "experiment"
    / "scripts"
    / "validate-oracle-rbac-terraform-plan.py"
)
SPEC = importlib.util.spec_from_file_location(
    "validate_oracle_rbac_terraform_plan", SCRIPT
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def role_rules():
    return [
        {
            "api_groups": list(api_groups),
            "resource_names": None,
            "resources": list(resources),
            "verbs": list(verbs),
        }
        for api_groups, resources, verbs in sorted(MODULE.EXPECTED_ROLE_RULES)
    ]


def resource(address, resource_type, after, after_unknown):
    return {
        "address": address,
        "mode": "managed",
        "type": resource_type,
        "change": {
            "actions": ["create"],
            "before": None,
            "after": after,
            "after_unknown": after_unknown,
        },
    }


def plan():
    metadata = {
        "annotations": None,
        "generate_name": None,
        "labels": None,
        "name": MODULE.ORACLE_ROLE,
        "namespace": MODULE.ORACLE_NAMESPACE,
    }
    role_after = {"metadata": [copy.deepcopy(metadata)], "rule": role_rules()}
    binding_after = {
        "metadata": [copy.deepcopy(metadata)],
        "role_ref": [
            {
                "api_group": "rbac.authorization.k8s.io",
                "kind": "Role",
                "name": MODULE.ORACLE_ROLE,
            }
        ],
        "subject": [
            {
                "api_group": "rbac.authorization.k8s.io",
                "kind": "User",
                "name": MODULE.EXPERIMENT_SERVICE_ACCOUNT_EMAIL,
                "namespace": "default",
            }
        ],
    }
    metadata_expression = [
        {
            "name": {"constant_value": MODULE.ORACLE_ROLE},
            "namespace": {"references": [MODULE.NAMESPACE_REFERENCE]},
        }
    ]
    return {
        "terraform_version": "1.16.3",
        "configuration": {
            "root_module": {
                "resources": [
                    {
                        "address": MODULE.ROLE_CONFIGURATION_ADDRESS,
                        "expressions": {
                            "metadata": copy.deepcopy(metadata_expression),
                            "rule": [],
                        },
                    },
                    {
                        "address": MODULE.ROLE_BINDING_CONFIGURATION_ADDRESS,
                        "expressions": {
                            "metadata": copy.deepcopy(metadata_expression),
                            "role_ref": [
                                {
                                    "api_group": {
                                        "constant_value": "rbac.authorization.k8s.io"
                                    },
                                    "kind": {"constant_value": "Role"},
                                    "name": {
                                        "references": [MODULE.ROLE_REFERENCE]
                                    },
                                }
                            ],
                            "subject": [
                                {
                                    "api_group": {
                                        "constant_value": "rbac.authorization.k8s.io"
                                    },
                                    "kind": {"constant_value": "User"},
                                    "name": {
                                        "references": [MODULE.IDENTITY_REFERENCE]
                                    },
                                }
                            ],
                        },
                    },
                ]
            }
        },
        "resource_changes": [
            resource(
                MODULE.ROLE_ADDRESS,
                "kubernetes_role_v1",
                role_after,
                {"id": True, "metadata": [{}], "rule": [{}] * 7},
            ),
            resource(
                MODULE.ROLE_BINDING_ADDRESS,
                "kubernetes_role_binding_v1",
                binding_after,
                {
                    "id": True,
                    "metadata": [{}],
                    "role_ref": [{}],
                    "subject": [{}],
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


class ValidateOracleRbacTerraformPlanTests(unittest.TestCase):
    def test_exact_two_create_plan_passes_without_authorizing_apply(self):
        result = MODULE.validate(plan(), "1" * 64)

        self.assertEqual(10, result["check_count"])
        self.assertEqual(10, result["passed_count"])
        self.assertTrue(result["plan_matches_approved_scope"])
        self.assertEqual([], result["blocking_requirements"])
        self.assertFalse(result["terraform_apply_performed"])
        self.assertFalse(result["kubernetes_mutation_performed"])
        self.assertFalse(result["apply_authorized"])
        self.assertFalse(result["cost_authorized"])
        self.assertFalse(result["ongoing_billable_resources_added"])

    def test_additional_billable_resource_is_rejected(self):
        value = plan()
        value["resource_changes"].append(
            resource(
                "google_compute_instance.unexpected",
                "google_compute_instance",
                {},
                {},
            )
        )

        result = MODULE.validate(value, "2" * 64)

        self.assertIn("exact-oracle-rbac-change-set", result["blocking_requirements"])
        self.assertIn(
            "no-compute-storage-network-or-billable-resource",
            result["blocking_requirements"],
        )

    def test_update_broad_rule_or_wrong_subject_is_rejected(self):
        value = plan()
        value["resource_changes"][0]["change"]["actions"] = ["update"]
        value["resource_changes"][0]["change"]["before"] = {"id": "existing"}
        value["resource_changes"][0]["change"]["after"]["rule"].append(
            {
                "api_groups": [""],
                "resource_names": None,
                "resources": ["secrets"],
                "verbs": ["get"],
            }
        )
        value["resource_changes"][1]["change"]["after"]["subject"][0][
            "name"
        ] = "other@example.com"

        result = MODULE.validate(value, "3" * 64)

        self.assertIn("create-only-no-update-or-destroy", result["blocking_requirements"])
        self.assertIn("oracle-role-rules-are-exact", result["blocking_requirements"])
        self.assertIn("oracle-role-binding-is-exact", result["blocking_requirements"])

    def test_unknown_authorization_or_wrong_reference_is_rejected(self):
        value = plan()
        value["resource_changes"][0]["change"]["after_unknown"]["rule"] = [
            {"verbs": [True]}
        ]
        value["configuration"]["root_module"]["resources"][1]["expressions"][
            "subject"
        ][0]["name"]["references"] = ["google_service_account.other.email"]

        result = MODULE.validate(value, "4" * 64)

        self.assertIn(
            "authorization-values-known-before-apply",
            result["blocking_requirements"],
        )
        self.assertIn(
            "oracle-rbac-reference-graph-is-exact",
            result["blocking_requirements"],
        )

    def test_malformed_plan_and_digest_fail_closed(self):
        value = plan()
        value["resource_changes"].append({"address": "malformed"})

        result = MODULE.validate(value, "invalid")

        self.assertIn("terraform-plan-json-structure", result["blocking_requirements"])
        self.assertIn("terraform-plan-digest-recorded", result["blocking_requirements"])

    def test_input_plan_is_not_mutated(self):
        value = plan()
        before = copy.deepcopy(value)

        MODULE.validate(value, "5" * 64)

        self.assertEqual(before, value)


if __name__ == "__main__":
    unittest.main()
