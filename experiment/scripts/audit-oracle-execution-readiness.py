#!/usr/bin/env python3

"""Read-only audit of the controls required before an Oracle execution."""

import argparse
import base64
import datetime
import hashlib
import json
import pathlib
import re
import subprocess
import sys


REPOSITORY = "omatheu/microservices-demo"
PROJECT_ID = "microservices-demo-tcc"
ENVIRONMENT = "tcc-experiment"
WORKFLOW_PATH = ".github/workflows/tcc-pr-experiment.yaml"
KUBE_CONTEXT = "gke_microservices-demo-tcc_us-central1_online-boutique-experiment"
ORACLE_NAMESPACE = "oracle"
ORACLE_ROLE = "github-tcc-oracle-runner"
EXPERIMENT_SERVICE_ACCOUNT_EMAIL = (
    "github-tcc-experiment@microservices-demo-tcc.iam.gserviceaccount.com"
)
REQUIRED_REVIEWER_LOGIN = "omatheu"
REQUIRED_DEPLOYMENT_BRANCH = "main"
REPOSITORY_PRINCIPAL = (
    "principalSet://iam.googleapis.com/projects/3042974916/locations/global/"
    "workloadIdentityPools/github-tcc-experiment/attribute.repository_id/1376372479"
)
WORKLOAD_IDENTITY_PROVIDER = (
    "projects/3042974916/locations/global/workloadIdentityPools/"
    "github-tcc-experiment/providers/github-tcc"
)
PROVIDER_ATTRIBUTE_MAPPING = {
    "attribute.environment": "assertion.environment",
    "attribute.event_name": "assertion.event_name",
    "attribute.repository_id": "assertion.repository_id",
    "attribute.repository_owner_id": "assertion.repository_owner_id",
    "attribute.workflow_ref": "assertion.workflow_ref",
    "google.subject": "assertion.sub",
}
PROVIDER_ATTRIBUTE_CONDITION = " && ".join(
    [
        "assertion.repository_id == '1376372479'",
        "assertion.repository_owner_id == '124204749'",
        "assertion.environment == 'tcc-experiment'",
        "assertion.event_name == 'workflow_run'",
        "assertion.workflow_ref == "
        "'omatheu/microservices-demo/.github/workflows/"
        "tcc-pr-experiment.yaml@refs/heads/main'",
    ]
)
REQUIRED_PROJECT_ROLES = {
    "roles/container.clusterViewer",
    "roles/monitoring.viewer",
    "roles/serviceusage.serviceUsageConsumer",
}
REQUIRED_LABELS = {
    "tcc-cost-reviewed",
    "tcc-experiment-cloud",
    "tcc-oracle-cloud",
}
REQUIRED_SECRETS = {
    "GCP_EXPERIMENT_SERVICE_ACCOUNT",
    "GCP_WORKLOAD_IDENTITY_PROVIDER",
    "TCC_ORACLE_ARCHIVE_PASSPHRASE",
    "TCC_ORACLE_BLINDING_KEY_B64",
}
REQUIRED_DISABLED_VARIABLES = {
    "TCC_COST_REVIEW_ACKNOWLEDGED": "false",
    "TCC_ORACLE_EXECUTION_ACKNOWLEDGED": "false",
}
AUTHORIZATION_LABELS = set(REQUIRED_LABELS)
CANDIDATE_CHECK_IDS = {"pull-request-safe-disarmed-state"}
DIGEST = re.compile(r"^[a-f0-9]{64}$")
COMMIT = re.compile(r"^[a-f0-9]{40}$")
RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
OPAQUE_CANDIDATE = re.compile(r"^cand-[a-z2-7]{16}$")
PDT_IMAGE = re.compile(
    r"^us-central1-docker\.pkg\.dev/microservices-demo-tcc/"
    r"online-boutique-experiment/checkout-pdt-controller@sha256:[a-f0-9]{64}$"
)
ORACLE_IMAGES = {
    "oracle_harness": re.compile(
        r"^us-central1-docker\.pkg\.dev/microservices-demo-tcc/"
        r"online-boutique-experiment/oracle-harness@sha256:[a-f0-9]{64}$"
    ),
    "currency_reference": re.compile(
        r"^us-central1-docker\.pkg\.dev/microservices-demo-tcc/"
        r"online-boutique-experiment/currency-reference@sha256:[a-f0-9]{64}$"
    ),
}
ORACLE_ROLE_RULES = {
    (
        ("",),
        ("serviceaccounts", "services"),
        ("create", "delete", "get", "list", "patch", "update", "watch"),
    ),
    (
        ("",),
        ("events", "pods", "resourcequotas"),
        ("get", "list", "watch"),
    ),
    (("",), ("pods/log",), ("get",)),
    (("",), ("pods/portforward",), ("create",)),
    (
        ("apps",),
        ("deployments",),
        ("create", "delete", "get", "list", "patch", "update", "watch"),
    ),
    (("apps",), ("replicasets",), ("get", "list", "watch")),
    (
        ("networking.k8s.io",),
        ("networkpolicies",),
        ("create", "delete", "get", "list", "patch", "update", "watch"),
    ),
}
PUBLICATION_BINDING_KEYS = {
    "schema_version",
    "publication_summary_sha256",
    "repository",
    "source_commit",
    "source_tree",
    "pull_request_number",
    "workflow_run_id",
    "published_at",
    "build_platform",
    "protected_environment",
    "explicit_cloud_gate",
    "cost_review_acknowledged",
}


def load(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command_json(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        executable = pathlib.Path(command[0]).name
        return None, f"{executable} failed with exit {result.returncode}"
    try:
        return json.loads(result.stdout), None
    except json.JSONDecodeError as error:
        return None, f"invalid JSON: {error}"


def github_content_sha256(document):
    if not isinstance(document, dict) or document.get("encoding") != "base64":
        return None
    content = document.get("content")
    if not isinstance(content, str):
        return None
    try:
        decoded = base64.b64decode("".join(content.split()), validate=True)
    except (ValueError, base64.binascii.Error):
        return None
    return hashlib.sha256(decoded).hexdigest()


def collect(pull_request, repo_root):
    errors = {}

    def gh(name, endpoint):
        value, error = command_json(["gh", "api", endpoint])
        if error:
            errors[name] = error
        return value

    def gcloud(name, arguments):
        value, error = command_json(["gcloud", *arguments, "--format=json"])
        if error:
            errors[name] = error
        return value

    def kubectl(name, arguments, optional=False):
        command = [
            "kubectl",
            "--context",
            KUBE_CONTEXT,
            *arguments,
            "-o",
            "json",
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            if optional and "NotFound" in result.stderr:
                return None
            errors[name] = f"kubectl failed with exit {result.returncode}"
            return None
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            errors[name] = f"invalid JSON: {error}"
            return None

    def local_json(name, relative, optional=False):
        path = repo_root / relative
        try:
            return load(path)
        except FileNotFoundError:
            if optional:
                return None
            errors[name] = "local JSON unavailable: FileNotFoundError"
            return None
        except (OSError, json.JSONDecodeError) as error:
            errors[name] = f"local JSON unavailable: {error.__class__.__name__}"
            return None

    repository = gh("repository", f"repos/{REPOSITORY}")
    labels = gh("labels", f"repos/{REPOSITORY}/labels?per_page=100")
    environment = gh(
        "environment", f"repos/{REPOSITORY}/environments/{ENVIRONMENT}"
    )
    environment_branch_policies = gh(
        "environment_branch_policies",
        f"repos/{REPOSITORY}/environments/{ENVIRONMENT}/"
        "deployment-branch-policies?per_page=100",
    )
    secrets = gh(
        "environment_secrets",
        f"repos/{REPOSITORY}/environments/{ENVIRONMENT}/secrets?per_page=100",
    )
    variables = gh(
        "environment_variables",
        f"repos/{REPOSITORY}/environments/{ENVIRONMENT}/variables?per_page=100",
    )
    workflow = gh(
        "workflow_on_default_branch",
        f"repos/{REPOSITORY}/contents/{WORKFLOW_PATH}?ref=main",
    )
    workflow_path = repo_root / WORKFLOW_PATH
    try:
        local_workflow_sha256 = sha256_file(workflow_path)
    except OSError as error:
        errors["reviewed_local_workflow"] = (
            f"local workflow unavailable: {error.__class__.__name__}"
        )
        local_workflow_sha256 = None
    pr = gh("pull_request", f"repos/{REPOSITORY}/pulls/{pull_request}")

    service_account = gcloud(
        "experiment_service_account",
        [
            "iam",
            "service-accounts",
            "describe",
            EXPERIMENT_SERVICE_ACCOUNT_EMAIL,
            "--project",
            PROJECT_ID,
        ],
    )
    service_account_policy = None
    user_managed_keys = None
    if service_account is not None:
        service_account_policy = gcloud(
            "experiment_service_account_policy",
            [
                "iam",
                "service-accounts",
                "get-iam-policy",
                EXPERIMENT_SERVICE_ACCOUNT_EMAIL,
                "--project",
                PROJECT_ID,
            ],
        )
        user_managed_keys = gcloud(
            "experiment_user_managed_keys",
            [
                "iam",
                "service-accounts",
                "keys",
                "list",
                "--iam-account",
                EXPERIMENT_SERVICE_ACCOUNT_EMAIL,
                "--managed-by=user",
                "--project",
                PROJECT_ID,
            ],
        )
    project_policy = gcloud(
        "project_policy", ["projects", "get-iam-policy", PROJECT_ID]
    )
    provider = gcloud(
        "workload_identity_provider",
        [
            "iam",
            "workload-identity-pools",
            "providers",
            "describe",
            "github-tcc",
            "--workload-identity-pool=github-tcc-experiment",
            "--location=global",
            "--project",
            PROJECT_ID,
        ],
    )

    namespace = kubectl("oracle_namespace", ["get", "namespace", ORACLE_NAMESPACE])
    namespaced = ["--namespace", ORACLE_NAMESPACE, "get"]
    oracle_role = kubectl(
        "oracle_role", [*namespaced, "role", ORACLE_ROLE], optional=True
    )
    oracle_role_binding = kubectl(
        "oracle_role_binding",
        [*namespaced, "rolebinding", ORACLE_ROLE],
        optional=True,
    )
    oracle_resources = {
        resource: kubectl(
            f"oracle_{resource.replace('.', '_')}", [*namespaced, resource]
        )
        for resource in (
            "deployments.apps",
            "networkpolicies.networking.k8s.io",
            "pods",
            "serviceaccounts",
            "services",
        )
    }

    protocol_path = repo_root / "experiment/protocol/protocol-v1.json"
    return {
        "auditor_sha256": sha256_file(pathlib.Path(__file__)),
        "repository": repository,
        "labels": labels,
        "environment": environment,
        "environment_branch_policies": environment_branch_policies,
        "environment_secrets": secrets,
        "environment_variables": variables,
        "workflow_on_default_branch": workflow,
        "workflow_on_default_branch_sha256": github_content_sha256(workflow),
        "reviewed_local_workflow_sha256": local_workflow_sha256,
        "pull_request": pr,
        "experiment_service_account": service_account,
        "experiment_service_account_policy": service_account_policy,
        "experiment_user_managed_keys": user_managed_keys,
        "project_policy": project_policy,
        "workload_identity_provider": provider,
        "oracle_namespace": namespace,
        "oracle_role": oracle_role,
        "oracle_role_binding": oracle_role_binding,
        "oracle_resources": oracle_resources,
        "protocol": local_json("protocol", "experiment/protocol/protocol-v1.json"),
        "protocol_sha256": (
            sha256_file(protocol_path) if protocol_path.is_file() else None
        ),
        "pdt_runtime": local_json(
            "pdt_runtime", "experiment/pdt/runtime-manifest.json"
        ),
        "oracle_suite": local_json(
            "oracle_suite", "experiment/oracle/suite-manifest.json"
        ),
        "public_corpus": local_json(
            "public_corpus",
            "experiment/protocol/corpus/public-corpus.json",
            optional=True,
        ),
        "collection_errors": errors,
    }


def members_for_role(policy, role):
    if not isinstance(policy, dict):
        return set()
    return {
        member
        for binding in policy.get("bindings", [])
        if isinstance(binding, dict) and binding.get("role") == role
        for member in binding.get("members", [])
        if isinstance(member, str)
    }


def roles_for_member(policy, member):
    if not isinstance(policy, dict):
        return set()
    return {
        binding.get("role")
        for binding in policy.get("bindings", [])
        if isinstance(binding, dict) and member in binding.get("members", [])
    }


def canonical_role_rules(role):
    if not isinstance(role, dict) or not isinstance(role.get("rules"), list):
        return None
    result = set()
    for rule in role["rules"]:
        if not isinstance(rule, dict) or not all(
            isinstance(rule.get(field), list)
            and all(isinstance(value, str) for value in rule[field])
            for field in ("apiGroups", "resources", "verbs")
        ):
            return None
        if set(rule) - {"apiGroups", "resources", "verbs", "resourceNames"}:
            return None
        if "resourceNames" in rule:
            return None
        result.add(
            (
                tuple(sorted(rule["apiGroups"])),
                tuple(sorted(rule["resources"])),
                tuple(sorted(rule["verbs"])),
            )
        )
    return result


def publication_binding_ready(binding):
    return bool(
        isinstance(binding, dict)
        and set(binding) == PUBLICATION_BINDING_KEYS
        and binding.get("schema_version") == "1.0.0"
        and isinstance(binding.get("publication_summary_sha256"), str)
        and DIGEST.fullmatch(binding["publication_summary_sha256"])
        and binding.get("repository") == REPOSITORY
        and isinstance(binding.get("source_commit"), str)
        and COMMIT.fullmatch(binding["source_commit"])
        and isinstance(binding.get("source_tree"), str)
        and COMMIT.fullmatch(binding["source_tree"])
        and isinstance(binding.get("pull_request_number"), int)
        and not isinstance(binding["pull_request_number"], bool)
        and binding["pull_request_number"] > 0
        and isinstance(binding.get("workflow_run_id"), str)
        and binding["workflow_run_id"].isdigit()
        and int(binding["workflow_run_id"]) > 0
        and isinstance(binding.get("published_at"), str)
        and RFC3339.fullmatch(binding["published_at"])
        and binding.get("build_platform") == "linux/amd64"
        and binding.get("protected_environment") == ENVIRONMENT
        and binding.get("explicit_cloud_gate") is True
        and binding.get("cost_review_acknowledged") is True
    )


def runtime_artifacts_ready(pdt_runtime, oracle_suite):
    if not isinstance(pdt_runtime, dict) or not isinstance(oracle_suite, dict):
        return False
    images = oracle_suite.get("images")
    pdt_binding = pdt_runtime.get("publication_binding")
    oracle_binding = oracle_suite.get("publication_binding")
    return bool(
        pdt_runtime.get("status") == "frozen"
        and isinstance(pdt_runtime.get("frozen_at"), str)
        and RFC3339.fullmatch(pdt_runtime["frozen_at"])
        and isinstance(pdt_runtime.get("controller_image"), str)
        and PDT_IMAGE.fullmatch(pdt_runtime["controller_image"])
        and oracle_suite.get("status") == "frozen"
        and isinstance(oracle_suite.get("frozen_at"), str)
        and RFC3339.fullmatch(oracle_suite["frozen_at"])
        and isinstance(images, dict)
        and set(images) == set(ORACLE_IMAGES)
        and all(
            isinstance(images.get(name), str) and pattern.fullmatch(images[name])
            for name, pattern in ORACLE_IMAGES.items()
        )
        and publication_binding_ready(pdt_binding)
        and pdt_binding == oracle_binding
    )


def corpus_ready(protocol, protocol_sha256, corpus):
    if not isinstance(protocol, dict) or not isinstance(corpus, dict):
        return False
    design = protocol.get("research_design")
    order = corpus.get("execution_order")
    if not isinstance(design, dict) or not isinstance(order, list):
        return False
    candidate_count = design.get("candidate_count")
    repetitions = design.get("technical_repetitions_per_candidate")
    expected_repetitions = (
        list(range(1, repetitions + 1))
        if isinstance(repetitions, int)
        and not isinstance(repetitions, bool)
        and repetitions > 0
        else None
    )
    candidate_ids = [
        item.get("candidate_id") for item in order if isinstance(item, dict)
    ]
    return bool(
        isinstance(protocol_sha256, str)
        and DIGEST.fullmatch(protocol_sha256)
        and corpus.get("protocol_id") == protocol.get("protocol_id")
        and corpus.get("protocol_sha256") == protocol_sha256
        and corpus.get("confirmatory_eligible") is True
        and corpus.get("candidate_count") == candidate_count
        and corpus.get("technical_repetitions_per_candidate") == repetitions
        and isinstance(candidate_count, int)
        and not isinstance(candidate_count, bool)
        and len(order) == candidate_count
        and len(candidate_ids) == candidate_count
        and len(set(candidate_ids)) == candidate_count
        and all(
            isinstance(candidate_id, str)
            and OPAQUE_CANDIDATE.fullmatch(candidate_id)
            for candidate_id in candidate_ids
        )
        and all(
            set(item) == {"sequence", "candidate_id", "repetitions"}
            and item["sequence"] == index
            and item["repetitions"] == expected_repetitions
            for index, item in enumerate(order, start=1)
        )
    )


def audit(snapshot, pull_request):
    checks = []

    def add(check_id, passed, detail):
        checks.append({"id": check_id, "passed": bool(passed), "detail": detail})

    repository = snapshot.get("repository")
    default_branch = (
        repository.get("default_branch") if isinstance(repository, dict) else None
    )
    add(
        "repository-default-branch",
        default_branch == "main",
        f"default_branch={default_branch or 'unavailable'}",
    )

    workflow = snapshot.get("workflow_on_default_branch")
    remote_workflow_sha256 = snapshot.get("workflow_on_default_branch_sha256")
    local_workflow_sha256 = snapshot.get("reviewed_local_workflow_sha256")
    workflow_ready = bool(
        isinstance(workflow, dict)
        and workflow.get("path") == WORKFLOW_PATH
        and isinstance(workflow.get("sha"), str)
        and workflow["sha"]
        and isinstance(remote_workflow_sha256, str)
        and remote_workflow_sha256 == local_workflow_sha256
    )
    add(
        "workflow-installed-on-default-branch",
        workflow_ready,
        (
            f"reviewed_sha256={local_workflow_sha256}"
            if workflow_ready
            else "workflow content on main differs from the reviewed local workflow"
        ),
    )

    labels = snapshot.get("labels")
    label_names = (
        {
            item.get("name")
            for item in labels
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        if isinstance(labels, list)
        else set()
    )
    missing_labels = sorted(REQUIRED_LABELS - label_names)
    add("required-labels-defined", not missing_labels, f"missing={missing_labels}")

    environment = snapshot.get("environment")
    protection_rules = (
        environment.get("protection_rules", [])
        if isinstance(environment, dict)
        else []
    )
    reviewer_logins = sorted(
        reviewer.get("reviewer", {}).get("login")
        for rule in protection_rules
        if isinstance(rule, dict) and rule.get("type") == "required_reviewers"
        for reviewer in rule.get("reviewers", [])
        if isinstance(reviewer, dict)
        and isinstance(reviewer.get("reviewer"), dict)
        and isinstance(reviewer["reviewer"].get("login"), str)
    )
    add(
        "protected-environment-review",
        REQUIRED_REVIEWER_LOGIN in reviewer_logins,
        f"required_reviewer_logins={reviewer_logins}",
    )

    branch_policy = (
        environment.get("deployment_branch_policy")
        if isinstance(environment, dict)
        else None
    )
    policies = snapshot.get("environment_branch_policies")
    branch_names = (
        {
            item.get("name")
            for item in policies.get("branch_policies", [])
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        if isinstance(policies, dict)
        else set()
    )
    branch_ready = bool(
        isinstance(branch_policy, dict)
        and branch_policy.get("custom_branch_policies") is True
        and branch_names == {REQUIRED_DEPLOYMENT_BRANCH}
    )
    add(
        "protected-environment-branch-policy",
        branch_ready,
        f"allowed_branches={sorted(branch_names)}",
    )

    secrets = snapshot.get("environment_secrets")
    secret_names = (
        {
            item.get("name")
            for item in secrets.get("secrets", [])
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        if isinstance(secrets, dict)
        else set()
    )
    missing_secrets = sorted(REQUIRED_SECRETS - secret_names)
    add(
        "protected-environment-secrets",
        not missing_secrets,
        f"missing={missing_secrets}",
    )

    variables = snapshot.get("environment_variables")
    variable_values = (
        {
            item.get("name"): item.get("value")
            for item in variables.get("variables", [])
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        if isinstance(variables, dict)
        else {}
    )
    invalid_variables = {
        name: variable_values.get(name)
        for name, expected in REQUIRED_DISABLED_VARIABLES.items()
        if variable_values.get(name) != expected
    }
    add(
        "execution-kill-switches-disabled",
        not invalid_variables,
        f"invalid_or_missing={invalid_variables}",
    )

    pr = snapshot.get("pull_request")
    pr_labels = (
        {
            item.get("name")
            for item in pr.get("labels", [])
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        }
        if isinstance(pr, dict)
        else set()
    )
    armed_labels = sorted(AUTHORIZATION_LABELS & pr_labels)
    pr_safe = bool(
        isinstance(pr, dict)
        and pr.get("number") == pull_request
        and pr.get("state") == "open"
        and pr.get("draft") is False
        and pr.get("base", {}).get("ref") == "main"
        and pr.get("head", {}).get("repo", {}).get("full_name") == REPOSITORY
        and not armed_labels
    )
    add(
        "pull-request-safe-disarmed-state",
        pr_safe,
        (
            f"state={pr.get('state') if isinstance(pr, dict) else 'unavailable'}; "
            f"base={pr.get('base', {}).get('ref') if isinstance(pr, dict) else 'unavailable'}; "
            f"authorization_labels={armed_labels}"
        ),
    )

    service_account = snapshot.get("experiment_service_account")
    service_account_ready = bool(
        isinstance(service_account, dict)
        and service_account.get("email") == EXPERIMENT_SERVICE_ACCOUNT_EMAIL
        and service_account.get("disabled") is not True
    )
    add(
        "experiment-service-account",
        service_account_ready,
        "service account is active" if service_account_ready else "service account is absent",
    )

    user_keys = snapshot.get("experiment_user_managed_keys")
    no_user_keys = service_account_ready and isinstance(user_keys, list) and not user_keys
    add(
        "experiment-service-account-no-user-managed-keys",
        no_user_keys,
        "user_managed_key_count="
        f"{len(user_keys) if isinstance(user_keys, list) else 'unavailable'}",
    )

    federation_members = members_for_role(
        snapshot.get("experiment_service_account_policy"),
        "roles/iam.workloadIdentityUser",
    )
    federation_ready = federation_members == {REPOSITORY_PRINCIPAL}
    add(
        "experiment-service-account-workload-identity",
        federation_ready,
        f"repository_principal_exact={federation_ready}",
    )

    service_account_member = f"serviceAccount:{EXPERIMENT_SERVICE_ACCOUNT_EMAIL}"
    project_roles = roles_for_member(
        snapshot.get("project_policy"), service_account_member
    )
    project_roles_ready = project_roles == REQUIRED_PROJECT_ROLES
    add(
        "experiment-service-account-project-roles",
        project_roles_ready,
        f"roles={sorted(project_roles)}",
    )

    provider = snapshot.get("workload_identity_provider")
    provider_ready = bool(
        isinstance(provider, dict)
        and provider.get("name") == WORKLOAD_IDENTITY_PROVIDER
        and provider.get("state") == "ACTIVE"
        and provider.get("attributeMapping") == PROVIDER_ATTRIBUTE_MAPPING
        and provider.get("attributeCondition") == PROVIDER_ATTRIBUTE_CONDITION
        and provider.get("oidc", {}).get("issuerUri")
        == "https://token.actions.githubusercontent.com/"
    )
    add(
        "workload-identity-provider-restricted",
        provider_ready,
        "provider binding is exact" if provider_ready else "provider binding differs",
    )

    namespace = snapshot.get("oracle_namespace")
    namespace_labels = (
        namespace.get("metadata", {}).get("labels", {})
        if isinstance(namespace, dict)
        else {}
    )
    namespace_ready = bool(
        isinstance(namespace, dict)
        and namespace.get("metadata", {}).get("name") == ORACLE_NAMESPACE
        and namespace.get("status", {}).get("phase") == "Active"
        and namespace_labels.get("environment") == "oracle"
        and namespace_labels.get("experiment.online-boutique.dev/role")
        == "independent-outcome-adjudication"
    )
    add(
        "oracle-namespace-identity",
        namespace_ready,
        "namespace is active and labeled" if namespace_ready else "namespace differs",
    )

    oracle_role = snapshot.get("oracle_role")
    role_rules = canonical_role_rules(oracle_role)
    role_ready = bool(
        isinstance(oracle_role, dict)
        and oracle_role.get("metadata", {}).get("name") == ORACLE_ROLE
        and oracle_role.get("metadata", {}).get("namespace") == ORACLE_NAMESPACE
        and role_rules == ORACLE_ROLE_RULES
    )
    add(
        "oracle-role-least-privilege",
        role_ready,
        (
            f"rule_count={len(role_rules)}"
            if isinstance(role_rules, set)
            else "role is absent or invalid"
        ),
    )

    role_binding = snapshot.get("oracle_role_binding")
    binding_ready = bool(
        isinstance(role_binding, dict)
        and role_binding.get("metadata", {}).get("name") == ORACLE_ROLE
        and role_binding.get("metadata", {}).get("namespace") == ORACLE_NAMESPACE
        and role_binding.get("roleRef")
        == {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "Role",
            "name": ORACLE_ROLE,
        }
        and role_binding.get("subjects")
        == [
            {
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": "User",
                "name": EXPERIMENT_SERVICE_ACCOUNT_EMAIL,
                "namespace": "default",
            }
        ]
    )
    add(
        "oracle-role-binding-exact",
        binding_ready,
        "binding is exact" if binding_ready else "binding is absent or differs",
    )

    resources = snapshot.get("oracle_resources")
    resource_counts = {}
    quiescent = isinstance(resources, dict)
    if isinstance(resources, dict):
        for resource, document in resources.items():
            if not isinstance(document, dict) or not isinstance(document.get("items"), list):
                quiescent = False
                resource_counts[resource] = "unavailable"
                continue
            names = {
                item.get("metadata", {}).get("name")
                for item in document["items"]
                if isinstance(item, dict)
            }
            resource_counts[resource] = len(document["items"])
            if resource == "serviceaccounts":
                quiescent = quiescent and names == {"default"}
            else:
                quiescent = quiescent and not document["items"]
    add(
        "oracle-namespace-quiescent",
        quiescent,
        f"resource_counts={dict(sorted(resource_counts.items()))}",
    )

    protocol = snapshot.get("protocol")
    auditor_binding = (
        protocol.get("frozen_inputs", {}).get("oracle_execution_readiness_auditor")
        if isinstance(protocol, dict)
        else None
    )
    auditor_sha256 = snapshot.get("auditor_sha256")
    auditor_sealed = bool(
        isinstance(auditor_sha256, str)
        and DIGEST.fullmatch(auditor_sha256)
        and auditor_binding
        == {
            "path": "experiment/scripts/audit-oracle-execution-readiness.py",
            "sha256": auditor_sha256,
        }
    )
    add(
        "oracle-auditor-sealed-by-protocol",
        auditor_sealed,
        (
            f"auditor_sha256={auditor_sha256}"
            if auditor_sealed
            else "auditor hash is not bound by the protocol"
        ),
    )

    protocol_ready = bool(
        isinstance(protocol, dict)
        and protocol.get("status") == "frozen"
        and isinstance(protocol.get("frozen_at"), str)
        and RFC3339.fullmatch(protocol["frozen_at"])
        and protocol.get("confirmatory_collection_allowed") is True
    )
    add(
        "confirmatory-protocol-frozen",
        protocol_ready,
        f"status={protocol.get('status') if isinstance(protocol, dict) else 'unavailable'}",
    )

    artifacts_ready = runtime_artifacts_ready(
        snapshot.get("pdt_runtime"), snapshot.get("oracle_suite")
    )
    add(
        "confirmatory-runtimes-frozen",
        artifacts_ready,
        "shared immutable publication is bound" if artifacts_ready else "runtimes are not frozen",
    )

    final_corpus_ready = corpus_ready(
        protocol, snapshot.get("protocol_sha256"), snapshot.get("public_corpus")
    )
    add(
        "confirmatory-public-corpus-bound",
        final_corpus_ready,
        (
            "final corpus is protocol-bound"
            if final_corpus_ready
            else "final confirmatory corpus is absent or invalid"
        ),
    )

    collection_errors = snapshot.get("collection_errors")
    add(
        "collection-complete",
        isinstance(collection_errors, dict) and not collection_errors,
        "errors="
        f"{sorted(collection_errors) if isinstance(collection_errors, dict) else ['unavailable']}",
    )

    infrastructure_checks = [
        item for item in checks if item["id"] not in CANDIDATE_CHECK_IDS
    ]
    candidate_checks = [item for item in checks if item["id"] in CANDIDATE_CHECK_IDS]
    infrastructure_blockers = [
        item["id"] for item in infrastructure_checks if not item["passed"]
    ]
    candidate_blockers = [
        item["id"] for item in candidate_checks if not item["passed"]
    ]
    blockers = infrastructure_blockers + candidate_blockers
    return {
        "schema_version": "1.0.0",
        "mechanism": "oracle-execution-readiness-audit",
        "repository": REPOSITORY,
        "project_id": PROJECT_ID,
        "environment": ENVIRONMENT,
        "kube_context": KUBE_CONTEXT,
        "oracle_namespace": ORACLE_NAMESPACE,
        "pull_request_number": pull_request,
        "check_count": len(checks),
        "passed_count": len(checks) - len(blockers),
        "infrastructure_check_count": len(infrastructure_checks),
        "infrastructure_passed_count": len(infrastructure_checks)
        - len(infrastructure_blockers),
        "infrastructure_ready_for_candidate": not infrastructure_blockers,
        "infrastructure_blocking_requirements": infrastructure_blockers,
        "candidate_check_count": len(candidate_checks),
        "candidate_passed_count": len(candidate_checks) - len(candidate_blockers),
        "candidate_ready_for_controlled_enablement": not candidate_blockers,
        "candidate_blocking_requirements": candidate_blockers,
        "ready_for_controlled_enablement": not blockers,
        "blocking_requirements": blockers,
        "checks": checks,
        "evidence_bindings": {
            "auditor_sha256": snapshot.get("auditor_sha256"),
            "protocol_sha256": snapshot.get("protocol_sha256"),
            "reviewed_local_workflow_sha256": snapshot.get(
                "reviewed_local_workflow_sha256"
            ),
            "workflow_on_default_branch_sha256": snapshot.get(
                "workflow_on_default_branch_sha256"
            ),
        },
        "collection_errors": collection_errors,
        "read_only": True,
        "cloud_mutation_performed": False,
        "github_mutation_performed": False,
        "oracle_execution_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pull-request", type=int, required=True)
    parser.add_argument(
        "--repo-root",
        type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parents[2],
    )
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    if args.pull_request <= 0:
        print("pull request number must be positive", file=sys.stderr)
        return 1
    repo_root = args.repo_root.resolve()
    result = audit(collect(args.pull_request, repo_root), args.pull_request)
    result["captured_at"] = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    if args.require_ready and not result["ready_for_controlled_enablement"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
