import importlib.util
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "select-affected-components.py"
MATRIX_PATH = REPO_ROOT / "experiment" / "ci" / "components.json"

SPEC = importlib.util.spec_from_file_location("select_affected_components", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class SelectAffectedComponentsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = MODULE.load_matrix(MATRIX_PATH)

    def select(self, *paths):
        return MODULE.select_components(self.matrix, paths, "unit-test")

    def test_checkout_change_uses_implemented_adapter(self):
        result = self.select("src/checkoutservice/main.go")

        self.assertEqual(result["decision"], "pass")
        self.assertEqual(
            [component["name"] for component in result["affected_components"]],
            ["checkoutservice"],
        )
        self.assertEqual(result["incomplete_validation_components"], [])

    def test_new_service_without_adapter_blocks_fail_closed(self):
        result = self.select("src/newservice/main.go")

        self.assertEqual(result["decision"], "block")
        self.assertEqual(result["incomplete_validation_components"], [])
        self.assertEqual(result["unknown_critical_paths"], ["src/newservice/main.go"])

    def test_node_dependency_with_adapter_passes(self):
        result = self.select("src/paymentservice/charge.js")

        self.assertEqual(result["decision"], "pass")
        self.assertEqual(result["incomplete_validation_components"], [])
        self.assertEqual(
            [component["validation_profile"] for component in result["affected_components"]],
            ["node-service"],
        )

    def test_shared_proto_selects_every_checkout_path_service(self):
        result = self.select("protos/demo.proto")

        names = [component["name"] for component in result["affected_components"]]
        self.assertEqual(
            names,
            [
                "cartservice",
                "checkoutservice",
                "currencyservice",
                "emailservice",
                "frontend",
                "paymentservice",
                "productcatalogservice",
                "protocol-contracts",
                "recommendationservice",
                "shippingservice",
            ],
        )
        self.assertEqual(result["decision"], "pass")
        self.assertEqual(result["incomplete_validation_components"], [])

    def test_infrastructure_change_passes_and_documentation_is_ignored(self):
        result = self.select("infra/kustomize/staging/kustomization.yaml", "docs/tcc.md")

        self.assertEqual(result["decision"], "pass")
        self.assertEqual(result["ignored_files"], ["docs/tcc.md"])
        self.assertEqual(
            [component["name"] for component in result["affected_components"]],
            ["infrastructure"],
        )

    def test_email_dependency_with_adapter_passes(self):
        result = self.select("src/emailservice/email_server.py")

        self.assertEqual(result["decision"], "pass")
        self.assertEqual(result["incomplete_validation_components"], [])

    def test_outside_twin_control_has_an_implemented_adapter(self):
        result = self.select("src/recommendationservice/recommendation_server.py")

        self.assertEqual(result["decision"], "pass")
        self.assertEqual(
            [component["name"] for component in result["affected_components"]],
            ["recommendationservice"],
        )

    def test_candidate_definition_always_binds_checkout_artifact(self):
        result = self.select("experiment/pdt/candidates/cand-opaque.json")

        self.assertEqual(result["decision"], "pass")
        self.assertEqual(
            [component["name"] for component in result["affected_components"]],
            ["checkoutservice", "experiment-control"],
        )

    def test_only_documentation_is_not_a_release_candidate(self):
        result = self.select("README.md", "docs/tcc.md")

        self.assertEqual(result["decision"], "block")
        self.assertTrue(
            any("no release-relevant component changes" in reason for reason in result["reasons"])
        )

    def test_changed_file_hash_is_order_independent(self):
        first = self.select("src/checkoutservice/main.go", "README.md")
        second = self.select("README.md", "src/checkoutservice/main.go")

        self.assertEqual(first["changed_files_sha256"], second["changed_files_sha256"])

    def test_parent_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            self.select("../outside")


if __name__ == "__main__":
    unittest.main()
