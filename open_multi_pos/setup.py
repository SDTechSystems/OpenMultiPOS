"""Minimal additional role; preserve existing ERPNext permissions."""

import frappe
from frappe.permissions import add_permission


def create_cashier_role():
    if not frappe.db.exists("Role", "OMP Cashier"):
        frappe.get_doc({"doctype": "Role", "role_name": "OMP Cashier", "desk_access": 1}).insert()


def ensure_cashier_role():
    create_cashier_role()
    if not frappe.db.exists("Custom Field", "POS Opening Entry-omp_checkout_revision"):
        from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

        create_custom_fields(
            {
                "POS Opening Entry": [
                    {
                        "fieldname": "omp_checkout_revision",
                        "fieldtype": "Int",
                        "label": "Revisión de caja OMP",
                        "default": "0",
                        "hidden": 1,
                        "read_only": 1,
                    }
                ]
            }
        )
    add_permission("POS Profile", "OMP Cashier", ptype="read")
    # Document hooks deny writes outside the service's private capability. Native
    # role and company permissions still run inside that capability; no Accounts role.
    for doctype in ("Sales Invoice", "POS Opening Entry", "POS Closing Entry"):
        add_permission(doctype, "OMP Cashier", ptype="read")
        name = frappe.db.get_value(
            "Custom DocPerm", {"parent": doctype, "role": "OMP Cashier", "permlevel": 0}
        )
        rule = frappe.get_doc("Custom DocPerm", name)
        if any(not rule.get(ptype) for ptype in ("read", "create", "write", "submit")):
            rule.update(dict.fromkeys(("read", "create", "write", "submit"), 1))
            rule.save()
            frappe.clear_cache(doctype=doctype)
