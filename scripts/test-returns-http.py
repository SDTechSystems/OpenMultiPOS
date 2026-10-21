"""Native guided returns over HTTP. Fictional disposable fixtures only."""

import argparse
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


class ReturnsHTTP(fixtures.WorkspaceHTTP):
    def sold(self, brand=None, qty=2):
        brand = brand or self.businesses[0]
        code = self.product(brand)
        data = self.sale(brand, code)
        ctx = self.result("cashier.context", {"terminal": brand["terminal"]})
        quote = self.result(
            "checkout.quote",
            {
                "data": {
                    "terminal": brand["terminal"],
                    "customer": ctx["customer"],
                    "items": [{"item_code": code, "qty": qty}],
                }
            },
            post=True,
        )
        data["quote"] = quote["quote"]
        data["payments"][0]["amount"] = quote["total"]
        sale = self.result("checkout.checkout", {"data": data}, post=True)
        return brand, code, sale["invoice"]

    def planned(self, brand, invoice, qty=1):
        info = self.result(
            "returns.inspect", {"brand": brand["brand"], "invoice": invoice}, post=True
        )
        selection = {
            "brand": brand["brand"],
            "invoice": invoice,
            "items": [{"row": info["items"][0]["row"], "qty": qty}],
        }
        quote = self.result("returns.quote", {"data": selection}, post=True)
        return {
            **selection,
            "request_id": str(uuid4()),
            "terminal": brand["terminal"],
            "financial_hash": quote["financial_hash"],
            "reason": "Devolución ficticia de prueba",
            "payments": [
                {
                    "mode_of_payment": quote["payment_modes"][0]["name"],
                    "amount": str(Decimal(quote["total"]) / 100),
                }
            ],
        }

    def test_01_partial_total_original_price_stock_and_balanced_gl(self):
        brand, code, invoice = self.sold()
        data = self.planned(brand, invoice)
        frappe.db.rollback()
        price = frappe.db.get_value("Item Price", {"item_code": code}, "name")
        frappe.db.set_value("Item Price", price, "price_list_rate", 9000)
        frappe.db.commit()
        before = self.counts()
        overview_before = self.result("workspace.overview", {"brand": brand["brand"]})
        result = self.result("returns.submit", {"data": data}, post=True)
        self.assertEqual(result["status"], "completed")
        overview_after = self.result("workspace.overview", {"brand": brand["brand"]})
        self.assertEqual(overview_after["count"], overview_before["count"])
        self.assertEqual(
            Decimal(overview_after["total"]), Decimal(overview_before["total"]) - Decimal("2500")
        )
        self.assertEqual(overview_after["recent"][0]["is_return"], 1)
        frappe.db.rollback()
        note = frappe.get_doc("Sales Invoice", result["credit_note"])
        self.assertEqual(note.return_against, invoice)
        self.assertEqual(note.company, brand["company"])
        self.assertEqual(note.pos_profile, brand["pos_profile"])
        self.assertEqual(note.items[0].warehouse, brand["warehouse"])
        self.assertEqual(note.items[0].rate, 2500)
        self.assertEqual(note.items[0].qty, -1)
        self.assertEqual(note.payments[0].amount, -2500)
        self.assertEqual(note.outstanding_amount, 0)
        self.assertEqual(self.counts()["Sales Invoice"], before["Sales Invoice"] + 1)
        self.assertEqual(
            frappe.db.get_value(
                "Bin", {"item_code": code, "warehouse": brand["warehouse"]}, "actual_qty"
            ),
            4,
        )
        self.assertEqual(
            frappe.db.sql(
                "SELECT SUM(debit-credit) FROM `tabGL Entry` WHERE voucher_no=%s AND is_cancelled=0",
                note.name,
            )[0][0],
            0,
        )
        self.assertEqual(
            frappe.db.sql(
                "SELECT SUM(actual_qty) FROM `tabStock Ledger Entry` WHERE voucher_no=%s AND is_cancelled=0",
                note.name,
            )[0][0],
            1,
        )
        self.assertEqual(
            self.result(
                "returns.inspect", {"brand": brand["brand"], "invoice": invoice}, post=True
            )["items"][0]["remaining"],
            1,
        )
        second = self.planned(brand, invoice)
        self.result("returns.submit", {"data": second}, post=True)
        self.assertEqual(
            self.result(
                "returns.inspect", {"brand": brand["brand"], "invoice": invoice}, post=True
            )["items"][0]["remaining"],
            0,
        )
        before = self.counts()
        invalid = {k: data[k] for k in ("brand", "invoice", "items")}
        self.assertEqual(
            self.request("returns.quote", {"data": invalid}, post=True).status_code, 409
        )
        self.assertEqual(self.counts(), before)

    def test_02_replay_changed_payload_and_historical_receipt(self):
        brand, _, invoice = self.sold()
        data = self.planned(brand, invoice, 2)
        first = self.result("returns.submit", {"data": data}, post=True)
        before = self.counts()
        html = self.result("returns.receipt", {"data": data}, post=True)["html"]
        self.assertIn(invoice, html)
        self.assertIn("DEVOLUCIÓN INTERNA", html)
        old = frappe.db.get_value("OMP Business Brand", brand["brand"], "display_name")
        frappe.db.set_value(
            "OMP Business Brand", brand["brand"], "display_name", "Cambio ficticio posterior"
        )
        frappe.db.commit()
        try:
            replay = self.result("returns.submit", {"data": data}, post=True)
            self.assertTrue(replay["duplicate"])
            self.assertEqual(replay["credit_note"], first["credit_note"])
            self.assertEqual(
                self.result("returns.receipt", {"data": data}, post=True)["html"], html
            )
            self.assertEqual(
                self.request(
                    "returns.submit",
                    {"data": {**data, "reason": "Otro motivo ficticio"}},
                    post=True,
                ).status_code,
                409,
            )
            self.assertEqual(self.counts(), before)
        finally:
            frappe.db.set_value("OMP Business Brand", brand["brand"], "display_name", old)
            frappe.db.commit()

    def test_03_concurrent_duplicate_and_excess_return(self):
        brand, _, invoice = self.sold(qty=1)
        data = self.planned(brand, invoice)
        before = self.counts()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda _: self.request("returns.submit", {"data": data}, post=True), range(2)
                )
            )
        self.assertTrue(all(r.status_code in (200, 409) for r in responses))
        result = self.result("returns.submit", {"data": data}, post=True)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.counts()["Sales Invoice"], before["Sales Invoice"] + 1)
        other = {**data, "request_id": str(uuid4())}
        self.assertEqual(
            self.request("returns.submit", {"data": other}, post=True).status_code, 409
        )
        self.assertEqual(self.counts()["Sales Invoice"], before["Sales Invoice"] + 1)

        brand, _, invoice = self.sold(qty=1)
        first = self.planned(brand, invoice)
        second = {**first, "request_id": str(uuid4())}
        before = self.counts()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda data: self.request("returns.submit", {"data": data}, post=True),
                    [first, second],
                )
            )
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        self.assertEqual(self.counts()["Sales Invoice"], before["Sales Invoice"] + 1)

    def test_04_abandon_blocks_late_submit_and_invalid_payment_rolls_back(self):
        brand, _, invoice = self.sold()
        data = self.planned(brand, invoice)
        self.assertEqual(
            self.result("returns.status", {"data": data}, post=True)["status"], "not_found"
        )
        invalid = {**data, "payments": [{**data["payments"][0], "amount": "1.00"}]}
        before = self.counts()
        self.assertEqual(
            self.request("returns.submit", {"data": invalid}, post=True).status_code, 409
        )
        self.assertEqual(
            self.result("returns.status", {"data": invalid}, post=True)["status"], "not_found"
        )
        self.assertEqual(
            self.result("returns.abandon", {"data": data}, post=True)["status"], "abandoned"
        )
        self.assertEqual(
            self.result("returns.submit", {"data": data}, post=True)["status"], "abandoned"
        )
        self.assertEqual(self.counts(), before)

    def test_05_mixed_basket_returns_keep_each_business(self):
        batch = self.batch()
        sale = self.result("batch.checkout", {"data": batch}, post=True)
        parts = {part["brand"]["id"]: part for part in sale["receipt"]["sales"]}
        first, second = self.businesses[:2]
        result = self.result(
            "returns.submit", {"data": self.planned(first, parts[first["brand"]]["id"])}, post=True
        )
        self.assertEqual(result["receipt"]["sales"][0]["brand"]["id"], first["brand"])
        untouched = self.result(
            "returns.inspect",
            {"brand": second["brand"], "invoice": parts[second["brand"]]["id"]},
            post=True,
        )
        self.assertEqual(untouched["items"][0]["remaining"], 1)
        self.assertEqual(
            self.request(
                "returns.inspect",
                {"brand": first["brand"], "invoice": parts[second["brand"]]["id"]},
                post=True,
            ).status_code,
            403,
        )

    def test_06_closed_opening_replay_and_refund_in_closing(self):
        brand, _, invoice = self.sold()
        data = self.planned(brand, invoice)
        ctx = self.result("cashier.context", {"terminal": brand["terminal"]})
        args = {"terminal": brand["terminal"], "opening_entry": ctx["opening"]["name"]}
        before = self.result("checkout.shift_summary", args, post=True)
        self.result("returns.submit", {"data": data}, post=True)
        after = self.result("checkout.shift_summary", args, post=True)
        mode = data["payments"][0]["mode_of_payment"]

        def expected(summary):
            return Decimal(
                next(p["expected"] for p in summary["payments"] if p["mode_of_payment"] == mode)
            )

        self.assertEqual(expected(after), expected(before) - Decimal("2500"))
        self.result(
            "checkout.close_shift",
            {
                "data": {
                    **args,
                    "counts": [
                        {"mode_of_payment": p["mode_of_payment"], "amount": p["expected"]}
                        for p in after["payments"]
                    ],
                }
            },
            post=True,
        )
        self.assertEqual(
            self.result("returns.submit", {"data": data}, post=True)["status"], "completed"
        )
        new = self.planned(brand, invoice)
        self.assertEqual(self.request("returns.submit", {"data": new}, post=True).status_code, 409)

    def test_07_guest_cashier_and_revoked_business_are_denied(self):
        brand, _, invoice = self.sold()
        data = self.planned(brand, invoice)
        for method in ("returns.submit", "returns.status", "returns.abandon", "returns.receipt"):
            self.assertIn(
                self.request(method, {"data": data}, post=True, guest=True).status_code, (401, 403)
            )
        frappe.db.set_value("OMP Business Brand", brand["brand"], "enabled", 0)
        frappe.db.commit()
        try:
            self.assertEqual(
                self.request("returns.submit", {"data": data}, post=True).status_code, 403
            )
        finally:
            frappe.db.set_value("OMP Business Brand", brand["brand"], "enabled", 1)
            frappe.db.commit()
        user = frappe.get_doc("User", self.user)
        roles = [r.role for r in user.roles]
        user.set("roles", [{"role": "OMP Cashier"}])
        user.save()
        frappe.db.commit()
        frappe.clear_cache(user=self.user)
        try:
            for method in (
                "returns.submit",
                "returns.status",
                "returns.abandon",
                "returns.receipt",
            ):
                self.assertEqual(self.request(method, {"data": data}, post=True).status_code, 403)
        finally:
            user = frappe.get_doc("User", self.user)
            user.set("roles", [{"role": r} for r in roles])
            user.save()
            frappe.db.commit()
            frappe.clear_cache(user=self.user)

    def test_08_original_tax_and_split_refund(self):
        brand = self.businesses[0]
        company = frappe.get_doc("Company", brand["company"])
        parent = frappe.db.get_value(
            "Account",
            {"company": company.name, "account_name": "Current Liabilities", "is_group": 1},
            "name",
        )
        account = (
            frappe.get_doc(
                {
                    "doctype": "Account",
                    "account_name": "Impuesto ficticio " + uuid4().hex[:6],
                    "parent_account": parent,
                    "company": company.name,
                    "account_type": "Tax",
                    "account_currency": "COP",
                }
            )
            .insert()
            .name
        )
        template = (
            frappe.get_doc(
                {
                    "doctype": "Sales Taxes and Charges Template",
                    "title": "Impuesto ficticio " + uuid4().hex[:6],
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
        profile = frappe.get_doc("POS Profile", brand["pos_profile"])
        old = profile.taxes_and_charges
        profile.taxes_and_charges = template
        profile.save()
        frappe.db.commit()
        try:
            _, _, invoice = self.sold(brand)
            # Changing today's profile tax must not change the original return.
            frappe.db.rollback()
            profile.reload()
            profile.taxes_and_charges = old
            profile.save()
            frappe.db.commit()
            data = self.planned(brand, invoice)
            self.assertEqual(Decimal(data["payments"][0]["amount"]), Decimal("2975"))
            quote = self.result(
                "returns.quote",
                {"data": {k: data[k] for k in ("brand", "invoice", "items")}},
                post=True,
            )
            modes = quote["payment_modes"]
            cash = next(m["name"] for m in modes if m["kind"] == "Cash")
            bank = next(m["name"] for m in modes if m["kind"] == "Bank")
            data["payments"] = [
                {"mode_of_payment": cash, "amount": "1000.00"},
                {
                    "mode_of_payment": bank,
                    "amount": "1975.00",
                    "reference_no": "REEMBOLSO-FICTICIO",
                },
            ]
            result = self.result("returns.submit", {"data": data}, post=True)
            frappe.db.rollback()
            doc = frappe.get_doc("Sales Invoice", result["credit_note"])
            self.assertEqual(doc.total_taxes_and_charges, -475)
            self.assertEqual(doc.paid_amount, -2975)
            self.assertEqual(
                next(p.reference_no for p in doc.payments if p.mode_of_payment == bank),
                "REEMBOLSO-FICTICIO",
            )
            self.assertEqual(
                frappe.db.sql(
                    "SELECT SUM(debit-credit) FROM `tabGL Entry` WHERE voucher_no=%s AND account=%s AND is_cancelled=0",
                    (doc.name, account),
                )[0][0],
                475,
            )
            self.assertEqual(
                frappe.db.sql(
                    "SELECT SUM(debit-credit) FROM `tabGL Entry` WHERE voucher_no=%s AND is_cancelled=0",
                    doc.name,
                )[0][0],
                0,
            )
        finally:
            frappe.db.rollback()
            profile.reload()
            profile.taxes_and_charges = old
            profile.save()
            frappe.db.commit()

    def test_09_native_account_failure_rolls_back_everything(self):
        brand, code, invoice = self.sold()
        data = self.planned(brand, invoice)
        frappe.db.rollback()
        account = frappe.get_doc("Sales Invoice", invoice).items[0].income_account
        old = frappe.db.get_value("Account", account, "disabled")
        before = self.counts()
        frappe.db.set_value("Account", account, "disabled", 1)
        frappe.db.commit()
        frappe.clear_cache(doctype="Account")
        try:
            response = self.request("returns.submit", {"data": data}, post=True)
            self.assertEqual(response.status_code, 417)
            self.assertEqual(self.counts(), before)
            self.assertEqual(
                self.result("returns.status", {"data": data}, post=True)["status"], "not_found"
            )
            frappe.db.rollback()
            self.assertEqual(
                frappe.db.get_value(
                    "Bin", {"item_code": code, "warehouse": brand["warehouse"]}, "actual_qty"
                ),
                3,
            )
        finally:
            frappe.db.set_value("Account", account, "disabled", old)
            frappe.db.commit()
            frappe.clear_cache(doctype="Account")
        self.assertEqual(
            self.result("returns.submit", {"data": data}, post=True)["status"], "completed"
        )

    def test_10_other_administrator_refunds_in_personal_opening(self):
        import secrets

        brand, _, invoice = self.sold()
        data = self.planned(brand, invoice)
        email = "omp-return-admin-" + uuid4().hex[:8] + "@example.invalid"
        self.result(
            "workspace.create_user",
            {
                "data": {
                    "email": email,
                    "full_name": "Administrador ficticio de devoluciones",
                    "password": secrets.token_urlsafe(24),
                    "role": "admin",
                    "brands": [brand["brand"]],
                }
            },
            post=True,
        )
        frappe.db.rollback()
        user = frappe.get_doc("User", email)
        user.api_key = secrets.token_hex(16)
        secret = secrets.token_hex(24)
        user.api_secret = secret
        user.save()
        frappe.db.commit()
        prior = self.__class__.authorization
        terminal = opening = None
        self.__class__.authorization = f"token {user.api_key}:{secret}"
        try:
            terminal = self.result("workspace.terminal_for", {"brand": brand["brand"]}, post=True)[
                "terminal"
            ]
            ctx = self.result("cashier.context", {"terminal": terminal})
            opening = self.result(
                "checkout.open_shift",
                {
                    "data": {
                        "terminal": terminal,
                        "balances": [
                            {"mode_of_payment": mode["name"], "amount": "0.00"}
                            for mode in ctx["payment_modes"]
                        ],
                    }
                },
                post=True,
            )
            data["terminal"] = terminal
            result = self.result("returns.submit", {"data": data}, post=True)
            frappe.db.rollback()
            note = frappe.get_doc("Sales Invoice", result["credit_note"])
            self.assertEqual(note.owner, email)
            self.assertEqual(note.return_against, invoice)
            self.assertEqual(
                result["receipt"]["sales"][0]["opening_entry"], opening["opening_entry"]
            )
        finally:
            if terminal and opening:
                summary = self.result(
                    "checkout.shift_summary",
                    {"terminal": terminal, "opening_entry": opening["opening_entry"]},
                    post=True,
                )
                self.result(
                    "checkout.close_shift",
                    {
                        "data": {
                            "terminal": terminal,
                            "opening_entry": opening["opening_entry"],
                            "counts": [
                                {
                                    "mode_of_payment": pay["mode_of_payment"],
                                    "amount": str(max(Decimal(pay["expected"]), Decimal(0))),
                                }
                                for pay in summary["payments"]
                            ],
                        }
                    },
                    post=True,
                )
            self.__class__.authorization = prior
            frappe.db.rollback()
            user = frappe.get_doc("User", email)
            user.enabled = 0
            user.api_key = None
            user.save()
            frappe.db.commit()

    def test_11_cancelled_original_and_credit_note_are_not_replayed(self):
        brand, _, invoice = self.sold()
        data = self.planned(brand, invoice)
        result = self.result("returns.submit", {"data": data}, post=True)
        frappe.db.rollback()
        frappe.get_doc("Sales Invoice", result["credit_note"]).cancel()
        frappe.db.commit()
        before = self.counts()
        self.assertEqual(self.request("returns.submit", {"data": data}, post=True).status_code, 409)
        self.assertEqual(self.request("returns.status", {"data": data}, post=True).status_code, 409)
        self.assertEqual(self.counts(), before)
        _, _, other = self.sold()
        frappe.db.rollback()
        frappe.get_doc("Sales Invoice", other).cancel()
        frappe.db.commit()
        self.assertEqual(
            self.request(
                "returns.inspect", {"brand": brand["brand"], "invoice": other}, post=True
            ).status_code,
            403,
        )


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
            ReturnsHTTP(name)
            for name in sorted(n for n in ReturnsHTTP.__dict__ if n.startswith("test_"))
        )
    )
    sys.exit(not result.wasSuccessful())
