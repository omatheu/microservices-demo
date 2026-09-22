import hashlib
import importlib.util
import json
import pathlib
import tempfile
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


def cost_evidence():
    return {
        "schema_version": "1.0.0",
        "observation_mode": "Cloud Billing Standard usage cost export",
        "project_id": "microservices-demo-tcc",
        "source": {
            "dataset_id": "online_boutique_billing",
            "location": "US",
            "table_id": "gcp_billing_export_v1_ABCDEF_0123",
            "maximum_bytes_billed": 100_000_000,
            "query_cache_enabled": True,
        },
        "window": {
            "start": "2026-09-19T00:00:00Z",
            "end": "2026-09-22T00:00:00Z",
        },
        "currency": "BRL",
        "gross_cost_brl": 12.34,
        "credits_brl": -12.34,
        "net_cost_brl": 0.0,
        "line_items": 10,
        "first_usage_start_time": "2026-09-19T00:00:00Z",
        "last_usage_end_time": "2026-09-21T23:59:59Z",
        "billing_data_as_of": "2026-09-22T00:30:00Z",
        "finalized_invoice_amount": False,
        "cloud_execution_authorized": False,
    }


def cost_review(binding):
    return {
        "schema_version": "1.0.0",
        "protocol_id": "checkout-pdt-comparison-v1",
        "project_id": "microservices-demo-tcc",
        "decision": "approved-for-protocol-freeze",
        "reviewed_at": "2026-09-22T01:00:00Z",
        "billing_data_as_of": "2026-09-22T00:30:00Z",
        "cost_data_available": True,
        "confirmatory_incremental_spend_brl": 12.34,
        "approved_incremental_spend_ceiling_brl": 200,
        "mandatory_review_at_brl": 150,
        "evidence": binding,
        "cloud_execution_authorized": False,
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

    def test_financial_review_requires_hash_bound_cost_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            evidence_path = root / "experiment/evidence/finance/cost-window.json"
            evidence_path.parent.mkdir(parents=True)
            evidence_path.write_text(json.dumps(cost_evidence()), encoding="utf-8")
            binding = {
                "path": "experiment/evidence/finance/cost-window.json",
                "sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
            }

            self.assertTrue(
                MODULE.validate_cost_review(root, protocol(), cost_review(binding))
            )

            tampered = cost_review(binding)
            tampered["confirmatory_incremental_spend_brl"] = 12.35
            self.assertFalse(MODULE.validate_cost_review(root, protocol(), tampered))

            wrong_hash = cost_review({**binding, "sha256": "0" * 64})
            self.assertFalse(MODULE.validate_cost_review(root, protocol(), wrong_hash))

    def test_readiness_snapshot_cannot_substitute_for_cost_observation(self):
        snapshot = (
            REPO_ROOT
            / "experiment/evidence/finance/protocol-freeze-readiness-20260922T013315Z.json"
        )
        binding = {
            "path": str(snapshot.relative_to(REPO_ROOT)),
            "sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        }

        self.assertFalse(
            MODULE.validate_cost_review(REPO_ROOT, protocol(), cost_review(binding))
        )


if __name__ == "__main__":
    unittest.main()
