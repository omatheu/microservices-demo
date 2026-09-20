import importlib.util
import json
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "run-oracle-functional-suite.py"
POLICY_PATH = REPO_ROOT / "experiment" / "oracle" / "policy-v1.json"
SPEC = importlib.util.spec_from_file_location("run_oracle_functional_suite", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class RunOracleFunctionalSuiteTests(unittest.TestCase):
    def test_cases_cover_the_full_matrix_and_negative_paths(self):
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        cases = MODULE.build_cases(policy, "cand-opaque", "deploy-as-is", 1)

        self.assertEqual(len(cases), 35)
        requests = [item["request"] for item in cases]
        success = [item for item in requests if item["expected_case"] == "success"]
        observed = {
            (
                item["currency"],
                len(item["items"]),
                next(iter({cart_item["quantity"] for cart_item in item["items"]})),
            )
            for item in success
        }
        expected = {
            (currency, item_count, quantity)
            for currency in policy["input_matrix"]["currencies"]
            for item_count in policy["input_matrix"]["cart_item_counts"]
            for quantity in policy["input_matrix"]["quantities"]
        }
        self.assertEqual(observed, expected)
        self.assertEqual(
            {item["expected_case"] for item in requests if item["expected_case"] != "success"},
            {
                "unsupported-card",
                "expired-card",
                "invalid-number",
                "payment-failure",
                "shipping-failure",
            },
        )
        self.assertEqual(len({item["user_id"] for item in requests}), 35)

    def test_endpoint_must_be_localhost(self):
        for endpoint in ("https://example.com", "http://10.0.0.1:8080"):
            with self.subTest(endpoint=endpoint):
                with self.assertRaisesRegex(ValueError, "localhost"):
                    MODULE.validate_endpoint(endpoint)


if __name__ == "__main__":
    unittest.main()
