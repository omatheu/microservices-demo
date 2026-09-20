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


class ValidatePdtRuntimeTests(unittest.TestCase):
    def test_candidate_runtime_files_are_bound_but_image_is_pending(self):
        result = MODULE.validate(REPO_ROOT, manifest())

        self.assertEqual(result["runtime_id"], "checkout-pdt-controller-v1")
        self.assertEqual(result["file_count"], 11)
        self.assertFalse(result["image_ready"])
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


if __name__ == "__main__":
    unittest.main()
