import copy
import importlib.util
import json
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = (
    REPO_ROOT / "experiment" / "scripts" / "prepare-protocol-freeze-candidate.py"
)
PROTOCOL_PATH = REPO_ROOT / "experiment" / "protocol" / "protocol-v1.json"
PDT_MANIFEST_PATH = REPO_ROOT / "experiment" / "pdt" / "runtime-manifest.json"
ORACLE_MANIFEST_PATH = REPO_ROOT / "experiment" / "oracle" / "suite-manifest.json"
SPEC = importlib.util.spec_from_file_location(
    "prepare_protocol_freeze_candidate", SCRIPT_PATH
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


FROZEN_AT = "2026-09-22T03:00:00Z"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def publication_binding():
    return {
        "schema_version": "1.0.0",
        "publication_summary_sha256": "a" * 64,
        "repository": "omatheu/microservices-demo",
        "source_commit": "b" * 40,
        "source_tree": "c" * 40,
        "pull_request_number": 42,
        "workflow_run_id": "1234",
        "published_at": "2026-09-22T02:00:00Z",
        "build_platform": "linux/amd64",
        "protected_environment": "tcc-experiment",
        "explicit_cloud_gate": True,
        "cost_review_acknowledged": True,
    }


def bound_manifests():
    prefix = (
        "us-central1-docker.pkg.dev/microservices-demo-tcc/"
        "online-boutique-experiment"
    )
    binding = publication_binding()
    pdt = load(PDT_MANIFEST_PATH)
    pdt["controller_image"] = (
        f"{prefix}/checkout-pdt-controller@sha256:" + "d" * 64
    )
    pdt["publication_binding"] = copy.deepcopy(binding)
    oracle = load(ORACLE_MANIFEST_PATH)
    oracle["images"] = {
        "oracle_harness": f"{prefix}/oracle-harness@sha256:" + "e" * 64,
        "currency_reference": f"{prefix}/currency-reference@sha256:" + "f" * 64,
    }
    oracle["publication_binding"] = copy.deepcopy(binding)
    return pdt, oracle


class PrepareProtocolFreezeCandidateTests(unittest.TestCase):
    def test_prepares_one_coherent_non_authorizing_bundle(self):
        protocol = load(PROTOCOL_PATH)
        pdt, oracle = bound_manifests()
        before_protocol = copy.deepcopy(protocol)
        before_pdt = copy.deepcopy(pdt)
        before_oracle = copy.deepcopy(oracle)

        rendered, receipt = MODULE.prepare(
            REPO_ROOT, protocol, pdt, oracle, FROZEN_AT
        )
        values = {
            path: json.loads(content.decode()) for path, content in rendered.items()
        }

        self.assertEqual(8, len(values))
        for relative in MODULE.POLICY_INPUTS:
            self.assertEqual("frozen", values[relative]["status"])
            self.assertEqual(FROZEN_AT, values[relative]["frozen_at"])
        self.assertEqual("frozen", values[MODULE.PDT_RUNTIME_PATH]["status"])
        self.assertEqual("frozen", values[MODULE.ORACLE_SUITE_PATH]["status"])
        candidate = values[MODULE.PROTOCOL_PATH]
        self.assertEqual("pre-registration-candidate", candidate["status"])
        self.assertIsNone(candidate["frozen_at"])
        self.assertFalse(candidate["confirmatory_collection_allowed"])

        proposed_hashes = {
            path: MODULE.sha256_bytes(content) for path, content in rendered.items()
        }
        self.assertEqual(
            proposed_hashes["experiment/pdt/model-policy.json"],
            next(
                item["sha256"]
                for item in values[MODULE.PDT_RUNTIME_PATH]["files"]
                if item["path"] == "experiment/pdt/model-policy.json"
            ),
        )
        for path in (
            "experiment/pdt/fidelity-policy.json",
            "experiment/oracle/policy-v1.json",
        ):
            self.assertEqual(
                proposed_hashes[path],
                next(
                    item["sha256"]
                    for item in values[MODULE.ORACLE_SUITE_PATH]["files"]
                    if item["path"] == path
                ),
            )
        self.assertEqual(
            proposed_hashes[MODULE.PDT_RUNTIME_PATH],
            candidate["frozen_inputs"]["pdt_runtime_manifest"]["sha256"],
        )
        self.assertEqual(
            proposed_hashes[MODULE.ORACLE_SUITE_PATH],
            candidate["frozen_inputs"]["oracle_suite_manifest"]["sha256"],
        )
        self.assertEqual(
            proposed_hashes[MODULE.PROTOCOL_PATH],
            receipt["candidate_protocol_sha256"],
        )
        self.assertEqual(
            publication_binding(), receipt["publication_binding"]
        )
        self.assertFalse(receipt["cloud_execution_authorized"])
        self.assertFalse(receipt["cloud_mutation_performed"])
        self.assertFalse(receipt["active_repository_files_modified"])
        self.assertEqual(before_protocol, protocol)
        self.assertEqual(before_pdt, pdt)
        self.assertEqual(before_oracle, oracle)

    def test_rejects_mismatched_publication_provenance(self):
        pdt, oracle = bound_manifests()
        oracle["publication_binding"]["workflow_run_id"] = "9999"

        with self.assertRaisesRegex(ValueError, "one valid publication"):
            MODULE.prepare(
                REPO_ROOT, load(PROTOCOL_PATH), pdt, oracle, FROZEN_AT
            )

    def test_rejects_extra_changes_hidden_in_bound_manifest(self):
        pdt, oracle = bound_manifests()
        pdt["freeze_rule"] = "silently changed"

        with self.assertRaisesRegex(ValueError, "more than publication fields"):
            MODULE.prepare(
                REPO_ROOT, load(PROTOCOL_PATH), pdt, oracle, FROZEN_AT
            )

    def test_rejects_protocol_hash_drift_and_invalid_timestamp(self):
        pdt, oracle = bound_manifests()
        protocol = load(PROTOCOL_PATH)
        protocol["frozen_inputs"]["ci_policy"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "hash differs"):
            MODULE.prepare(REPO_ROOT, protocol, pdt, oracle, FROZEN_AT)

        with self.assertRaisesRegex(ValueError, "RFC3339"):
            MODULE.prepare(
                REPO_ROOT, load(PROTOCOL_PATH), pdt, oracle, "tomorrow"
            )

        with self.assertRaisesRegex(ValueError, "cannot precede"):
            MODULE.prepare(
                REPO_ROOT,
                load(PROTOCOL_PATH),
                pdt,
                oracle,
                "2026-09-22T01:59:59Z",
            )


if __name__ == "__main__":
    unittest.main()
