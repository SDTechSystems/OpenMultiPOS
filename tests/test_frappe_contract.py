"""Contract tests with an explicit fake frappe module; NOT Bench integration tests."""

import importlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class FrappeContractTests(unittest.TestCase):
    def setUp(self):
        self.frappe = MagicMock()
        self.frappe.session.user = "cashier@example.invalid"
        self.frappe.get_roles.return_value = ["Sales User"]
        self.frappe.PermissionError = PermissionError
        self.frappe.whitelist.return_value = lambda f: f

        def throw(message, exc=ValueError):
            raise exc(message)

        self.frappe.throw.side_effect = throw
        self.patcher = patch.dict(sys.modules, {"frappe": self.frappe})
        self.patcher.start()
        for name in ("open_multi_pos.permissions", "open_multi_pos.api"):
            sys.modules.pop(name, None)
        self.permissions = importlib.import_module("open_multi_pos.permissions")
        self.api = importlib.import_module("open_multi_pos.api")
        self.addCleanup(self.patcher.stop)
        self.addCleanup(
            lambda: [
                sys.modules.pop(name, None)
                for name in ("open_multi_pos.permissions", "open_multi_pos.api")
            ]
        )

    def test_permission_hook_uses_frappe_v16_ptype_contract(self):
        doc = SimpleNamespace(
            enabled=1, allowed_users=[SimpleNamespace(user="cashier@example.invalid")]
        )
        self.assertTrue(
            self.permissions.brand_permission(doc, user="cashier@example.invalid", ptype="read")
        )
        self.assertFalse(
            self.permissions.brand_permission(doc, user="other@example.invalid", ptype="read")
        )
        self.assertFalse(
            self.permissions.brand_permission(doc, user="cashier@example.invalid", ptype="write")
        )
        self.assertFalse(self.permissions.brand_permission(doc, user="Guest", ptype="read"))
        self.assertTrue(self.permissions.brand_permission(doc, user="Administrator", ptype="read"))

    def test_guest_query_has_no_records(self):
        self.assertEqual(self.permissions.brand_query("Guest"), "1=0")

    def test_native_document_permissions_are_checked_and_payload_is_narrow(self):
        brand = MagicMock(company="C", warehouse="W", pos_profile="P", enabled=1)
        brand.name = "B"
        profile = MagicMock(company="C", warehouse="W", applicable_for_users=[])
        company, warehouse = MagicMock(), MagicMock()
        self.frappe.get_doc.side_effect = [brand, profile, company, warehouse]
        result = self.api.get_brand_context("B")
        for doc in (brand, profile, company, warehouse):
            doc.check_permission.assert_called_once_with("read")
        self.assertEqual(result["fiscal_status"], "not_configured")
        self.assertNotIn("allowed_users", result)

    def test_forged_profile_company_is_rejected(self):
        brand = MagicMock(company="C", warehouse="W", pos_profile="P", enabled=1)
        profile = MagicMock(company="OTHER", warehouse="W", applicable_for_users=[])
        self.frappe.get_doc.side_effect = [brand, profile, MagicMock(), MagicMock()]
        with self.assertRaises(ValueError):
            self.api.get_brand_context("B")

    def test_native_pos_profile_user_restriction_is_enforced(self):
        brand = MagicMock(company="C", warehouse="W", pos_profile="P", enabled=1)
        profile = MagicMock(
            company="C",
            warehouse="W",
            applicable_for_users=[SimpleNamespace(user="another@example.invalid")],
        )
        self.frappe.get_doc.side_effect = [brand, profile]
        with self.assertRaises(PermissionError):
            self.api.get_brand_context("B")
