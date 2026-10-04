import contextlib
import hashlib
import importlib.util
import io
import json
import pathlib
import tempfile
import unittest
from unittest import mock


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "experiment" / "scripts" / "prepare-researcher-approval.py"
PROTOCOL = REPO_ROOT / "experiment" / "protocol" / "protocol-v1.json"
SPEC = importlib.util.spec_from_file_location("prepare_researcher_approval", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def ready_audit(protocol_sha256):
    checks = [
        {"id": f"ready-{index}", "passed": True, "detail": "ready"}
        for index in range(16)
    ]
    checks.append(
        {
            "id": "researcher-approval",
            "passed": False,
            "detail": "approval required",
        }
    )
    return {
        "protocol_sha256": protocol_sha256,
        "passed_count": 16,
        "check_count": 17,
        "ready_to_freeze": False,
        "blocking_requirements": ["researcher-approval"],
        "checks": checks,
    }


class Repository:
    def __init__(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        protocol_path = self.root / MODULE.PROTOCOL_PATH
        protocol_path.parent.mkdir(parents=True)
        protocol_path.write_bytes(PROTOCOL.read_bytes())
        self.protocol_path = protocol_path

    def close(self):
        self.temporary.cleanup()


class PrepareResearcherApprovalTests(unittest.TestCase):
    def setUp(self):
        self.repository = Repository()
        self.protocol_sha256 = hashlib.sha256(
            self.repository.protocol_path.read_bytes()
        ).hexdigest()
        self.clock = mock.patch.object(
            MODULE, "utc_now", return_value="2026-09-27T01:00:00Z"
        )
        self.clock.start()

    def tearDown(self):
        self.clock.stop()
        self.repository.close()

    def test_current_repository_is_not_ready_for_researcher_approval(self):
        result = MODULE.prepare(REPO_ROOT)

        self.assertFalse(result["eligible_for_researcher_approval"])
        self.assertFalse(result["approval_generated"])
        self.assertFalse(result["cloud_execution_authorized"])
        self.assertNotIn("financial-review", result["blocking_requirements"])
        self.assertIn("researcher-approval", result["blocking_requirements"])

    def test_read_only_mode_accepts_only_researcher_as_remaining_blocker(self):
        with mock.patch.object(
            MODULE.AUDITOR,
            "audit",
            return_value=ready_audit(self.protocol_sha256),
        ):
            result = MODULE.prepare(self.repository.root)

        self.assertTrue(result["eligible_for_researcher_approval"])
        self.assertEqual(16, result["checks_passed"])
        self.assertEqual(17, result["check_count"])
        self.assertFalse(result["approval_generated"])

    def test_approval_requires_exact_acknowledgement_before_audit(self):
        with mock.patch.object(MODULE.AUDITOR, "audit") as audit:
            with self.assertRaisesRegex(MODULE.ApprovalError, "requires"):
                MODULE.prepare(
                    self.repository.root,
                    approve=True,
                    acknowledgement="wrong",
                    approved_by="omatheu",
                )

        audit.assert_not_called()

    def test_approval_requires_nonempty_researcher_identity(self):
        with self.assertRaisesRegex(MODULE.ApprovalError, "approved-by"):
            MODULE.prepare(
                self.repository.root,
                approve=True,
                acknowledgement=MODULE.ACKNOWLEDGEMENT,
                approved_by="  ",
            )

    def test_approval_binds_exact_protocol_and_does_not_authorize_cloud(self):
        with mock.patch.object(
            MODULE.AUDITOR,
            "audit",
            return_value=ready_audit(self.protocol_sha256),
        ):
            approval = MODULE.prepare(
                self.repository.root,
                approve=True,
                acknowledgement=MODULE.ACKNOWLEDGEMENT,
                approved_by="  omatheu  ",
            )

        self.assertEqual(self.protocol_sha256, approval["candidate_protocol_sha256"])
        self.assertEqual("approve-protocol-freeze", approval["decision"])
        self.assertEqual("omatheu", approval["approved_by"])
        self.assertEqual("2026-09-27T01:00:00Z", approval["approved_at"])
        self.assertFalse(approval["cloud_execution_authorized"])
        self.assertTrue(all(approval["acknowledgements"].values()))

    def test_additional_blocker_makes_candidate_ineligible(self):
        audit = ready_audit(self.protocol_sha256)
        audit["passed_count"] = 15
        audit["blocking_requirements"] = [
            "financial-review",
            "researcher-approval",
        ]
        with mock.patch.object(MODULE.AUDITOR, "audit", return_value=audit):
            result = MODULE.prepare(self.repository.root)

        self.assertFalse(result["eligible_for_researcher_approval"])

    def test_auditor_digest_mismatch_is_rejected(self):
        with mock.patch.object(
            MODULE.AUDITOR,
            "audit",
            return_value=ready_audit("0" * 64),
        ):
            result = MODULE.prepare(self.repository.root)

        self.assertFalse(result["audit_protocol_sha256_matches"])
        self.assertFalse(result["eligible_for_researcher_approval"])

    def test_duplicate_audit_check_is_rejected(self):
        audit = ready_audit(self.protocol_sha256)
        audit["checks"][1]["id"] = audit["checks"][0]["id"]
        with mock.patch.object(MODULE.AUDITOR, "audit", return_value=audit):
            result = MODULE.prepare(self.repository.root)

        self.assertFalse(result["eligible_for_researcher_approval"])

    def test_cli_writes_only_canonical_approval_path(self):
        arguments = [
            str(SCRIPT),
            "--repo-root",
            str(self.repository.root),
            "--approve",
            "--acknowledge",
            MODULE.ACKNOWLEDGEMENT,
            "--approved-by",
            "omatheu",
            "--output",
            MODULE.CANONICAL_APPROVAL_PATH.as_posix(),
        ]
        with mock.patch.object(
            MODULE.AUDITOR,
            "audit",
            return_value=ready_audit(self.protocol_sha256),
        ):
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
            "--approve",
            "--acknowledge",
            MODULE.ACKNOWLEDGEMENT,
            "--approved-by",
            "omatheu",
            "--output",
            "approval.json",
        ]
        errors = io.StringIO()

        with mock.patch.object(MODULE.sys, "argv", arguments):
            with contextlib.redirect_stderr(errors):
                self.assertEqual(2, MODULE.main())

        self.assertIn("must be", errors.getvalue())
        self.assertFalse((self.repository.root / "approval.json").exists())


if __name__ == "__main__":
    unittest.main()
