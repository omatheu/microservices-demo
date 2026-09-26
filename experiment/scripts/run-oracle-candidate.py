#!/usr/bin/env python3

"""Run the post-decision independent Oracle for one sealed candidate."""

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


DIGEST = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")
FORBIDDEN_PUBLIC_KEYS = {
    "context_dependency",
    "intended_label",
    "intent_matches_observation",
    "label",
    "observed_deploy_as_is_label",
    "operator_id",
    "oracle_decision",
    "parameters",
    "selected_alternative",
    "stratum",
    "target_component",
    "violations",
}


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


def recursively_find_keys(value, forbidden=FORBIDDEN_PUBLIC_KEYS):
    findings = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in forbidden:
                findings.append(key)
            findings.extend(recursively_find_keys(child, forbidden))
    elif isinstance(value, list):
        for child in value:
            findings.extend(recursively_find_keys(child, forbidden))
    return findings


def write_json_exclusive(path, value, mode):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
    except Exception:
        path.unlink(missing_ok=True)
        raise


def write_text_exclusive(path, value, mode=0o600):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(value)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def classify_control_path(control):
    if (
        control.get("decision") == "block"
        and control.get("staging", {}).get("executed") is False
        and control.get("immutable_artifacts") == []
    ):
        return "preartifact"
    if control.get("decision") in {"approve", "block"}:
        if not control.get("immutable_artifacts"):
            raise ValueError("runtime Oracle requires sealed immutable artifacts")
        if control.get("decision") == "block" and (
            control.get("staging", {}).get("executed") is not True
            or not control.get("immutable_artifacts")
        ):
            raise ValueError(
                "runtime Oracle requires sealed artifacts from an executed staging condition"
            )
        return "runtime"
    raise ValueError("conventional decision is not terminal")


def validate_design(protocol, mode, allow_draft):
    repetitions = protocol.get("research_design", {}).get(
        "technical_repetitions_per_candidate"
    )
    minimum_valid = protocol.get("aggregation", {}).get(
        "minimum_valid_repetitions"
    )
    if (
        not isinstance(repetitions, int)
        or isinstance(repetitions, bool)
        or repetitions < 2
        or not isinstance(minimum_valid, int)
        or isinstance(minimum_valid, bool)
        or not 2 <= minimum_valid <= repetitions
    ):
        raise ValueError("protocol repetition design is invalid")
    frozen = (
        protocol.get("status") == "frozen"
        and protocol.get("confirmatory_collection_allowed") is True
        and isinstance(protocol.get("frozen_at"), str)
        and bool(protocol["frozen_at"])
    )
    if mode == "confirmatory" and not frozen:
        raise ValueError("confirmatory Oracle requires the frozen protocol")
    if mode == "engineering" and not allow_draft:
        raise ValueError("engineering Oracle requires --allow-draft")
    return list(range(1, repetitions + 1)), minimum_valid


def validate_candidate(candidate, candidate_id, candidate_sha256, control, mode):
    control_mode = control.get("execution_mode")
    if (
        candidate.get("candidate_id") != candidate_id
        or control.get("candidate_id") != candidate_id
        or control.get("candidate_definition_sha256") != candidate_sha256
        or control.get("mechanism") != "conventional-ci-cd-with-staging"
        or control.get("control_decision_sealed") is not True
        or (mode == "confirmatory" and control_mode != "confirmatory")
        or (
            mode == "engineering"
            and control_mode not in {None, "engineering-dry-run"}
        )
    ):
        raise ValueError("candidate and sealed conventional decision bindings differ")
    if mode == "confirmatory" and candidate.get("confirmatory_eligibility") is not True:
        raise ValueError("confirmatory Oracle requires an eligible candidate")
    alternatives = [
        item.get("id")
        for item in candidate.get("alternatives", [])
        if isinstance(item, dict) and item.get("action") == "deploy"
    ]
    if (
        not alternatives
        or len(alternatives) != len(set(alternatives))
        or alternatives.count("deploy-as-is") != 1
        or any(not isinstance(item, str) or not SAFE_ID.fullmatch(item) for item in alternatives)
    ):
        raise ValueError("candidate deployable alternative inventory is invalid")
    return alternatives


def find_by_sha256(root, expected):
    if not isinstance(expected, str) or not DIGEST.fullmatch(expected):
        raise ValueError("sealed evidence contains an invalid SHA-256")
    matches = []
    for path in sorted(pathlib.Path(root).rglob("*.json")):
        if path.is_file() and sha256_file(path) == expected:
            matches.append(path)
    if not matches:
        raise ValueError(f"sealed evidence file is missing for SHA-256 {expected}")
    return matches[0]


def resolve_prediction_inputs(pdt, evidence_root, repetitions, minimum_valid):
    if (
        pdt.get("mechanism") != "candidate-level-pdt-decision"
        or pdt.get("repetition") is not None
    ):
        raise ValueError("candidate Oracle requires a candidate-level PDT decision")
    aggregation = pdt.get("repetition_aggregation", {})
    valid = aggregation.get("valid_repetitions")
    invalid = aggregation.get("invalid_repetitions")
    if (
        not isinstance(valid, list)
        or not isinstance(invalid, list)
        or len(valid) < minimum_valid
        or sorted(valid + invalid) != repetitions
        or set(valid) & set(invalid)
    ):
        raise ValueError("PDT repetition partition is invalid")
    entries = pdt.get("evidence", {}).get("pdt_decisions")
    if not isinstance(entries, list) or len(entries) != len(valid):
        raise ValueError("PDT decision evidence does not cover every valid repetition")
    predictions = {}
    for entry in entries:
        repetition = entry.get("repetition") if isinstance(entry, dict) else None
        if repetition not in valid or repetition in predictions:
            raise ValueError("PDT decision evidence repetitions are invalid or duplicated")
        path = find_by_sha256(evidence_root, entry.get("sha256"))
        decision = load(path)
        if decision.get("repetition") != repetition:
            raise ValueError("resolved PDT prediction has a different repetition")
        predictions[repetition] = path
    if set(predictions) != set(valid):
        raise ValueError("resolved PDT predictions differ from the valid repetition set")

    ledger = None
    ledger_entry = pdt.get("evidence", {}).get("infrastructure_invalid_ledger")
    if invalid:
        if not isinstance(ledger_entry, dict):
            raise ValueError("missing PDT repetitions require the sealed pre-label ledger")
        ledger = find_by_sha256(evidence_root, ledger_entry.get("sha256"))
        ledger_value = load(ledger)
        if (
            ledger_value.get("label_revealed") is not False
            or ledger_value.get("valid_repetitions") != valid
            or sorted(
                item.get("repetition")
                for item in ledger_value.get("invalid_repetitions", [])
                if isinstance(item, dict)
            )
            != invalid
        ):
            raise ValueError("resolved infrastructure ledger differs from PDT aggregation")
    elif ledger_entry is not None:
        raise ValueError("PDT aggregation references a ledger without missing repetitions")
    return predictions, ledger


def matrix(alternatives, repetitions):
    return [
        {"alternative_id": alternative, "repetition": repetition}
        for alternative in alternatives
        for repetition in repetitions
    ]


def run_command(command, *, cwd, environment=None, log_path=None):
    completed = subprocess.run(
        [str(item) for item in command],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if log_path is not None:
        write_text_exclusive(
            log_path,
            completed.stdout + ("\n[stderr]\n" if completed.stderr else "") + completed.stderr,
        )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        suffix = detail[-1] if detail else "no diagnostic output"
        raise ValueError(f"command failed ({completed.returncode}): {suffix}")
    return completed.stdout


def existing(path, label, required=True):
    if path is None:
        if required:
            raise ValueError(f"{label} is required")
        return None
    value = pathlib.Path(path).resolve()
    if not value.is_file():
        raise ValueError(f"{label} does not exist: {value}")
    return value


def pipeline_file(pipeline, name, required=True):
    path = pathlib.Path(pipeline) / name
    if not path.is_file():
        if required:
            raise ValueError(f"paired pipeline evidence is missing {name}")
        return None
    return path.resolve()


def validate_snapshot_binding(snapshot, summary, pdt=None):
    binding = summary.get("oracle_binding_snapshot")
    if (
        not isinstance(binding, dict)
        or binding.get("path") != "oracle-binding-snapshot.json"
        or binding.get("sha256") != sha256_file(snapshot)
    ):
        raise ValueError("paired summary did not seal the Oracle binding snapshot")
    snapshot_id = load(snapshot).get("snapshot_id")
    if not isinstance(snapshot_id, str) or not snapshot_id:
        raise ValueError("Oracle binding snapshot lacks an identity")
    if pdt is not None and pdt.get("snapshot_id") != snapshot_id:
        raise ValueError("Oracle binding snapshot differs from the PDT action snapshot")


def unlock_command(args, paths, private_work_item, public_receipt):
    command = [
        sys.executable,
        paths["unlock_script"],
        "--public-corpus",
        paths["public_corpus"],
        "--oracle-manifest",
        paths["oracle_manifest"],
        "--candidate-id",
        args.candidate_id,
        "--conventional-decision",
        paths["control"],
        "--private-work-item",
        private_work_item,
        "--public-receipt",
        public_receipt,
    ]
    if paths.get("pdt") is not None:
        command.extend(["--pdt-decision", paths["pdt"]])
    if paths.get("gate") is not None:
        command.extend(["--deployment-gate", paths["gate"]])
    protected = {
        "--candidate-definition": paths.get("candidate_definition"),
        "--snapshot": paths.get("snapshot"),
        "--deployment-action": paths.get("deployment_action"),
        "--human-gate-decision": paths.get("human_gate_decision"),
        "--github-approval-history": paths.get("github_approval_history"),
    }
    for flag, path in protected.items():
        if path is not None:
            command.extend([flag, path])
    if args.allow_draft:
        command.append("--allow-draft")
    return command


def public_summary_base(args, path_kind, control, public_receipt):
    return {
        "schema_version": "1.0.0",
        "mechanism": "candidate-level-independent-oracle",
        "candidate_id": args.candidate_id,
        "execution_mode": args.mode,
        "path": path_kind,
        "control_decision": control["decision"],
        "treatment_decision": (
            load(public_receipt).get("treatment_decision")
        ),
        "oracle_metadata_released": True,
        "operational_mutation_performed": False,
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "public_unlock_receipt": {
            "path": "unlock-receipt.json",
            "sha256": sha256_file(public_receipt),
        },
    }


def require_cloud_gates(environment):
    required = (
        "ALLOW_EXPERIMENTAL_CLOUD_EXECUTION",
        "COST_REVIEW_ACKNOWLEDGED",
        "ALLOW_ORACLE_CLOUD_EXECUTION",
    )
    if any(environment.get(name) != "true" for name in required):
        raise ValueError(
            "runtime Oracle is disabled until all cloud, cost and Oracle gates are true"
        )


def require_immutable_image(reference, component):
    pattern = re.compile(
        r"^us-central1-docker\.pkg\.dev/microservices-demo-tcc/"
        + r"online-boutique-experiment/"
        + re.escape(component)
        + r"@sha256:[0-9a-f]{64}$"
    )
    if not isinstance(reference, str) or not pattern.fullmatch(reference):
        raise ValueError(
            f"{component} image must use the frozen immutable registry digest"
        )


def ensure_output_directories(output):
    output = pathlib.Path(output)
    if output.exists():
        raise ValueError("Oracle candidate output directory already exists")
    output.mkdir(parents=True, mode=0o700)
    public = output / "public"
    private = output / "private"
    public.mkdir(mode=0o755)
    private.mkdir(mode=0o700)
    return output.resolve(), public.resolve(), private.resolve()


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("engineering", "confirmatory"), required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--candidate-definition", type=pathlib.Path, required=True)
    parser.add_argument("--pipeline-directory", type=pathlib.Path, required=True)
    parser.add_argument("--evidence-root", type=pathlib.Path)
    parser.add_argument("--public-corpus", type=pathlib.Path, required=True)
    parser.add_argument("--oracle-manifest", type=pathlib.Path, required=True)
    parser.add_argument("--protocol", type=pathlib.Path)
    parser.add_argument("--oracle-policy", type=pathlib.Path)
    parser.add_argument("--fidelity-policy", type=pathlib.Path)
    parser.add_argument("--oracle-harness-image")
    parser.add_argument("--currency-reference-image")
    parser.add_argument("--work-order", type=pathlib.Path)
    parser.add_argument("--candidate-patch", type=pathlib.Path)
    parser.add_argument("--source-workspace", type=pathlib.Path)
    parser.add_argument("--output-directory", type=pathlib.Path, required=True)
    parser.add_argument("--allow-draft", action="store_true")
    return parser.parse_args()


def main():
    args = parse_arguments()
    try:
        repo_root = pathlib.Path(__file__).resolve().parents[2]
        if not SAFE_ID.fullmatch(args.candidate_id):
            raise ValueError("candidate ID contains invalid characters")
        defaults = {
            "protocol": repo_root / "experiment/protocol/protocol-v1.json",
            "oracle_policy": repo_root / "experiment/oracle/policy-v1.json",
            "fidelity_policy": repo_root / "experiment/pdt/fidelity-policy.json",
        }
        protocol_path = existing(args.protocol or defaults["protocol"], "protocol")
        oracle_policy = existing(
            args.oracle_policy or defaults["oracle_policy"], "Oracle policy"
        )
        fidelity_policy = existing(
            args.fidelity_policy or defaults["fidelity_policy"], "fidelity policy"
        )
        candidate_definition = existing(args.candidate_definition, "candidate definition")
        public_corpus = existing(args.public_corpus, "public corpus")
        oracle_manifest = existing(args.oracle_manifest, "private Oracle manifest")
        if not private_file(oracle_manifest):
            raise ValueError("private Oracle manifest permissions must be 0600-compatible")
        pipeline = pathlib.Path(args.pipeline_directory).resolve()
        if not pipeline.is_dir():
            raise ValueError("paired pipeline directory does not exist")
        evidence_root = pathlib.Path(
            args.evidence_root or pipeline.parent.parent
        ).resolve()
        if not evidence_root.is_dir():
            raise ValueError("paired evidence root does not exist")

        control_path = pipeline_file(pipeline, "conventional-decision.json")
        summary_path = pipeline_file(pipeline, "summary.json")
        status_path = pipeline_file(pipeline, "status.json")
        pipeline_candidate = pipeline_file(pipeline, "candidate-definition.json")
        if sha256_file(pipeline_candidate) != sha256_file(candidate_definition):
            raise ValueError("pipeline candidate definition differs from requested definition")
        protocol = load(protocol_path)
        repetitions, minimum_valid = validate_design(
            protocol, args.mode, args.allow_draft
        )
        candidate = load(candidate_definition)
        control = load(control_path)
        summary = load(summary_path)
        status = load(status_path)
        alternatives = validate_candidate(
            candidate,
            args.candidate_id,
            sha256_file(candidate_definition),
            control,
            args.mode,
        )
        if summary.get("candidate_id") != args.candidate_id:
            raise ValueError("paired summary candidate differs")
        if status.get("state") != "completed":
            raise ValueError("paired pipeline is not terminally completed")
        path_kind = classify_control_path(control)

        paths = {
            "unlock_script": repo_root
            / "experiment/scripts/unlock-oracle-candidate.py",
            "public_corpus": public_corpus,
            "oracle_manifest": oracle_manifest,
            "candidate_definition": candidate_definition,
            "control": control_path,
        }
        predictions = {}
        invalid_ledger = None
        treatment_decision = "block"
        preartifact_inputs = None
        if path_kind == "runtime":
            require_cloud_gates(os.environ)
            require_immutable_image(args.oracle_harness_image, "oracle-harness")
            require_immutable_image(
                args.currency_reference_image, "currency-reference"
            )
            snapshot = pipeline_file(pipeline, "oracle-binding-snapshot.json")
            paths["snapshot"] = snapshot
            if control["decision"] == "approve":
                pdt_path = pipeline_file(pipeline, "pdt-decision.json")
                gate_path = pipeline_file(pipeline, "gate.json")
                pdt = load(pdt_path)
                treatment_decision = pdt.get("decision")
                if treatment_decision not in {"approve", "block", "reconfigure"}:
                    raise ValueError("PDT decision is not terminal")
                validate_snapshot_binding(snapshot, summary, pdt)
                predictions, invalid_ledger = resolve_prediction_inputs(
                    pdt, evidence_root, repetitions, minimum_valid
                )
                paths.update({"pdt": pdt_path, "gate": gate_path})
                if treatment_decision in {"approve", "reconfigure"}:
                    paths.update(
                        {
                            "deployment_action": pipeline_file(
                                pipeline, "deployment-action.json"
                            ),
                            "human_gate_decision": pipeline_file(
                                pipeline, "human-gate-decision.json"
                            ),
                            "github_approval_history": pipeline_file(
                                pipeline, "github-environment-approvals.json"
                            ),
                        }
                    )
            else:
                validate_snapshot_binding(snapshot, summary)
        else:
            if args.source_workspace is None:
                raise ValueError("sealed candidate source workspace is required")
            source_workspace = pathlib.Path(args.source_workspace).resolve()
            if not source_workspace.is_dir():
                raise ValueError("sealed candidate source workspace does not exist")
            preartifact_inputs = {
                "local_ci": pipeline_file(pipeline, "local-ci-decision.json"),
                "work_order": existing(
                    args.work_order, "private candidate work order"
                ),
                "candidate_patch": existing(
                    args.candidate_patch, "private candidate patch"
                ),
                "source_workspace": source_workspace,
            }
            for private_input in (
                preartifact_inputs["work_order"],
                preartifact_inputs["candidate_patch"],
            ):
                if not private_file(private_input):
                    raise ValueError("preartifact private input permissions are unsafe")

        output, public_dir, private_dir = ensure_output_directories(
            args.output_directory
        )
        private_work_item = private_dir / "private-work-item.json"
        public_receipt = public_dir / "unlock-receipt.json"
        run_command(
            unlock_command(args, paths, private_work_item, public_receipt),
            cwd=repo_root,
            log_path=private_dir / "unlock.log",
        )

        if path_kind == "preartifact":
            adjudication = private_dir / "preartifact-adjudication.json"
            verification_log = private_dir / "preartifact-verification.log"
            run_command(
                [
                    sys.executable,
                    repo_root / "experiment/scripts/evaluate-oracle-preartifact.py",
                    "--policy",
                    oracle_policy,
                    "--candidate-definition",
                    candidate_definition,
                    "--private-work-item",
                    private_work_item,
                    "--work-order",
                    preartifact_inputs["work_order"],
                    "--candidate-patch",
                    preartifact_inputs["candidate_patch"],
                    "--conventional-decision",
                    control_path,
                    "--local-ci-decision",
                    preartifact_inputs["local_ci"],
                    "--source-workspace",
                    preartifact_inputs["source_workspace"],
                    "--log-output",
                    verification_log,
                    "--output",
                    adjudication,
                ],
                cwd=repo_root,
                log_path=private_dir / "preartifact-runner.log",
            )
            result = public_summary_base(
                args, path_kind, control, public_receipt
            )
            result.update(
                {
                    "status": "completed",
                    "matrix": None,
                    "oracle_observation_count": 0,
                    "pdt_fidelity": None,
                    "private_result_sha256": sha256_file(adjudication),
                    "input_sha256": {
                        "candidate_definition": sha256_file(candidate_definition),
                        "conventional_decision": sha256_file(control_path),
                        "protocol": sha256_file(protocol_path),
                        "oracle_policy": sha256_file(oracle_policy),
                    },
                }
            )
        else:
            execution_index = []
            observation_paths = []
            fidelity_paths = []
            for item in matrix(alternatives, repetitions):
                alternative = item["alternative_id"]
                repetition = item["repetition"]
                environment = os.environ.copy()
                environment.update(
                    {
                        "MODE": args.mode,
                        "CANDIDATE_ID": args.candidate_id,
                        "CANDIDATE_DEFINITION": str(candidate_definition),
                        "CONVENTIONAL_DECISION": str(control_path),
                        "PRIVATE_WORK_ITEM": str(private_work_item),
                        "SNAPSHOT_FILE": str(paths["snapshot"]),
                        "ALTERNATIVE_ID": alternative,
                        "REPETITION": str(repetition),
                        "ORACLE_HARNESS_IMAGE": args.oracle_harness_image,
                        "CURRENCY_REFERENCE_IMAGE": args.currency_reference_image,
                        "ORACLE_POLICY": str(oracle_policy),
                        "FIDELITY_POLICY": str(fidelity_policy),
                        "ALLOW_EXPERIMENTAL_CLOUD_EXECUTION": "true",
                        "COST_REVIEW_ACKNOWLEDGED": "true",
                        "ALLOW_ORACLE_CLOUD_EXECUTION": "true",
                    }
                )
                if control["decision"] == "approve":
                    environment.update(
                        {
                            "PDT_DECISION": str(paths["pdt"]),
                            "DEPLOYMENT_GATE": str(paths["gate"]),
                        }
                    )
                    prediction = predictions.get(repetition)
                    if prediction is not None:
                        environment["PDT_PREDICTION_DECISION"] = str(prediction)
                    else:
                        environment["PDT_INVALID_REPETITION_LEDGER"] = str(
                            invalid_ledger
                        )
                    if treatment_decision in {"approve", "reconfigure"}:
                        environment.update(
                            {
                                "DEPLOYMENT_ACTION": str(paths["deployment_action"]),
                                "HUMAN_GATE_DECISION": str(paths["human_gate_decision"]),
                                "GITHUB_APPROVAL_HISTORY": str(
                                    paths["github_approval_history"]
                                ),
                            }
                        )
                log_path = private_dir / f"{alternative}-r{repetition}.log"
                stdout = run_command(
                    [repo_root / "experiment/scripts/run-oracle-repetition.sh"],
                    cwd=repo_root,
                    environment=environment,
                    log_path=log_path,
                )
                lines = [line.strip() for line in stdout.splitlines() if line.strip()]
                if not lines:
                    raise ValueError("Oracle repetition did not report its evidence directory")
                run_dir = pathlib.Path(lines[-1]).resolve()
                try:
                    run_dir.relative_to(repo_root / "experiment/evidence/oracle")
                except ValueError as error:
                    raise ValueError("Oracle repetition returned an unsafe evidence path") from error
                observation = existing(run_dir / "observation.json", "Oracle observation")
                metadata = load(existing(run_dir / "metadata.json", "Oracle metadata"))
                if (
                    metadata.get("candidate_id") != args.candidate_id
                    or metadata.get("alternative_id") != alternative
                    or metadata.get("repetition") != repetition
                ):
                    raise ValueError("Oracle repetition metadata differs from the requested matrix cell")
                fidelity = run_dir / "pdt-fidelity.json"
                fidelity_value = None
                if fidelity.is_file():
                    fidelity = fidelity.resolve()
                    fidelity_paths.append(fidelity)
                    fidelity_value = sha256_file(fidelity)
                observation_paths.append(observation)
                execution_index.append(
                    {
                        "alternative_id": alternative,
                        "repetition": repetition,
                        "run_id": metadata.get("run_id"),
                        "observation_sha256": sha256_file(observation),
                        "fidelity_sha256": fidelity_value,
                    }
                )

            adjudication = private_dir / "oracle-adjudication.json"
            adjudication_command = [
                sys.executable,
                repo_root / "experiment/scripts/adjudicate-oracle.py",
                "--policy",
                oracle_policy,
                "--candidate-definition",
                candidate_definition,
                "--private-work-item",
                private_work_item,
            ]
            for observation in observation_paths:
                adjudication_command.extend(["--observation", observation])
            adjudication_command.extend(["--output", adjudication])
            run_command(
                adjudication_command,
                cwd=repo_root,
                log_path=private_dir / "adjudication.log",
            )

            fidelity_aggregate = None
            if control["decision"] == "approve":
                expected_fidelity = len(alternatives) * len(predictions)
                if len(fidelity_paths) != expected_fidelity:
                    raise ValueError("PDT fidelity reports do not cover the valid prediction matrix")
                fidelity_aggregate = private_dir / "pdt-fidelity-aggregate.json"
                fidelity_command = [
                    sys.executable,
                    repo_root / "experiment/scripts/aggregate-pdt-fidelity.py",
                    "--protocol",
                    protocol_path,
                    "--policy",
                    fidelity_policy,
                    "--candidate-definition",
                    candidate_definition,
                ]
                for report in fidelity_paths:
                    fidelity_command.extend(["--report", report])
                if invalid_ledger is not None:
                    fidelity_command.extend(
                        ["--infrastructure-invalid-ledger", invalid_ledger]
                    )
                if args.allow_draft:
                    fidelity_command.append("--allow-draft")
                fidelity_command.extend(["--output", fidelity_aggregate])
                run_command(
                    fidelity_command,
                    cwd=repo_root,
                    log_path=private_dir / "fidelity-aggregation.log",
                )

            result = public_summary_base(
                args, path_kind, control, public_receipt
            )
            result.update(
                {
                    "status": "completed",
                    "matrix": {
                        "deployable_alternatives": alternatives,
                        "repetitions": repetitions,
                        "expected_cells": len(alternatives) * len(repetitions),
                        "completed_cells": len(execution_index),
                        "complete": len(execution_index)
                        == len(alternatives) * len(repetitions),
                    },
                    "oracle_observation_count": len(observation_paths),
                    "execution_index": execution_index,
                    "pdt_fidelity": (
                        {
                            "available": True,
                            "report_count": len(fidelity_paths),
                            "aggregate_sha256": sha256_file(fidelity_aggregate),
                        }
                        if fidelity_aggregate is not None
                        else None
                    ),
                    "private_result_sha256": sha256_file(adjudication),
                    "input_sha256": {
                        "candidate_definition": sha256_file(candidate_definition),
                        "conventional_decision": sha256_file(control_path),
                        "protocol": sha256_file(protocol_path),
                        "oracle_policy": sha256_file(oracle_policy),
                        "fidelity_policy": sha256_file(fidelity_policy),
                        "oracle_binding_snapshot": sha256_file(paths["snapshot"]),
                        "pdt_decision": (
                            sha256_file(paths["pdt"])
                            if paths.get("pdt") is not None
                            else None
                        ),
                        "deployment_gate": (
                            sha256_file(paths["gate"])
                            if paths.get("gate") is not None
                            else None
                        ),
                    },
                }
            )

        leaked = sorted(set(recursively_find_keys(result)))
        if leaked:
            raise ValueError(
                "public Oracle summary contains forbidden private keys: "
                + ", ".join(leaked)
            )
        summary_output = public_dir / "summary.json"
        write_json_exclusive(summary_output, result, 0o644)
        print(output)
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        json.JSONDecodeError,
    ) as error:
        print(f"candidate Oracle orchestration failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
