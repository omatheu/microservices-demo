#!/usr/bin/env python3
"""Regression tests for cold-start probe hardening in experiment workloads."""

from pathlib import Path
import unittest

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MANIFESTS = (
    REPOSITORY_ROOT / "kubernetes-manifests" / "emailservice.yaml",
    REPOSITORY_ROOT / "kubernetes-manifests" / "recommendationservice.yaml",
    REPOSITORY_ROOT / "kustomize" / "base" / "emailservice.yaml",
    REPOSITORY_ROOT / "kustomize" / "base" / "recommendationservice.yaml",
)


def deployment_container(path: Path) -> dict:
    documents = yaml.safe_load_all(path.read_text(encoding="utf-8"))
    deployment = next(document for document in documents if document.get("kind") == "Deployment")
    return deployment["spec"]["template"]["spec"]["containers"][0]


class ExperimentProbeHardeningTests(unittest.TestCase):
    def test_python_services_get_a_bounded_grpc_startup_window(self):
        for manifest in MANIFESTS:
            with self.subTest(manifest=manifest.name):
                probe = deployment_container(manifest)["startupProbe"]
                self.assertEqual(probe["grpc"]["port"], 8080)
                self.assertEqual(probe["periodSeconds"], 5)
                self.assertEqual(probe["timeoutSeconds"], 5)
                self.assertEqual(probe["failureThreshold"], 24)

    def test_runtime_probes_tolerate_transient_autopilot_latency(self):
        for manifest in MANIFESTS:
            with self.subTest(manifest=manifest.name):
                container = deployment_container(manifest)
                for probe_name in ("readinessProbe", "livenessProbe"):
                    probe = container[probe_name]
                    self.assertEqual(probe["grpc"]["port"], 8080)
                    self.assertEqual(probe["periodSeconds"], 5)
                    self.assertEqual(probe["timeoutSeconds"], 5)
                    self.assertEqual(probe["failureThreshold"], 3)


if __name__ == "__main__":
    unittest.main()
