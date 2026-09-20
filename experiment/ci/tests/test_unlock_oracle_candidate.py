import importlib.util
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "unlock-oracle-candidate.py"
SPEC = importlib.util.spec_from_file_location("unlock_oracle_candidate", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


CANDIDATE_ID = "cand-abcdefghijklmnop"
DEFINITION_SHA256 = "d" * 64


def public(eligible=True):
    return {
        "corpus_id": "corpus-test",
        "protocol_sha256": "p" * 64,
        "confirmatory_eligible": eligible,
        "oracle_manifest_commitment_sha256": "c" * 64,
        "execution_order": [
            {"sequence": 1, "candidate_id": CANDIDATE_ID, "repetitions": [1, 2, 3]}
        ],
    }


def oracle():
    return {
        "corpus_id": "corpus-test",
        "protocol_sha256": "p" * 64,
        "oracle_manifest_commitment_sha256": "c" * 64,
        "candidates": [
            {
                "candidate_id": CANDIDATE_ID,
                "operator_id": "INF-CPU-01",
                "operator_instance": 1,
                "stratum": "nonfunctional-infrastructure",
                "intended_label": "harmful",
                "target_component": "checkoutservice",
                "context_dependency": "load-dependent",
                "parameters": {"cpu_limit": "75m"},
            }
        ],
    }


def control(decision="approve"):
    return {
        "mechanism": "conventional-ci-cd-with-staging",
        "candidate_id": CANDIDATE_ID,
        "decision": decision,
        "control_decision_sealed": True,
        "candidate_definition_sha256": DEFINITION_SHA256,
        "immutable_artifacts": [],
    }


def pdt():
    return {
        "candidate": CANDIDATE_ID,
        "decision": "approve",
        "artifact_binding": {
            "candidate_definition_sha256": DEFINITION_SHA256,
            "immutable_artifacts": [],
        },
    }


def gate():
    return {
        "candidate_id": CANDIDATE_ID,
        "gate_state": "awaiting-human-confirmation",
        "operational_mutation_performed": False,
    }


class UnlockOracleCandidateTests(unittest.TestCase):
    def test_approved_control_requires_and_accepts_sealed_pdt(self):
        private_item, receipt = MODULE.unlock(
            public(), oracle(), CANDIDATE_ID, control(), pdt(), gate()
        )

        self.assertEqual(private_item["operator_id"], "INF-CPU-01")
        self.assertEqual(receipt["treatment_decision"], "approve")
        self.assertEqual(
            MODULE.recursively_find_keys(receipt, MODULE.FORBIDDEN_RECEIPT_KEYS), []
        )

    def test_approved_control_without_pdt_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "requires sealed PDT"):
            MODULE.unlock(public(), oracle(), CANDIDATE_ID, control())

    def test_control_block_inherits_treatment_block_without_running_pdt(self):
        private_item, receipt = MODULE.unlock(
            public(), oracle(), CANDIDATE_ID, control("block")
        )

        self.assertEqual(
            private_item["treatment_decision"],
            {"decision": "block", "source": "inherited-control-block"},
        )
        self.assertEqual(receipt["treatment_decision"], "block")

    def test_unsealed_control_is_blocked(self):
        decision = control()
        decision["control_decision_sealed"] = False

        with self.assertRaisesRegex(ValueError, "must be sealed"):
            MODULE.unlock(public(), oracle(), CANDIDATE_ID, decision, pdt(), gate())

    def test_draft_corpus_needs_explicit_nonconfirmatory_override(self):
        with self.assertRaisesRegex(ValueError, "confirmatory-eligible"):
            MODULE.unlock(
                public(eligible=False), oracle(), CANDIDATE_ID, control(), pdt(), gate()
            )

        private_item, _ = MODULE.unlock(
            public(eligible=False),
            oracle(),
            CANDIDATE_ID,
            control(),
            pdt(),
            gate(),
            allow_draft=True,
        )
        self.assertEqual(private_item["candidate_id"], CANDIDATE_ID)

    def test_candidate_definition_substitution_is_blocked(self):
        pdt_decision = pdt()
        pdt_decision["artifact_binding"]["candidate_definition_sha256"] = "e" * 64

        with self.assertRaisesRegex(ValueError, "candidate definitions differ"):
            MODULE.unlock(
                public(), oracle(), CANDIDATE_ID, control(), pdt_decision, gate()
            )


if __name__ == "__main__":
    unittest.main()
