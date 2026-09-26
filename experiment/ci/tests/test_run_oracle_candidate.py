import hashlib
import importlib.util
import json
import os
import pathlib
import stat
import subprocess
import tempfile
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "run-oracle-candidate.py"
SPEC = importlib.util.spec_from_file_location("run_oracle_candidate", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def write(path, value, mode=0o644):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(mode)
    return path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OracleCandidateRunnerTests(unittest.TestCase):
    def test_matrix_is_complete_and_sequentially_ordered(self):
        result = MODULE.matrix(["deploy-as-is", "capacity-safe"], [1, 2, 3])

        self.assertEqual(
            result,
            [
                {"alternative_id": "deploy-as-is", "repetition": 1},
                {"alternative_id": "deploy-as-is", "repetition": 2},
                {"alternative_id": "deploy-as-is", "repetition": 3},
                {"alternative_id": "capacity-safe", "repetition": 1},
                {"alternative_id": "capacity-safe", "repetition": 2},
                {"alternative_id": "capacity-safe", "repetition": 3},
            ],
        )

    def test_prediction_resolution_uses_hashes_and_prelabel_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            decisions = []
            for repetition in (1, 2):
                path = write(root / f"decision-{repetition}.json", {"repetition": repetition})
                decisions.append(
                    {
                        "repetition": repetition,
                        "path": f"untrusted/original-{repetition}.json",
                        "sha256": digest(path),
                    }
                )
            ledger = write(
                root / "ledger.json",
                {
                    "label_revealed": False,
                    "valid_repetitions": [1, 2],
                    "invalid_repetitions": [
                        {
                            "repetition": 3,
                            "attempts": 2,
                            "reasons": ["timeout", "replacement-timeout"],
                        }
                    ],
                },
            )
            pdt = {
                "mechanism": "candidate-level-pdt-decision",
                "repetition": None,
                "repetition_aggregation": {
                    "valid_repetitions": [1, 2],
                    "invalid_repetitions": [3],
                },
                "evidence": {
                    "pdt_decisions": decisions,
                    "infrastructure_invalid_ledger": {
                        "path": "untrusted/ledger.json",
                        "sha256": digest(ledger),
                    },
                },
            }

            predictions, resolved_ledger = MODULE.resolve_prediction_inputs(
                pdt, root, [1, 2, 3], 2
            )

            self.assertEqual(set(predictions), {1, 2})
            self.assertEqual(resolved_ledger, ledger)

    def test_prediction_resolution_rejects_missing_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            entries = []
            for repetition in (1, 2):
                decision = write(
                    root / f"decision-{repetition}.json", {"repetition": repetition}
                )
                entries.append(
                    {"repetition": repetition, "sha256": digest(decision)}
                )
            pdt = {
                "mechanism": "candidate-level-pdt-decision",
                "repetition": None,
                "repetition_aggregation": {
                    "valid_repetitions": [1, 2],
                    "invalid_repetitions": [3],
                },
                "evidence": {"pdt_decisions": entries},
            }
            with self.assertRaisesRegex(ValueError, "require the sealed"):
                MODULE.resolve_prediction_inputs(pdt, directory, [1, 2, 3], 2)

    def test_public_summary_rejects_oracle_labels_at_any_depth(self):
        safe = {
            "candidate_id": "cand-opaque",
            "execution_index": [{"repetition": 1, "observation_sha256": "a" * 64}],
        }
        self.assertEqual(MODULE.recursively_find_keys(safe), [])

        leaked = {**safe, "nested": {"observed_deploy_as_is_label": "harmful"}}
        self.assertEqual(
            MODULE.recursively_find_keys(leaked), ["observed_deploy_as_is_label"]
        )

    def test_runtime_cloud_gates_fail_before_unlock_or_output_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            pipeline = root / "evidence" / "pipeline" / "paired-candidate"
            candidate = {
                "candidate_id": "cand-opaque",
                "confirmatory_eligibility": False,
                "alternatives": [
                    {
                        "id": "deploy-as-is",
                        "action": "deploy",
                        "configuration_changes": [],
                        "change_cost": 0,
                    },
                    {
                        "id": "block",
                        "action": "block",
                        "configuration_changes": [],
                        "change_cost": 10,
                    },
                ],
            }
            candidate_path = write(root / "candidate.json", candidate)
            write(pipeline / "candidate-definition.json", candidate)
            write(
                pipeline / "conventional-decision.json",
                {
                    "mechanism": "conventional-ci-cd-with-staging",
                    "candidate_id": "cand-opaque",
                    "candidate_definition_sha256": digest(candidate_path),
                    "control_decision_sealed": True,
                    "decision": "block",
                    "staging": {"executed": True},
                    "immutable_artifacts": [
                        {
                            "component": "checkoutservice",
                            "remote_reference": "registry.example/checkout@sha256:"
                            + "c" * 64,
                        }
                    ],
                },
            )
            write(
                pipeline / "summary.json",
                {"candidate_id": "cand-opaque", "control_decision": "block"},
            )
            write(pipeline / "status.json", {"state": "completed"})
            protocol = write(
                root / "protocol.json",
                {
                    "status": "pre-registration-candidate",
                    "confirmatory_collection_allowed": False,
                    "frozen_at": None,
                    "research_design": {"technical_repetitions_per_candidate": 3},
                    "aggregation": {"minimum_valid_repetitions": 2},
                },
            )
            public = write(root / "public.json", {})
            oracle = write(root / "oracle.json", {}, mode=0o600)
            output = root / "output"
            environment = os.environ.copy()
            environment.update(
                {
                    "ALLOW_EXPERIMENTAL_CLOUD_EXECUTION": "false",
                    "COST_REVIEW_ACKNOWLEDGED": "false",
                    "ALLOW_ORACLE_CLOUD_EXECUTION": "false",
                }
            )

            result = subprocess.run(
                [
                    str(SCRIPT_PATH),
                    "--mode",
                    "engineering",
                    "--allow-draft",
                    "--candidate-id",
                    "cand-opaque",
                    "--candidate-definition",
                    str(candidate_path),
                    "--pipeline-directory",
                    str(pipeline),
                    "--evidence-root",
                    str(root / "evidence"),
                    "--public-corpus",
                    str(public),
                    "--oracle-manifest",
                    str(oracle),
                    "--protocol",
                    str(protocol),
                    "--output-directory",
                    str(output),
                ],
                cwd=REPO_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("disabled until all cloud", result.stderr)
            self.assertFalse(output.exists())

    def test_private_output_directory_permissions_are_restrictive(self):
        with tempfile.TemporaryDirectory() as directory:
            output, public, private = MODULE.ensure_output_directories(
                pathlib.Path(directory) / "candidate-oracle"
            )

            self.assertEqual(stat.S_IMODE(output.stat().st_mode) & 0o077, 0)
            self.assertEqual(stat.S_IMODE(private.stat().st_mode) & 0o077, 0)
            self.assertEqual(stat.S_IMODE(public.stat().st_mode), 0o755)


if __name__ == "__main__":
    unittest.main()
