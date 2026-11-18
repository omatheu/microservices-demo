import json
import pathlib
import re
import subprocess
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "experiment" / "scripts" / "run-pdt-cycle.sh"
RUNTIME_MANIFEST = REPO_ROOT / "experiment" / "pdt" / "runtime-manifest.json"


class RunPdtControllerRuntimeTests(unittest.TestCase):
    def test_cycle_executes_immutable_controller_in_pdt_system(self):
        rendered = RUNNER.read_text(encoding="utf-8")

        self.assertIn("PDT_CONTROLLER_IMAGE", rendered)
        self.assertIn("checkout-pdt-controller@sha256:", rendered)
        self.assertIn("prepare-pdt-controller-job.py", rendered)
        self.assertIn('kubectl apply -f "$controller_manifest"', rendered)
        self.assertIn("--namespace pdt-system", rendered)
        self.assertIn('kubectl logs --namespace pdt-system "job/${controller_job}"', rendered)

    def test_runtime_plan_must_match_the_preflight_plan(self):
        rendered = RUNNER.read_text(encoding="utf-8")

        self.assertIn("controller-plan.normalized.json", rendered)
        self.assertIn("controller-runtime-plan.normalized.json", rendered)
        self.assertIn("plans_equivalent", rendered)
        self.assertIn('cmp "${cycle_dir}/controller-plan.normalized.json"', rendered)

    def test_runtime_plan_accepts_controller_utc_timestamp_precision(self):
        rendered = RUNNER.read_text(encoding="utf-8")
        match = re.search(
            r"^controller_generated_at_pattern='([^']+)'$", rendered, re.MULTILINE
        )
        self.assertIsNotNone(match)
        pattern = match.group(1)

        for timestamp in (
            "2026-11-17T23:43:08Z",
            "2026-11-17T23:43:08.230028Z",
        ):
            completed = subprocess.run(
                [
                    "jq",
                    "-n",
                    "-e",
                    "--arg",
                    "pattern",
                    pattern,
                    "--arg",
                    "timestamp",
                    timestamp,
                    "$timestamp | test($pattern)",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)

        invalid = subprocess.run(
            [
                "jq",
                "-n",
                "-e",
                "--arg",
                "pattern",
                pattern,
                "--arg",
                "timestamp",
                "2026-11-17T23:43:08+00:00",
                "$timestamp | test($pattern)",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(0, invalid.returncode)

    def test_controller_cleanup_is_part_of_success_and_failure_paths(self):
        rendered = RUNNER.read_text(encoding="utf-8")

        self.assertIn("cleanup_controller()", rendered)
        self.assertGreaterEqual(rendered.count("cleanup_controller"), 5)
        self.assertIn("kubectl delete -f", rendered)

    def test_frozen_runtime_scope_includes_the_controller_rbac(self):
        manifest = json.loads(RUNTIME_MANIFEST.read_text(encoding="utf-8"))
        paths = {item["path"] for item in manifest["files"]}

        self.assertIn("infra/terraform/github-actions.tf", paths)
        self.assertIn("experiment/scripts/publish-experiment-runtimes.sh", paths)


if __name__ == "__main__":
    unittest.main()
