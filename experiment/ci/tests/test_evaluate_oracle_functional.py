import copy
import hashlib
import importlib.util
import json
import pathlib
import unittest
import tempfile


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "experiment" / "scripts" / "evaluate-oracle-functional.py"
POLICY_PATH = REPO_ROOT / "experiment" / "oracle" / "policy-v1.json"
SPEC = importlib.util.spec_from_file_location("evaluate_oracle_functional", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def policy():
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def money(currency, units, nanos=0):
    return {"currency_code": currency, "units": units, "nanos": nanos}


def result(expected_case, suffix, currency="USD", item_count=1, quantity=1):
    items = [
        {"product_id": f"sku-{index + 1}", "quantity": quantity}
        for index in range(item_count)
    ]
    conversions = [
        {
            "from": money("USD", index + 1),
            "to": currency,
            "actual": money(currency, index + 1),
            "reference": money(currency, index + 1),
        }
        for index in range(item_count)
    ]
    conversions.append(
        {
            "from": money("USD", 1),
            "to": currency,
            "actual": money(currency, 1),
            "reference": money(currency, 1),
        }
    )
    total_units = sum((index + 1) * quantity for index in range(item_count)) + 1
    value = {
        "schema_version": "1.0.0",
        "user_id": f"oracle-{suffix}",
        "expected_case": expected_case,
        "input": {
            "user_id": f"oracle-{suffix}",
            "currency": currency,
            "items": items,
            "fault": "",
            "card_case": "valid",
            "timeout_ms": 30000,
            "expected_case": expected_case,
        },
        "grpc_code": "OK",
        "response": {"order": {"orderId": f"order-{suffix}"}},
        "events": [
            {"sequence": 1, "name": "charge-attempt"},
            {"sequence": 2, "name": "charge-success"},
            {"sequence": 3, "name": "ship-attempt"},
            {"sequence": 4, "name": "ship-success"},
            {"sequence": 5, "name": "cart-clear"},
            {"sequence": 6, "name": "confirmation"},
        ],
        "charges": [money(currency, total_units)],
        "conversions": conversions,
        "cart_cleared": True,
        "remaining_cart_items": 0,
    }
    return value


def suite():
    value = policy()
    results = []
    sequence = 0
    for currency in value["input_matrix"]["currencies"]:
        for item_count in value["input_matrix"]["cart_item_counts"]:
            for quantity in value["input_matrix"]["quantities"]:
                sequence += 1
                results.append(
                    result("success", sequence, currency, item_count, quantity)
                )

    payment = result("payment-failure", "payment")
    payment.update(
        {
            "grpc_code": "Internal",
            "response": None,
            "events": [
                {"sequence": 1, "name": "charge-attempt"},
                {"sequence": 2, "name": "charge-error"},
            ],
            "cart_cleared": False,
            "remaining_cart_items": 1,
        }
    )
    payment["input"]["fault"] = "payment-unavailable"
    results.append(payment)

    shipping = result("shipping-failure", "shipping")
    shipping.update(
        {
            "grpc_code": "Unavailable",
            "response": None,
            "events": [
                {"sequence": 1, "name": "charge-attempt"},
                {"sequence": 2, "name": "charge-success"},
                {"sequence": 3, "name": "ship-attempt"},
                {"sequence": 4, "name": "ship-error"},
            ],
            "cart_cleared": False,
            "remaining_cart_items": 1,
        }
    )
    shipping["input"]["fault"] = "shipping-unavailable"
    results.append(shipping)

    for card_case in value["input_matrix"]["negative_cards"]:
        negative = result(card_case, card_case)
        negative.update(
            {
                "grpc_code": "Internal",
                "response": None,
                "events": [
                    {"sequence": 1, "name": "charge-attempt"},
                    {"sequence": 2, "name": "charge-error"},
                ],
                "cart_cleared": False,
                "remaining_cart_items": 1,
            }
        )
        negative["input"]["card_case"] = card_case
        negative["charges"] = [money("USD", 2)]
        results.append(negative)
    return results


class EvaluateOracleFunctionalTests(unittest.TestCase):
    def test_complete_safe_suite_passes_every_assertion(self):
        report = MODULE.evaluate(policy(), suite())

        self.assertTrue(report["valid"])
        self.assertEqual(report["success_matrix_case_count"], 30)
        self.assertTrue(all(item["passed"] for item in report["functional_assertions"]))

    def test_undercharge_is_detected_without_using_operator_label(self):
        values = suite()
        candidate = next(item for item in values if item["expected_case"] == "success")
        candidate["charges"][0]["units"] -= 1

        report = MODULE.evaluate(policy(), values)
        assertions = {item["id"]: item["passed"] for item in report["functional_assertions"]}

        self.assertTrue(report["valid"])
        self.assertFalse(assertions["charged-total-equals-independent-total"])

    def test_currency_difference_is_detected_independently(self):
        values = suite()
        candidate = next(item for item in values if item["expected_case"] == "success")
        candidate["conversions"][0]["actual"]["nanos"] = 1

        report = MODULE.evaluate(policy(), values)
        assertions = {item["id"]: item["passed"] for item in report["functional_assertions"]}

        self.assertFalse(assertions["currency-rounding-matches-independent-calculation"])

    def test_missing_matrix_cell_invalidates_the_suite(self):
        values = suite()[1:]

        report = MODULE.evaluate(policy(), values)

        self.assertFalse(report["valid"])
        self.assertIn("success-input-matrix-incomplete", report["invalid_reasons"])

    def test_input_is_not_mutated(self):
        values = suite()
        before = copy.deepcopy(values)

        MODULE.evaluate(policy(), values)

        self.assertEqual(values, before)

    def test_manifest_binding_detects_result_substitution(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = pathlib.Path(temporary_directory)
            result_path = root / "case.json"
            result_path.write_text(json.dumps(result("success", "one")), encoding="utf-8")
            digest = hashlib.sha256(result_path.read_bytes()).hexdigest()
            manifest = {"case_count": 1, "cases": [{"path": "case.json", "sha256": digest}]}

            MODULE.verify_manifest(manifest, [result_path])
            result_path.write_text("{}", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "differ from the sealed manifest"):
                MODULE.verify_manifest(manifest, [result_path])


if __name__ == "__main__":
    unittest.main()
