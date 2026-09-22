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


class AuditProtocolFreezeTests(unittest.TestCase):
    def test_current_candidate_reports_explicit_freeze_blockers(self):
        result = MODULE.audit(REPO_ROOT, protocol())

        self.assertFalse(result["ready_to_freeze"])
        self.assertIn("ci-policy-frozen", result["blocking_requirements"])
        self.assertIn("staging-thresholds-frozen", result["blocking_requirements"])
        self.assertIn("pdt-model-policy-frozen", result["blocking_requirements"])
        self.assertIn("pdt-fidelity-policy-frozen", result["blocking_requirements"])
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

    def test_publication_binding_identity_is_fail_closed(self):
        value = publication_binding()
        self.assertIsNotNone(MODULE.publication_binding_identity(value))

        value["protected_environment"] = "unprotected"
        self.assertIsNone(MODULE.publication_binding_identity(value))


if __name__ == "__main__":
    unittest.main()
