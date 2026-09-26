import json
import os
import pathlib
import subprocess
import tempfile
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "cleanup-experimental-workloads.sh"


FAKE_KUBECTL = r"""#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "${KUBECTL_LOG}"
if [[ "$*" == "config current-context" ]]; then
  printf '%s\n' "${FAKE_CONTEXT}"
elif [[ "$1 $2" == "get pods" ]]; then
  if [[ -f "${CLEANUP_MARKER}" ]]; then
    printf '%s\n' '{"items": []}'
  else
    printf '%s\n' '{"items": [{"status": {"phase": "Running"}}]}'
  fi
elif [[ "$1" == "delete" ]]; then
  touch "${CLEANUP_MARKER}"
else
  printf 'unexpected kubectl arguments: %s\n' "$*" >&2
  exit 1
fi
"""


class CleanupExperimentalWorkloadsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        kubectl = self.bin_dir / "kubectl"
        kubectl.write_text(FAKE_KUBECTL, encoding="utf-8")
        kubectl.chmod(0o755)
        self.output = self.root / "cleanup.json"
        self.log = self.root / "kubectl.log"
        self.marker = self.root / "cleaned"

    def environment(self):
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{self.bin_dir}:{environment['PATH']}",
                "ALLOW_EXPERIMENTAL_CLEANUP": "true",
                "OUTPUT_FILE": str(self.output),
                "KUBECTL_LOG": str(self.log),
                "CLEANUP_MARKER": str(self.marker),
                "FAKE_CONTEXT": "gke_microservices-demo-tcc_us-central1_online-boutique-experiment",
            }
        )
        return environment

    def run_script(self, environment=None):
        return subprocess.run(
            [str(SCRIPT_PATH)],
            cwd=REPO_ROOT,
            env=environment or self.environment(),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cleanup_is_restricted_and_records_zero_remaining_pods(self):
        result = self.run_script()

        self.assertEqual(result.returncode, 0, result.stderr)
        evidence = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(evidence["allowed_namespaces"], ["staging", "pdt", "pdt-system"])
        self.assertEqual(evidence["before_active_pods"], 3)
        self.assertEqual(evidence["after_active_pods"], 0)
        self.assertTrue(evidence["cleanup_complete"])
        self.assertFalse(evidence["operational_namespace_touched"])
        self.assertFalse(evidence["oracle_namespace_touched"])
        self.assertFalse(evidence["persistent_volumes_touched"])

        calls = self.log.read_text(encoding="utf-8").splitlines()
        deletes = [call for call in calls if call.startswith("delete ")]
        self.assertEqual(
            deletes,
            [
                "delete deployments.apps --all --namespace staging --ignore-not-found --wait=false",
                "delete deployments.apps --all --namespace pdt --ignore-not-found --wait=false",
                "delete jobs.batch --all --namespace pdt-system --ignore-not-found --wait=false",
            ],
        )
        self.assertFalse(any("operational" in call or "oracle" in call for call in deletes))

    def test_cleanup_refuses_to_call_kubectl_without_explicit_gate(self):
        environment = self.environment()
        environment["ALLOW_EXPERIMENTAL_CLEANUP"] = "false"

        result = self.run_script(environment)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ALLOW_EXPERIMENTAL_CLEANUP=true", result.stderr)
        self.assertFalse(self.log.exists())

    def test_cleanup_refuses_a_different_cluster_context_before_deletion(self):
        environment = self.environment()
        environment["FAKE_CONTEXT"] = "gke_other-project_us-central1_other-cluster"

        result = self.run_script(environment)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside the reviewed experiment cluster", result.stderr)
        calls = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(calls, ["config current-context"])


if __name__ == "__main__":
    unittest.main()
