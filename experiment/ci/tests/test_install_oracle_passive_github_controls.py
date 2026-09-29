import copy
import importlib.util
import json
import pathlib
import unittest
from unittest import mock


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = (
    REPO_ROOT
    / "experiment"
    / "scripts"
    / "install-oracle-passive-github-controls.py"
)
SPEC = importlib.util.spec_from_file_location(
    "install_oracle_passive_github_controls", SCRIPT
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FakeRunner:
    def __init__(self, labels=None, secrets=None, variables=None, pull_requests=None):
        self.labels = set(labels or [])
        self.secrets = set(secrets or [])
        self.variables = dict(variables or {})
        self.pull_requests = copy.deepcopy(pull_requests or [])
        self.json_calls = []
        self.run_calls = []
        self.fail_secret = None

    def json(self, command):
        self.json_calls.append(list(command))
        endpoint = command[-1]
        if endpoint.endswith("/labels?per_page=100"):
            return [{"name": name} for name in sorted(self.labels)]
        if endpoint.endswith("/secrets?per_page=100"):
            return {"secrets": [{"name": name} for name in sorted(self.secrets)]}
        if endpoint.endswith("/variables?per_page=100"):
            return {
                "variables": [
                    {"name": name, "value": value}
                    for name, value in sorted(self.variables.items())
                ]
            }
        if endpoint.endswith("/pulls?state=open&per_page=100"):
            return copy.deepcopy(self.pull_requests)
        raise AssertionError(f"unexpected endpoint: {endpoint}")

    def run(self, command, input_text=None):
        self.run_calls.append({"command": list(command), "input_text": input_text})
        if command[1:3] == ["variable", "set"]:
            self.variables[command[3]] = input_text.strip()
            return
        if command[1:3] == ["label", "create"]:
            self.labels.add(command[3])
            return
        if command[1:3] == ["secret", "set"]:
            if command[3] == self.fail_secret:
                raise MODULE.InstallationError("gh failed with exit 1")
            self.secrets.add(command[3])
            return
        raise AssertionError(f"unexpected command: {command}")


class OraclePassiveGithubControlsTests(unittest.TestCase):
    def test_dry_run_is_read_only_and_orders_kill_switch_first(self):
        runner = FakeRunner()

        result = MODULE.execute(runner)

        self.assertEqual("read-only-plan", result["mode"])
        self.assertEqual([], runner.run_calls)
        self.assertEqual(4, len(runner.json_calls))
        self.assertEqual(
            [
                "environment-variable",
                "repository-label",
                "environment-secret",
                "environment-secret",
            ],
            [item["kind"] for item in result["proposed_actions"]],
        )
        self.assertFalse(result["github_mutation_performed"])
        self.assertFalse(result["oracle_execution_authorized"])

    def test_apply_requires_exact_acknowledgement_before_collection(self):
        runner = FakeRunner()

        with self.assertRaisesRegex(MODULE.InstallationError, "requires"):
            MODULE.execute(runner, apply=True, acknowledgement="wrong")

        self.assertEqual([], runner.json_calls)
        self.assertEqual([], runner.run_calls)

    def test_apply_installs_controls_without_disclosing_secret_values(self):
        runner = FakeRunner()
        secret_values = {
            "TCC_ORACLE_ARCHIVE_PASSPHRASE": "archive-value-DO-NOT-DISCLOSE",
            "TCC_ORACLE_BLINDING_KEY_B64": "blinding-value-DO-NOT-DISCLOSE",
        }

        with mock.patch.object(
            MODULE, "generate_secret", side_effect=lambda name: secret_values[name]
        ):
            result = MODULE.execute(
                runner,
                apply=True,
                acknowledgement=MODULE.ACKNOWLEDGEMENT,
            )

        self.assertEqual("apply", result["mode"])
        self.assertTrue(result["controls_installed"])
        self.assertEqual("false", result["execution_switch_value"])
        self.assertTrue(result["github_mutation_performed"])
        self.assertFalse(result["gcp_mutation_performed"])
        self.assertFalse(result["cloud_execution_authorized"])
        self.assertEqual([], result["remaining_actions"])
        self.assertEqual(
            ["variable", "set"], runner.run_calls[0]["command"][1:3]
        )
        receipt = json.dumps(result, sort_keys=True)
        for value in secret_values.values():
            self.assertNotIn(value, receipt)
            self.assertFalse(
                any(value in part for call in runner.run_calls for part in call["command"])
            )

    def test_existing_secrets_are_not_rotated(self):
        runner = FakeRunner(
            secrets=MODULE.SECRET_NAMES,
            variables={MODULE.VARIABLE_NAME: MODULE.DISABLED_VALUE},
        )

        result = MODULE.execute(
            runner,
            apply=True,
            acknowledgement=MODULE.ACKNOWLEDGEMENT,
        )

        self.assertEqual(1, len(runner.run_calls))
        self.assertEqual(["label", "create"], runner.run_calls[0]["command"][1:3])
        self.assertEqual(
            [{"kind": "repository-label", "name": MODULE.LABEL_NAME}],
            result["applied_controls"],
        )

    def test_armed_pull_request_blocks_before_any_write(self):
        runner = FakeRunner(
            pull_requests=[
                {
                    "number": 9,
                    "labels": [{"name": "tcc-cost-reviewed"}],
                }
            ]
        )

        with self.assertRaisesRegex(MODULE.InstallationError, "cloud-armed"):
            MODULE.execute(
                runner,
                apply=True,
                acknowledgement=MODULE.ACKNOWLEDGEMENT,
            )

        self.assertEqual([], runner.run_calls)

    def test_partial_failure_keeps_switch_disabled_and_error_secret_free(self):
        runner = FakeRunner()
        runner.fail_secret = "TCC_ORACLE_ARCHIVE_PASSPHRASE"
        marker = "secret-value-DO-NOT-DISCLOSE"

        with mock.patch.object(MODULE, "generate_secret", return_value=marker):
            with self.assertRaises(MODULE.InstallationError) as raised:
                MODULE.execute(
                    runner,
                    apply=True,
                    acknowledgement=MODULE.ACKNOWLEDGEMENT,
                )

        self.assertEqual(MODULE.DISABLED_VALUE, runner.variables[MODULE.VARIABLE_NAME])
        self.assertNotIn(marker, str(raised.exception))
        self.assertNotIn(marker, " ".join(runner.run_calls[-1]["command"]))

    def test_fully_installed_state_needs_no_action(self):
        runner = FakeRunner(
            labels={MODULE.LABEL_NAME},
            secrets=MODULE.SECRET_NAMES,
            variables={MODULE.VARIABLE_NAME: MODULE.DISABLED_VALUE},
        )

        result = MODULE.execute(runner)

        self.assertTrue(result["controls_installed"])
        self.assertEqual([], result["proposed_actions"])
        self.assertEqual([], result["remaining_actions"])


if __name__ == "__main__":
    unittest.main()
