import importlib.util
import json
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "validate-protocol-inputs.py"
PROTOCOL_PATH = REPO_ROOT / "experiment" / "protocol" / "protocol-v1.json"
SPEC = importlib.util.spec_from_file_location("validate_protocol_inputs", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def protocol():
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


class ValidateProtocolInputsTests(unittest.TestCase):
    def test_all_declared_inputs_match_their_files(self):
        result = MODULE.validate(REPO_ROOT, protocol())

        self.assertEqual(result["input_count"], 5)
        self.assertTrue(result["all_hashes_match"])

    def test_missing_required_input_is_rejected(self):
        value = protocol()
        del value["frozen_inputs"]["oracle_suite_manifest"]

        with self.assertRaisesRegex(ValueError, "incomplete"):
            MODULE.validate(REPO_ROOT, value)

    def test_hash_drift_is_rejected(self):
        value = protocol()
        value["frozen_inputs"]["ci_policy"]["sha256"] = "0" * 64

        with self.assertRaisesRegex(ValueError, "hash differs"):
            MODULE.validate(REPO_ROOT, value)


if __name__ == "__main__":
    unittest.main()
