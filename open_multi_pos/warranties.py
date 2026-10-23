"""Warranty follow-up on native documents; no billing or stock movement."""

from contextvars import ContextVar
from datetime import date
from html import escape, unescape

import frappe
from frappe.utils import nowdate, strip_html

from open_multi_pos import checkout as native
from open_multi_pos import checkout_contract as wire
from open_multi_pos.workspace import brand_context, clean_text

DOCTYPE = "Warranty Claim"
JOURNAL = "OMP Warranty Request"
STATUSES = ("Open", "Work In Progress", "Closed", "Cancelled")
CREATING = ContextVar("omp_warranty_creating", default=False)
LINKS = (
    "company",
    "customer",
    "item_code",
    "omp_business_brand",
    "omp_sales_invoice",
    "omp_invoice_item",
    "omp_operation_key",
)


def context(brand):
    ctx = brand_context(wire.identifier(brand))
    frappe.db.get_value("POS Profile", ctx["pos_profile"], "name", for_update=True)
    frappe.db.get_value("OMP Business Brand", brand, "name", for_update=True)
    return brand_context(brand)


def source(ctx, invoice, row="", *, creating=False):
    doc = frappe.get_doc("Sales Invoice", wire.identifier(invoice), for_update=True)
    doc.check_permission("read")
    if (
        doc.company != ctx["company"]
        or doc.pos_profile != ctx["pos_profile"]
        or doc.is_return
        or not doc.is_pos
        or not frappe.db.exists(
            "OMP Checkout Request", {"brand": ctx["brand"], "invoice": doc.name, "abandoned": 0}
        )
    ):
        frappe.throw("Venta de otro negocio o fuera de la caja autorizada", frappe.PermissionError)
    if creating and doc.docstatus != 1:
        native.conflict("Seleccione una venta enviada y vigente")
    if row and row not in [item.name for item in doc.items]:
        raise ValueError("El artículo no pertenece a esta venta")
    return doc


def record(ctx, request_id):
    key = wire.digest(["warranty", frappe.session.user, wire.request_uuid(request_id)])
    row = frappe.db.get_value(
        JOURNAL,
        key,
        ["actor", "brand", "status", "claim", "payload_hash"],
        as_dict=True,
        for_update=True,
    )
    if row and (row.actor != frappe.session.user or row.brand != ctx["brand"]):
        frappe.throw("Intento de otro usuario o negocio", frappe.PermissionError)
    return key, row


def load(ctx, name):
    doc = frappe.get_doc(DOCTYPE, wire.identifier(name), for_update=True)
    doc.check_permission("read")
    if doc.omp_business_brand != ctx["brand"] or doc.company != ctx["company"]:
        frappe.throw("Reclamación de otro negocio", frappe.PermissionError)
    invoice = source(ctx, doc.omp_sales_invoice, doc.omp_invoice_item)
    item = next(item for item in invoice.items if item.name == doc.omp_invoice_item)
    if doc.item_code != item.item_code or doc.customer != invoice.customer:
        native.conflict("El vínculo histórico de la reclamación cambió; revise ERPNext")
    return doc


def view(doc):
    return {
        "claim": doc.name,
        "invoice": doc.omp_sales_invoice,
        "row": doc.omp_invoice_item,
        "item_code": doc.item_code,
        "item_name": doc.item_name,
        "status": doc.status,
        "date": str(doc.complaint_date),
        "resolved_at": str(doc.resolution_date or ""),
        "complaint": unescape(strip_html(doc.complaint)),
        "notes": doc.resolution_details or "",
        "modified": str(doc.modified),
    }


def outcome(ctx, row):
    if not row:
        return {"status": "not_found"}
    if row.status == "Abandoned":
        return {"status": "abandoned"}
    return {"status": "completed", "record": view(load(ctx, row.claim))}


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def inspect(brand, invoice):
    ctx = context(brand)
    if not frappe.has_permission(DOCTYPE, "create"):
        frappe.throw("Requiere permiso para registrar garantías", frappe.PermissionError)
    doc = source(ctx, invoice, creating=True)
    return {
        "invoice": doc.name,
        "date": nowdate(),
        "items": [
            {"row": row.name, "item_code": row.item_code, "name": row.item_name}
            for row in doc.items
        ],
    }


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def create(data):
    data = wire.mapping(data, ("brand", "invoice", "row", "date", "complaint", "request_id"))
    if not isinstance(data["date"], str):
        raise ValueError("Fecha de reclamación inválida")
    data = {
        **{key: wire.identifier(data[key]) for key in ("brand", "invoice", "row")},
        "date": date.fromisoformat(data["date"]).isoformat(),
        "complaint": clean_text(data["complaint"], maximum=2000, required=True),
        "request_id": wire.request_uuid(data["request_id"]),
    }
    if data["date"] > nowdate():
        raise ValueError("La fecha de reclamación no puede estar en el futuro")
    ctx = context(data["brand"])
    key, prior = record(ctx, data["request_id"])
    if prior:
        if prior.status == "Abandoned":
            native.conflict("El intento fue abandonado; prepare otra reclamación")
        if prior.payload_hash != wire.digest(data):
            native.conflict("La clave pertenece a otra reclamación")
        return outcome(ctx, prior)
    invoice = source(ctx, data["invoice"], data["row"], creating=True)
    item = next(row for row in invoice.items if row.name == data["row"])
    if data["date"] < str(invoice.posting_date):
        raise ValueError("La reclamación no puede ser anterior a la venta")
    doc = frappe.get_doc(
        {
            "doctype": DOCTYPE,
            "naming_series": "SER-WRN-.YYYY.-",
            "company": invoice.company,
            "customer": invoice.customer,
            "item_code": item.item_code,
            "status": "Open",
            "complaint_date": data["date"],
            "complaint": escape(data["complaint"]),
            "omp_operation_key": key,
            "omp_business_brand": ctx["brand"],
            "omp_sales_invoice": invoice.name,
            "omp_invoice_item": item.name,
        }
    )
    token = CREATING.set(True)
    try:
        doc.insert()
    finally:
        CREATING.reset(token)
    native.journal(
        JOURNAL,
        key,
        {
            "actor": frappe.session.user,
            "brand": ctx["brand"],
            "status": "Completed",
            "claim": doc.name,
            "payload_hash": wire.digest(data),
        },
    )
    return {"status": "completed", "record": view(doc)}


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def status(brand, request_id):
    ctx = context(brand)
    return outcome(ctx, record(ctx, request_id)[1])


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def abandon(brand, request_id):
    ctx = context(brand)
    key, prior = record(ctx, request_id)
    if prior:
        return outcome(ctx, prior)
    native.journal(
        JOURNAL, key, {"actor": frappe.session.user, "brand": ctx["brand"], "status": "Abandoned"}
    )
    return {"status": "abandoned"}


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def listing(brand, claim=""):
    ctx = context(brand)
    if claim:
        return [view(load(ctx, claim))]
    return [
        view(load(ctx, row))
        for row in frappe.get_list(
            DOCTYPE,
            filters={"omp_business_brand": ctx["brand"]},
            pluck="name",
            order_by="modified desc",
            limit=50,
        )
    ]


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def update(brand, claim, modified, status, notes):
    if status not in STATUSES:
        raise ValueError("Estado de reclamación no admitido")
    notes = clean_text(notes, maximum=4000)
    ctx = context(brand)
    doc = load(ctx, claim)
    doc.check_permission("write")
    if doc.status == status and (doc.resolution_details or "") == notes:
        return view(doc)
    if str(doc.modified) != modified:
        native.conflict("La reclamación cambió. Consúltela otra vez antes de guardar")
    doc.status, doc.resolution_details = status, notes
    if status == "Closed":
        doc.resolved_by = frappe.session.user
    else:
        doc.resolution_date = None
        doc.resolved_by = None
    doc.save()
    return view(doc)


def guard_links(doc, method=None):
    previous = doc.get_doc_before_save()
    if not (
        any(doc.get(field) for field in LINKS[3:])
        or (previous and previous.get("omp_operation_key"))
    ):
        return
    if doc.is_new():
        if not CREATING.get():
            frappe.throw("Registre la reclamación desde Garantías", frappe.PermissionError)
    elif previous and any(doc.get(field) != previous.get(field) for field in LINKS):
        frappe.throw(
            "El vínculo de la reclamación con la venta es inmutable", frappe.PermissionError
        )


def guard_delete(doc, method=None):
    if doc.get("omp_operation_key"):
        frappe.throw("Conserve el historial; cambie el estado a Cancelada", frappe.PermissionError)
