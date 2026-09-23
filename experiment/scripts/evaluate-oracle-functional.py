#!/usr/bin/env python3

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import sys


NANOS_PER_UNIT = 1_000_000_000


def load(path):
    with pathlib.Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def sha256_file(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(manifest, result_paths):
    expected = {item["path"]: item["sha256"] for item in manifest.get("cases", [])}
    observed = {pathlib.Path(path).name: sha256_file(path) for path in result_paths}
    if len(expected) != manifest.get("case_count") or len(expected) != len(
        manifest.get("cases", [])
    ):
        raise ValueError("functional manifest case count is inconsistent")
    if observed != expected:
        raise ValueError("functional results differ from the sealed manifest")


def money_value(value):
    return int(value["units"]) * NANOS_PER_UNIT + int(value["nanos"])


def event_names(result):
    return [item.get("name") for item in result.get("events", [])]


def first_index(values, name):
    try:
        return values.index(name)
    except ValueError:
        return None


def expected_charge(result):
    items = result["input"]["items"]
    conversions = result.get("conversions", [])
    if len(conversions) != len(items) + 1:
        raise ValueError("conversion count does not cover every item plus shipping")
    currency = result["input"]["currency"]
    total = 0
    for item, conversion in zip(items, conversions[:-1]):
        reference = conversion["reference"]
        if reference["currency_code"] != currency:
            raise ValueError("reference product conversion uses the wrong currency")
        total += money_value(reference) * int(item["quantity"])
    shipping = conversions[-1]["reference"]
    if shipping["currency_code"] != currency:
        raise ValueError("reference shipping conversion uses the wrong currency")
    return currency, total + money_value(shipping)


def exact_charge_passed(result):
    if len(result.get("charges", [])) != 1:
        return False
    try:
        currency, expected = expected_charge(result)
    except (KeyError, TypeError, ValueError):
        return False
    actual = result["charges"][0]
    return actual.get("currency_code") == currency and money_value(actual) == expected


def matrix_requirements(policy):
    matrix = policy["input_matrix"]
    return {
        (currency, item_count, quantity)
        for currency in matrix["currencies"]
        for item_count in matrix["cart_item_counts"]
        for quantity in matrix["quantities"]
    }


def observed_matrix(results):
    observed = set()
    for result in results:
        if result.get("expected_case") != "success":
            continue
        input_value = result.get("input", {})
        items = input_value.get("items", [])
        quantities = {item.get("quantity") for item in items}
        if len(quantities) == 1:
            observed.add(
                (input_value.get("currency"), len(items), next(iter(quantities)))
            )
    return observed


def evaluate(policy, results):
    invalid_reasons = []
    user_ids = [item.get("user_id") for item in results]
    if not results:
        invalid_reasons.append("no-functional-results")
    if len(user_ids) != len(set(user_ids)) or any(not value for value in user_ids):
        invalid_reasons.append("functional-user-ids-missing-or-duplicated")
    if any(item.get("schema_version") != "1.0.0" for item in results):
        invalid_reasons.append("functional-result-schema-mismatch")

    required_matrix = matrix_requirements(policy)
    missing_matrix = sorted(required_matrix - observed_matrix(results))
    if missing_matrix:
        invalid_reasons.append("success-input-matrix-incomplete")

    success = [item for item in results if item.get("expected_case") == "success"]
    payment_failures = [
        item for item in results if item.get("expected_case") == "payment-failure"
    ]
    shipping_failures = [
        item for item in results if item.get("expected_case") == "shipping-failure"
    ]
    negative_cases = {
        card_case: [
            item for item in results if item.get("expected_case") == card_case
        ]
        for card_case in policy["input_matrix"]["negative_cards"]
    }
    if len(payment_failures) != 1:
        invalid_reasons.append("payment-failure-case-count-invalid")
    if len(shipping_failures) != 1:
        invalid_reasons.append("shipping-failure-case-count-invalid")
    for card_case, values in negative_cases.items():
        if len(values) != 1:
            invalid_reasons.append(f"negative-card-case-count-invalid:{card_case}")

    success_has_one_order = all(
        item.get("grpc_code") == "OK"
        and bool(item.get("response", {}).get("order", {}).get("orderId"))
        for item in success
    ) and bool(success)
    exact_charges = all(exact_charge_passed(item) for item in success) and bool(success)
    exactly_one_charge = all(
        event_names(item).count("charge-success") == 1
        and len(item.get("charges", [])) == 1
        for item in success
    ) and bool(success)

    ordered_effects = True
    for item in success:
        names = event_names(item)
        indexes = [
            first_index(names, name)
            for name in ("charge-success", "ship-success", "cart-clear", "confirmation")
        ]
        if any(index is None for index in indexes) or indexes != sorted(indexes):
            ordered_effects = False
            break
    ordered_effects = ordered_effects and bool(success)

    payment_failure_safe = len(payment_failures) == 1
    if payment_failure_safe:
        item = payment_failures[0]
        names = event_names(item)
        payment_failure_safe = (
            item.get("grpc_code") != "OK"
            and "charge-error" in names
            and "ship-attempt" not in names
            and "confirmation" not in names
            and "cart-clear" not in names
            and item.get("cart_cleared") is False
            and item.get("remaining_cart_items", 0) > 0
            and item.get("response") is None
        )

    shipping_failure_safe = len(shipping_failures) == 1
    if shipping_failure_safe:
        item = shipping_failures[0]
        names = event_names(item)
        shipping_failure_safe = (
            item.get("grpc_code") != "OK"
            and "charge-success" in names
            and "ship-error" in names
            and "confirmation" not in names
            and "cart-clear" not in names
            and item.get("cart_cleared") is False
            and item.get("remaining_cart_items", 0) > 0
            and item.get("response") is None
        )

    invalid_card_safe = all(len(values) == 1 for values in negative_cases.values())
    if invalid_card_safe:
        for values in negative_cases.values():
            item = values[0]
            names = event_names(item)
            if not (
                item.get("grpc_code") != "OK"
                and "charge-error" in names
                and "charge-success" not in names
                and "ship-attempt" not in names
                and "confirmation" not in names
                and "cart-clear" not in names
                and item.get("cart_cleared") is False
                and item.get("remaining_cart_items", 0) > 0
                and item.get("response") is None
            ):
                invalid_card_safe = False
                break

    successful_order_clears_cart = all(
        item.get("cart_cleared") is True
        and item.get("remaining_cart_items") == 0
        and "cart-clear" in event_names(item)
        for item in success
    ) and bool(success)

    currency_rounding_matches = all(
        bool(item.get("conversions"))
        and all(
            conversion.get("actual") == conversion.get("reference")
            for conversion in item["conversions"]
        )
        for item in success
    ) and bool(success)

    observed = {
        "checkout-success-produces-one-order": success_has_one_order,
        "charged-total-equals-independent-total": exact_charges,
        "exactly-one-charge-per-order": exactly_one_charge,
        "charge-precedes-shipping-and-confirmation": ordered_effects,
        "payment-failure-prevents-shipping-confirmation-and-cart-clear": payment_failure_safe,
        "shipping-failure-prevents-confirmation-and-cart-clear": shipping_failure_safe,
        "invalid-card-prevents-order-and-retains-cart": invalid_card_safe,
        "successful-order-clears-cart": successful_order_clears_cart,
        "currency-rounding-matches-independent-calculation": currency_rounding_matches,
    }
    required_assertions = set(policy["functional_assertions"])
    if set(observed) != required_assertions:
        invalid_reasons.append("functional-policy-assertion-set-mismatch")

    return {
        "schema_version": "1.0.0",
        "policy_id": policy["policy_id"],
        "valid": not invalid_reasons,
        "invalid_reasons": sorted(set(invalid_reasons)),
        "case_count": len(results),
        "success_matrix_case_count": len(success),
        "functional_assertions": [
            {"id": assertion_id, "passed": observed[assertion_id]}
            for assertion_id in policy["functional_assertions"]
        ],
    }


def write_json_exclusive(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
    except Exception:
        path.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=pathlib.Path, required=True)
    parser.add_argument("--manifest", type=pathlib.Path)
    parser.add_argument("--result", type=pathlib.Path, action="append", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        report = evaluate(load(args.policy), [load(path) for path in args.result])
        report["evidence_binding_verified"] = False
        if args.manifest:
            manifest = load(args.manifest)
            verify_manifest(manifest, args.result)
            for field in ("candidate_id", "alternative_id", "repetition"):
                report[field] = manifest[field]
            report["evidence_binding_verified"] = True
        report["generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
        write_json_exclusive(args.output, report)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"oracle functional evaluation failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(args.output)


if __name__ == "__main__":
    main()
