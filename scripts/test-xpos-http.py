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
            if user == MANAGER and "Sales User" not in [row.role for row in doc.roles]:
                doc.append("roles", {"role": "Sales User"})
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
