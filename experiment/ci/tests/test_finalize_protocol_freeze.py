import copy
import importlib.util
import json
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "finalize-protocol-freeze.py"
PROTOCOL_PATH = REPO_ROOT / "experiment" / "protocol" / "protocol-v1.json"
SPEC = importlib.util.spec_from_file_location("finalize_protocol_freeze", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


CANDIDATE_SHA256 = "a" * 64
FROZEN_AT = "2026-09-22T06:00:00Z"


def protocol():
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


def audit_result():
    checks = [
        {"id": check_id, "passed": True, "detail": "test"}
        for check_id in sorted(MODULE.REQUIRED_AUDIT_CHECKS)
    ]
    return {
        "protocol_id": "checkout-pdt-comparison-v1",
        "protocol_sha256": CANDIDATE_SHA256,
        "ready_to_freeze": True,
        "passed_count": len(checks),
        "check_count": len(checks),
        "blocking_requirements": [],
        "checks": checks,
    }


def researcher_approval():
    return {
        "schema_version": "1.0.0",
        "protocol_id": "checkout-pdt-comparison-v1",
        "candidate_protocol_sha256": CANDIDATE_SHA256,
        "decision": "approve-protocol-freeze",
        "approved_by": "researcher",
        "approved_at": "2026-09-22T05:00:00Z",
        "cloud_execution_authorized": False,
        "acknowledgements": {
            "protocol_reviewed": True,
            "no_confirmatory_outcomes_observed": True,
            "changes_require_new_protocol_version": True,
        },
    }


def cost_review():
    return {
        "schema_version": "1.0.0",
        "protocol_id": "checkout-pdt-comparison-v1",
        "project_id": "microservices-demo-tcc",
        "decision": "approved-for-protocol-freeze",
        "reviewed_at": "2026-09-22T05:30:00Z",
        "billing_data_as_of": "2026-09-22T05:00:00Z",
        "cost_data_available": True,
        "confirmatory_incremental_spend_brl": 12.34,
        "approved_incremental_spend_ceiling_brl": 200,
        "mandatory_review_at_brl": 150,
        "evidence": {
            "path": "experiment/evidence/finance/cost-window.json",
            "sha256": "b" * 64,
        },
        "cloud_execution_authorized": False,
    }


def binding(path, digest):
    return {"path": path, "sha256": digest}


def component_times():
    return {path: "2026-09-22T04:00:00Z" for path in MODULE.COMPONENT_PATHS}


class FinalizeProtocolFreezeTests(unittest.TestCase):
    def finalize(self, **overrides):
        values = {
            "protocol": protocol(),
            "candidate_protocol_sha256": CANDIDATE_SHA256,
            "audit_result": audit_result(),
            "researcher_approval": researcher_approval(),
            "researcher_binding": binding(
                "experiment/protocol/approvals/researcher-approval-v1.json",
                "c" * 64,
            ),
            "cost_review": cost_review(),
            "cost_binding": binding(
                "experiment/protocol/approvals/cost-review-v1.json", "d" * 64
            ),
            "component_frozen_at": component_times(),
            "frozen_at": FROZEN_AT,
        }
        values.update(overrides)
        return MODULE.finalize(**values)

    def test_produces_a_non_authorizing_frozen_protocol_proposal(self):
        source = protocol()
        before = copy.deepcopy(source)

        frozen_content, audit_content, receipt = self.finalize(protocol=source)
        frozen = json.loads(frozen_content.decode())

        self.assertEqual("frozen", frozen["status"])
        self.assertEqual(FROZEN_AT, frozen["frozen_at"])
        self.assertTrue(frozen["confirmatory_collection_allowed"])
        self.assertEqual(
            "explicit-user-authorization-required-after-freeze",
            frozen["execution_limits"]["cloud_execution_authorization"],
        )
        self.assertEqual(
            MODULE.sha256_bytes(frozen_content), receipt["frozen_protocol_sha256"]
        )
        self.assertEqual(
            MODULE.sha256_bytes(audit_content), receipt["pre_freeze_audit_sha256"]
        )
        self.assertFalse(receipt["cloud_execution_authorized"])
        self.assertFalse(receipt["cloud_mutation_performed"])
        self.assertFalse(receipt["active_repository_files_modified"])
        self.assertEqual(before, source)

    def test_rejects_an_incomplete_or_blocked_audit(self):
        audit = audit_result()
        audit["ready_to_freeze"] = False
        audit["blocking_requirements"] = ["financial-review"]
        audit["checks"][-1]["passed"] = False
        audit["passed_count"] -= 1

        with self.assertRaisesRegex(ValueError, "audit is incomplete"):
            self.finalize(audit_result=audit)

        audit = audit_result()
        audit["checks"].pop()
        audit["passed_count"] -= 1
        audit["check_count"] -= 1
        with self.assertRaisesRegex(ValueError, "audit is incomplete"):
            self.finalize(audit_result=audit)

    def test_rejects_approval_for_another_protocol_or_cloud_authorization(self):
        approval = researcher_approval()
        approval["candidate_protocol_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "does not bind"):
            self.finalize(researcher_approval=approval)

        approval = researcher_approval()
        approval["cloud_execution_authorized"] = True
        with self.assertRaisesRegex(ValueError, "does not bind"):
            self.finalize(researcher_approval=approval)

        review = cost_review()
        review["cloud_execution_authorized"] = True
        with self.assertRaisesRegex(ValueError, "non-authorizing"):
            self.finalize(cost_review=review)

    def test_rejects_backdated_finalization_and_unsafe_bindings(self):
        with self.assertRaisesRegex(ValueError, "cannot precede"):
            self.finalize(frozen_at="2026-09-22T05:29:59Z")

        with self.assertRaisesRegex(ValueError, "binding is invalid"):
            self.finalize(
                researcher_binding=binding("../approval.json", "c" * 64)
            )

    def test_rejects_protocol_without_independent_cloud_gate(self):
        value = protocol()
        value["execution_limits"]["cloud_execution_authorization"] = "implicit"

        with self.assertRaisesRegex(ValueError, "cloud authorization gate"):
            self.finalize(protocol=value)


if __name__ == "__main__":
    unittest.main()
