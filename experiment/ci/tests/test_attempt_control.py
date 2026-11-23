import os
import pathlib
import subprocess
import tempfile
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
LIBRARY = REPO_ROOT / "experiment/scripts/lib/attempt-control.sh"


class AttemptControlTests(unittest.TestCase):
    def test_first_failure_is_captured_and_second_attempt_runs_under_err_trap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            state = root / "attempt-count"
            trap_marker = root / "err-trap-fired"
            fake = root / "fake-attempt.sh"
            fake.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
count=0
[[ ! -f \"${ATTEMPT_STATE}\" ]] || count=$(<\"${ATTEMPT_STATE}\")
count=$((count + 1))
printf '%s\\n' \"$count\" >\"${ATTEMPT_STATE}\"
printf 'attempt-%s\\n' \"$count\"
(( count > 1 )) || exit 7
""",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            harness = root / "harness.sh"
            harness.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
source \"${ATTEMPT_LIBRARY}\"
on_error() { printf 'fired\\n' >\"${TRAP_MARKER}\"; exit 99; }
trap on_error ERR
for attempt in 1 2; do
  run_logged_attempt status \"${LOG_DIR}/attempt-${attempt}.log\" on_error \"${FAKE_ATTEMPT}\"
  printf '%s\\n' \"$status\"
  (( status == 0 )) && break
done
""",
                encoding="utf-8",
            )
            harness.chmod(0o755)
            environment = os.environ.copy()
            environment.update(
                {
                    "ATTEMPT_LIBRARY": str(LIBRARY),
                    "ATTEMPT_STATE": str(state),
                    "TRAP_MARKER": str(trap_marker),
                    "LOG_DIR": str(root),
                    "FAKE_ATTEMPT": str(fake),
                }
            )

            result = subprocess.run(
                [str(harness)],
                cwd=REPO_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), ["attempt-1", "7", "attempt-2", "0"])
            self.assertEqual(state.read_text(encoding="utf-8").strip(), "2")
            self.assertFalse(trap_marker.exists())


if __name__ == "__main__":
    unittest.main()
