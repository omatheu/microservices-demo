import importlib.util
import json
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "audit-protocol-freeze.py"
PROTOCOL_PATH = REPO_ROOT / "experiment" / "protocol" / "protocol-v1.json"
SPEC = importlib.util.spec_from_file_location("audit_protocol_freeze", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def protocol():
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


class AuditProtocolFreezeTests(unittest.TestCase):
    def test_current_candidate_reports_explicit_freeze_blockers(self):
        result = MODULE.audit(REPO_ROOT, protocol())

        self.assertFalse(result["ready_to_freeze"])
        self.assertIn("ci-policy-frozen", result["blocking_requirements"])
        self.assertIn("staging-thresholds-frozen", result["blocking_requirements"])
        self.assertIn("pdt-model-policy-frozen", result["blocking_requirements"])
        self.assertIn("pdt-controller-image-bound", result["blocking_requirements"])
        self.assertIn("pdt-runtime-frozen", result["blocking_requirements"])
        self.assertIn("oracle-images-bound", result["blocking_requirements"])
        self.assertIn("researcher-approval", result["blocking_requirements"])
        self.assertIn("financial-review", result["blocking_requirements"])

    def test_current_candidate_passes_implemented_and_hashed_inputs(self):
        result = MODULE.audit(REPO_ROOT, protocol())
        checks = {item["id"]: item["passed"] for item in result["checks"]}

        self.assertTrue(checks["protocol-structure"])
        self.assertTrue(checks["collection-locked-before-freeze"])
        self.assertTrue(checks["frozen-input-hashes"])
        self.assertTrue(checks["mutation-operators-implemented"])
        self.assertTrue(checks["pdt-runtime-file-hashes"])
        self.assertTrue(checks["oracle-file-hashes"])

    def test_protocol_hash_drift_is_reported(self):
        value = protocol()
        value["frozen_inputs"]["ci_policy"]["sha256"] = "0" * 64

        result = MODULE.audit(REPO_ROOT, value)
        checks = {item["id"]: item["passed"] for item in result["checks"]}

        self.assertFalse(checks["frozen-input-hashes"])


if __name__ == "__main__":
    unittest.main()
