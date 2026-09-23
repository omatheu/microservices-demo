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


def pdt(decision="approve"):
    return {
        "candidate": CANDIDATE_ID,
        "decision": decision,
        "selected_alternative": "deploy-as-is",
        "artifact_binding": {
            "candidate_definition_sha256": DEFINITION_SHA256,
            "immutable_artifacts": [],
        },
    }


def gate(decision="approve"):
    blocked = decision == "block"
    return {
        "candidate_id": CANDIDATE_ID,
        "gate_state": "blocked" if blocked else "awaiting-human-confirmation",
        "pdt": {
            "decision": decision,
            "selected_alternative": "deploy-as-is",
        },
        "human_confirmation": {
            "status": "not-requested" if blocked else "pending"
        },
        "operational_mutation_performed": False,
    }


def protected_review():
    return {
        "validated": True,
        "candidate_id": CANDIDATE_ID,
        "selected_alternative": "deploy-as-is",
        "review_environment": "tcc-deployment-approval",
        "repository": "owner/repository",
        "workflow_run_id": 1234,
    }


class UnlockOracleCandidateTests(unittest.TestCase):
    def test_approved_control_requires_and_accepts_sealed_pdt(self):
        private_item, receipt = MODULE.unlock(
            public(),
            oracle(),
            CANDIDATE_ID,
            control(),
            pdt(),
            gate(),
            protected_review(),
        )

        self.assertEqual(private_item["operator_id"], "INF-CPU-01")
        self.assertEqual(receipt["treatment_decision"], "approve")
        self.assertTrue(receipt["protected_human_gate_verified"])
        self.assertEqual(
            MODULE.recursively_find_keys(receipt, MODULE.FORBIDDEN_RECEIPT_KEYS), []
        )

    def test_approved_control_without_pdt_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "requires sealed PDT"):
            MODULE.unlock(public(), oracle(), CANDIDATE_ID, control())

    def test_deployable_pdt_action_without_protected_review_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "protected human review"):
            MODULE.unlock(
                public(), oracle(), CANDIDATE_ID, control(), pdt(), gate()
            )

    def test_pdt_block_does_not_require_a_deployable_action_review(self):
        private_item, receipt = MODULE.unlock(
            public(),
            oracle(),
            CANDIDATE_ID,
            control(),
            pdt("block"),
            gate("block"),
        )

        self.assertEqual(private_item["treatment_decision"]["decision"], "block")
        self.assertFalse(receipt["protected_human_gate_verified"])

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
            protected_review(),
            allow_draft=True,
        )
        self.assertEqual(private_item["candidate_id"], CANDIDATE_ID)

    def test_candidate_definition_substitution_is_blocked(self):
        pdt_decision = pdt()
        pdt_decision["artifact_binding"]["candidate_definition_sha256"] = "e" * 64

        with self.assertRaisesRegex(ValueError, "candidate definitions differ"):
            MODULE.unlock(
                public(),
                oracle(),
                CANDIDATE_ID,
                control(),
                pdt_decision,
                gate(),
                protected_review(),
            )


if __name__ == "__main__":
    unittest.main()
