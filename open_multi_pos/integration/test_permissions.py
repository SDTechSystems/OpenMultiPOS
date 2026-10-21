"""Integration tests against real Frappe, ERPNext and MariaDB; no mocked permissions."""

import frappe
from frappe.client import get as get_document
from frappe.tests import IntegrationTestCase

from open_multi_pos.api import get_brand_context
from open_multi_pos.setup import ensure_cashier_role


class TestBrandPermissions(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not frappe.conf.get("allow_tests"):
            raise RuntimeError("Ejecutar exclusivamente en un sitio local de pruebas.")
        from erpnext.setup.setup_wizard.operations.install_fixtures import install

        install("Colombia")
        ensure_cashier_role()
        cls.fixtures = []
        for suffix in ("A", "B"):
            user = f"omp-cashier-{suffix.lower()}@example.invalid"
            if not frappe.db.exists("User", user):
                frappe.get_doc(
                    {
                        "doctype": "User",
                        "email": user,
                        "first_name": f"OMP Cajero {suffix}",
                        "send_welcome_email": 0,
                        "roles": [{"role": "Sales User"}, {"role": "OMP Cashier"}],
                    }
                ).insert()
            company_name = f"OMP Test Company {suffix}"
            if not frappe.db.exists("Company", company_name):
                frappe.get_doc(
                    {
                        "doctype": "Company",
                        "company_name": company_name,
                        "abbr": f"OMP{suffix}",
                        "country": "Colombia",
                        "default_currency": "COP",
                        "chart_of_accounts": "Standard",
                    }
                ).insert()
            company = frappe.get_doc("Company", company_name)
            warehouse = frappe.db.get_value(
                "Warehouse", {"company": company_name, "is_group": 0}, "name"
            )
            if not warehouse:
                warehouse = (
                    frappe.get_doc(
                        {
                            "doctype": "Warehouse",
                            "warehouse_name": f"OMP Test {suffix}",
                            "company": company_name,
                        }
                    )
                    .insert()
                    .name
                )
            cash_account = frappe.db.get_value(
                "Account", {"company": company_name, "account_type": "Cash", "is_group": 0}, "name"
            )
            payment_name = f"OMP Test Cash {suffix}"
            if not frappe.db.exists("Mode of Payment", payment_name):
                frappe.get_doc(
                    {
                        "doctype": "Mode of Payment",
                        "mode_of_payment": payment_name,
                        "type": "Cash",
                        "accounts": [{"company": company_name, "default_account": cash_account}],
                    }
                ).insert()
            profile_name = f"OMP Test Profile {suffix}"
            if not frappe.db.exists("POS Profile", profile_name):
                frappe.get_doc(
                    {
                        "doctype": "POS Profile",
                        "name": profile_name,
                        "company": company_name,
                        "warehouse": warehouse,
                        "currency": "COP",
                        "write_off_account": company.default_expense_account,
                        "write_off_cost_center": company.cost_center,
                        "payments": [{"mode_of_payment": payment_name, "default": 1}],
                        "applicable_for_users": [{"user": user, "default": 1}],
                    }
                ).insert()
            brand = frappe.db.get_value(
                "OMP Business Brand", {"display_name": f"OMP Test Brand {suffix}"}
            )
            if not brand:
                brand = (
                    frappe.get_doc(
                        {
                            "doctype": "OMP Business Brand",
                            "display_name": f"OMP Test Brand {suffix}",
                            "company": company_name,
                            "warehouse": warehouse,
                            "pos_profile": profile_name,
                            "printer_profile": "generic-58",
                            "qr_url": "https://example.com/demo",
                            "allowed_users": [{"user": user}],
                        }
                    )
                    .insert()
                    .name
                )
            if not frappe.db.exists(
                "User Permission", {"user": user, "allow": "Company", "for_value": company_name}
            ):
                frappe.get_doc(
                    {
                        "doctype": "User Permission",
                        "user": user,
                        "allow": "Company",
                        "for_value": company_name,
                        "apply_to_all_doctypes": 1,
                    }
                ).insert()
            cls.fixtures.append(
                frappe._dict(
                    user=user,
                    company=company_name,
                    warehouse=warehouse,
                    profile=profile_name,
                    brand=brand,
                )
            )
        frappe.db.commit()

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.a, self.b = self.fixtures

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.rollback()
        frappe.clear_cache()
        super().tearDown()

    def test_cashiers_list_only_their_brand_and_profile(self):
        for fixture in self.fixtures:
            with self.subTest(user=fixture.user):
                frappe.set_user(fixture.user)
                self.assertEqual(
                    frappe.get_list("OMP Business Brand", pluck="name"), [fixture.brand]
                )
                self.assertEqual(frappe.get_list("POS Profile", pluck="name"), [fixture.profile])
                self.assertEqual(get_brand_context(fixture.brand)["company"], fixture.company)

    def test_direct_document_api_and_context_reject_other_brand(self):
        for own, other in ((self.a, self.b), (self.b, self.a)):
            frappe.set_user(own.user)
            for doctype, name in (
                ("OMP Business Brand", other.brand),
                ("POS Profile", other.profile),
                ("Company", other.company),
                ("Warehouse", other.warehouse),
            ):
                with (
                    self.subTest(doctype=doctype, user=own.user),
                    self.assertRaises(frappe.PermissionError),
                ):
                    get_document(doctype, name)
            with self.assertRaises(frappe.PermissionError):
                get_brand_context(other.brand)

    def test_guest_is_rejected(self):
        frappe.set_user("Guest")
        with self.assertRaises(frappe.PermissionError):
            get_brand_context(self.a.brand)
        self.assertFalse(
            frappe.has_permission("OMP Business Brand", doc=self.a.brand, ptype="read")
        )

    def test_brand_grant_does_not_override_native_company_permission(self):
        doc = frappe.get_doc("OMP Business Brand", self.b.brand)
        doc.append("allowed_users", {"user": self.a.user})
        doc.save()
        profile = frappe.get_doc("POS Profile", self.b.profile)
        profile.append("applicable_for_users", {"user": self.a.user})
        profile.save()
        frappe.set_user(self.a.user)
        with self.assertRaises(frappe.PermissionError):
            get_brand_context(self.b.brand)

    def test_native_profile_user_restriction_applies_to_list_and_direct_access(self):
        profile = frappe.get_doc("POS Profile", self.a.profile)
        profile.set("applicable_for_users", [{"user": self.b.user, "default": 1}])
        profile.save()
        frappe.set_user(self.a.user)
        self.assertEqual(frappe.get_list("POS Profile", pluck="name"), [])
        with self.assertRaises(frappe.PermissionError):
            get_brand_context(self.a.brand)

    def test_disabled_brand_and_profile_are_rejected(self):
        for doctype, name, field in (
            ("OMP Business Brand", self.a.brand, "enabled"),
            ("POS Profile", self.a.profile, "disabled"),
        ):
            frappe.set_user("Administrator")
            old = frappe.db.get_value(doctype, name, field)
            frappe.db.set_value(doctype, name, field, 0 if field == "enabled" else 1)
            frappe.set_user(self.a.user)
            with self.assertRaises(frappe.PermissionError):
                get_brand_context(self.a.brand)
            frappe.set_user("Administrator")
            frappe.db.set_value(doctype, name, field, old)

    def test_cashier_cannot_edit_brand_or_profile(self):
        frappe.set_user(self.a.user)
        for doctype, name in (
            ("OMP Business Brand", self.a.brand),
            ("POS Profile", self.a.profile),
        ):
            doc = frappe.get_doc(doctype, name)
            with self.assertRaises(frappe.PermissionError):
                doc.save()

    def test_configuration_rejects_mismatched_warehouse(self):
        doc = frappe.get_doc("OMP Business Brand", self.a.brand)
        doc.warehouse = self.b.warehouse
        with self.assertRaises(frappe.ValidationError):
            doc.save()

    def test_role_setup_preserves_native_roles_and_is_idempotent(self):
        before = frappe.get_all(
            "Custom DocPerm",
            filters={"parent": "POS Profile"},
            fields=["name", "role", "read", "write", "create", "delete"],
        )
        ensure_cashier_role()
        after = frappe.get_all(
            "Custom DocPerm",
            filters={"parent": "POS Profile"},
            fields=["name", "role", "read", "write", "create", "delete"],
        )
        self.assertEqual(before, after)
        native = {row.role for row in after}
        self.assertIn("Accounts Manager", native)
        cashier = next(row for row in after if row.role == "OMP Cashier")
        self.assertEqual(cashier.read, 1)
        self.assertFalse(cashier.write or cashier.create or cashier.delete)
