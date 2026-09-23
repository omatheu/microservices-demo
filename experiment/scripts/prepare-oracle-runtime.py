#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import pathlib
import re
import stat
import sys


IMMUTABLE_IMAGE = re.compile(r"^[a-z0-9.-]+/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$")
ALLOWED_TARGETS = {
    "checkoutservice",
    "currencyservice",
    "paymentservice",
    "recommendationservice",
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


def private_file(path):
    mode = stat.S_IMODE(pathlib.Path(path).stat().st_mode)
    return mode & 0o077 == 0


def strategic_merge(base, patch):
    if isinstance(base, dict) and isinstance(patch, dict):
        result = {key: value for key, value in base.items()}
        for key, value in patch.items():
            result[key] = strategic_merge(result.get(key), value)
        return result
    if isinstance(base, list) and isinstance(patch, list):
        if all(isinstance(item, dict) and "name" in item for item in patch):
            result = [item for item in base]
            by_name = {
                item.get("name"): index
                for index, item in enumerate(result)
                if isinstance(item, dict) and "name" in item
            }
            for item in patch:
                name = item["name"]
                if name in by_name:
                    index = by_name[name]
                    result[index] = strategic_merge(result[index], item)
                else:
                    by_name[name] = len(result)
                    result.append(item)
            return result
        return patch
    return patch


def workload(snapshot, name):
    matches = [
        item
        for item in snapshot.get("synchronized_state", {}).get("workloads", [])
        if item.get("name") == name
    ]
    if len(matches) != 1:
        raise ValueError(f"snapshot must contain exactly one {name} workload")
    return matches[0]


def artifact_map(control):
    artifacts = control.get("immutable_artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("conventional decision lacks immutable artifacts")
    result = {}
    for artifact in artifacts:
        component = artifact.get("component")
        image = artifact.get("remote_reference")
        if not component or component in result or not IMMUTABLE_IMAGE.fullmatch(str(image)):
            raise ValueError("conventional decision contains invalid immutable artifacts")
        result[component] = image
    return result


def service_account(name, namespace):
    return {
        "apiVersion": "v1",
        "kind": "ServiceAccount",
        "metadata": {"name": name, "namespace": namespace},
        "automountServiceAccountToken": False,
    }


def service(name, namespace, ports):
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": name, "namespace": namespace},
        "spec": {
            "type": "ClusterIP",
            "selector": {"app": name},
            "ports": ports,
        },
    }


def security_context():
    return {
        "allowPrivilegeEscalation": False,
        "capabilities": {"drop": ["ALL"]},
        "privileged": False,
        "readOnlyRootFilesystem": True,
    }


def deployment(name, namespace, image, env, ports, resources, replicas=1):
    if not IMMUTABLE_IMAGE.fullmatch(image):
        raise ValueError(f"{name} image is not immutable")
    container = {
        "name": "server",
        "image": image,
        "env": [{"name": key, "value": str(value)} for key, value in sorted(env.items())],
        "ports": [{"containerPort": port} for port in ports],
        "resources": resources,
        "securityContext": security_context(),
    }
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": {"app": name, "experiment-role": "oracle-runtime"},
        },
        "spec": {
            "replicas": replicas,
            "selector": {"matchLabels": {"app": name}},
            "template": {
                "metadata": {"labels": {"app": name, "experiment-role": "oracle-runtime"}},
                "spec": {
                    "serviceAccountName": name,
                    "automountServiceAccountToken": False,
                    "terminationGracePeriodSeconds": 5,
                    "securityContext": {
                        "fsGroup": 65532,
                        "runAsGroup": 65532,
                        "runAsNonRoot": True,
                        "runAsUser": 65532,
                    },
                    "containers": [container],
                },
            },
        },
    }


def environment_from_workload(value):
    containers = value.get("containers", [])
    if len(containers) != 1:
        raise ValueError(f"workload {value.get('name')} must contain one container")
    result = {}
    for entry in containers[0].get("env", []):
        if "value" in entry:
            result[entry["name"]] = entry["value"]
    return result


def resources_from_workload(value):
    containers = value.get("containers", [])
    if len(containers) != 1:
        raise ValueError(f"workload {value.get('name')} must contain one container")
    return containers[0].get("resources", {})


def same_namespace_network_policy(namespace):
    return [
        {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {"name": "oracle-deny-all", "namespace": namespace},
            "spec": {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]},
        },
        {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {"name": "oracle-runtime-internal-only", "namespace": namespace},
            "spec": {
                "podSelector": {"matchLabels": {"experiment-role": "oracle-runtime"}},
                "policyTypes": ["Ingress", "Egress"],
                "ingress": [
                    {
                        "from": [
                            {
                                "podSelector": {
                                    "matchLabels": {"experiment-role": "oracle-runtime"}
                                }
                            }
                        ]
                    }
                ],
                "egress": [
                    {
                        "to": [
                            {
                                "podSelector": {
                                    "matchLabels": {"experiment-role": "oracle-runtime"}
                                }
                            }
                        ]
                    },
                    {
                        "to": [
                            {
                                "namespaceSelector": {
                                    "matchLabels": {"kubernetes.io/metadata.name": "kube-system"}
                                },
                                "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}},
                            }
                        ],
                        "ports": [
                            {"port": 53, "protocol": "UDP"},
                            {"port": 53, "protocol": "TCP"},
                        ],
                    },
                ],
            },
        },
    ]


def prepare(
    work_item,
    candidate_definition,
    control,
    snapshot,
    alternative_id,
    harness_image,
    currency_reference_image,
    namespace="oracle",
):
    candidate_id = work_item.get("candidate_id")
    if candidate_definition.get("candidate_id") != candidate_id:
        raise ValueError("candidate definition and oracle work item differ")
    if control.get("candidate_id") != candidate_id or control.get("decision") not in {
        "approve",
        "block",
    }:
        raise ValueError("oracle runtime requires a sealed control for the same candidate")
    if control.get("control_decision_sealed") is not True:
        raise ValueError("conventional decision is not sealed")
    if control.get("decision") == "block" and control.get("staging", {}).get(
        "executed"
    ) is not True:
        raise ValueError(
            "a control-blocked candidate is deployable in the oracle only after staging executed"
        )
    if work_item.get("candidate_definition_sha256") != control.get(
        "candidate_definition_sha256"
    ):
        raise ValueError("oracle work item and control candidate definitions differ")
    target = work_item.get("target_component")
    if target not in ALLOWED_TARGETS:
        raise ValueError("oracle work item has an unsupported target component")
    if not IMMUTABLE_IMAGE.fullmatch(harness_image) or not IMMUTABLE_IMAGE.fullmatch(
        currency_reference_image
    ):
        raise ValueError("oracle harness and reference currency images must be immutable")

    alternatives = [
        item
        for item in candidate_definition.get("alternatives", [])
        if item.get("id") == alternative_id
    ]
    if len(alternatives) != 1 or alternatives[0].get("action") != "deploy":
        raise ValueError("oracle alternative must identify one deployable definition")
    alternative = alternatives[0]
    artifacts = artifact_map(control)
    if "checkoutservice" not in artifacts:
        raise ValueError("oracle runtime requires an immutable checkoutservice artifact")
    if target in {"currencyservice", "paymentservice"} and target not in artifacts:
        raise ValueError(f"oracle runtime lacks the immutable {target} candidate artifact")

    checkout_state = workload(snapshot, "checkoutservice")
    checkout_env = {
        "PORT": "5050",
        "PRODUCT_CATALOG_SERVICE_ADDR": "oracle-harness:5051",
        "SHIPPING_SERVICE_ADDR": "oracle-harness:5051",
        "PAYMENT_SERVICE_ADDR": "oracle-harness:5051",
        "EMAIL_SERVICE_ADDR": "oracle-harness:5051",
        "CURRENCY_SERVICE_ADDR": "oracle-harness:5051",
        "CART_SERVICE_ADDR": "oracle-harness:5051",
        "ENABLE_TRACING": "0",
        "ENABLE_PROFILER": "0",
    }
    checkout = deployment(
        "checkoutservice",
        namespace,
        artifacts["checkoutservice"],
        checkout_env,
        [5050],
        resources_from_workload(checkout_state),
        checkout_state.get("replicas", 1),
    )
    for change in alternative.get("configuration_changes", []):
        if change.get("deployment") != "checkoutservice":
            raise ValueError("oracle alternatives may configure only checkoutservice")
        checkout = strategic_merge(checkout, change.get("patch", {}))

    harness_env = {
        "CHECKOUT_SERVICE_ADDR": "checkoutservice:5050",
        "CURRENCY_REFERENCE_ADDR": "currency-reference:7000",
        "GRPC_PORT": "5051",
        "HTTP_PORT": "8080",
    }
    if target == "currencyservice":
        harness_env["CURRENCY_CANDIDATE_ADDR"] = "currency-candidate:7000"
    if target == "paymentservice":
        harness_env["PAYMENT_CANDIDATE_ADDR"] = "payment-candidate:50051"
    harness = deployment(
        "oracle-harness",
        namespace,
        harness_image,
        harness_env,
        [5051, 8080],
        {
            "requests": {"cpu": "100m", "memory": "64Mi"},
            "limits": {"cpu": "500m", "memory": "256Mi"},
        },
    )
    harness["spec"]["template"]["spec"]["containers"][0]["readinessProbe"] = {
        "httpGet": {"path": "/healthz", "port": 8080},
        "periodSeconds": 3,
        "timeoutSeconds": 1,
    }

    currency_state = workload(snapshot, "currencyservice")
    currency_reference = deployment(
        "currency-reference",
        namespace,
        currency_reference_image,
        environment_from_workload(currency_state),
        [7000],
        resources_from_workload(currency_state),
    )

    items = []
    for name in ("checkoutservice", "oracle-harness", "currency-reference"):
        items.append(service_account(name, namespace))
    items.extend(
        [
            service(
                "checkoutservice",
                namespace,
                [{"name": "grpc", "port": 5050, "targetPort": 5050}],
            ),
            service(
                "oracle-harness",
                namespace,
                [
                    {"name": "grpc", "port": 5051, "targetPort": 5051},
                    {"name": "http", "port": 8080, "targetPort": 8080},
                ],
            ),
            service(
                "currency-reference",
                namespace,
                [{"name": "grpc", "port": 7000, "targetPort": 7000}],
            ),
            checkout,
            harness,
            currency_reference,
        ]
    )

    if target == "currencyservice":
        candidate_state = workload(snapshot, "currencyservice")
        items.extend(
            [
                service_account("currency-candidate", namespace),
                service(
                    "currency-candidate",
                    namespace,
                    [{"name": "grpc", "port": 7000, "targetPort": 7000}],
                ),
                deployment(
                    "currency-candidate",
                    namespace,
                    artifacts["currencyservice"],
                    environment_from_workload(candidate_state),
                    [7000],
                    resources_from_workload(candidate_state),
                ),
            ]
        )
    if target == "paymentservice":
        candidate_state = workload(snapshot, "paymentservice")
        items.extend(
            [
                service_account("payment-candidate", namespace),
                service(
                    "payment-candidate",
                    namespace,
                    [{"name": "grpc", "port": 50051, "targetPort": 50051}],
                ),
                deployment(
                    "payment-candidate",
                    namespace,
                    artifacts["paymentservice"],
                    environment_from_workload(candidate_state),
                    [50051],
                    resources_from_workload(candidate_state),
                ),
            ]
        )
    items.extend(same_namespace_network_policy(namespace))

    return {
        "apiVersion": "v1",
        "kind": "List",
        "metadata": {
            "annotations": {
                "experiment.online-boutique.dev/candidate-id": candidate_id,
                "experiment.online-boutique.dev/alternative-id": alternative_id,
            }
        },
        "items": items,
    }


def write_json_exclusive(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
    except Exception:
        path.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-work-item", type=pathlib.Path, required=True)
    parser.add_argument("--candidate-definition", type=pathlib.Path, required=True)
    parser.add_argument("--conventional-decision", type=pathlib.Path, required=True)
    parser.add_argument("--snapshot", type=pathlib.Path, required=True)
    parser.add_argument("--alternative-id", required=True)
    parser.add_argument("--harness-image", required=True)
    parser.add_argument("--currency-reference-image", required=True)
    parser.add_argument("--namespace", default="oracle")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        if not private_file(args.private_work_item):
            raise ValueError("oracle work item must have private file permissions")
        candidate_definition_sha256 = sha256_file(args.candidate_definition)
        work_item = load(args.private_work_item)
        if work_item.get("candidate_definition_sha256") != candidate_definition_sha256:
            raise ValueError("candidate definition hash differs from the unlocked oracle work item")
        output = prepare(
            work_item,
            load(args.candidate_definition),
            load(args.conventional_decision),
            load(args.snapshot),
            args.alternative_id,
            args.harness_image,
            args.currency_reference_image,
            args.namespace,
        )
        write_json_exclusive(args.output, output)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"oracle runtime preparation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(args.output)


if __name__ == "__main__":
    main()
