import importlib.util
import json
import pathlib
import tempfile
import unittest

import yaml


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "validate-kubernetes-policy.py"
POLICY_PATH = REPO_ROOT / "experiment" / "ci" / "policy.json"
SPEC = importlib.util.spec_from_file_location("validate_kubernetes_policy", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def policy():
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def deployment(privileged=False, replicas=1):
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "checkoutservice", "namespace": "staging"},
        "spec": {
            "replicas": replicas,
            "selector": {"matchLabels": {"app": "checkoutservice"}},
            "template": {
                "metadata": {"labels": {"app": "checkoutservice"}},
                "spec": {
                    "securityContext": {"runAsNonRoot": True},
                    "containers": [
                        {
                            "name": "server",
                            "image": "example.invalid/checkout@sha256:" + "a" * 64,
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "capabilities": {"drop": ["ALL"]},
                                "privileged": privileged,
                                "readOnlyRootFilesystem": True,
                            },
                        }
                    ],
                },
            },
        },
    }


def validate_documents(*documents):
    with tempfile.TemporaryDirectory() as directory:
        manifest = pathlib.Path(directory) / "manifest.yaml"
        manifest.write_text(
            "\n---\n".join(yaml.safe_dump(item) for item in documents),
            encoding="utf-8",
        )
        return MODULE.validate(policy(), [manifest])


class ValidateKubernetesPolicyTests(unittest.TestCase):
    def test_restricted_workload_passes(self):
        result = validate_documents(deployment())

        self.assertEqual(result["decision"], "pass")
        self.assertEqual(result["violation_count"], 0)

    def test_privileged_container_is_blocked(self):
        result = validate_documents(deployment(privileged=True))

        self.assertEqual(result["decision"], "block")
        self.assertIn("container-privileged", {item["rule"] for item in result["violations"]})

    def test_public_service_in_staging_is_blocked(self):
        result = validate_documents(
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {"name": "frontend", "namespace": "staging"},
                "spec": {"type": "LoadBalancer"},
            }
        )

        self.assertEqual(result["decision"], "block")
        self.assertEqual(result["violations"][0]["rule"], "service-public-exposure")

    def test_public_operational_frontend_is_allowed(self):
        result = validate_documents(
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {"name": "frontend", "namespace": "operational"},
                "spec": {"type": "LoadBalancer"},
            }
        )

        self.assertEqual(result["decision"], "pass")

    def test_host_path_and_missing_restrictions_are_blocked(self):
        value = deployment()
        pod = value["spec"]["template"]["spec"]
        pod["volumes"] = [{"name": "host", "hostPath": {"path": "/"}}]
        del pod["containers"][0]["securityContext"]["capabilities"]

        result = validate_documents(value)
        rules = {item["rule"] for item in result["violations"]}

        self.assertIn("volume-host-path", rules)
        self.assertIn("container-capabilities", rules)


if __name__ == "__main__":
    unittest.main()
