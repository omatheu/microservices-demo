import importlib.util
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "prepare-runtime-publication-plan.py"
SPEC = importlib.util.spec_from_file_location("prepare_runtime_publication_plan", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


COMMIT = "1" * 40


def summary():
    return {
        "schema_version": "1.1.0",
        "source": {
            "repository": "omatheu/microservices-demo",
            "commit": COMMIT,
            "tree": "2" * 40,
            "pull_request_number": 1,
            "workflow_run_id": "1234",
        },
        "build_platform": "linux/amd64",
        "published_to_registry": False,
        "images": [
            {
                "name": name,
                "local_tag": f"online-boutique/{name}:pr-{COMMIT}",
                "image_id": f"sha256:{index}".ljust(71, str(index)),
                "size_bytes": size,
                "sbom": "pass",
                "scan": "pass",
            }
            for name, index, size in (
                ("checkout-pdt-controller", "1", 49_000_000),
                ("oracle-harness", "2", 16_000_000),
                ("currency-reference", "3", 165_000_000),
            )
        ],
    }


class PrepareRuntimePublicationPlanTests(unittest.TestCase):
    def test_plan_is_non_authorizing_and_conservative(self):
        result = MODULE.prepare_plan(
            summary(),
            COMMIT,
            8_000_000,
            "us-central1-docker.pkg.dev/microservices-demo-tcc/online-boutique-experiment",
        )

        self.assertEqual(result["decision"], "review-required-no-publication-authorized")
        self.assertFalse(result["cloud_execution_authorized"])
        storage = result["storage_assessment"]
        self.assertEqual(storage["additional_uncompressed_upper_bound_bytes"], 230_000_000)
        self.assertEqual(storage["projected_repository_upper_bound_bytes"], 238_000_000)
        self.assertTrue(storage["fits_if_allowance_is_unshared"])
        self.assertIsNone(storage["fits_billing_account_allowance"])
        self.assertIn(
            "billing-account-wide Artifact Registry storage is unavailable",
            result["review_blockers"],
        )

    def test_rejects_scan_failure(self):
        value = summary()
        value["images"][0]["scan"] = "fail"

        with self.assertRaisesRegex(ValueError, "vulnerability scan did not pass"):
            MODULE.prepare_plan(value, COMMIT, 0, "registry.example/project/repository")

    def test_rejects_commit_mismatch(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            MODULE.prepare_plan(summary(), "4" * 40, 0, "registry.example/project/repository")

    def test_rejects_missing_runtime_image(self):
        value = summary()
        value["images"].pop()

        with self.assertRaisesRegex(ValueError, "incomplete or unexpected"):
            MODULE.prepare_plan(value, COMMIT, 0, "registry.example/project/repository")


if __name__ == "__main__":
    unittest.main()
