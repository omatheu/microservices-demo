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


class ValidateOracleSuiteTests(unittest.TestCase):
    def test_candidate_suite_files_are_bound_but_images_remain_pending(self):
        result = MODULE.validate(REPO_ROOT, manifest())

        self.assertEqual(result["file_count"], 21)
        self.assertIn(
            "experiment/scripts/validate-human-gate-receipt.py",
            {item["path"] for item in manifest()["files"]},
        )
        self.assertIn(
            "experiment/scripts/calculate-pdt-fidelity.py",
            {item["path"] for item in manifest()["files"]},
        )
        self.assertIn(
            "experiment/pdt/fidelity-policy.json",
            {item["path"] for item in manifest()["files"]},
        )
        self.assertFalse(result["images_ready"])
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


if __name__ == "__main__":
    unittest.main()
