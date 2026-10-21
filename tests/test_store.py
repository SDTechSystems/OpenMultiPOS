import copy
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from open_multi_pos.demo.store import ConflictError, DemoStore


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = DemoStore(Path(self.tmp.name) / "test.sqlite3")
        self.payload = {
            "brand": "atelier",
            "terminal": str(uuid4()),
            "transaction_id": str(uuid4()),
            "items": [{"sku": "VEL-01", "qty": 1}],
            "cash": "30000",
            "transfer": "0",
        }

    def test_sale_exact_amount_mixed_tender_and_warehouse_stock(self):
        self.payload.update(cash="10000", transfer="18000")
        before_tech = self.store.catalog("owner", "tech")
        receipt = self.store.checkout("cashier", self.payload)["receipt"]
        self.assertEqual(receipt["total"], 2800000)
        self.assertEqual(receipt["change"], 0)
        self.assertEqual(sum(p["amount"] for p in receipt["payments"]), receipt["total"])
        self.assertEqual(self.store.catalog("cashier", "atelier")[-2]["sku"], "VEL-01")
        candle = next(p for p in self.store.catalog("owner", "atelier") if p["sku"] == "VEL-01")
        self.assertEqual(candle["stock"], 14)
        self.assertEqual(before_tech, self.store.catalog("owner", "tech"))
        self.assertEqual(receipt["fiscal_status"], "not_configured")

    def test_retry_returns_original_without_second_stock_change(self):
        first = self.store.checkout("cashier", self.payload)
        second = self.store.checkout("cashier", self.payload)
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["receipt"], second["receipt"])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM sales").fetchone()[0], 1)
            self.assertEqual(
                db.execute("SELECT stock FROM products WHERE sku='VEL-01'").fetchone()[0], 14
            )

    def test_concurrent_retries_commit_only_once(self):
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(
                executor.map(lambda _: self.store.checkout("cashier", self.payload), range(5))
            )
        self.assertEqual(sum(not result["duplicate"] for result in results), 1)
        self.assertEqual(len({r["receipt"]["id"] for r in results}), 1)

    def test_same_key_different_payload_is_rejected(self):
        self.store.checkout("cashier", self.payload)
        self.payload["cash"] = "40000"
        with self.assertRaises(ConflictError):
            self.store.checkout("cashier", self.payload)

    def test_cross_brand_catalog_and_transaction_rejected(self):
        with self.assertRaises(PermissionError):
            self.store.catalog("cashier", "tech")
        self.payload["brand"] = "tech"
        with self.assertRaises(PermissionError):
            self.store.checkout("cashier", self.payload)

    def test_cross_brand_receipt_rejected(self):
        self.payload.update(brand="tech", items=[{"sku": "MOU-01", "qty": 1}], cash="45000")
        receipt = self.store.checkout("owner", self.payload)["receipt"]
        with self.assertRaises(PermissionError):
            self.store.receipt("cashier", receipt["id"])

    def test_product_substitution_is_rejected(self):
        self.payload["items"] = [{"sku": "MOU-01", "qty": 1}]
        with self.assertRaisesRegex(ValueError, "no pertenece"):
            self.store.checkout("cashier", self.payload)

    def test_forged_client_price_is_ignored(self):
        self.payload["items"][0]["price"] = 1
        self.assertEqual(self.store.checkout("cashier", self.payload)["receipt"]["total"], 2800000)

    def test_insufficient_payment_rolls_back(self):
        self.payload["cash"] = "1"
        with self.assertRaises(ValueError):
            self.store.checkout("cashier", self.payload)
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM sales").fetchone()[0], 0)
            self.assertEqual(
                db.execute("SELECT stock FROM products WHERE sku='VEL-01'").fetchone()[0], 15
            )

    def test_stock_conflict_does_not_partially_decrement(self):
        self.payload["items"] = [{"sku": "JAB-01", "qty": 1}, {"sku": "VEL-01", "qty": 16}]
        self.payload["cash"] = "999999"
        before = self.store.catalog("cashier", "atelier")
        with self.assertRaises(ConflictError):
            self.store.checkout("cashier", self.payload)
        self.assertEqual(before, self.store.catalog("cashier", "atelier"))

    def test_two_sales_for_last_unit_have_one_winner(self):
        with self.store.connect() as db:
            db.execute("UPDATE products SET stock=1 WHERE sku='VEL-01'")
        other = copy.deepcopy(self.payload)
        other["transaction_id"] = str(uuid4())

        def checkout(payload):
            try:
                return self.store.checkout("cashier", payload)
            except ConflictError:
                return None

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(checkout, [self.payload, other]))
        self.assertEqual(sum(r is not None for r in results), 1)

    def test_invalid_quantities_and_duplicate_lines(self):
        for qty in (0, -1, True, 1.1, "2", 1000):
            with self.subTest(qty=qty), self.assertRaises(ValueError):
                self.payload["items"] = [{"sku": "VEL-01", "qty": qty}]
                self.store.checkout("cashier", self.payload)
        self.payload["items"] = [{"sku": "VEL-01", "qty": 1}] * 2
        with self.assertRaises(ValueError):
            self.store.checkout("cashier", self.payload)

    def test_historical_brand_snapshot_survives_configuration_change_and_restart(self):
        original = self.store.checkout("owner", self.payload)["receipt"]
        with self.store.connect() as db:
            db.execute(
                "UPDATE brands SET data=? WHERE id='atelier'", (json.dumps({"name": "Cambio"}),)
            )
        restarted = DemoStore(self.store.path)
        self.assertEqual(restarted.receipt("owner", original["id"]), original)
        self.assertEqual(restarted.checkout("owner", self.payload)["receipt"], original)
