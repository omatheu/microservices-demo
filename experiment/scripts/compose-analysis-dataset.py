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
    for public_entry in public_entries:
        candidate_id = public_entry["candidate_id"]
        item = by_id[candidate_id]
        exclusion = item.get("exclusion")
        if exclusion is not None:
            if not isinstance(exclusion, dict) or not exclusion.get("reason"):
                raise ValueError("candidate exclusion must contain a reason")
            candidates.append({"candidate_id": candidate_id, "exclusion": exclusion})
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
        if confirmatory and oracle.get("eligible_for_primary_analysis") is not True:
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
