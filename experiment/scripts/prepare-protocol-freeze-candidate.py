#!/usr/bin/env python3

"""Prepare a coherent, non-applying protocol-freeze candidate bundle."""

import argparse
import copy
import hashlib
import json
import os
import pathlib
import re
import sys


DIGEST = re.compile(r"^[a-f0-9]{64}$")
COMMIT = re.compile(r"^[a-f0-9]{40}$")
RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
PDT_IMAGE = re.compile(
    r"^us-central1-docker\.pkg\.dev/microservices-demo-tcc/"
    r"online-boutique-experiment/checkout-pdt-controller@sha256:[a-f0-9]{64}$"
)
ORACLE_IMAGES = {
    "oracle_harness": re.compile(
        r"^us-central1-docker\.pkg\.dev/microservices-demo-tcc/"
        r"online-boutique-experiment/oracle-harness@sha256:[a-f0-9]{64}$"
    ),
    "currency_reference": re.compile(
        r"^us-central1-docker\.pkg\.dev/microservices-demo-tcc/"
        r"online-boutique-experiment/currency-reference@sha256:[a-f0-9]{64}$"
    ),
}
PUBLICATION_BINDING_KEYS = {
    "schema_version",
    "publication_summary_sha256",
    "repository",
    "source_commit",
    "source_tree",
    "pull_request_number",
    "workflow_run_id",
    "published_at",
    "build_platform",
    "protected_environment",
    "explicit_cloud_gate",
    "cost_review_acknowledged",
}
PROTOCOL_PATH = "experiment/protocol/protocol-v1.json"
PDT_RUNTIME_PATH = "experiment/pdt/runtime-manifest.json"
ORACLE_SUITE_PATH = "experiment/oracle/suite-manifest.json"
POLICY_INPUTS = {
    "experiment/ci/policy.json": "ci_policy",
    "experiment/staging/safety-thresholds.json": "staging_thresholds",
    "experiment/pdt/model-policy.json": "pdt_model_policy",
    "experiment/pdt/fidelity-policy.json": None,
    "experiment/oracle/policy-v1.json": None,
}


def load(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def render(value):
    return (json.dumps(value, indent=2) + "\n").encode()


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def publication_identity(binding):
    if not (
        isinstance(binding, dict)
        and set(binding) == PUBLICATION_BINDING_KEYS
        and binding.get("schema_version") == "1.0.0"
        and isinstance(binding.get("publication_summary_sha256"), str)
        and DIGEST.fullmatch(binding["publication_summary_sha256"])
        and binding.get("repository") == "omatheu/microservices-demo"
        and isinstance(binding.get("source_commit"), str)
        and COMMIT.fullmatch(binding["source_commit"])
        and isinstance(binding.get("source_tree"), str)
        and COMMIT.fullmatch(binding["source_tree"])
        and isinstance(binding.get("pull_request_number"), int)
        and not isinstance(binding["pull_request_number"], bool)
        and binding["pull_request_number"] > 0
        and isinstance(binding.get("workflow_run_id"), str)
        and binding["workflow_run_id"].isdigit()
        and int(binding["workflow_run_id"]) > 0
        and isinstance(binding.get("published_at"), str)
        and RFC3339.fullmatch(binding["published_at"])
        and binding.get("build_platform") == "linux/amd64"
        and binding.get("protected_environment") == "tcc-experiment"
        and binding.get("explicit_cloud_gate") is True
        and binding.get("cost_review_acknowledged") is True
    ):
        return None
    return tuple(binding[name] for name in sorted(PUBLICATION_BINDING_KEYS))


def validate_inventory(repo_root, manifest, label):
    entries = manifest.get("files")
    require(isinstance(entries, list) and entries, f"{label} inventory is empty")
    paths = [item.get("path") for item in entries if isinstance(item, dict)]
    require(
        len(paths) == len(entries) and len(paths) == len(set(paths)),
        f"{label} inventory is invalid or duplicated",
    )
    for item in entries:
        relative = pathlib.PurePosixPath(item["path"])
        expected = item.get("sha256")
        require(
            relative.parts and not relative.is_absolute() and ".." not in relative.parts,
            f"{label} contains an unsafe path",
        )
        require(
            isinstance(expected, str) and DIGEST.fullmatch(expected),
            f"{label} contains an invalid hash",
        )
        require(
            sha256_file(pathlib.Path(repo_root) / relative) == expected,
            f"{label} hash differs: {item['path']}",
        )


def replace_inventory_hash(manifest, path, digest, label):
    matches = [item for item in manifest["files"] if item.get("path") == path]
    require(len(matches) == 1, f"{label} must contain exactly one {path} binding")
    matches[0]["sha256"] = digest


def validate_protocol_candidate(repo_root, protocol):
    require(
        protocol.get("status") == "pre-registration-candidate"
        and protocol.get("frozen_at") is None
        and protocol.get("confirmatory_collection_allowed") is False,
        "protocol must remain a locked pre-registration candidate",
    )
    inputs = protocol.get("frozen_inputs")
    require(isinstance(inputs, dict) and inputs, "protocol input bindings are absent")
    for name, binding in inputs.items():
        require(
            isinstance(binding, dict) and set(binding) == {"path", "sha256"},
            f"protocol input {name} is invalid",
        )
        relative = pathlib.PurePosixPath(binding["path"])
        require(
            relative.parts and not relative.is_absolute() and ".." not in relative.parts,
            f"protocol input {name} path is unsafe",
        )
        require(
            isinstance(binding["sha256"], str)
            and DIGEST.fullmatch(binding["sha256"])
            and sha256_file(pathlib.Path(repo_root) / relative) == binding["sha256"],
            f"protocol input {name} hash differs",
        )


def validate_bound_manifests(repo_root, pdt_bound, oracle_bound):
    current_pdt = load(pathlib.Path(repo_root) / PDT_RUNTIME_PATH)
    current_oracle = load(pathlib.Path(repo_root) / ORACLE_SUITE_PATH)
    require(
        pdt_bound.get("runtime_id") == "checkout-pdt-controller-v1",
        "bound PDT runtime identity is invalid",
    )
    require(
        oracle_bound.get("suite_id") == "checkout-independent-oracle-v1",
        "bound oracle suite identity is invalid",
    )
    for manifest, label in (
        (pdt_bound, "bound PDT runtime"),
        (oracle_bound, "bound oracle suite"),
    ):
        require(
            manifest.get("status") == "pre-registration-candidate"
            and manifest.get("frozen_at") is None,
            f"{label} must not already be frozen",
        )
        validate_inventory(repo_root, manifest, label)

    expected_pdt = copy.deepcopy(current_pdt)
    expected_pdt["controller_image"] = pdt_bound.get("controller_image")
    expected_pdt["publication_binding"] = pdt_bound.get("publication_binding")
    expected_oracle = copy.deepcopy(current_oracle)
    expected_oracle["images"] = copy.deepcopy(oracle_bound.get("images"))
    expected_oracle["publication_binding"] = oracle_bound.get("publication_binding")
    require(pdt_bound == expected_pdt, "bound PDT manifest changes more than publication fields")
    require(
        oracle_bound == expected_oracle,
        "bound oracle manifest changes more than publication fields",
    )

    pdt_publication = publication_identity(pdt_bound.get("publication_binding"))
    oracle_publication = publication_identity(oracle_bound.get("publication_binding"))
    require(
        pdt_publication is not None and pdt_publication == oracle_publication,
        "PDT and oracle manifests do not share one valid publication",
    )
    require(
        isinstance(pdt_bound.get("controller_image"), str)
        and PDT_IMAGE.fullmatch(pdt_bound["controller_image"]),
        "bound PDT controller image is invalid",
    )
    images = oracle_bound.get("images")
    require(
        isinstance(images, dict)
        and set(images) == set(ORACLE_IMAGES)
        and all(
            isinstance(images.get(name), str) and pattern.fullmatch(images[name])
            for name, pattern in ORACLE_IMAGES.items()
        ),
        "bound oracle images are invalid",
    )
    return copy.deepcopy(pdt_bound["publication_binding"])


def prepare(repo_root, protocol, pdt_bound, oracle_bound, frozen_at):
    repo_root = pathlib.Path(repo_root)
    require(
        isinstance(frozen_at, str) and RFC3339.fullmatch(frozen_at),
        "frozen-at must be an RFC3339 UTC timestamp",
    )
    validate_protocol_candidate(repo_root, protocol)
    publication = validate_bound_manifests(repo_root, pdt_bound, oracle_bound)
    require(
        frozen_at >= publication["published_at"],
        "frozen-at cannot precede the runtime publication",
    )

    proposed = {}
    for relative in POLICY_INPUTS:
        value = load(repo_root / relative)
        require(
            value.get("status") == "pre-registration-candidate"
            and value.get("frozen_at") is None,
            f"{relative} is not an unfrozen policy candidate",
        )
        value["status"] = "frozen"
        value["frozen_at"] = frozen_at
        proposed[relative] = value

    pdt_frozen = copy.deepcopy(pdt_bound)
    pdt_frozen["status"] = "frozen"
    pdt_frozen["frozen_at"] = frozen_at
    replace_inventory_hash(
        pdt_frozen,
        "experiment/pdt/model-policy.json",
        sha256_bytes(render(proposed["experiment/pdt/model-policy.json"])),
        "PDT runtime manifest",
    )
    proposed[PDT_RUNTIME_PATH] = pdt_frozen

    oracle_frozen = copy.deepcopy(oracle_bound)
    oracle_frozen["status"] = "frozen"
    oracle_frozen["frozen_at"] = frozen_at
    for relative in (
        "experiment/pdt/fidelity-policy.json",
        "experiment/oracle/policy-v1.json",
    ):
        replace_inventory_hash(
            oracle_frozen,
            relative,
            sha256_bytes(render(proposed[relative])),
            "oracle suite manifest",
        )
    proposed[ORACLE_SUITE_PATH] = oracle_frozen

    protocol_candidate = copy.deepcopy(protocol)
    proposed_hashes = {
        path: sha256_bytes(render(value)) for path, value in proposed.items()
    }
    for relative, input_name in POLICY_INPUTS.items():
        if input_name is not None:
            protocol_candidate["frozen_inputs"][input_name]["sha256"] = proposed_hashes[
                relative
            ]
    protocol_candidate["frozen_inputs"]["pdt_runtime_manifest"]["sha256"] = (
        proposed_hashes[PDT_RUNTIME_PATH]
    )
    protocol_candidate["frozen_inputs"]["oracle_suite_manifest"]["sha256"] = (
        proposed_hashes[ORACLE_SUITE_PATH]
    )
    proposed[PROTOCOL_PATH] = protocol_candidate

    rendered = {path: render(value) for path, value in proposed.items()}
    receipt = {
        "schema_version": "1.0.0",
        "mechanism": "protocol-freeze-candidate-bundle",
        "status": "prepared-requires-application-and-approvals",
        "frozen_at_for_components": frozen_at,
        "publication_binding": publication,
        "candidate_protocol_sha256": sha256_bytes(rendered[PROTOCOL_PATH]),
        "proposed_files": [
            {"path": path, "sha256": sha256_bytes(content)}
            for path, content in sorted(rendered.items())
        ],
        "protocol_status_after_application": "pre-registration-candidate",
        "confirmatory_collection_allowed_after_application": False,
        "cloud_execution_authorized": False,
        "cloud_mutation_performed": False,
        "active_repository_files_modified": False,
    }
    return rendered, receipt


def write_exclusive(path, content):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=pathlib.Path, required=True)
    parser.add_argument(
        "--protocol",
        type=pathlib.Path,
        default=pathlib.Path(PROTOCOL_PATH),
    )
    parser.add_argument("--bound-pdt-manifest", type=pathlib.Path, required=True)
    parser.add_argument("--bound-oracle-manifest", type=pathlib.Path, required=True)
    parser.add_argument("--frozen-at", required=True)
    parser.add_argument("--output-directory", type=pathlib.Path, required=True)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    try:
        rendered, receipt = prepare(
            repo_root,
            load(repo_root / args.protocol),
            load(args.bound_pdt_manifest),
            load(args.bound_oracle_manifest),
            args.frozen_at,
        )
        for relative, content in rendered.items():
            write_exclusive(args.output_directory / "proposed" / relative, content)
        receipt_content = render(receipt)
        write_exclusive(
            args.output_directory / "freeze-candidate-receipt.json", receipt_content
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"protocol freeze candidate rejected: {error}", file=sys.stderr)
        return 1
    print(receipt_content.decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
