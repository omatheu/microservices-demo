import copy
import importlib.util
import json
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment/scripts/validate-pdt-runtime.py"
MANIFEST_PATH = REPO_ROOT / "experiment/pdt/runtime-manifest.json"
SPEC = importlib.util.spec_from_file_location("validate_pdt_runtime", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def publication_binding():
    return {
        "schema_version": "1.0.0",
        "publication_summary_sha256": "a" * 64,
        "repository": "omatheu/microservices-demo",
        "source_commit": "b" * 40,
        "source_tree": "c" * 40,
        "pull_request_number": 42,
        "workflow_run_id": "1234",
        "published_at": "2026-09-21T12:00:00Z",
        "build_platform": "linux/amd64",
        "protected_environment": "tcc-experiment",
        "explicit_cloud_gate": True,
        "cost_review_acknowledged": True,
    }


class ValidatePdtRuntimeTests(unittest.TestCase):
    def test_candidate_runtime_files_are_bound_but_image_is_pending(self):
        result = MODULE.validate(REPO_ROOT, manifest())

        self.assertEqual(result["runtime_id"], "checkout-pdt-controller-v1")
        self.assertEqual(result["file_count"], 15)
        self.assertIn(
            "experiment/scripts/bind-runtime-publication.py",
            {item["path"] for item in manifest()["files"]},
        )
        self.assertIn(
            "experiment/scripts/validate-pdt-runtime.py",
            {item["path"] for item in manifest()["files"]},
        )
        self.assertFalse(result["image_ready"])
        self.assertFalse(result["publication_bound"])
        self.assertFalse(result["frozen"])

    def test_runtime_hash_drift_is_rejected(self):
        value = manifest()
        value["files"][0]["sha256"] = "0" * 64

        with self.assertRaisesRegex(ValueError, "hash differs"):
            MODULE.validate(REPO_ROOT, value)

    def test_frozen_runtime_requires_controller_digest(self):
        value = copy.deepcopy(manifest())
        value["status"] = "frozen"

        with self.assertRaisesRegex(ValueError, "image digest"):
            MODULE.validate(REPO_ROOT, value)

    def test_candidate_image_requires_attested_publication(self):
        value = manifest()
        value["controller_image"] = (
            "us-central1-docker.pkg.dev/microservices-demo-tcc/"
            "online-boutique-experiment/checkout-pdt-controller@sha256:" + "d" * 64
        )
        with self.assertRaisesRegex(ValueError, "publication binding"):
            MODULE.validate(REPO_ROOT, value)

        value["publication_binding"] = publication_binding()
        result = MODULE.validate(REPO_ROOT, value)
        self.assertTrue(result["image_ready"])
        self.assertTrue(result["publication_bound"])
        self.assertFalse(result["frozen"])

    def test_frozen_runtime_requires_timestamp_after_image_binding(self):
        value = manifest()
        value["status"] = "frozen"
        value["controller_image"] = (
            "us-central1-docker.pkg.dev/microservices-demo-tcc/"
            "online-boutique-experiment/checkout-pdt-controller@sha256:" + "d" * 64
        )
        value["publication_binding"] = publication_binding()

        with self.assertRaisesRegex(ValueError, "freeze timestamp"):
            MODULE.validate(REPO_ROOT, value)


if __name__ == "__main__":
    unittest.main()
