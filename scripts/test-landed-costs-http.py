"""Real native landed-cost HTTP checks; fictional disposable site only."""

import argparse
import copy
import importlib.util
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import frappe

spec = importlib.util.spec_from_file_location(
    "workspace_fixtures", Path(__file__).with_name("test-workspace-http.py")
)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


class LandedCostsHTTP(fixtures.WorkspaceHTTP):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The HTTP-created companies committed through another database connection.
        frappe.db.rollback()
        from erpnext.accounts.utils import get_fiscal_year
        from frappe.utils import nowdate

        today = nowdate()
        year = today[:4]
        for company in sorted({brand["company"] for brand in cls.businesses}):
            if get_fiscal_year(today, company=company, raise_on_missing=False):
                continue
            frappe.get_doc(
                {
                    "doctype": "Fiscal Year",
                    "year": "OMP LCV HTTP " + year + " " + uuid4().hex[:8],
                    "year_start_date": year + "-01-01",
                    "year_end_date": year + "-12-31",
                    "companies": [{"company": company}],
                }
            ).insert()
        frappe.db.commit()

    def purchase(self, brand=None, doctype="Purchase Receipt", valuation_tax=0):
        brand = brand or self.businesses[0]
        code = self.product(brand, stock=False)
        frappe.db.rollback()
        supplier = frappe.get_doc(
            {
                "doctype": "Supplier",
                "supplier_name": "Proveedor ficticio " + uuid4().hex[:10],
                "supplier_type": "Company",
            }
        ).insert()
        doc = frappe.get_doc(
            {
                "doctype": doctype,
                "company": brand["company"],
                "supplier": supplier.name,
                "currency": "COP",
                "conversion_rate": 1,
                "update_stock": 1,
                "items": [
                    {
                        "item_code": code,
                        "qty": 5,
                        "rate": 1000,
                        "warehouse": brand["warehouse"],
                        "cost_center": frappe.db.get_value(
                            "Company", brand["company"], "cost_center"
                        ),
                    }
                ],
            }
        ).insert()
        if valuation_tax:
            account = frappe.db.get_value(
                "Account",
                {
                    "company": brand["company"],
                    "account_type": "Expenses Included In Valuation",
                    "account_currency": "COP",
                    "is_group": 0,
                },
                "name",
            )
            doc.append(
                "taxes",
                {
                    "charge_type": "Actual",
                    "account_head": account,
                    "category": "Valuation",
                    "add_deduct_tax": "Add",
                    "description": "Costo ficticio previo",
                    "tax_amount": valuation_tax,
                },
            )
            doc.save()
        doc.submit()
        frappe.db.commit()
        return doc

    def data(self, doc, brand=None):
        brand = brand or self.businesses[0]
        account = frappe.db.get_value(
            "Account",
            {
                "company": brand["company"],
                "account_type": "Expenses Included In Valuation",
                "account_currency": "COP",
                "is_group": 0,
            },
            "name",
        )
        return {
            "brand": brand["brand"],
            "receipts": [{"doctype": doc.doctype, "name": doc.name}],
            "basis": "Amount",
            "charges": [
                {
                    "account": account,
                    "currency": "COP",
                    "amount": "500.00",
                    "exchange_rate": "1",
                    "description": "Flete ficticio",
                }
            ],
        }

    def prepared(self, data, submit=1):
        quote = self.result("landed_costs.preview", {"data": data}, post=True)
        return {
            "data": data,
            "request_id": str(uuid4()),
            "plan_hash": quote["plan_hash"],
            "submit": submit,
        }, quote

    def test_01_preview_submit_retry_stock_and_balanced_gl(self):
        doc = self.purchase()
        data = self.data(doc)
        before = frappe.db.count("Landed Cost Voucher")
        args, preview = self.prepared(data)
        self.assertEqual(frappe.db.count("Landed Cost Voucher"), before)
        row = preview["plan"]["items"][0]
        self.assertEqual(Decimal(row["before"]), 1000)
        self.assertEqual(Decimal(row["after"]), 1100)
        result = self.result("landed_costs.save", args, post=True)
        self.assertEqual(result["status"], "submitted")
        self.assertEqual(self.result("landed_costs.save", args, post=True), result)
        frappe.db.rollback()
        self.assertEqual(frappe.db.count("Landed Cost Voucher"), before + 1)
        purchase = frappe.get_doc(doc.doctype, doc.name)
        self.assertEqual(Decimal(str(purchase.items[0].landed_cost_voucher_amount)), 500)
        self.assertEqual(Decimal(str(purchase.items[0].valuation_rate)), 1100)
        self.assertEqual(
            frappe.db.sql(
                "SELECT SUM(debit-credit) FROM `tabGL Entry` WHERE voucher_no=%s AND is_cancelled=0",
                doc.name,
            )[0][0],
            0,
        )
        bin_rate = frappe.db.get_value(
            "Bin",
            {"item_code": doc.items[0].item_code, "warehouse": self.businesses[0]["warehouse"]},
            "valuation_rate",
        )
        self.assertEqual(Decimal(str(bin_rate)), 1100)
        self.assertEqual(
            self.result(
                "landed_costs.status",
                {"brand": data["brand"], "request_id": args["request_id"]},
                post=True,
            ),
            result,
        )

    def test_02_estimate_native_edit_review_and_submit(self):
        doc = self.purchase()
        args, _ = self.prepared(self.data(doc), submit=0)
        result = self.result("landed_costs.save", args, post=True)
        self.assertEqual(result["status"], "draft")
        frappe.db.rollback()
        self.assertEqual(
            frappe.db.get_value(
                "Purchase Receipt Item", doc.items[0].name, "landed_cost_voucher_amount"
            ),
            0,
        )
        draft = frappe.get_doc("Landed Cost Voucher", result["voucher"])
        draft.taxes[0].amount = 1000
        draft.save()
        frappe.db.commit()
        with self.assertRaises(frappe.ValidationError):
            draft.submit()
        frappe.db.rollback()
        submit = {
            "brand": args["data"]["brand"],
            "voucher": draft.name,
            "plan_hash": result["plan_hash"],
        }
        self.assertEqual(
            self.request("landed_costs.submit_draft", submit, post=True).status_code, 409
        )
        updated = self.result(
            "landed_costs.status",
            {"brand": submit["brand"], "request_id": args["request_id"]},
            post=True,
        )
        self.assertEqual(Decimal(updated["plan"]["total"]), 1000)
        submit["plan_hash"] = updated["plan_hash"]
        final = self.result("landed_costs.submit_draft", submit, post=True)
        self.assertEqual(final["status"], "submitted")
        self.assertEqual(self.result("landed_costs.submit_draft", submit, post=True), final)

    def test_03_concurrent_duplicate_and_payload_binding(self):
        doc = self.purchase()
        args, _ = self.prepared(self.data(doc))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(lambda _: self.request("landed_costs.save", args, post=True), range(2))
            )
        self.assertTrue(all(r.status_code in (200, 409) for r in results))
        self.assertTrue(any(r.status_code == 200 for r in results))
        recovered = self.result("landed_costs.save", args, post=True)
        for response in results:
            if response.status_code == 200:
                self.assertEqual(response.json()["message"]["voucher"], recovered["voucher"])
        frappe.db.rollback()
        self.assertEqual(
            frappe.db.count(
                "Landed Cost Voucher",
                {
                    "omp_operation_key": frappe.db.get_value(
                        "Landed Cost Voucher", recovered["voucher"], "omp_operation_key"
                    )
                },
            ),
            1,
        )
        changed = copy.deepcopy(args)
        changed["data"]["charges"][0]["amount"] = "999.00"
        self.assertEqual(self.request("landed_costs.save", changed, post=True).status_code, 409)

    def test_04_permissions_ownership_and_currency_validation(self):
        doc = self.purchase()
        data = self.data(doc)
        self.assertIn(
            self.request("landed_costs.preview", {"data": data}, post=True, guest=True).status_code,
            (401, 403),
        )
        wrong = copy.deepcopy(data)
        wrong["brand"] = self.businesses[2]["brand"]  # same company, different business
        self.assertNotEqual(
            self.request("landed_costs.preview", {"data": wrong}, post=True).status_code, 200
        )
        for field, value in [("currency", "USD"), ("exchange_rate", "0"), ("exchange_rate", "2")]:
            wrong = copy.deepcopy(data)
            wrong["charges"][0][field] = value
            self.assertNotEqual(
                self.request("landed_costs.preview", {"data": wrong}, post=True).status_code, 200
            )
        options = self.result(
            "landed_costs.options", {"brand": self.businesses[2]["brand"]}, post=True
        )
        self.assertNotIn(doc.name, [r["name"] for r in options["receipts"]])

    def test_05_stale_preview_and_cancelled_voucher(self):
        doc = self.purchase()
        args, _ = self.prepared(self.data(doc))
        other, _ = self.prepared(self.data(doc))
        self.result("landed_costs.save", other, post=True)
        self.assertEqual(self.request("landed_costs.save", args, post=True).status_code, 409)
        args, _ = self.prepared(self.data(doc))
        result = self.result("landed_costs.save", args, post=True)
        frappe.db.rollback()
        frappe.get_doc("Landed Cost Voucher", result["voucher"]).cancel()
        frappe.db.commit()
        self.assertEqual(self.request("landed_costs.save", args, post=True).status_code, 409)
        state = self.result(
            "landed_costs.status",
            {"brand": args["data"]["brand"], "request_id": args["request_id"]},
            post=True,
        )
        self.assertEqual(state["status"], "cancelled")

    def test_06_purchase_invoice_with_stock(self):
        doc = self.purchase(doctype="Purchase Invoice")
        args, _ = self.prepared(self.data(doc))
        self.assertEqual(self.result("landed_costs.save", args, post=True)["status"], "submitted")

    def test_07_explicit_foreign_currency_and_multiple_receipts(self):
        first, second = self.purchase(), self.purchase()
        data = self.data(first)
        data["receipts"].append({"doctype": second.doctype, "name": second.name})
        frappe.db.rollback()
        base = frappe.get_doc("Account", data["charges"][0]["account"])
        account = frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": "Flete ficticio USD " + uuid4().hex[:6],
                "company": base.company,
                "parent_account": base.parent_account,
                "account_type": "Expenses Included In Valuation",
                "account_currency": "USD",
                "is_group": 0,
            }
        ).insert()
        frappe.db.commit()
        data["charges"][0].update(
            account=account.name, currency="USD", amount="10.00", exchange_rate="4000"
        )
        data["basis"] = "Qty"
        args, preview = self.prepared(data)
        self.assertEqual(Decimal(preview["plan"]["total"]), 40000)
        self.assertEqual([Decimal(r["charge"]) for r in preview["plan"]["items"]], [20000, 20000])
        result = self.result("landed_costs.save", args, post=True)
        self.assertEqual(result["status"], "submitted")
        frappe.db.rollback()
        doc = frappe.get_doc("Landed Cost Voucher", result["voucher"])
        self.assertEqual(doc.taxes[0].account_currency, "USD")
        self.assertEqual(doc.taxes[0].amount, 10)
        self.assertEqual(doc.taxes[0].base_amount, 40000)

    def test_08_cashier_denied_and_native_failure_rolls_back(self):
        doc = self.purchase()
        data = self.data(doc)
        args, _ = self.prepared(data)
        frappe.db.rollback()
        user = frappe.get_doc("User", self.user)
        roles = [r.role for r in user.roles]
        try:
            user.set("roles", [{"role": "OMP Cashier"}, {"role": "Sales User"}])
            user.save()
            frappe.db.commit()
            self.assertEqual(self.request("landed_costs.save", args, post=True).status_code, 403)
            self.assertEqual(
                self.request(
                    "landed_costs.options", {"brand": data["brand"]}, post=True
                ).status_code,
                403,
            )
            self.assertEqual(
                self.request(
                    "landed_costs.abandon",
                    {"brand": data["brand"], "request_id": args["request_id"]},
                    post=True,
                ).status_code,
                403,
            )
        finally:
            frappe.db.rollback()
            user = frappe.get_doc("User", self.user)
            user.set("roles", [{"role": role} for role in roles])
            user.save()
            frappe.db.commit()
        # A native frozen-period validation fails after insert. The request must
        # roll back the LCV too; state lookup may then return not_found.
        old_settings = frappe.db.sql(
            "SELECT field, value FROM tabSingles WHERE doctype='Stock Settings' AND field IN ('stock_frozen_upto', 'stock_auth_role')"
        )
        try:
            from frappe.utils import nowdate

            frappe.db.set_single_value("Stock Settings", "stock_auth_role", "")
            frappe.db.set_single_value("Stock Settings", "stock_frozen_upto", nowdate())
            frappe.db.commit()
            response = self.request("landed_costs.save", args, post=True)
            self.assertNotEqual(response.status_code, 200)
            state = self.result(
                "landed_costs.status",
                {"brand": data["brand"], "request_id": args["request_id"]},
                post=True,
            )
            self.assertEqual(state["status"], "not_found")
        finally:
            frappe.db.rollback()
            frappe.db.delete(
                "Singles",
                {
                    "doctype": "Stock Settings",
                    "field": ["in", ["stock_frozen_upto", "stock_auth_role"]],
                },
            )
            for field, value in old_settings:
                frappe.db.sql(
                    "INSERT INTO tabSingles (doctype, field, value) VALUES (%s,%s,%s)",
                    ("Stock Settings", field, value),
                )
            frappe.clear_document_cache("Stock Settings", "Stock Settings")
            frappe.db.commit()

    def test_09_preview_includes_native_valuation_taxes(self):
        doc = self.purchase(valuation_tax=100)
        args, preview = self.prepared(self.data(doc))
        row = preview["plan"]["items"][0]
        self.assertEqual(Decimal(row["before"]), 1020)
        self.assertEqual(Decimal(row["after"]), 1120)
        self.result("landed_costs.save", args, post=True)
        frappe.db.rollback()
        updated = frappe.get_doc("Purchase Receipt", doc.name)
        self.assertEqual(Decimal(str(updated.items[0].valuation_rate)), Decimal(row["after"]))

    def test_10_rejected_purchase_can_be_abandoned_and_delayed_save_is_fenced(self):
        doc = self.purchase()
        args, _ = self.prepared(self.data(doc))
        doc.cancel()
        frappe.db.commit()
        before = frappe.db.count("Landed Cost Voucher")
        self.assertNotEqual(self.request("landed_costs.save", args, post=True).status_code, 200)
        lookup = {"brand": args["data"]["brand"], "request_id": args["request_id"]}
        self.assertEqual(
            self.result("landed_costs.status", lookup, post=True)["status"], "not_found"
        )
        self.assertIn(
            self.request("landed_costs.abandon", lookup, post=True, guest=True).status_code,
            (401, 403),
        )
        for _ in range(2):
            self.assertEqual(
                self.result("landed_costs.abandon", lookup, post=True), {"status": "abandoned"}
            )
        self.assertEqual(
            self.result("landed_costs.status", lookup, post=True)["status"], "abandoned"
        )
        self.assertEqual(self.request("landed_costs.save", args, post=True).status_code, 409)
        for method in ("status", "abandon"):
            self.assertEqual(
                self.request(
                    "landed_costs." + method,
                    {**lookup, "brand": self.businesses[2]["brand"]},
                    post=True,
                ).status_code,
                403,
            )
        frappe.db.rollback()
        self.assertEqual(frappe.db.count("Landed Cost Voucher"), before)
        fresh, _ = self.prepared(self.data(self.purchase()))
        self.assertEqual(self.result("landed_costs.save", fresh, post=True)["status"], "submitted")

    def test_11_abandon_and_save_serialize_without_duplicate_vouchers(self):
        args, _ = self.prepared(self.data(self.purchase()))
        lookup = {"brand": args["data"]["brand"], "request_id": args["request_id"]}
        frappe.db.rollback()
        before = frappe.db.count("Landed Cost Voucher")
        with ThreadPoolExecutor(max_workers=2) as pool:
            calls = [
                pool.submit(self.request, "landed_costs.save", args, post=True),
                pool.submit(self.request, "landed_costs.abandon", lookup, post=True),
            ]
            responses = [call.result() for call in calls]
        self.assertTrue(all(r.status_code in (200, 409) for r in responses))
        state = self.result("landed_costs.status", lookup, post=True)
        self.assertIn(state["status"], ("submitted", "abandoned"))
        self.assertEqual(self.result("landed_costs.abandon", lookup, post=True), state)
        if state["status"] == "abandoned":
            self.assertEqual(self.request("landed_costs.save", args, post=True).status_code, 409)
        else:
            self.assertEqual(self.result("landed_costs.save", args, post=True), state)
        frappe.db.rollback()
        self.assertEqual(
            frappe.db.count("Landed Cost Voucher"), before + (state["status"] == "submitted")
        )

    def test_12_resolve_existing_voucher_and_cancelled_source(self):
        source = self.purchase()
        args, _ = self.prepared(self.data(source))
        result = self.result("landed_costs.save", args, post=True)
        lookup = {"brand": args["data"]["brand"], "request_id": args["request_id"]}
        self.assertEqual(self.result("landed_costs.abandon", lookup, post=True), result)
        frappe.db.rollback()
        frappe.get_doc("Landed Cost Voucher", result["voucher"]).cancel()
        frappe.db.commit()
        frappe.get_doc(source.doctype, source.name).cancel()
        frappe.db.commit()
        cancelled = {"status": "cancelled", "voucher": result["voucher"]}
        self.assertEqual(self.result("landed_costs.status", lookup, post=True), cancelled)
        self.assertEqual(self.result("landed_costs.abandon", lookup, post=True), cancelled)
        self.assertEqual(self.request("landed_costs.save", args, post=True).status_code, 409)


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
            LandedCostsHTTP(name)
            for name in sorted(n for n in LandedCostsHTTP.__dict__ if n.startswith("test_"))
        )
    )
    sys.exit(not result.wasSuccessful())
