import os
import pathlib
import subprocess
import tempfile
import textwrap
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "experiment" / "scripts" / "scan-sealed-candidate-tree.sh"


class SealedCandidateSecretScanTests(unittest.TestCase):
    def test_scan_uses_only_the_committed_tree(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = pathlib.Path(temporary_directory)
            repository = root / "repository"
            bin_directory = root / "bin"
            repository.mkdir()
            bin_directory.mkdir()
            (repository / "experiment" / "ci").mkdir(parents=True)
            (repository / "experiment" / "ci" / "gitleaks.toml").write_text(
                "title = 'test policy'\n", encoding="utf-8"
            )
            (repository / "tracked.txt").write_text("sealed\n", encoding="utf-8")

            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"], cwd=repository, check=True
            )
            subprocess.run(["git", "add", "."], cwd=repository, check=True)
            subprocess.run(
                ["git", "commit", "-qm", "sealed tree"], cwd=repository, check=True
            )

            (repository / "gha-creds-runtime.json").write_text(
                "temporary credential", encoding="utf-8"
            )
            docker = bin_directory / "docker"
            docker.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    mount_spec=""
                    while (($#)); do
                      if [[ "$1" == "-v" ]]; then
                        mount_spec=$2
                        shift 2
                        continue
                      fi
                      shift
                    done
                    scan_root=${mount_spec%%:/candidate:ro}
                    [[ -f "${scan_root}/tracked.txt" ]]
                    [[ -f "${scan_root}/experiment/ci/gitleaks.toml" ]]
                    [[ ! -e "${scan_root}/gha-creds-runtime.json" ]]
                    """
                ),
                encoding="utf-8",
            )
            docker.chmod(0o755)

            environment = os.environ.copy()
            environment["PATH"] = f"{bin_directory}:{environment['PATH']}"
            result = subprocess.run(
                [str(SCRIPT), str(repository), "HEAD", "gitleaks:test"],
                cwd=repository,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)

    def test_runner_selects_sealed_scan_only_in_confirmatory_mode(self):
        runner = (
            REPO_ROOT / "experiment" / "scripts" / "run-conventional-ci-local.sh"
        ).read_text(encoding="utf-8")

        self.assertIn('if [[ "${MODE}" == "confirmatory" ]]', runner)
        self.assertIn('"${SCRIPT_DIR}/scan-sealed-candidate-tree.sh"', runner)
        self.assertIn('"${GIT_COMMIT}"', runner)


if __name__ == "__main__":
    unittest.main()
