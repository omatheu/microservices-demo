#!/usr/bin/env python3

"""Compose the candidate-level analysis dataset from hash-bound evidence."""

import argparse
import datetime
import hashlib
import json
import pathlib
import re


DIGEST = re.compile(r"^[0-9a-f]{64}$")


def load(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_binding(repo_root, binding, label):
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise ValueError(f"{label} must contain only path and sha256")
    relative = pathlib.PurePosixPath(binding.get("path", ""))
    expected = binding.get("sha256")
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{label} contains an unsafe evidence path")
    if not isinstance(expected, str) or not DIGEST.fullmatch(expected):
        raise ValueError(f"{label} contains an invalid evidence digest")
    path = pathlib.Path(repo_root) / relative
    if not path.is_file() or sha256_file(path) != expected:
        raise ValueError(f"{label} evidence hash differs")
    return load(path)


def validate_metrics(metrics, label):
    if metrics is None:
        return {}
    if not isinstance(metrics, dict):
        raise ValueError(f"{label} continuous metrics must be an object")
    return metrics.copy()


def validate_exclusion(repo_root, candidate_id, planned_repetitions, exclusion, protocol):
    required_keys = {
        "reason_code",
        "reason",
        "decided_before_oracle_label",
        "label_revealed",
        "valid_repetitions",
        "invalid_repetitions",
        "replacement_attempted",
        "evidence",
    }
    if not isinstance(exclusion, dict) or set(exclusion) != required_keys:
        raise ValueError("candidate exclusion has an incomplete or unexpected schema")
    minimum_valid = protocol.get("aggregation", {}).get("minimum_valid_repetitions")
    if exclusion.get("reason_code") != "insufficient-valid-repetitions":
        raise ValueError("candidate exclusion reason code is not protocol-authorized")
    if not isinstance(exclusion.get("reason"), str) or not exclusion["reason"].strip():
        raise ValueError("candidate exclusion must contain a non-empty reason")
    if (
        exclusion.get("decided_before_oracle_label") is not True
        or exclusion.get("label_revealed") is not False
    ):
        raise ValueError("candidate exclusion must be decided before oracle label release")
    if exclusion.get("replacement_attempted") is not True:
        raise ValueError("candidate exclusion requires the protocol replacement attempt")
    valid = exclusion.get("valid_repetitions")
    invalid = exclusion.get("invalid_repetitions")
    if (
        not isinstance(valid, list)
        or not isinstance(invalid, list)
        or any(not isinstance(item, int) or isinstance(item, bool) for item in valid + invalid)
        or len(valid) != len(set(valid))
        or len(invalid) != len(set(invalid))
        or valid != sorted(valid)
        or invalid != sorted(invalid)
        or set(valid) & set(invalid)
        or set(valid) | set(invalid) != set(planned_repetitions)
        or not isinstance(minimum_valid, int)
        or isinstance(minimum_valid, bool)
        or minimum_valid <= 0
        or minimum_valid > len(planned_repetitions)
        or len(valid) >= minimum_valid
    ):
        raise ValueError("candidate exclusion repetition accounting is invalid")

    evidence = resolve_binding(
        repo_root, exclusion.get("evidence"), f"{candidate_id} exclusion ledger"
    )
    invalid_attempts = (
        evidence.get("invalid_repetitions") if isinstance(evidence, dict) else None
    )
    evidence_keys = {
        "schema_version",
        "candidate_id",
        "classification",
        "label_revealed",
        "planned_repetitions",
        "valid_repetitions",
        "invalid_repetitions",
    }
    if (
        not isinstance(evidence, dict)
        or set(evidence) != evidence_keys
        or evidence.get("schema_version") != "1.0.0"
        or evidence.get("candidate_id") != candidate_id
        or evidence.get("classification") != "infrastructure-invalid"
        or evidence.get("label_revealed") is not False
        or evidence.get("planned_repetitions") != planned_repetitions
        or evidence.get("valid_repetitions") != valid
        or not isinstance(invalid_attempts, list)
        or len(invalid_attempts) != len(invalid)
    ):
        raise ValueError("candidate exclusion ledger differs from the declared repetitions")
    for expected_repetition, item in zip(invalid, invalid_attempts):
        if (
            not isinstance(item, dict)
            or set(item) != {"repetition", "attempts", "reasons"}
            or item.get("repetition") != expected_repetition
            or item.get("attempts") != 2
            or not isinstance(item.get("reasons"), list)
            or len(item["reasons"]) != 2
            or not all(
                isinstance(reason, str) and reason.strip() for reason in item["reasons"]
            )
        ):
            raise ValueError("excluded repetition lacks both infrastructure-invalid attempts")
    return {
        "reason_code": exclusion["reason_code"],
        "reason": exclusion["reason"].strip(),
        "decided_before_oracle_label": True,
        "label_revealed": False,
        "valid_repetitions": valid.copy(),
        "invalid_repetitions": invalid.copy(),
        "replacement_attempted": True,
        "evidence": exclusion["evidence"].copy(),
    }


def compose(protocol, protocol_sha256, public, public_sha256, manifest, repo_root, allow_draft=False):
    confirmatory = (
        protocol.get("status") == "frozen"
        and protocol.get("confirmatory_collection_allowed") is True
        and bool(protocol.get("frozen_at"))
    )
    if not confirmatory and not allow_draft:
        raise ValueError("candidate dataset composition requires a frozen protocol")
    if (
        public.get("protocol_id") != protocol.get("protocol_id")
        or public.get("protocol_sha256") != protocol_sha256
    ):
        raise ValueError("public corpus is not bound to the supplied protocol")
    if confirmatory and public.get("confirmatory_eligible") is not True:
        raise ValueError("confirmatory composition requires an eligible public corpus")
    if (
        manifest.get("protocol_id") != protocol.get("protocol_id")
        or manifest.get("protocol_sha256") != protocol_sha256
        or manifest.get("public_corpus_sha256") != public_sha256
    ):
        raise ValueError("collection manifest bindings differ from protocol or corpus")
    if manifest.get("collection_complete") is not True:
        raise ValueError("collection manifest must be explicitly complete")

    public_entries = public.get("execution_order")
    manifest_entries = manifest.get("candidates")
    declared_count = protocol.get("research_design", {}).get("candidate_count")
    if (
        not isinstance(public_entries, list)
        or not isinstance(manifest_entries, list)
        or len(public_entries) != declared_count
        or len(manifest_entries) != declared_count
    ):
        raise ValueError("corpus or manifest candidate count differs from the protocol")
    public_ids = [item.get("candidate_id") for item in public_entries]
    manifest_ids = [item.get("candidate_id") for item in manifest_entries]
    if len(set(public_ids)) != len(public_ids) or set(public_ids) != set(manifest_ids):
        raise ValueError("collection manifest candidate set differs from the public corpus")
    by_id = {item["candidate_id"]: item for item in manifest_entries}

    candidates = []
    manifest_exclusions = []
    for public_entry in public_entries:
        candidate_id = public_entry["candidate_id"]
        planned_repetitions = public_entry.get("repetitions")
        required_repetitions = protocol.get("research_design", {}).get(
            "technical_repetitions_per_candidate"
        )
        if (
            not isinstance(required_repetitions, int)
            or required_repetitions <= 0
            or planned_repetitions != list(range(1, required_repetitions + 1))
        ):
            raise ValueError("public corpus repetition plan differs from the protocol")
        item = by_id[candidate_id]
        exclusion = item.get("exclusion")
        if exclusion is not None:
            normalized = validate_exclusion(
                repo_root,
                candidate_id,
                planned_repetitions,
                exclusion,
                protocol,
            )
            if any(
                item.get(field) is not None
                for field in (
                    "conventional_decision",
                    "pdt_decision",
                    "deployment_gate",
                    "oracle_adjudication",
                    "control_continuous_metrics",
                    "treatment_continuous_metrics",
                )
            ):
                raise ValueError(
                    f"{candidate_id} excluded candidate must not contain decision or oracle evidence"
                )
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "sequence": public_entry.get("sequence"),
                    "repetitions": public_entry.get("repetitions"),
                    "exclusion": normalized,
                }
            )
            manifest_exclusions.append(
                {"candidate_id": candidate_id, **normalized}
            )
            continue

        control = resolve_binding(
            repo_root, item.get("conventional_decision"), f"{candidate_id} conventional decision"
        )
        oracle = resolve_binding(
            repo_root, item.get("oracle_adjudication"), f"{candidate_id} oracle adjudication"
        )
        if (
            control.get("candidate_id") != candidate_id
            or control.get("mechanism") != "conventional-ci-cd-with-staging"
            or control.get("control_decision_sealed") is not True
            or control.get("decision") not in {"approve", "block"}
            or control.get("operational_mutation_performed") is not False
        ):
            raise ValueError(f"{candidate_id} conventional decision is invalid or unsealed")
        if oracle.get("candidate_id") != candidate_id:
            raise ValueError(f"{candidate_id} oracle adjudication belongs to another candidate")
        if confirmatory:
            actual = oracle.get("observed_deploy_as_is_label")
            eligible = oracle.get("eligible_for_primary_analysis")
            if actual == "inconclusive" and eligible is not False:
                raise ValueError(
                    f"{candidate_id} inconclusive oracle adjudication must be analysis-ineligible"
                )
            if actual != "inconclusive" and eligible is not True:
                raise ValueError(f"{candidate_id} oracle adjudication is not analysis-eligible")

        control_result = {
            "decision": control["decision"],
            "selected_alternative": (
                "deploy-as-is" if control["decision"] == "approve" else "block"
            ),
            "continuous_metrics": validate_metrics(
                item.get("control_continuous_metrics"), f"{candidate_id} control"
            ),
        }
        if control["decision"] == "approve":
            pdt = resolve_binding(repo_root, item.get("pdt_decision"), f"{candidate_id} PDT decision")
            gate = resolve_binding(
                repo_root, item.get("deployment_gate"), f"{candidate_id} deployment gate"
            )
            if (
                pdt.get("candidate") != candidate_id
                or pdt.get("decision") not in {"approve", "block", "reconfigure"}
                or not pdt.get("selected_alternative")
                or pdt.get("artifact_binding", {}).get("immutable_artifacts")
                != control.get("immutable_artifacts")
                or pdt.get("artifact_binding", {}).get("candidate_definition_sha256")
                != control.get("candidate_definition_sha256")
            ):
                raise ValueError(f"{candidate_id} PDT decision is invalid or not control-bound")
            expected_gate = (
                "blocked" if pdt["decision"] == "block" else "awaiting-human-confirmation"
            )
            if (
                gate.get("candidate_id") != candidate_id
                or gate.get("gate_state") != expected_gate
                or gate.get("operational_mutation_performed") is not False
            ):
                raise ValueError(f"{candidate_id} deployment gate is inconsistent")
            treatment_result = {
                "decision": pdt["decision"],
                "selected_alternative": pdt["selected_alternative"],
                "continuous_metrics": validate_metrics(
                    item.get("treatment_continuous_metrics"), f"{candidate_id} treatment"
                ),
            }
        else:
            if item.get("pdt_decision") is not None or item.get("deployment_gate") is not None:
                raise ValueError(f"{candidate_id} control-blocked candidate must not contain PDT evidence")
            treatment_result = {
                "decision": "block",
                "selected_alternative": "block",
                "continuous_metrics": validate_metrics(
                    item.get("treatment_continuous_metrics"), f"{candidate_id} treatment"
                ),
            }

        candidates.append(
            {
                "candidate_id": candidate_id,
                "sequence": public_entry.get("sequence"),
                "repetitions": public_entry.get("repetitions"),
                "exclusion": None,
                "control": control_result,
                "treatment": treatment_result,
                "oracle": oracle,
            }
        )

    return {
        "schema_version": "1.0.0",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": protocol_sha256,
        "corpus_id": public.get("corpus_id"),
        "public_corpus_sha256": public_sha256,
        "collection_complete": True,
        "confirmatory_eligible": confirmatory and not allow_draft,
        "composition_mode": "confirmatory" if confirmatory and not allow_draft else "engineering-dry-run",
        "collection_flow": {
            "declared_candidates": declared_count,
            "candidate_records": len(candidates),
            "complete_decision_pairs": declared_count - len(manifest_exclusions),
            "manifest_exclusions": manifest_exclusions,
            "silently_missing_candidates": 0,
        },
        "candidates": candidates,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=pathlib.Path, required=True)
    parser.add_argument("--protocol", type=pathlib.Path, required=True)
    parser.add_argument("--public-corpus", type=pathlib.Path, required=True)
    parser.add_argument("--collection-manifest", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--allow-draft", action="store_true")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    try:
        result = compose(
            load(args.protocol),
            sha256_file(args.protocol),
            load(args.public_corpus),
            sha256_file(args.public_corpus),
            load(args.collection_manifest),
            repo_root,
            allow_draft=args.allow_draft,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"analysis dataset composition failed: {error}") from error
    result["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    result["inputs"] = {
        "protocol": str(args.protocol),
        "public_corpus": str(args.public_corpus),
        "collection_manifest": str(args.collection_manifest),
        "collection_manifest_sha256": sha256_file(args.collection_manifest),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
