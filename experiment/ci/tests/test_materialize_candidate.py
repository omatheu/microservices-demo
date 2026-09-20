import importlib.util
import itertools
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "materialize-candidate.py"
PROTOCOL_PATH = REPO_ROOT / "experiment" / "protocol" / "protocol-v1.json"
SPEC = importlib.util.spec_from_file_location("materialize_candidate", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def entry(operator_id, parameters, candidate_id="cand-abcdefghijklmnop"):
    return {
        "candidate_id": candidate_id,
        "operator_id": operator_id,
        "parameters": parameters,
        "stratum": "test",
        "intended_label": "harmful",
        "target_component": "checkoutservice",
        "context_dependency": "test",
    }


def oracle(candidate):
    return {
        "corpus_id": "corpus-test",
        "confirmatory_eligible": False,
        "candidates": [candidate],
    }


class MaterializeCandidateTests(unittest.TestCase):
    def workspace(self, root):
        root = pathlib.Path(root)
        checkout = root / "src" / "checkoutservice"
        recommendation = root / "src" / "recommendationservice"
        kustomize = root / "kustomize" / "base"
        checkout.mkdir(parents=True)
        recommendation.mkdir(parents=True)
        kustomize.mkdir(parents=True)
        payment = root / "src" / "paymentservice"
        payment.mkdir(parents=True)
        currency = root / "src" / "currencyservice"
        currency.mkdir(parents=True)
        shutil.copy2(REPO_ROOT / "src" / "checkoutservice" / "main.go", checkout)
        shutil.copy2(
            REPO_ROOT / "src" / "recommendationservice" / "recommendation_server.py",
            recommendation,
        )
        shutil.copy2(REPO_ROOT / "src" / "paymentservice" / "server.js", payment)
        shutil.copy2(REPO_ROOT / "src" / "currencyservice" / "server.js", currency)
        shutil.copy2(REPO_ROOT / "kustomize" / "base" / "checkoutservice.yaml", kustomize)
        return root

    def test_safe_control_changes_source_without_oracle_leak(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = self.workspace(temporary_directory)
            candidate = entry("CTRL-SAFE-01", {"variant": "log-message-only"})

            _, definition, changed = MODULE.materialize(
                workspace, oracle(candidate), candidate["candidate_id"]
            )

            content = (workspace / "src" / "checkoutservice" / "main.go").read_text()
            self.assertIn("Tracing disabled for this process.", content)
            self.assertIn("src/checkoutservice/main.go", changed)
            self.assertEqual(
                MODULE.recursively_find_keys(definition, MODULE.FORBIDDEN_DEFINITION_KEYS),
                [],
            )
            self.assertFalse(definition["confirmatory_eligibility"])

    def test_cpu_candidate_uses_same_deploy_as_is_patch_and_restore_option(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = self.workspace(temporary_directory)
            candidate = entry("INF-CPU-01", {"cpu_limit": "75m"})

            _, definition, changed = MODULE.materialize(
                workspace, oracle(candidate), candidate["candidate_id"]
            )

            deploy_as_is = next(
                item for item in definition["alternatives"] if item["id"] == "deploy-as-is"
            )
            restore = next(
                item
                for item in definition["alternatives"]
                if item["id"] == "restore-baseline-cpu"
            )
            resources = deploy_as_is["configuration_changes"][0]["patch"]["spec"][
                "template"
            ]["spec"]["containers"][0]["resources"]
            self.assertEqual(resources["requests"]["cpu"], "75m")
            self.assertEqual(resources["limits"]["cpu"], "75m")
            self.assertEqual(restore["change_cost"], 1)
            self.assertEqual(
                changed, ["experiment/pdt/candidates/cand-abcdefghijklmnop.json"]
            )

    def test_ci_regression_creates_a_failing_test_fixture(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = self.workspace(temporary_directory)
            candidate = entry("CTRL-CI-01", {"failure_kind": "unit-test-regression"})

            MODULE.materialize(workspace, oracle(candidate), candidate["candidate_id"])

            regression = (
                workspace / "src" / "checkoutservice" / "candidate_regression_test.go"
            ).read_text()
            self.assertIn("t.Fatal", regression)
            self.assertIn("synthetic candidate regression", regression)

    def test_security_privilege_canary_changes_manifest(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = self.workspace(temporary_directory)
            candidate = entry(
                "CTRL-SEC-01", {"failure_kind": "prohibited-container-privilege"}
            )

            MODULE.materialize(workspace, oracle(candidate), candidate["candidate_id"])

            manifest = (
                workspace / "kustomize" / "base" / "checkoutservice.yaml"
            ).read_text()
            self.assertIn("privileged: true", manifest)

    def test_replica_control_scales_to_zero_and_offers_baseline_restore(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = self.workspace(temporary_directory)
            candidate = entry("INF-REPLICA-01", {"replicas": 0})

            _, definition, changed = MODULE.materialize(
                workspace, oracle(candidate), candidate["candidate_id"]
            )

            deploy_as_is = next(
                item for item in definition["alternatives"] if item["id"] == "deploy-as-is"
            )
            restore = next(
                item
                for item in definition["alternatives"]
                if item["id"] == "restore-baseline-replicas"
            )
            self.assertEqual(
                deploy_as_is["configuration_changes"][0]["patch"]["spec"]["replicas"],
                0,
            )
            self.assertEqual(
                restore["configuration_changes"][0]["patch"]["spec"]["replicas"],
                1,
            )
            self.assertEqual(
                changed, ["experiment/pdt/candidates/cand-abcdefghijklmnop.json"]
            )

    def test_currency_mutation_is_conditional_and_changes_rounding(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = self.workspace(temporary_directory)
            candidate = entry(
                "DEP-CURRENCY-01", {"currency": "JPY", "rounding_mode": "truncate"}
            )

            MODULE.materialize(workspace, oracle(candidate), candidate["candidate_id"])

            content = (workspace / "src" / "currencyservice" / "server.js").read_text()
            self.assertIn("request.to_code === 'JPY'", content)
            self.assertIn("Math.trunc(euros.nanos)", content)
            self.assertIn("Math.round(euros.nanos)", content)

    def test_unimplemented_operator_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = self.workspace(temporary_directory)
            candidate = entry("INF-NOT-REAL", {"value": 1})

            with self.assertRaisesRegex(ValueError, "operator is not implemented"):
                MODULE.materialize(workspace, oracle(candidate), candidate["candidate_id"])

    def test_sealed_candidate_commit_preserves_tree_and_private_patch(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = pathlib.Path(directory) / "repo"
            workspace.mkdir()
            subprocess.run(["git", "init", "-q", str(workspace)], check=True)
            tracked = workspace / "tracked.txt"
            tracked.write_text("baseline\n", encoding="utf-8")
            identity = {
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "test@example.invalid",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@example.invalid",
            }
            subprocess.run(
                ["git", "-C", str(workspace), "add", "tracked.txt"], check=True
            )
            subprocess.run(
                ["git", "-C", str(workspace), "commit", "-q", "-m", "base"],
                check=True,
                env={**os.environ, **identity},
            )
            base_commit = subprocess.check_output(
                ["git", "-C", str(workspace), "rev-parse", "HEAD"], text=True
            ).strip()
            tracked.write_text("candidate\n", encoding="utf-8")
            (workspace / "new.txt").write_text(
                "new candidate file\n", encoding="utf-8"
            )
            patch_path = pathlib.Path(directory) / "candidate.patch"

            result = MODULE.seal_candidate_commit(
                workspace,
                "cand-test",
                "2026-09-20T00:00:00Z",
                patch_path,
            )

            self.assertEqual(result["base_commit"], base_commit)
            self.assertRegex(result["candidate_commit"], r"^[0-9a-f]{40}$")
            self.assertRegex(result["candidate_tree"], r"^[0-9a-f]{40}$")
            self.assertTrue(result["worktree_clean"])
            self.assertEqual(patch_path.stat().st_mode & 0o777, 0o600)
            self.assertIn("new.txt", patch_path.read_text(encoding="utf-8"))

    def test_every_implemented_parameter_choice_materializes(self):
        value = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
        operators = {
            item["id"]: item
            for item in value["operators"]
            if item["id"] in MODULE.IMPLEMENTED_OPERATORS
        }
        self.assertEqual(set(operators), MODULE.IMPLEMENTED_OPERATORS)

        for operator_id, operator in operators.items():
            parameter_names = sorted(operator["parameter_space"])
            choice_products = itertools.product(
                *(operator["parameter_space"][name] for name in parameter_names)
            )
            for choices in choice_products:
                parameters = dict(zip(parameter_names, choices))
                with self.subTest(operator=operator_id, parameters=parameters):
                    with tempfile.TemporaryDirectory() as temporary_directory:
                        workspace = self.workspace(temporary_directory)
                        candidate = entry(operator_id, parameters)
                        _, definition, _ = MODULE.materialize(
                            workspace, oracle(candidate), candidate["candidate_id"]
                        )
                        self.assertEqual(
                            MODULE.recursively_find_keys(
                                definition, MODULE.FORBIDDEN_DEFINITION_KEYS
                            ),
                            [],
                        )
                        if operator_id in {"DEP-CURRENCY-01", "DEP-TAIL-01"}:
                            node = shutil.which("node")
                            if node is None:
                                self.skipTest("node is required for JavaScript syntax validation")
                            target = (
                                workspace
                                / "src"
                                / (
                                    "currencyservice/server.js"
                                    if operator_id == "DEP-CURRENCY-01"
                                    else "paymentservice/server.js"
                                )
                            )
                            subprocess.run(
                                [node, "--check", str(target)],
                                check=True,
                                capture_output=True,
                                text=True,
                            )


if __name__ == "__main__":
    unittest.main()
