import copy
import importlib.util
import json
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "bind-runtime-publication.py"
PDT_MANIFEST = REPO_ROOT / "experiment" / "pdt" / "runtime-manifest.json"
ORACLE_MANIFEST = REPO_ROOT / "experiment" / "oracle" / "suite-manifest.json"
SPEC = importlib.util.spec_from_file_location("bind_runtime_publication", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


SOURCE_COMMIT = "1" * 40
SOURCE_TREE = "2" * 40
SUMMARY_SHA256 = "3" * 64


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def summary():
    images = []
    for index, name in enumerate(
        ("checkout-pdt-controller", "oracle-harness", "currency-reference"),
        start=4,
    ):
        digest = f"sha256:{str(index) * 64}"
        images.append(
            {
                "name": name,
                "source_tag": (
                    f"{MODULE.REGISTRY_PREFIX}/{name}:git-{SOURCE_COMMIT}"
                ),
                "local_image_id": f"sha256:{str(index + 3) * 64}",
                "immutable_reference": (
                    f"{MODULE.REGISTRY_PREFIX}/{name}@{digest}"
                ),
                "registry_digest": digest,
                "uncompressed_size_bytes": index * 1_000_000,
                "sbom": "pass",
                "vulnerability_scan": "pass",
                "published": True,
            }
        )
    return {
        "schema_version": "1.0.0",
        "source": {
            "repository": "omatheu/microservices-demo",
            "commit": SOURCE_COMMIT,
            "tree": SOURCE_TREE,
            "pull_request_number": 42,
            "workflow_run_id": "987654",
        },
        "authorization": {
            "protected_environment": "tcc-experiment",
            "explicit_cloud_gate": True,
            "cost_review_acknowledged": True,
        },
        "build_platform": "linux/amd64",
        "published_at": "2026-09-21T12:00:00Z",
        "published_to_registry": True,
        "images": images,
    }


class BindRuntimePublicationTests(unittest.TestCase):
    def bind(self, value=None, pdt=None, oracle=None):
        return MODULE.bind(
            REPO_ROOT,
            value or summary(),
            SUMMARY_SHA256,
            pdt or load(PDT_MANIFEST),
            oracle or load(ORACLE_MANIFEST),
            SOURCE_COMMIT,
            SOURCE_TREE,
        )

    def test_binds_all_digests_without_freezing_or_mutating_cloud(self):
        original_pdt = load(PDT_MANIFEST)
        original_oracle = load(ORACLE_MANIFEST)
        pdt_before = copy.deepcopy(original_pdt)
        oracle_before = copy.deepcopy(original_oracle)

        pdt, oracle, receipt = self.bind(
            pdt=original_pdt, oracle=original_oracle
        )

        self.assertEqual("pre-registration-candidate", pdt["status"])
        self.assertIsNone(pdt["frozen_at"])
        self.assertRegex(pdt["controller_image"], r"@sha256:[a-f0-9]{64}$")
        self.assertRegex(
            oracle["images"]["oracle_harness"], r"@sha256:[a-f0-9]{64}$"
        )
        self.assertEqual(pdt["publication_binding"], oracle["publication_binding"])
        self.assertEqual(
            SUMMARY_SHA256,
            pdt["publication_binding"]["publication_summary_sha256"],
        )
        self.assertFalse(receipt["cloud_mutation_performed"])
        self.assertFalse(receipt["protocol_frozen"])
        self.assertEqual(pdt_before, original_pdt)
        self.assertEqual(oracle_before, original_oracle)

    def test_rejects_source_revision_mismatch(self):
        value = summary()
        value["source"]["tree"] = "9" * 40

        with self.assertRaisesRegex(ValueError, "tree differs"):
            self.bind(value=value)

    def test_rejects_mutable_or_wrong_registry_reference(self):
        value = summary()
        value["images"][0]["immutable_reference"] = (
            "us-central1-docker.pkg.dev/other/project/image:latest"
        )

        with self.assertRaisesRegex(ValueError, "reviewed registry"):
            self.bind(value=value)

    def test_rejects_scan_or_authorization_failure(self):
        value = summary()
        value["images"][1]["vulnerability_scan"] = "fail"
        with self.assertRaisesRegex(ValueError, "scan did not pass"):
            self.bind(value=value)

        value = summary()
        value["authorization"]["cost_review_acknowledged"] = False
        with self.assertRaisesRegex(ValueError, "authorization evidence"):
            self.bind(value=value)

    def test_refuses_to_replace_an_existing_binding(self):
        pdt = load(PDT_MANIFEST)
        pdt["publication_binding"] = {"already": "bound"}

        with self.assertRaisesRegex(ValueError, "already contains"):
            self.bind(pdt=pdt)


if __name__ == "__main__":
    unittest.main()
