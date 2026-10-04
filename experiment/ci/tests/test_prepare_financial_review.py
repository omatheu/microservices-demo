import copy
import contextlib
import importlib.util
import io
import json
import pathlib
import tempfile
import unittest
from unittest import mock


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "experiment" / "scripts" / "prepare-financial-review.py"
PROTOCOL = REPO_ROOT / "experiment" / "protocol" / "protocol-v1.json"
SPEC = importlib.util.spec_from_file_location("prepare_financial_review", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


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


class Repository:
    def __init__(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        protocol_path = self.root / MODULE.PROTOCOL_PATH
        protocol_path.parent.mkdir(parents=True)
        protocol_path.write_bytes(PROTOCOL.read_bytes())
        self.evidence_path = (
            self.root / "experiment/evidence/finance/cost-window.json"
        )
        self.evidence_path.parent.mkdir(parents=True)
        self.write_evidence(cost_evidence())

    def write_evidence(self, value):
        self.evidence_path.write_text(json.dumps(value), encoding="utf-8")

    def close(self):
        self.temporary.cleanup()


class PrepareFinancialReviewTests(unittest.TestCase):
    def setUp(self):
        self.repository = Repository()
        self.clock = mock.patch.object(
            MODULE, "utc_now", return_value="2026-09-27T00:40:00Z"
        )
        self.clock.start()

    def tearDown(self):
        self.clock.stop()
        self.repository.close()

    def prepare(self, **kwargs):
        return MODULE.prepare(
            self.repository.root,
            pathlib.Path("experiment/evidence/finance/cost-window.json"),
            **kwargs,
        )

    def test_read_only_mode_reports_eligibility_without_approval(self):
        result = self.prepare()

        self.assertEqual("read-only-eligibility", result["mode"])
        self.assertTrue(result["eligible_for_human_approval"])
        self.assertFalse(result["approval_generated"])
        self.assertFalse(result["cloud_execution_authorized"])
        self.assertFalse(result["gcp_mutation_performed"])
        self.assertEqual([], result["blocking_requirements"])
        self.assertEqual(12.34, result["observed_project_gross_cost_brl"])
        self.assertEqual(212.34, result["projected_project_gross_cost_ceiling_brl"])
        self.assertEqual(1751.1, result["project_gross_cost_budget_brl"])
        self.assertAlmostEqual(
            1538.76,
            result["remaining_project_gross_budget_after_approved_ceiling_brl"],
        )

    def test_approval_requires_exact_acknowledgement(self):
        with self.assertRaisesRegex(MODULE.ReviewError, "requires"):
            self.prepare(approve=True, acknowledgement="wrong")

    def test_approved_document_is_accepted_by_frozen_auditor(self):
        review = self.prepare(
            approve=True,
            acknowledgement=MODULE.ACKNOWLEDGEMENT,
        )
        protocol = json.loads(
            (self.repository.root / MODULE.PROTOCOL_PATH).read_text(encoding="utf-8")
        )

        self.assertTrue(
            MODULE.AUDITOR.validate_cost_review(
                self.repository.root, protocol, review
            )
        )
        self.assertEqual("approved-for-protocol-freeze", review["decision"])
        self.assertFalse(review["cloud_execution_authorized"])
        self.assertEqual(
            "experiment/evidence/finance/cost-window.json",
            review["evidence"]["path"],
        )

    def test_tampered_net_cost_is_ineligible(self):
        value = cost_evidence()
        value["net_cost_brl"] = 99.0
        self.repository.write_evidence(value)

        result = self.prepare()

        self.assertFalse(result["eligible_for_human_approval"])
        self.assertEqual(
            ["cost-evidence-or-protocol-limits-invalid"],
            result["blocking_requirements"],
        )

    def test_projected_total_above_project_budget_is_ineligible(self):
        value = cost_evidence()
        value["gross_cost_brl"] = 1600.0
        value["credits_brl"] = -1600.0
        self.repository.write_evidence(value)

        result = self.prepare()

        self.assertFalse(result["eligible_for_human_approval"])

    def test_future_billing_timestamp_is_ineligible(self):
        value = cost_evidence()
        value["billing_data_as_of"] = "2026-09-28T00:00:00Z"
        self.repository.write_evidence(value)

        result = self.prepare()

        self.assertFalse(result["eligible_for_human_approval"])

    def test_evidence_outside_finance_directory_is_rejected(self):
        outside = self.repository.root / "cost-window.json"
        outside.write_text(json.dumps(cost_evidence()), encoding="utf-8")

        with self.assertRaisesRegex(MODULE.ReviewError, "under"):
            MODULE.prepare(self.repository.root, outside)

    def test_approval_rejects_ineligible_evidence(self):
        value = copy.deepcopy(cost_evidence())
        value["cloud_execution_authorized"] = True
        self.repository.write_evidence(value)

        with self.assertRaisesRegex(MODULE.ReviewError, "not eligible"):
            self.prepare(
                approve=True,
                acknowledgement=MODULE.ACKNOWLEDGEMENT,
            )

    def test_cli_writes_only_the_canonical_approval_path(self):
        output = MODULE.CANONICAL_APPROVAL_PATH.as_posix()
        arguments = [
            str(SCRIPT),
            "--repo-root",
            str(self.repository.root),
            "--cost-evidence",
            "experiment/evidence/finance/cost-window.json",
            "--approve",
            "--acknowledge",
            MODULE.ACKNOWLEDGEMENT,
            "--output",
            output,
        ]

        with mock.patch.object(MODULE.sys, "argv", arguments):
            self.assertEqual(0, MODULE.main())

        approval = self.repository.root / MODULE.CANONICAL_APPROVAL_PATH
        self.assertTrue(approval.is_file())
        self.assertFalse(json.loads(approval.read_text())["cloud_execution_authorized"])

    def test_cli_rejects_noncanonical_approval_output(self):
        arguments = [
            str(SCRIPT),
            "--repo-root",
            str(self.repository.root),
            "--cost-evidence",
            "experiment/evidence/finance/cost-window.json",
            "--approve",
            "--acknowledge",
            MODULE.ACKNOWLEDGEMENT,
            "--output",
            "review.json",
        ]
        errors = io.StringIO()

        with mock.patch.object(MODULE.sys, "argv", arguments):
            with contextlib.redirect_stderr(errors):
                self.assertEqual(2, MODULE.main())

        self.assertIn("must be", errors.getvalue())
        self.assertFalse((self.repository.root / "review.json").exists())


if __name__ == "__main__":
    unittest.main()
