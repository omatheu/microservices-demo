#!/usr/bin/env python3

import argparse
import importlib.util
import json
import pathlib
import re


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTROLLER_PATH = REPO_ROOT / "experiment/pdt/controller/checkout_pdt_controller.py"
SPEC = importlib.util.spec_from_file_location("checkout_pdt_controller", CONTROLLER_PATH)
CONTROLLER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(CONTROLLER)

IMAGE_PATTERN = re.compile(r"^[a-z0-9.-]+/[a-z0-9._/-]+@sha256:[a-f0-9]{64}$")


def safe_name(candidate_id, repetition):
    normalized = re.sub(r"[^a-z0-9-]+", "-", candidate_id.lower()).strip("-")
    normalized = normalized[:35].rstrip("-") or "candidate"
    return f"checkout-pdt-controller-{normalized}-r{repetition}"


def read_text(path):
    return pathlib.Path(path).read_text(encoding="utf-8")


def prepare(
    controller_image,
    candidate_path,
    conventional_path,
    snapshot_path,
    thresholds_path,
    model_policy_path,
    repetition,
):
    if not IMAGE_PATTERN.fullmatch(controller_image):
        raise ValueError("controller image must be an immutable registry digest")
    candidate = CONTROLLER.load(candidate_path)
    conventional = CONTROLLER.load(conventional_path)
    snapshot = CONTROLLER.load(snapshot_path)
    thresholds = CONTROLLER.load(thresholds_path)
    model_policy = CONTROLLER.load(model_policy_path)
    plan = CONTROLLER.build_execution_plan(
        candidate,
        CONTROLLER.sha256_file(candidate_path),
        conventional,
        CONTROLLER.sha256_file(conventional_path),
        snapshot,
        thresholds,
        CONTROLLER.sha256_file(thresholds_path),
        model_policy,
        CONTROLLER.sha256_file(model_policy_path),
        repetition,
    )
    name = safe_name(candidate["candidate_id"], repetition)
    labels = {
        "app.kubernetes.io/name": "checkout-pdt-controller",
        "app.kubernetes.io/component": "pdt-control-plane",
        "experiment-role": "pdt-controller",
        "candidate-id": candidate["candidate_id"],
    }
    data = {
        "candidate.json": read_text(candidate_path),
        "conventional-decision.json": read_text(conventional_path),
        "pdt-input-state.json": read_text(snapshot_path),
        "safety-thresholds.json": read_text(thresholds_path),
        "model-policy.json": read_text(model_policy_path),
        "expected-plan.json": json.dumps(plan, indent=2, sort_keys=True) + "\n",
    }
    if sum(len(key) + len(value) for key, value in data.items()) > 900_000:
        raise ValueError("controller input exceeds the safe ConfigMap size")

    service_account = {
        "apiVersion": "v1",
        "kind": "ServiceAccount",
        "metadata": {"name": "checkout-pdt-controller", "namespace": "pdt-system", "labels": labels},
        "automountServiceAccountToken": False,
    }
    config_map = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": name, "namespace": "pdt-system", "labels": labels},
        "immutable": True,
        "data": data,
    }
    network_policy = {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {"name": name, "namespace": "pdt-system", "labels": labels},
        "spec": {"podSelector": {"matchLabels": {"job-name": name}}, "policyTypes": ["Ingress", "Egress"]},
    }
    job = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": name, "namespace": "pdt-system", "labels": labels},
        "spec": {
            "backoffLimit": 0,
            "activeDeadlineSeconds": 300,
            "ttlSecondsAfterFinished": 600,
            "template": {
                "metadata": {"labels": {**labels, "job-name": name}},
                "spec": {
                    "serviceAccountName": "checkout-pdt-controller",
                    "automountServiceAccountToken": False,
                    "restartPolicy": "Never",
                    "securityContext": {
                        "runAsNonRoot": True,
                        "runAsUser": 10001,
                        "runAsGroup": 10001,
                        "fsGroup": 10001,
                        "seccompProfile": {"type": "RuntimeDefault"},
                    },
                    "containers": [
                        {
                            "name": "controller",
                            "image": controller_image,
                            "imagePullPolicy": "IfNotPresent",
                            "args": [
                                "plan",
                                "--candidate",
                                "/inputs/candidate.json",
                                "--conventional-decision",
                                "/inputs/conventional-decision.json",
                                "--snapshot",
                                "/inputs/pdt-input-state.json",
                                "--thresholds",
                                "/inputs/safety-thresholds.json",
                                "--model-policy",
                                "/inputs/model-policy.json",
                                "--repetition",
                                str(repetition),
                                "--output",
                                "-",
                            ],
                            "resources": {
                                "requests": {"cpu": "50m", "memory": "64Mi", "ephemeral-storage": "64Mi"},
                                "limits": {"cpu": "250m", "memory": "256Mi", "ephemeral-storage": "256Mi"},
                            },
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "capabilities": {"drop": ["ALL"]},
                                "privileged": False,
                                "readOnlyRootFilesystem": True,
                            },
                            "volumeMounts": [{"name": "inputs", "mountPath": "/inputs", "readOnly": True}],
                        }
                    ],
                    "volumes": [{"name": "inputs", "configMap": {"name": name}}],
                },
            },
        },
    }
    return {"apiVersion": "v1", "kind": "List", "items": [service_account, config_map, network_policy, job]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--controller-image", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--conventional-decision", required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--thresholds", required=True)
    parser.add_argument("--model-policy", required=True)
    parser.add_argument("--repetition", type=int, default=1)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare(
            args.controller_image,
            args.candidate,
            args.conventional_decision,
            args.snapshot,
            args.thresholds,
            args.model_policy,
            args.repetition,
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"PDT controller Job preparation failed: {error}") from error
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
