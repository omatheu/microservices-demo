#!/usr/bin/env python3

"""Fail-closed validation for the runtime publisher Terraform plan."""

import argparse
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys


PROJECT_ID = "microservices-demo-tcc"
REGION = "us-central1"
REGISTRY_REPOSITORY = "online-boutique-experiment"
PUBLISHER_EMAIL = (
    "github-tcc-runtime-publisher@microservices-demo-tcc.iam.gserviceaccount.com"
)
PUBLISHER_MEMBER = f"serviceAccount:{PUBLISHER_EMAIL}"
REPOSITORY_PRINCIPAL = (
    "principalSet://iam.googleapis.com/projects/3042974916/locations/global/"
    "workloadIdentityPools/github-tcc-experiment/attribute.repository_id/1376372479"
)
EXPECTED_ADDRESSES = {
    "google_service_account.github_runtime_publisher[0]",
    "google_service_account_iam_member.github_runtime_publisher_federation[0]",
    "google_artifact_registry_repository_iam_member.github_runtime_publisher_writer[0]",
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


def after_matches(resource, expected_type, expected_values):
    if not isinstance(resource, dict) or resource.get("type") != expected_type:
        return False
    change = resource.get("change")
    if not isinstance(change, dict):
        return False
    after = change.get("after")
    if not isinstance(after, dict):
        return False
    return all(after.get(name) == value for name, value in expected_values.items())


def configuration_has_reference(resource, expression_name, expected_reference):
    if not isinstance(resource, dict):
        return False
    expressions = resource.get("expressions")
    if not isinstance(expressions, dict):
        return False
    expression = expressions.get(expression_name)
    if not isinstance(expression, dict):
        return False
    references = expression.get("references")
    return isinstance(references, list) and expected_reference in references


def validate(plan, plan_sha256):
    checks = []

    def add(check_id, passed, detail):
        checks.append({"id": check_id, "passed": bool(passed), "detail": detail})

    resource_changes = plan.get("resource_changes") if isinstance(plan, dict) else None
    structure_valid = isinstance(resource_changes, list) and all(
        isinstance(resource, dict)
        and isinstance(resource.get("address"), str)
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
            if isinstance(resource, dict)
            and isinstance(resource.get("change"), dict)
            and resource["change"].get("actions") != ["no-op"]
        ]
    addresses = [resource.get("address") for resource in changed]
    unique_addresses = {address for address in addresses if isinstance(address, str)}
    exact_change_set = (
        len(changed) == len(EXPECTED_ADDRESSES)
        and len(unique_addresses) == len(changed)
        and unique_addresses == EXPECTED_ADDRESSES
    )
    add(
        "exact-runtime-publisher-change-set",
        exact_change_set,
        f"changed_addresses={sorted(unique_addresses)}",
    )

    create_only = exact_change_set and all(
        resource.get("mode") == "managed"
        and resource.get("change", {}).get("actions") == ["create"]
        and resource.get("change", {}).get("before") is None
        for resource in changed
    )
    add(
        "create-only-no-update-or-destroy",
        create_only,
        f"actions={[resource.get('change', {}).get('actions') for resource in changed]}",
    )

    by_address = {
        resource.get("address"): resource
        for resource in changed
        if isinstance(resource.get("address"), str)
    }
    service_account_valid = after_matches(
        by_address.get("google_service_account.github_runtime_publisher[0]"),
        "google_service_account",
        {
            "account_id": "github-tcc-runtime-publisher",
            "project": PROJECT_ID,
            "email": PUBLISHER_EMAIL,
            "disabled": False,
        },
    )
    add(
        "keyless-runtime-publisher-identity",
        service_account_valid,
        f"publisher_email={PUBLISHER_EMAIL}",
    )

    writer_valid = after_matches(
        by_address.get(
            "google_artifact_registry_repository_iam_member.github_runtime_publisher_writer[0]"
        ),
        "google_artifact_registry_repository_iam_member",
        {
            "project": PROJECT_ID,
            "location": REGION,
            "repository": REGISTRY_REPOSITORY,
            "role": "roles/artifactregistry.writer",
            "member": PUBLISHER_MEMBER,
        },
    )
    add(
        "artifact-registry-repository-writer-only",
        writer_valid,
        f"scope={PROJECT_ID}/{REGION}/{REGISTRY_REPOSITORY}",
    )

    federation_valid = after_matches(
        by_address.get(
            "google_service_account_iam_member.github_runtime_publisher_federation[0]"
        ),
        "google_service_account_iam_member",
        {
            "role": "roles/iam.workloadIdentityUser",
            "member": REPOSITORY_PRINCIPAL,
        },
    )
    add(
        "repository-scoped-workload-identity",
        federation_valid,
        f"principal={REPOSITORY_PRINCIPAL}",
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
    federation_configuration = configuration_by_address.get(
        "google_service_account_iam_member.github_runtime_publisher_federation"
    )
    writer_configuration = configuration_by_address.get(
        "google_artifact_registry_repository_iam_member.github_runtime_publisher_writer"
    )
    reference_graph_valid = all(
        (
            configuration_has_reference(
                federation_configuration,
                "service_account_id",
                "google_service_account.github_runtime_publisher[0].name",
            ),
            configuration_has_reference(
                federation_configuration,
                "member",
                "google_iam_workload_identity_pool.github_experiment[0].name",
            ),
            configuration_has_reference(
                federation_configuration,
                "member",
                "var.github_repository_id",
            ),
            configuration_has_reference(
                writer_configuration,
                "member",
                "google_service_account.github_runtime_publisher[0].email",
            ),
            configuration_has_reference(
                writer_configuration,
                "repository",
                "google_artifact_registry_repository.experiment[0].repository_id",
            ),
            configuration_has_reference(
                writer_configuration,
                "location",
                "google_artifact_registry_repository.experiment[0].location",
            ),
        )
    )
    add(
        "isolated-runtime-publisher-reference-graph",
        reference_graph_valid,
        f"publisher_reference_graph_valid={reference_graph_valid}",
    )

    changed_types = {
        resource.get("type")
        for resource in changed
        if isinstance(resource.get("type"), str)
    }
    no_key_resource = "google_service_account_key" not in changed_types
    add(
        "no-service-account-key",
        no_key_resource,
        f"changed_types={sorted(changed_types)}",
    )

    allowed_types = {
        "google_service_account",
        "google_service_account_iam_member",
        "google_artifact_registry_repository_iam_member",
    }
    no_billable_resource = exact_change_set and changed_types <= allowed_types
    add(
        "no-compute-storage-or-network-resource-change",
        no_billable_resource,
        f"changed_types={sorted(changed_types)}",
    )

    blockers = [item["id"] for item in checks if not item["passed"]]
    return {
        "schema_version": "1.0.0",
        "mechanism": "runtime-publication-terraform-plan-validator",
        "project_id": PROJECT_ID,
        "terraform_version": plan.get("terraform_version") if isinstance(plan, dict) else None,
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
        "github_mutation_performed": False,
        "apply_authorized": False,
        "cost_authorized": False,
        "artifact_publication_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=pathlib.Path, required=True)
    parser.add_argument("--terraform-binary", default="terraform")
    parser.add_argument(
        "--terraform-directory", type=pathlib.Path, default=pathlib.Path("infra/terraform")
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
        print(f"runtime publication Terraform plan validation failed: {error}", file=sys.stderr)
        return 1
    result["validated_at"] = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
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
