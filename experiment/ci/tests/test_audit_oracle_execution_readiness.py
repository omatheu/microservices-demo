import copy
import hashlib
import importlib.util
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "experiment" / "scripts" / "audit-oracle-execution-readiness.py"
SPEC = importlib.util.spec_from_file_location("audit_oracle_execution_readiness", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def role_rules():
    return [
        {
            "apiGroups": list(api_groups),
            "resources": list(resources),
            "verbs": list(verbs),
        }
        for api_groups, resources, verbs in sorted(MODULE.ORACLE_ROLE_RULES)
    ]


def image(name):
    return (
        "us-central1-docker.pkg.dev/microservices-demo-tcc/"
        f"online-boutique-experiment/{name}@sha256:{'a' * 64}"
    )


def snapshot():
    workflow_sha256 = hashlib.sha256(
        (REPO_ROOT / MODULE.WORKFLOW_PATH).read_bytes()
    ).hexdigest()
    binding = {
        "schema_version": "1.0.0",
        "publication_summary_sha256": "b" * 64,
        "repository": MODULE.REPOSITORY,
        "source_commit": "1" * 40,
        "source_tree": "2" * 40,
        "pull_request_number": 4,
        "workflow_run_id": "1234",
        "published_at": "2026-09-26T11:00:00Z",
        "build_platform": "linux/amd64",
        "protected_environment": MODULE.ENVIRONMENT,
        "explicit_cloud_gate": True,
        "cost_review_acknowledged": True,
    }
    protocol_sha256 = "c" * 64
    protocol = {
        "protocol_id": "checkout-pdt-comparison-v1",
        "status": "frozen",
        "frozen_at": "2026-09-26T12:00:00Z",
        "confirmatory_collection_allowed": True,
        "research_design": {
            "candidate_count": 2,
            "technical_repetitions_per_candidate": 3,
        },
        "frozen_inputs": {
            "oracle_execution_readiness_auditor": {
                "path": "experiment/scripts/audit-oracle-execution-readiness.py",
                "sha256": hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
            }
        },
    }
    public_corpus = {
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": protocol_sha256,
        "confirmatory_eligible": True,
        "candidate_count": 2,
        "technical_repetitions_per_candidate": 3,
        "execution_order": [
            {
                "sequence": 1,
                "candidate_id": "cand-aaaaaaaaaaaaaaaa",
                "repetitions": [1, 2, 3],
            },
            {
                "sequence": 2,
                "candidate_id": "cand-bbbbbbbbbbbbbbbb",
                "repetitions": [1, 2, 3],
            },
        ],
    }
    return {
        "auditor_sha256": hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
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
            "number": 4,
            "state": "open",
            "draft": False,
            "base": {"ref": "main"},
            "head": {"repo": {"full_name": MODULE.REPOSITORY}},
            "labels": [],
        },
        "experiment_service_account": {
            "email": MODULE.EXPERIMENT_SERVICE_ACCOUNT_EMAIL,
            "disabled": False,
        },
        "experiment_service_account_policy": {
            "bindings": [
                {
                    "role": "roles/iam.workloadIdentityUser",
                    "members": [MODULE.REPOSITORY_PRINCIPAL],
                }
            ]
        },
        "experiment_user_managed_keys": [],
        "project_policy": {
            "bindings": [
                {
                    "role": role,
                    "members": [
                        f"serviceAccount:{MODULE.EXPERIMENT_SERVICE_ACCOUNT_EMAIL}"
                    ],
                }
                for role in sorted(MODULE.REQUIRED_PROJECT_ROLES)
            ]
        },
        "workload_identity_provider": {
            "name": MODULE.WORKLOAD_IDENTITY_PROVIDER,
            "state": "ACTIVE",
            "attributeMapping": copy.deepcopy(MODULE.PROVIDER_ATTRIBUTE_MAPPING),
            "attributeCondition": MODULE.PROVIDER_ATTRIBUTE_CONDITION,
            "oidc": {"issuerUri": "https://token.actions.githubusercontent.com/"},
        },
        "oracle_namespace": {
            "metadata": {
                "name": MODULE.ORACLE_NAMESPACE,
                "labels": {
                    "environment": "oracle",
                    "experiment.online-boutique.dev/role": (
                        "independent-outcome-adjudication"
                    ),
                },
            },
            "status": {"phase": "Active"},
        },
        "oracle_role": {
            "metadata": {
                "name": MODULE.ORACLE_ROLE,
                "namespace": MODULE.ORACLE_NAMESPACE,
            },
            "rules": role_rules(),
        },
        "oracle_role_binding": {
            "metadata": {
                "name": MODULE.ORACLE_ROLE,
                "namespace": MODULE.ORACLE_NAMESPACE,
            },
            "roleRef": {
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": "Role",
                "name": MODULE.ORACLE_ROLE,
            },
            "subjects": [
                {
                    "apiGroup": "rbac.authorization.k8s.io",
                    "kind": "User",
                    "name": MODULE.EXPERIMENT_SERVICE_ACCOUNT_EMAIL,
                }
            ],
        },
        "oracle_resources": {
            "deployments.apps": {"items": []},
            "networkpolicies.networking.k8s.io": {"items": []},
            "pods": {"items": []},
            "serviceaccounts": {"items": [{"metadata": {"name": "default"}}]},
            "services": {"items": []},
        },
        "protocol": protocol,
        "protocol_sha256": protocol_sha256,
        "pdt_runtime": {
            "status": "frozen",
            "frozen_at": "2026-09-26T11:00:00Z",
            "controller_image": image("checkout-pdt-controller"),
            "publication_binding": copy.deepcopy(binding),
        },
        "oracle_suite": {
            "status": "frozen",
            "frozen_at": "2026-09-26T11:00:00Z",
            "images": {
                "oracle_harness": image("oracle-harness"),
                "currency_reference": image("currency-reference"),
            },
            "publication_binding": copy.deepcopy(binding),
        },
        "public_corpus": public_corpus,
        "collection_errors": {},
    }


class AuditOracleExecutionReadinessTests(unittest.TestCase):
    def test_ready_state_is_safe_and_does_not_authorize_oracle(self):
        result = MODULE.audit(snapshot(), 4)

        self.assertEqual(22, result["check_count"])
        self.assertEqual(22, result["passed_count"])
        self.assertEqual(21, result["infrastructure_check_count"])
        self.assertEqual(21, result["infrastructure_passed_count"])
        self.assertTrue(result["infrastructure_ready_for_candidate"])
        self.assertEqual(1, result["candidate_check_count"])
        self.assertEqual(1, result["candidate_passed_count"])
        self.assertTrue(result["ready_for_controlled_enablement"])
        self.assertEqual([], result["blocking_requirements"])
        self.assertTrue(result["read_only"])
        self.assertFalse(result["cloud_mutation_performed"])
        self.assertFalse(result["github_mutation_performed"])
        self.assertFalse(result["oracle_execution_authorized"])

    def test_missing_oracle_controls_and_rbac_fail_closed(self):
        value = snapshot()
        value["labels"] = [
            item for item in value["labels"] if item["name"] != "tcc-oracle-cloud"
        ]
        value["environment_secrets"]["secrets"] = [
            item
            for item in value["environment_secrets"]["secrets"]
            if item["name"] != "TCC_ORACLE_BLINDING_KEY_B64"
        ]
        value["environment_variables"]["variables"] = [
            item
            for item in value["environment_variables"]["variables"]
            if item["name"] != "TCC_ORACLE_EXECUTION_ACKNOWLEDGED"
        ]
        value["oracle_role"] = None
        value["oracle_role_binding"] = None

        result = MODULE.audit(value, 4)

        for blocker in (
            "required-labels-defined",
            "protected-environment-secrets",
            "execution-kill-switches-disabled",
            "oracle-role-least-privilege",
            "oracle-role-binding-exact",
        ):
            self.assertIn(blocker, result["blocking_requirements"])
        self.assertFalse(result["ready_for_controlled_enablement"])

    def test_broad_role_wrong_binding_and_active_workload_are_rejected(self):
        value = snapshot()
        value["oracle_role"]["rules"].append(
            {"apiGroups": [""], "resources": ["secrets"], "verbs": ["get"]}
        )
        value["oracle_role"]["metadata"]["namespace"] = "operational"
        value["oracle_role_binding"]["subjects"][0]["name"] = "other@example.com"
        value["oracle_resources"]["pods"]["items"] = [
            {"metadata": {"name": "stale-oracle"}}
        ]

        result = MODULE.audit(value, 4)

        self.assertIn("oracle-role-least-privilege", result["blocking_requirements"])
        self.assertIn("oracle-role-binding-exact", result["blocking_requirements"])
        self.assertIn("oracle-namespace-quiescent", result["blocking_requirements"])

    def test_armed_pr_and_unfrozen_methodology_are_rejected(self):
        value = snapshot()
        value["pull_request"]["labels"] = [{"name": "tcc-oracle-cloud"}]
        value["protocol"]["status"] = "pre-registration-candidate"
        value["protocol"]["confirmatory_collection_allowed"] = False
        value["pdt_runtime"]["status"] = "pre-registration-candidate"
        value["public_corpus"] = None

        result = MODULE.audit(value, 4)

        self.assertIn(
            "pull-request-safe-disarmed-state", result["candidate_blocking_requirements"]
        )
        self.assertIn("confirmatory-protocol-frozen", result["blocking_requirements"])
        self.assertIn("confirmatory-runtimes-frozen", result["blocking_requirements"])
        self.assertIn("confirmatory-public-corpus-bound", result["blocking_requirements"])

    def test_broad_project_role_or_provider_condition_is_rejected(self):
        value = snapshot()
        value["project_policy"]["bindings"].append(
            {
                "role": "roles/owner",
                "members": [
                    f"serviceAccount:{MODULE.EXPERIMENT_SERVICE_ACCOUNT_EMAIL}"
                ],
            }
        )
        value["workload_identity_provider"]["attributeCondition"] = "true"

        result = MODULE.audit(value, 4)

        self.assertIn(
            "experiment-service-account-project-roles",
            result["blocking_requirements"],
        )
        self.assertIn(
            "workload-identity-provider-restricted",
            result["blocking_requirements"],
        )

    def test_incomplete_or_divergent_publication_binding_is_rejected(self):
        value = snapshot()
        value["pdt_runtime"]["publication_binding"] = {"repository": MODULE.REPOSITORY}

        result = MODULE.audit(value, 4)

        self.assertIn("confirmatory-runtimes-frozen", result["blocking_requirements"])

        value = snapshot()
        value["oracle_suite"]["publication_binding"]["source_tree"] = "3" * 40

        result = MODULE.audit(value, 4)

        self.assertIn("confirmatory-runtimes-frozen", result["blocking_requirements"])

    def test_unsealed_auditor_hash_is_rejected(self):
        value = snapshot()
        value["protocol"]["frozen_inputs"][
            "oracle_execution_readiness_auditor"
        ]["sha256"] = "0" * 64

        result = MODULE.audit(value, 4)

        self.assertIn(
            "oracle-auditor-sealed-by-protocol", result["blocking_requirements"]
        )

    def test_input_snapshot_is_not_mutated(self):
        value = snapshot()
        before = copy.deepcopy(value)

        MODULE.audit(value, 4)

        self.assertEqual(before, value)


if __name__ == "__main__":
    unittest.main()
