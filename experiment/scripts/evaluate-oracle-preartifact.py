#!/usr/bin/env python3

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import stat
import subprocess
import sys

import yaml


def load(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def private_file(path):
    return stat.S_IMODE(pathlib.Path(path).stat().st_mode) & 0o077 == 0


def git_output(workspace, *arguments):
    return subprocess.check_output(
        ["git", "-C", str(workspace), *arguments], text=True
    ).strip()


def validate_bindings(
    candidate_definition_path,
    private_work_item,
    work_order,
    candidate_patch_path,
    conventional,
    local_ci,
    local_ci_path,
    workspace,
):
    candidate_definition = load(candidate_definition_path)
    candidate_id = private_work_item.get("candidate_id")
    if candidate_definition.get("candidate_id") != candidate_id:
        raise ValueError("candidate definition and private work item differ")
    candidate_sha = sha256_file(candidate_definition_path)
    if any(
        item.get("candidate_definition_sha256") != candidate_sha
        for item in (private_work_item, work_order, conventional)
    ):
        raise ValueError("candidate definition hash binding failed")
    if work_order.get("candidate_id") != candidate_id:
        raise ValueError("work order candidate mismatch")
    if work_order.get("operator_id") != private_work_item.get("operator_id"):
        raise ValueError("work order and private item operator mismatch")
    if work_order.get("parameters") != private_work_item.get("parameters"):
        raise ValueError("work order and private item parameters mismatch")
    if conventional.get("candidate_id") != candidate_id:
        raise ValueError("conventional decision candidate mismatch")
    if (
        conventional.get("decision") != "block"
        or conventional.get("control_decision_sealed") is not True
        or conventional.get("staging", {}).get("executed") is not False
        or conventional.get("immutable_artifacts") != []
    ):
        raise ValueError("preartifact oracle requires a sealed local-CI block without artifacts")
    if local_ci.get("candidate_id") != candidate_id or local_ci.get("local_decision") != "block":
        raise ValueError("local CI evidence is not a block for this candidate")
    evidence = conventional.get("evidence", {}).get("local_ci_decision", {})
    if evidence.get("sha256") != sha256_file(local_ci_path):
        raise ValueError("local CI evidence hash binding failed")
    if conventional.get("evidence", {}).get("candidate_definition", {}).get(
        "sha256"
    ) != candidate_sha:
        raise ValueError("conventional decision did not seal the candidate definition")

    source = work_order.get("source_binding", {})
    if source.get("worktree_clean") is not True:
        raise ValueError("candidate source was not sealed from a clean worktree")
    if source.get("patch_sha256") != sha256_file(candidate_patch_path):
        raise ValueError("candidate patch hash binding failed")
    current_commit = git_output(workspace, "rev-parse", "HEAD")
    current_tree = git_output(workspace, "rev-parse", "HEAD^{tree}")
    current_status = git_output(workspace, "status", "--porcelain", "--untracked-files=all")
    if current_status:
        raise ValueError("candidate source workspace is not clean")
    if source.get("candidate_commit") != current_commit or source.get(
        "candidate_tree"
    ) != current_tree:
        raise ValueError("candidate source commit or tree binding failed")
    local_git = local_ci.get("git", {})
    if local_git.get("commit") != current_commit or local_git.get("tree") != current_tree:
        raise ValueError("local CI did not evaluate the sealed candidate source")
    if local_git.get("dirty") is not False:
        raise ValueError("local CI source was not clean")
    if source.get("base_commit") != local_git.get("base_commit"):
        raise ValueError("candidate base commit binding failed")
    return candidate_id


def scan_secret_canary(workspace, pattern):
    compiled = re.compile(pattern)
    findings = []
    root = pathlib.Path(workspace) / "src" / "checkoutservice"
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(content.splitlines(), start=1):
            if compiled.search(line):
                findings.append(
                    {
                        "path": str(path.relative_to(workspace)),
                        "line": line_number,
                        "value_redacted": True,
                    }
                )
    return findings


def privileged_containers(rendered_yaml):
    findings = []
    for document in yaml.safe_load_all(rendered_yaml):
        if not isinstance(document, dict):
            continue
        resources = document.get("items", []) if document.get("kind") == "List" else [document]
        for resource in resources:
            if not isinstance(resource, dict) or resource.get("kind") != "Deployment":
                continue
            metadata = resource.get("metadata", {})
            containers = (
                resource.get("spec", {})
                .get("template", {})
                .get("spec", {})
                .get("containers", [])
            )
            for container in containers:
                if container.get("securityContext", {}).get("privileged") is True:
                    findings.append(
                        {
                            "namespace": metadata.get("namespace"),
                            "deployment": metadata.get("name"),
                            "container": container.get("name"),
                        }
                    )
    return findings


def run_go_verification(workspace, go_image, timeout_seconds=600):
    command = [
        "docker",
        "run",
        "--rm",
        "-e",
        "HOME=/tmp",
        "-e",
        "GOCACHE=/tmp/go-build",
        "-e",
        "GOMODCACHE=/tmp/go-mod",
        "-v",
        f"{pathlib.Path(workspace) / 'src' / 'checkoutservice'}:/workspace:ro",
        "-w",
        "/workspace",
        go_image,
        "go",
        "test",
        "./...",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        return {
            "execution_valid": False,
            "invalid_reason": "go-verification-timeout",
            "exit_code": None,
            "stdout": error.stdout or "",
            "stderr": error.stderr or "",
        }
    if completed.returncode in {125, 126, 127}:
        return {
            "execution_valid": False,
            "invalid_reason": "go-verification-runtime-error",
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    return {
        "execution_valid": True,
        "invalid_reason": None,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def evaluate(policy, private_work_item, workspace, go_runner=run_go_verification, renderer=None):
    configuration = policy.get("preartifact_verification", {})
    operator_id = private_work_item.get("operator_id")
    parameters = private_work_item.get("parameters", {})
    result = {
        "execution_valid": True,
        "invalid_reason": None,
        "check_id": None,
        "requirement_violated": False,
        "details": {},
        "log": "",
    }
    if operator_id == "CTRL-CI-01":
        if parameters.get("failure_kind") not in {"compile-error", "unit-test-regression"}:
            raise ValueError("unsupported CTRL-CI-01 failure kind")
        result["check_id"] = "independent-checkout-go-test"
        verification = go_runner(workspace, configuration["go_image"])
        result["execution_valid"] = verification["execution_valid"]
        result["invalid_reason"] = verification["invalid_reason"]
        result["requirement_violated"] = (
            verification["execution_valid"] and verification["exit_code"] != 0
        )
        result["details"] = {"exit_code": verification["exit_code"]}
        result["log"] = verification["stdout"] + verification["stderr"]
    elif operator_id == "CTRL-SEC-01" and parameters.get(
        "failure_kind"
    ) == "synthetic-secret-canary":
        result["check_id"] = "independent-secret-pattern"
        findings = scan_secret_canary(workspace, configuration["synthetic_secret_pattern"])
        result["requirement_violated"] = bool(findings)
        result["details"] = {"redacted_findings": findings}
    elif operator_id == "CTRL-SEC-01" and parameters.get(
        "failure_kind"
    ) == "prohibited-container-privilege":
        result["check_id"] = "independent-rendered-privilege-inspection"
        if renderer is None:
            completed = subprocess.run(
                [
                    "kubectl",
                    "kustomize",
                    str(pathlib.Path(workspace) / configuration["staging_overlay"]),
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if completed.returncode != 0:
                result["execution_valid"] = False
                result["invalid_reason"] = "kustomize-render-failed"
                result["log"] = completed.stdout + completed.stderr
                return result
            rendered = completed.stdout
        else:
            rendered = renderer(workspace, configuration["staging_overlay"])
        findings = privileged_containers(rendered)
        result["requirement_violated"] = bool(findings)
        result["details"] = {"privileged_containers": findings}
    else:
        raise ValueError("preartifact oracle does not support this operator and parameter set")
    return result


def write_text_exclusive(path, content, mode=0o600):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=pathlib.Path, required=True)
    parser.add_argument("--candidate-definition", type=pathlib.Path, required=True)
    parser.add_argument("--private-work-item", type=pathlib.Path, required=True)
    parser.add_argument("--work-order", type=pathlib.Path, required=True)
    parser.add_argument("--candidate-patch", type=pathlib.Path, required=True)
    parser.add_argument("--conventional-decision", type=pathlib.Path, required=True)
    parser.add_argument("--local-ci-decision", type=pathlib.Path, required=True)
    parser.add_argument("--source-workspace", type=pathlib.Path, required=True)
    parser.add_argument("--log-output", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        for path in (args.private_work_item, args.work_order, args.candidate_patch):
            if not private_file(path):
                raise ValueError(f"private oracle input has unsafe permissions: {path}")
        policy = load(args.policy)
        private_work_item = load(args.private_work_item)
        candidate_id = validate_bindings(
            args.candidate_definition,
            private_work_item,
            load(args.work_order),
            args.candidate_patch,
            load(args.conventional_decision),
            load(args.local_ci_decision),
            args.local_ci_decision,
            args.source_workspace,
        )
        observation = evaluate(policy, private_work_item, args.source_workspace)
        write_text_exclusive(args.log_output, observation.pop("log"))
        label = None
        if observation["execution_valid"]:
            label = "harmful" if observation["requirement_violated"] else "safe"
        intended_label = private_work_item.get("intended_label")
        output = {
            "schema_version": "1.0.0",
            "policy_id": policy.get("policy_id"),
            "candidate_id": candidate_id,
            "adjudication_source": "independent-preartifact-verification",
            **observation,
            "observed_deploy_as_is_label": label,
            "intended_label": intended_label,
            "intent_matches_observation": (
                intended_label == label if label in {"safe", "harmful"} else None
            ),
            "eligible_for_primary_analysis": (
                policy.get("status") == "frozen"
                and observation["execution_valid"]
                and label in {"safe", "harmful"}
            ),
            "generated_at": datetime.datetime.now(datetime.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "evidence_sha256": {
                "candidate_definition": sha256_file(args.candidate_definition),
                "private_work_item": sha256_file(args.private_work_item),
                "work_order": sha256_file(args.work_order),
                "candidate_patch": sha256_file(args.candidate_patch),
                "conventional_decision": sha256_file(args.conventional_decision),
                "local_ci_decision": sha256_file(args.local_ci_decision),
                "verification_log": sha256_file(args.log_output),
            },
        }
        write_text_exclusive(args.output, json.dumps(output, indent=2) + "\n")
    except (
        OSError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
        yaml.YAMLError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"preartifact oracle evaluation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(args.output)


if __name__ == "__main__":
    main()
