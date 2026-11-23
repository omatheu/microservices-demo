import json
import os
import pathlib
import subprocess
import tempfile
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "experiment/scripts/wait-for-workload-stability.sh"


FAKE_KUBECTL = r"""#!/usr/bin/env bash
set -euo pipefail
if [[ "$1 $2" == "get deployments" ]]; then
  printf '%s\n' "${DEPLOYMENTS_JSON}"
elif [[ "$1 $2" == "get pods" ]]; then
  printf '%s\n' "${PODS_JSON}"
else
  exit 2
fi
"""


def deployment(name="frontend", available=True):
    replicas = 1
    return {
        "metadata": {"name": name, "generation": 1},
        "spec": {"replicas": replicas},
        "status": {
            "observedGeneration": 1,
            "availableReplicas": replicas if available else 0,
            "readyReplicas": replicas if available else 0,
            "updatedReplicas": replicas,
        },
    }


def pod(app="frontend", ready=True):
    return {
        "metadata": {"name": f"{app}-pod", "labels": {"app": app}},
        "status": {
            "phase": "Running",
            "conditions": [{"type": "Ready", "status": "True" if ready else "False"}],
            "containerStatuses": [{"ready": ready, "restartCount": 0}],
        },
    }


class WaitForWorkloadStabilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        kubectl = self.bin_dir / "kubectl"
        kubectl.write_text(FAKE_KUBECTL, encoding="utf-8")
        kubectl.chmod(0o755)
        self.output = self.root / "stability.json"

    def environment(self, deployments, pods):
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{self.bin_dir}:{environment['PATH']}",
                "NAMESPACE": "staging",
                "OUTPUT_FILE": str(self.output),
                "MINIMUM_EXPECTED_DEPLOYMENTS": "1",
                "STABILITY_WINDOW_SECONDS": "0",
                "STABILITY_TIMEOUT_SECONDS": "1",
                "POLL_INTERVAL_SECONDS": "1",
                "DEPLOYMENTS_JSON": json.dumps({"items": deployments}),
                "PODS_JSON": json.dumps({"items": pods}),
            }
        )
        return environment

    def test_healthy_workloads_pass_and_write_a_bound_receipt(self):
        result = subprocess.run(
            [str(SCRIPT)],
            cwd=REPO_ROOT,
            env=self.environment([deployment()], [pod()]),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(receipt["state"], "stable")
        self.assertEqual(receipt["classification"], "eligible")
        self.assertEqual(receipt["final_observation"]["unavailable_deployments"], 0)

    def test_unhealthy_non_candidate_workload_is_infrastructure_invalid(self):
        result = subprocess.run(
            [str(SCRIPT)],
            cwd=REPO_ROOT,
            env=self.environment([deployment(available=False)], [pod(ready=False)]),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 70)
        receipt = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(receipt["state"], "unstable")
        self.assertEqual(receipt["classification"], "infrastructure-invalid")

    def test_candidate_target_can_be_excluded_from_infrastructure_stability(self):
        environment = self.environment(
            [deployment("checkoutservice", available=False)],
            [pod("checkoutservice", ready=False)],
        )
        environment["EXCLUDED_DEPLOYMENTS"] = "checkoutservice"

        result = subprocess.run(
            [str(SCRIPT)],
            cwd=REPO_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(
            receipt["required"]["excluded_candidate_deployments"],
            ["checkoutservice"],
        )


if __name__ == "__main__":
    unittest.main()
