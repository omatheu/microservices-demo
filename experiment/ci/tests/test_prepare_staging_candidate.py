import importlib.util
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "prepare-staging-candidate.py"

SPEC = importlib.util.spec_from_file_location("prepare_staging_candidate", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


DIGEST = "sha256:" + "a" * 64


def decision(with_service=True):
    components = ["checkoutservice"] if with_service else []
    artifacts = (
        [
            {
                "component": "checkoutservice",
                "source_image_name": "us-central1-docker.pkg.dev/online-boutique-ci/microservices-demo/checkoutservice",
                "build_status": "pass",
                "sbom_status": "pass",
                "image_scan_status": "pass",
                "publication_status": "pass",
                "remote_reference": (
                    "us-central1-docker.pkg.dev/example/project/checkoutservice@" + DIGEST
                ),
                "manifest_digest": DIGEST,
            }
        ]
        if with_service
        else []
    )
    return {
        "candidate_id": "opaque-1",
        "scope": "local-pre-staging-ci",
        "local_decision": "pass",
        "eligible_for_staging": True,
        "confirmatory_eligible": True,
        "git": {"commit": "abc", "dirty": False},
        "run_id": "ci-1",
        "component_selection": {"affected_service_components": components},
        "artifacts": artifacts,
    }


class PrepareStagingCandidateTests(unittest.TestCase):
    def prepare(self, local_ci, mode="engineering"):
        return MODULE.prepare(
            local_ci,
            "opaque-1",
            REPO_ROOT / "infra" / "kustomize" / "staging",
            mode,
            "f" * 64,
        )

    def test_binds_service_to_digest(self):
        overlay, binding = self.prepare(decision())

        self.assertEqual(
            overlay["images"][0]["name"],
            "us-central1-docker.pkg.dev/online-boutique-ci/microservices-demo/checkoutservice",
        )
        self.assertEqual(overlay["images"][0]["digest"], DIGEST)
        self.assertEqual(binding["decision"], "bound")

    def test_infrastructure_only_candidate_needs_no_image(self):
        overlay, binding = self.prepare(decision(with_service=False))

        self.assertEqual(overlay["images"], [])
        self.assertEqual(binding["artifacts"], [])

    def test_unpublished_service_is_blocked(self):
        local_ci = decision()
        local_ci["artifacts"][0]["publication_status"] = "not-requested"

        with self.assertRaisesRegex(ValueError, "was not published"):
            self.prepare(local_ci)

    def test_missing_service_artifact_is_blocked(self):
        local_ci = decision()
        local_ci["artifacts"] = []

        with self.assertRaisesRegex(ValueError, "artifact set differs"):
            self.prepare(local_ci)

    def test_candidate_mismatch_is_blocked(self):
        local_ci = decision()
        local_ci["candidate_id"] = "different"

        with self.assertRaisesRegex(ValueError, "candidate IDs differ"):
            self.prepare(local_ci)

    def test_confirmatory_mode_requires_confirmatory_local_ci(self):
        local_ci = decision()
        local_ci["confirmatory_eligible"] = False

        with self.assertRaisesRegex(ValueError, "confirmatory-eligible"):
            self.prepare(local_ci, mode="confirmatory")


if __name__ == "__main__":
    unittest.main()
