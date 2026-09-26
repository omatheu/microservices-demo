#!/usr/bin/env python3

"""Fail-closed validation for the Oracle namespace RBAC Terraform plan."""

import argparse
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys


PROJECT_ID = "microservices-demo-tcc"
ORACLE_NAMESPACE = "oracle"
ORACLE_ROLE = "github-tcc-oracle-runner"
EXPERIMENT_SERVICE_ACCOUNT_EMAIL = (
    "github-tcc-experiment@microservices-demo-tcc.iam.gserviceaccount.com"
)
ROLE_ADDRESS = "kubernetes_role_v1.github_experiment_oracle_runner[0]"
ROLE_BINDING_ADDRESS = (
    "kubernetes_role_binding_v1.github_experiment_oracle_runner[0]"
)
EXPECTED_ADDRESSES = {ROLE_ADDRESS, ROLE_BINDING_ADDRESS}
ROLE_CONFIGURATION_ADDRESS = "kubernetes_role_v1.github_experiment_oracle_runner"
ROLE_BINDING_CONFIGURATION_ADDRESS = (
    "kubernetes_role_binding_v1.github_experiment_oracle_runner"
)
NAMESPACE_REFERENCE = (
    'kubernetes_namespace_v1.experiment["oracle"].metadata[0].name'
)
ROLE_REFERENCE = (
    "kubernetes_role_v1.github_experiment_oracle_runner[0].metadata[0].name"
)
IDENTITY_REFERENCE = "google_service_account.github_experiment[0].email"
EXPECTED_ROLE_RULES = {
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


def load_terraform_plan(path, terraform_binary, terraform_directory):
    result = subprocess.run(
        [
            terraform_binary,
            f"-chdir={pathlib.Path(terraform_directory).resolve()}",
            "show",
            "-json",
            str(pathlib.Path(path).resolve()),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(f"terraform show failed with exit {result.returncode}")
    return json.loads(result.stdout)


def sha256_file(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def singleton_block(document, key):
    value = document.get(key) if isinstance(document, dict) else None
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        return None
    return value[0]


def canonical_role_rules(rules):
    if not isinstance(rules, list):
        return None
    result = set()
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != {
            "api_groups",
            "resource_names",
            "resources",
            "verbs",
        }:
            return None
        if rule.get("resource_names") is not None:
            return None
        if not all(
            isinstance(rule.get(field), list)
            and all(isinstance(item, str) for item in rule[field])
            for field in ("api_groups", "resources", "verbs")
        ):
            return None
        result.add(
            (
                tuple(sorted(rule["api_groups"])),
                tuple(sorted(rule["resources"])),
                tuple(sorted(rule["verbs"])),
            )
        )
    return result


def expression_block(resource, block_name):
    expressions = resource.get("expressions") if isinstance(resource, dict) else None
    block = expressions.get(block_name) if isinstance(expressions, dict) else None
    if not isinstance(block, list) or len(block) != 1 or not isinstance(block[0], dict):
        return None
    return block[0]


def references(expression):
    if not isinstance(expression, dict):
        return set()
    value = expression.get("references")
    return set(value) if isinstance(value, list) else set()


def constant(expression):
    return expression.get("constant_value") if isinstance(expression, dict) else None


def contains_unknown_true(value):
    if value is True:
        return True
    if isinstance(value, dict):
        return any(contains_unknown_true(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_unknown_true(item) for item in value)
    return False


def validate(plan, plan_sha256):
    checks = []

    def add(check_id, passed, detail):
        checks.append({"id": check_id, "passed": bool(passed), "detail": detail})

    resource_changes = plan.get("resource_changes") if isinstance(plan, dict) else None
    structure_valid = isinstance(resource_changes, list) and all(
        isinstance(resource, dict)
        and isinstance(resource.get("address"), str)
        and isinstance(resource.get("type"), str)
        and isinstance(resource.get("change"), dict)
        and isinstance(resource["change"].get("actions"), list)
        for resource in resource_changes
    )
    add(
        "terraform-plan-json-structure",
        structure_valid,
        f"resource_change_count={len(resource_changes) if structure_valid else 'unavailable'}",
    )

    changed = []
    if structure_valid:
        changed = [
            resource
            for resource in resource_changes
            if resource["change"].get("actions") != ["no-op"]
        ]
    addresses = [resource.get("address") for resource in changed]
    unique_addresses = {address for address in addresses if isinstance(address, str)}
    exact_change_set = bool(
        len(changed) == len(EXPECTED_ADDRESSES)
        and len(unique_addresses) == len(changed)
        and unique_addresses == EXPECTED_ADDRESSES
    )
    add(
        "exact-oracle-rbac-change-set",
        exact_change_set,
        f"changed_addresses={sorted(unique_addresses)}",
    )

    create_only = exact_change_set and all(
        resource.get("mode") == "managed"
        and resource["change"].get("actions") == ["create"]
        and resource["change"].get("before") is None
        for resource in changed
    )
    add(
        "create-only-no-update-or-destroy",
        create_only,
        f"actions={[resource.get('change', {}).get('actions') for resource in changed]}",
    )

    by_address = {resource.get("address"): resource for resource in changed}
    role = by_address.get(ROLE_ADDRESS)
    role_after = role.get("change", {}).get("after") if isinstance(role, dict) else None
    role_metadata = singleton_block(role_after, "metadata")
    role_metadata_ready = bool(
        isinstance(role, dict)
        and role.get("type") == "kubernetes_role_v1"
        and isinstance(role_metadata, dict)
        and role_metadata.get("name") == ORACLE_ROLE
        and role_metadata.get("namespace") == ORACLE_NAMESPACE
        and role_metadata.get("labels") is None
        and role_metadata.get("annotations") is None
        and role_metadata.get("generate_name") is None
    )
    add(
        "oracle-role-target-is-exact",
        role_metadata_ready,
        f"target={ORACLE_NAMESPACE}/{ORACLE_ROLE}",
    )

    role_rules = canonical_role_rules(
        role_after.get("rule") if isinstance(role_after, dict) else None
    )
    role_rules_ready = role_rules == EXPECTED_ROLE_RULES
    add(
        "oracle-role-rules-are-exact",
        role_rules_ready,
        (
            f"rule_count={len(role_rules)}"
            if isinstance(role_rules, set)
            else "rules are unavailable or malformed"
        ),
    )

    binding = by_address.get(ROLE_BINDING_ADDRESS)
    binding_after = (
        binding.get("change", {}).get("after") if isinstance(binding, dict) else None
    )
    binding_metadata = singleton_block(binding_after, "metadata")
    role_ref = singleton_block(binding_after, "role_ref")
    subject = singleton_block(binding_after, "subject")
    binding_ready = bool(
        isinstance(binding, dict)
        and binding.get("type") == "kubernetes_role_binding_v1"
        and isinstance(binding_metadata, dict)
        and binding_metadata.get("name") == ORACLE_ROLE
        and binding_metadata.get("namespace") == ORACLE_NAMESPACE
        and binding_metadata.get("labels") is None
        and binding_metadata.get("annotations") is None
        and binding_metadata.get("generate_name") is None
        and role_ref
        == {
            "api_group": "rbac.authorization.k8s.io",
            "kind": "Role",
            "name": ORACLE_ROLE,
        }
        and subject
        == {
            "api_group": "rbac.authorization.k8s.io",
            "kind": "User",
            "name": EXPERIMENT_SERVICE_ACCOUNT_EMAIL,
            "namespace": "default",
        }
    )
    add(
        "oracle-role-binding-is-exact",
        binding_ready,
        f"subject={EXPERIMENT_SERVICE_ACCOUNT_EMAIL}",
    )

    role_unknown = (
        role.get("change", {}).get("after_unknown") if isinstance(role, dict) else None
    )
    binding_unknown = (
        binding.get("change", {}).get("after_unknown")
        if isinstance(binding, dict)
        else None
    )
    critical_values_known = bool(
        isinstance(role_unknown, dict)
        and isinstance(binding_unknown, dict)
        and not contains_unknown_true(role_unknown.get("rule"))
        and not contains_unknown_true(binding_unknown.get("role_ref"))
        and not contains_unknown_true(binding_unknown.get("subject"))
    )
    add(
        "authorization-values-known-before-apply",
        critical_values_known,
        f"critical_values_known={critical_values_known}",
    )

    configuration = plan.get("configuration") if isinstance(plan, dict) else None
    root_module = (
        configuration.get("root_module") if isinstance(configuration, dict) else None
    )
    configuration_resources = (
        root_module.get("resources", []) if isinstance(root_module, dict) else []
    )
    configuration_by_address = {
        resource.get("address"): resource
        for resource in configuration_resources
        if isinstance(resource, dict) and isinstance(resource.get("address"), str)
    }
    role_configuration = configuration_by_address.get(ROLE_CONFIGURATION_ADDRESS)
    binding_configuration = configuration_by_address.get(
        ROLE_BINDING_CONFIGURATION_ADDRESS
    )
    role_metadata_expression = expression_block(role_configuration, "metadata")
    binding_metadata_expression = expression_block(
        binding_configuration, "metadata"
    )
    role_ref_expression = expression_block(binding_configuration, "role_ref")
    subject_expression = expression_block(binding_configuration, "subject")
    reference_graph_ready = bool(
        NAMESPACE_REFERENCE
        in references(
            role_metadata_expression.get("namespace")
            if isinstance(role_metadata_expression, dict)
            else None
        )
        and constant(
            role_metadata_expression.get("name")
            if isinstance(role_metadata_expression, dict)
            else None
        )
        == ORACLE_ROLE
        and NAMESPACE_REFERENCE
        in references(
            binding_metadata_expression.get("namespace")
            if isinstance(binding_metadata_expression, dict)
            else None
        )
        and constant(
            binding_metadata_expression.get("name")
            if isinstance(binding_metadata_expression, dict)
            else None
        )
        == ORACLE_ROLE
        and ROLE_REFERENCE
        in references(
            role_ref_expression.get("name")
            if isinstance(role_ref_expression, dict)
            else None
        )
        and IDENTITY_REFERENCE
        in references(
            subject_expression.get("name")
            if isinstance(subject_expression, dict)
            else None
        )
    )
    add(
        "oracle-rbac-reference-graph-is-exact",
        reference_graph_ready,
        f"reference_graph_exact={reference_graph_ready}",
    )

    changed_types = {
        resource.get("type")
        for resource in changed
        if isinstance(resource.get("type"), str)
    }
    allowed_types = {"kubernetes_role_v1", "kubernetes_role_binding_v1"}
    no_billable_resources = exact_change_set and changed_types == allowed_types
    add(
        "no-compute-storage-network-or-billable-resource",
        no_billable_resources,
        f"changed_types={sorted(changed_types)}",
    )

    plan_digest_ready = (
        isinstance(plan_sha256, str)
        and len(plan_sha256) == 64
        and all(character in "0123456789abcdef" for character in plan_sha256)
    )
    add(
        "terraform-plan-digest-recorded",
        plan_digest_ready,
        f"plan_sha256={plan_sha256 if plan_digest_ready else 'invalid'}",
    )

    blockers = [item["id"] for item in checks if not item["passed"]]
    return {
        "schema_version": "1.0.0",
        "mechanism": "oracle-rbac-terraform-plan-validator",
        "project_id": PROJECT_ID,
        "namespace": ORACLE_NAMESPACE,
        "terraform_version": (
            plan.get("terraform_version") if isinstance(plan, dict) else None
        ),
        "plan_sha256": plan_sha256,
        "expected_change_count": len(EXPECTED_ADDRESSES),
        "observed_change_count": len(changed),
        "check_count": len(checks),
        "passed_count": len(checks) - len(blockers),
        "plan_matches_approved_scope": not blockers,
        "blocking_requirements": blockers,
        "checks": checks,
        "read_only_validation": True,
        "terraform_apply_performed": False,
        "gcp_mutation_performed": False,
        "kubernetes_mutation_performed": False,
        "github_mutation_performed": False,
        "apply_authorized": False,
        "cost_authorized": False,
        "ongoing_billable_resources_added": False,
        "oracle_execution_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=pathlib.Path, required=True)
    parser.add_argument("--terraform-binary", default="terraform")
    parser.add_argument(
        "--terraform-directory",
        type=pathlib.Path,
        default=pathlib.Path("infra/terraform"),
    )
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument("--require-safe", action="store_true")
    args = parser.parse_args()
    try:
        result = validate(
            load_terraform_plan(
                args.plan, args.terraform_binary, args.terraform_directory
            ),
            sha256_file(args.plan),
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Oracle RBAC Terraform plan validation failed: {error}", file=sys.stderr)
        return 1
    result["validated_at"] = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    result["validator_sha256"] = sha256_file(pathlib.Path(__file__))
    configuration_path = args.terraform_directory / "github-actions.tf"
    result["terraform_configuration"] = {
        "path": "infra/terraform/github-actions.tf",
        "sha256": sha256_file(configuration_path),
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    if args.require_safe and not result["plan_matches_approved_scope"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
