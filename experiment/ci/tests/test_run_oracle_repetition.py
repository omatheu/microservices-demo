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
                        "decision": "approve",
                        "control_decision_sealed": True,
                        "candidate_definition_sha256": candidate_sha,
                        "immutable_artifacts": [],
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
                        "control_decision": "approve",
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
