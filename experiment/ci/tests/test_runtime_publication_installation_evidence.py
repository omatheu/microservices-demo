import hashlib
import json
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
RECEIPT_PATH = (
    REPO_ROOT
    / "experiment"
    / "evidence"
    / "finance"
    / "runtime-publication-controls-installation-20260922T033857Z.json"
)


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RuntimePublicationInstallationEvidenceTests(unittest.TestCase):
    def test_receipt_binds_safe_installation_and_post_install_readiness(self):
        receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))

        terraform = receipt["terraform"]
        self.assertEqual(
            {"add": 3, "change": 0, "destroy": 0}, terraform["apply_summary"]
        )
        self.assertEqual(3, len(terraform["resources_created"]))
        self.assertTrue(terraform["post_apply_plan"]["no_changes"])
        self.assertEqual([], terraform["post_apply_plan"]["changed_addresses"])
        self.assertTrue(terraform["gcp_mutation_performed"])

        billing = receipt["billing_impact"]
        self.assertEqual(0, billing["billable_compute_storage_or_network_resources_added"])
        self.assertFalse(billing["image_storage_added"])
        self.assertFalse(receipt["artifact_publication_performed"])
        self.assertFalse(receipt["publication_authorized"])

        variables = receipt["github"]["financial_variables"]
        self.assertEqual("false", variables["TCC_COST_REVIEW_ACKNOWLEDGED"])
        self.assertEqual("false", variables["TCC_RUNTIME_PUBLICATION_ACKNOWLEDGED"])
        self.assertEqual([], receipt["github"]["authorization_labels_on_pull_request_1"])

        for binding in (terraform["plan_validation"], receipt["readiness"]):
            relative = pathlib.PurePosixPath(binding["path"])
            self.assertFalse(relative.is_absolute())
            self.assertNotIn("..", relative.parts)
            self.assertEqual(
                binding["sha256"], sha256_file(REPO_ROOT / relative)
            )

        readiness = receipt["readiness"]
        self.assertEqual(13, readiness["check_count"])
        self.assertEqual(12, readiness["passed_count"])
        self.assertEqual(
            ["workflow-installed-on-default-branch"],
            readiness["blocking_requirements"],
        )
        self.assertFalse(receipt["workflow_installed_on_main"])


if __name__ == "__main__":
    unittest.main()
