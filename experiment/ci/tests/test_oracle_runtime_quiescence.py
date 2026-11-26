import json
import os
import pathlib
import stat
import subprocess
import tempfile
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
LIBRARY_PATH = (
    REPO_ROOT / "experiment" / "scripts" / "lib" / "oracle-runtime-quiescence.sh"
)


class OracleRuntimeQuiescenceTests(unittest.TestCase):
    def test_waits_for_late_pods_and_runtime_resources_before_succeeding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            bin_path = root / "bin"
            bin_path.mkdir()
            counter_path = root / "pod-probes"
            resource_counter_path = root / "resource-probes"
            manifest_path = root / "runtime.yaml"
            cleanup_log = root / "cleanup.log"
            manifest_path.write_text("apiVersion: v1\nkind: List\nitems: []\n", encoding="utf-8")

            fake_kubectl = bin_path / "kubectl"
            fake_kubectl.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1 $2" == "get pods" ]]; then
  count=0
  [[ ! -f "$POD_PROBE_COUNTER" ]] || count=$(cat "$POD_PROBE_COUNTER")
  count=$((count + 1))
  printf '%s' "$count" >"$POD_PROBE_COUNTER"
  if (( count < 3 )); then
    printf '%s\n' '{"items":[{"status":{"phase":"Running"}}]}'
  else
    printf '%s\n' '{"items":[]}'
  fi
elif [[ "$1" == "get" && " $* " == *" --filename "* ]]; then
  count=0
  [[ ! -f "$RESOURCE_PROBE_COUNTER" ]] || count=$(cat "$RESOURCE_PROBE_COUNTER")
  count=$((count + 1))
  printf '%s' "$count" >"$RESOURCE_PROBE_COUNTER"
  if (( count < 4 )); then
    printf '%s\n' 'deployment.apps/oracle-harness'
  fi
else
  echo "unexpected kubectl arguments: $*" >&2
  exit 90
fi
""",
                encoding="utf-8",
            )
            fake_kubectl.chmod(fake_kubectl.stat().st_mode | stat.S_IXUSR)

            environment = os.environ.copy()
            environment.update(
                {
                    "PATH": f"{bin_path}:{environment['PATH']}",
                    "POD_PROBE_COUNTER": str(counter_path),
                    "RESOURCE_PROBE_COUNTER": str(resource_counter_path),
                    "LIBRARY_PATH": str(LIBRARY_PATH),
                    "MANIFEST_PATH": str(manifest_path),
                    "CLEANUP_LOG": str(cleanup_log),
                }
            )
            command = r"""
set -euo pipefail
source "$LIBRARY_PATH"
wait_for_oracle_runtime_quiescence oracle "$MANIFEST_PATH" "$CLEANUP_LOG" 5 1 0
printf '{"active":%s,"resources":%s,"observations":%s}\n' \
  "$ORACLE_CLEANUP_AFTER_ACTIVE_PODS" \
  "$ORACLE_CLEANUP_REMAINING_RESOURCES" \
  "$ORACLE_CLEANUP_OBSERVATIONS"
"""

            result = subprocess.run(
                ["bash", "-c", command],
                cwd=REPO_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            evidence = json.loads(result.stdout)
            self.assertEqual(evidence["active"], 0)
            self.assertEqual(evidence["resources"], 0)
            self.assertGreaterEqual(evidence["observations"], 4)
            self.assertGreaterEqual(int(counter_path.read_text(encoding="utf-8")), 3)
            self.assertGreaterEqual(
                int(resource_counter_path.read_text(encoding="utf-8")), 4
            )

    def test_runner_records_quiescence_evidence_for_every_cleanup(self):
        runner = (
            REPO_ROOT / "experiment" / "scripts" / "run-oracle-repetition.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("wait_for_oracle_runtime_quiescence", runner)
        self.assertIn('remaining_runtime_resources:', runner)
        self.assertIn('quiescence_window_seconds:', runner)
        self.assertIn('observed_quiescent_seconds:', runner)
        self.assertIn('schema_version: "1.1.0"', runner)


if __name__ == "__main__":
    unittest.main()
