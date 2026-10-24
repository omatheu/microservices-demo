import importlib.util
import pathlib
import unittest


SCRIPT = (
    pathlib.Path(__file__).parents[2]
    / "scripts"
    / "validate-conventional-workflow-outcome.py"
)
SPEC = importlib.util.spec_from_file_location(
    "validate_conventional_workflow_outcome", SCRIPT
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def local_decision(decision="pass", change_class="release-relevant"):
    blocked = decision == "block"
    return {
        "schema_version": "1.0.0",
        "scope": "local-pre-staging-ci",
        "candidate_id": "cand-aaaaaaaaaaaaaaaa",
        "local_decision": decision,
        "change_class": change_class,
        "eligible_for_staging": decision == "pass" and change_class == "release-relevant",
        "failed_required_gates": 1 if blocked else 0,
    }


def sealed_block(local_sha256="a" * 64):
    return {
        "schema_version": "1.0.0",
        "mechanism": "conventional-ci-cd-with-staging",
        "candidate_id": "cand-aaaaaaaaaaaaaaaa",
        "decision": "block",
        "local_ci": {"decision": "block", "failed_required_gates": 1},
        "staging": {"executed": False, "decision": "NOT_RUN"},
        "immutable_artifacts": [],
        "candidate_definition_sha256": "b" * 64,
        "pdt_consulted": False,
        "control_decision_sealed": True,
        "operational_mutation_performed": False,
        "evidence": {"local_ci_decision": {"sha256": local_sha256}},
    }


class ValidateConventionalWorkflowOutcomeTests(unittest.TestCase):
    def test_release_pass_progresses(self):
        outcome = MODULE.validate(local_decision(), 0, False, None, "a" * 64)
        self.assertEqual("release-progression", outcome)

    def test_documentation_pass_completes_without_staging(self):
        outcome = MODULE.validate(
            local_decision(change_class="documentation-only"), 0, False, None, "a" * 64
        )
        self.assertEqual("documentation-only", outcome)

    def test_non_experimental_block_remains_a_failed_workflow(self):
        with self.assertRaisesRegex(ValueError, "non-experimental"):
            MODULE.validate(local_decision("block"), 1, False, sealed_block(), "a" * 64)

    def test_experimental_block_is_a_valid_terminal_outcome(self):
        outcome = MODULE.validate(
            local_decision("block"), 1, True, sealed_block(), "a" * 64
        )
        self.assertEqual("sealed-preartifact-block", outcome)

    def test_block_requires_canonical_runner_exit(self):
        with self.assertRaisesRegex(ValueError, "canonical status one"):
            MODULE.validate(local_decision("block"), 0, True, sealed_block(), "a" * 64)

    def test_block_requires_sealed_control_decision(self):
        with self.assertRaisesRegex(ValueError, "requires a sealed"):
            MODULE.validate(local_decision("block"), 1, True, None, "a" * 64)

    def test_block_rejects_tampered_local_evidence_binding(self):
        with self.assertRaisesRegex(ValueError, "not completely sealed"):
            MODULE.validate(local_decision("block"), 1, True, sealed_block("c" * 64), "a" * 64)

    def test_pass_rejects_nonzero_exit(self):
        with self.assertRaisesRegex(ValueError, "status zero"):
            MODULE.validate(local_decision(), 1, False, None, "a" * 64)

if __name__ == "__main__":
    unittest.main()
