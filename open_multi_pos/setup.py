"""Minimal additional role; preserve existing ERPNext permissions."""

import json
from pathlib import Path

import frappe
from frappe.permissions import add_permission


def create_cashier_role():
    if not frappe.db.exists("Role", "OMP Cashier"):
        frappe.get_doc({"doctype": "Role", "role_name": "OMP Cashier", "desk_access": 1}).insert()
    if not frappe.db.exists("Role", "OMP Administrator"):
        frappe.get_doc(
            {"doctype": "Role", "role_name": "OMP Administrator", "desk_access": 1}
        ).insert()


def ensure_first_use_defaults():
    """Native login settings for a fresh shop server; never overrides an owner's choice."""
    if not frappe.db.get_single_value("System Settings", "default_app"):
        frappe.db.set_single_value("System Settings", "default_app", "open_multi_pos")
    # With three apps declaring app_logo_url Frappe shows its own; this is the owner's setting.
    if not frappe.db.get_single_value("Navbar Settings", "app_logo"):
        frappe.db.set_single_value(
            "Navbar Settings", "app_logo", "/assets/open_multi_pos/images/openmultipos.svg"
        )
    # "Correo / Usuario" tells the owner that the installation account `Administrator` is valid.
    frappe.db.set_single_value("System Settings", "allow_login_using_user_name", 1)
    # A fresh server cannot send mail; the email-link button would be a dead end.
    if not frappe.db.exists("Email Account", {"enable_outgoing": 1}) and frappe.db.get_single_value(
        "System Settings", "login_with_email_link"
    ):
        frappe.db.set_single_value("System Settings", "login_with_email_link", 0)


def ensure_first_use_labels():
    """Spanish for native login and wizard text; owner edits to these records are kept."""
    if not frappe.db.exists("Language", "es"):
        return
    labels = json.loads((Path(__file__).parent / "first_use_es.json").read_text(encoding="utf-8"))
    for source, text in labels.items():
        if not frappe.db.exists("Translation", {"language": "es", "source_text": source}):
            frappe.get_doc(
                {
                    "doctype": "Translation",
                    "language": "es",
                    "source_text": source,
                    "translated_text": text,
                }
            ).insert(ignore_permissions=True)


def ensure_cashier_role():
    create_cashier_role()
    ensure_first_use_defaults()
    ensure_first_use_labels()
    ensure_landed_cost_fields()
    ensure_warranty_fields()
    if frappe.db.exists("DocType", "OMP Import Request"):
        frappe.db.add_index(
            "OMP Import Request", ["brand", "source_hash", "status"], "omp_import_content"
        )
    if frappe.db.exists("Custom Field", "Item-omp_business_brand"):
        frappe.db.add_index("Item", ["omp_business_brand", "item_name"], "omp_business_item_name")
    if not frappe.db.exists("Custom Field", "Stock Entry-omp_operation_key"):
        from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

        create_custom_fields(
            {
                "Stock Entry": [
                    {
                        "fieldname": "omp_operation_key",
                        "fieldtype": "Data",
                        "label": "Operación de inventario",
                        "unique": 1,
                        "read_only": 1,
                        "hidden": 1,
                    },
                    {
                        "fieldname": "omp_payload_hash",
                        "fieldtype": "Data",
                        "label": "Huella de inventario",
                        "read_only": 1,
                        "hidden": 1,
                    },
                ]
            }
        )
    if not frappe.db.exists("Custom Field", "Item-omp_operation_key"):
        from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

        create_custom_fields(
            {
                "Item": [
                    {
                        "fieldname": "omp_operation_key",
                        "fieldtype": "Data",
                        "label": "Operación de creación",
                        "unique": 1,
                        "hidden": 1,
                        "read_only": 1,
                    },
                    {
                        "fieldname": "omp_payload_hash",
                        "fieldtype": "Data",
                        "label": "Huella de creación",
                        "hidden": 1,
                        "read_only": 1,
                    },
                ]
            }
        )
    if not frappe.db.exists("Custom Field", "Item-omp_business_brand"):
        from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

        create_custom_fields(
            {
                "Item": [
                    {
                        "fieldname": "omp_business_brand",
                        "fieldtype": "Link",
                        "label": "Negocio propietario",
                        "options": "OMP Business Brand",
                    }
                ]
            }
        )
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
    rights = ("read", "create", "write", "submit")
    for doctype, granted in (
        # The receipt endpoints check native print permission on the invoice.
        ("Sales Invoice", (*rights, "print")),
        ("POS Opening Entry", rights),
        ("POS Closing Entry", rights),
    ):
        add_permission(doctype, "OMP Cashier", ptype="read")
        name = frappe.db.get_value(
            "Custom DocPerm", {"parent": doctype, "role": "OMP Cashier", "permlevel": 0}
        )
        rule = frappe.get_doc("Custom DocPerm", name)
        if any(not rule.get(ptype) for ptype in granted):
            rule.update(dict.fromkeys(granted, 1))
            rule.save()
            frappe.clear_cache(doctype=doctype)


def ensure_landed_cost_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    fields = [
        {
            "fieldname": "omp_operation_key",
            "fieldtype": "Data",
            "label": "Operación OMP",
            "unique": 1,
        },
        {"fieldname": "omp_payload_hash", "fieldtype": "Data", "label": "Huella OMP"},
        {
            "fieldname": "omp_business_brand",
            "fieldtype": "Link",
            "options": "OMP Business Brand",
            "label": "Negocio OMP",
        },
        {
            "fieldname": "omp_actor",
            "fieldtype": "Link",
            "options": "User",
            "label": "Administrador OMP",
        },
        {"fieldname": "omp_result_json", "fieldtype": "Long Text", "label": "Vista previa OMP"},
    ]
    for field in fields:
        field.update({"hidden": 1, "read_only": 1, "no_copy": 1})
    create_custom_fields({"Landed Cost Voucher": fields})


def ensure_warranty_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    fields = [
        {
            "fieldname": "omp_operation_key",
            "fieldtype": "Data",
            "label": "Operación OMP",
            "unique": 1,
        },
        {
            "fieldname": "omp_business_brand",
            "fieldtype": "Link",
            "options": "OMP Business Brand",
            "label": "Negocio OMP",
        },
        {
            "fieldname": "omp_sales_invoice",
            "fieldtype": "Link",
            "options": "Sales Invoice",
            "label": "Venta original",
        },
        {"fieldname": "omp_invoice_item", "fieldtype": "Data", "label": "Línea original"},
    ]
    for field in fields:
        field.update({"hidden": 1, "read_only": 1, "no_copy": 1})
    create_custom_fields({"Warranty Claim": fields})
    add_permission("Warranty Claim", "OMP Administrator", ptype="read")
    name = frappe.db.get_value(
        "Custom DocPerm", {"parent": "Warranty Claim", "role": "OMP Administrator", "permlevel": 0}
    )
    rule = frappe.get_doc("Custom DocPerm", name)
    if not rule.create or not rule.write:
        rule.update({"create": 1, "write": 1}).save()
        frappe.clear_cache(doctype="Warranty Claim")
