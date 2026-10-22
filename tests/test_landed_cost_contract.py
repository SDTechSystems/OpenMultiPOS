import copy
import unittest

from open_multi_pos.landed_cost_contract import selection


class LandedCostContractTests(unittest.TestCase):
    def data(self):
        return {
            "brand": "Negocio ficticio",
            "basis": "Amount",
            "receipts": [{"doctype": "Purchase Receipt", "name": "FAKE-PR-1"}],
            "charges": [
                {
                    "account": "Fletes ficticios",
                    "currency": "USD",
                    "amount": "10.50",
                    "exchange_rate": "4200.123456789",
                    "description": "Flete ficticio",
                }
            ],
        }

    def test_preserves_decimal_currency_and_explicit_rate(self):
        result = selection(self.data())
        self.assertEqual(result["charges"][0]["amount"], "10.50")
        self.assertEqual(result["charges"][0]["exchange_rate"], "4200.123456789")
        self.assertEqual(result["charges"][0]["currency"], "USD")

    def test_rejects_unsafe_rates_and_imprecise_amounts(self):
        for field, values in {
            "exchange_rate": ["0", "-1", "NaN", "Infinity", "1e3", "1.1234567890", 1, True, ""],
            "amount": ["0", "-1", "1.001", "1,20", 1.2, "NaN"],
            "description": [None, 123, "", "   "],
        }.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    data = self.data()
                    data["charges"][0][field] = value
                    selection(data)

    def test_rejects_duplicates_unknown_fields_and_document_types(self):
        data = self.data()
        invalid = []
        duplicate = copy.deepcopy(data)
        duplicate["receipts"] *= 2
        invalid.append(duplicate)
        extra = copy.deepcopy(data)
        extra["company"] = "Otra empresa"
        invalid.append(extra)
        wrong = copy.deepcopy(data)
        wrong["receipts"][0]["doctype"] = "Stock Entry"
        invalid.append(wrong)
        for value in invalid:
            with self.assertRaises(ValueError):
                selection(value)

    def test_bounds_and_basis(self):
        for field, value in [
            ("receipts", []),
            ("receipts", self.data()["receipts"] * 11),
            ("charges", []),
            ("charges", self.data()["charges"] * 21),
            ("basis", "Distribute Manually"),
        ]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                data = self.data()
                data[field] = value
                selection(data)
