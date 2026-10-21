"""Guided native credit notes. No external refund or fiscal transmission."""

import json
from decimal import Decimal

import frappe
from frappe.utils import cint, now_datetime, nowdate

from open_multi_pos import checkout as native
from open_multi_pos import checkout_contract as wire
from open_multi_pos.receipt_preview import saved as saved_receipt
from open_multi_pos.receipts import render_compact_receipt
from open_multi_pos.workspace import brand_context, clean_text, require_admin


def cents(amount):
    return int(native.money(amount) * 100)


def selection(data):
    data = wire.mapping(data, ("brand", "invoice", "items"))
    if not isinstance(data["items"], list) or not 1 <= len(data["items"]) <= 50:
        raise ValueError("Seleccione al menos un producto")
    rows = []
    for row in data["items"]:
        row = wire.mapping(row, ("row", "qty"))
        if type(row["qty"]) is not int or not 1 <= row["qty"] <= 10000:
            raise ValueError("La cantidad debe ser un entero positivo")
        rows.append({"row": wire.identifier(row["row"]), "qty": row["qty"]})
    if len({r["row"] for r in rows}) != len(rows):
        raise ValueError("No repita una línea")
    return {
        "brand": wire.identifier(data["brand"]),
        "invoice": wire.identifier(data["invoice"]),
        "items": sorted(rows, key=lambda r: r["row"]),
    }


def payload(data):
    data = wire.mapping(
        data,
        (
            "brand",
            "invoice",
            "items",
            "request_id",
            "terminal",
            "payments",
            "financial_hash",
            "reason",
        ),
    )
    return {
        **selection({k: data[k] for k in ("brand", "invoice", "items")}),
        "request_id": wire.request_uuid(data["request_id"]),
        "terminal": wire.identifier(data["terminal"]),
        "payments": wire.payments(data["payments"]),
        "financial_hash": wire.identifier(data["financial_hash"]),
        "reason": clean_text(data["reason"], maximum=500, required=True),
    }


def source(brand, invoice, *, lock=False):
    context = brand_context(brand)
    if lock:
        frappe.db.get_value("POS Profile", context["pos_profile"], "name", for_update=True)
    snapshot = saved_receipt(brand, "invoice", invoice)["sales"][0]
    doc = frappe.get_doc("Sales Invoice", invoice, for_update=lock)
    if doc.docstatus != 1 or doc.is_return or not doc.is_pos or not doc.update_stock:
        native.conflict("Seleccione una venta de caja enviada y vigente")
    if doc.discount_amount or any(t.charge_type == "Actual" for t in doc.taxes):
        native.conflict(
            "Esta factura tiene ajustes globales. Revise su devolución en el formulario nativo de ERPNext"
        )
    return context, doc, snapshot


def remaining(doc):
    # Current locking reads avoid a stale REPEATABLE READ view after waiting for
    # another return. The original invoice serializes this service's operations.
    rows = frappe.db.sql(
        """SELECT i.sales_invoice_item, i.qty, p.grand_total, p.name
        FROM `tabSales Invoice` p INNER JOIN `tabSales Invoice Item` i ON i.parent=p.name
        WHERE p.return_against=%s AND p.is_return=1 AND p.docstatus=1 FOR UPDATE""",
        doc.name,
        as_dict=True,
    )
    returned = {}
    for row in rows:
        if not row.sales_invoice_item:
            native.conflict(
                "Hay una devolución sin vínculo de línea. Revísela en ERPNext antes de continuar"
            )
        returned[row.sales_invoice_item] = returned.get(
            row.sales_invoice_item, Decimal(0)
        ) - Decimal(str(row.qty))
    result = {
        row.name: Decimal(str(row.qty)) - returned.get(row.name, Decimal(0)) for row in doc.items
    }
    if any(qty < 0 or qty != qty.to_integral_value() for qty in result.values()):
        native.conflict(
            "Hay cantidades fraccionarias o inconsistentes. Revise las devoluciones en ERPNext"
        )
    return result


def build(data):
    from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

    context, original, snapshot = source(data["brand"], data["invoice"], lock=True)
    available = remaining(original)
    requested = {r["row"]: r["qty"] for r in data["items"]}
    if any(key not in available or qty > available[key] for key, qty in requested.items()):
        native.conflict("La cantidad supera lo que falta por devolver. Carga de nuevo la factura")
    doc = make_sales_return(original.name)
    selected = []
    for row in doc.items:
        if row.sales_invoice_item in requested:
            if row.serial_and_batch_bundle or row.serial_no or row.batch_no:
                native.conflict("Este producto requiere selección de serie o lote en ERPNext")
            row.qty = -requested[row.sales_invoice_item]
            row.warehouse = context["warehouse"]
            selected.append(row)
    if len(selected) != len(requested):
        native.conflict("No se pudieron relacionar todas las líneas con la venta original")
    doc.set("items", selected)
    doc.set_qty_as_per_stock_uom()
    doc.set_warehouse = context["warehouse"]
    doc.posting_date = nowdate()
    doc.posting_time = now_datetime().time()
    doc.set_posting_time = 1
    doc.set("payments", [])
    doc.paid_amount = doc.base_paid_amount = doc.change_amount = doc.base_change_amount = 0
    doc.write_off_amount = doc.base_write_off_amount = 0
    doc.update_outstanding_for_self = 1
    doc.calculate_taxes_and_totals()
    prior_notes = frappe.db.sql(
        """SELECT name, grand_total, rounded_total, disable_rounded_total
        FROM `tabSales Invoice` WHERE return_against=%s AND is_return=1 AND docstatus=1 FOR UPDATE""",
        original.name,
        as_dict=True,
    )
    refund_balance = native.invoice_total(original) + sum(
        (native.invoice_total(note) for note in prior_notes), Decimal(0)
    )
    refund = -native.invoice_total(doc)
    final = all(Decimal(requested.get(row, 0)) == qty for row, qty in available.items())
    if refund > refund_balance or (final and refund != refund_balance):
        native.conflict(
            "Hay una diferencia de redondeo con el saldo original. Revise la devolución en ERPNext antes de reembolsar"
        )
    if native.invoice_total(doc) >= 0:
        native.conflict("La devolución debe tener un importe positivo a reembolsar")
    return context, original, snapshot, doc, available


def estimate(doc, available):
    return {
        "financial": native.financial(doc),
        "remaining": {k: str(v) for k, v in available.items()},
    }


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def inspect(brand, invoice):
    _, doc, snapshot = source(wire.identifier(brand), wire.identifier(invoice), lock=True)
    available = remaining(doc)
    return {
        "invoice": doc.name,
        "currency": doc.currency,
        "business": snapshot["brand"]["name"],
        "items": [
            {
                "row": r.name,
                "item_code": r.item_code,
                "name": r.item_name,
                "sold": int(r.qty),
                "remaining": int(available[r.name]),
                "rate": cents(r.rate),
            }
            for r in doc.items
        ],
        "credit_notes": frappe.get_list(
            "Sales Invoice",
            filters={"return_against": doc.name, "is_return": 1, "docstatus": 1},
            fields=["name", "grand_total"],
            limit=100,
        ),
    }


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def quote(data):
    data = selection(data)
    _, _, _, doc, available = build(data)
    modes = native.payment_modes(frappe.get_doc("POS Profile", doc.pos_profile))
    return {
        "total": cents(-native.invoice_total(doc)),
        "currency": doc.currency,
        "financial_hash": wire.digest(estimate(doc, available)),
        "payment_modes": [{"name": name, "kind": mode["type"]} for name, mode in modes.items()],
    }


def authorize(data):
    require_admin()
    terminal, context, profile = native.terminal_context(data["terminal"], lock=True)
    if terminal.brand != data["brand"]:
        frappe.throw("Terminal de otro negocio", frappe.PermissionError)
    source(data["brand"], data["invoice"], lock=True)
    return terminal, context, profile


def key(request_id):
    return wire.digest([frappe.session.user, wire.request_uuid(request_id)])


def claim(data):
    name, stamp = key(data["request_id"]), now_datetime()
    frappe.db.sql(
        """INSERT INTO `tabOMP Return Request`
        (name,creation,modified,owner,modified_by,docstatus,actor,brand,invoice,request_id,payload_hash,request_json,status)
        VALUES (%s,%s,%s,%s,%s,0,%s,%s,%s,%s,%s,%s,'Pending') ON DUPLICATE KEY UPDATE name=name""",
        (
            name,
            stamp,
            stamp,
            frappe.session.user,
            frappe.session.user,
            frappe.session.user,
            data["brand"],
            data["invoice"],
            data["request_id"],
            wire.digest(data),
            wire.canonical(data),
        ),
    )
    record = frappe.get_doc("OMP Return Request", name, for_update=True)
    if record.actor != frappe.session.user or record.payload_hash != wire.digest(data):
        native.conflict("Esta clave pertenece a otra devolución")
    return record


def saved(record):
    if record.status == "Abandoned":
        return {"status": "abandoned", "request_id": record.request_id}
    if record.status != "Completed":
        return {"status": "pending", "request_id": record.request_id}
    doc = frappe.get_doc("Sales Invoice", record.credit_note, for_update=True)
    doc.check_permission("read")
    if doc.docstatus != 1 or not doc.is_return or doc.return_against != record.invoice:
        native.conflict("La nota crédito ya no está vigente. Revise la operación en ERPNext")
    return {
        "status": "completed",
        "request_id": record.request_id,
        "credit_note": doc.name,
        "receipt": json.loads(record.receipt_json),
        "duplicate": True,
    }


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def submit(data):
    data = payload(data)
    terminal, _, profile = authorize(data)
    record = claim(data)
    if record.status != "Pending":
        return saved(record)
    native.checkout_configuration(profile)
    opening = native.active_opening(terminal, profile)
    context, _, original_snapshot, doc, available = build(data)
    if wire.digest(estimate(doc, available)) != data["financial_hash"]:
        native.conflict(
            "La devolución cambió. Resuelve este intento y vuelve a calcular antes de reembolsar"
        )
    modes = native.payment_modes(profile)
    native.validate_modes(data["payments"], modes)
    total = -native.invoice_total(doc)
    if sum(Decimal(p["amount"]) for p in data["payments"]) != total:
        native.conflict("Los medios de reembolso deben sumar exactamente el total")
    for pay in data["payments"]:
        mode = modes[pay["mode_of_payment"]]
        doc.append(
            "payments",
            {
                "mode_of_payment": pay["mode_of_payment"],
                "type": mode["type"],
                "account": mode["account"],
                "amount": -Decimal(pay["amount"]),
                "reference_no": pay.get("reference_no", ""),
            },
        )
    doc.remarks = data["reason"]
    doc.calculate_taxes_and_totals()
    expected = wire.digest(native.financial(doc))
    doc.insert()
    doc.submit()
    if wire.digest(native.financial(doc)) != expected or -native.invoice_total(doc) != total:
        native.conflict("La validación nativa cambió los importes; no se guardó la devolución")
    receipt = native.receipt_snapshot(doc, context, data["request_id"], opening.name)
    receipt["brand"] = original_snapshot["brand"]
    receipt["return_against"] = data["invoice"]
    receipt["reason"] = data["reason"]
    snapshot = {
        "sales": [receipt],
        "currency": receipt["currency"],
        "total": receipt["total"],
        "change": 0,
        "is_return": True,
    }
    frappe.db.set_value(
        "OMP Return Request",
        record.name,
        {"status": "Completed", "credit_note": doc.name, "receipt_json": wire.canonical(snapshot)},
    )
    frappe.db.set_value(
        "POS Opening Entry",
        opening.name,
        "omp_checkout_revision",
        cint(opening.get("omp_checkout_revision")) + 1,
    )
    return {**saved(frappe.get_doc("OMP Return Request", record.name)), "duplicate": False}


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def status(data):
    data = payload(data)
    authorize(data)
    name = key(data["request_id"])
    if not frappe.db.exists("OMP Return Request", name):
        return {"status": "not_found", "request_id": data["request_id"]}
    return saved(claim(data))


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def abandon(data):
    data = payload(data)
    authorize(data)
    record = claim(data)
    if record.status == "Completed":
        return saved(record)
    frappe.db.set_value("OMP Return Request", record.name, "status", "Abandoned")
    return {"status": "abandoned", "request_id": data["request_id"]}


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def receipt(data):
    data = payload(data)
    authorize(data)
    record = claim(data)
    result = saved(record)
    if result["status"] != "completed":
        native.conflict("La devolución todavía no tiene recibo")
    frappe.get_doc("Sales Invoice", record.credit_note).check_permission("print")
    return {"html": render_compact_receipt(result["receipt"])}
