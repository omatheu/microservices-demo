#!/usr/bin/env python3

"""Read-only audit of the GitHub/GCP controls required for runtime publication."""

import argparse
import base64
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys


REPOSITORY = "omatheu/microservices-demo"
PROJECT_ID = "microservices-demo-tcc"
ENVIRONMENT = "tcc-experiment"
WORKFLOW_PATH = ".github/workflows/tcc-pr-experiment.yaml"
REGISTRY_REPOSITORY = "online-boutique-experiment"
REGION = "us-central1"
RUNTIME_PUBLISHER_EMAIL = (
    "github-tcc-runtime-publisher@microservices-demo-tcc.iam.gserviceaccount.com"
)
REQUIRED_REVIEWER_LOGIN = "omatheu"
REQUIRED_DEPLOYMENT_BRANCH = "main"
REPOSITORY_PRINCIPAL = (
    "principalSet://iam.googleapis.com/projects/3042974916/locations/global/"
    "workloadIdentityPools/github-tcc-experiment/attribute.repository_id/1376372479"
)
REQUIRED_LABELS = {
    "tcc-cost-reviewed",
    "tcc-experiment-cloud",
    "tcc-runtime-publication",
}
REQUIRED_SECRETS = {
    "GCP_EXPERIMENT_SERVICE_ACCOUNT",
    "GCP_RUNTIME_PUBLISHER_SERVICE_ACCOUNT",
    "GCP_WORKLOAD_IDENTITY_PROVIDER",
}
REQUIRED_DISABLED_VARIABLES = {
    "TCC_COST_REVIEW_ACKNOWLEDGED": "false",
    "TCC_RUNTIME_PUBLICATION_ACKNOWLEDGED": "false",
}
AUTHORIZATION_LABELS = {
    "tcc-cost-reviewed",
    "tcc-experiment-cloud",
    "tcc-runtime-publication",
}
CANDIDATE_CHECK_IDS = {"pull-request-safe-disarmed-state"}


def command_json(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        return None, f"{pathlib.Path(command[0]).name} failed with exit {result.returncode}"
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


def collect(pull_request):
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

    repository = gh("repository", f"repos/{REPOSITORY}")
    labels = gh("labels", f"repos/{REPOSITORY}/labels?per_page=100")
    environment = gh(
        "environment", f"repos/{REPOSITORY}/environments/{ENVIRONMENT}"
    )
    environment_branch_policies = gh(
        "environment_branch_policies",
        f"repos/{REPOSITORY}/environments/{ENVIRONMENT}/deployment-branch-policies?per_page=100",
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
    local_workflow_path = pathlib.Path(__file__).resolve().parents[2] / WORKFLOW_PATH
    local_workflow_sha256 = hashlib.sha256(local_workflow_path.read_bytes()).hexdigest()
    pr = gh("pull_request", f"repos/{REPOSITORY}/pulls/{pull_request}")

    service_account = gcloud(
        "runtime_publisher_service_account",
        [
            "iam",
            "service-accounts",
            "describe",
            RUNTIME_PUBLISHER_EMAIL,
            "--project",
            PROJECT_ID,
        ],
    )
    service_account_policy = None
    user_managed_keys = None
    if service_account is not None:
        service_account_policy = gcloud(
            "runtime_publisher_service_account_policy",
            [
                "iam",
                "service-accounts",
                "get-iam-policy",
                RUNTIME_PUBLISHER_EMAIL,
                "--project",
                PROJECT_ID,
            ],
        )
        user_managed_keys = gcloud(
            "runtime_publisher_user_managed_keys",
            [
                "iam",
                "service-accounts",
                "keys",
                "list",
                "--iam-account",
                RUNTIME_PUBLISHER_EMAIL,
                "--managed-by=user",
                "--project",
                PROJECT_ID,
            ],
        )
    repository_policy = gcloud(
        "artifact_registry_policy",
        [
            "artifacts",
            "repositories",
            "get-iam-policy",
            REGISTRY_REPOSITORY,
            "--location",
            REGION,
            "--project",
            PROJECT_ID,
        ],
    )
    project_policy = gcloud(
        "project_policy",
        ["projects", "get-iam-policy", PROJECT_ID],
    )

    return {
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
        "runtime_publisher_service_account": service_account,
        "runtime_publisher_service_account_policy": service_account_policy,
        "runtime_publisher_user_managed_keys": user_managed_keys,
        "artifact_registry_policy": repository_policy,
        "project_policy": project_policy,
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


def all_policy_members(policy):
    if not isinstance(policy, dict):
        return set()
    return {
        member
        for binding in policy.get("bindings", [])
        if isinstance(binding, dict)
        for member in binding.get("members", [])
        if isinstance(member, str)
    }


def audit(snapshot, pull_request):
    checks = []

    def add(check_id, passed, detail):
        checks.append({"id": check_id, "passed": bool(passed), "detail": detail})

    repository = snapshot.get("repository")
    default_branch = repository.get("default_branch") if isinstance(repository, dict) else None
    add(
        "repository-default-branch",
        default_branch == "main",
        f"default_branch={default_branch or 'unavailable'}",
    )

    workflow = snapshot.get("workflow_on_default_branch")
    remote_workflow_sha256 = snapshot.get("workflow_on_default_branch_sha256")
    local_workflow_sha256 = snapshot.get("reviewed_local_workflow_sha256")
    workflow_ready = (
        isinstance(workflow, dict)
        and workflow.get("path") == WORKFLOW_PATH
        and isinstance(workflow.get("sha"), str)
        and bool(workflow["sha"])
        and isinstance(remote_workflow_sha256, str)
        and remote_workflow_sha256 == local_workflow_sha256
    )
    add(
        "workflow-installed-on-default-branch",
        workflow_ready,
        (
            f"reviewed_sha256={local_workflow_sha256}"
            if workflow_ready
            else (
                "workflow is absent from main"
                if not isinstance(workflow, dict)
                else "workflow content on main differs from the reviewed local workflow"
            )
        ),
    )

    labels = snapshot.get("labels")
    label_names = {
        item.get("name")
        for item in labels
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    } if isinstance(labels, list) else set()
    missing_labels = sorted(REQUIRED_LABELS - label_names)
    add(
        "required-labels-defined",
        not missing_labels,
        f"missing={missing_labels}",
    )

    environment = snapshot.get("environment")
    protection_rules = (
        environment.get("protection_rules", []) if isinstance(environment, dict) else []
    )
    reviewer_rules = [
        rule
        for rule in protection_rules
        if isinstance(rule, dict) and rule.get("type") == "required_reviewers"
    ]
    reviewer_logins = sorted(
        reviewer.get("reviewer", {}).get("login")
        for rule in reviewer_rules
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
    branch_restricted = (
        isinstance(branch_policy, dict)
        and branch_policy.get("custom_branch_policies") is True
    )
    environment_branch_policies = snapshot.get("environment_branch_policies")
    branch_names = {
        item.get("name")
        for item in environment_branch_policies.get("branch_policies", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    } if isinstance(environment_branch_policies, dict) else set()
    add(
        "protected-environment-branch-policy",
        branch_restricted and branch_names == {REQUIRED_DEPLOYMENT_BRANCH},
        (
            "custom_branch_policies="
            f"{branch_policy.get('custom_branch_policies') if isinstance(branch_policy, dict) else 'unavailable'}; "
            f"allowed_branches={sorted(branch_names)}"
        ),
    )

    secrets = snapshot.get("environment_secrets")
    secret_names = {
        item.get("name")
        for item in secrets.get("secrets", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    } if isinstance(secrets, dict) else set()
    missing_secrets = sorted(REQUIRED_SECRETS - secret_names)
    add(
        "protected-environment-secrets",
        not missing_secrets,
        f"missing={missing_secrets}",
    )

    variables = snapshot.get("environment_variables")
    variable_values = {
        item.get("name"): item.get("value")
        for item in variables.get("variables", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    } if isinstance(variables, dict) else {}
    invalid_variables = {
        name: variable_values.get(name)
        for name, expected in REQUIRED_DISABLED_VARIABLES.items()
        if variable_values.get(name) != expected
    }
    add(
        "financial-kill-switches-disabled",
        not invalid_variables,
        f"invalid_or_missing={invalid_variables}",
    )

    pr = snapshot.get("pull_request")
    pr_labels = {
        item.get("name")
        for item in pr.get("labels", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    } if isinstance(pr, dict) else set()
    armed_labels = sorted(AUTHORIZATION_LABELS & pr_labels)
    pr_safe = (
        isinstance(pr, dict)
        and pr.get("number") == pull_request
        and pr.get("state") == "open"
        and pr.get("draft") is False
        and pr.get("head", {}).get("repo", {}).get("full_name") == REPOSITORY
        and not armed_labels
    )
    add(
        "pull-request-safe-disarmed-state",
        pr_safe,
        (
            f"state={pr.get('state') if isinstance(pr, dict) else 'unavailable'}; "
            f"draft={pr.get('draft') if isinstance(pr, dict) else 'unavailable'}; "
            "head_repository="
            f"{pr.get('head', {}).get('repo', {}).get('full_name') if isinstance(pr, dict) else 'unavailable'}; "
            f"authorization_labels={armed_labels}"
        ),
    )

    service_account = snapshot.get("runtime_publisher_service_account")
    service_account_ready = (
        isinstance(service_account, dict)
        and service_account.get("email") == RUNTIME_PUBLISHER_EMAIL
        and service_account.get("disabled") is not True
    )
    add(
        "runtime-publisher-service-account",
        service_account_ready,
        "service account is active" if service_account_ready else "service account is absent",
    )

    user_keys = snapshot.get("runtime_publisher_user_managed_keys")
    no_user_keys = service_account_ready and isinstance(user_keys, list) and not user_keys
    add(
        "runtime-publisher-no-user-managed-keys",
        no_user_keys,
        f"user_managed_key_count={len(user_keys) if isinstance(user_keys, list) else 'unavailable'}",
    )

    publisher_member = f"serviceAccount:{RUNTIME_PUBLISHER_EMAIL}"
    writer_members = members_for_role(
        snapshot.get("artifact_registry_policy"), "roles/artifactregistry.writer"
    )
    add(
        "runtime-publisher-repository-writer",
        publisher_member in writer_members,
        f"repository_writer_bound={publisher_member in writer_members}",
    )

    project_policy = snapshot.get("project_policy")
    project_policy_known = isinstance(project_policy, dict)
    project_members = all_policy_members(project_policy)
    add(
        "runtime-publisher-no-project-role",
        project_policy_known and publisher_member not in project_members,
        (
            f"project_role_bound={publisher_member in project_members}"
            if project_policy_known
            else "project policy is unavailable"
        ),
    )

    federation_members = members_for_role(
        snapshot.get("runtime_publisher_service_account_policy"),
        "roles/iam.workloadIdentityUser",
    )
    federation_ready = REPOSITORY_PRINCIPAL in federation_members
    add(
        "runtime-publisher-workload-identity",
        federation_ready,
        f"repository_principal_bound={federation_ready}",
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
        "mechanism": "runtime-publication-readiness-audit",
        "repository": REPOSITORY,
        "project_id": PROJECT_ID,
        "environment": ENVIRONMENT,
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
        "collection_errors": snapshot.get("collection_errors", {}),
        "read_only": True,
        "cloud_mutation_performed": False,
        "github_mutation_performed": False,
        "publication_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pull-request", type=int, default=1)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    if args.pull_request <= 0:
        print("pull request number must be positive", file=sys.stderr)
        return 1
    result = audit(collect(args.pull_request), args.pull_request)
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
