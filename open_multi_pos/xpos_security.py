"""HTTP adapters for the pinned X POS APIs; no monkeypatches or core modifications."""

import frappe
from frappe.utils import cint

from open_multi_pos.api import get_brand_context
from open_multi_pos.xpos_routes import INVOICE_DOCTYPES


class PrintTrackingConflict(frappe.ValidationError):
    http_status_code = 409


def require_user():
    if frappe.session.user == "Guest":
        frappe.throw("Se requiere una sesión autenticada", frappe.PermissionError)


def authorized_profile(name):
    require_user()
    brands = frappe.get_list(
        "OMP Business Brand", filters={"pos_profile": name, "enabled": 1}, pluck="name", limit=1
    )
    if not brands:
        frappe.throw("Perfil POS no autorizado", frappe.PermissionError)
    get_brand_context(brands[0])  # Brand, native permissions, assignments and current links.
    return frappe.get_doc("POS Profile", name)


def checked_invoice(doctype, name, *, for_update=False):
    require_user()
    if doctype not in INVOICE_DOCTYPES:
        frappe.throw("Tipo de documento no permitido", frappe.PermissionError)
    doc = frappe.get_doc(doctype, name, for_update=for_update)
    doc.check_permission("read")
    profile = authorized_profile(doc.get("pos_profile"))
    if (
        not doc.get("is_pos")
        or doc.company != profile.company
        or doc.get("set_warehouse") != profile.warehouse
    ):
        frappe.throw("Documento fuera del contexto POS autorizado", frappe.PermissionError)
    return doc


def authorize_print_page():
    """Guard both native print-page URL forms before any template is rendered."""
    from open_multi_pos.permissions import manager

    path = frappe.request.path.strip("/")
    if path == "printview":
        doctype, name = frappe.form_dict.get("doctype"), frappe.form_dict.get("name")
    else:
        doctype, _, name = path.partition("/")
    if doctype not in INVOICE_DOCTYPES:
        return
    require_user()
    user = frappe.session.user
    if manager(user) or "OMP Cashier" not in frappe.get_roles(user):
        return
    if frappe.form_dict.get("doc") or not name:
        frappe.throw("Se requiere un documento guardado y autorizado", frappe.PermissionError)
    doc = checked_invoice(doctype, name)
    doc.check_permission("print")


@frappe.whitelist(methods=["GET", "POST"])
def get_receipt_context(pos_profile: str, print_format: str | None = None) -> dict:
    profile = authorized_profile(pos_profile)
    company = frappe.get_doc("Company", profile.company)
    company.check_permission("read")
    address_name = company.get("company_address")
    company.apply_fieldlevel_read_permissions()
    # A cashier may use the format assigned by the administrator, but cannot
    # inspect arbitrary Print Format configuration (a System Manager capability).
    configured = (
        profile.get("default_print_format") or profile.get("print_format") or "XPOS Thermal Receipt"
    )
    if print_format and print_format != configured:
        frappe.throw("Formato no autorizado para este perfil", frappe.PermissionError)
    template = frappe.get_doc("Print Format", configured)
    if template.disabled or template.doc_type not in INVOICE_DOCTYPES:
        frappe.throw("Formato de recibo no habilitado", frappe.PermissionError)
    address_parts = []
    if address_name and company.get("company_address") == address_name:
        address = frappe.get_doc("Address", address_name)
        address.check_permission("read")
        address.apply_fieldlevel_read_permissions()
        address_parts = [
            address.get(field)
            for field in ("address_line1", "address_line2", "city", "state", "pincode")
        ]
    # Keep the upstream response contract using only freshly authorized documents;
    # do not re-enter the original cached resolver after checking another object.
    result = {
        "company_" + key: company.get(field) or ""
        for key, field in {
            "name": "company_name",
            "phone": "phone_no",
            "email": "email",
            "website": "website",
            "tax_id": "tax_id",
            "logo": "company_logo",
        }.items()
    }
    result.update(
        company_address=", ".join(part for part in address_parts if part),
        receipt_header=company.get("receipt_header") or "",
        receipt_footer=company.get("receipt_footer") or "",
        currency=company.get("default_currency") or "",
        print_discount_amount=cint(profile.get("print_discount_amount")),
        print_format=configured,
        css=template.get("css") or "",
    )
    return result


@frappe.whitelist(methods=["POST"])
def mark_invoice_printed(doctype: str, name: str) -> dict:
    try:
        return _mark_invoice_printed(doctype, name)
    except frappe.QueryDeadlockError:
        # MariaDB snapshot isolation may abort a waiting locking read (CHECKREAD).
        # Let Frappe roll back the request; never reset/commit a caller's transaction
        # or automatically repeat a physical print to conceal the conflict.
        frappe.throw(
            "Conflicto al registrar la impresión. Consulte el estado antes de reintentar el registro; no reenvíe el recibo a la impresora.",
            PrintTrackingConflict,
        )


def _mark_invoice_printed(doctype, name):
    from xpos.api.auth import user_has_pos_permission

    doc = checked_invoice(doctype, name, for_update=True)
    doc.check_permission("print")
    if doc.docstatus == 2:
        frappe.throw("Documento anulado", frappe.PermissionError)
    if doc.docstatus == 0 and not user_has_pos_permission(
        "print_draft_invoice", pos_profile=doc.pos_profile
    ):
        frappe.throw("Impresión de borradores no autorizada", frappe.PermissionError)
    count = cint(doc.get("print_count"))
    if count and not user_has_pos_permission("allow_reprint_invoice", pos_profile=doc.pos_profile):
        frappe.throw("Reimpresión no autorizada", frappe.PermissionError)
    # The row lock covers the permission/count check and increment together.
    # Frappe commits successful POST requests; we never commit a caller's transaction.
    frappe.db.set_value(doctype, name, "print_count", count + 1, update_modified=False)
    return {"name": name, "print_count": count + 1}


@frappe.whitelist(methods=["GET", "POST"])
def get_invoice_details(invoice_name: str, doctype: str = ""):
    require_user()
    if not doctype:
        for candidate in INVOICE_DOCTYPES:
            if frappe.get_list(candidate, filters={"name": invoice_name}, pluck="name", limit=1):
                doctype = candidate
                break
    doc = checked_invoice(doctype, invoice_name)
    from xpos.api.invoices import get_invoice_details as upstream

    original = upstream(invoice_name=invoice_name, doctype=doctype)
    doc.apply_fieldlevel_read_permissions()
    readable = doc.as_dict()
    result = {key: readable.get(key) for key in original}
    for table in ("items", "payments", "taxes"):
        rows = readable.get(table) or []
        result[table] = [
            {key: row.get(key) for key in original_row}
            for original_row, row in zip(original.get(table) or [], rows, strict=False)
        ]
    team = readable.get("sales_team") or []
    result["sales_person"] = team[0].get("sales_person") if team else None
    result["pos_delivery_charges_label"] = (
        original.get("pos_delivery_charges_label")
        if readable.get("pos_delivery_charges")
        and readable.get("pos_delivery_charges") == original.get("pos_delivery_charges")
        else None
    )
    return result


@frappe.whitelist(methods=["GET", "POST"])
def unavailable_invoice_operation(**kwargs):
    frappe.throw(
        "Operación X POS deshabilitada hasta validar el checkout nativo y sus permisos",
        frappe.PermissionError,
    )
