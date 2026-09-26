import hashlib
import json
import os
import pathlib
import stat
import subprocess
import tempfile
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "run-oracle-repetition.sh"
POLICY_PATH = REPO_ROOT / "experiment" / "oracle" / "policy-v1.json"
IMAGE_PREFIX = "us-central1-docker.pkg.dev/project/repository"


class RunOracleRepetitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = SCRIPT_PATH.read_text(encoding="utf-8")

    def test_all_predeclared_pdt_deployments_can_reach_the_isolated_oracle(self):
        self.assertIn(
            "pdt_selected_alternative=$(jq -er '.selected_alternative' \"$pdt_decision\")",
            self.script,
        )
        self.assertIn('.id == $alternative', self.script)
        self.assertIn('.action == "deploy"', self.script)
        self.assertIn('(.predicted_metrics | type == "object")', self.script)
        self.assertIn('.repetition == $repetition', self.script)
        self.assertIn("PDT_PREDICTION_DECISION", self.script)
        self.assertIn(
            "PDT repetition prediction is not an input of the sealed candidate-level decision.",
            self.script,
        )
        self.assertIn("pdt-prediction-decision.json", self.script)
        self.assertNotIn(
            '== "$alternative_id" ]] || {\n      echo "Oracle alternative differs from the protected human decision.',
            self.script,
        )

    def test_oracle_run_persists_hash_bound_post_decision_fidelity(self):
        self.assertIn("calculate-pdt-fidelity.py", self.script)
        self.assertIn('--oracle-observation "${run_dir}/observation.json"', self.script)
        self.assertIn('fidelity_report="${run_dir}/pdt-fidelity.json"', self.script)
        self.assertIn('pdt_fidelity:', self.script)
        self.assertIn('fidelity_policy:', self.script)
        self.assertIn('pdt_prediction_decision:', self.script)

    def test_cloud_execution_is_fail_closed_before_kubectl(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            candidate_path = root / "candidate.json"
            control_path = root / "control.json"
            private_path = root / "private.json"
            snapshot_path = root / "snapshot.json"
            marker_path = root / "kubectl-called"
            bin_path = root / "bin"
            bin_path.mkdir()
            fake_kubectl = bin_path / "kubectl"
            fake_kubectl.write_text(
                "#!/usr/bin/env sh\n: > \"$KUBECTL_MARKER\"\nexit 99\n",
                encoding="utf-8",
            )
            fake_kubectl.chmod(fake_kubectl.stat().st_mode | stat.S_IXUSR)

            candidate = {
                "candidate_id": "cand-test",
                "confirmatory_eligibility": False,
                "alternatives": [
                    {
                        "id": "deploy-as-is",
                        "action": "deploy",
                        "configuration_changes": [],
                    }
                ],
            }
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            candidate_sha = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
            control_path.write_text(
                json.dumps(
                    {
                        "mechanism": "conventional-ci-cd-with-staging",
                        "candidate_id": "cand-test",
                        "decision": "block",
                        "control_decision_sealed": True,
                        "candidate_definition_sha256": candidate_sha,
                        "immutable_artifacts": [
                            {
                                "component": "checkoutservice",
                                "remote_reference": (
                                    f"{IMAGE_PREFIX}/checkoutservice@sha256:{'c' * 64}"
                                ),
                            }
                        ],
                        "staging": {"executed": True},
                    }
                ),
                encoding="utf-8",
            )
            private_path.write_text(
                json.dumps(
                    {
                        "candidate_id": "cand-test",
                        "candidate_definition_sha256": candidate_sha,
                        "repetitions": [1, 2, 3],
                        "control_decision": "block",
                        "treatment_decision": {
                            "decision": "block",
                            "source": "inherited-control-block",
                        },
                    }
                ),
                encoding="utf-8",
            )
            private_path.chmod(0o600)
            snapshot_path.write_text(
                json.dumps(
                    {
                        "binding": {
                            "source_namespace": "operational",
                            "source_namespace_uid": "namespace-uid",
                            "twin_object": {
                                "kind": "Deployment",
                                "name": "checkoutservice",
                            },
                        },
                        "synchronized_state": {
                            "workloads": [
                                {"name": "checkoutservice"},
                                {"name": "currencyservice"},
                            ]
                        },
                    }
                ),
                encoding="utf-8",
            )

            environment = os.environ.copy()
            environment.update(
                {
                    "PATH": f"{bin_path}:{environment['PATH']}",
                    "KUBECTL_MARKER": str(marker_path),
                    "MODE": "engineering",
                    "CANDIDATE_ID": "cand-test",
                    "CANDIDATE_DEFINITION": str(candidate_path),
                    "CONVENTIONAL_DECISION": str(control_path),
                    "PRIVATE_WORK_ITEM": str(private_path),
                    "SNAPSHOT_FILE": str(snapshot_path),
                    "ORACLE_POLICY": str(POLICY_PATH),
                    "ORACLE_HARNESS_IMAGE": f"{IMAGE_PREFIX}/oracle-harness@sha256:{'a' * 64}",
                    "CURRENCY_REFERENCE_IMAGE": f"{IMAGE_PREFIX}/currencyservice@sha256:{'b' * 64}",
                    "ALLOW_EXPERIMENTAL_CLOUD_EXECUTION": "false",
                    "COST_REVIEW_ACKNOWLEDGED": "false",
                    "ALLOW_ORACLE_CLOUD_EXECUTION": "false",
                }
            )

            result = subprocess.run(
                [str(SCRIPT_PATH)],
                cwd=REPO_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("starts billable GKE workloads and is disabled", result.stderr)
            self.assertFalse(marker_path.exists())


if __name__ == "__main__":
    unittest.main()
