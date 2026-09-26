import importlib.util
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "aggregate-conventional-repetitions.py"
SPEC = importlib.util.spec_from_file_location("aggregate_conventional_repetitions", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


DIGEST = "a" * 64
CANDIDATE_DIGEST = "b" * 64


def protocol(frozen=False):
    return {
        "protocol_id": "checkout-pdt-comparison-v1",
        "status": "frozen" if frozen else "pre-registration-candidate",
        "confirmatory_collection_allowed": frozen,
        "frozen_at": "2026-09-25T00:00:00Z" if frozen else None,
        "research_design": {"technical_repetitions_per_candidate": 3},
        "aggregation": {
            "minimum_valid_repetitions": 2,
            "mechanism_repetition_rule": {
                "planned_repetitions": 3,
                "minimum_valid_repetitions": 2,
                "safe_votes_to_approve": 2,
                "applies_symmetrically_to_control_and_treatment": True,
                "incomplete_outcome": "retry-once-before-label-then-exclude-or-block",
            }
        },
    }


def local(decision="pass"):
    return {
        "scope": "local-pre-staging-ci",
        "run_id": "ci-cand-opaque",
        "candidate_id": "cand-opaque",
        "local_decision": decision,
        "failed_required_gates": 0 if decision == "pass" else 1,
        "artifacts": [
            {
                "component": "checkoutservice",
                "remote_reference": "registry.example/checkout@sha256:" + "c" * 64,
            }
        ],
        "gates": [],
    }


def staging(repetition, decision="PASS", mode="engineering"):
    return {
        "run_id": f"staging-cand-opaque-r{repetition}",
        "candidate_id": "cand-opaque",
        "mode": mode,
        "repetition": repetition,
        "decision": decision,
        "rationale": [] if decision == "PASS" else ["latency_p95_above_threshold"],
        "artifact_binding": {
            "decision": "bound",
            "candidate_id": "cand-opaque",
            "local_ci_run_id": "ci-cand-opaque",
            "local_ci_decision_sha256": DIGEST,
            "candidate_definition_sha256": CANDIDATE_DIGEST,
            "artifacts": local()["artifacts"],
        },
    }


def invalid_ledger(valid=(1, 2), invalid=3):
    return {
        "schema_version": "1.0.0",
        "candidate_id": "cand-opaque",
        "classification": "infrastructure-invalid",
        "label_revealed": False,
        "planned_repetitions": [1, 2, 3],
        "valid_repetitions": list(valid),
        "invalid_repetitions": [
            {
                "repetition": invalid,
                "attempts": 2,
                "reasons": ["cluster-timeout", "replacement-cluster-timeout"],
            }
        ],
    }


def aggregate(
    decisions,
    local_decision=None,
    protocol_value=None,
    allow_draft=True,
    invalid_repetition_ledger=None,
):
    return MODULE.aggregate(
        protocol_value or protocol(),
        local_decision or local(),
        decisions,
        DIGEST,
        CANDIDATE_DIGEST,
        invalid_repetition_ledger=invalid_repetition_ledger,
        allow_draft=allow_draft,
    )


class AggregateConventionalRepetitionsTests(unittest.TestCase):
    def test_two_of_three_safe_votes_approve_candidate(self):
        result = aggregate([staging(1), staging(2), staging(3, "FAIL")])

        self.assertEqual(result["decision"], "approve")
        self.assertEqual(result["staging"]["decision"], "PASS")
        self.assertEqual(result["repetition_aggregation"]["safe_votes"], 2)
        self.assertEqual(result["repetition_aggregation"]["unsafe_votes"], 1)
        self.assertTrue(result["control_decision_sealed"])

    def test_two_of_three_unsafe_votes_block_candidate(self):
        result = aggregate([staging(1, "FAIL"), staging(2), staging(3, "FAIL")])

        self.assertEqual(result["decision"], "block")
        self.assertEqual(result["staging"]["decision"], "FAIL")
        self.assertIn("traditional-staging-majority-did-not-pass", result["reasons"])

    def test_missing_or_duplicate_repetition_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "ledger is incomplete"):
            aggregate([staging(1), staging(2)])
        with self.assertRaisesRegex(ValueError, "incomplete or duplicated"):
            aggregate([staging(1), staging(1), staging(3)])

    def test_artifact_substitution_in_one_repetition_is_rejected(self):
        changed = staging(3)
        changed["artifact_binding"]["artifacts"][0]["remote_reference"] = (
            "registry.example/checkout@sha256:" + "d" * 64
        )

        with self.assertRaisesRegex(ValueError, "did not evaluate"):
            aggregate([staging(1), staging(2), changed])

    def test_two_safe_repetitions_require_a_bound_invalid_attempt_ledger(self):
        with self.assertRaisesRegex(ValueError, "ledger is incomplete"):
            aggregate([staging(1), staging(2)])

        result = aggregate(
            [staging(1), staging(2)],
            invalid_repetition_ledger=invalid_ledger(),
        )
        self.assertEqual(result["decision"], "approve")
        self.assertEqual(result["repetition_aggregation"]["valid_repetitions"], [1, 2])
        self.assertEqual(result["repetition_aggregation"]["invalid_repetitions"], [3])

    def test_split_two_valid_repetitions_blocks_fail_closed(self):
        result = aggregate(
            [staging(1), staging(2, "FAIL")],
            invalid_repetition_ledger=invalid_ledger(),
        )
        self.assertEqual(result["decision"], "block")

    def test_invalid_ledger_requires_both_failed_attempts_before_label(self):
        ledger = invalid_ledger()
        ledger["invalid_repetitions"][0]["attempts"] = 1
        with self.assertRaisesRegex(ValueError, "original and replacement"):
            aggregate(
                [staging(1), staging(2)],
                invalid_repetition_ledger=ledger,
            )

    def test_local_ci_block_skips_repetitions_and_remains_sealed(self):
        result = aggregate([], local("block"))

        self.assertEqual(result["decision"], "block")
        self.assertEqual(result["repetition_aggregation"]["outcome"], "local-ci-block")
        self.assertEqual(result["repetition_aggregation"]["observed_valid_repetitions"], 0)

    def test_local_ci_block_rejects_staging_evidence(self):
        with self.assertRaisesRegex(ValueError, "must not contain staging"):
            aggregate([staging(1), staging(2), staging(3)], local("block"))

    def test_frozen_protocol_requires_confirmatory_repetitions(self):
        with self.assertRaisesRegex(ValueError, "confirmatory staging"):
            aggregate(
                [staging(1), staging(2), staging(3)],
                protocol_value=protocol(frozen=True),
                allow_draft=False,
            )

        result = aggregate(
            [
                staging(1, mode="confirmatory"),
                staging(2, mode="confirmatory"),
                staging(3, mode="confirmatory"),
            ],
            protocol_value=protocol(frozen=True),
            allow_draft=False,
        )
        self.assertEqual(result["execution_mode"], "confirmatory")

    def test_draft_protocol_rejects_confirmatory_labeled_evidence(self):
        with self.assertRaisesRegex(ValueError, "engineering staging"):
            aggregate(
                [
                    staging(1, mode="confirmatory"),
                    staging(2, mode="confirmatory"),
                    staging(3, mode="confirmatory"),
                ]
            )

    def test_asymmetric_or_nonmajority_protocol_rule_is_rejected(self):
        value = protocol()
        value["aggregation"]["mechanism_repetition_rule"][
            "applies_symmetrically_to_control_and_treatment"
        ] = False
        with self.assertRaisesRegex(ValueError, "repetition rule"):
            aggregate([staging(1), staging(2), staging(3)], protocol_value=value)

        value = protocol()
        value["aggregation"]["mechanism_repetition_rule"]["safe_votes_to_approve"] = 1
        with self.assertRaisesRegex(ValueError, "repetition rule"):
            aggregate([staging(1), staging(2), staging(3)], protocol_value=value)


if __name__ == "__main__":
    unittest.main()
