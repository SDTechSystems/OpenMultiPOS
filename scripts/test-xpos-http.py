"""Real HTTP regression suite. Requires the disposable Bench permission fixtures."""

import argparse
import ast
import json
import os
import secrets
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote, urlparse

import frappe
import requests
from frappe.permissions import add_permission
from frappe.utils.password import remove_encrypted_password

from open_multi_pos.xpos_routes import BLOCKED_INVOICE_METHODS, METHOD_OVERRIDES

PRINT_ROLE = "OMP HTTP Test Printer"
POS_ROLE = "OMP HTTP Test POS Role"
MANAGER = "omp-http-manager@example.invalid"


class XPOSHTTPTests(unittest.TestCase):
    def test_remaining_upstream_http_surface_is_closed(self):
        from open_multi_pos.upstream_gate import REVIEWED
        from open_multi_pos.upstream_inventory import inventory

        entries = inventory(OPTIONS.bench / "apps" / "xpos")
        self.assertEqual(len(entries), 227, "Cambió upstream; revisar el inventario y la política.")
        denied = sorted({entry["method"] for entry in entries} - REVIEWED)
        for method in denied:
            for version in ("v1", "v2"):
                with self.subTest(method=method, version=version):
                    response = self.call(method, version=version, user=self.a["user"])
                    self.assertEqual(response.status_code, 403, response.text[-250:])
        # Scope is independent of role, authentication, verb, cmd and future methods.
        for user in (None, self.a["user"], MANAGER):
            for method in ("xpos.api.sync.get_child_table_data", "xpos.future.unreviewed"):
                for version in ("v1", "v2"):
                    self.assertEqual(self.call(method, version=version, user=user).status_code, 403)
        session = requests.Session()
        session.headers.update({"Host": OPTIONS.site, "Authorization": self.tokens[MANAGER]})
        for path, payload in (
            ("/", {"cmd": "xpos.api.shifts.get_opening_data"}),
            ("/api/method/frappe.client.get_list", {"cmd": "xpos.api.customers.get_customers"}),
            (
                "/api/v2/method/run_doc_method",
                {
                    "method": "get_payment_reconciliation_details",
                    "document": {"doctype": "POS Closing Shift"},
                },
            ),
            (
                "/api/method/run_doc_method",
                {"dt": "POS Closing Shift", "method": "get_payment_reconciliation_details"},
            ),
            (
                "/api/method/frappe.handler.run_doc_method",
                {
                    "docs": json.dumps({"doctype": "POS Closing Shift"}),
                    "method": "get_payment_reconciliation_details",
                },
            ),
            ("/api/v2/method/POS Closing Shift/get_payment_reconciliation_details", {}),
            (
                "/api/v2/document/POS Closing Shift/OMP-NOT-A-DOCUMENT/method/get_payment_reconciliation_details",
                {},
            ),
            (
                "/api/resource/POS Closing Shift/OMP-NOT-A-DOCUMENT",
                {"run_method": "get_payment_reconciliation_details"},
            ),
        ):
            self.assertEqual(
                session.post(OPTIONS.base_url + path, json=payload, timeout=30).status_code, 403
            )
        for path in ("/xpos", "/xpos.html", "/xpos/sw.js", "/xpos/manifest.webmanifest"):
            self.assertEqual(session.get(OPTIONS.base_url + path, timeout=30).status_code, 403)
        from xpos.startup.boot import extend_bootinfo

        from open_multi_pos.upstream_gate import filter_boot

        previous_user = frappe.session.user
        try:
            frappe.set_user(self.a["user"])
            boot = frappe._dict()
            extend_bootinfo(boot)
            self.assertIn("pos_settings", boot)
            filter_boot(boot)
            self.assertNotIn("pos_settings", boot)
            self.assertNotIn("accounts_setting", boot)
            self.assertFalse(any(key.startswith("xpos_") for key in boot))
        finally:
            frappe.set_user(previous_user)

    @classmethod
    def setUpClass(cls):
        os.chdir(OPTIONS.bench / "sites")
        frappe.init(OPTIONS.site, sites_path=str(OPTIONS.bench / "sites"))
        frappe.connect()
        frappe.set_user("Administrator")
        if not frappe.conf.get("allow_tests"):
            raise RuntimeError("Se requiere un sitio desechable con allow_tests.")
        cls.original_users = {}
        cls.tokens = {}
        cls.a = {"user": "omp-cashier-a@example.invalid", "profile": "OMP Test Profile A"}
        cls.b = {"user": "omp-cashier-b@example.invalid", "profile": "OMP Test Profile B"}
        cls.manager_created = not frappe.db.exists("User", MANAGER)
        cls.prior_perms = set(
            frappe.get_all("Custom DocPerm", filters={"parent": "Sales Invoice"}, pluck="name")
        )
        cls.addClassCleanup(cls.cleanup)
        if cls.manager_created:
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": MANAGER,
                    "first_name": "OMP HTTP Test Manager",
                    "send_welcome_email": 0,
                    "roles": [{"role": "System Manager"}, {"role": "Accounts Manager"}],
                }
            ).insert()
        if not frappe.db.exists("Role", PRINT_ROLE):
            frappe.get_doc({"doctype": "Role", "role_name": PRINT_ROLE}).insert()
        add_permission("Sales Invoice", PRINT_ROLE, ptype="read")
        rule = frappe.db.get_value(
            "Custom DocPerm", {"parent": "Sales Invoice", "role": PRINT_ROLE}
        )
        frappe.db.set_value("Custom DocPerm", rule, "print", 1)
        if not frappe.db.exists("POS Role", POS_ROLE):
            frappe.get_doc(
                {
                    "doctype": "POS Role",
                    "role_name": POS_ROLE,
                    "permissions": [
                        {"permission": "print_draft_invoice", "enabled": 1},
                        {"permission": "allow_reprint_invoice", "enabled": 0},
                    ],
                }
            ).insert()
        cls.original_pos_role = (
            frappe.get_doc("POS Profile", cls.a["profile"]).applicable_for_users[0].get("pos_role")
        )
        for user in (cls.a["user"], cls.b["user"], MANAGER):
            doc = frappe.get_doc("User", user)
            cls.original_users[user] = (
                doc.api_key,
                doc.get_password("api_secret", raise_exception=False),
                [row.role for row in doc.roles],
                doc.enabled,
            )
            doc.api_key = secrets.token_hex(16)
            doc.api_secret = secrets.token_hex(24)
            cls.tokens[user] = f"token {doc.api_key}:{doc.api_secret}"
            doc.enabled = 1
            for role in ("Sales User",) if user == MANAGER else ("Sales User", "OMP Cashier"):
                # Cashiers must hold the native roles whose reads the hooks restrict.
                if role not in [row.role for row in doc.roles]:
                    doc.append("roles", {"role": role})
            doc.save()
        frappe.get_doc("User", cls.a["user"]).add_roles(PRINT_ROLE)
        if not frappe.db.exists("Price List", "OMP HTTP COP"):
            frappe.get_doc(
                {
                    "doctype": "Price List",
                    "price_list_name": "OMP HTTP COP",
                    "currency": "COP",
                    "selling": 1,
                }
            ).insert()
        if not frappe.db.exists("Item", "OMP-HTTP-SERVICE"):
            frappe.get_doc(
                {
                    "doctype": "Item",
                    "item_code": "OMP-HTTP-SERVICE",
                    "item_name": "Servicio ficticio HTTP",
                    "item_group": "Services",
                    "stock_uom": "Nos",
                    "is_stock_item": 0,
                }
            ).insert()
        if not frappe.db.exists("Customer", "OMP HTTP Customer"):
            frappe.get_doc(
                {
                    "doctype": "Customer",
                    "customer_name": "OMP HTTP Customer",
                    "customer_type": "Individual",
                    "customer_group": "Commercial",
                    "territory": "All Territories",
                }
            ).insert()
        year = frappe.utils.nowdate()[:4]
        if not frappe.db.exists("Fiscal Year", "OMP HTTP " + year):
            frappe.get_doc(
                {
                    "doctype": "Fiscal Year",
                    "year": "OMP HTTP " + year,
                    "year_start_date": year + "-01-01",
                    "year_end_date": year + "-12-31",
                }
            ).insert()
        for fixture in (cls.a, cls.b):
            profile = frappe.get_doc("POS Profile", fixture["profile"])
            fixture.update(company=profile.company, warehouse=profile.warehouse)
            fixture["brand"] = frappe.db.get_value(
                "OMP Business Brand", {"pos_profile": profile.name, "enabled": 1}
            )
            existing = frappe.db.get_value(
                "Sales Invoice", {"pos_notes": "OMP HTTP security fixture " + profile.name}
            )
            fixture["invoice"] = existing or cls.invoice(profile).name
            existing_pos = frappe.db.get_value(
                "POS Invoice", {"pos_notes": "OMP HTTP security fixture " + profile.name}
            )
            if existing_pos:
                fixture["pos_invoice"] = existing_pos
                continue  # Reusing a fixture must not change a site's live invoice mode.
            mode = frappe.get_single("POS Settings")
            original_mode = mode.invoice_type
            mode.invoice_type = "POS Invoice"
            mode.save()
            opening = None
            try:
                existing_pos = frappe.db.get_value(
                    "POS Invoice", {"pos_notes": "OMP HTTP security fixture " + profile.name}
                )
                if not existing_pos:
                    opening = frappe.get_doc(
                        {
                            "doctype": "POS Opening Entry",
                            "period_start_date": frappe.utils.now_datetime(),
                            "company": profile.company,
                            "pos_profile": profile.name,
                            "user": fixture["user"],
                            "balance_details": [
                                {
                                    "mode_of_payment": profile.payments[0].mode_of_payment,
                                    "opening_amount": 0,
                                }
                            ],
                        }
                    ).insert()
                    opening.submit()
                fixture["pos_invoice"] = existing_pos or cls.invoice(profile, "POS Invoice").name
            finally:
                if opening and opening.docstatus == 1:
                    opening.cancel()
                mode.invoice_type = original_mode
                mode.save()
        cls.other_profile = "AAA OMP HTTP Other Profile"
        if not frappe.db.exists("POS Profile", cls.other_profile):
            profile = frappe.copy_doc(frappe.get_doc("POS Profile", cls.a["profile"]))
            profile.name = cls.other_profile
            profile.set("applicable_for_users", [])
            profile.insert()
        if not frappe.db.exists("OMP Business Brand", {"pos_profile": cls.other_profile}):
            frappe.get_doc(
                {
                    "doctype": "OMP Business Brand",
                    "display_name": "OMP HTTP Restricted Brand",
                    "company": cls.a["company"],
                    "warehouse": cls.a["warehouse"],
                    "pos_profile": cls.other_profile,
                    "printer_profile": "generic-58",
                    "allowed_users": [],
                }
            ).insert()
        profile = frappe.get_doc("POS Profile", cls.other_profile)
        cls.other_invoice = (
            frappe.db.get_value(
                "Sales Invoice", {"pos_notes": "OMP HTTP security fixture " + profile.name}
            )
            or cls.invoice(profile).name
        )
        frappe.db.commit()
        frappe.clear_cache()

    @staticmethod
    def invoice(profile, doctype="Sales Invoice"):
        company = frappe.get_doc("Company", profile.company)
        return frappe.get_doc(
            {
                "doctype": doctype,
                "customer": "OMP HTTP Customer",
                "company": profile.company,
                "currency": "COP",
                "conversion_rate": 1,
                "selling_price_list": "OMP HTTP COP",
                "price_list_currency": "COP",
                "plc_conversion_rate": 1,
                "ignore_pricing_rule": 1,
                "is_pos": 1,
                "pos_profile": profile.name,
                "set_warehouse": profile.warehouse,
                "update_stock": 0,
                "debit_to": company.default_receivable_account,
                "items": [
                    {
                        "item_code": "OMP-HTTP-SERVICE",
                        "qty": 1,
                        "rate": 1000,
                        "income_account": company.default_income_account,
                        "cost_center": company.cost_center,
                    }
                ],
                "payments": [
                    {"mode_of_payment": profile.payments[0].mode_of_payment, "amount": 1000}
                ],
                "pos_notes": "OMP HTTP security fixture " + profile.name,
            }
        ).insert()

    @classmethod
    def cleanup(cls):
        frappe.set_user("Administrator")
        frappe.db.rollback()
        for user, (key, secret, roles, enabled) in cls.original_users.items():
            if not frappe.db.exists("User", user):
                continue  # A failed class setup may have rolled back this new fixture.
            doc = frappe.get_doc("User", user)
            doc.api_key, doc.api_secret, doc.enabled = key, secret, enabled
            doc.set("roles", [{"role": role} for role in roles])
            if user == MANAGER and cls.manager_created:
                doc.enabled = 0
            doc.save()
            if not secret:
                remove_encrypted_password("User", user, "api_secret")
        if hasattr(cls, "original_pos_role"):
            profile = frappe.get_doc("POS Profile", cls.a["profile"])
            profile.applicable_for_users[0].pos_role = cls.original_pos_role
            profile.save()
        if hasattr(cls, "other_profile"):
            profile = frappe.get_doc("POS Profile", cls.other_profile)
            profile.set("applicable_for_users", [])
            profile.save()
        added = (
            set(frappe.get_all("Custom DocPerm", filters={"parent": "Sales Invoice"}, pluck="name"))
            - cls.prior_perms
        )
        for name in added:
            frappe.delete_doc("Custom DocPerm", name)
        frappe.db.commit()
        frappe.clear_cache()
        frappe.destroy()

    def setUp(self):
        frappe.set_user("Administrator")
        frappe.db.rollback()
        for fixture in (self.a, self.b):
            frappe.db.set_value("OMP Business Brand", fixture["brand"], "enabled", 1)
            frappe.db.set_value("POS Profile", fixture["profile"], "disabled", 0)
            frappe.db.set_value(
                "POS Invoice", fixture["pos_invoice"], "print_count", 0, update_modified=False
            )
            frappe.db.set_value(
                "Sales Invoice",
                fixture["invoice"],
                {
                    "print_count": 0,
                    "docstatus": 0,
                    "company": fixture["company"],
                    "set_warehouse": fixture["warehouse"],
                },
                update_modified=False,
            )
        profile = frappe.get_doc("POS Profile", self.a["profile"])
        profile.applicable_for_users[0].pos_role = POS_ROLE
        profile.save()
        # The upstream global role lookup sees Manager on another profile first.
        # The adapter must still enforce the current invoice profile's print role.
        other = frappe.get_doc("POS Profile", self.other_profile)
        other.set("applicable_for_users", [{"user": self.a["user"], "pos_role": "Manager"}])
        other.save()
        role = frappe.get_doc("POS Role", POS_ROLE)
        for row in role.permissions:
            row.enabled = int(row.permission == "print_draft_invoice")
        role.save()
        frappe.get_doc("User", self.a["user"]).add_roles(PRINT_ROLE)
        frappe.db.commit()
        frappe.clear_cache()

    def call(self, method, payload=None, *, user=None, verb="GET", version="v1"):
        prefix = "/api/method/" if version == "v1" else "/api/v2/method/"
        headers = {"Host": OPTIONS.site}
        if user:
            headers["Authorization"] = self.tokens[user]
        options = {"params": payload} if verb == "GET" else {"json": payload}
        response = requests.request(
            verb, OPTIONS.base_url + prefix + method, headers=headers, timeout=30, **options
        )
        if response.status_code >= 500:
            self.fail(f"HTTP {response.status_code}: {response.json().get('exception', 'unknown')}")
        return response

    def counter(self, name=None):
        frappe.db.rollback()
        return frappe.db.get_value("Sales Invoice", name or self.a["invoice"], "print_count") or 0

    def test_receipt_context_v1_v2_allows_only_own_brand(self):
        for version in ("v1", "v2"):
            for own, other in ((self.a, self.b), (self.b, self.a)):
                with self.subTest(version=version, user=own["user"]):
                    response = self.call(
                        "xpos.api.print_formats.get_receipt_context",
                        {"pos_profile": own["profile"]},
                        user=own["user"],
                        version=version,
                    )
                    self.assertEqual(response.status_code, 200)
                    data = response.json().get("message", response.json().get("data"))
                    self.assertEqual(data["company_name"], own["company"])
                    self.assertEqual(
                        self.call(
                            "xpos.api.print_formats.get_receipt_context",
                            {"pos_profile": other["profile"]},
                            user=own["user"],
                            version=version,
                        ).status_code,
                        403,
                    )

    def test_guest_and_direct_adapter_url_are_restricted(self):
        for version in ("v1", "v2"):
            for method in (
                "xpos.api.print_formats.get_receipt_context",
                "open_multi_pos.xpos_security.get_receipt_context",
            ):
                self.assertEqual(
                    self.call(
                        method, {"pos_profile": self.a["profile"]}, version=version
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    self.call(
                        method,
                        {"pos_profile": self.b["profile"]},
                        user=self.a["user"],
                        version=version,
                    ).status_code,
                    403,
                )

    def test_same_company_does_not_grant_other_brand(self):
        doc = frappe.get_doc("Sales Invoice", self.other_invoice)
        self.assertFalse(frappe.has_permission("Sales Invoice", doc=doc, user=self.a["user"]))
        self.assertEqual(
            self.call(
                "xpos.api.invoices.get_invoice_details",
                {"invoice_name": self.other_invoice, "doctype": "Sales Invoice"},
                user=self.a["user"],
            ).status_code,
            403,
        )
        self.assertEqual(
            self.call(
                "xpos.api.print_formats.get_receipt_context",
                {"pos_profile": self.other_profile},
                user=self.a["user"],
            ).status_code,
            403,
        )

    def test_native_document_list_and_print_routes_respect_brand_scope(self):
        headers = {"Host": OPTIONS.site, "Authorization": self.tokens[self.a["user"]]}
        for doctype, name in (
            ("Sales Invoice", self.other_invoice),
            ("Sales Invoice", self.b["invoice"]),
            ("POS Invoice", self.b["pos_invoice"]),
        ):
            for prefix in ("/api/resource/", "/api/v2/document/"):
                with self.subTest(doctype=doctype, prefix=prefix):
                    response = requests.get(
                        OPTIONS.base_url
                        + prefix
                        + quote(doctype, safe="")
                        + "/"
                        + quote(name, safe=""),
                        headers=headers,
                        timeout=30,
                    )
                    self.assertEqual(response.status_code, 403)
        response = self.call(
            "frappe.client.get_list",
            {"doctype": "Sales Invoice", "fields": '["name"]', "limit_page_length": 100},
            user=self.a["user"],
        )
        self.assertEqual(response.status_code, 200)
        names = {row["name"] for row in response.json()["message"]}
        self.assertIn(self.a["invoice"], names)
        self.assertNotIn(self.other_invoice, names)
        self.assertNotIn(self.b["invoice"], names)
        rendered = self.call(
            "frappe.www.printview.get_html_and_style",
            {"doc": "Sales Invoice", "name": self.other_invoice, "print_format": "Standard"},
            user=self.a["user"],
        )
        self.assertEqual(rendered.status_code, 403)
        for path, params in (
            (
                "/printview",
                {"doctype": "Sales Invoice", "name": self.other_invoice, "format": "Standard"},
            ),
            (
                "/printview.html",
                {"doctype": "Sales Invoice", "name": self.other_invoice, "format": "Standard"},
            ),
            ("/Sales%20Invoice/" + quote(self.other_invoice, safe=""), {}),
            ("/Sales%20Invoice/" + quote(self.other_invoice, safe="") + ".html", {}),
        ):
            for accept in ("application/json", "text/html"):
                with self.subTest(path=path, accept=accept):
                    response = requests.get(
                        OPTIONS.base_url + path,
                        params=params,
                        headers={**headers, "Accept": accept},
                        timeout=30,
                    )
                    self.assertEqual(response.status_code, 403)
                    self.assertNotIn("OMP HTTP Customer", response.text)

    def test_native_catalog_customers_reports_and_sales_documents_respect_brand_scope(self):
        a, b, user = self.a, self.b, self.a["user"]
        profiles = {a["profile"]: None, b["profile"]: None}
        created = {"Bin": [], "Item": [], "Customer": []}
        suffix = secrets.token_hex(3)  # Survives leftovers from an interrupted run.

        def restore():
            frappe.set_user("Administrator")
            frappe.db.rollback()
            for profile, customer in profiles.items():
                frappe.db.set_value("POS Profile", profile, "customer", customer)
            for doctype in ("Bin", "Item", "Customer"):
                for name in created[doctype]:
                    frappe.delete_doc(doctype, name, force=1)
            frappe.db.commit()
            frappe.clear_cache()

        self.addCleanup(restore)
        for profile in profiles:
            profiles[profile] = frappe.db.get_value("POS Profile", profile, "customer")
        counters = {}
        for key, fixture in (("a", a), ("b", b)):
            counters[key] = frappe.get_doc(
                {
                    "doctype": "Customer",
                    "customer_name": "OMP HTTP Counter " + key.upper() + " " + suffix,
                    "customer_type": "Individual",
                    "customer_group": "Commercial",
                    "territory": "All Territories",
                }
            ).insert()
            created["Customer"].append(counters[key].name)
            frappe.db.set_value("POS Profile", fixture["profile"], "customer", counters[key].name)
        items = {}
        for key, brand in (("a", a["brand"]), ("b", b["brand"]), ("free", None)):
            items[key] = frappe.get_doc(
                {
                    "doctype": "Item",
                    "item_code": "OMP-HTTP-CAT-" + key.upper() + "-" + suffix,
                    "item_name": "Catalogo ficticio " + key,
                    "item_group": "Services",
                    "stock_uom": "Nos",
                    "is_stock_item": int(brand is None),  # Bin fixtures use the free item.
                    "omp_business_brand": brand,
                }
            ).insert()
            created["Item"].append(items[key].name)
        for fixture in (a, b):
            bin_doc = frappe.get_doc(
                {
                    "doctype": "Bin",
                    "item_code": items["free"].name,
                    "warehouse": fixture["warehouse"],
                }
            ).insert()
            created["Bin"].append(bin_doc.name)
        frappe.db.commit()
        frappe.clear_cache()
        headers = {"Host": OPTIONS.site, "Authorization": self.tokens[user]}

        def resource(doctype, name, verb="GET", **options):
            path = "/api/resource/" + quote(doctype, safe="") + "/" + quote(name, safe="")
            return requests.request(
                verb, OPTIONS.base_url + path, headers=headers, timeout=30, **options
            )

        def listing(doctype, filters, fields):
            response = self.call(
                "frappe.client.get_list",
                {
                    "doctype": doctype,
                    "filters": json.dumps(filters),
                    "fields": json.dumps(fields),
                    "limit_page_length": 100,
                },
                user=user,
            )
            self.assertEqual(response.status_code, 200)
            rows = response.json()["message"]
            for prefix in ("/api/resource/", "/api/v2/document/"):
                native = requests.get(
                    OPTIONS.base_url + prefix + quote(doctype, safe=""),
                    headers=headers,
                    params={
                        "fields": json.dumps(fields),
                        "filters": json.dumps(filters),
                        "limit": 100,
                    },
                    timeout=30,
                )
                self.assertEqual(native.status_code, 200, native.text[-1000:])
                self.assertEqual(
                    {row["name"]: row for row in native.json()["data"]},
                    {row["name"]: row for row in rows},
                )
            return rows

        rows = listing("Item", [["item_code", "like", f"OMP-HTTP-CAT-%-{suffix}"]], ["name"])
        self.assertEqual({row["name"] for row in rows}, {items["a"].name, items["free"].name})
        for key, status in (("a", 200), ("free", 200), ("b", 403)):
            self.assertEqual(resource("Item", items[key].name).status_code, status, key)
        rows = listing("Customer", [["name", "in", [c.name for c in counters.values()]]], ["name"])
        self.assertEqual({row["name"] for row in rows}, {counters["a"].name})
        self.assertEqual(resource("Customer", counters["a"].name).status_code, 200)
        self.assertEqual(resource("Customer", counters["b"].name).status_code, 403)
        update = resource("Customer", counters["a"].name, "PUT", json={"mobile_no": "0"})
        self.assertEqual(update.status_code, 403)
        rows = listing("Bin", [["item_code", "=", items["free"].name]], ["name", "warehouse"])
        self.assertEqual({row["warehouse"] for row in rows}, {a["warehouse"]})
        for doctype in ("Sales Order", "Quotation", "Delivery Note"):
            with self.subTest(doctype=doctype):
                self.assertEqual(listing(doctype, [], ["name"]), [])
                doc = frappe.new_doc(doctype)
                self.assertFalse(frappe.has_permission(doctype, doc=doc, user=user))
                self.assertTrue(frappe.has_permission(doctype, doc=doc, user=MANAGER))
        report = {"report_name": "Item-wise Sales History"}
        for method, payload, version in (
            ("frappe.desk.query_report.run", report, "v1"),
            ("frappe.desk.query_report.run", report, "v2"),
            ("frappe.desk.query_report.background_enqueue_run", report, "v1"),
            ("frappe.desk.query_report.export_query", report, "v1"),
            ("frappe.desk.reportview.export_query", {"doctype": "Item"}, "v1"),
        ):
            with self.subTest(method=method, version=version):
                response = self.call(method, payload, user=user, version=version)
                self.assertEqual(response.status_code, 403)
                # Proves the OpenMultiPOS gate denied it, not a native permission.
                self.assertIn("no está habilitada", response.text)

    def cashier_http_fixture(self, *, attachments=False):
        marker = "OMP-HTTP-SURFACE-" + secrets.token_hex(6)
        created = []

        def restore():
            frappe.set_user("Administrator")
            frappe.db.rollback()
            for doctype, name in reversed(created):
                if frappe.db.exists(doctype, name):
                    frappe.delete_doc(doctype, name, force=1)
            for name in frappe.get_all(
                "Comment", filters={"content": ["like", "%" + marker + "%"]}, pluck="name"
            ):
                frappe.delete_doc("Comment", name, force=1)
            frappe.db.commit()
            frappe.clear_cache()

        self.addCleanup(restore)

        def insert(doctype, **fields):
            doc = frappe.get_doc({"doctype": doctype, **fields}).insert()
            created.append((doctype, doc.name))
            return doc

        customer = insert(
            "Customer",
            customer_name=marker,
            customer_type="Individual",
            customer_group="Commercial",
            territory="All Territories",
        )
        links = [{"link_doctype": "Customer", "link_name": customer.name}]
        records = {
            "Address": insert(
                "Address",
                address_title=marker,
                address_type="Billing",
                address_line1=marker,
                city="Ciudad ficticia",
                country="Colombia",
                links=links,
            ),
            "Contact": insert("Contact", first_name=marker, links=links),
            "Price List": insert(
                "Price List", price_list_name=marker, currency="COP", selling=1, enabled=1
            ),
        }
        parents = {"address": ("Address", records["Address"].name)}
        if attachments:
            for key, fixture in (("own_item", self.a), ("foreign_item", self.b)):
                records[key] = insert(
                    "Item",
                    item_code=marker + "-" + key,
                    item_name=marker + "-" + key,
                    item_group="Services",
                    stock_uom="Nos",
                    is_stock_item=0,
                    omp_business_brand=fixture["brand"],
                )
                parents[key] = ("Item", records[key].name)
            parents.update(
                own_invoice=("Sales Invoice", self.a["invoice"]),
                own_pos_invoice=("POS Invoice", self.a["pos_invoice"]),
                foreign_invoice=("Sales Invoice", self.b["invoice"]),
                foreign_pos_invoice=("POS Invoice", self.b["pos_invoice"]),
                contact=("Contact", records["Contact"].name),
                price_list=("Price List", records["Price List"].name),
                unlinked=(None, None),
                missing=("Item", records["own_item"].name),
            )
        files, contents = {}, {}
        for key, (doctype, name) in parents.items():
            contents[key] = (marker + ":" + key).encode()
            files[key] = insert(
                "File",
                file_name=marker + "-" + key + ".txt",
                content=contents[key],
                is_private=1,
                attached_to_doctype=doctype,
                attached_to_name=name,
            )
        if attachments:
            frappe.db.set_value(
                "File", files["missing"].name, "attached_to_name", marker + "-missing"
            )
            duplicate = files["own_item"].create_attachment_copy("Address", records["Address"].name)
            created.append(("File", duplicate.name))
            files["disallowed_duplicate"] = duplicate
        records["File"] = files["address"]
        frappe.db.commit()
        frappe.clear_cache()
        return marker, customer, records, files, contents

    def test_cashier_native_metadata_surface_is_denied(self):
        marker, customer, records, _, _ = self.cashier_http_fixture()
        headers = {"Host": OPTIONS.site, "Authorization": self.tokens[self.a["user"]]}
        manager_headers = {**headers, "Authorization": self.tokens[MANAGER]}

        def denied(response):
            self.assertEqual(response.status_code, 403)
            self.assertNotIn(marker, response.text)

        for doctype in ("File", "Address", "Contact", "Price List"):
            name = records[doctype].name
            filters = {"filters": json.dumps([["name", "=", name]]), "fields": '["name"]'}
            for prefix in ("/api/resource/", "/api/v1/resource/", "/api/v2/document/"):
                collection = OPTIONS.base_url + prefix + quote(doctype, safe="")
                document = collection + "/" + quote(name, safe="")
                with self.subTest(doctype=doctype, prefix=prefix):
                    control = requests.get(document, headers=manager_headers, timeout=30)
                    self.assertEqual(control.status_code, 200)
                    self.assertIn(name, control.text)
                    control = requests.get(
                        collection, params=filters, headers=manager_headers, timeout=30
                    )
                    self.assertEqual(control.status_code, 200)
                    self.assertIn(name, control.text)
                    denied(requests.get(document, headers=headers, timeout=30))
                    denied(requests.get(collection, params=filters, headers=headers, timeout=30))
                    denied(
                        requests.post(
                            collection, json={"doctype": doctype}, headers=headers, timeout=30
                        )
                    )
                    for verb in ("PUT", "PATCH") if "/v2/" in prefix else ("PUT",):
                        denied(
                            requests.request(
                                verb,
                                document,
                                json={"name": name},
                                headers=headers,
                                timeout=30,
                            )
                        )
                    denied(requests.delete(document, headers=headers, timeout=30))
            for version in ("v1", "v2"):
                denied(
                    self.call(
                        "frappe.client.get_list",
                        {"doctype": doctype, **filters},
                        user=self.a["user"],
                        version=version,
                    )
                )
            self.assertTrue(frappe.db.exists(doctype, name))
        for method, payload in (
            ("frappe.desk.search.search_link", {"doctype": "Address", "txt": marker}),
            (
                "frappe.contacts.doctype.contact.contact.get_contact_details",
                {"contact": records["Contact"].name},
            ),
            (
                "frappe.contacts.doctype.contact.contact.download_vcard",
                {"contact": records["Contact"].name},
            ),
            (
                "frappe.contacts.doctype.address.address.get_default_address",
                {"doctype": "Customer", "name": customer.name},
            ),
            (
                "frappe.contacts.doctype.address.address.get_address_display",
                {"address_dict": records["Address"].name},
            ),
            ("frappe.core.api.file.get_files_by_search_text", {"text": marker}),
            (
                "frappe.core.api.file.get_attached_images",
                {"doctype": "Address", "names": json.dumps([records["Address"].name])},
            ),
            (
                "frappe.desk.query_report.get_data_for_custom_field",
                {
                    "doctype": "Price List",
                    "field": "currency",
                    "names": json.dumps([records["Price List"].name]),
                },
            ),
            ("frappe.desk.query_report.run", {"report_name": "Item-wise Sales History"}),
            (
                "frappe.core.doctype.data_export.exporter.export_data",
                {"doctype": "Price List", "with_data": 1},
            ),
        ):
            for version in ("v1", "v2"):
                with self.subTest(method=method, version=version):
                    denied(self.call(method, payload, user=self.a["user"], version=version))
        control = self.call(
            "frappe.contacts.doctype.contact.contact.get_contact_details",
            {"contact": records["Contact"].name},
            user=MANAGER,
        )
        self.assertEqual(control.status_code, 200)
        self.assertEqual(control.json()["message"]["contact_person"], records["Contact"].name)
        control = self.call(
            "frappe.contacts.doctype.address.address.get_default_address",
            {"doctype": "Customer", "name": customer.name},
            user=MANAGER,
        )
        self.assertEqual(control.status_code, 200)
        self.assertEqual(control.json()["message"], records["Address"].name)

    def test_cashier_private_attachments_require_current_allowed_parent(self):
        marker, _, records, files, contents = self.cashier_http_fixture(attachments=True)
        from frappe import share

        for key in ("foreign_item", "address", "unlinked", "missing"):
            frappe.db.set_value("File", files[key].name, "owner", self.a["user"])
        for key in ("foreign_invoice", "contact", "price_list"):
            share.add("File", files[key].name, user=self.a["user"], read=1, notify=0)
        duplicate = files["disallowed_duplicate"]
        frappe.db.commit()
        frappe.clear_cache()

        def downloads(file, *, user):
            headers = {"Host": OPTIONS.site}
            if user:
                headers["Authorization"] = self.tokens[user]
            for params in ({}, {"fid": file.name}):
                yield requests.get(
                    OPTIONS.base_url + file.file_url, params=params, headers=headers, timeout=30
                )
            yield self.call("download_file", {"file_url": file.file_url}, user=user)
            for version, methods in (
                (
                    "v1",
                    (
                        "frappe.handler.download_file",
                        "frappe.utils.file_manager.download_file",
                        "frappe.core.doctype.file.file.download_file",
                    ),
                ),
                ("v2", ("frappe.handler.download_file",)),
            ):
                for method in methods:
                    yield self.call(method, {"file_url": file.file_url}, user=user, version=version)

        for key in ("own_item", "own_invoice", "own_pos_invoice"):
            for response in downloads(files[key], user=self.a["user"]):
                with self.subTest(file=key, url=response.url):
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.content, contents[key])
        for key in (
            "foreign_item",
            "foreign_invoice",
            "foreign_pos_invoice",
            "address",
            "contact",
            "price_list",
            "unlinked",
            "missing",
        ):
            for response in downloads(files[key], user=self.a["user"]):
                with self.subTest(file=key, url=response.url):
                    self.assertEqual(response.status_code, 403)
                    self.assertNotIn(contents[key], response.content)
                    self.assertNotIn(marker, response.text)
        for key in ("foreign_item", "address", "contact", "price_list"):
            control = self.call(
                "frappe.handler.download_file", {"file_url": files[key].file_url}, user=MANAGER
            )
            self.assertEqual(control.status_code, 200)
            self.assertEqual(control.content, contents[key])
        headers = {"Host": OPTIONS.site, "Authorization": self.tokens[self.a["user"]]}
        for fid in (duplicate.name, files["address"].name, marker + "-missing"):
            response = requests.get(
                OPTIONS.base_url + files["own_item"].file_url,
                params={"fid": fid},
                headers=headers,
                timeout=30,
            )
            self.assertEqual(response.status_code, 403)
            self.assertNotIn(contents["own_item"], response.content)
        for response in downloads(files["own_item"], user=None):
            self.assertEqual(response.status_code, 403)
            self.assertNotIn(contents["own_item"], response.content)
        try:
            frappe.db.set_value("OMP Business Brand", self.a["brand"], "enabled", 0)
            frappe.db.commit()
            for response in downloads(files["own_item"], user=self.a["user"]):
                self.assertEqual(response.status_code, 403)
        finally:
            frappe.db.set_value("OMP Business Brand", self.a["brand"], "enabled", 1)
            frappe.db.commit()

    def test_cashier_unknown_http_surface_is_closed(self):
        headers = {"Host": OPTIONS.site, "Authorization": self.tokens[self.a["user"]]}
        invoice = quote(self.a["invoice"], safe="")
        marker = "OMP-HTTP-UNKNOWN-" + secrets.token_hex(6)

        def denied(response):
            self.assertEqual(response.status_code, 403)
            self.assertNotIn(marker, response.text)

        for version in ("v1", "v2"):
            for method, payload in (
                ("open_multi_pos.cashier.future_unreviewed", {"text": marker}),
                ("frappe.client.get_count", {"doctype": "Item"}),
                ("run_doc_method", {"dt": "Sales Invoice", "dn": self.a["invoice"]}),
                (
                    "frappe.handler.run_doc_method",
                    {"dt": "Sales Invoice", "dn": self.a["invoice"]},
                ),
                (
                    "frappe.client.get_list",
                    {"doctype": "Item", "fields": '["name"]', "expand": '["item_group"]'},
                ),
                (
                    "frappe.client.get_list",
                    {"doctype": "Item", "fields": '["item_group.item_group_name"]'},
                ),
            ):
                with self.subTest(method=method, version=version):
                    denied(self.call(method, payload, user=self.a["user"], version=version))
            control = self.call(
                "frappe.client.get_count", {"doctype": "Item"}, user=MANAGER, version=version
            )
            self.assertEqual(control.status_code, 200)
            self.assertIsInstance(control.json().get("message", control.json().get("data")), int)
        for path, params in (
            ("/api/v2/document/Sales%20Invoice/" + invoice + "/copy", {}),
            ("/api/v2/document/Sales%20Invoice/" + invoice + "/method/get_doc_before_save", {}),
            ("/api/v2/doctype/Sales%20Invoice/count", {}),
            ("/api/v2/doctype/Sales%20Invoice/meta", {}),
            ("/api/v2/method/Address/get_default_address", {"doctype": "Customer", "name": marker}),
            ("/api/resource/User/" + quote(self.a["user"], safe=""), {}),
            ("/api/v2/document/User/" + quote(self.a["user"], safe=""), {}),
            ("/api/resource/DocType/Sales%20Invoice", {}),
            ("/api/resource/Sales%20Invoice/" + invoice, {"run_method": ""}),
            ("/api/v1/resource/Sales%20Invoice/" + invoice, {"run_method": "get_doc_before_save"}),
            ("/api/resource/Sales%20Invoice/" + invoice, {"expand_links": 1}),
            ("/api/resource/Item", {"fields": '["item_group.item_group_name"]'}),
            ("/api/v2/document/Item", {"fields": '["item_group.item_group_name"]'}),
            ("/api/resource/Item", {"limit_page_length": 0}),
            ("/api/v2/document/Item", {"limit": 101}),
            ("/api/resource/Item", {"fields": "false"}),
            ("/api/v2/document/Item", {"fields": "{}"}),
            ("/Sales%20Invoice", {}),
            ("/api/resource/Item", {"fields": '["name"]', "expand": '["item_group"]'}),
        ):
            with self.subTest(path=path, params=params):
                denied(
                    requests.get(
                        OPTIONS.base_url + path, params=params, headers=headers, timeout=30
                    )
                )
        allowed = {"cmd": "frappe.client.get_list", "doctype": "Item", "fields": '["name"]'}
        for path in (
            "/api/method/frappe.client.get_count",
            "/api/v2/document/Price%20List",
            "/private/files/" + marker + ".txt",
        ):
            response = requests.post(
                OPTIONS.base_url + path, json=allowed, headers=headers, timeout=30
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("message", response.json())
        for cmd in ("frappe.client.get_count", " "):
            denied(
                requests.post(
                    OPTIONS.base_url + "/api/method/open_multi_pos.cashier.terminals",
                    json={"cmd": cmd, "text": marker},
                    headers=headers,
                    timeout=30,
                )
            )
        redirect = requests.get(
            OPTIONS.base_url + "/omp", headers=headers, allow_redirects=False, timeout=30
        )
        self.assertIn(redirect.status_code, (301, 302, 303, 307, 308))
        self.assertEqual(redirect.headers["Location"], "/omp_pos")

    def test_native_dashboard_chart_routes_are_denied_to_cashiers(self):
        method = "frappe.desk.doctype.dashboard_chart.dashboard_chart.get"
        chart = {
            "name": "OMP HTTP chart " + secrets.token_hex(6),
            "document_type": "Sales Invoice",
            "chart_type": "Count",
            "type": "Line",
            "based_on": "posting_date",
            "timespan": "Last Year",
            "time_interval": "Daily",
            "filters_json": json.dumps([["name", "=", self.b["invoice"]]]),
        }
        cache_key = "chart-data:" + chart["name"]
        cached = {"labels": [self.b["invoice"]], "datasets": [{"values": [1]}]}
        frappe.cache.set_value(cache_key, json.dumps(cached))
        self.addCleanup(frappe.cache.delete_value, cache_key)
        payload = {"chart": json.dumps(chart)}
        allowed = self.call(method, payload, user=MANAGER)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.json()["message"], cached)
        for user in (self.a["user"], self.b["user"]):
            headers = {"Host": OPTIONS.site, "Authorization": self.tokens[user]}
            for no_cache in (None, 1):
                data = {**payload, **({"no_cache": no_cache} if no_cache else {})}
                for path, args in (
                    ("/api/method/" + method, data),
                    ("/api/v2/method/" + method, data),
                    ("/", {**data, "cmd": method}),
                ):
                    for verb in ("GET", "POST"):
                        with self.subTest(user=user, no_cache=no_cache, path=path, verb=verb):
                            options = {"params": args} if verb == "GET" else {"json": args}
                            response = requests.request(
                                verb,
                                OPTIONS.base_url + path,
                                headers=headers,
                                timeout=30,
                                **options,
                            )
                            self.assertEqual(response.status_code, 403)
                            self.assertIn("no está habilitada", response.text)
                            self.assertNotIn(self.b["invoice"], response.text)

    def test_unassigned_format_is_rejected(self):
        self.assertEqual(
            self.call(
                "xpos.api.print_formats.get_receipt_context",
                {"pos_profile": self.a["profile"], "print_format": "XPOS PO A4"},
                user=self.a["user"],
            ).status_code,
            403,
        )

    def test_disabled_brand_or_profile_is_rejected(self):
        for doctype, name, field, value in (
            ("OMP Business Brand", self.a["brand"], "enabled", 0),
            ("POS Profile", self.a["profile"], "disabled", 1),
        ):
            frappe.db.set_value(doctype, name, field, value)
            frappe.db.commit()
            self.assertEqual(
                self.call(
                    "xpos.api.print_formats.get_receipt_context",
                    {"pos_profile": self.a["profile"]},
                    user=self.a["user"],
                ).status_code,
                403,
            )
            frappe.db.set_value(doctype, name, field, 1 - value)
            frappe.db.commit()

    def test_invoice_detail_read_checks_both_native_and_brand_scope(self):
        for version in ("v1", "v2"):
            self.assertEqual(
                self.call(
                    "xpos.api.invoices.get_invoice_details",
                    {"invoice_name": self.a["invoice"]},
                    user=self.a["user"],
                    version=version,
                ).status_code,
                200,
            )
            self.assertEqual(
                self.call(
                    "xpos.api.invoices.get_invoice_details",
                    {"invoice_name": self.b["invoice"], "doctype": "Sales Invoice"},
                    user=self.a["user"],
                    version=version,
                ).status_code,
                403,
            )
        self.assertEqual(
            self.call(
                "xpos.api.invoices.get_invoice_details",
                {"invoice_name": self.a["invoice"], "doctype": "User"},
                user=self.a["user"],
            ).status_code,
            403,
        )

    def test_pos_invoice_alias_checks_reads_and_print_tracking(self):
        for version in ("v1", "v2"):
            self.assertEqual(
                self.call(
                    "xpos.api.invoices.get_invoice_details",
                    {"invoice_name": self.a["pos_invoice"], "doctype": "POS Invoice"},
                    user=self.a["user"],
                    version=version,
                ).status_code,
                200,
            )
            self.assertEqual(
                self.call(
                    "xpos.api.print_formats.mark_invoice_printed",
                    {"doctype": "POS Invoice", "name": self.b["pos_invoice"]},
                    user=self.a["user"],
                    verb="POST",
                    version=version,
                ).status_code,
                403,
            )
            self.assertEqual(
                self.call(
                    "xpos.api.print_formats.mark_invoice_printed",
                    {"doctype": "POS Invoice", "name": self.a["pos_invoice"]},
                    user=MANAGER,
                    verb="POST",
                    version=version,
                ).status_code,
                200,
            )
        frappe.db.rollback()
        self.assertEqual(
            frappe.db.get_value("POS Invoice", self.b["pos_invoice"], "print_count") or 0, 0
        )
        self.assertEqual(
            frappe.db.get_value("POS Invoice", self.a["pos_invoice"], "print_count"), 2
        )

    def test_invoice_detail_respects_native_field_permission_levels(self):
        from frappe.custom.doctype.property_setter.property_setter import make_property_setter

        filters = {"doc_type": "Sales Invoice", "field_name": "remarks", "property": "permlevel"}
        prior = frappe.db.get_value("Property Setter", filters, ["name", "value"], as_dict=True)
        previous_remark = frappe.db.get_value("Sales Invoice", self.a["invoice"], "remarks")
        marker = "OMP HTTP restricted test note"
        make_property_setter("Sales Invoice", "remarks", "permlevel", 2, "Int")
        frappe.db.set_value("Sales Invoice", self.a["invoice"], "remarks", marker)
        frappe.db.commit()
        frappe.clear_cache(doctype="Sales Invoice")
        try:
            response = self.call(
                "xpos.api.invoices.get_invoice_details",
                {"invoice_name": self.a["invoice"], "doctype": "Sales Invoice"},
                user=self.a["user"],
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()["message"]
            self.assertNotEqual(data.get("remarks"), marker)
            self.assertEqual(data["grand_total"], 1000)
            self.assertEqual(data["items"][0]["item_code"], "OMP-HTTP-SERVICE")
        finally:
            if prior:
                frappe.db.set_value("Property Setter", prior.name, "value", prior.value)
            else:
                name = frappe.db.get_value("Property Setter", filters)
                if name:
                    frappe.delete_doc("Property Setter", name)
            frappe.db.set_value("Sales Invoice", self.a["invoice"], "remarks", previous_remark)
            frappe.db.commit()
            frappe.clear_cache(doctype="Sales Invoice")

    def test_revoked_profile_user_is_rejected_after_successful_read(self):
        self.assertEqual(
            self.call(
                "xpos.api.print_formats.get_receipt_context",
                {"pos_profile": self.a["profile"]},
                user=self.a["user"],
            ).status_code,
            200,
        )
        profile = frappe.get_doc("POS Profile", self.a["profile"])
        row = profile.applicable_for_users[0].name
        frappe.db.set_value("POS Profile User", row, "user", self.b["user"])
        frappe.db.commit()
        try:
            self.assertEqual(
                self.call(
                    "xpos.api.print_formats.get_receipt_context",
                    {"pos_profile": self.a["profile"]},
                    user=self.a["user"],
                ).status_code,
                403,
            )
        finally:
            frappe.db.set_value("POS Profile User", row, "user", self.a["user"])
            frappe.db.commit()

    def test_print_rejects_mismatched_warehouse_even_for_manager(self):
        frappe.db.set_value(
            "Sales Invoice", self.a["invoice"], "set_warehouse", self.b["warehouse"]
        )
        frappe.db.commit()
        self.assertEqual(
            self.call(
                "xpos.api.print_formats.mark_invoice_printed",
                {"doctype": "Sales Invoice", "name": self.a["invoice"]},
                user=MANAGER,
                verb="POST",
            ).status_code,
            403,
        )
        self.assertEqual(self.counter(), 0)

    def test_print_counter_requires_post_and_native_print_permission(self):
        payload = {"doctype": "Sales Invoice", "name": self.a["invoice"]}
        self.assertEqual(
            self.call(
                "xpos.api.print_formats.mark_invoice_printed", payload, user=MANAGER
            ).status_code,
            403,
        )
        frappe.get_doc("User", self.a["user"]).remove_roles(PRINT_ROLE)
        frappe.db.commit()
        frappe.clear_cache(user=self.a["user"])
        self.assertEqual(
            self.call(
                "xpos.api.print_formats.mark_invoice_printed",
                payload,
                user=self.a["user"],
                verb="POST",
            ).status_code,
            403,
        )
        self.assertEqual(self.counter(), 0)

    def test_print_counter_rejects_foreign_invoice_without_mutation(self):
        for version in ("v1", "v2"):
            response = self.call(
                "xpos.api.print_formats.mark_invoice_printed",
                {"doctype": "Sales Invoice", "name": self.b["invoice"]},
                user=self.a["user"],
                verb="POST",
                version=version,
            )
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.counter(self.b["invoice"]), 0)

    def test_first_print_and_scoped_reprint_permission(self):
        payload = {"doctype": "Sales Invoice", "name": self.a["invoice"]}
        self.assertEqual(
            self.call(
                "xpos.api.print_formats.mark_invoice_printed",
                payload,
                user=self.a["user"],
                verb="POST",
            ).status_code,
            200,
        )
        self.assertEqual(
            self.call(
                "xpos.api.print_formats.mark_invoice_printed",
                payload,
                user=self.a["user"],
                verb="POST",
                version="v2",
            ).status_code,
            403,
        )
        self.assertEqual(self.counter(), 1)

    def test_draft_print_permission_and_cancelled_document(self):
        row = frappe.db.get_value(
            "POS Role Permission", {"parent": POS_ROLE, "permission": "print_draft_invoice"}
        )
        frappe.db.set_value("POS Role Permission", row, "enabled", 0)
        frappe.db.commit()
        from xpos.api.auth import clear_role_permission_cache

        clear_role_permission_cache(POS_ROLE)
        payload = {"doctype": "Sales Invoice", "name": self.a["invoice"]}
        self.assertEqual(
            self.call(
                "xpos.api.print_formats.mark_invoice_printed",
                payload,
                user=self.a["user"],
                verb="POST",
            ).status_code,
            403,
        )
        frappe.db.set_value("Sales Invoice", self.a["invoice"], "docstatus", 2)
        frappe.db.commit()
        self.assertEqual(
            self.call(
                "xpos.api.print_formats.mark_invoice_printed", payload, user=MANAGER, verb="POST"
            ).status_code,
            403,
        )
        self.assertEqual(self.counter(), 0)

    def test_concurrent_first_print_cannot_bypass_reprint_permission(self):
        def send(_):
            return self.call(
                "xpos.api.print_formats.mark_invoice_printed",
                {"doctype": "Sales Invoice", "name": self.a["invoice"]},
                user=self.a["user"],
                verb="POST",
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = sorted(pool.map(send, range(2)))
        self.assertIn(statuses, ([200, 403], [200, 409]))
        # A confirmed aborted tracking request can be retried without printing paper.
        # It must now be rejected by the invoice profile's reprint permission.
        self.assertEqual(send(0), 403)
        self.assertEqual(self.counter(), 1)

    def test_authorized_concurrent_print_updates_are_not_lost(self):
        before = frappe.db.get_value("Sales Invoice", self.a["invoice"], "modified")

        def send(_):
            return self.call(
                "xpos.api.print_formats.mark_invoice_printed",
                {"doctype": "Sales Invoice", "name": self.a["invoice"]},
                user=MANAGER,
                verb="POST",
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(send, range(2)))
        self.assertIn(200, statuses)
        for status in statuses:
            if status == 409:
                self.assertEqual(send(0), 200)
            else:
                self.assertEqual(status, 200)
        self.assertEqual(self.counter(), 2)
        self.assertEqual(
            frappe.db.get_value("Sales Invoice", self.a["invoice"], "modified"), before
        )

    def test_unreviewed_invoice_routes_cannot_read_write_or_retry(self):
        before = {
            doctype: frappe.db.count(doctype)
            for doctype in ("Sales Invoice", "POS Invoice", "Stock Ledger Entry", "GL Entry")
        }
        for version in ("v1", "v2"):
            for method in BLOCKED_INVOICE_METHODS:
                for user in (self.a["user"], MANAGER):
                    with self.subTest(method=method, version=version, user=user):
                        response = self.call(
                            "xpos.api.invoices." + method,
                            {
                                "data": {
                                    "pos_profile": self.a["profile"],
                                    "name": self.b["invoice"],
                                    "warehouse": self.b["warehouse"],
                                    "local_id": "OMP-HTTP-RETRY",
                                },
                                "local_id": "OMP-HTTP-RETRY",
                                "name": self.b["invoice"],
                                "doctype": "Sales Invoice",
                            },
                            user=user,
                            verb="POST",
                            version=version,
                        )
                        self.assertEqual(response.status_code, 403)
        frappe.db.rollback()
        self.assertEqual(before, {doctype: frappe.db.count(doctype) for doctype in before})

    def test_pinned_invoice_api_inventory_has_no_unclassified_routes(self):
        path = OPTIONS.bench / "apps/xpos/xpos/api/invoices.py"
        functions = {
            node.name
            for node in ast.parse(path.read_text()).body
            if isinstance(node, ast.FunctionDef)
            and any(
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "whitelist"
                for decorator in node.decorator_list
            )
        }
        classified = set(BLOCKED_INVOICE_METHODS) | {"get_invoice_details", "fetch_exchange_rate"}
        self.assertEqual(functions, classified)
        for name in functions - {"fetch_exchange_rate"}:
            self.assertIn("xpos.api.invoices." + name, METHOD_OVERRIDES)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench", required=True, type=Path)
    parser.add_argument("--site", default="omp.localhost")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--tests", nargs="*")
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
        parser.error("Las credenciales de prueba solo se envían a una URL HTTP loopback sin ruta.")
    unittest.main(argv=[sys.argv[0], *(OPTIONS.tests or [])], verbosity=2)
