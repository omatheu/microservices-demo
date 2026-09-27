#!/usr/bin/env python3

"""Install passive GitHub controls for the Oracle path without arming execution."""

import argparse
import base64
import datetime
import json
import pathlib
import secrets
import subprocess
import sys


REPOSITORY = "omatheu/microservices-demo"
ENVIRONMENT = "tcc-experiment"
LABEL_NAME = "tcc-oracle-cloud"
LABEL_COLOR = "5319E7"
LABEL_DESCRIPTION = "Explicitly request the protected Oracle validation path"
VARIABLE_NAME = "TCC_ORACLE_EXECUTION_ACKNOWLEDGED"
DISABLED_VALUE = "false"
SECRET_NAMES = {
    "TCC_ORACLE_ARCHIVE_PASSPHRASE",
    "TCC_ORACLE_BLINDING_KEY_B64",
}
AUTHORIZATION_LABELS = {
    "tcc-cost-reviewed",
    "tcc-experiment-cloud",
    "tcc-runtime-publication",
    LABEL_NAME,
}
ACKNOWLEDGEMENT = "INSTALL_PASSIVE_ORACLE_GITHUB_CONTROLS"


class InstallationError(RuntimeError):
    """Fail-closed installation error with no secret-bearing command output."""


class CommandRunner:
    def json(self, command):
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise InstallationError(
                f"{pathlib.Path(command[0]).name} failed with exit {result.returncode}"
            )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise InstallationError(f"invalid JSON from {command[0]}") from error

    def run(self, command, input_text=None):
        result = subprocess.run(
            command,
            input=input_text,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise InstallationError(
                f"{pathlib.Path(command[0]).name} failed with exit {result.returncode}"
            )


def names(document, key=None):
    if key is not None:
        document = document.get(key, []) if isinstance(document, dict) else []
    if not isinstance(document, list):
        return set()
    return {
        item.get("name")
        for item in document
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }


def collect(runner):
    labels = runner.json(["gh", "api", f"repos/{REPOSITORY}/labels?per_page=100"])
    environment_secrets = runner.json(
        [
            "gh",
            "api",
            f"repos/{REPOSITORY}/environments/{ENVIRONMENT}/secrets?per_page=100",
        ]
    )
    environment_variables = runner.json(
        [
            "gh",
            "api",
            f"repos/{REPOSITORY}/environments/{ENVIRONMENT}/variables?per_page=100",
        ]
    )
    pull_requests = runner.json(
        ["gh", "api", f"repos/{REPOSITORY}/pulls?state=open&per_page=100"]
    )

    variable_values = {
        item.get("name"): item.get("value")
        for item in (
            environment_variables.get("variables", [])
            if isinstance(environment_variables, dict)
            else []
        )
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    armed_pull_requests = []
    if isinstance(pull_requests, list):
        for pull_request in pull_requests:
            if not isinstance(pull_request, dict):
                continue
            pull_labels = names(pull_request.get("labels", []))
            armed = sorted(AUTHORIZATION_LABELS & pull_labels)
            if armed:
                armed_pull_requests.append(
                    {
                        "number": pull_request.get("number"),
                        "authorization_labels": armed,
                    }
                )

    return {
        "label_names": names(labels),
        "secret_names": names(environment_secrets, "secrets"),
        "variable_values": variable_values,
        "armed_pull_requests": armed_pull_requests,
    }


def plan(snapshot):
    missing_secrets = sorted(SECRET_NAMES - snapshot["secret_names"])
    actions = []
    if snapshot["variable_values"].get(VARIABLE_NAME) != DISABLED_VALUE:
        actions.append(
            {
                "kind": "environment-variable",
                "name": VARIABLE_NAME,
                "action": "set-disabled",
                "value": DISABLED_VALUE,
            }
        )
    if LABEL_NAME not in snapshot["label_names"]:
        actions.append(
            {
                "kind": "repository-label",
                "name": LABEL_NAME,
                "action": "create",
                "attach_to_pull_request": False,
            }
        )
    actions.extend(
        {
            "kind": "environment-secret",
            "name": name,
            "action": "create-random-value",
            "value_disclosed": False,
        }
        for name in missing_secrets
    )
    return {
        "actions": actions,
        "action_count": len(actions),
        "already_installed": not actions,
        "armed_pull_requests": snapshot["armed_pull_requests"],
        "safe_to_apply": not snapshot["armed_pull_requests"],
    }


def generate_secret(name):
    if name == "TCC_ORACLE_BLINDING_KEY_B64":
        return base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    if name == "TCC_ORACLE_ARCHIVE_PASSPHRASE":
        return secrets.token_urlsafe(48)
    raise InstallationError(f"unsupported secret name: {name}")


def apply_plan(value, runner):
    if not value["safe_to_apply"]:
        raise InstallationError("an open pull request has a cloud-authorization label")

    applied = []
    for action in value["actions"]:
        kind = action["kind"]
        name = action["name"]
        if kind == "environment-variable":
            runner.run(
                [
                    "gh",
                    "variable",
                    "set",
                    name,
                    "--env",
                    ENVIRONMENT,
                    "--repo",
                    REPOSITORY,
                ],
                input_text=f"{DISABLED_VALUE}\n",
            )
        elif kind == "repository-label":
            runner.run(
                [
                    "gh",
                    "label",
                    "create",
                    name,
                    "--repo",
                    REPOSITORY,
                    "--color",
                    LABEL_COLOR,
                    "--description",
                    LABEL_DESCRIPTION,
                ]
            )
        elif kind == "environment-secret":
            secret_value = generate_secret(name)
            runner.run(
                [
                    "gh",
                    "secret",
                    "set",
                    name,
                    "--env",
                    ENVIRONMENT,
                    "--repo",
                    REPOSITORY,
                ],
                input_text=f"{secret_value}\n",
            )
            secret_value = None
        else:
            raise InstallationError(f"unsupported action kind: {kind}")
        applied.append({"kind": kind, "name": name})
    return applied


def execute(runner, apply=False, acknowledgement=None):
    if apply and acknowledgement != ACKNOWLEDGEMENT:
        raise InstallationError(
            f"--apply requires --acknowledge {ACKNOWLEDGEMENT}"
        )

    before = collect(runner)
    proposed = plan(before)
    if apply and not proposed["safe_to_apply"]:
        raise InstallationError("refusing apply while an open PR is cloud-armed")

    applied = apply_plan(proposed, runner) if apply else []
    after = collect(runner) if apply else before
    remaining = plan(after)
    installed = bool(
        LABEL_NAME in after["label_names"]
        and SECRET_NAMES <= after["secret_names"]
        and after["variable_values"].get(VARIABLE_NAME) == DISABLED_VALUE
    )
    if apply and (not installed or remaining["actions"]):
        raise InstallationError("post-installation audit did not confirm all controls")

    return {
        "schema_version": "1.0.0",
        "captured_at": datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "mechanism": "oracle-passive-github-controls-installer",
        "repository": REPOSITORY,
        "environment": ENVIRONMENT,
        "mode": "apply" if apply else "read-only-plan",
        "proposed_actions": proposed["actions"],
        "applied_controls": applied,
        "remaining_actions": remaining["actions"],
        "controls_installed": installed,
        "armed_pull_requests": after["armed_pull_requests"],
        "execution_switch_value": after["variable_values"].get(VARIABLE_NAME),
        "secret_names_present": sorted(SECRET_NAMES & after["secret_names"]),
        "secret_values_disclosed": False,
        "label_attachment_performed": False,
        "github_mutation_performed": bool(applied),
        "gcp_mutation_performed": False,
        "kubernetes_mutation_performed": False,
        "oracle_execution_authorized": False,
        "cloud_execution_authorized": False,
    }


def write_json(path, document):
    output = pathlib.Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--acknowledge")
    parser.add_argument("--output")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.apply and not args.output:
        print("error: --apply requires --output for a secret-free receipt", file=sys.stderr)
        return 2
    if args.apply and pathlib.Path(args.output).exists():
        print("error: refusing to overwrite an existing receipt", file=sys.stderr)
        return 2
    try:
        result = execute(
            CommandRunner(),
            apply=args.apply,
            acknowledgement=args.acknowledge,
        )
    except InstallationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.output:
        write_json(args.output, result)
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
