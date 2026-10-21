"""Guided import integration with native documents and fictional disposable fixtures."""

import argparse
import csv
import importlib.util
import io
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import frappe

from open_multi_pos.import_contract import COLUMNS

spec = importlib.util.spec_from_file_location(
    "workspace_fixtures", Path(__file__).with_name("test-workspace-http.py")
)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


class ImportsHTTP(fixtures.WorkspaceHTTP):
    def csv(self, rows):
        output = io.StringIO(newline="")
        writer = csv.writer(output, delimiter=";")
        writer.writerow(COLUMNS)
        writer.writerows(rows)
        return output.getvalue()

    def rows(self):
        suffix = uuid4().hex[:9]
        return [
            [
                "crear",
                "",
                "Artículo ficticio A " + suffix,
                "OMP-FAKE-" + suffix,
                "Products",
                "2500.50",
                "2",
                "800.25",
            ],
            [
                "crear",
                "",
                "Artículo ficticio B " + suffix,
                "",
                "Products",
                "5000.00",
                "3",
                "1000.00",
            ],
        ]

    def prepare(self, rows, brand=None):
        brand = brand or self.businesses[0]
        data = {"brand": brand["brand"], "request_id": str(uuid4()), "csv_text": self.csv(rows)}
        result = self.result("imports.preview", {"data": data}, post=True)
        self.assertEqual(result["status"], "prepared", result)
        return data, result

    def apply_data(self, data, preview):
        return {
            "brand": data["brand"],
            "request_id": data["request_id"],
            "plan_hash": preview["plan_hash"],
            "confirm_repeat": 0,
        }

    def args(self, data):
        return {k: data[k] for k in ("brand", "request_id")}

    def test_01_preview_then_native_products_prices_stock_gl_and_sku(self):
        before = self.counts()
        item_count = frappe.db.count("Item")
        data, preview = self.prepare(self.rows())
        self.assertEqual(self.counts(), before)
        self.assertEqual(frappe.db.count("Item"), item_count)
        self.assertEqual(preview["plan"]["units"], 5)
        self.assertEqual(preview["plan"]["stock_value"], "4600.50")
        result = self.result("imports.apply", {"data": self.apply_data(data, preview)}, post=True)
        self.assertEqual(result["status"], "completed")
        frappe.db.rollback()
        self.assertEqual(frappe.db.count("Item"), item_count + 2)
        self.assertEqual(self.counts()["Stock Entry"], before["Stock Entry"] + 1)
        doc = frappe.get_doc("Stock Entry", result["result"]["stock_entry"])
        self.assertEqual(doc.docstatus, 1)
        self.assertEqual(doc.company, self.businesses[0]["company"])
        self.assertEqual(len(doc.items), 2)
        for row in result["result"]["items"]:
            item = frappe.get_doc("Item", row["item_code"])
            self.assertTrue(item.name.startswith(self.businesses[0]["sku_prefix"] + "-"))
            self.assertEqual(item.omp_business_brand, data["brand"])
            self.assertEqual(
                frappe.db.get_value(
                    "Bin",
                    {"item_code": item.name, "warehouse": self.businesses[0]["warehouse"]},
                    "actual_qty",
                ),
                row["qty"],
            )
        self.assertEqual(
            frappe.db.sql(
                "SELECT SUM(debit-credit) FROM `tabGL Entry` WHERE voucher_no=%s AND is_cancelled=0",
                doc.name,
            )[0][0],
            0,
        )
        self.assertEqual(
            frappe.db.sql(
                "SELECT SUM(actual_qty) FROM `tabStock Ledger Entry` WHERE voucher_no=%s AND is_cancelled=0",
                doc.name,
            )[0][0],
            5,
        )

    def test_02_update_price_barcode_stock_preserves_saved_sale(self):
        brand = self.businesses[0]
        code = self.product(brand)
        sale = self.result("checkout.checkout", {"data": self.sale(brand, code)}, post=True)
        snapshot = self.result(
            "receipt_preview.preview",
            {"brand": brand["brand"], "kind": "invoice", "document": sale["invoice"]},
        )["html"]
        barcode = "OMP-IMPORT-" + uuid4().hex[:10]
        data, preview = self.prepare(
            [
                [
                    "actualizar",
                    code,
                    "Nombre ficticio actualizado",
                    barcode,
                    "",
                    "3100.00",
                    "2",
                    "900.00",
                ]
            ]
        )
        self.result("imports.apply", {"data": self.apply_data(data, preview)}, post=True)
        frappe.db.rollback()
        item = frappe.get_doc("Item", code)
        self.assertEqual(item.item_name, "Nombre ficticio actualizado")
        self.assertIn(barcode, [r.barcode for r in item.barcodes])
        self.assertEqual(
            frappe.db.get_value("Item Price", {"item_code": code}, "price_list_rate"), 3100
        )
        self.assertEqual(
            frappe.db.get_value(
                "Bin", {"item_code": code, "warehouse": brand["warehouse"]}, "actual_qty"
            ),
            6,
        )
        self.assertEqual(
            self.result(
                "receipt_preview.preview",
                {"brand": brand["brand"], "kind": "invoice", "document": sale["invoice"]},
            )["html"],
            snapshot,
        )

    def test_03_row_errors_duplicate_barcode_wrong_owner_and_unknown_group(self):
        other = self.product(self.businesses[1], barcode="OMP-DUP-" + uuid4().hex[:8])
        frappe.db.rollback()
        barcode = frappe.get_doc("Item", other).barcodes[0].barcode
        rows = self.rows()
        rows[0][3] = barcode
        rows += [
            ["actualizar", other, "", "", "", "", "0", ""],
            ["crear", "", "Producto ficticio inválido", "", "NO-EXISTE-GRUPO", "1000", "0", ""],
        ]
        before = self.counts()
        item_count = frappe.db.count("Item")
        response = self.result(
            "imports.preview",
            {
                "data": {
                    "brand": self.businesses[0]["brand"],
                    "request_id": str(uuid4()),
                    "csv_text": self.csv(rows),
                }
            },
            post=True,
        )
        self.assertEqual(response["status"], "invalid")
        self.assertEqual([e["line"] for e in response["errors"]], [2, 4, 5])
        self.assertEqual(self.counts(), before)
        self.assertEqual(frappe.db.count("Item"), item_count)
        duplicate = self.rows()
        duplicate[1][3] = duplicate[0][3]
        result = self.result(
            "imports.preview",
            {
                "data": {
                    "brand": self.businesses[0]["brand"],
                    "request_id": str(uuid4()),
                    "csv_text": self.csv(duplicate),
                }
            },
            post=True,
        )
        self.assertEqual(result["status"], "invalid")

    def test_04_concurrent_apply_once_and_file_key_binding(self):
        data, preview = self.prepare(self.rows())
        apply = self.apply_data(data, preview)
        before = self.counts()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda _: self.request("imports.apply", {"data": apply}, post=True), range(2)
                )
            )
        self.assertTrue(all(r.status_code in (200, 409) for r in responses))
        result = self.result("imports.apply", {"data": apply}, post=True)
        self.assertTrue(result["duplicate"])
        self.assertEqual(
            self.request(
                "imports.apply", {"data": {**apply, "plan_hash": "wrong-preview"}}, post=True
            ).status_code,
            409,
        )
        self.assertEqual(self.counts()["Stock Entry"], before["Stock Entry"] + 1)
        self.assertEqual(
            self.result("imports.status", self.args(data), post=True)["result"], result["result"]
        )
        self.assertEqual(
            self.request(
                "imports.preview", {"data": {**data, "csv_text": self.csv(self.rows())}}, post=True
            ).status_code,
            409,
        )

    def test_05_stale_preview_requires_explicit_refresh(self):
        code = self.product()
        data, preview = self.prepare([["actualizar", code, "", "", "", "", "1", "800.00"]])
        frappe.db.rollback()
        price = frappe.db.get_value("Item Price", {"item_code": code}, "name")
        frappe.db.set_value("Item Price", price, "price_list_rate", 3500)
        frappe.db.commit()
        before = self.counts()
        self.assertEqual(
            self.request(
                "imports.apply", {"data": self.apply_data(data, preview)}, post=True
            ).status_code,
            409,
        )
        self.assertEqual(self.counts(), before)
        refreshed = self.result("imports.refresh", self.args(data), post=True)
        self.assertEqual(refreshed["plan"]["rows"][0]["precio"], "3500.00")
        self.assertNotEqual(preview["plan_hash"], refreshed["plan_hash"])
        self.assertEqual(
            self.request(
                "imports.apply", {"data": self.apply_data(data, preview)}, post=True
            ).status_code,
            409,
        )
        self.assertEqual(
            self.result("imports.apply", {"data": self.apply_data(data, refreshed)}, post=True)[
                "status"
            ],
            "completed",
        )

    def test_06_abandon_blocks_late_preview_and_apply(self):
        data = {
            "brand": self.businesses[0]["brand"],
            "request_id": str(uuid4()),
            "csv_text": self.csv(self.rows()),
        }
        self.assertEqual(
            self.result("imports.status", self.args(data), post=True)["status"], "not_found"
        )
        self.assertEqual(
            self.result("imports.abandon", self.args(data), post=True)["status"], "abandoned"
        )
        self.assertEqual(
            self.result("imports.preview", {"data": data}, post=True)["status"], "abandoned"
        )
        data, preview = self.prepare(self.rows())
        self.result("imports.abandon", self.args(data), post=True)
        self.assertEqual(
            self.result("imports.apply", {"data": self.apply_data(data, preview)}, post=True)[
                "status"
            ],
            "abandoned",
        )

    def test_07_identical_receipt_requires_new_reception_confirmation(self):
        code = self.product()
        rows = [["ingresar", code, "", "", "", "", "1", "800.00"]]
        first, plan = self.prepare(rows)
        self.result("imports.apply", {"data": self.apply_data(first, plan)}, post=True)
        data, preview = self.prepare(rows)
        self.assertEqual(preview["plan"]["previous_count"], 1)
        before = self.counts()
        self.assertEqual(
            self.request(
                "imports.apply", {"data": self.apply_data(data, preview)}, post=True
            ).status_code,
            409,
        )
        self.assertEqual(self.counts(), before)
        apply = {**self.apply_data(data, preview), "confirm_repeat": 1}
        self.assertEqual(
            self.result("imports.apply", {"data": apply}, post=True)["status"], "completed"
        )

    def test_08_native_posting_failure_rolls_back_catalog_and_stock(self):
        data, preview = self.prepare(self.rows())
        company = frappe.get_doc("Company", self.businesses[0]["company"])
        account = company.stock_adjustment_account
        old = frappe.db.get_value("Account", account, "disabled")
        before = self.counts()
        items = frappe.db.count("Item")
        frappe.db.set_value("Account", account, "disabled", 1)
        frappe.db.commit()
        frappe.clear_cache(doctype="Account")
        try:
            response = self.request(
                "imports.apply", {"data": self.apply_data(data, preview)}, post=True
            )
            self.assertEqual(response.status_code, 417, response.text[-1200:])
            self.assertEqual(self.counts(), before)
            self.assertEqual(frappe.db.count("Item"), items)
            self.assertEqual(
                self.result("imports.status", self.args(data), post=True)["status"], "prepared"
            )
        finally:
            frappe.db.set_value("Account", account, "disabled", old)
            frappe.db.commit()
            frappe.clear_cache(doctype="Account")
        self.assertEqual(
            self.result("imports.apply", {"data": self.apply_data(data, preview)}, post=True)[
                "status"
            ],
            "completed",
        )

    def test_09_permissions_methods_and_revoked_business(self):
        data, preview = self.prepare(self.rows())
        args = self.args(data)
        for method in ("imports.status", "imports.refresh", "imports.abandon"):
            self.assertIn(self.request(method, args, post=True, guest=True).status_code, (401, 403))
            self.assertEqual(self.request(method, args).status_code, 403)
        frappe.db.set_value("OMP Business Brand", data["brand"], "enabled", 0)
        frappe.db.commit()
        try:
            self.assertEqual(
                self.request(
                    "imports.apply", {"data": self.apply_data(data, preview)}, post=True
                ).status_code,
                403,
            )
        finally:
            frappe.db.set_value("OMP Business Brand", data["brand"], "enabled", 1)
            frappe.db.commit()
        user = frappe.get_doc("User", self.user)
        roles = [r.role for r in user.roles]
        user.set("roles", [{"role": "OMP Cashier"}])
        user.save()
        frappe.db.commit()
        frappe.clear_cache(user=self.user)
        try:
            self.assertEqual(
                self.request(
                    "imports.apply", {"data": self.apply_data(data, preview)}, post=True
                ).status_code,
                403,
            )
            self.assertEqual(self.request("imports.status", args, post=True).status_code, 403)
            self.assertEqual(
                self.request("imports.preview", {"data": data}, post=True).status_code, 403
            )
        finally:
            user = frappe.get_doc("User", self.user)
            user.set("roles", [{"role": role} for role in roles])
            user.save()
            frappe.db.commit()
            frappe.clear_cache(user=self.user)

    def test_10_cancelled_stock_entry_does_not_reimport(self):
        data, preview = self.prepare(self.rows())
        result = self.result("imports.apply", {"data": self.apply_data(data, preview)}, post=True)
        frappe.db.rollback()
        frappe.get_doc("Stock Entry", result["result"]["stock_entry"]).cancel()
        frappe.db.commit()
        before = self.counts()
        self.assertEqual(
            self.request(
                "imports.apply", {"data": self.apply_data(data, preview)}, post=True
            ).status_code,
            409,
        )
        self.assertEqual(self.counts(), before)

    def test_11_catalog_only_manual_sku_and_case_duplicate(self):
        sku = "00" + str(int(uuid4().hex[:8], 16))
        rows = [["crear", sku, "Producto ficticio " + sku, "", "Products", "1999.25", "0", ""]]
        before = self.counts()
        data, preview = self.prepare(rows)
        result = self.result("imports.apply", {"data": self.apply_data(data, preview)}, post=True)
        self.assertIsNone(result["result"]["stock_entry"])
        self.assertEqual(result["result"]["items"][0]["item_code"], sku)
        self.assertEqual(self.counts(), before)
        frappe.db.rollback()
        price = frappe.db.get_value("Item Price", {"item_code": sku}, "name")
        frappe.delete_doc("Item Price", price)
        frappe.db.commit()
        stock, stock_plan = self.prepare([["ingresar", sku, "", "", "", "", "1", "900.00"]])
        self.assertEqual(stock_plan["plan"]["rows"][0]["precio"], "")
        self.assertIsNotNone(
            self.result("imports.apply", {"data": self.apply_data(stock, stock_plan)}, post=True)[
                "result"
            ]["stock_entry"]
        )
        duplicate = self.rows()
        duplicate[0][1] = "OMP-CASE-" + uuid4().hex[:6]
        duplicate[1][1] = duplicate[0][1].lower()
        result = self.result(
            "imports.preview",
            {
                "data": {
                    "brand": data["brand"],
                    "request_id": str(uuid4()),
                    "csv_text": self.csv(duplicate),
                }
            },
            post=True,
        )
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["errors"][0]["line"], 3)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench", required=True, type=Path)
    parser.add_argument("--site", default="omp.localhost")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    fixtures.OPTIONS = parser.parse_args()
    fixtures.OPTIONS.bench = fixtures.OPTIONS.bench.expanduser().resolve()
    address = urlparse(fixtures.OPTIONS.base_url)
    if (
        address.scheme != "http"
        or address.hostname not in ("127.0.0.1", "localhost")
        or address.username
        or address.password
        or address.path
    ):
        parser.error("Se requiere una URL HTTP loopback sin ruta")
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.TestSuite(
            ImportsHTTP(name)
            for name in sorted(n for n in ImportsHTTP.__dict__ if n.startswith("test_"))
        )
    )
    sys.exit(not result.wasSuccessful())
