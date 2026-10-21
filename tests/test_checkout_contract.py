import unittest
from decimal import Decimal
from uuid import uuid4

from open_multi_pos import checkout_contract as contract


class CheckoutContractTests(unittest.TestCase):
    def test_money_uses_decimal_and_rejects_ambiguous_or_nonfinite_values(self):
        self.assertEqual(contract.amount("0.10") + contract.amount("0.20"), Decimal("0.30"))
        for value in (1.5, True, "NaN", "Infinity", "1e2", "1,00", "1.001", "-1", "0"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                contract.amount(value)
        self.assertEqual(contract.amount("0.00", zero=True), 0)

    def test_only_canonical_uuid4_is_an_operation_id(self):
        value = str(uuid4())
        self.assertEqual(contract.request_uuid(value), value)
        for invalid in (
            value.upper(),
            value.replace("-", ""),
            "123",
            "00000000-0000-0000-0000-000000000000",
        ):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                contract.request_uuid(invalid)

    def test_items_reject_price_warehouse_and_nonpositive_or_boolean_quantity(self):
        self.assertEqual(contract.items([{"item_code": "ITEM", "qty": 1}])[0]["qty"], 1)
        for row in (
            {"item_code": "ITEM", "qty": True},
            {"item_code": "ITEM", "qty": -1},
            {"item_code": "ITEM", "qty": 1, "rate": 1},
            {"item_code": "ITEM", "qty": 1, "warehouse": "OTHER"},
        ):
            with self.subTest(row=row), self.assertRaises(ValueError):
                contract.items([row])

    def test_duplicate_items_and_payment_modes_are_rejected(self):
        with self.assertRaises(ValueError):
            contract.items([{"item_code": "ITEM", "qty": 1}] * 2)
        with self.assertRaises(ValueError):
            contract.payments([{"mode_of_payment": "Cash", "amount": "1"}] * 2)

    def test_equivalent_payment_order_and_decimal_format_have_same_hash(self):
        first = [
            {"mode_of_payment": "Cash", "amount": "1"},
            {"mode_of_payment": "Bank", "amount": "2.00"},
        ]
        second = [
            {"mode_of_payment": "Bank", "amount": "2"},
            {"mode_of_payment": "Cash", "amount": "1.00", "reference_no": ""},
        ]
        self.assertEqual(
            contract.digest(contract.payments(first)), contract.digest(contract.payments(second))
        )

    def test_operation_key_is_bound_to_terminal_and_transaction(self):
        first, second = str(uuid4()), str(uuid4())
        self.assertNotEqual(contract.operation_key("A", first), contract.operation_key("B", first))
        self.assertNotEqual(contract.operation_key("A", first), contract.operation_key("A", second))

    def test_unknown_fields_and_missing_required_fields_are_rejected(self):
        for value in ({"quote": "Q", "ignore_permissions": True}, {}, [], None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                contract.mapping(value, ("quote",))
