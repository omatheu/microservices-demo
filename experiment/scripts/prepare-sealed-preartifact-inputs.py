#!/usr/bin/env python3

"""Reconstruct private preartifact Oracle inputs from sealed Git evidence."""

import argparse
import hashlib
import json
import os
import pathlib
import re
import stat
import subprocess
import sys


COMMIT = re.compile(r"^[0-9a-f]{40}$")


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


def oracle_candidate(oracle, candidate_id):
    matches = [
        item
        for item in oracle.get("candidates", [])
        if item.get("candidate_id") == candidate_id
    ]
    if len(matches) != 1:
        raise ValueError("candidate must occur exactly once in the Oracle manifest")
    return matches[0]


def validate_sealed_source(
    workspace,
    candidate_definition_path,
    control,
    local_ci,
    candidate_id,
):
    workspace = pathlib.Path(workspace).resolve()
    top_level = pathlib.Path(git_output(workspace, "rev-parse", "--show-toplevel")).resolve()
    if top_level != workspace:
        raise ValueError("source workspace must be the root of its Git worktree")
    if git_output(workspace, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("source workspace is not clean")

    candidate_sha256 = sha256_file(candidate_definition_path)
    source_candidate_definition = (
        workspace
        / "experiment"
        / "pdt"
        / "candidates"
        / f"{candidate_id}.json"
    )
    if (
        not source_candidate_definition.is_file()
        or sha256_file(source_candidate_definition) != candidate_sha256
    ):
        raise ValueError("source commit contains a different candidate definition")
    if (
        control.get("mechanism") != "conventional-ci-cd-with-staging"
        or control.get("candidate_id") != candidate_id
        or control.get("decision") != "block"
        or control.get("control_decision_sealed") is not True
        or control.get("candidate_definition_sha256") != candidate_sha256
        or control.get("staging", {}).get("executed") is not False
        or control.get("immutable_artifacts") != []
    ):
        raise ValueError("preartifact preparation requires a sealed local-CI block")
    if (
        local_ci.get("candidate_id") != candidate_id
        or local_ci.get("local_decision") != "block"
        or control.get("evidence", {}).get("local_ci_decision", {}).get("sha256")
        != local_ci["_sha256"]
    ):
        raise ValueError("local CI block is not the evidence sealed by the control")

    git_binding = local_ci.get("git", {})
    head = git_output(workspace, "rev-parse", "HEAD")
    tree = git_output(workspace, "rev-parse", "HEAD^{tree}")
    base = git_binding.get("base_commit")
    if (
        git_binding.get("commit") != head
        or git_binding.get("tree") != tree
        or git_binding.get("dirty") is not False
        or not isinstance(base, str)
        or not COMMIT.fullmatch(base)
    ):
        raise ValueError("source commit, tree or cleanliness differs from local CI")
    subprocess.check_call(
        ["git", "-C", str(workspace), "merge-base", "--is-ancestor", base, head],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if int(git_output(workspace, "rev-list", "--count", f"{base}..{head}")) != 1:
        raise ValueError("sealed candidate must contain exactly one commit after its base")
    return {
        "base_commit": base,
        "candidate_commit": head,
        "candidate_tree": tree,
        "candidate_definition_sha256": candidate_sha256,
    }


def write_exclusive(path, content, mode):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def prepare(
    workspace,
    oracle,
    candidate_definition_path,
    control,
    local_ci,
    local_ci_sha256,
    candidate_id,
):
    local_ci = dict(local_ci)
    local_ci["_sha256"] = local_ci_sha256
    definition = load(candidate_definition_path)
    if definition.get("candidate_id") != candidate_id:
        raise ValueError("candidate definition identity differs")
    candidate = oracle_candidate(oracle, candidate_id)
    binding = validate_sealed_source(
        workspace,
        candidate_definition_path,
        control,
        local_ci,
        candidate_id,
    )
    patch = subprocess.check_output(
        [
            "git",
            "-C",
            str(workspace),
            "diff",
            "--binary",
            binding["base_commit"],
            binding["candidate_commit"],
            "--",
        ],
        text=True,
    )
    if not patch:
        raise ValueError("sealed candidate patch is empty")
    changed_files = git_output(
        workspace,
        "diff",
        "--name-only",
        "--diff-filter=ACDMRTUXB",
        binding["base_commit"],
        binding["candidate_commit"],
        "--",
    ).splitlines()
    work_order = {
        "schema_version": "1.0.0",
        "corpus_id": oracle.get("corpus_id"),
        "candidate_id": candidate_id,
        "operator_id": candidate.get("operator_id"),
        "parameters": candidate.get("parameters"),
        "changed_files": sorted(changed_files),
        "candidate_definition": f"experiment/pdt/candidates/{candidate_id}.json",
        "candidate_definition_sha256": binding["candidate_definition_sha256"],
        "confirmatory_eligible": definition.get("confirmatory_eligibility") is True,
        "source_binding": {
            "base_commit": binding["base_commit"],
            "candidate_commit": binding["candidate_commit"],
            "candidate_tree": binding["candidate_tree"],
            "patch_sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
            "patch_path": "private:candidate.patch",
            "worktree_clean": True,
        },
    }
    return patch, work_order


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-workspace", type=pathlib.Path, required=True)
    parser.add_argument("--oracle-manifest", type=pathlib.Path, required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--candidate-definition", type=pathlib.Path, required=True)
    parser.add_argument("--conventional-decision", type=pathlib.Path, required=True)
    parser.add_argument("--local-ci-decision", type=pathlib.Path, required=True)
    parser.add_argument("--work-order-output", type=pathlib.Path, required=True)
    parser.add_argument("--patch-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        if not private_file(args.oracle_manifest):
            raise ValueError("Oracle manifest permissions must be 0600-compatible")
        patch, work_order = prepare(
            args.source_workspace.resolve(),
            load(args.oracle_manifest),
            args.candidate_definition,
            load(args.conventional_decision),
            load(args.local_ci_decision),
            sha256_file(args.local_ci_decision),
            args.candidate_id,
        )
        write_exclusive(args.patch_output, patch, 0o600)
        try:
            write_exclusive(
                args.work_order_output,
                json.dumps(work_order, indent=2) + "\n",
                0o600,
            )
        except Exception:
            args.patch_output.unlink(missing_ok=True)
            raise
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"preartifact input preparation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(
        json.dumps(
            {
                "candidate_id": args.candidate_id,
                "patch_sha256": sha256_file(args.patch_output),
                "work_order_sha256": sha256_file(args.work_order_output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
