"""Online COP checkout using native Sales Invoice, stock ledger and accounting.

All business authorization precedes idempotency lookup. Internal journals use
private low-level inserts; native financial documents never ignore permissions.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal
from functools import wraps
from uuid import uuid4

import frappe
from frappe.utils import add_to_date, cint, get_datetime, now_datetime, nowdate

from open_multi_pos import checkout_contract as contract
from open_multi_pos.api import get_brand_context
from open_multi_pos.checkout_permissions import native_documents


class CheckoutConflict(frappe.ValidationError):
    http_status_code = 409


def conflict(message):
    frappe.throw(message, CheckoutConflict)


def contract_errors(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ValueError as exc:
            frappe.throw("Solicitud de caja inválida: " + str(exc))
        except frappe.QueryDeadlockError:
            conflict(
                "Solicitud concurrente abortada. Consulte el estado y reintente con la misma clave; no repita el cobro externo."
            )

    return wrapped


def terminal_context(name, *, lock=False):
    user = frappe.session.user
    if user == "Guest" or "OMP Cashier" not in frappe.get_roles(user):
        frappe.throw("Se requiere un cajero autenticado", frappe.PermissionError)
    terminal = frappe.get_doc("OMP POS Terminal", contract.identifier(name))
    terminal.check_permission("read")
    if not terminal.enabled or terminal.user != user:
        frappe.throw("Terminal no autorizada", frappe.PermissionError)
    context = get_brand_context(terminal.brand)
    if lock:
        # Every service opening/checkout/closing takes this common profile lock.
        # Inventory also uses sorted item/bin locks across different profiles.
        frappe.db.get_value("POS Profile", context["pos_profile"], "name", for_update=True)
        terminal = frappe.get_doc("OMP POS Terminal", terminal.name, for_update=True)
        context = get_brand_context(terminal.brand)
        if not terminal.enabled or terminal.user != user:
            frappe.throw("Terminal no autorizada", frappe.PermissionError)
    profile = frappe.get_doc("POS Profile", context["pos_profile"])
    return terminal, context, profile


def checkout_configuration(profile):
    company = frappe.get_doc("Company", profile.company)
    warehouse = frappe.get_doc("Warehouse", profile.warehouse)
    if not profile.currency or profile.currency != company.default_currency:
        frappe.throw("La moneda de caja debe coincidir con la entidad legal")
    if frappe.db.count("OMP Business Brand", {"pos_profile": profile.name}) != 1:
        frappe.throw(
            "Cada marca requiere un perfil POS exclusivo; puede compartir empresa y almacén"
        )
    if frappe.db.get_single_value("POS Settings", "invoice_type") != "Sales Invoice":
        frappe.throw("Configure Sales Invoice en POS Settings para contabilización inmediata")
    if not profile.update_stock or warehouse.is_group or warehouse.disabled:
        frappe.throw("Se requiere almacén activo y actualización de stock")
    if profile.get("enable_fbr_integration"):
        frappe.throw("Desactive la integración fiscal antes de usar esta caja")
    if profile.get("auto_set_delivery_charges"):
        frappe.throw("Cargos de entrega automáticos fuera del alcance de este incremento")
    price_list = frappe.get_doc("Price List", profile.selling_price_list)
    if not price_list.enabled or not price_list.selling or price_list.currency != profile.currency:
        frappe.throw("La lista de precios debe usar la moneda de caja")


def active_opening(terminal, profile, name=None):
    name = name or terminal.opening_entry
    if not name:
        conflict("Abra la caja antes de cotizar o cobrar")
    opening = locked_opening(name)
    opening.check_permission("read")
    if (
        opening.user != terminal.user
        or opening.pos_profile != profile.name
        or opening.company != profile.company
    ):
        frappe.throw("Apertura no autorizada", frappe.PermissionError)
    if opening.docstatus != 1 or opening.status != "Open":
        conflict("La apertura ya no está activa")
    if opening.period_start_date.date().isoformat() != nowdate():
        conflict("Cierre la apertura anterior antes de continuar")
    return opening


def locked_opening(name):
    # REPEATABLE READ can retain the pre-lock auth snapshot. Compare a snapshot
    # read with a current locking read: a completed sale advances this revision
    # in the same transaction. Never build a closing from an older invoice view.
    snapshot = frappe.db.get_value(
        "POS Opening Entry", name, ["omp_checkout_revision", "status"], as_dict=True
    )
    opening = frappe.get_doc("POS Opening Entry", name, for_update=True)
    if (
        not snapshot
        or cint(snapshot.omp_checkout_revision) != cint(opening.get("omp_checkout_revision"))
        or snapshot.status != opening.status
    ):
        conflict("La sesión cambió durante esta solicitud; consulte y reintente con la misma clave")
    return opening


def payment_modes(profile):
    modes = {}
    for row in profile.payments:
        mode = frappe.get_doc("Mode of Payment", row.mode_of_payment)
        if not mode.enabled or mode.type not in ("Cash", "Bank"):
            continue
        account = next(
            (a.default_account for a in mode.accounts if a.company == profile.company), None
        )
        if not account:
            continue
        ledger = frappe.get_doc("Account", account)
        if (
            ledger.disabled
            or ledger.is_group
            or ledger.company != profile.company
            or ledger.account_currency != profile.currency
            or ledger.account_type != mode.type
        ):
            continue
        modes[mode.name] = {"type": mode.type, "account": account}
    if not modes:
        frappe.throw("Configure medios de pago con cuentas COP de la empresa")
    return modes


def validate_modes(rows, modes, *, complete=False):
    names = {row["mode_of_payment"] for row in rows}
    if not names <= modes.keys() or (complete and names != modes.keys()):
        frappe.throw("Medios de pago no autorizados o incompletos", frappe.PermissionError)


def group_allowed(doctype, name, allowed):
    if not allowed:
        return True
    node = frappe.get_doc(doctype, name)
    for row in allowed:
        parent = frappe.get_doc(doctype, row.get(doctype.lower().replace(" ", "_")))
        if parent.lft <= node.lft and parent.rgt >= node.rgt:
            return True
    return False


def simple_sale_item(item):
    return not (
        item.disabled
        or not item.is_sales_item
        or item.has_variants
        or item.is_fixed_asset
        or item.has_batch_no
        or item.has_serial_no
        or frappe.db.exists("Product Bundle", item.name)
    )


def validate_catalog(profile, customer_name, rows, *, stock=False):
    customer = frappe.get_doc("Customer", customer_name)
    customer.check_permission("read")
    if customer.disabled or not group_allowed(
        "Customer Group", customer.customer_group, profile.customer_groups
    ):
        frappe.throw("Cliente no habilitado en el perfil")
    for row in rows:
        if stock:
            frappe.db.get_value("Item", row["item_code"], "name", for_update=True)
        item = frappe.get_doc("Item", row["item_code"])
        item.check_permission("read")
        owner = item.get("omp_business_brand")
        if (
            owner
            and frappe.db.get_value("OMP Business Brand", owner, "pos_profile") != profile.name
        ):
            frappe.throw("El artículo pertenece a otro negocio", frappe.PermissionError)
        if not simple_sale_item(item):
            frappe.throw("Artículo no habilitado para venta")
        if not group_allowed("Item Group", item.item_group, profile.item_groups):
            frappe.throw("Artículo fuera de los grupos autorizados", frappe.PermissionError)
        if stock and item.is_stock_item:
            qty = frappe.db.get_value(
                "Bin",
                {"item_code": item.name, "warehouse": profile.warehouse},
                "actual_qty",
                for_update=True,
            )
            if Decimal(str(qty or 0)) < row["qty"]:
                conflict("Stock insuficiente en el almacén autorizado")


def build_invoice(profile, customer, rows):
    doc = frappe.get_doc(
        {
            "doctype": "Sales Invoice",
            "is_pos": 1,
            "is_created_using_pos": 1,
            "company": profile.company,
            "pos_profile": profile.name,
            "customer": customer,
            "set_warehouse": profile.warehouse,
            "update_stock": 1,
            "currency": profile.currency,
            "conversion_rate": 1,
            "price_list_currency": profile.currency,
            "plc_conversion_rate": 1,
            "selling_price_list": profile.selling_price_list,
            "posting_date": nowdate(),
            "disable_rounded_total": cint(profile.disable_rounded_total),
            "items": [
                {
                    **row,
                    "warehouse": profile.warehouse,
                    "uom": frappe.db.get_value("Item", row["item_code"], "stock_uom"),
                    "conversion_factor": 1,
                }
                for row in rows
            ],
        }
    )
    doc.set_missing_values()
    doc.calculate_taxes_and_totals()
    if len(doc.items) != len(rows) or any(
        row.uom != row.stock_uom or row.conversion_factor != 1 or row.stock_qty != row.qty
        for row in doc.items
    ):
        frappe.throw("Este incremento vende unidades enteras de la unidad de inventario")
    if doc.selling_price_list != profile.selling_price_list:
        frappe.throw("La lista del cliente difiere de la lista del perfil")
    if any(not row.price_list_rate or row.rate < 0 for row in doc.items):
        frappe.throw("Configure precios de venta para todos los artículos")
    if doc.currency != profile.currency or doc.company != profile.company or not doc.update_stock:
        frappe.throw("Configuración nativa de factura incoherente")
    return doc


def money(value):
    result = Decimal(str(value or 0))
    if not result.is_finite() or result != result.quantize(Decimal(".01")):
        frappe.throw("La precisión monetaria nativa excede dos decimales")
    return result.quantize(Decimal(".01"))


def financial(doc):
    def values(row, fields):
        result = {}
        for key in fields:
            value = row.get(key)
            if isinstance(value, (int, float, Decimal)):
                value = format(Decimal(str(value)).normalize(), "f")
            result[key] = str(value if value is not None else "")
        return result

    return {
        **values(
            doc,
            (
                "company",
                "pos_profile",
                "set_warehouse",
                "customer",
                "currency",
                "selling_price_list",
                "grand_total",
                "rounded_total",
                "net_total",
                "total_taxes_and_charges",
                "disable_rounded_total",
                "debit_to",
                "account_for_change_amount",
            ),
        ),
        "items": [
            values(
                row,
                (
                    "item_code",
                    "qty",
                    "stock_qty",
                    "uom",
                    "warehouse",
                    "rate",
                    "price_list_rate",
                    "discount_percentage",
                    "net_rate",
                    "net_amount",
                    "amount",
                    "income_account",
                    "expense_account",
                    "cost_center",
                    "item_tax_template",
                ),
            )
            for row in doc.items
        ],
        "taxes": [
            values(
                row,
                (
                    "charge_type",
                    "account_head",
                    "rate",
                    "tax_amount",
                    "included_in_print_rate",
                    "cost_center",
                ),
            )
            for row in doc.taxes
        ],
    }


def invoice_total(doc):
    return money(
        doc.grand_total if doc.disable_rounded_total else doc.rounded_total or doc.grand_total
    )


def journal(doctype, name, fields):
    # Private journals have no public create/write permission. Every supplied
    # field is built here after terminal and native context authorization.
    doc = frappe.get_doc({"doctype": doctype, "name": name, **fields})
    doc.creation = doc.modified = now_datetime()
    doc.owner = doc.modified_by = frappe.session.user
    doc.docstatus = 0
    doc.db_insert()
    return doc


@frappe.whitelist(methods=["POST"])
@contract_errors
def quote(data: str | dict):
    data = contract.mapping(data, ("terminal", "customer", "items"))
    rows = contract.items(data["items"])
    customer = contract.identifier(data["customer"])
    terminal, context, profile = terminal_context(data["terminal"], lock=True)
    checkout_configuration(profile)
    opening = active_opening(terminal, profile)
    validate_catalog(profile, customer, rows)
    doc = build_invoice(profile, customer, rows)
    total = invoice_total(doc)
    if total <= 0:
        frappe.throw("El total debe ser positivo")
    quote_id = str(uuid4())
    result = {
        "quote": quote_id,
        "currency": profile.currency,
        "total": str(total),
        "taxes": str(money(doc.total_taxes_and_charges)),
        "items": [
            {
                "item_code": r.item_code,
                "item_name": r.item_name,
                "qty": r.qty,
                "rate": str(money(r.rate)),
                "amount": str(money(r.amount)),
            }
            for r in doc.items
        ],
        "payment_modes": list(payment_modes(profile)),
        "opening_entry": opening.name,
    }
    journal(
        "OMP Checkout Quote",
        quote_id,
        {
            "terminal": terminal.name,
            "actor": terminal.user,
            "brand": terminal.brand,
            "opening_entry": opening.name,
            "valid_until": add_to_date(now_datetime(), minutes=10),
            "request_json": contract.canonical({"customer": customer, "items": rows}),
            "financial_hash": contract.digest(financial(doc)),
            "result_json": contract.canonical(result),
        },
    )
    return result


def authorized_quote(name, terminal):
    doc = frappe.get_doc("OMP Checkout Quote", contract.identifier(name))
    if (
        doc.terminal != terminal.name
        or doc.actor != frappe.session.user
        or doc.brand != terminal.brand
    ):
        frappe.throw("Cotización no autorizada", frappe.PermissionError)
    return doc


def saved_sale(record, terminal):
    if (
        record.actor != terminal.user
        or record.terminal != terminal.name
        or record.brand != terminal.brand
    ):
        frappe.throw("Transacción no autorizada", frappe.PermissionError)
    if record.get("abandoned"):
        return {"status": "abandoned", "request_id": record.request_id}
    if not record.invoice or not record.receipt_json:
        conflict("Transacción no completada; consulte el estado con la misma clave")
    doc = frappe.get_doc("Sales Invoice", record.invoice)
    doc.check_permission("read")
    if doc.docstatus != 1:
        conflict("La factura original ya no está enviada; no cree otra venta como reintento")
    return {
        "status": "completed",
        "invoice": doc.name,
        "receipt": json.loads(record.receipt_json),
        "duplicate": True,
    }


def claim_request(terminal, request_id, quote_doc, payload):
    key = contract.operation_key(terminal.name, request_id)
    hashed = contract.digest(payload)
    timestamp = now_datetime()
    # Both the request key and quote are database-unique. A new UUID cannot sell
    # the same quote again. This insert and the native invoice share one transaction.
    frappe.db.sql(
        """INSERT INTO `tabOMP Checkout Request`
        (name,creation,modified,owner,modified_by,docstatus,terminal,request_id,actor,brand,quote,payload_hash)
        VALUES (%s,%s,%s,%s,%s,0,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE name=name""",
        (
            key,
            timestamp,
            timestamp,
            terminal.user,
            terminal.user,
            terminal.name,
            request_id,
            terminal.user,
            terminal.brand,
            quote_doc.name,
            hashed,
        ),
    )
    rows = frappe.db.sql(
        "SELECT * FROM `tabOMP Checkout Request` WHERE name=%s FOR UPDATE", (key,), as_dict=True
    )
    if not rows:
        conflict("Cotización ya utilizada con otra clave; consulte la venta original")
    record = rows[0]
    if record.payload_hash != hashed:
        conflict("La clave ya pertenece a otra solicitud")
    return record


def apply_payments(doc, rows, profile):
    modes = payment_modes(profile)
    validate_modes(rows, modes)
    total = invoice_total(doc)
    paid = sum((Decimal(row["amount"]) for row in rows), Decimal(0))
    change = paid - total
    cash_rows = [row for row in rows if modes[row["mode_of_payment"]]["type"] == "Cash"]
    if change < 0:
        frappe.throw("El pago debe cubrir el total")
    if change and (len(cash_rows) != 1 or change > Decimal(cash_rows[0]["amount"])):
        frappe.throw("El cambio solo puede devolverse del efectivo recibido")
    if (
        change
        and doc.account_for_change_amount != modes[cash_rows[0]["mode_of_payment"]]["account"]
    ):
        frappe.throw("Configure la cuenta de cambio igual a la cuenta de efectivo")
    doc.set("payments", [])
    for row in rows:
        # Float conversion is confined to ERPNext's native currency fields; own
        # validation, hashing and snapshots use Decimal/decimal strings.
        doc.append(
            "payments",
            {
                **row,
                "amount": float(Decimal(row["amount"])),
                "account": modes[row["mode_of_payment"]]["account"],
                "type": modes[row["mode_of_payment"]]["type"],
            },
        )
    doc.calculate_taxes_and_totals()
    if money(doc.change_amount) != change:
        frappe.throw("El cambio calculado por ERPNext no coincide")
    return change


def receipt_snapshot(doc, context, request_id, opening):
    def cents(value):
        return int(money(value) * 100)

    return {
        "version": 1,
        "id": doc.name,
        "request_id": request_id,
        "opening_entry": opening,
        "fiscal_status": "not_configured",
        "fiscal_issued": False,
        "label": "RECIBO INTERNO · SIN VALIDEZ FISCAL",
        "created_at": datetime.now(UTC).isoformat(),
        "time_zone": frappe.db.get_single_value("OMP Workspace Settings", "time_zone")
        or "America/Bogota",
        "currency": doc.currency,
        "brand": {
            "id": context["brand"],
            "name": context["display_name"],
            "company": context["company"],
            "warehouse": context["warehouse"],
            "pos_profile": context["pos_profile"],
            "printer_profile": context["printer_profile"],
            "footer": context["footer"],
            "qr_url": context["qr_url"],
            "receipt_details": context.get("receipt_details", {}),
        },
        "items": [
            {
                "item_code": r.item_code,
                "name": r.item_name,
                "qty": r.qty,
                "rate": cents(r.rate),
                "amount": cents(r.amount),
                "net_amount": cents(r.net_amount),
            }
            for r in doc.items
        ],
        "total": cents(invoice_total(doc)),
        "taxes": cents(doc.total_taxes_and_charges),
        "payments": [
            {
                "mode_of_payment": p.mode_of_payment,
                "kind": frappe.db.get_value("Mode of Payment", p.mode_of_payment, "type"),
                "amount": cents(p.amount),
                "reference_no": p.reference_no or "",
                "verified_externally": False,
            }
            for p in doc.payments
        ],
        "change": cents(doc.change_amount),
    }


@frappe.whitelist(methods=["POST"])
@contract_errors
def checkout(data: str | dict):
    data = contract.mapping(data, ("terminal", "request_id", "quote", "payments"))
    request_id = contract.request_uuid(data["request_id"])
    rows = contract.payments(data["payments"])
    terminal, context, profile = terminal_context(data["terminal"], lock=True)
    quote_doc = authorized_quote(data["quote"], terminal)
    payload = {"quote": quote_doc.name, "payments": rows}
    record = claim_request(terminal, request_id, quote_doc, payload)
    if record.get("abandoned"):
        conflict("Intento liberado; esta clave y cotización ya no pueden vender")
    if record.invoice:
        locked_opening(
            quote_doc.opening_entry
        )  # Historical/closed replay, but never a stale read view.
        return saved_sale(record, terminal)
    checkout_configuration(profile)
    opening = active_opening(terminal, profile, quote_doc.opening_entry)
    if terminal.opening_entry != opening.name:
        conflict("La cotización pertenece a otra apertura")
    if get_datetime(quote_doc.valid_until) < now_datetime():
        conflict("Cotización vencida; vuelva a cotizar antes de cobrar")
    source = json.loads(quote_doc.request_json)
    validate_catalog(profile, source["customer"], source["items"], stock=True)
    doc = build_invoice(profile, source["customer"], source["items"])
    if contract.digest(financial(doc)) != quote_doc.financial_hash:
        conflict("Precios o configuración cambiaron; solicite otra cotización")
    apply_payments(doc, rows, profile)
    with native_documents(doc):
        doc.insert()
        if contract.digest(financial(doc)) != quote_doc.financial_hash:
            conflict("La validación nativa cambió la cotización")
        doc.submit()
        if contract.digest(financial(doc)) != quote_doc.financial_hash:
            conflict("El envío nativo cambió la cotización")
    receipt = receipt_snapshot(doc, context, request_id, opening.name)
    frappe.db.set_value(
        "POS Opening Entry",
        opening.name,
        "omp_checkout_revision",
        cint(opening.get("omp_checkout_revision")) + 1,
    )
    frappe.db.set_value(
        "OMP Checkout Request",
        record.name,
        {"invoice": doc.name, "receipt_json": contract.canonical(receipt)},
    )
    return {"status": "completed", "invoice": doc.name, "receipt": receipt, "duplicate": False}


@frappe.whitelist(methods=["GET", "POST"])
@contract_errors
def get_status(terminal: str, request_id: str):
    terminal, _, _ = terminal_context(terminal)
    key = contract.operation_key(terminal.name, request_id)
    if not frappe.db.exists("OMP Checkout Request", key):
        return {"status": "not_found", "request_id": request_id, "retry_with_same_key": True}
    record = frappe.get_doc("OMP Checkout Request", key)
    return saved_sale(record, terminal)


@frappe.whitelist(methods=["POST"])
@contract_errors
def abandon_checkout(data: str | dict):
    """Fence delayed checkout requests before the UI may release an uncertain cart.

    The profile lock waits for in-flight sales. A unique tombstone then prevents
    a delayed request from selling this quote/key, even after this POST commits.
    This only resolves the invoice attempt; it never refunds an external payment.
    """
    data = contract.mapping(data, ("terminal", "request_id", "quote", "payments"))
    request_id = contract.request_uuid(data["request_id"])
    rows = contract.payments(data["payments"])
    terminal, _, _ = terminal_context(data["terminal"], lock=True)
    quote_doc = authorized_quote(data["quote"], terminal)
    record = claim_request(
        terminal, request_id, quote_doc, {"quote": quote_doc.name, "payments": rows}
    )
    if record.invoice:
        locked_opening(quote_doc.opening_entry)
        return saved_sale(record, terminal)
    frappe.db.set_value("OMP Checkout Request", record.name, "abandoned", 1)
    return {"status": "abandoned", "request_id": request_id}


@frappe.whitelist(methods=["POST"])
@contract_errors
def open_shift(data: str | dict):
    data = contract.mapping(data, ("terminal", "balances"))
    rows = contract.payments(data["balances"], zero=True)
    terminal, _, profile = terminal_context(data["terminal"], lock=True)
    checkout_configuration(profile)
    modes = payment_modes(profile)
    validate_modes(rows, modes, complete=True)
    if terminal.opening_entry:
        old = frappe.get_doc("POS Opening Entry", terminal.opening_entry)
        if old.docstatus == 1 and old.status == "Open":
            active_opening(terminal, profile)
            expected = {r.mode_of_payment: money(r.opening_amount) for r in old.balance_details}
            if expected != {r["mode_of_payment"]: Decimal(r["amount"]) for r in rows}:
                conflict("La apertura existente tiene otros saldos")
            return {"opening_entry": old.name, "duplicate": True}
    doc = frappe.get_doc(
        {
            "doctype": "POS Opening Entry",
            "company": profile.company,
            "pos_profile": profile.name,
            "user": terminal.user,
            "period_start_date": now_datetime(),
            "balance_details": [
                {
                    "mode_of_payment": row["mode_of_payment"],
                    "opening_amount": float(Decimal(row["amount"])),
                }
                for row in rows
            ],
        }
    )
    with native_documents(doc):
        doc.insert()
        doc.submit()
    frappe.db.set_value("OMP POS Terminal", terminal.name, "opening_entry", doc.name)
    return {"opening_entry": doc.name, "duplicate": False}


def closing_context(terminal_name, opening_name):
    terminal, _, profile = terminal_context(terminal_name, lock=True)
    checkout_configuration(profile)
    opening = locked_opening(contract.identifier(opening_name))
    opening.check_permission("read")
    if (
        opening.user != terminal.user
        or opening.pos_profile != profile.name
        or opening.company != profile.company
        or opening.docstatus != 1
    ):
        frappe.throw("Apertura no autorizada", frappe.PermissionError)
    return terminal, profile, opening


def build_closing(opening):
    from erpnext.accounts.doctype.pos_closing_entry.pos_closing_entry import (
        make_closing_entry_from_opening,
    )

    doc = make_closing_entry_from_opening(opening)
    rows = {r.mode_of_payment: r for r in doc.payment_reconciliation}
    # ERPNext's builder summarizes net tenders. Include opening floats, also
    # preserving configured modes that had no sales in this session.
    for balance in opening.balance_details:
        row = rows.get(balance.mode_of_payment)
        if row is None:
            row = doc.append(
                "payment_reconciliation",
                {"mode_of_payment": balance.mode_of_payment, "expected_amount": 0},
            )
        row.opening_amount = balance.opening_amount
        row.expected_amount = float(money(row.expected_amount) + money(balance.opening_amount))
    return doc


def closing_summary(doc):
    return {
        "opening_entry": doc.pos_opening_entry,
        "closing_entry": doc.name if not doc.is_new() else None,
        "status": doc.status or "Draft",
        "total": str(money(doc.grand_total)),
        "invoice_count": len(doc.sales_invoices),
        "payments": [
            {
                "mode_of_payment": r.mode_of_payment,
                "opening": str(money(r.opening_amount)),
                "expected": str(money(r.expected_amount)),
                "counted": str(money(r.closing_amount)),
                "difference": str(money(r.difference)),
            }
            for r in doc.payment_reconciliation
        ],
    }


@frappe.whitelist(methods=["POST"])
@contract_errors
def shift_summary(terminal: str, opening_entry: str):
    _, _, opening = closing_context(terminal, opening_entry)
    if opening.status == "Closed":
        return closing_summary(frappe.get_doc("POS Closing Entry", opening.pos_closing_entry))
    if opening.status != "Open":
        conflict("Apertura no activa")
    return closing_summary(build_closing(opening))


@frappe.whitelist(methods=["POST"])
@contract_errors
def close_shift(data: str | dict):
    data = contract.mapping(data, ("terminal", "opening_entry", "counts"))
    rows = contract.payments(data["counts"], zero=True)
    _, profile, opening = closing_context(data["terminal"], data["opening_entry"])
    if opening.status == "Closed":
        doc = frappe.get_doc("POS Closing Entry", opening.pos_closing_entry)
        prior = {r.mode_of_payment: money(r.closing_amount) for r in doc.payment_reconciliation}
        if prior != {r["mode_of_payment"]: Decimal(r["amount"]) for r in rows}:
            conflict("El cierre existente tiene otros conteos")
        # Native closing commits internally before updating invoice associations.
        # A retry safely repairs those links; it never reposts stock or payments.
        doc.update_sales_invoices_closing_entry()
        return {**closing_summary(doc), "duplicate": True}
    if opening.status != "Open":
        conflict("Apertura no activa")
    validate_modes(rows, payment_modes(profile), complete=True)
    doc = build_closing(opening)
    counts = {r["mode_of_payment"]: Decimal(r["amount"]) for r in rows}
    for row in doc.payment_reconciliation:
        row.closing_amount = float(counts[row.mode_of_payment])
        row.difference = float(counts[row.mode_of_payment] - money(row.expected_amount))
    with native_documents(doc, ("POS Opening Entry", opening.name)):
        doc.insert()
        doc.submit()
    return {**closing_summary(doc), "duplicate": False}
