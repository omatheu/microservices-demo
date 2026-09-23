#!/usr/bin/env python3

import argparse
import datetime
import json
import os
import pathlib
import sys

import yaml


WORKLOAD_POD_PATHS = {
    "Pod": ("spec",),
    "Deployment": ("spec", "template", "spec"),
    "StatefulSet": ("spec", "template", "spec"),
    "DaemonSet": ("spec", "template", "spec"),
    "Job": ("spec", "template", "spec"),
    "CronJob": ("spec", "jobTemplate", "spec", "template", "spec"),
}


def load_json(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def nested(value, path):
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def resources_from_manifest(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        documents = list(yaml.safe_load_all(stream))
    resources = []
    for document in documents:
        if document is None:
            continue
        if not isinstance(document, dict):
            raise ValueError(f"{path} contains a non-object YAML document")
        if document.get("kind") == "List":
            items = document.get("items")
            if not isinstance(items, list):
                raise ValueError(f"{path} contains an invalid Kubernetes List")
            resources.extend(items)
        else:
            resources.append(document)
    return resources


def violation(path, resource, rule, detail, container=None):
    metadata = resource.get("metadata", {}) if isinstance(resource, dict) else {}
    result = {
        "manifest": str(path),
        "kind": resource.get("kind"),
        "namespace": metadata.get("namespace"),
        "name": metadata.get("name"),
        "rule": rule,
        "detail": detail,
    }
    if container is not None:
        result["container"] = container
    return result


def validate_container(path, resource, container, rules):
    name = container.get("name") if isinstance(container, dict) else None
    security = container.get("securityContext", {}) if isinstance(container, dict) else {}
    findings = []
    expectations = (
        ("privileged", False, "container-privileged", "privileged must be explicitly false"),
        (
            "allowPrivilegeEscalation",
            False,
            "container-privilege-escalation",
            "allowPrivilegeEscalation must be explicitly false",
        ),
        (
            "readOnlyRootFilesystem",
            True,
            "container-read-only-root",
            "readOnlyRootFilesystem must be explicitly true",
        ),
    )
    if rules.get("require_restricted_container_security_context") is True:
        for key, expected, rule, detail in expectations:
            if security.get(key) is not expected:
                findings.append(violation(path, resource, rule, detail, name))
        dropped = security.get("capabilities", {}).get("drop", [])
        if "ALL" not in dropped:
            findings.append(
                violation(
                    path,
                    resource,
                    "container-capabilities",
                    "capabilities.drop must include ALL",
                    name,
                )
            )
    if rules.get("forbid_host_port") is True:
        for port in container.get("ports", []) if isinstance(container, dict) else []:
            if port.get("hostPort") not in (None, 0):
                findings.append(
                    violation(
                        path,
                        resource,
                        "container-host-port",
                        "hostPort is forbidden",
                        name,
                    )
                )
    return findings


def validate_workload(path, resource, pod_spec, rules):
    findings = []
    if rules.get("require_run_as_non_root") is True:
        pod_security = pod_spec.get("securityContext", {})
        if pod_security.get("runAsNonRoot") is not True:
            findings.append(
                violation(
                    path,
                    resource,
                    "pod-run-as-non-root",
                    "pod securityContext.runAsNonRoot must be explicitly true",
                )
            )
    if rules.get("forbid_host_namespaces") is True:
        for key, rule in (
            ("hostNetwork", "pod-host-network"),
            ("hostPID", "pod-host-pid"),
            ("hostIPC", "pod-host-ipc"),
        ):
            if pod_spec.get(key) is True:
                findings.append(violation(path, resource, rule, f"{key} is forbidden"))
    if rules.get("forbid_host_path") is True:
        for volume in pod_spec.get("volumes", []) or []:
            if "hostPath" in volume:
                findings.append(
                    violation(
                        path,
                        resource,
                        "volume-host-path",
                        "hostPath volumes are forbidden",
                    )
                )
    for container in (pod_spec.get("initContainers", []) or []) + (
        pod_spec.get("containers", []) or []
    ):
        findings.extend(validate_container(path, resource, container, rules))
    return findings


def validate_resources(path, resources, rules):
    findings = []
    protected_namespaces = set(rules.get("protected_namespaces", []))
    forbidden_service_types = set(rules.get("forbidden_service_types", []))
    for resource in resources:
        if not isinstance(resource, dict):
            raise ValueError(f"{path} contains an invalid Kubernetes resource")
        kind = resource.get("kind")
        metadata = resource.get("metadata", {})
        if not kind or not isinstance(metadata, dict) or not metadata.get("name"):
            raise ValueError(f"{path} contains a resource without kind or metadata.name")
        namespace = metadata.get("namespace")
        if kind == "Service" and namespace in protected_namespaces:
            service_type = resource.get("spec", {}).get("type", "ClusterIP")
            if service_type in forbidden_service_types:
                findings.append(
                    violation(
                        path,
                        resource,
                        "service-public-exposure",
                        f"Service type {service_type} is forbidden in {namespace}",
                    )
                )
        pod_path = WORKLOAD_POD_PATHS.get(kind)
        if pod_path is not None:
            pod_spec = nested(resource, pod_path)
            if not isinstance(pod_spec, dict):
                raise ValueError(f"{path} contains {kind} without a valid pod spec")
            findings.extend(validate_workload(path, resource, pod_spec, rules))
    return findings


def validate(policy, manifest_paths):
    rules = policy.get("kubernetes_policy")
    if not isinstance(rules, dict):
        raise ValueError("CI policy lacks kubernetes_policy")
    expected_yaml = policy.get("tool_versions", {}).get("pyyaml")
    if expected_yaml != yaml.__version__:
        raise ValueError(
            f"PyYAML version differs from policy: expected {expected_yaml}, found {yaml.__version__}"
        )
    findings = []
    resource_count = 0
    for path in manifest_paths:
        resources = resources_from_manifest(path)
        resource_count += len(resources)
        findings.extend(validate_resources(path, resources, rules))
    if resource_count == 0:
        raise ValueError("Kubernetes policy received no resources")
    return {
        "schema_version": "1.0.0",
        "decision": "pass" if not findings else "block",
        "manifest_count": len(manifest_paths),
        "resource_count": resource_count,
        "violation_count": len(findings),
        "violations": findings,
    }


def write_json(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", type=pathlib.Path, action="append", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        result = validate(load_json(args.policy), args.manifest)
        result["generated_at"] = datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat().replace("+00:00", "Z")
        write_json(args.output, result)
    except (OSError, ValueError, TypeError, yaml.YAMLError, json.JSONDecodeError) as error:
        print(f"Kubernetes policy validation failed: {error}", file=sys.stderr)
        raise SystemExit(2) from error
    print(args.output)
    if result["decision"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
