import hashlib
import importlib.util
import json
import pathlib
import stat
import subprocess
import tempfile
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = (
    REPO_ROOT / "experiment" / "scripts" / "prepare-sealed-preartifact-inputs.py"
)
SPEC = importlib.util.spec_from_file_location(
    "prepare_sealed_preartifact_inputs", SCRIPT_PATH
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


CANDIDATE_ID = "cand-abcdefghijklmnop"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PrepareSealedPreartifactInputsTests(unittest.TestCase):
    def repository(self, root):
        workspace = pathlib.Path(root) / "source"
        workspace.mkdir()
        subprocess.check_call(["git", "init", "-q", str(workspace)])
        subprocess.check_call(
            ["git", "-C", str(workspace), "config", "user.name", "Test"]
        )
        subprocess.check_call(
            ["git", "-C", str(workspace), "config", "user.email", "test@example.invalid"]
        )
        (workspace / "README.md").write_text("base\n", encoding="utf-8")
        subprocess.check_call(["git", "-C", str(workspace), "add", "README.md"])
        subprocess.check_call(
            ["git", "-C", str(workspace), "commit", "-q", "-m", "base"]
        )
        base = subprocess.check_output(
            ["git", "-C", str(workspace), "rev-parse", "HEAD"], text=True
        ).strip()
        candidate_path = (
            workspace
            / "experiment"
            / "pdt"
            / "candidates"
            / f"{CANDIDATE_ID}.json"
        )
        candidate_path.parent.mkdir(parents=True)
        candidate_path.write_text(
            json.dumps(
                {
                    "candidate_id": CANDIDATE_ID,
                    "confirmatory_eligibility": True,
                    "alternatives": [],
                }
            ),
            encoding="utf-8",
        )
        source = workspace / "src" / "checkoutservice" / "candidate_regression_test.go"
        source.parent.mkdir(parents=True)
        source.write_text("package main\nfunc broken( {\n", encoding="utf-8")
        subprocess.check_call(["git", "-C", str(workspace), "add", "--all"])
        subprocess.check_call(
            ["git", "-C", str(workspace), "commit", "-q", "-m", "candidate"]
        )
        head = subprocess.check_output(
            ["git", "-C", str(workspace), "rev-parse", "HEAD"], text=True
        ).strip()
        tree = subprocess.check_output(
            ["git", "-C", str(workspace), "rev-parse", "HEAD^{tree}"], text=True
        ).strip()
        return workspace, candidate_path, base, head, tree

    def values(self, candidate_path, base, head, tree, local_ci_sha):
        oracle = {
            "corpus_id": "corpus-test",
            "candidates": [
                {
                    "candidate_id": CANDIDATE_ID,
                    "operator_id": "CTRL-CI-01",
                    "parameters": {"failure_kind": "compile-error"},
                    "intended_label": "harmful",
                }
            ],
        }
        local_ci = {
            "candidate_id": CANDIDATE_ID,
            "local_decision": "block",
            "git": {
                "base_commit": base,
                "commit": head,
                "tree": tree,
                "dirty": False,
            },
        }
        control = {
            "mechanism": "conventional-ci-cd-with-staging",
            "candidate_id": CANDIDATE_ID,
            "decision": "block",
            "control_decision_sealed": True,
            "candidate_definition_sha256": sha256(candidate_path),
            "staging": {"executed": False},
            "immutable_artifacts": [],
            "evidence": {"local_ci_decision": {"sha256": local_ci_sha}},
        }
        return oracle, local_ci, control

    def test_reconstructs_private_patch_and_work_order_from_sealed_git(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, candidate_path, base, head, tree = self.repository(directory)
            local_ci_path = pathlib.Path(directory) / "local-ci.json"
            local_ci_path.write_text("placeholder", encoding="utf-8")
            local_sha = sha256(local_ci_path)
            oracle, local_ci, control = self.values(
                candidate_path, base, head, tree, local_sha
            )

            patch, work_order = MODULE.prepare(
                workspace,
                oracle,
                candidate_path,
                control,
                local_ci,
                local_sha,
                CANDIDATE_ID,
            )

            self.assertIn("candidate_regression_test.go", patch)
            self.assertEqual(work_order["operator_id"], "CTRL-CI-01")
            self.assertEqual(work_order["source_binding"]["base_commit"], base)
            self.assertEqual(work_order["source_binding"]["candidate_commit"], head)
            self.assertEqual(
                work_order["source_binding"]["patch_sha256"],
                hashlib.sha256(patch.encode("utf-8")).hexdigest(),
            )
            self.assertNotIn("intended_label", work_order)

    def test_rejects_source_substitution(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace, candidate_path, base, head, tree = self.repository(directory)
            oracle, local_ci, control = self.values(
                candidate_path, base, head, tree, "a" * 64
            )
            local_ci["git"]["tree"] = "f" * 40

            with self.assertRaisesRegex(ValueError, "differs from local CI"):
                MODULE.prepare(
                    workspace,
                    oracle,
                    candidate_path,
                    control,
                    local_ci,
                    "a" * 64,
                    CANDIDATE_ID,
                )

    def test_cli_outputs_are_private_and_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            workspace, candidate_path, base, head, tree = self.repository(directory)
            local_ci_path = root / "local-ci.json"
            oracle_path = root / "oracle.json"
            control_path = root / "control.json"
            local_ci_path.write_text("{}", encoding="utf-8")
            local_sha = sha256(local_ci_path)
            oracle, local_ci, control = self.values(
                candidate_path, base, head, tree, local_sha
            )
            local_ci_path.write_text(json.dumps(local_ci), encoding="utf-8")
            local_sha = sha256(local_ci_path)
            control["evidence"]["local_ci_decision"]["sha256"] = local_sha
            oracle_path.write_text(json.dumps(oracle), encoding="utf-8")
            oracle_path.chmod(0o600)
            control_path.write_text(json.dumps(control), encoding="utf-8")
            patch_path = root / "private" / "candidate.patch"
            work_order_path = root / "private" / "work-order.json"

            completed = subprocess.run(
                [
                    str(SCRIPT_PATH),
                    "--source-workspace",
                    str(workspace),
                    "--oracle-manifest",
                    str(oracle_path),
                    "--candidate-id",
                    CANDIDATE_ID,
                    "--candidate-definition",
                    str(candidate_path),
                    "--conventional-decision",
                    str(control_path),
                    "--local-ci-decision",
                    str(local_ci_path),
                    "--work-order-output",
                    str(work_order_path),
                    "--patch-output",
                    str(patch_path),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

            self.assertEqual(stat.S_IMODE(patch_path.stat().st_mode) & 0o077, 0)
            self.assertEqual(stat.S_IMODE(work_order_path.stat().st_mode) & 0o077, 0)
            repeated = subprocess.run(
                [
                    str(SCRIPT_PATH),
                    "--source-workspace",
                    str(workspace),
                    "--oracle-manifest",
                    str(oracle_path),
                    "--candidate-id",
                    CANDIDATE_ID,
                    "--candidate-definition",
                    str(candidate_path),
                    "--conventional-decision",
                    str(control_path),
                    "--local-ci-decision",
                    str(local_ci_path),
                    "--work-order-output",
                    str(work_order_path),
                    "--patch-output",
                    str(patch_path),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(repeated.returncode, 0)


if __name__ == "__main__":
    unittest.main()
