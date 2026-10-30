"""Guided native warranty claims. No charges, refunds or stock movements."""

import frappe
from frappe.utils import getdate, nowdate

from open_multi_pos import checkout as native
from open_multi_pos import checkout_contract as wire
from open_multi_pos import warranty_contract as contract
from open_multi_pos.receipt_preview import saved as saved_receipt
from open_multi_pos.workspace import brand_context

DOCTYPE = "Warranty Claim"
TOMBSTONE = "OMP Warranty Tombstone"
FIELDS = (
    "name",
    "status",
    "complaint_date",
    "item_code",
    "item_name",
    "omp_sales_invoice",
    "resolution_date",
    "modified",
)


def context(brand):
    ctx = brand_context(brand)
    # Same profile/brand locks as other workspace writes: they fence a create
    # already in flight from a concurrent abandon of the same attempt.
    frappe.db.get_value("POS Profile", ctx["pos_profile"], "name", for_update=True)
    frappe.db.get_value("OMP Business Brand", brand, "name", for_update=True)
    ctx = brand_context(brand)
    if not frappe.has_permission(DOCTYPE, "read"):
        frappe.throw("Requiere permiso de lectura de garantías", frappe.PermissionError)
    return ctx


def sale(ctx, invoice):
    # Only invoices recorded by this business's checkout journal, re-authorized now.
    saved_receipt(ctx["brand"], "invoice", invoice)
    doc = frappe.get_doc("Sales Invoice", invoice)
    doc.check_permission("read")
    if doc.docstatus != 1 or doc.is_return or doc.company != ctx["company"]:
        native.conflict("Seleccione una venta enviada y vigente de este negocio")
    return doc


def operation_key(request_id):
    return wire.digest(["warranty", frappe.session.user, wire.request_uuid(request_id)])


def abandoned(ctx, key):
    record = frappe.db.get_value(TOMBSTONE, key, ["actor", "brand"], as_dict=True, for_update=True)
    if record and (record.actor != frappe.session.user or record.brand != ctx["brand"]):
        frappe.throw("Intento de otro negocio o usuario", frappe.PermissionError)
    return bool(record)


def existing(key):
    # Current locking read, including after waiting for a concurrent request.
    rows = frappe.db.sql(
        f"SELECT name FROM `tab{DOCTYPE}` WHERE omp_operation_key=%s FOR UPDATE", key
    )
    return rows[0][0] if rows else None


def claim(ctx, name, *, lock=False):
    doc = frappe.get_doc(DOCTYPE, name, for_update=lock)
    doc.check_permission("read")
    if doc.get("omp_business_brand") != ctx["brand"] or doc.company != ctx["company"]:
        frappe.throw("Reclamación de otro negocio", frappe.PermissionError)
    return doc


def result(doc, **extra):
    notes = frappe.get_all(
        "Comment",
        filters={
            "reference_doctype": DOCTYPE,
            "reference_name": doc.name,
            "comment_type": "Comment",
        },
        fields=["owner", "creation", "content"],
        order_by="creation asc",
        limit=100,
    )
    return {
        "status": "saved",
        "claim": doc.name,
        "claim_status": doc.status,
        "modified": str(doc.modified),
        "complaint_date": str(doc.complaint_date),
        "complaint": contract.from_html(doc.complaint),
        "resolution_details": doc.resolution_details or "",
        "resolution_date": str(doc.resolution_date or ""),
        "resolved_by": doc.resolved_by or "",
        "invoice": doc.get("omp_sales_invoice"),
        "item_code": doc.item_code,
        "item_name": doc.item_name,
        "notes": [
            {
                "by": n.owner,
                "at": str(n.creation),
                "text": contract.from_html(n.content),
            }
            for n in notes
        ],
        **extra,
    }


@frappe.whitelist(methods=["GET"])
@native.contract_errors
def claims(brand, status=""):
    ctx = brand_context(wire.identifier(brand))
    filters = {"omp_business_brand": ctx["brand"], "company": ctx["company"]}
    if status:
        if status not in contract.STATUSES:
            raise ValueError("Estado no admitido")
        filters["status"] = status
    return frappe.get_list(
        DOCTYPE, filters=filters, fields=list(FIELDS), order_by="modified desc", limit=50
    )


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def inspect(brand, invoice):
    ctx = context(wire.identifier(brand))
    doc = sale(ctx, wire.identifier(invoice))
    return {
        "invoice": doc.name,
        "posting_date": str(doc.posting_date),
        "items": [
            {"row": r.name, "item_code": r.item_code, "name": r.item_name, "qty": r.qty}
            for r in doc.items
        ],
        "claims": frappe.get_list(
            DOCTYPE,
            filters={"omp_sales_invoice": doc.name, "omp_business_brand": ctx["brand"]},
            fields=list(FIELDS),
            limit=100,
        ),
    }


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def detail(brand, claim_name):
    ctx = context(wire.identifier(brand))
    return result(claim(ctx, wire.identifier(claim_name)))


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def create(data):
    data = contract.creation(data)
    ctx = context(data["brand"])
    if not frappe.has_permission(DOCTYPE, "create"):
        frappe.throw("Requiere permiso para registrar garantías", frappe.PermissionError)
    key = operation_key(data["request_id"])
    if abandoned(ctx, key):
        native.conflict("El intento fue resuelto sin registrar; empiece una nueva reclamación")
    payload_hash = wire.digest(data)
    name = existing(key)
    if name:
        doc = claim(ctx, name, lock=True)
        if doc.omp_payload_hash != payload_hash:
            native.conflict("Esta clave pertenece a otra reclamación")
        return result(doc, duplicate=True)
    invoice = sale(ctx, data["invoice"])
    line = next((r for r in invoice.items if r.name == data["row"]), None)
    if not line:
        native.conflict("El artículo no pertenece a la venta seleccionada")
    if not getdate(invoice.posting_date) <= getdate(data["complaint_date"]) <= getdate(nowdate()):
        raise ValueError("La fecha debe estar entre la venta y hoy")
    doc = frappe.get_doc(
        {
            "doctype": DOCTYPE,
            "status": "Open",
            "complaint_date": data["complaint_date"],
            "customer": invoice.customer,
            "company": invoice.company,
            "item_code": line.item_code,
            "item_name": line.item_name,
            "description": line.description,
            "complaint": contract.to_html(data["complaint"]),
            "omp_operation_key": key,
            "omp_payload_hash": payload_hash,
            "omp_business_brand": ctx["brand"],
            "omp_sales_invoice": invoice.name,
            "omp_invoice_item": line.name,
        }
    )
    doc.insert()
    return result(doc, duplicate=False)


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def update(data):
    data = contract.change(data)
    ctx = context(data["brand"])
    doc = claim(ctx, data["claim"], lock=True)
    doc.check_permission("write")
    if str(doc.modified) != data["modified"]:
        native.conflict(
            "Otra persona actualizó esta reclamación. Carga de nuevo y revisa antes de guardar"
        )
    if (
        doc.status == data["status"]
        and (doc.resolution_details or "") == data["resolution_details"]
        and not data["note"]
    ):
        raise ValueError("No hay cambios para guardar")
    if data["status"] == "Closed" and doc.status != "Closed":
        doc.resolved_by = frappe.session.user
    doc.status = data["status"]
    doc.resolution_details = data["resolution_details"]
    doc.save()
    if data["note"]:
        doc.add_comment("Comment", contract.to_html(data["note"]))
    return result(doc)


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def status(brand, request_id):
    ctx = context(wire.identifier(brand))
    key = operation_key(request_id)
    if abandoned(ctx, key):
        return {"status": "abandoned"}
    name = existing(key)
    if not name:
        return {"status": "not_found"}
    return result(claim(ctx, name, lock=True), duplicate=True)


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def abandon(brand, request_id):
    ctx = context(wire.identifier(brand))
    key = operation_key(request_id)
    if abandoned(ctx, key):
        return {"status": "abandoned"}
    name = existing(key)
    if name:
        return result(claim(ctx, name, lock=True), duplicate=True)
    native.journal(TOMBSTONE, key, {"actor": frappe.session.user, "brand": ctx["brand"]})
    return {"status": "abandoned"}
