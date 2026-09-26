import copy
import importlib.util
import json
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "validate-oracle-suite.py"
MANIFEST_PATH = REPO_ROOT / "experiment" / "oracle" / "suite-manifest.json"
SPEC = importlib.util.spec_from_file_location("validate_oracle_suite", SCRIPT_PATH)
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


class ValidateOracleSuiteTests(unittest.TestCase):
    def test_candidate_suite_files_are_bound_but_images_remain_pending(self):
        result = MODULE.validate(REPO_ROOT, manifest())

        self.assertEqual(result["file_count"], 27)
        self.assertIn(
            "experiment/scripts/bind-runtime-publication.py",
            {item["path"] for item in manifest()["files"]},
        )
        self.assertIn(
            "experiment/scripts/validate-oracle-suite.py",
            {item["path"] for item in manifest()["files"]},
        )
        self.assertIn(
            "experiment/scripts/validate-human-gate-receipt.py",
            {item["path"] for item in manifest()["files"]},
        )
        self.assertIn(
            "experiment/scripts/calculate-pdt-fidelity.py",
            {item["path"] for item in manifest()["files"]},
        )
        self.assertIn(
            "experiment/scripts/aggregate-pdt-fidelity.py",
            {item["path"] for item in manifest()["files"]},
        )
        self.assertIn(
            "experiment/pdt/fidelity-policy.json",
            {item["path"] for item in manifest()["files"]},
        )
        self.assertFalse(result["images_ready"])
        self.assertFalse(result["publication_bound"])
        self.assertFalse(result["frozen"])

    def test_file_hash_drift_is_rejected(self):
        value = manifest()
        value["files"][0]["sha256"] = "0" * 64

        with self.assertRaisesRegex(ValueError, "hash differs"):
            MODULE.validate(REPO_ROOT, value)

    def test_candidate_suite_cannot_satisfy_frozen_requirement(self):
        with self.assertRaisesRegex(ValueError, "not frozen"):
            MODULE.validate(REPO_ROOT, manifest(), require_frozen=True)

    def test_frozen_suite_requires_both_image_digests(self):
        value = copy.deepcopy(manifest())
        value["status"] = "frozen"

        with self.assertRaisesRegex(ValueError, "image digests"):
            MODULE.validate(REPO_ROOT, value)

    def test_candidate_images_require_attested_publication(self):
        value = manifest()
        prefix = (
            "us-central1-docker.pkg.dev/microservices-demo-tcc/"
            "online-boutique-experiment"
        )
        value["images"] = {
            "oracle_harness": f"{prefix}/oracle-harness@sha256:" + "d" * 64,
            "currency_reference": f"{prefix}/currency-reference@sha256:" + "e" * 64,
        }
        with self.assertRaisesRegex(ValueError, "publication binding"):
            MODULE.validate(REPO_ROOT, value)

        value["publication_binding"] = publication_binding()
        result = MODULE.validate(REPO_ROOT, value)
        self.assertTrue(result["images_ready"])
        self.assertTrue(result["publication_bound"])
        self.assertFalse(result["frozen"])

    def test_frozen_suite_requires_timestamp_after_image_binding(self):
        value = manifest()
        prefix = (
            "us-central1-docker.pkg.dev/microservices-demo-tcc/"
            "online-boutique-experiment"
        )
        value["status"] = "frozen"
        value["images"] = {
            "oracle_harness": f"{prefix}/oracle-harness@sha256:" + "d" * 64,
            "currency_reference": f"{prefix}/currency-reference@sha256:" + "e" * 64,
        }
        value["publication_binding"] = publication_binding()

        with self.assertRaisesRegex(ValueError, "freeze timestamp"):
            MODULE.validate(REPO_ROOT, value)


if __name__ == "__main__":
    unittest.main()
