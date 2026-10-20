"""Small authorized web-cashier facade. ERPNext remains the financial engine."""

import frappe

from open_multi_pos import checkout as service
from open_multi_pos import checkout_contract as contract
from open_multi_pos.hardware import printer_profiles
from open_multi_pos.receipts import render_receipt


def require_cashier():
    if frappe.session.user == "Guest" or "OMP Cashier" not in frappe.get_roles():
        frappe.throw("Se requiere un cajero autenticado", frappe.PermissionError)


@frappe.whitelist(methods=["GET"])
def terminals():
    require_cashier()
    result = []
    for row in frappe.get_list(
        "OMP POS Terminal", filters={"enabled": 1}, fields=["name", "display_name"], limit=100
    ):
        muted = frappe.flags.mute_messages
        try:
            frappe.flags.mute_messages = True
            _, context, _ = service.terminal_context(row.name)
        except frappe.PermissionError:
            continue
        finally:
            frappe.flags.mute_messages = muted
        result.append(
            {"name": row.name, "label": row.display_name, "brand": context["display_name"]}
        )
    return result


@frappe.whitelist(methods=["GET"])
@service.contract_errors
def context(terminal: str):
    terminal, brand, profile = service.terminal_context(terminal)
    service.checkout_configuration(profile)
    customer = profile.customer
    if not customer:
        frappe.throw("Configure el cliente de mostrador en el perfil POS")
    service.validate_catalog(profile, customer, [])
    opening = None
    if terminal.opening_entry:
        doc = frappe.get_doc("POS Opening Entry", terminal.opening_entry)
        doc.check_permission("read")
        opening = {"name": doc.name, "status": doc.status}
    return {
        "terminal": terminal.name,
        "brand": brand,
        "customer": customer,
        "currency": profile.currency,
        "opening": opening,
        "payment_modes": [
            {"name": name, "type": mode["type"]}
            for name, mode in service.payment_modes(profile).items()
        ],
        "printers": [{"id": p.id, "name": p.name} for p in printer_profiles().values()],
    }


@frappe.whitelist(methods=["GET"])
@service.contract_errors
def search(terminal: str, text: str = ""):
    _, _, profile = service.terminal_context(terminal)
    text = str(text).strip()
    if not text or len(text) > 140:
        return []
    service.validate_catalog(profile, profile.customer, [])
    # Barcode lookup only selects candidates. Native Item permissions and profile
    # groups are checked before returning any candidate or its label.
    barcode_items = frappe.get_all(
        "Item Barcode", filters={"barcode": text}, pluck="parent", limit=20
    )
    pattern = "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    rows = frappe.get_list(
        "Item",
        filters={"disabled": 0, "is_sales_item": 1, "has_variants": 0, "is_fixed_asset": 0},
        or_filters={"name": ["like", pattern], "item_name": ["like", pattern]},
        fields=["name", "item_name", "stock_uom"],
        order_by="name",
        limit=30,
    )
    exact = set(barcode_items + [text])
    names = list(dict.fromkeys(barcode_items + [r.name for r in rows]))
    result = []
    for name in names:
        doc = frappe.get_doc("Item", name)
        # Boolean checks avoid exception message logs leaking a forbidden barcode
        # candidate in an otherwise successful empty search response.
        if not doc.has_permission("read") or not service.simple_sale_item(doc):
            continue
        if (
            doc.get("omp_business_brand")
            and frappe.db.get_value("OMP Business Brand", doc.omp_business_brand, "pos_profile")
            != profile.name
        ):
            continue
        if not service.group_allowed("Item Group", doc.item_group, profile.item_groups):
            continue
        doc.apply_fieldlevel_read_permissions()
        if not doc.item_name or not doc.stock_uom:
            continue
        result.append(
            {"item_code": name, "name": doc.item_name, "uom": doc.stock_uom, "exact": name in exact}
        )
    return result


@frappe.whitelist(methods=["POST"])
@service.contract_errors
def receipt(terminal: str, request_id: str, printer: str | None = None):
    sale = service.get_status(terminal, contract.request_uuid(request_id))
    if sale["status"] != "completed":
        service.conflict("No hay un recibo de venta completada")
    frappe.get_doc("Sales Invoice", sale["invoice"]).check_permission("print")
    snapshot = sale["receipt"]
    profiles = printer_profiles()
    profile = profiles.get(printer or snapshot["brand"]["printer_profile"])
    if not profile:
        frappe.throw("Perfil de impresora desconocido")
    return {"html": render_receipt(snapshot, profile, native=True), "invoice": sale["invoice"]}
