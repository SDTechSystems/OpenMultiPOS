"""Read-only administrator previews using saved, authorized native receipts."""

import json
from datetime import UTC, datetime

import frappe

from open_multi_pos import checkout
from open_multi_pos import checkout_contract as wire
from open_multi_pos.receipts import render_compact_receipt
from open_multi_pos.workspace import brand_context, require_admin, settings


def denied():
    frappe.throw("Recibo no disponible para este negocio o usuario", frappe.PermissionError)


def saved_part(record):
    if record.abandoned or not record.invoice or not record.receipt_json:
        denied()
    part = json.loads(record.receipt_json)
    context = brand_context(record.brand)
    invoice = frappe.get_doc("Sales Invoice", record.invoice)
    invoice.check_permission("read")
    invoice.check_permission("print")
    if (
        invoice.docstatus != 1
        or invoice.company != context["company"]
        or invoice.pos_profile != context["pos_profile"]
        or part["id"] != invoice.name
        or part["request_id"] != record.request_id
        or part["brand"]["id"] != record.brand
        or part["brand"]["company"] != invoice.company
        or part["brand"]["pos_profile"] != invoice.pos_profile
        or part["brand"]["warehouse"] != context["warehouse"]
        or part["currency"] != invoice.currency
        or part["total"] != int(checkout.money(checkout.invoice_total(invoice)) * 100)
    ):
        denied()
    return part


def saved(brand, kind, document):
    brand_context(brand)
    document = wire.identifier(document)
    if kind == "invoice":
        names = frappe.get_list(
            "OMP Checkout Request",
            filters={"brand": brand, "invoice": document, "abandoned": 0},
            pluck="name",
            limit=2,
        )
        if len(names) != 1:
            denied()
        parts = [saved_part(frappe.get_doc("OMP Checkout Request", names[0]))]
        return {
            "sales": parts,
            "currency": parts[0]["currency"],
            "total": parts[0]["total"],
            "change": parts[0]["change"],
        }
    if kind != "batch":
        raise ValueError("Tipo de documento no admitido")
    record = frappe.get_doc("OMP Sale Batch", document)
    record.check_permission("read")
    if record.status != "Completed" or not record.receipt_json:
        denied()
    receipt = json.loads(record.receipt_json)
    source = json.loads(record.request_json)
    parts = []
    for row in source["sales"]:
        child = frappe.get_doc(
            "OMP Checkout Request", wire.operation_key(row["terminal"], row["request_id"])
        )
        parts.append(saved_part(child))
    if (
        not 1 <= len(parts) <= 2
        or brand not in [part["brand"]["id"] for part in parts]
        or receipt["sales"] != parts
        or receipt["total"] != sum(part["total"] for part in parts)
        or any(part["currency"] != receipt["currency"] for part in parts)
        or receipt["change"] != sum(part["change"] for part in parts)
    ):
        denied()
    return receipt


@frappe.whitelist(methods=["GET"])
@checkout.contract_errors
def documents(brand):
    """Bounded recent list; exact invoice lookup remains available for older sales."""
    brand_context(brand)
    result = []
    for row in frappe.get_list(
        "OMP Checkout Request",
        filters={"brand": brand, "invoice": ["!=", ""], "abandoned": 0},
        fields=["name", "invoice"],
        order_by="creation desc",
        limit=30,
    ):
        try:
            saved_part(frappe.get_doc("OMP Checkout Request", row.name))
        except frappe.PermissionError:
            continue
        result.append({"kind": "invoice", "document": row.invoice, "label": row.invoice})
    for row in frappe.get_list(
        "OMP Sale Batch",
        filters={"status": "Completed"},
        pluck="name",
        order_by="creation desc",
        limit=30,
    ):
        try:
            receipt = saved(brand, "batch", row)
        except frappe.PermissionError:
            continue
        if len(receipt["sales"]) > 1:
            result.append(
                {
                    "kind": "batch",
                    "document": row,
                    "label": "Recibo conjunto · " + " / ".join(p["id"] for p in receipt["sales"]),
                }
            )
    return result


@frappe.whitelist(methods=["GET"])
@checkout.contract_errors
def preview(brand, kind="sample", document=""):
    require_admin()
    context = brand_context(brand)
    if kind == "sample":
        part = {
            "id": "MUESTRA · NO ES UNA VENTA",
            "created_at": datetime.now(UTC).isoformat(),
            "time_zone": settings()["time_zone"],
            "currency": frappe.db.get_value("Company", context["company"], "default_currency"),
            "brand": {**context, "name": context["display_name"]},
            "items": [{"name": "Producto de ejemplo", "qty": 1, "rate": 100000, "amount": 100000}],
            "payments": [{"kind": "Cash", "amount": 100000}],
            "total": 100000,
            "taxes": 0,
            "change": 0,
        }
        receipt = {
            "sales": [part],
            "currency": part["currency"],
            "total": part["total"],
            "change": 0,
        }
    else:
        receipt = saved(brand, kind, document)
    return {"html": render_compact_receipt(receipt), "sample": kind == "sample"}
