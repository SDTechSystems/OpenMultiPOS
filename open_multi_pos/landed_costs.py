"""Guided native LCVs. No private ledger and no permission bypass."""

import json
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal

import frappe
from frappe.utils import nowdate

from open_multi_pos import checkout as native
from open_multi_pos import checkout_contract as wire
from open_multi_pos.landed_cost_contract import selection
from open_multi_pos.workspace import brand_context

DOCTYPE = "Landed Cost Voucher"
TOMBSTONE = "OMP Landed Cost Tombstone"
_submitting = ContextVar("omp_landed_cost_submit", default=False)


@contextmanager
def submission():
    token = _submitting.set(True)
    try:
        yield
    finally:
        _submitting.reset(token)


def guard_submit(doc, method=None):
    if doc.get("omp_operation_key") and not _submitting.get():
        frappe.throw(
            "Revisa y envía este borrador desde Costos de compra en OMP para conservar la vista previa final"
        )


def number(value):
    return Decimal(str(value or 0))


def context(brand):
    ctx = brand_context(brand)
    frappe.db.get_value("POS Profile", ctx["pos_profile"], "name", for_update=True)
    frappe.db.get_value("OMP Business Brand", brand, "name", for_update=True)
    ctx = brand_context(brand)
    if not frappe.has_permission(DOCTYPE, "read"):
        frappe.throw("Requiere permiso de lectura de costos de compra", frappe.PermissionError)
    return ctx


def sources(ctx, receipts):
    result = []
    for ref in receipts:
        doc = frappe.get_doc(ref["doctype"], ref["name"], for_update=True)
        doc.check_permission("read")
        if (
            doc.company != ctx["company"]
            or doc.docstatus != 1
            or doc.is_return
            or (doc.doctype == "Purchase Invoice" and not doc.update_stock)
        ):
            frappe.throw(
                "Seleccione una compra enviada con stock de esta empresa", frappe.PermissionError
            )
        for row in doc.items:
            item = frappe.get_doc("Item", row.item_code, for_update=True)
            item.check_permission("read")
            if (
                item.omp_business_brand != ctx["brand"]
                or row.warehouse != ctx["warehouse"]
                or not item.is_stock_item
                or item.is_fixed_asset
                or item.has_batch_no
                or item.has_serial_no
                or number(row.qty) <= 0
                or number(row.conversion_factor) != 1
                or number(row.rejected_qty) != 0
            ):
                raise ValueError(
                    "Todas las filas deben ser stock del negocio y su almacén, sin series, lotes, "
                    "rechazos ni conversiones de unidad. Revise otros casos en ERPNext"
                )
        if not doc.items or sum(number(r.base_net_amount) for r in doc.items) <= 0:
            raise ValueError("La compra debe tener artículos y costo base positivo")
        result.append(doc)
    return result


def validate_charges(ctx, charges):
    currency = frappe.db.get_value("Company", ctx["company"], "default_currency")
    for row in charges:
        account = frappe.get_doc("Account", row["account"], for_update=True)
        account.check_permission("read")
        if account.company != ctx["company"] or account.is_group or account.disabled:
            raise ValueError("Seleccione una cuenta activa de la empresa")
        if account.account_type != "Expenses Included In Valuation":
            raise ValueError("La cuenta debe ser de tipo Gastos incluidos en valoración")
        if row["currency"] != (account.account_currency or currency):
            raise ValueError("La moneda original debe coincidir con la moneda de la cuenta nativa")
        if row["currency"] == currency and number(row["exchange_rate"]) != 1:
            raise ValueError("La tasa de la moneda contable debe ser 1")
    return currency


def build(ctx, data):
    docs = sources(ctx, data["receipts"])
    validate_charges(ctx, data["charges"])
    doc = frappe.get_doc(
        {
            "doctype": DOCTYPE,
            "company": ctx["company"],
            "posting_date": nowdate(),
            "distribute_charges_based_on": data["basis"],
            "purchase_receipts": [
                {"receipt_document_type": d.doctype, "receipt_document": d.name} for d in docs
            ],
            "taxes": [
                {
                    "expense_account": r["account"],
                    "account_currency": r["currency"],
                    "exchange_rate": r["exchange_rate"],
                    "amount": r["amount"],
                    "description": r["description"],
                }
                for r in data["charges"]
            ],
        }
    )
    doc.check_permission("create")
    doc.get_items_from_purchase_receipts()
    doc.validate()
    return doc, docs


def plan(ctx, doc, docs):
    originals = {(d.doctype, d.name, r.name): r for d in docs for r in d.items}
    currency = frappe.db.get_value("Company", ctx["company"], "default_currency")
    charges = [
        {
            "account": r.expense_account,
            "currency": r.account_currency,
            "amount": str(number(r.amount)),
            "exchange_rate": str(number(r.exchange_rate)),
            "base_amount": str(number(r.base_amount)),
            "description": r.description,
        }
        for r in doc.taxes
    ]
    rows = []
    for r in doc.items:
        original = originals[(r.receipt_document_type, r.receipt_document, r.purchase_receipt_item)]
        before = number(original.valuation_rate)
        qty = number(original.qty)
        added = number(r.applicable_charges)
        rows.append(
            {
                "receipt": r.receipt_document,
                "item_code": r.item_code,
                "qty": str(qty),
                "before": str(before),
                "charge": str(added),
                "after": str(before + added / qty),
            }
        )
    return {
        "brand": ctx["brand"],
        "business": ctx["display_name"],
        "company": ctx["company"],
        "warehouse": ctx["warehouse"],
        "currency": currency,
        "posting_date": str(doc.posting_date),
        "basis": doc.distribute_charges_based_on,
        "total": str(number(doc.total_taxes_and_charges)),
        "charges": charges,
        "items": rows,
        "sources": [
            {"doctype": d.doctype, "name": d.name, "modified": str(d.modified)} for d in docs
        ],
        "revision": str(doc.modified) if not doc.is_new() else None,
    }


def operation_key(request_id):
    return wire.digest(["landed_cost", frappe.session.user, wire.request_uuid(request_id)])


def abandoned(ctx, key):
    record = frappe.db.get_value(TOMBSTONE, key, ["actor", "brand"], as_dict=True, for_update=True)
    if record and (record.actor != frappe.session.user or record.brand != ctx["brand"]):
        frappe.throw("Intento de otro negocio o usuario", frappe.PermissionError)
    return bool(record)


def saved(ctx, name, *, allow_cancelled=False):
    doc = frappe.get_doc(DOCTYPE, name, for_update=True)
    doc.check_permission("read")
    if doc.omp_business_brand != ctx["brand"] or doc.omp_actor != frappe.session.user:
        frappe.throw("Operación de otro negocio o usuario", frappe.PermissionError)
    if doc.company != ctx["company"]:
        frappe.throw("Comprobante de otra empresa", frappe.PermissionError)
    if doc.docstatus == 2:
        if not allow_cancelled:
            native.conflict("El comprobante fue cancelado; no se recreará al reintentar")
        return doc, []
    if doc.vendor_invoices:
        raise ValueError("Revise empresa y facturas de servicios en el formulario nativo")
    refs = [
        {"doctype": r.receipt_document_type, "name": r.receipt_document}
        for r in doc.purchase_receipts
    ]
    if any(r["doctype"] not in ("Purchase Receipt", "Purchase Invoice") for r in refs):
        raise ValueError("Tipo de recepción no admitido")
    docs = sources(ctx, sorted(refs, key=lambda r: (r["doctype"], r["name"])))
    return doc, docs


def result(ctx, doc, docs):
    if doc.docstatus == 2:
        return {"status": "cancelled", "voucher": doc.name}
    if doc.docstatus == 1:
        preview = json.loads(doc.omp_result_json)
    else:
        # Native drafts may be adjusted in Desk. Recheck their actual configuration.
        data = selection(
            {
                "brand": ctx["brand"],
                "basis": doc.distribute_charges_based_on,
                "receipts": [{"doctype": d.doctype, "name": d.name} for d in docs],
                "charges": [
                    {
                        "account": r.expense_account,
                        "currency": r.account_currency,
                        "amount": str(number(r.amount)),
                        "exchange_rate": str(number(r.exchange_rate)),
                        "description": r.description,
                    }
                    for r in doc.taxes
                ],
            }
        )
        validate_charges(ctx, data["charges"])
        # Rebuild items from receipts; never trust edits to the draft's item table.
        doc.get_items_from_purchase_receipts()
        doc.validate()
        preview = plan(ctx, doc, docs)
    return {
        "status": "submitted" if doc.docstatus == 1 else "draft",
        "voucher": doc.name,
        "plan": preview,
        "plan_hash": wire.digest(preview),
    }


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def preview(data):
    data = selection(data)
    ctx = context(data["brand"])
    doc, docs = build(ctx, data)
    value = plan(ctx, doc, docs)
    return {"plan": value, "plan_hash": wire.digest(value)}


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def save(data, request_id, plan_hash, submit=0):
    data = selection(data)
    if type(submit) is not int or submit not in (0, 1):
        raise ValueError("Acción inválida")
    ctx = context(data["brand"])
    key = operation_key(request_id)
    if abandoned(ctx, key):
        native.conflict("El intento fue abandonado; prepare una nueva distribución")
    # Current locking read, including after waiting for a concurrent request.
    names = frappe.db.sql(
        f"SELECT name FROM `tab{DOCTYPE}` WHERE omp_operation_key=%s FOR UPDATE", key
    )
    if names:
        doc, docs = saved(ctx, names[0][0])
        if doc.omp_payload_hash != wire.digest({"data": data, "submit": submit}):
            native.conflict("La clave ya corresponde a otro contenido o acción")
        return result(ctx, doc, docs)
    doc, docs = build(ctx, data)
    value = plan(ctx, doc, docs)
    if wire.digest(value) != plan_hash:
        native.conflict("La compra o el cálculo cambió. Revise una nueva vista previa")
    doc.omp_operation_key = key
    doc.omp_payload_hash = wire.digest({"data": data, "submit": submit})
    doc.omp_business_brand = ctx["brand"]
    doc.omp_actor = frappe.session.user
    doc.omp_result_json = wire.canonical(value)
    doc.insert()
    if submit:
        with submission():
            doc.submit()
    return result(ctx, doc, docs)


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def status(brand, request_id):
    ctx = context(wire.identifier(brand))
    key = operation_key(request_id)
    if abandoned(ctx, key):
        return {"status": "abandoned"}
    rows = frappe.db.sql(
        f"SELECT name FROM `tab{DOCTYPE}` WHERE omp_operation_key=%s FOR UPDATE",
        key,
    )
    if not rows:
        return {"status": "not_found"}
    doc, docs = saved(ctx, rows[0][0], allow_cancelled=True)
    return result(ctx, doc, docs)


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def abandon(brand, request_id):
    ctx = context(wire.identifier(brand))
    key = operation_key(request_id)
    if abandoned(ctx, key):
        return {"status": "abandoned"}
    rows = frappe.db.sql(
        f"SELECT name FROM `tab{DOCTYPE}` WHERE omp_operation_key=%s FOR UPDATE", key
    )
    if rows:
        doc, docs = saved(ctx, rows[0][0], allow_cancelled=True)
        return result(ctx, doc, docs)
    # The shared profile/brand locks fence a save already in flight before this marker.
    native.journal(TOMBSTONE, key, {"actor": frappe.session.user, "brand": ctx["brand"]})
    return {"status": "abandoned"}


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def submit_draft(brand, voucher, plan_hash):
    ctx = context(wire.identifier(brand))
    doc, docs = saved(ctx, wire.identifier(voucher))
    current = result(ctx, doc, docs)
    if doc.docstatus == 1:
        return current
    if current["plan_hash"] != plan_hash:
        native.conflict(
            "El borrador o la compra cambió. Consulte el estado y revise antes de enviar"
        )
    doc.check_permission("write")
    doc.omp_result_json = wire.canonical(current["plan"])
    doc.save()
    with submission():
        doc.submit()
    return result(ctx, doc, docs)


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def options(brand):
    ctx = context(wire.identifier(brand))
    currency = frappe.db.get_value("Company", ctx["company"], "default_currency")
    accounts = frappe.get_list(
        "Account",
        filters={
            "company": ctx["company"],
            "is_group": 0,
            "disabled": 0,
            "account_type": "Expenses Included In Valuation",
        },
        fields=["name", "account_currency"],
        limit_page_length=100,
    )
    receipts = []
    for doctype in ("Purchase Receipt", "Purchase Invoice"):
        filters = {"company": ctx["company"], "docstatus": 1, "is_return": 0}
        if doctype == "Purchase Invoice":
            filters["update_stock"] = 1
        candidates = frappe.get_list(
            doctype,
            filters=filters,
            fields=["name", "posting_date"],
            order_by="posting_date desc, name desc",
            limit_page_length=50,
        )
        for r in candidates:
            # Only show entirely owned receipts; the write path rechecks under locks.
            items = frappe.get_all(
                doctype + " Item", filters={"parent": r.name}, fields=["item_code", "warehouse"]
            )
            if items and all(
                i.warehouse == ctx["warehouse"]
                and frappe.db.get_value("Item", i.item_code, "omp_business_brand") == brand
                for i in items
            ):
                receipts.append({"doctype": doctype, "name": r.name, "date": str(r.posting_date)})
    return {"currency": currency, "accounts": accounts, "receipts": receipts}
