import os
import pathlib
import subprocess
import tempfile
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
LIBRARY = REPO_ROOT / "experiment/scripts/lib/port-forward-supervisor.sh"


FAKE_KUBECTL = r"""#!/usr/bin/env bash
set -euo pipefail
[[ "$1" == "port-forward" ]]
printf 'Forwarding from 127.0.0.1:18080 -> 80\n'
if [[ "${PORT_FORWARD_MODE}" == "exit" ]]; then
  sleep 0.2
  exit 0
fi
trap 'exit 0' TERM INT
while :; do sleep 1; done
"""


class PortForwardSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        kubectl = self.bin_dir / "kubectl"
        kubectl.write_text(FAKE_KUBECTL, encoding="utf-8")
        kubectl.chmod(0o755)

    def run_harness(self, mode):
        environment = os.environ.copy()
        environment.update(
            {
                "PATH": f"{self.bin_dir}:{environment['PATH']}",
                "PORT_FORWARD_MODE": mode,
                "SUPERVISOR_LIBRARY": str(LIBRARY),
                "FORWARD_LOG": str(self.root / f"{mode}.log"),
            }
        )
        command = r"""
set -euo pipefail
source "${SUPERVISOR_LIBRARY}"
start_supervised_port_forward staging frontend 18080 80 "${FORWARD_LOG}"
sleep 1
if assert_supervised_port_forwards test-phase; then
  status=0
else
  status=$?
fi
stop_supervised_port_forwards
exit "$status"
"""
        return subprocess.run(
            ["bash", "-c", command],
            cwd=REPO_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_live_tunnel_remains_eligible(self):
        result = self.run_harness("live")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_lost_tunnel_returns_dedicated_infrastructure_exit(self):
        result = self.run_harness("exit")
        self.assertEqual(result.returncode, 70, result.stderr)
        self.assertIn("was lost during test-phase", result.stderr)


if __name__ == "__main__":
    unittest.main()
