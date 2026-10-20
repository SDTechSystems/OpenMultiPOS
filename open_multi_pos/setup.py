"""Minimal additional role; preserve existing ERPNext permissions."""

import frappe
from frappe.permissions import add_permission


def ensure_cashier_role():
    if not frappe.db.exists("Role", "OMP Cashier"):
        frappe.get_doc({"doctype": "Role", "role_name": "OMP Cashier", "desk_access": 1}).insert()
    add_permission("POS Profile", "OMP Cashier", ptype="read")
