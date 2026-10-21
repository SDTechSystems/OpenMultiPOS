"""Native online checkout regressions; disposable Bench only, fictional data."""

import argparse
import importlib.util
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import frappe

from open_multi_pos.checkout_contract import operation_key

spec = importlib.util.spec_from_file_location(
    "omp_http_fixtures", Path(__file__).with_name("test-xpos-http.py")
)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)
BaseFixtures = fixtures.XPOSHTTPTests


class NativeCheckoutHTTPTests(BaseFixtures):
    def test_native_cashier_facade_and_catalog_scope(self):
        def facade(method, data=None, user=None):
            return self.call("open_multi_pos.cashier." + method, data, user=user or self.na["user"])

        listed = facade("terminals")
        self.assertEqual(listed.status_code, 200)
        names = {row["name"] for row in listed.json()["message"]}
        self.assertIn(self.na["terminal"], names)
        self.assertNotIn(self.nb["terminal"], names)
        self.assertNotIn(self.nc["terminal"], names)
        context = facade("context", {"terminal": self.na["terminal"]})
        self.assertEqual(context.status_code, 200)
        self.assertEqual(context.json()["message"]["customer"], "OMP HTTP Customer")
        self.assertEqual(facade("context", {"terminal": self.nb["terminal"]}).status_code, 403)
        result = facade("search", {"terminal": self.na["terminal"], "text": self.na["item"]})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["message"][0]["item_code"], self.na["item"])
        self.assertTrue(result.json()["message"][0]["exact"])
        self.assertEqual(
            facade(
                "search", {"terminal": self.nb["terminal"], "text": self.nb["item"]}
            ).status_code,
            403,
        )
        guest = self.call("open_multi_pos.cashier.terminals")
        self.assertEqual(guest.status_code, 403)
        try:
            frappe.db.set_value("POS Profile", self.na["profile"], "disabled", 1)
            frappe.db.commit()
            frappe.clear_cache()
            hidden_terminal = facade("terminals")
            self.assertEqual(hidden_terminal.status_code, 200)
            self.assertNotIn(
                self.na["terminal"], {r["name"] for r in hidden_terminal.json()["message"]}
            )
            self.assertNotIn("_server_messages", hidden_terminal.json())
        finally:
            frappe.db.set_value("POS Profile", self.na["profile"], "disabled", 0)
            frappe.db.commit()
            frappe.clear_cache()
        profile = frappe.get_doc("POS Profile", self.na["profile"])
        item = frappe.get_doc("Item", self.na["item"])
        groups, barcodes = (
            [r.as_dict() for r in profile.item_groups],
            [r.as_dict() for r in item.barcodes],
        )
        barcode = "OMP-HTTP-FICTIONAL-BARCODE"
        try:
            item.append("barcodes", {"barcode": barcode})
            item.save()
            profile.set("item_groups", [{"item_group": "Services"}])
            profile.save()
            frappe.db.commit()
            frappe.clear_cache()
            hidden = facade("search", {"terminal": self.na["terminal"], "text": barcode})
            self.assertEqual(hidden.status_code, 200)
            self.assertEqual(hidden.json()["message"], [])
            self.assertNotIn("_server_messages", hidden.json())
        finally:
            frappe.db.rollback()
            profile = frappe.get_doc("POS Profile", self.na["profile"])
            profile.set("item_groups", groups)
            profile.save()
            item = frappe.get_doc("Item", self.na["item"])
            item.set("barcodes", barcodes)
            item.save()
            frappe.db.commit()
            frappe.clear_cache()

    def test_native_abandoned_attempt_fences_delayed_checkout(self):
        self.stock()
        self.open()
        quoted = self.quote()
        data = self.payload(quoted)
        before = self.counts()
        result = self.native_call("abandon_checkout", data)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["message"]["status"], "abandoned")
        self.assertEqual(self.native_call("abandon_checkout", data).status_code, 200)
        self.assertEqual(self.native_call("checkout", data).status_code, 409)
        self.assertEqual(
            self.native_call("checkout", {**data, "request_id": str(uuid4())}).status_code, 409
        )
        status = self.native_call(
            "get_status", {"terminal": self.na["terminal"], "request_id": data["request_id"]}
        )
        self.assertEqual(status.json()["message"]["status"], "abandoned")
        before["OMP Checkout Request"] += 1  # Durable tombstone, no financial document.
        self.assertEqual(before, self.counts())
        sale = self.payload(self.quote())
        self.assertEqual(self.native_call("checkout", sale).status_code, 200)
        result = self.native_call("abandon_checkout", sale)
        self.assertEqual(result.json()["message"]["status"], "completed")

    def test_native_abandon_checkout_race(self):
        self.stock()
        self.open()
        data = self.payload(self.quote())
        with ThreadPoolExecutor(max_workers=2) as pool:
            sale = pool.submit(self.native_call, "checkout", data)
            abandon = pool.submit(self.native_call, "abandon_checkout", data)
            sale, abandon = sale.result(), abandon.result()
        self.assertIn(sale.status_code, (200, 409))
        self.assertIn(abandon.status_code, (200, 409))
        status = self.native_call(
            "get_status", {"terminal": self.na["terminal"], "request_id": data["request_id"]}
        )
        self.assertEqual(status.status_code, 200)
        final = status.json()["message"]
        self.assertIn(final["status"], ("completed", "abandoned"))
        late = self.native_call("checkout", data)
        self.assertEqual(late.status_code, 200 if final["status"] == "completed" else 409)

    def test_native_saved_receipt_authorization_and_layout(self):
        self.stock()
        self.open()
        data = self.payload(self.quote())
        result = self.native_call("checkout", data)
        self.assertEqual(result.status_code, 200)
        before = self.counts()
        args = {
            "terminal": self.na["terminal"],
            "request_id": data["request_id"],
            "printer": "generic-80",
        }
        receipt = self.call(
            "open_multi_pos.cashier.receipt", args, user=self.na["user"], verb="POST"
        )
        self.assertEqual(receipt.status_code, 200)
        html = receipt.json()["message"]["html"]
        self.assertIn('data-paper-mm="80"', html)
        self.assertIn("SIN VALIDEZ FISCAL", html)
        self.assertNotIn("DEMO ·", html)
        self.assertIn("/assets/open_multi_pos/receipt-print.js", html)
        denied = self.call(
            "open_multi_pos.cashier.receipt", args, user=self.nb["user"], verb="POST"
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(before, self.counts())

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(cls.cleanup_native)
        cls.original_mode = frappe.db.get_single_value("POS Settings", "invoice_type")
        frappe.get_doc("POS Settings").update({"invoice_type": "Sales Invoice"}).save()
        cls.native = []
        cls.permission_added = None
        # A third profile shares A's stock, but belongs to cashier B. This exercises
        # inventory contention across different profile locks, not just one terminal.
        if not frappe.db.exists(
            "User Permission",
            {"user": cls.b["user"], "allow": "Company", "for_value": cls.a["company"]},
        ):
            cls.permission_added = (
                frappe.get_doc(
                    {
                        "doctype": "User Permission",
                        "user": cls.b["user"],
                        "allow": "Company",
                        "for_value": cls.a["company"],
                        "apply_to_all_doctypes": 1,
                    }
                )
                .insert()
                .name
            )
        fixture_run = uuid4().hex[:8]
        for suffix, source in (("A", cls.a), ("B", cls.b), ("C", cls.a)):
            user = cls.b["user"] if suffix == "C" else source["user"]
            company = frappe.get_doc("Company", source["company"])
            bank = f"OMP Native Transfer {suffix}"
            cash = frappe.get_doc("POS Profile", source["profile"]).payments[0].mode_of_payment
            # Use a native Bank account under the company chart, never a real bank.
            account = frappe.db.get_value(
                "Account", {"company": company.name, "account_type": "Bank", "is_group": 0}
            )
            if not account:
                parent = frappe.db.get_value(
                    "Account",
                    {"company": company.name, "account_name": "Bank Accounts", "is_group": 1},
                )
                account = (
                    frappe.get_doc(
                        {
                            "doctype": "Account",
                            "account_name": "OMP Native Test Bank",
                            "company": company.name,
                            "parent_account": parent,
                            "account_type": "Bank",
                            "account_currency": "COP",
                        }
                    )
                    .insert()
                    .name
                )
            if not frappe.db.exists("Mode of Payment", bank):
                frappe.get_doc(
                    {
                        "doctype": "Mode of Payment",
                        "mode_of_payment": bank,
                        "type": "Bank",
                        "accounts": [{"company": company.name, "default_account": account}],
                    }
                ).insert()
            profile_name = f"OMP Native Profile {suffix}"
            if not frappe.db.exists("POS Profile", profile_name):
                profile = frappe.copy_doc(frappe.get_doc("POS Profile", source["profile"]))
                profile.name = profile_name
                profile.set("applicable_for_users", [{"user": user}])
                profile.set(
                    "payments", [{"mode_of_payment": cash, "default": 1}, {"mode_of_payment": bank}]
                )
                profile.customer = "OMP HTTP Customer"
                profile.selling_price_list = "OMP HTTP COP"
                profile.update_stock = 1
                profile.disable_rounded_total = 1
                profile.set_grand_total_to_default_mop = 0
                profile.account_for_change_amount = frappe.db.get_value(
                    "Mode of Payment Account",
                    {"parent": cash, "company": company.name},
                    "default_account",
                )
                profile.insert()
            brand = frappe.db.get_value("OMP Business Brand", {"pos_profile": profile_name})
            if not brand:
                brand = (
                    frappe.get_doc(
                        {
                            "doctype": "OMP Business Brand",
                            "display_name": f"OMP Native Brand {suffix}",
                            "company": company.name,
                            "warehouse": source["warehouse"],
                            "pos_profile": profile_name,
                            "printer_profile": "generic-58",
                            "receipt_footer": "Gracias · prueba ficticia",
                            "qr_url": "https://example.com/native-test",
                            "allowed_users": [{"user": user}],
                        }
                    )
                    .insert()
                    .name
                )
            terminal = frappe.db.get_value("OMP POS Terminal", {"brand": brand, "user": user})
            if not terminal:
                terminal = (
                    frappe.get_doc(
                        {
                            "doctype": "OMP POS Terminal",
                            "display_name": f"OMP Native Terminal {suffix}",
                            "brand": brand,
                            "user": user,
                            "enabled": 1,
                        }
                    )
                    .insert()
                    .name
                )
            # Fresh items avoid inheriting stock ledger dates from another timezone/run.
            code = ("OMP-NATIVE-STOCK-B-" if suffix == "B" else "OMP-NATIVE-STOCK-A-") + fixture_run
            if not frappe.db.exists("Item", code):
                frappe.get_doc(
                    {
                        "doctype": "Item",
                        "item_code": code,
                        "item_name": "Artículo ficticio de integración",
                        "item_group": "Products",
                        "stock_uom": "Nos",
                        "is_stock_item": 1,
                        "is_sales_item": 1,
                        "valuation_rate": 100,
                    }
                ).insert()
            if not frappe.db.exists(
                "Item Price", {"item_code": code, "price_list": "OMP HTTP COP"}
            ):
                frappe.get_doc(
                    {
                        "doctype": "Item Price",
                        "item_code": code,
                        "price_list": "OMP HTTP COP",
                        "price_list_rate": 1000,
                        "currency": "COP",
                        "uom": "Nos",
                    }
                ).insert()
            cls.native.append(
                {
                    "user": user,
                    "profile": profile_name,
                    "brand": brand,
                    "terminal": terminal,
                    "company": company.name,
                    "warehouse": source["warehouse"],
                    "item": code,
                    "cash": cash,
                    "bank": bank,
                }
            )
        frappe.db.commit()
        frappe.clear_cache()

    @classmethod
    def cleanup_native(cls):
        frappe.set_user("Administrator")
        frappe.db.rollback()
        if hasattr(cls, "original_mode"):
            frappe.get_doc("POS Settings").update({"invoice_type": cls.original_mode}).save()
        if getattr(cls, "permission_added", None):
            frappe.delete_doc("User Permission", cls.permission_added)
        for config in getattr(cls, "native", []):
            frappe.db.set_value("OMP POS Terminal", config["terminal"], "enabled", 0)
            frappe.db.set_value("OMP Business Brand", config["brand"], "enabled", 0)
            frappe.db.set_value("POS Profile", config["profile"], "disabled", 1)
        frappe.db.commit()
        frappe.clear_cache()

    def setUp(self):
        super().setUp()
        self.na, self.nb, self.nc = self.native
        self.openings = []
        for config in self.native:
            frappe.db.set_value("OMP POS Terminal", config["terminal"], "enabled", 1)
            frappe.db.set_value("OMP Business Brand", config["brand"], "enabled", 1)
            profile = frappe.get_doc("POS Profile", config["profile"])
            profile.disabled = 0
            profile.enable_fbr_integration = 0
            profile.save()
        frappe.db.commit()
        frappe.clear_cache()

    def tearDown(self):
        # Close successful test sessions natively; preserve financial/stock evidence.
        # Failure diagnostics never dump API keys or document payloads.
        for config, opening in reversed(self.openings):
            frappe.set_user("Administrator")
            frappe.db.rollback()
            frappe.db.set_value("OMP POS Terminal", config["terminal"], "enabled", 1)
            frappe.db.set_value("OMP Business Brand", config["brand"], "enabled", 1)
            frappe.db.set_value("POS Profile", config["profile"], "enable_fbr_integration", 0)
            frappe.db.commit()
            if frappe.db.get_value("POS Opening Entry", opening, "status") != "Open":
                continue
            response = self.native_call(
                "shift_summary", {"terminal": config["terminal"], "opening_entry": opening}, config
            )
            self.assertEqual(response.status_code, 200)
            summary = response.json()["message"]
            counts = [
                {"mode_of_payment": row["mode_of_payment"], "amount": row["expected"]}
                for row in summary["payments"]
            ]
            response = self.native_call(
                "close_shift",
                {"terminal": config["terminal"], "opening_entry": opening, "counts": counts},
                config,
            )
            self.assertEqual(response.status_code, 200, response.json().get("exception"))
        frappe.set_user("Administrator")
        frappe.db.rollback()

    def native_call(self, method, data, config=None, *, version="v1", verb="POST"):
        args = data if method in ("get_status", "shift_summary") else {"data": data}
        return self.call(
            "open_multi_pos.checkout." + method,
            args,
            user=(config or self.na)["user"],
            verb=verb,
            version=version,
        )

    def open(self, config=None):
        config = config or self.na
        balances = [
            {"mode_of_payment": config["cash"], "amount": "100.00"},
            {"mode_of_payment": config["bank"], "amount": "0.00"},
        ]
        response = self.native_call(
            "open_shift", {"terminal": config["terminal"], "balances": balances}, config
        )
        self.assertEqual(response.status_code, 200, response.json().get("exception"))
        name = response.json()["message"]["opening_entry"]
        self.openings.append((config, name))
        return name

    def stock(self, config=None, quantity=10):
        config = config or self.na
        frappe.db.rollback()
        current = Decimal(
            str(
                frappe.db.get_value(
                    "Bin",
                    {"item_code": config["item"], "warehouse": config["warehouse"]},
                    "actual_qty",
                )
                or 0
            )
        )
        difference = Decimal(quantity) - current
        if difference:
            entry = frappe.get_doc(
                {
                    "doctype": "Stock Entry",
                    "stock_entry_type": "Material Receipt" if difference > 0 else "Material Issue",
                    "company": config["company"],
                    "items": [
                        {
                            "item_code": config["item"],
                            "qty": float(abs(difference)),
                            "t_warehouse" if difference > 0 else "s_warehouse": config["warehouse"],
                            "basic_rate": 100,
                            "allow_zero_valuation_rate": 0,
                        }
                    ],
                }
            )
            entry.insert()
            entry.submit()
            frappe.db.commit()

    def quote(self, config=None):
        config = config or self.na
        response = self.native_call(
            "quote",
            {
                "terminal": config["terminal"],
                "customer": "OMP HTTP Customer",
                "items": [{"item_code": config["item"], "qty": 1}],
            },
            config,
        )
        self.assertEqual(response.status_code, 200, response.json().get("exception"))
        frappe.db.rollback()  # Diagnostic connection must see the quote committed by HTTP.
        return response.json()["message"]

    def payload(self, quoted, config=None, *, mixed=False):
        config = config or self.na
        payments = [{"mode_of_payment": config["cash"], "amount": quoted["total"]}]
        if mixed:
            payments = [
                {"mode_of_payment": config["cash"], "amount": "700.00"},
                {
                    "mode_of_payment": config["bank"],
                    "amount": "500.00",
                    "reference_no": "OMP-FICTIONAL-TRANSFER",
                },
            ]
        return {
            "terminal": config["terminal"],
            "quote": quoted["quote"],
            "request_id": str(uuid4()),
            "payments": payments,
        }

    def counts(self):
        frappe.db.rollback()
        return {
            d: frappe.db.count(d)
            for d in ("Sales Invoice", "Stock Ledger Entry", "GL Entry", "OMP Checkout Request")
        }

    def test_native_sale_stock_gl_mixed_payment_change_and_identical_retry(self):
        self.stock(quantity=10)
        self.open()
        quoted = self.quote()
        self.assertEqual(quoted["total"], "1000.00")
        data = self.payload(quoted, mixed=True)
        response = self.native_call("checkout", data)
        self.assertEqual(response.status_code, 200, response.json().get("exception"))
        sale = response.json()["message"]
        frappe.db.rollback()
        invoice = frappe.get_doc("Sales Invoice", sale["invoice"])
        self.assertEqual(invoice.docstatus, 1)
        self.assertEqual(invoice.owner, self.na["user"])
        self.assertEqual(invoice.set_warehouse, self.na["warehouse"])
        self.assertEqual(invoice.change_amount, 200)
        self.assertEqual(invoice.outstanding_amount, 0)
        self.assertTrue(invoice.is_created_using_pos and invoice.update_stock)
        entries = frappe.get_all(
            "Stock Ledger Entry",
            filters={"voucher_type": "Sales Invoice", "voucher_no": invoice.name},
            fields=["actual_qty", "warehouse"],
        )
        self.assertEqual(
            [(r.actual_qty, r.warehouse) for r in entries], [(-1, self.na["warehouse"])]
        )
        ledger = frappe.get_all(
            "GL Entry",
            filters={
                "voucher_type": "Sales Invoice",
                "voucher_no": invoice.name,
                "is_cancelled": 0,
            },
            fields=["debit", "credit"],
        )
        self.assertTrue(ledger)
        self.assertEqual(sum(Decimal(str(r.debit)) - Decimal(str(r.credit)) for r in ledger), 0)
        before = self.counts()
        retried = self.native_call("checkout", data, version="v2")
        self.assertEqual(retried.status_code, 200)
        self.assertEqual(retried.json()["data"]["invoice"], invoice.name)
        self.assertEqual(before, self.counts())
        self.assertEqual(sale["receipt"]["change"], 20000)
        self.assertFalse(sale["receipt"]["fiscal_issued"])
        self.assertFalse(sale["receipt"]["payments"][0]["verified_externally"])

    def test_native_payload_hash_and_unique_quote_prevent_changed_retries(self):
        self.stock()
        self.open()
        data = self.payload(self.quote())
        self.assertEqual(self.native_call("checkout", data).status_code, 200)
        before = self.counts()
        changed = {**data, "payments": [{"mode_of_payment": self.na["cash"], "amount": "1001.00"}]}
        self.assertEqual(self.native_call("checkout", changed).status_code, 409)
        self.assertEqual(
            self.native_call("checkout", {**data, "request_id": str(uuid4())}).status_code, 409
        )
        self.assertEqual(before, self.counts())

    def test_native_concurrent_identical_requests_post_exactly_once(self):
        self.stock()
        self.open()
        data = self.payload(self.quote())
        before = self.counts()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.native_call("checkout", data), range(2)))
        self.assertIn(200, [r.status_code for r in results])
        self.assertTrue(all(r.status_code in (200, 409) for r in results))
        response = self.native_call("checkout", data)
        self.assertEqual(response.status_code, 200)
        after = self.counts()
        self.assertEqual(after["Sales Invoice"] - before["Sales Invoice"], 1)
        self.assertEqual(after["Stock Ledger Entry"] - before["Stock Ledger Entry"], 1)
        self.assertEqual(after["OMP Checkout Request"] - before["OMP Checkout Request"], 1)
        names = {r.json()["message"]["invoice"] for r in results if r.status_code == 200}
        self.assertEqual(names, {response.json()["message"]["invoice"]})

    def test_native_two_profiles_competing_for_last_unit(self):
        self.stock(quantity=1)
        self.open(self.na)
        self.open(self.nc)
        payloads = [
            (self.na, self.payload(self.quote(self.na), self.na)),
            (self.nc, self.payload(self.quote(self.nc), self.nc)),
        ]
        before = self.counts()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(lambda pair: self.native_call("checkout", pair[1], pair[0]), payloads)
            )
        self.assertEqual(sorted(r.status_code for r in results), [200, 409])
        frappe.db.rollback()
        self.assertEqual(
            frappe.db.get_value(
                "Bin",
                {"item_code": self.na["item"], "warehouse": self.na["warehouse"]},
                "actual_qty",
            ),
            0,
        )
        self.assertEqual(self.counts()["Sales Invoice"] - before["Sales Invoice"], 1)

    def test_native_stock_unit_is_used_even_with_a_different_sales_unit(self):
        self.stock(quantity=10)
        self.open()
        item = frappe.get_doc("Item", self.na["item"])
        previous = item.sales_uom
        if not frappe.db.exists("UOM", "OMP Native Box"):
            frappe.get_doc(
                {"doctype": "UOM", "uom_name": "OMP Native Box", "must_be_whole_number": 1}
            ).insert()
        if not any(row.uom == "OMP Native Box" for row in item.uoms):
            item.append("uoms", {"uom": "OMP Native Box", "conversion_factor": 10})
        item.sales_uom = "OMP Native Box"
        item.save()
        frappe.db.commit()
        try:
            response = self.native_call("checkout", self.payload(self.quote()))
            self.assertEqual(response.status_code, 200, response.json().get("exception"))
            frappe.db.rollback()
            invoice = frappe.get_doc("Sales Invoice", response.json()["message"]["invoice"])
            self.assertEqual(invoice.items[0].uom, item.stock_uom)
            self.assertEqual(invoice.items[0].stock_qty, 1)
            self.assertEqual(
                frappe.db.get_value(
                    "Bin", {"item_code": item.name, "warehouse": self.na["warehouse"]}, "actual_qty"
                ),
                9,
            )
        finally:
            frappe.db.rollback()
            item = frappe.get_doc("Item", item.name)
            item.sales_uom = previous
            item.save()
            frappe.db.commit()

    def test_native_negative_stock_setting_cannot_bypass_checkout(self):
        self.stock(quantity=0)
        self.open()
        item = frappe.get_doc("Item", self.na["item"])
        original = item.allow_negative_stock
        try:
            item.allow_negative_stock = 1
            item.save()
            frappe.db.commit()
            data = self.payload(self.quote())
            before = self.counts()
            self.assertEqual(self.native_call("checkout", data).status_code, 409)
            self.assertEqual(before, self.counts())
        finally:
            frappe.db.rollback()
            item = frappe.get_doc("Item", item.name)
            item.allow_negative_stock = original
            item.save()
            frappe.db.commit()

    def test_native_forbidden_terminal_quote_and_revoked_brand(self):
        self.stock()
        self.open()
        data = self.payload(self.quote())
        before = self.counts()
        self.assertEqual(self.native_call("checkout", data, self.nb).status_code, 403)
        self.assertEqual(
            self.native_call(
                "checkout", {**data, "terminal": self.nb["terminal"]}, self.nb
            ).status_code,
            403,
        )
        frappe.db.set_value("OMP Business Brand", self.na["brand"], "enabled", 0)
        frappe.db.commit()
        self.assertEqual(self.native_call("checkout", data).status_code, 403)
        self.assertEqual(before, self.counts())

    def test_native_stale_price_quote_and_failed_payment_leave_no_partial_sale(self):
        self.stock()
        self.open()
        data = self.payload(self.quote())
        price_name = frappe.db.get_value(
            "Item Price", {"item_code": self.na["item"], "price_list": "OMP HTTP COP"}
        )
        price = frappe.get_doc("Item Price", price_name)
        original = price.price_list_rate
        before = self.counts()
        try:
            price.price_list_rate = original + 1
            price.save()
            frappe.db.commit()
            self.assertEqual(self.native_call("checkout", data).status_code, 409)
        finally:
            price.price_list_rate = original
            price.save()
            frappe.db.commit()
        data["payments"][0]["amount"] = "1.00"
        self.assertEqual(self.native_call("checkout", data).status_code, 417)
        self.assertEqual(before, self.counts())
        self.assertFalse(
            frappe.db.exists(
                "OMP Checkout Request", operation_key(data["terminal"], data["request_id"])
            )
        )

    def test_native_replay_keeps_receipt_snapshot_after_brand_edit_and_close(self):
        self.stock()
        self.open()
        data = self.payload(self.quote())
        response = self.native_call("checkout", data)
        self.assertEqual(response.status_code, 200)
        receipt = response.json()["message"]["receipt"]
        brand = frappe.get_doc("OMP Business Brand", self.na["brand"])
        original = brand.receipt_footer
        try:
            brand.receipt_footer = "Otro pie ficticio"
            brand.save()
            frappe.db.commit()
            status = self.native_call(
                "get_status",
                {"terminal": data["terminal"], "request_id": data["request_id"]},
                verb="GET",
            )
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.json()["message"]["receipt"], receipt)
        finally:
            brand.receipt_footer = original
            brand.save()
            frappe.db.commit()

    def test_native_opening_closing_reconciliation_and_no_reposting(self):
        self.stock()
        opening = self.open()
        self.assertEqual(self.open(), opening)
        data = self.payload(self.quote(), mixed=True)
        response = self.native_call("checkout", data)
        self.assertEqual(response.status_code, 200, response.json().get("exception"))
        invoice = response.json()["message"]["invoice"]
        before = self.counts()
        summary = self.native_call(
            "shift_summary", {"terminal": self.na["terminal"], "opening_entry": opening}
        ).json()["message"]
        expected = {r["mode_of_payment"]: r["expected"] for r in summary["payments"]}
        self.assertEqual(expected, {self.na["cash"]: "600.00", self.na["bank"]: "500.00"})
        close = {
            "terminal": self.na["terminal"],
            "opening_entry": opening,
            "counts": [{"mode_of_payment": k, "amount": v} for k, v in expected.items()],
        }
        response = self.native_call("close_shift", close)
        self.assertEqual(response.status_code, 200, response.json().get("exception"))
        closing = response.json()["message"]["closing_entry"]
        frappe.db.rollback()
        self.assertEqual(frappe.db.get_value("POS Opening Entry", opening, "status"), "Closed")
        self.assertEqual(
            frappe.db.get_value("Sales Invoice", invoice, "pos_closing_entry"), closing
        )
        self.assertEqual(self.native_call("close_shift", close).status_code, 200)
        changed = {
            **close,
            "counts": [
                {"mode_of_payment": self.na["cash"], "amount": "601.00"},
                {"mode_of_payment": self.na["bank"], "amount": "500.00"},
            ],
        }
        self.assertEqual(self.native_call("close_shift", changed).status_code, 409)
        self.assertEqual(before, self.counts())
        self.assertEqual(self.native_call("checkout", data).status_code, 200)
        self.assertEqual(
            self.native_call("checkout", {**data, "request_id": str(uuid4())}).status_code,
            409,
        )

    def test_native_close_racing_sale_is_serialized(self):
        self.stock()
        opening = self.open()
        data = self.payload(self.quote())
        close = {
            "terminal": self.na["terminal"],
            "opening_entry": opening,
            "counts": [
                {"mode_of_payment": self.na["cash"], "amount": "100.00"},
                {"mode_of_payment": self.na["bank"], "amount": "0.00"},
            ],
        }
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda pair: self.native_call(*pair),
                    (("checkout", data), ("close_shift", close)),
                )
            )
        self.assertTrue(all(r.status_code in (200, 409) for r in results))
        closed = self.native_call("close_shift", close)
        self.assertEqual(closed.status_code, 200)
        status = self.native_call(
            "get_status",
            {"terminal": data["terminal"], "request_id": data["request_id"]},
            verb="GET",
        )
        self.assertEqual(status.status_code, 200)
        saved = status.json()["message"]
        if saved["status"] == "completed":
            frappe.db.rollback()
            self.assertEqual(
                frappe.db.get_value("Sales Invoice", saved["invoice"], "pos_closing_entry"),
                closed.json()["message"]["closing_entry"],
            )
        else:
            self.assertEqual(self.native_call("checkout", data).status_code, 409)

    def test_native_recorded_brand_prevents_access_through_reused_profile(self):
        self.stock()
        self.open()
        response = self.native_call("checkout", self.payload(self.quote()))
        self.assertEqual(response.status_code, 200)
        invoice = response.json()["message"]["invoice"]
        profile = frappe.get_doc("POS Profile", self.na["profile"])
        prior_users = [row.as_dict() for row in profile.applicable_for_users]
        brand = None
        try:
            profile.append("applicable_for_users", {"user": self.nb["user"]})
            profile.save()
            brand = (
                frappe.get_doc(
                    {
                        "doctype": "OMP Business Brand",
                        "display_name": "OMP Native Temporary Shared Profile",
                        "company": self.na["company"],
                        "warehouse": self.na["warehouse"],
                        "pos_profile": profile.name,
                        "printer_profile": "generic-58",
                        "allowed_users": [{"user": self.nb["user"]}],
                    }
                )
                .insert()
                .name
            )
            frappe.db.commit()
            denied = self.call(
                "xpos.api.invoices.get_invoice_details",
                {"invoice_name": invoice, "doctype": "Sales Invoice"},
                user=self.nb["user"],
            )
            self.assertEqual(denied.status_code, 403)
        finally:
            frappe.db.rollback()
            profile = frappe.get_doc("POS Profile", profile.name)
            profile.set("applicable_for_users", prior_users)
            profile.save()
            if brand:
                frappe.delete_doc("OMP Business Brand", brand)
            frappe.db.commit()

    def test_native_guest_get_mutation_raw_document_and_fiscal_routes_are_rejected(self):
        self.stock()
        self.open()
        data = self.payload(self.quote())
        before = self.counts()
        self.assertEqual(self.native_call("checkout", data, verb="GET").status_code, 403)
        self.assertEqual(
            self.call("open_multi_pos.checkout.checkout", {"data": data}, verb="POST").status_code,
            403,
        )
        self.assertEqual(
            self.native_call("checkout", {**data, "company": self.nb["company"]}).status_code, 417
        )
        raw = {
            "doctype": "Sales Invoice",
            "company": self.na["company"],
            "customer": "OMP HTTP Customer",
            "pos_profile": self.na["profile"],
            "is_pos": 1,
            "items": [{"item_code": self.na["item"], "qty": 1, "rate": 1}],
        }
        self.assertEqual(
            self.call(
                "frappe.client.insert", {"doc": raw}, user=self.na["user"], verb="POST"
            ).status_code,
            403,
        )
        frappe.db.set_value("POS Profile", self.na["profile"], "enable_fbr_integration", 1)
        frappe.db.commit()
        self.assertEqual(self.native_call("checkout", data).status_code, 417)
        self.assertEqual(before, self.counts())

    def test_native_tax_template_is_calculated_and_posted_by_erpnext(self):
        self.stock()
        self.open()
        company = frappe.get_doc("Company", self.na["company"])
        account_name = "OMP Native Fictional Tax"
        account = frappe.db.get_value(
            "Account", {"company": company.name, "account_name": account_name}
        )
        if not account:
            parent = frappe.db.get_value(
                "Account",
                {"company": company.name, "account_name": "Current Liabilities", "is_group": 1},
            )
            account = (
                frappe.get_doc(
                    {
                        "doctype": "Account",
                        "account_name": account_name,
                        "parent_account": parent,
                        "company": company.name,
                        "account_type": "Tax",
                        "account_currency": "COP",
                    }
                )
                .insert()
                .name
            )
        template = frappe.db.get_value(
            "Sales Taxes and Charges Template",
            {"title": "OMP Native Fictional Tax", "company": company.name},
        )
        if not template:
            template = (
                frappe.get_doc(
                    {
                        "doctype": "Sales Taxes and Charges Template",
                        "title": "OMP Native Fictional Tax",
                        "company": company.name,
                        "taxes": [
                            {
                                "charge_type": "On Net Total",
                                "account_head": account,
                                "description": "Impuesto ficticio 19%",
                                "rate": 19,
                                "cost_center": company.cost_center,
                            }
                        ],
                    }
                )
                .insert()
                .name
            )
        profile = frappe.get_doc("POS Profile", self.na["profile"])
        original = profile.taxes_and_charges
        try:
            profile.taxes_and_charges = template
            profile.save()
            frappe.db.commit()
            quoted = self.quote()
            self.assertEqual(quoted["total"], "1190.00")
            self.assertEqual(quoted["taxes"], "190.00")
            response = self.native_call("checkout", self.payload(quoted))
            self.assertEqual(response.status_code, 200, response.json().get("exception"))
            sale = response.json()["message"]
            self.assertEqual(sale["receipt"]["taxes"], 19000)
            frappe.db.rollback()
            tax = frappe.db.get_value(
                "GL Entry",
                {
                    "voucher_type": "Sales Invoice",
                    "voucher_no": sale["invoice"],
                    "account": account,
                    "is_cancelled": 0,
                },
                "credit",
            )
            self.assertEqual(tax, 190)
        finally:
            frappe.set_user("Administrator")
            frappe.db.rollback()
            profile = frappe.get_doc("POS Profile", self.na["profile"])
            profile.taxes_and_charges = original
            profile.save()
            frappe.db.commit()

    def test_native_gl_failure_rolls_back_invoice_stock_and_idempotency_claim(self):
        self.stock(quantity=10)
        self.open()
        data = self.payload(self.quote())
        company = frappe.get_doc("Company", self.na["company"])
        original = company.accounts_frozen_till_date
        role = company.role_allowed_for_frozen_entries
        before = self.counts()
        try:
            company.accounts_frozen_till_date = frappe.utils.nowdate()
            company.role_allowed_for_frozen_entries = "Accounts Manager"
            company.save()
            frappe.db.commit()
            response = self.native_call("checkout", data)
            self.assertEqual(response.status_code, 417)
            self.assertIn("not authorized", response.json().get("exception", ""))
            self.assertEqual(before, self.counts())
            self.assertEqual(
                frappe.db.get_value(
                    "Bin",
                    {"item_code": self.na["item"], "warehouse": self.na["warehouse"]},
                    "actual_qty",
                ),
                10,
            )
        finally:
            frappe.db.rollback()
            company = frappe.get_doc("Company", self.na["company"])
            company.accounts_frozen_till_date = original
            company.role_allowed_for_frozen_entries = role
            company.save()
            frappe.db.commit()
        self.assertEqual(self.native_call("checkout", data).status_code, 200)

    def test_native_expired_quote_and_raw_writes_after_success_are_rejected(self):
        self.stock()
        self.open()
        quoted = self.quote()
        data = self.payload(quoted)
        valid = frappe.db.get_value("OMP Checkout Quote", quoted["quote"], "valid_until")
        frappe.db.set_value(
            "OMP Checkout Quote", quoted["quote"], "valid_until", "2000-01-01 00:00:00"
        )
        frappe.db.commit()
        self.assertEqual(self.native_call("checkout", data).status_code, 409)
        frappe.db.set_value("OMP Checkout Quote", quoted["quote"], "valid_until", valid)
        frappe.db.commit()
        response = self.native_call("checkout", data)
        self.assertEqual(response.status_code, 200)
        name = response.json()["message"]["invoice"]
        raw = self.call(
            "frappe.client.set_value",
            {
                "doctype": "Sales Invoice",
                "name": name,
                "fieldname": "remarks",
                "value": "Cambio ficticio no autorizado",
            },
            user=self.na["user"],
            verb="POST",
        )
        self.assertEqual(raw.status_code, 403)
        from frappe import share

        share.add("Sales Invoice", name, user=self.na["user"], read=1, write=1, notify=0)
        frappe.db.commit()
        try:
            shared_write = self.call(
                "frappe.client.set_value",
                {
                    "doctype": "Sales Invoice",
                    "name": name,
                    "fieldname": "remarks",
                    "value": "Cambio compartido ficticio no autorizado",
                },
                user=self.na["user"],
                verb="POST",
            )
            self.assertEqual(shared_write.status_code, 403)
        finally:
            share.remove("Sales Invoice", name, user=self.na["user"])
            frappe.db.commit()
        before = self.counts()
        printed = self.call(
            "xpos.api.print_formats.mark_invoice_printed",
            {"doctype": "Sales Invoice", "name": name},
            user=self.na["user"],
            verb="POST",
        )
        self.assertEqual(printed.status_code, 200)
        self.assertEqual(self.native_call("checkout", data).status_code, 200)
        self.assertEqual(before, self.counts())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench", required=True, type=Path)
    parser.add_argument("--site", default="omp.localhost")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--tests", nargs="*")
    options = parser.parse_args()
    options.bench = options.bench.expanduser().resolve()
    address = fixtures.urlparse(options.base_url)
    if (
        address.scheme != "http"
        or address.hostname not in ("127.0.0.1", "localhost")
        or address.username
        or address.password
        or address.path
    ):
        parser.error("Las credenciales solo se envían a una URL HTTP loopback sin ruta.")
    fixtures.OPTIONS = options
    names = options.tests or sorted(
        name for name in NativeCheckoutHTTPTests.__dict__ if name.startswith("test_native_")
    )
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.TestSuite(NativeCheckoutHTTPTests(name) for name in names)
    )
    sys.exit(not result.wasSuccessful())
