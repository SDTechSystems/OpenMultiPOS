"""One customer basket, native documents per business, one immutable receipt."""

import json

import frappe
from frappe.utils import now_datetime

from open_multi_pos import checkout as native
from open_multi_pos import checkout_contract as wire
from open_multi_pos.receipts import render_compact_receipt


def payload(data):
    data = wire.mapping(data, ("request_id", "sales"))
    request_id = wire.request_uuid(data["request_id"])
    if not isinstance(data["sales"], list) or not 1 <= len(data["sales"]) <= 2:
        raise ValueError("La cesta admite uno o dos negocios")
    rows = []
    for row in data["sales"]:
        row = wire.mapping(row, ("terminal", "request_id", "quote", "payments"))
        rows.append(
            {
                "terminal": wire.identifier(row["terminal"]),
                "request_id": wire.request_uuid(row["request_id"]),
                "quote": wire.identifier(row["quote"]),
                "payments": wire.payments(row["payments"]),
            }
        )
    if len({r["terminal"] for r in rows}) != len(rows) or len({r["quote"] for r in rows}) != len(
        rows
    ):
        raise ValueError("No repita negocio o cotización en una cesta")
    return {"request_id": request_id, "sales": sorted(rows, key=lambda r: r["terminal"])}


def authorize(rows, *, lock=False):
    contexts = [native.terminal_context(r["terminal"]) for r in rows]
    if len({c[0].brand for c in contexts}) != len(contexts):
        raise ValueError("Seleccione una terminal por negocio")
    if len({c[2].currency for c in contexts}) != 1:
        raise ValueError("Una cesta conjunta requiere la misma moneda en todos los negocios")
    if lock:
        # Common sorted locks precede child service calls. No inner commit/rollback.
        for profile in sorted({c[2].name for c in contexts}):
            frappe.db.get_value("POS Profile", profile, "name", for_update=True)
        for row in rows:
            native.terminal_context(row["terminal"], lock=True)
    return contexts


def key(request_id):
    return wire.digest([frappe.session.user, wire.request_uuid(request_id)])


def claim(data):
    name = key(data["request_id"])
    stamp = now_datetime()
    hashed = wire.digest(data)
    frappe.db.sql(
        """INSERT INTO `tabOMP Sale Batch` (name,creation,modified,owner,modified_by,docstatus,actor,request_id,payload_hash,request_json,status)
        VALUES (%s,%s,%s,%s,%s,0,%s,%s,%s,%s,'Pending') ON DUPLICATE KEY UPDATE name=name""",
        (
            name,
            stamp,
            stamp,
            frappe.session.user,
            frappe.session.user,
            frappe.session.user,
            data["request_id"],
            hashed,
            wire.canonical(data),
        ),
    )
    record = frappe.db.sql(
        "SELECT * FROM `tabOMP Sale Batch` WHERE name=%s FOR UPDATE", (name,), as_dict=True
    )[0]
    if record.payload_hash != hashed:
        native.conflict("El intento ya pertenece a otra cesta")
    return record


def saved(record):
    source = json.loads(record.request_json)
    contexts = authorize(source["sales"], lock=record.status == "Completed")
    if record.actor != frappe.session.user:
        frappe.throw("Operación ajena", frappe.PermissionError)
    if record.status == "Completed":
        # Current native permissions, including cancellation and revocation, remain authoritative.
        for row, ctx in zip(source["sales"], contexts, strict=True):
            quote = frappe.get_doc("OMP Checkout Quote", row["quote"])
            native.locked_opening(quote.opening_entry)
            child = frappe.get_doc(
                "OMP Checkout Request", wire.operation_key(row["terminal"], row["request_id"])
            )
            native.saved_sale(child, ctx[0])
        return {
            "status": "completed",
            "request_id": record.request_id,
            "receipt": json.loads(record.receipt_json),
            "duplicate": True,
        }
    if record.status == "Abandoned":
        return {"status": "abandoned", "request_id": record.request_id}
    native.conflict("La cesta no tiene un resultado definitivo; consulte con la misma clave")


def completed(record, sales):
    receipts = [s["receipt"] for s in sales]
    snapshot = {
        "version": 1,
        "id": record.request_id,
        "currency": receipts[0]["currency"],
        "sales": receipts,
        "total": sum(r["total"] for r in receipts),
        "change": sum(r["change"] for r in receipts),
        "fiscal_issued": False,
    }
    frappe.db.set_value(
        "OMP Sale Batch",
        record.name,
        {"status": "Completed", "receipt_json": wire.canonical(snapshot)},
    )
    return {
        "status": "completed",
        "request_id": record.request_id,
        "receipt": snapshot,
        "duplicate": False,
    }


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def checkout(data):
    data = payload(data)
    authorize(data["sales"], lock=True)
    record = claim(data)
    if record.status != "Pending":
        return saved(record)
    results = [native.checkout(row) for row in data["sales"]]
    return completed(record, results)


@frappe.whitelist(methods=["GET"])
@native.contract_errors
def get_status(request_id):
    if frappe.session.user == "Guest":
        frappe.throw("Inicie sesión", frappe.PermissionError)
    name = key(request_id)
    if not frappe.db.exists("OMP Sale Batch", name):
        return {"status": "not_found", "retry_with_same_key": True}
    return saved(frappe.get_doc("OMP Sale Batch", name))


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def abandon(data):
    data = payload(data)
    authorize(data["sales"], lock=True)
    record = claim(data)
    if record.status != "Pending":
        return saved(record)
    results = [native.abandon_checkout(row) for row in data["sales"]]
    statuses = {r["status"] for r in results}
    if statuses == {"completed"}:
        return completed(record, results)
    if statuses != {"abandoned"}:
        native.conflict(
            "Una parte de esta cesta ya existe. Un administrador debe revisar las facturas antes de continuar"
        )
    frappe.db.set_value("OMP Sale Batch", record.name, "status", "Abandoned")
    return {"status": "abandoned", "request_id": record.request_id}


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def receipt(request_id):
    result = get_status(request_id)
    if result["status"] != "completed":
        native.conflict("No hay un recibo guardado de esta cesta")
    for part in result["receipt"]["sales"]:
        frappe.get_doc("Sales Invoice", part["id"]).check_permission("print")
    return {"html": render_compact_receipt(result["receipt"])}
