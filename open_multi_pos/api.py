"""Authorized read-only brand context; online checkout lives in checkout.py."""

import frappe

from open_multi_pos.permissions import manager


@frappe.whitelist()
def get_brand_context(brand: str) -> dict:
    doc = frappe.get_doc("OMP Business Brand", brand)
    doc.check_permission("read")
    if not doc.enabled:
        frappe.throw("Negocio desactivado", frappe.PermissionError)
    profile = frappe.get_doc("POS Profile", doc.pos_profile)
    profile.check_permission("read")
    if profile.disabled:
        frappe.throw("Perfil POS desactivado", frappe.PermissionError)
    profile_users = [row.user for row in profile.applicable_for_users]
    if (
        profile_users
        and frappe.session.user not in profile_users
        and not manager(frappe.session.user)
    ):
        frappe.throw("Usuario no autorizado en el perfil POS", frappe.PermissionError)
    # The brand grant must never confer access to an unrelated company/warehouse.
    company = frappe.get_doc("Company", doc.company)
    company.check_permission("read")
    warehouse = frappe.get_doc("Warehouse", doc.warehouse)
    warehouse.check_permission("read")
    if (
        profile.company != doc.company
        or profile.warehouse != doc.warehouse
        or warehouse.company != doc.company
    ):
        frappe.throw("Perfil POS no coincide con empresa y almacén")
    return {
        "brand": doc.name,
        "display_name": doc.display_name,
        "company": doc.company,
        "warehouse": doc.warehouse,
        "pos_profile": doc.pos_profile,
        "printer_profile": doc.printer_profile,
        "footer": doc.receipt_footer,
        "qr_url": doc.qr_url,
        "fiscal_status": "not_configured",
    }
