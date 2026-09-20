import importlib.util
import hashlib
import json
import os
import pathlib
import subprocess
import tempfile
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "evaluate-oracle-preartifact.py"
POLICY_PATH = REPO_ROOT / "experiment" / "oracle" / "policy-v1.json"
SPEC = importlib.util.spec_from_file_location("evaluate_oracle_preartifact", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def policy():
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def item(operator_id, failure_kind, intended="harmful"):
    return {
        "operator_id": operator_id,
        "parameters": {"failure_kind": failure_kind},
        "intended_label": intended,
    }


class EvaluateOraclePreartifactTests(unittest.TestCase):
    def binding_fixture(self, directory):
        root = pathlib.Path(directory)
        workspace = root / "repo"
        workspace.mkdir()
        subprocess.run(["git", "init", "-q", str(workspace)], check=True)
        identity = {
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
        }
        (workspace / "base.txt").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(workspace), "add", "--all"], check=True)
        subprocess.run(
            ["git", "-C", str(workspace), "commit", "-q", "-m", "base"],
            check=True,
            env={**os.environ, **identity},
        )
        base_commit = subprocess.check_output(
            ["git", "-C", str(workspace), "rev-parse", "HEAD"], text=True
        ).strip()
        definition_path = workspace / "candidate.json"
        definition_path.write_text(
            json.dumps({"candidate_id": "cand-test"}), encoding="utf-8"
        )
        subprocess.run(["git", "-C", str(workspace), "add", "--all"], check=True)
        subprocess.run(
            ["git", "-C", str(workspace), "commit", "-q", "-m", "candidate"],
            check=True,
            env={**os.environ, **identity},
        )
        commit = subprocess.check_output(
            ["git", "-C", str(workspace), "rev-parse", "HEAD"], text=True
        ).strip()
        tree = subprocess.check_output(
            ["git", "-C", str(workspace), "rev-parse", "HEAD^{tree}"], text=True
        ).strip()
        definition_sha = hashlib.sha256(definition_path.read_bytes()).hexdigest()
        patch_path = root / "candidate.patch"
        patch_path.write_text("sealed patch\n", encoding="utf-8")
        patch_path.chmod(0o600)
        patch_sha = hashlib.sha256(patch_path.read_bytes()).hexdigest()
        local_path = root / "local.json"
        local = {
            "candidate_id": "cand-test",
            "local_decision": "block",
            "git": {
                "commit": commit,
                "tree": tree,
                "base_commit": base_commit,
                "dirty": False,
            },
        }
        local_path.write_text(json.dumps(local), encoding="utf-8")
        local_sha = hashlib.sha256(local_path.read_bytes()).hexdigest()
        private = {
            "candidate_id": "cand-test",
            "candidate_definition_sha256": definition_sha,
            "operator_id": "CTRL-CI-01",
            "parameters": {"failure_kind": "compile-error"},
        }
        work_order = {
            "candidate_id": "cand-test",
            "candidate_definition_sha256": definition_sha,
            "operator_id": "CTRL-CI-01",
            "parameters": {"failure_kind": "compile-error"},
            "source_binding": {
                "base_commit": base_commit,
                "candidate_commit": commit,
                "candidate_tree": tree,
                "patch_sha256": patch_sha,
                "worktree_clean": True,
            },
        }
        conventional = {
            "candidate_id": "cand-test",
            "candidate_definition_sha256": definition_sha,
            "decision": "block",
            "control_decision_sealed": True,
            "staging": {"executed": False},
            "immutable_artifacts": [],
            "evidence": {
                "local_ci_decision": {"sha256": local_sha},
                "candidate_definition": {"sha256": definition_sha},
            },
        }
        return (
            definition_path,
            private,
            work_order,
            patch_path,
            conventional,
            local,
            local_path,
            workspace,
        )

    def test_binding_validation_accepts_exact_clean_candidate_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            values = self.binding_fixture(directory)

            candidate_id = MODULE.validate_bindings(*values)

            self.assertEqual(candidate_id, "cand-test")

    def test_binding_validation_rejects_patch_substitution(self):
        with tempfile.TemporaryDirectory() as directory:
            values = list(self.binding_fixture(directory))
            values[3].write_text("substituted\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "patch hash"):
                MODULE.validate_bindings(*values)

    def test_compile_failure_is_observed_without_using_intended_label(self):
        def failed_go_test(_workspace, _image):
            return {
                "execution_valid": True,
                "invalid_reason": None,
                "exit_code": 1,
                "stdout": "FAIL\n",
                "stderr": "",
            }

        result = MODULE.evaluate(
            policy(), item("CTRL-CI-01", "compile-error", intended="safe"),
            pathlib.Path("/unused"), go_runner=failed_go_test,
        )

        self.assertTrue(result["requirement_violated"])
        self.assertNotIn("intended_label", result)

    def test_go_runtime_failure_is_invalid_not_harmful(self):
        def unavailable_runtime(_workspace, _image):
            return {
                "execution_valid": False,
                "invalid_reason": "go-verification-runtime-error",
                "exit_code": 125,
                "stdout": "",
                "stderr": "daemon unavailable",
            }

        result = MODULE.evaluate(
            policy(), item("CTRL-CI-01", "unit-test-regression"),
            pathlib.Path("/unused"), go_runner=unavailable_runtime,
        )

        self.assertFalse(result["execution_valid"])
        self.assertFalse(result["requirement_violated"])

    def test_synthetic_secret_is_detected_with_redacted_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = pathlib.Path(directory)
            source = workspace / "src" / "checkoutservice"
            source.mkdir(parents=True)
            synthetic_prefix = "AKIA"
            synthetic_suffix = "QWERTYUIOPASDFGH"
            (source / "candidate.txt").write_text(
                f'aws_access_key_id = "{synthetic_prefix}{synthetic_suffix}"\n',
                encoding="utf-8",
            )

            result = MODULE.evaluate(
                policy(), item("CTRL-SEC-01", "synthetic-secret-canary"), workspace
            )

            self.assertTrue(result["requirement_violated"])
            self.assertTrue(result["details"]["redacted_findings"][0]["value_redacted"])

    def test_privileged_rendered_container_is_detected_independently(self):
        rendered = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkoutservice
  namespace: staging
spec:
  template:
    spec:
      containers:
        - name: server
          securityContext:
            privileged: true
"""

        result = MODULE.evaluate(
            policy(), item("CTRL-SEC-01", "prohibited-container-privilege"),
            pathlib.Path("/unused"), renderer=lambda _workspace, _overlay: rendered,
        )

        self.assertTrue(result["requirement_violated"])
        self.assertEqual(
            result["details"]["privileged_containers"][0]["deployment"],
            "checkoutservice",
        )


if __name__ == "__main__":
    unittest.main()
