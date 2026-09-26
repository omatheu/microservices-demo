import os
import pathlib
import subprocess
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "cleanup-oracle-workloads.sh"


class CleanupOracleWorkloadsTests(unittest.TestCase):
    def test_cleanup_is_disabled_before_kubernetes_access(self):
        environment = os.environ.copy()
        environment.update(
            {"ALLOW_ORACLE_CLEANUP": "false", "OUTPUT_FILE": "/tmp/not-written.json"}
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
        self.assertIn("requires ALLOW_ORACLE_CLEANUP=true", result.stderr)
        self.assertNotIn("reviewed experiment cluster", result.stderr)

    def test_cleanup_scope_is_explicit_and_never_targets_operational(self):
        rendered = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("namespace=oracle", rendered)
        self.assertIn("runtime_names=(checkoutservice", rendered)
        self.assertIn("network_policy_names=(oracle-deny-all", rendered)
        self.assertNotIn("--all", rendered)
        self.assertNotIn("namespace=operational", rendered)
        self.assertIn("operational_namespace_touched: false", rendered)
        self.assertIn("persistent_volumes_touched: false", rendered)


if __name__ == "__main__":
    unittest.main()
