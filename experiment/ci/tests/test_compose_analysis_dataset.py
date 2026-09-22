import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "compose-analysis-dataset.py"
SPEC = importlib.util.spec_from_file_location("compose_analysis_dataset", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(root, name, value):
    path = root / name
    path.write_text(json.dumps(value), encoding="utf-8")
    return {"path": name, "sha256": digest(path)}


def protocol():
    return {
        "protocol_id": "test-protocol",
        "status": "pre-registration-candidate",
        "frozen_at": None,
        "confirmatory_collection_allowed": False,
        "research_design": {
            "candidate_count": 2,
            "technical_repetitions_per_candidate": 3,
        },
        "aggregation": {"minimum_valid_repetitions": 2},
    }


def oracle(candidate_id, actual):
    return {
        "candidate_id": candidate_id,
        "observed_deploy_as_is_label": actual,
        "eligible_for_primary_analysis": False,
        "selected_alternative": "block" if actual == "harmful" else "deploy-as-is",
        "alternatives": [{"id": "deploy-as-is", "label": actual, "change_cost": 0}],
    }


def summary(value, count=3):
    return {
        "count": count,
        "mean": value,
        "median": value,
        "sample_standard_deviation": 0.0 if count > 1 else None,
        "minimum": value,
        "maximum": value,
    }


def fidelity(candidate_id, protocol_id, protocol_sha, definition_sha, artifacts):
    metrics = {}
    for metric_id, unit in MODULE.FIDELITY_METRICS.items():
        zero_observed = metric_id in {
            "checkoutservice_unavailable",
            "checkoutservice_restart_increase",
        }
        metrics[metric_id] = {
            "unit": unit,
            "report_count": 3,
            "signed_error": summary(0.0),
            "absolute_error": summary(0.0),
            "relative_error": None if zero_observed else summary(0.0),
            "undefined_relative_error_count": 3 if zero_observed else 0,
        }
    return {
        "schema_version": "1.0.0",
        "mechanism": "candidate-level-pdt-fidelity",
        "protocol_id": protocol_id,
        "protocol_sha256": protocol_sha,
        "policy_id": "checkout-pdt-fidelity-v1",
        "policy_sha256": "f" * 64,
        "candidate_id": candidate_id,
        "candidate_definition_sha256": definition_sha,
        "immutable_artifacts": artifacts,
        "unit_of_analysis": "candidate",
        "execution_mode": "engineering",
        "confirmatory_eligible": False,
        "coverage": {
            "deployable_alternatives": ["deploy-as-is"],
            "repetitions": [1, 2, 3],
            "expected_reports": 3,
            "observed_reports": 3,
            "complete": True,
        },
        "classification": {
            "agreements": 2,
            "comparisons": 3,
            "agreement_rate": 2 / 3,
            "by_alternative": {
                "deploy-as-is": {
                    "agreements": 2,
                    "comparisons": 3,
                    "agreement_rate": 2 / 3,
                }
            },
        },
        "metrics": metrics,
        "report_index": [
            {
                "alternative_id": "deploy-as-is",
                "repetition": repetition,
                "classification_agreement": repetition != 3,
            }
            for repetition in (1, 2, 3)
        ],
        "controls": {
            "complete_matrix_required": True,
            "model_mutation_performed": False,
            "recalibration_allowed": False,
            "confirmatory_reports_are_evaluation_only": True,
        },
    }


class ComposeAnalysisDatasetTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        root = pathlib.Path(temporary.name)
        proto = protocol()
        proto_sha = hashlib.sha256(b"protocol").hexdigest()
        public = {
            "protocol_id": proto["protocol_id"],
            "protocol_sha256": proto_sha,
            "corpus_id": "corpus-test",
            "confirmatory_eligible": False,
            "execution_order": [
                {"sequence": 1, "candidate_id": "cand-0001", "repetitions": [1, 2, 3]},
                {"sequence": 2, "candidate_id": "cand-0002", "repetitions": [1, 2, 3]},
            ],
        }
        public_path = root / "public.json"
        public_path.write_text(json.dumps(public), encoding="utf-8")
        artifacts = [{"component": "checkoutservice", "remote_reference": "image@sha256:" + "a" * 64}]
        definition_sha = "b" * 64
        control_approved = {
            "candidate_id": "cand-0001",
            "mechanism": "conventional-ci-cd-with-staging",
            "decision": "approve",
            "control_decision_sealed": True,
            "operational_mutation_performed": False,
            "immutable_artifacts": artifacts,
            "candidate_definition_sha256": definition_sha,
        }
        pdt = {
            "candidate": "cand-0001",
            "decision": "block",
            "selected_alternative": "block",
            "artifact_binding": {
                "immutable_artifacts": artifacts,
                "candidate_definition_sha256": definition_sha,
            },
        }
        gate = {
            "candidate_id": "cand-0001",
            "gate_state": "blocked",
            "operational_mutation_performed": False,
        }
        fidelity_approved = fidelity(
            "cand-0001", proto["protocol_id"], proto_sha, definition_sha, artifacts
        )
        control_blocked = {
            "candidate_id": "cand-0002",
            "mechanism": "conventional-ci-cd-with-staging",
            "decision": "block",
            "control_decision_sealed": True,
            "operational_mutation_performed": False,
            "immutable_artifacts": [],
            "candidate_definition_sha256": "c" * 64,
        }
        manifest = {
            "protocol_id": proto["protocol_id"],
            "protocol_sha256": proto_sha,
            "public_corpus_sha256": digest(public_path),
            "collection_complete": True,
            "candidates": [
                {
                    "candidate_id": "cand-0001",
                    "exclusion": None,
                    "conventional_decision": write(root, "control-1.json", control_approved),
                    "pdt_decision": write(root, "pdt-1.json", pdt),
                    "deployment_gate": write(root, "gate-1.json", gate),
                    "pdt_fidelity": write(root, "fidelity-1.json", fidelity_approved),
                    "oracle_adjudication": write(root, "oracle-1.json", oracle("cand-0001", "harmful")),
                },
                {
                    "candidate_id": "cand-0002",
                    "exclusion": None,
                    "conventional_decision": write(root, "control-2.json", control_blocked),
                    "pdt_decision": None,
                    "deployment_gate": None,
                    "pdt_fidelity": None,
                    "oracle_adjudication": write(root, "oracle-2.json", oracle("cand-0002", "safe")),
                },
            ],
        }
        return temporary, root, proto, proto_sha, public, digest(public_path), manifest

    def test_composes_approved_and_inherited_control_paths(self):
        temporary, root, proto, proto_sha, public, public_sha, manifest = self.fixture()
        self.addCleanup(temporary.cleanup)
        result = MODULE.compose(proto, proto_sha, public, public_sha, manifest, root, allow_draft=True)
        self.assertEqual("block", result["candidates"][0]["treatment"]["decision"])
        self.assertEqual("block", result["candidates"][1]["treatment"]["decision"])
        self.assertEqual(
            "candidate-level-pdt-fidelity",
            result["candidates"][0]["treatment"]["fidelity"]["mechanism"],
        )
        self.assertIsNone(result["candidates"][1]["treatment"]["fidelity"])
        self.assertEqual("engineering-dry-run", result["composition_mode"])
        self.assertFalse(result["confirmatory_eligible"])
        self.assertEqual(2, result["collection_flow"]["complete_decision_pairs"])
        self.assertEqual(1, result["collection_flow"]["pdt_fidelity_candidates"])
        self.assertEqual(
            1,
            result["collection_flow"][
                "pdt_fidelity_not_applicable_control_blocked"
            ],
        )
        self.assertEqual([], result["collection_flow"]["manifest_exclusions"])

    def test_evidence_hash_substitution_is_rejected(self):
        temporary, root, proto, proto_sha, public, public_sha, manifest = self.fixture()
        self.addCleanup(temporary.cleanup)
        manifest["candidates"][0]["pdt_decision"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "hash differs"):
            MODULE.compose(proto, proto_sha, public, public_sha, manifest, root, allow_draft=True)

    def test_control_approval_requires_pdt_and_gate(self):
        temporary, root, proto, proto_sha, public, public_sha, manifest = self.fixture()
        self.addCleanup(temporary.cleanup)
        manifest["candidates"][0]["pdt_decision"] = None
        with self.assertRaisesRegex(ValueError, "must contain only path"):
            MODULE.compose(proto, proto_sha, public, public_sha, manifest, root, allow_draft=True)

    def test_control_approval_requires_hash_bound_complete_fidelity(self):
        temporary, root, proto, proto_sha, public, public_sha, manifest = self.fixture()
        self.addCleanup(temporary.cleanup)
        manifest["candidates"][0]["pdt_fidelity"] = None
        with self.assertRaisesRegex(ValueError, "must contain only path"):
            MODULE.compose(
                proto, proto_sha, public, public_sha, manifest, root, allow_draft=True
            )

        temporary, root, proto, proto_sha, public, public_sha, manifest = self.fixture()
        self.addCleanup(temporary.cleanup)
        fidelity_path = root / manifest["candidates"][0]["pdt_fidelity"]["path"]
        value = json.loads(fidelity_path.read_text(encoding="utf-8"))
        value["coverage"]["complete"] = False
        fidelity_path.write_text(json.dumps(value), encoding="utf-8")
        manifest["candidates"][0]["pdt_fidelity"]["sha256"] = digest(fidelity_path)
        with self.assertRaisesRegex(ValueError, "coverage is incomplete"):
            MODULE.compose(
                proto, proto_sha, public, public_sha, manifest, root, allow_draft=True
            )

    def test_control_blocked_candidate_cannot_carry_fidelity(self):
        temporary, root, proto, proto_sha, public, public_sha, manifest = self.fixture()
        self.addCleanup(temporary.cleanup)
        manifest["candidates"][1]["pdt_fidelity"] = manifest["candidates"][0][
            "pdt_fidelity"
        ]

        with self.assertRaisesRegex(ValueError, "must not contain PDT evidence"):
            MODULE.compose(
                proto, proto_sha, public, public_sha, manifest, root, allow_draft=True
            )

    def test_fidelity_report_index_must_cover_every_repetition(self):
        temporary, root, proto, proto_sha, public, public_sha, manifest = self.fixture()
        self.addCleanup(temporary.cleanup)
        fidelity_path = root / manifest["candidates"][0]["pdt_fidelity"]["path"]
        value = json.loads(fidelity_path.read_text(encoding="utf-8"))
        value["report_index"][2]["repetition"] = 2
        fidelity_path.write_text(json.dumps(value), encoding="utf-8")
        manifest["candidates"][0]["pdt_fidelity"]["sha256"] = digest(fidelity_path)

        with self.assertRaisesRegex(ValueError, "report index is inconsistent"):
            MODULE.compose(
                proto, proto_sha, public, public_sha, manifest, root, allow_draft=True
            )

    def test_candidate_set_must_match_public_corpus(self):
        temporary, root, proto, proto_sha, public, public_sha, manifest = self.fixture()
        self.addCleanup(temporary.cleanup)
        manifest["candidates"][1]["candidate_id"] = "cand-other"
        with self.assertRaisesRegex(ValueError, "candidate set"):
            MODULE.compose(proto, proto_sha, public, public_sha, manifest, root, allow_draft=True)

    def test_exclusion_requires_a_pre_unblinding_repetition_ledger(self):
        temporary, root, proto, proto_sha, public, public_sha, manifest = self.fixture()
        self.addCleanup(temporary.cleanup)
        ledger = {
            "schema_version": "1.0.0",
            "candidate_id": "cand-0002",
            "classification": "infrastructure-invalid",
            "label_revealed": False,
            "planned_repetitions": [1, 2, 3],
            "valid_repetitions": [1],
            "invalid_repetitions": [
                {
                    "repetition": 2,
                    "attempts": 2,
                    "reasons": ["cluster-error", "cluster-error"],
                },
                {
                    "repetition": 3,
                    "attempts": 2,
                    "reasons": ["quota-error", "quota-error"],
                },
            ],
        }
        manifest["candidates"][1] = {
            "candidate_id": "cand-0002",
            "exclusion": {
                "reason_code": "insufficient-valid-repetitions",
                "reason": "two repetitions remained infrastructure-invalid",
                "decided_before_oracle_label": True,
                "label_revealed": False,
                "valid_repetitions": [1],
                "invalid_repetitions": [2, 3],
                "replacement_attempted": True,
                "evidence": write(root, "exclusion-2.json", ledger),
            },
        }

        result = MODULE.compose(
            proto, proto_sha, public, public_sha, manifest, root, allow_draft=True
        )

        self.assertEqual(1, result["collection_flow"]["complete_decision_pairs"])
        self.assertEqual(
            "insufficient-valid-repetitions",
            result["collection_flow"]["manifest_exclusions"][0]["reason_code"],
        )

    def test_exclusion_after_label_release_is_rejected(self):
        temporary, root, proto, proto_sha, public, public_sha, manifest = self.fixture()
        self.addCleanup(temporary.cleanup)
        manifest["candidates"][1]["exclusion"] = {
            "reason_code": "undesired-result",
            "reason": "remove after seeing the label",
        }

        with self.assertRaisesRegex(ValueError, "schema"):
            MODULE.compose(
                proto, proto_sha, public, public_sha, manifest, root, allow_draft=True
            )

    def test_exclusion_cannot_coexist_with_decision_or_oracle_evidence(self):
        temporary, root, proto, proto_sha, public, public_sha, manifest = self.fixture()
        self.addCleanup(temporary.cleanup)
        ledger = {
            "schema_version": "1.0.0",
            "candidate_id": "cand-0002",
            "classification": "infrastructure-invalid",
            "label_revealed": False,
            "planned_repetitions": [1, 2, 3],
            "valid_repetitions": [1],
            "invalid_repetitions": [
                {"repetition": 2, "attempts": 2, "reasons": ["quota", "quota"]},
                {"repetition": 3, "attempts": 2, "reasons": ["quota", "quota"]},
            ],
        }
        manifest["candidates"][1]["exclusion"] = {
            "reason_code": "insufficient-valid-repetitions",
            "reason": "two repetitions remained infrastructure-invalid",
            "decided_before_oracle_label": True,
            "label_revealed": False,
            "valid_repetitions": [1],
            "invalid_repetitions": [2, 3],
            "replacement_attempted": True,
            "evidence": write(root, "exclusion-2.json", ledger),
        }

        with self.assertRaisesRegex(ValueError, "must not contain decision"):
            MODULE.compose(
                proto, proto_sha, public, public_sha, manifest, root, allow_draft=True
            )

    def test_draft_protocol_is_fail_closed_by_default(self):
        temporary, root, proto, proto_sha, public, public_sha, manifest = self.fixture()
        self.addCleanup(temporary.cleanup)
        with self.assertRaisesRegex(ValueError, "frozen protocol"):
            MODULE.compose(proto, proto_sha, public, public_sha, manifest, root)


if __name__ == "__main__":
    unittest.main()
