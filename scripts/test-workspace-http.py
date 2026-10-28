"""Real HTTP checks for the administrative workspace. Fictional, disposable site only."""

import argparse
import json
import os
import secrets
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import frappe
import requests

from open_multi_pos.workspace import ADMIN_ROLES, DEFAULTS


class WorkspaceHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.chdir(OPTIONS.bench / "sites")
        frappe.init(OPTIONS.site, sites_path=str(OPTIONS.bench / "sites"))
        frappe.connect()
        frappe.set_user("Administrator")
        if not frappe.conf.get("allow_tests"):
            raise RuntimeError("Se requiere un sitio desechable con allow_tests")
        cls.user = "omp-workspace-test@example.invalid"
        cls.old_settings = frappe.get_single("OMP Workspace Settings").as_dict()
        cls.old_mode = frappe.db.get_single_value("POS Settings", "invoice_type")
        cls.addClassCleanup(cls.cleanup)
        cls.token = secrets.token_hex(16)
        secret = secrets.token_hex(24)
        cls.authorization = f"token {cls.token}:{secret}"
        if not frappe.db.exists("User", cls.user):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": cls.user,
                    "first_name": "Administrador ficticio",
                    "send_welcome_email": 0,
                }
            ).insert()
        user = frappe.get_doc("User", cls.user)
        cls.old_user = user.as_dict()
        cls.old_secret = user.get_password("api_secret", raise_exception=False)
        user.api_key, user.api_secret, user.enabled = cls.token, secret, 1
        user.language = "es"
        user.set("roles", [{"role": role} for role in ADMIN_ROLES])
        user.save()
        frappe.get_single("OMP Workspace Settings").update(DEFAULTS).save()
        frappe.get_single("POS Settings").update({"invoice_type": "Sales Invoice"}).save()
        frappe.db.commit()
        frappe.clear_cache()
        cls.businesses = []
        for suffix in ("A", "B", "Compartido"):
            data = {
                "display_name": "Negocio ficticio " + suffix,
                "company": cls.businesses[0]["company"] if suffix == "Compartido" else "",
                "legal_name": "OMP Workspace Test " + suffix + " " + uuid4().hex[:6],
                "abbr": uuid4().hex[:5],
                "currency": "COP",
            }
            response = cls.request("workspace.create_business", {"data": data}, post=True)
            if response.status_code != 200:
                raise AssertionError("Crear negocio: " + response.text[-1800:])
            context = response.json()["message"]
            terminal = cls.request("workspace.terminal_for", {"brand": context["brand"]}, post=True)
            if terminal.status_code != 200:
                raise AssertionError("Preparar terminal: " + terminal.text[-1800:])
            context["terminal"] = terminal.json()["message"]["terminal"]
            cls.businesses.append(context)

        cls.ensure_fiscal_years()

    @classmethod
    def ensure_fiscal_years(cls):
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
                    "year": "OMP Workspace HTTP " + year + " " + uuid4().hex[:8],
                    "year_start_date": year + "-01-01",
                    "year_end_date": year + "-12-31",
                    "companies": [{"company": company}],
                }
            ).insert()
        frappe.db.commit()

    @classmethod
    def request(cls, method, args=None, *, post=False, guest=False):
        response = requests.request(
            "POST" if post else "GET",
            OPTIONS.base_url + "/api/method/open_multi_pos." + method,
            headers={
                "Host": OPTIONS.site,
                **({} if guest else {"Authorization": cls.authorization}),
            },
            timeout=40,
            **({"json": args or {}} if post else {"params": args or {}}),
        )
        return response

    @classmethod
    def cleanup(cls):
        frappe.set_user("Administrator")
        frappe.db.rollback()
        for name in frappe.get_all(
            "POS Opening Entry",
            filters={
                "user": cls.user,
                "status": "Open",
                "pos_profile": ["in", [b["pos_profile"] for b in getattr(cls, "businesses", [])]],
            },
            pluck="name",
        ):
            from open_multi_pos.checkout import close_shift, shift_summary

            terminal = frappe.db.get_value(
                "OMP POS Terminal", {"opening_entry": name, "user": cls.user}, "name"
            )
            if terminal:
                frappe.set_user(cls.user)
                summary = shift_summary(terminal, name)
                close_shift(
                    {
                        "terminal": terminal,
                        "opening_entry": name,
                        "counts": [
                            {
                                "mode_of_payment": r["mode_of_payment"],
                                "amount": str(max(Decimal(r["expected"]), Decimal(0))),
                            }
                            for r in summary["payments"]
                        ],
                    }
                )
                frappe.set_user("Administrator")
        for brand in getattr(cls, "businesses", []):
            frappe.db.set_value(
                "OMP Business Brand", brand["brand"], {"enabled": 0, "workspace_visible": 0}
            )
            frappe.db.set_value("POS Profile", brand["pos_profile"], "disabled", 1)
            for terminal in frappe.get_all(
                "OMP POS Terminal", filters={"brand": brand["brand"]}, pluck="name"
            ):
                frappe.db.set_value("OMP POS Terminal", terminal, "enabled", 0)
        if hasattr(cls, "old_settings"):
            frappe.get_single("OMP Workspace Settings").update(
                {key: cls.old_settings.get(key) for key in DEFAULTS}
            ).save()
            frappe.db.set_single_value(
                "System Settings",
                "time_zone",
                cls.old_settings.get("time_zone") or DEFAULTS["time_zone"],
            )
        if hasattr(cls, "old_mode"):
            frappe.get_single("POS Settings").update({"invoice_type": cls.old_mode}).save()
        if hasattr(cls, "old_user"):
            user = frappe.get_doc("User", cls.user)
            user.set("roles", cls.old_user["roles"])
            user.api_key = cls.old_user.get("api_key")
            user.api_secret = cls.old_secret
            user.enabled = 0
            user.save()
        frappe.db.commit()
        frappe.clear_cache()
        frappe.destroy()

    def result(self, method, args=None, *, post=False):
        response = self.request(method, args, post=post)
        self.assertEqual(response.status_code, 200, response.text[-1600:])
        return response.json()["message"]

    def product(self, brand=None, *, stock=True, barcode=""):
        brand = brand or self.businesses[0]
        code = "OMP-WORKSPACE-" + uuid4().hex[:12]
        self.result(
            "workspace.create_product",
            {
                "data": {
                    "brand": brand["brand"],
                    "request_id": str(uuid4()),
                    "code": code,
                    "name": "Producto ficticio " + code[-4:],
                    "barcode": barcode,
                    "price": "2500.00",
                    "item_group": "Products",
                }
            },
            post=True,
        )
        if stock:
            self.result(
                "workspace.receive_stock", {"data": self.stock_payload(brand, code)}, post=True
            )
        return code

    def stock_payload(self, brand, code):
        return {
            "brand": brand["brand"],
            "item_code": code,
            "qty": 5,
            "cost": "800.00",
            "request_id": str(uuid4()),
        }

    def sale(self, brand, item):
        context = self.result("cashier.context", {"terminal": brand["terminal"]})
        if not context["opening"] or context["opening"]["status"] != "Open":
            self.result(
                "checkout.open_shift",
                {
                    "data": {
                        "terminal": brand["terminal"],
                        "balances": [
                            {"mode_of_payment": p["name"], "amount": "0.00"}
                            for p in context["payment_modes"]
                        ],
                    }
                },
                post=True,
            )
        quote = self.result(
            "checkout.quote",
            {
                "data": {
                    "terminal": brand["terminal"],
                    "customer": context["customer"],
                    "items": [{"item_code": item, "qty": 1}],
                }
            },
            post=True,
        )
        return {
            "terminal": brand["terminal"],
            "quote": quote["quote"],
            "request_id": str(uuid4()),
            "payments": [
                {"mode_of_payment": context["payment_modes"][0]["name"], "amount": quote["total"]}
            ],
        }

    def batch(self):
        return {
            "request_id": str(uuid4()),
            "sales": [self.sale(b, self.product(b)) for b in self.businesses[:2]],
        }

    def counts(self):
        frappe.db.rollback()
        return {
            dt: frappe.db.count(dt)
            for dt in ("Sales Invoice", "Stock Ledger Entry", "GL Entry", "Stock Entry")
        }

    def test_01_admin_access_and_guest_rejection(self):
        self.assertEqual(self.request("workspace.boot", guest=True).status_code, 403)
        self.assertEqual(self.request("workspace.recovery_status", guest=True).status_code, 403)
        self.assertEqual(
            set(self.result("workspace.recovery_status")),
            {"backup_at", "restore_at", "backup_recent"},
        )
        self.assertEqual(
            self.request("workspace.create_user", {"data": {}}, post=True, guest=True).status_code,
            403,
        )
        boot = self.result("workspace.boot")
        self.assertEqual(boot["settings"]["interface_language"], "es")
        self.assertEqual(boot["settings"]["default_currency"], "COP")
        self.assertTrue(
            {b["brand"] for b in self.businesses}.issubset({b["brand"] for b in boot["businesses"]})
        )
        self.assertEqual(self.businesses[0]["company"], self.businesses[2]["company"])
        self.assertNotEqual(self.businesses[0]["warehouse"], self.businesses[2]["warehouse"])
        self.assertNotEqual(self.businesses[0]["company"], self.businesses[1]["company"])

    def test_02_inventory_idempotency_and_tombstone(self):
        brand = self.businesses[0]
        code = self.product(stock=False)
        data = self.stock_payload(brand, code)
        before = self.counts()
        result = self.result("workspace.receive_stock", {"data": data}, post=True)
        self.assertTrue(
            self.result("workspace.receive_stock", {"data": data}, post=True)["duplicate"]
        )
        self.assertEqual(
            self.result("workspace.resolve_stock", {"data": data}, post=True)["stock_entry"],
            result["stock_entry"],
        )
        self.assertEqual(self.counts()["Stock Entry"], before["Stock Entry"] + 1)
        inventory = self.result("workspace.inventory", {"brand": brand["brand"]})
        self.assertEqual(next(r["qty"] for r in inventory["items"] if r["name"] == code), 5)
        blocked = {**data, "request_id": str(uuid4())}
        self.assertEqual(
            self.result("workspace.resolve_stock", {"data": blocked}, post=True)["status"],
            "abandoned",
        )
        self.assertEqual(
            self.request("workspace.receive_stock", {"data": blocked}, post=True).status_code, 409
        )
        self.assertEqual(
            self.request(
                "workspace.receive_stock", {"data": {**data, "qty": 6}}, post=True
            ).status_code,
            409,
        )

    def test_03_inventory_concurrent_retry_and_ownership(self):
        brand = self.businesses[0]
        code = self.product(stock=False)
        data = self.stock_payload(brand, code)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda _: self.request("workspace.receive_stock", {"data": data}, post=True),
                    range(2),
                )
            )
        self.assertIn(200, [r.status_code for r in results])
        self.assertTrue(all(r.status_code in (200, 409) for r in results))
        results = [
            self.request("workspace.receive_stock", {"data": data}, post=True)
            if r.status_code == 409
            else r
            for r in results
        ]
        self.assertEqual(len({r.json()["message"]["stock_entry"] for r in results}), 1)
        self.assertEqual(
            self.request(
                "workspace.receive_stock",
                {
                    "data": {
                        **data,
                        "brand": self.businesses[1]["brand"],
                        "request_id": str(uuid4()),
                    }
                },
                post=True,
            ).status_code,
            417,
        )
        context = self.result("cashier.context", {"terminal": self.businesses[1]["terminal"]})
        self.assertEqual(
            self.result("cashier.search", {"terminal": context["terminal"], "text": code}), []
        )

    def test_04_mixed_sale_native_documents_and_replay(self):
        data = self.batch()
        before = self.counts()
        result = self.result("batch.checkout", {"data": data}, post=True)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["receipt"]["total"], 500000)
        self.assertEqual(len(result["receipt"]["sales"]), 2)
        self.assertEqual(self.counts()["Sales Invoice"], before["Sales Invoice"] + 2)
        self.assertEqual(self.counts()["Stock Ledger Entry"], before["Stock Ledger Entry"] + 2)
        for row, brand in zip(data["sales"], self.businesses[:2], strict=True):
            invoice = frappe.db.get_value(
                "OMP Checkout Request",
                {"terminal": row["terminal"], "request_id": row["request_id"]},
                "invoice",
            )
            self.assertEqual(
                frappe.db.get_value("Sales Invoice", invoice, "company"), brand["company"]
            )
        final = self.counts()
        self.assertTrue(self.result("batch.checkout", {"data": data}, post=True)["duplicate"])
        self.assertEqual(
            self.result("batch.get_status", {"request_id": data["request_id"]})["receipt"],
            result["receipt"],
        )
        self.assertEqual(final, self.counts())
        html = self.result("batch.receipt", {"request_id": data["request_id"]}, post=True)["html"]
        self.assertIn("SIN VALIDEZ FISCAL", html)
        self.assertIn('data-paper-mm="48"', html)
        self.assertNotIn("Impuestos: $ 0", html)

    def test_05_atomic_rollback_on_second_failure(self):
        data = self.batch()
        # The first child is valid. Make the second fail after its predecessor submitted.
        data["sales"].sort(key=lambda row: row["terminal"])
        data["sales"][-1]["payments"][0]["amount"] = "1.00"
        before = self.counts()
        self.assertGreaterEqual(
            self.request("batch.checkout", {"data": data}, post=True).status_code, 400
        )
        self.assertEqual(before, self.counts())
        self.assertEqual(
            self.result("batch.get_status", {"request_id": data["request_id"]})["status"],
            "not_found",
        )

    def test_06_batch_concurrent_duplicate_and_payload_conflict(self):
        data = self.batch()
        before = self.counts()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda _: self.request("batch.checkout", {"data": data}, post=True), range(2)
                )
            )
        self.assertIn(200, [r.status_code for r in results])
        self.assertTrue(all(r.status_code in (200, 409) for r in results))
        results = [
            self.request("batch.checkout", {"data": data}, post=True) if r.status_code == 409 else r
            for r in results
        ]
        self.assertTrue(
            all(r.status_code == 200 for r in results), [r.text[-1000:] for r in results]
        )
        self.assertEqual(self.counts()["Sales Invoice"], before["Sales Invoice"] + 2)
        self.assertEqual(len({r.json()["message"]["receipt"]["id"] for r in results}), 1)
        other = json.loads(json.dumps(data))
        other["sales"][0]["payments"][0]["amount"] = "3000.00"
        self.assertEqual(
            self.request("batch.checkout", {"data": other}, post=True).status_code, 409
        )

    def test_07_batch_abandon_fences_delayed_sale(self):
        data = self.batch()
        before = self.counts()
        self.assertEqual(
            self.result("batch.abandon", {"data": data}, post=True)["status"], "abandoned"
        )
        self.assertEqual(
            self.request("batch.checkout", {"data": data}, post=True).json()["message"]["status"],
            "abandoned",
        )
        self.assertEqual(before, self.counts())
        self.assertEqual(
            self.result("batch.get_status", {"request_id": data["request_id"]})["status"],
            "abandoned",
        )
        fresh = {**data, "request_id": str(uuid4())}
        self.assertEqual(
            self.request("batch.checkout", {"data": fresh}, post=True).status_code, 409
        )

    def test_08_contacts_snapshot_and_independent_flags(self):
        brand = self.businesses[0]
        original = self.result("workspace.business", {"brand": brand["brand"]})
        keys = (
            "brand",
            "display_name",
            "sku_prefix",
            "legal_name",
            "tax_id",
            "phone",
            "email",
            "address",
            "receipt_footer",
            "qr_url",
            "receipt_show_legal_name",
            "receipt_show_tax_id",
            "receipt_show_phone",
            "receipt_show_email",
            "receipt_show_address",
            "receipt_show_footer",
            "receipt_show_qr",
        )
        data = {key: original[key] for key in keys}
        try:
            changed = {
                **data,
                "phone": "000-000-0000",
                "receipt_show_phone": 1,
                "address": "Calle ficticia <almacén>",
                "receipt_show_address": 1,
            }
            self.result("workspace.save_business", {"data": changed}, post=True)
            sale = {"request_id": str(uuid4()), "sales": [self.sale(brand, self.product())]}
            self.result("batch.checkout", {"data": sale}, post=True)
            before = self.result("batch.receipt", {"request_id": sale["request_id"]}, post=True)[
                "html"
            ]
            self.assertIn("000-000-0000", before)
            self.assertNotIn("<almacén>", before)
            self.assertIn("Calle ficticia", before)  # Native sanitization removes unsupported tags.
            self.result(
                "workspace.save_business", {"data": {**changed, "receipt_show_phone": 0}}, post=True
            )
            self.assertEqual(
                self.result("batch.receipt", {"request_id": sale["request_id"]}, post=True)["html"],
                before,
            )
            other = self.result("workspace.business", {"brand": self.businesses[1]["brand"]})
            self.assertFalse(other["receipt_show_phone"])
        finally:
            self.result("workspace.save_business", {"data": data}, post=True)

    def test_09_settings_validation(self):
        for changed in (
            {"printer_profile": "other"},
            {"time_zone": "Not/AZone"},
            {"default_currency": "INVALID"},
            {"interface_language": "xx"},
        ):
            response = self.request(
                "workspace.save_settings", {"data": {**DEFAULTS, **changed}}, post=True
            )
            self.assertGreaterEqual(response.status_code, 400)
        configured = self.result(
            "workspace.save_settings",
            {
                "data": {
                    **DEFAULTS,
                    "interface_language": "en",
                    "locale": "en-US",
                    "default_currency": "USD",
                }
            },
            post=True,
        )
        self.assertEqual(configured["default_currency"], "USD")
        self.result("workspace.save_settings", {"data": DEFAULTS}, post=True)

    def test_10_create_cashier_and_admin_only_team(self):
        email = "omp-fake-" + uuid4().hex[:8] + "@example.invalid"
        self.result(
            "workspace.create_user",
            {
                "data": {
                    "email": email,
                    "full_name": "Cajero ficticio",
                    "password": secrets.token_urlsafe(24),
                    "role": "cashier",
                    "brands": [self.businesses[0]["brand"]],
                }
            },
            post=True,
        )
        frappe.db.rollback()
        user = frappe.get_doc("User", email)
        self.assertNotIn("System Manager", [row.role for row in user.roles])
        user.api_key = secrets.token_hex(16)
        secret = secrets.token_hex(24)
        user.api_secret = secret
        user.save()
        frappe.db.commit()
        response = requests.get(
            OPTIONS.base_url + "/api/method/open_multi_pos.workspace.boot",
            headers={"Host": OPTIONS.site, "Authorization": f"token {user.api_key}:{secret}"},
            timeout=20,
        )
        self.assertEqual(response.status_code, 403)
        user.reload()
        user.enabled = 0
        user.api_key = None
        user.save()
        frappe.db.commit()

    def test_11_native_currency_and_mixed_currency_rejection(self):
        brand = self.result(
            "workspace.create_business",
            {
                "data": {
                    "display_name": "Negocio ficticio USD",
                    "company": "",
                    "legal_name": "OMP Fictional USD " + uuid4().hex[:6],
                    "abbr": uuid4().hex[:5],
                    "currency": "USD",
                }
            },
            post=True,
        )
        brand["terminal"] = self.result(
            "workspace.terminal_for", {"brand": brand["brand"]}, post=True
        )["terminal"]
        self.businesses.append(brand)
        self.ensure_fiscal_years()
        child = self.sale(brand, self.product(brand))
        group = {"request_id": str(uuid4()), "sales": [child]}
        result = self.result("batch.checkout", {"data": group}, post=True)
        self.assertEqual(result["receipt"]["currency"], "USD")
        self.assertEqual(result["receipt"]["sales"][0]["currency"], "USD")
        mixed = {
            "request_id": str(uuid4()),
            "sales": [
                self.sale(brand, self.product(brand)),
                self.sale(self.businesses[0], self.product()),
            ],
        }
        before = self.counts()
        self.assertEqual(
            self.request("batch.checkout", {"data": mixed}, post=True).status_code, 417
        )
        self.assertEqual(before, self.counts())

    def test_12_saved_batch_rechecks_disabled_business_and_cancelled_invoice(self):
        brand = self.businesses[0]
        data = {"request_id": str(uuid4()), "sales": [self.sale(brand, self.product())]}
        result = self.result("batch.checkout", {"data": data}, post=True)
        try:
            frappe.db.set_value("OMP Business Brand", brand["brand"], "enabled", 0)
            frappe.db.commit()
            self.assertEqual(
                self.request("batch.get_status", {"request_id": data["request_id"]}).status_code,
                403,
            )
            self.assertEqual(
                self.request(
                    "batch.receipt", {"request_id": data["request_id"]}, post=True
                ).status_code,
                403,
            )
        finally:
            frappe.db.set_value("OMP Business Brand", brand["brand"], "enabled", 1)
            frappe.db.commit()
        invoice = frappe.get_doc("Sales Invoice", result["receipt"]["sales"][0]["id"])
        invoice.cancel()
        frappe.db.commit()
        self.assertEqual(
            self.request("batch.get_status", {"request_id": data["request_id"]}).status_code, 409
        )
        self.assertEqual(
            self.request(
                "receipt_preview.preview",
                {"brand": self.businesses[0]["brand"], "kind": "invoice", "document": invoice.name},
            ).status_code,
            403,
        )
        self.assertNotIn(
            invoice.name,
            [
                row["document"]
                for row in self.result(
                    "receipt_preview.documents", {"brand": self.businesses[0]["brand"]}
                )
            ],
        )

    def test_13_second_administrator_personal_opening_and_closing_scope(self):
        email = "omp-second-" + uuid4().hex[:8] + "@example.invalid"
        brand = self.businesses[0]
        self.sale(brand, self.product())
        self.result(
            "workspace.create_user",
            {
                "data": {
                    "email": email,
                    "full_name": "Segundo administrador ficticio",
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
        auth = f"token {user.api_key}:{secret}"

        def second(method, args=None, post=False):
            response = requests.request(
                "POST" if post else "GET",
                OPTIONS.base_url + "/api/method/open_multi_pos." + method,
                headers={"Host": OPTIONS.site, "Authorization": auth},
                timeout=30,
                **({"json": args or {}} if post else {"params": args or {}}),
            )
            self.assertEqual(response.status_code, 200, response.text[-1000:])
            return response.json()["message"]

        try:
            terminal = second("workspace.terminal_for", {"brand": brand["brand"]}, True)["terminal"]
            ctx = second("cashier.context", {"terminal": terminal})
            opening = second(
                "checkout.open_shift",
                {
                    "data": {
                        "terminal": terminal,
                        "balances": [
                            {"mode_of_payment": row["name"], "amount": "0.00"}
                            for row in ctx["payment_modes"]
                        ],
                    }
                },
                True,
            )["opening_entry"]
            quote = second(
                "checkout.quote",
                {
                    "data": {
                        "terminal": terminal,
                        "customer": ctx["customer"],
                        "items": [{"item_code": self.product(), "qty": 1}],
                    }
                },
                True,
            )
            child = {
                "terminal": terminal,
                "request_id": str(uuid4()),
                "quote": quote["quote"],
                "payments": [
                    {"mode_of_payment": ctx["payment_modes"][0]["name"], "amount": quote["total"]}
                ],
            }
            result = second("checkout.checkout", {"data": child}, True)
            frappe.db.rollback()
            self.assertEqual(
                frappe.db.get_value("Sales Invoice", result["invoice"], "owner"), email
            )
            summary = second(
                "checkout.shift_summary", {"terminal": terminal, "opening_entry": opening}, True
            )
            self.assertEqual(summary["invoice_count"], 1)
            second(
                "checkout.close_shift",
                {
                    "data": {
                        "terminal": terminal,
                        "opening_entry": opening,
                        "counts": [
                            {"mode_of_payment": row["mode_of_payment"], "amount": row["expected"]}
                            for row in summary["payments"]
                        ],
                    }
                },
                True,
            )
            primary = self.result("cashier.context", {"terminal": brand["terminal"]})
            self.assertEqual(primary["opening"]["status"], "Open")
        finally:
            frappe.set_user("Administrator")
            frappe.db.rollback()
            for name in frappe.get_all(
                "POS Opening Entry", filters={"user": email, "status": "Open"}, pluck="name"
            ):
                from open_multi_pos.checkout import close_shift, shift_summary

                terminal = frappe.db.get_value(
                    "OMP POS Terminal", {"opening_entry": name, "user": email}, "name"
                )
                if terminal:
                    frappe.set_user(email)
                    summary = shift_summary(terminal, name)
                    close_shift(
                        {
                            "terminal": terminal,
                            "opening_entry": name,
                            "counts": [
                                {"mode_of_payment": r["mode_of_payment"], "amount": r["expected"]}
                                for r in summary["payments"]
                            ],
                        }
                    )
                    frappe.set_user("Administrator")
            frappe.db.set_value("User", email, {"enabled": 0, "api_key": None})
            for name in frappe.get_all("OMP POS Terminal", filters={"user": email}, pluck="name"):
                frappe.db.set_value("OMP POS Terminal", name, "enabled", 0)
            frappe.db.commit()

    def test_14_automatic_sku_product_data_business_prefix_and_replay(self):
        contexts = [
            self.result("workspace.business", {"brand": b["brand"]}) for b in self.businesses[:2]
        ]
        codes = []
        for brand in contexts:
            data = {
                "brand": brand["brand"],
                "code": "",
                "name": "Café ámbar de prueba",
                "barcode": "",
                "price": "1200.00",
                "item_group": "Products",
                "request_id": str(uuid4()),
            }
            result = self.result("workspace.create_product", {"data": data}, post=True)
            self.assertRegex(
                result["item_code"], "^" + brand["sku_prefix"] + "-CAFE-AMBAR-DE-PRUEBA-[0-9]{5,}$"
            )
            repeated = self.result("workspace.create_product", {"data": data}, post=True)
            self.assertEqual(result["item_code"], repeated["item_code"])
            self.assertTrue(repeated["duplicate"])
            self.assertEqual(
                self.request(
                    "workspace.create_product", {"data": {**data, "name": "Otro nombre"}}, post=True
                ).status_code,
                409,
            )
            codes.append(result["item_code"])
        self.assertNotEqual(codes[0], codes[1])
        data = {
            "brand": contexts[0]["brand"],
            "code": "",
            "name": "Producto ficticio concurrente",
            "barcode": "",
            "price": "1500.00",
            "item_group": "Products",
            "request_id": str(uuid4()),
        }
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda _: self.request("workspace.create_product", {"data": data}, post=True),
                    range(2),
                )
            )
        self.assertIn(200, [r.status_code for r in results])
        self.assertTrue(all(r.status_code in (200, 409) for r in results))
        final = self.result("workspace.create_product", {"data": data}, post=True)
        self.assertTrue(final["duplicate"])
        self.assertTrue(
            all(
                r.status_code == 409 or r.json()["message"]["item_code"] == final["item_code"]
                for r in results
            )
        )

    def test_15_concurrent_personal_opening_is_unique(self):
        brand = self.businesses[2]
        context = self.result("cashier.context", {"terminal": brand["terminal"]})
        data = {
            "terminal": brand["terminal"],
            "balances": [
                {"mode_of_payment": p["name"], "amount": "0.00"} for p in context["payment_modes"]
            ],
        }
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda _: self.request("checkout.open_shift", {"data": data}, post=True),
                    range(2),
                )
            )
        self.assertIn(200, [r.status_code for r in responses])
        self.assertTrue(all(r.status_code in (200, 409) for r in responses))
        final = self.result("checkout.open_shift", {"data": data}, post=True)
        self.assertTrue(final["duplicate"])
        frappe.db.rollback()
        self.assertEqual(
            frappe.db.count(
                "POS Opening Entry",
                {"pos_profile": brand["pos_profile"], "user": self.user, "status": "Open"},
            ),
            1,
        )

    def test_16_receipt_preview_sample_and_saved_snapshot_are_read_only(self):
        brand = self.businesses[0]
        data = self.sale(brand, self.product(brand))
        sale = self.result("checkout.checkout", {"data": data}, post=True)
        args = {"brand": brand["brand"], "kind": "invoice", "document": sale["invoice"]}
        original = self.result("receipt_preview.preview", args)["html"]
        before = self.counts()
        journal_counts = {
            dt: frappe.db.count(dt) for dt in ("OMP Checkout Request", "OMP Sale Batch")
        }
        old_name = frappe.db.get_value("OMP Business Brand", brand["brand"], "display_name")
        frappe.db.set_value(
            "OMP Business Brand", brand["brand"], "display_name", "Nombre ficticio cambiado"
        )
        frappe.db.commit()
        try:
            sample = self.result("receipt_preview.preview", {"brand": brand["brand"]})
            self.assertTrue(sample["sample"])
            self.assertIn("MUESTRA · NO ES UNA VENTA", sample["html"])
            self.assertIn("Nombre ficticio cambiado", sample["html"])
            self.assertEqual(self.result("receipt_preview.preview", args)["html"], original)
            self.assertEqual(self.counts(), before)
            for dt, count in journal_counts.items():
                self.assertEqual(frappe.db.count(dt), count)
            listing = self.result("receipt_preview.documents", {"brand": brand["brand"]})
            self.assertIn(sale["invoice"], [row["document"] for row in listing])
        finally:
            frappe.db.set_value("OMP Business Brand", brand["brand"], "display_name", old_name)
            frappe.db.commit()

    def test_17_receipt_preview_mixed_requires_every_business(self):
        data = self.batch()
        sale = self.result("batch.checkout", {"data": data}, post=True)
        frappe.db.rollback()
        batch_name = frappe.db.get_value(
            "OMP Sale Batch", {"request_id": data["request_id"]}, "name"
        )
        args = {"brand": self.businesses[0]["brand"], "kind": "batch", "document": batch_name}
        html = self.result("receipt_preview.preview", args)["html"]
        for part in sale["receipt"]["sales"]:
            self.assertIn(part["id"], html)
        self.assertEqual(
            self.request(
                "receipt_preview.preview", {**args, "brand": self.businesses[2]["brand"]}
            ).status_code,
            403,
        )
        other = self.businesses[1]["brand"]
        frappe.db.set_value("OMP Business Brand", other, "enabled", 0)
        frappe.db.commit()
        try:
            self.assertEqual(self.request("receipt_preview.preview", args).status_code, 403)
            self.assertNotIn(
                batch_name,
                [
                    r["document"]
                    for r in self.result("receipt_preview.documents", {"brand": args["brand"]})
                ],
            )
        finally:
            frappe.db.set_value("OMP Business Brand", other, "enabled", 1)
            frappe.db.commit()

    def test_18_receipt_preview_rejects_cross_business_and_missing_snapshot(self):
        brand = self.businesses[0]
        data = self.sale(brand, self.product(brand))
        sale = self.result("checkout.checkout", {"data": data}, post=True)
        args = {
            "brand": self.businesses[1]["brand"],
            "kind": "invoice",
            "document": sale["invoice"],
        }
        self.assertEqual(self.request("receipt_preview.preview", args).status_code, 403)
        args["brand"] = brand["brand"]
        args["document"] = "NONEXISTENT-FICTIONAL-INVOICE"
        self.assertEqual(self.request("receipt_preview.preview", args).status_code, 403)
        self.assertEqual(
            self.request(
                "receipt_preview.preview", {"brand": brand["brand"]}, post=True
            ).status_code,
            403,
        )

    def test_19_receipt_preview_admin_only(self):
        args = {"brand": self.businesses[0]["brand"]}
        for method in ("receipt_preview.preview", "receipt_preview.documents"):
            self.assertIn(self.request(method, args, guest=True).status_code, (401, 403))
        user = frappe.get_doc("User", self.user)
        roles = [r.role for r in user.roles]
        user.set("roles", [{"role": "OMP Cashier"}])
        user.save()
        frappe.db.commit()
        frappe.clear_cache(user=self.user)
        try:
            for method in ("receipt_preview.preview", "receipt_preview.documents"):
                self.assertEqual(self.request(method, args).status_code, 403)
        finally:
            user = frappe.get_doc("User", self.user)
            user.set("roles", [{"role": role} for role in roles])
            user.save()
            frappe.db.commit()
            frappe.clear_cache(user=self.user)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench", required=True, type=Path)
    parser.add_argument("--site", default="omp.localhost")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    OPTIONS = parser.parse_args()
    OPTIONS.bench = OPTIONS.bench.expanduser().resolve()
    address = urlparse(OPTIONS.base_url)
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
            WorkspaceHTTP(name)
            for name in sorted(n for n in WorkspaceHTTP.__dict__ if n.startswith("test_"))
        )
    )
    sys.exit(not result.wasSuccessful())
