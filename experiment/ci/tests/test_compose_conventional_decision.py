import importlib.util
import pathlib
import unittest


CANDIDATE_DEFINITION_SHA256 = "e" * 64

SCRIPT = pathlib.Path(__file__).parents[2] / "scripts" / "compose-conventional-decision.py"
SPEC = importlib.util.spec_from_file_location("compose_conventional_decision", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def local_decision(decision="pass", candidate_id="opaque-001"):
    failed = decision != "pass"
    return {
        "scope": "local-pre-staging-ci",
        "run_id": "ci-opaque-001",
        "candidate_id": candidate_id,
        "local_decision": decision,
        "failed_required_gates": 1 if failed else 0,
        "artifacts": [],
        "gates": [
            {
                "id": "checkout-unit-tests",
                "required": True,
                "status": "fail" if failed else "pass",
            }
        ],
    }


def staging_decision(decision="PASS", candidate_id="opaque-001"):
    return {
        "run_id": "staging-opaque-001-r1",
        "candidate_id": candidate_id,
        "decision": decision,
        "rationale": [] if decision == "PASS" else ["functional-failure"],
        "artifact_binding": {
            "decision": "bound",
            "candidate_id": candidate_id,
            "local_ci_run_id": "ci-opaque-001",
            "local_ci_decision_sha256": "a" * 64,
            "candidate_definition_sha256": CANDIDATE_DEFINITION_SHA256,
            "artifacts": [],
        },
    }


class ComposeConventionalDecisionTests(unittest.TestCase):
    def test_approve_requires_both_local_and_staging_pass(self):
        result = MODULE.compose(local_decision(), staging_decision(), "a" * 64)
        self.assertEqual("approve", result["decision"])
        self.assertTrue(result["control_decision_sealed"])
        self.assertFalse(result["pdt_consulted"])
        self.assertTrue(result["staging"]["artifact_binding_verified"])
        self.assertEqual(result["immutable_artifacts"], [])
        self.assertEqual(result["candidate_definition_sha256"], CANDIDATE_DEFINITION_SHA256)

    def test_staging_failure_blocks(self):
        result = MODULE.compose(local_decision(), staging_decision("FAIL"))
        self.assertEqual("block", result["decision"])
        self.assertIn("traditional-staging-did-not-pass", result["reasons"])

    def test_local_failure_blocks_without_staging(self):
        result = MODULE.compose(local_decision("block"))
        self.assertEqual("block", result["decision"])
        self.assertFalse(result["staging"]["executed"])
        self.assertIn("local-gate-failed:checkout-unit-tests", result["reasons"])

    def test_local_failure_preserves_explicit_candidate_definition_hash(self):
        result = MODULE.compose(
            local_decision("block"), candidate_definition_sha256="d" * 64
        )

        self.assertEqual("d" * 64, result["candidate_definition_sha256"])

    def test_staging_cannot_substitute_explicit_candidate_definition(self):
        with self.assertRaisesRegex(ValueError, "different candidate definition"):
            MODULE.compose(
                local_decision(),
                staging_decision(),
                candidate_definition_sha256="d" * 64,
            )

    def test_local_pass_without_staging_is_incomplete(self):
        with self.assertRaisesRegex(ValueError, "requires a staging decision"):
            MODULE.compose(local_decision())

    def test_candidate_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "same candidate"):
            MODULE.compose(local_decision(), staging_decision(candidate_id="opaque-002"))

    def test_artifact_binding_hash_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "decision hash"):
            MODULE.compose(local_decision(), staging_decision(), "b" * 64)

    def test_confirmatory_staging_requires_candidate_definition_hash(self):
        staging = staging_decision()
        staging["mode"] = "confirmatory"
        del staging["artifact_binding"]["candidate_definition_sha256"]

        with self.assertRaisesRegex(ValueError, "candidate definition hash"):
            MODULE.compose(local_decision(), staging)

    def test_same_immutable_artifact_is_preserved_for_pdt(self):
        local = local_decision()
        staging = staging_decision()
        artifact = {
            "component": "checkoutservice",
            "remote_reference": "registry.example/repository/checkoutservice@sha256:" + "c" * 64,
        }
        local["artifacts"] = [artifact]
        staging["artifact_binding"]["artifacts"] = [artifact]

        result = MODULE.compose(local, staging, "a" * 64)

        self.assertEqual(result["immutable_artifacts"], [artifact])

    def test_staging_artifact_substitution_is_rejected(self):
        local = local_decision()
        staging = staging_decision()
        local["artifacts"] = [
            {
                "component": "checkoutservice",
                "remote_reference": "registry.example/repository/checkoutservice@sha256:" + "c" * 64,
            }
        ]
        staging["artifact_binding"]["artifacts"] = [
            {
                "component": "checkoutservice",
                "remote_reference": "registry.example/repository/checkoutservice@sha256:" + "d" * 64,
            }
        ]

        with self.assertRaisesRegex(ValueError, "did not evaluate"):
            MODULE.compose(local, staging, "a" * 64)


if __name__ == "__main__":
    unittest.main()
