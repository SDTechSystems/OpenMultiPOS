"""Administrative workspace using native ERPNext documents and permissions."""

from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import frappe
from frappe.utils import nowdate, validate_email_address

from open_multi_pos import checkout as sale
from open_multi_pos import checkout_contract as wire
from open_multi_pos.api import get_brand_context
from open_multi_pos.permissions import manager
from open_multi_pos.sku import business_initials, sku_code, validate_prefix

ADMIN_ROLES = (
    "OMP Administrator",
    "System Manager",
    "Sales Master Manager",
    "Purchase Master Manager",
    "Sales Manager",
    "Sales User",
    "Item Manager",
    "Purchase Manager",
    "Purchase User",
    "Stock Manager",
    "Stock User",
    "Accounts Manager",
    "Accounts User",
    "OMP Cashier",
)
BRAND_FIELDS = (
    "display_name",
    "sku_prefix",
    "legal_name",
    "tax_id",
    "phone",
    "email",
    "address",
    "receipt_footer",
    "qr_url",
)
RECEIPT_FIELDS = tuple(
    "receipt_show_" + k
    for k in ("legal_name", "tax_id", "phone", "email", "address", "footer", "qr")
)
DEFAULTS = {
    "interface_language": "es",
    "locale": "es-CO",
    "default_currency": "COP",
    "time_zone": "America/Bogota",
    "scanner_us": 1,
    "scanner_terminator": "Enter",
    "printer_profile": "jaltech-jal58m",
}


def require_admin():
    if frappe.session.user == "Guest" or not manager(frappe.session.user):
        frappe.throw("Solo un administrador puede usar esta herramienta", frappe.PermissionError)


def clean_text(value, *, maximum=140, required=False):
    if (
        not isinstance(value, str)
        or len(value) > maximum
        or any(ord(c) < 32 and c not in "\n\t" for c in value)
    ):
        raise ValueError("Texto inválido o demasiado largo")
    value = value.strip()
    if required and not value:
        raise ValueError("Complete los campos obligatorios")
    return value


def settings():
    doc = frappe.get_single("OMP Workspace Settings")
    return {
        key: doc.get(key) if doc.get(key) not in (None, "") else default
        for key, default in DEFAULTS.items()
    }


def brand_context(brand):
    require_admin()
    return get_brand_context(wire.identifier(brand))


@frappe.whitelist(methods=["GET"])
def boot():
    require_admin()
    brands = []
    for name in frappe.get_list(
        "OMP Business Brand",
        filters={"enabled": 1, "workspace_visible": 1},
        pluck="name",
        limit=100,
    ):
        brands.append(get_brand_context(name))
    return {
        "user": frappe.session.user,
        "full_name": frappe.db.get_value("User", frappe.session.user, "full_name"),
        "first_setup": not bool(
            frappe.db.sql(
                "SELECT u.name FROM tabUser u INNER JOIN `tabHas Role` r ON r.parent=u.name AND r.parenttype='User' WHERE u.enabled=1 AND r.role='OMP Administrator' LIMIT 1"
            )
        ),
        "businesses": brands,
        "settings": settings(),
        "companies": frappe.get_list("Company", fields=["name", "default_currency"], limit=100),
        "item_groups": frappe.get_list(
            "Item Group", filters={"is_group": 0}, pluck="name", limit=100
        ),
        "currencies": frappe.get_list("Currency", filters={"enabled": 1}, pluck="name", limit=100),
        "suggestions": frappe.db.get_single_value("OMP Workspace Settings", "setup_suggestions")
        or "",
    }


@frappe.whitelist(methods=["POST"])
@sale.contract_errors
def save_settings(data):
    require_admin()
    data = wire.mapping(data, tuple(DEFAULTS))
    if data["interface_language"] not in ("es", "en") or data["locale"] not in (
        "es-CO",
        "es-MX",
        "es-PE",
        "es-CL",
        "en-US",
    ):
        raise ValueError("Idioma o formato regional no disponible")
    if (
        data["scanner_terminator"] not in ("Enter", "Tab")
        or data["printer_profile"] != "jaltech-jal58m"
        or type(data["scanner_us"]) is not int
        or data["scanner_us"] not in (0, 1)
    ):
        raise ValueError("Configuración del equipo no admitida")
    currency = frappe.get_doc("Currency", wire.identifier(data["default_currency"]))
    currency.check_permission("read")
    if not currency.enabled:
        raise ValueError("Moneda deshabilitada")
    try:
        ZoneInfo(data["time_zone"])
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ValueError("Zona horaria inválida") from exc
    doc = frappe.get_single("OMP Workspace Settings")
    doc.update(data)
    doc.save()
    system = frappe.get_single("System Settings")
    system.update(
        {"time_zone": data["time_zone"], "language": system.language or data["interface_language"]}
    ).save()
    frappe.db.set_value("User", frappe.session.user, "language", data["interface_language"])
    frappe.clear_cache(user=frappe.session.user)
    return settings()


@frappe.whitelist(methods=["GET"])
def business(brand):
    context = brand_context(brand)
    doc = frappe.get_doc("OMP Business Brand", brand)
    return {
        **context,
        **{key: doc.get(key) or "" for key in BRAND_FIELDS},
        **{key: int(bool(doc.get(key))) for key in RECEIPT_FIELDS},
    }


@frappe.whitelist(methods=["POST"])
@sale.contract_errors
def save_business(data):
    data = wire.mapping(data, ("brand", *BRAND_FIELDS, *RECEIPT_FIELDS))
    brand_context(data["brand"])
    doc = frappe.get_doc("OMP Business Brand", data["brand"])
    for key in BRAND_FIELDS:
        doc.set(
            key,
            clean_text(
                data[key],
                maximum=500 if key in ("address", "receipt_footer") else 140,
                required=key == "display_name",
            ),
        )
    doc.sku_prefix = validate_prefix(doc.sku_prefix or business_initials(doc.display_name))
    if doc.email:
        validate_email_address(doc.email, throw=True)
    for key in RECEIPT_FIELDS:
        if type(data[key]) is not int or data[key] not in (0, 1):
            raise ValueError("Opción de recibo inválida")
        doc.set(key, data[key])
    doc.printer_profile = "jaltech-jal58m"
    doc.save()
    return business(doc.name)


def account(company, kind, label):
    name = frappe.db.get_value(
        "Account", {"company": company.name, "account_type": kind, "is_group": 0, "disabled": 0}
    )
    if name:
        return name
    parent = frappe.db.get_value(
        "Account",
        {
            "company": company.name,
            "root_type": "Asset",
            "is_group": 1,
            "parent_account": ["in", ("", None)],
        },
    )
    if not parent:
        parent = frappe.get_all(
            "Account",
            filters={"company": company.name, "root_type": "Asset", "is_group": 1},
            order_by="lft",
            pluck="name",
            limit=1,
        )[0]
    return (
        frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": label,
                "parent_account": parent,
                "company": company.name,
                "account_type": kind,
                "account_currency": company.default_currency,
            }
        )
        .insert()
        .name
    )


@frappe.whitelist(methods=["POST"])
@sale.contract_errors
def create_business(data):
    require_admin()
    data = wire.mapping(data, ("display_name", "company", "legal_name", "abbr", "currency"))
    display = clean_text(data["display_name"], maximum=100, required=True)
    if data["company"]:
        company = frappe.get_doc("Company", wire.identifier(data["company"]))
        company.check_permission("write")
    else:
        name = clean_text(data["legal_name"], required=True)
        if frappe.db.exists("Company", name):
            raise ValueError("La entidad ya existe. Selecciónela en el formulario")
        company = frappe.get_doc(
            {
                "doctype": "Company",
                "company_name": name,
                "abbr": clean_text(data["abbr"], maximum=5, required=True),
                "country": "Colombia",
                "default_currency": wire.identifier(data["currency"]),
                "chart_of_accounts": "Standard",
            }
        ).insert()
    frappe.db.get_value("Company", company.name, "name", for_update=True)
    if frappe.db.get_value(
        "OMP Business Brand",
        {"display_name": display, "company": company.name, "enabled": 1},
        "name",
        for_update=True,
    ):
        sale.conflict(
            "Este negocio ya existe en la entidad. Actualiza la página y revisa el selector antes de repetir el alta"
        )
    currency = company.default_currency
    suffix = uuid4().hex[:8]
    warehouse = (
        frappe.get_doc(
            {
                "doctype": "Warehouse",
                "warehouse_name": display + " " + suffix,
                "company": company.name,
            }
        )
        .insert()
        .name
    )
    price_list = (
        frappe.get_doc(
            {
                "doctype": "Price List",
                "price_list_name": "Ventas " + display + " " + suffix,
                "currency": currency,
                "selling": 1,
                "enabled": 1,
            }
        )
        .insert()
        .name
    )
    customer = (
        frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": "Mostrador " + display + " " + suffix,
                "customer_type": "Individual",
                "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
                "territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
                "default_price_list": price_list,
            }
        )
        .insert()
        .name
    )
    payments = []
    for kind, label in (("Cash", "Efectivo"), ("Bank", "Transferencia")):
        ledger = account(company, kind, "Caja principal" if kind == "Cash" else "Cuenta bancaria")
        mode = (
            frappe.get_doc(
                {
                    "doctype": "Mode of Payment",
                    "mode_of_payment": label + " " + display + " " + suffix,
                    "type": kind,
                    "enabled": 1,
                    "accounts": [{"company": company.name, "default_account": ledger}],
                }
            )
            .insert()
            .name
        )
        payments.append({"mode_of_payment": mode, "default": int(kind == "Cash")})
    profile = frappe.get_doc(
        {
            "doctype": "POS Profile",
            "name": "Caja " + display + " " + suffix,
            "company": company.name,
            "warehouse": warehouse,
            "currency": currency,
            "selling_price_list": price_list,
            "customer": customer,
            "payments": payments,
            "update_stock": 1,
            "disable_rounded_total": 1,
            "write_off_account": company.round_off_account or company.default_expense_account,
            "write_off_cost_center": company.cost_center,
            "account_for_change_amount": account(company, "Cash", "Caja principal"),
            "applicable_for_users": [{"user": frappe.session.user}],
        }
    ).insert()
    doc = frappe.get_doc(
        {
            "doctype": "OMP Business Brand",
            "display_name": display,
            "legal_name": company.company_name,
            "company": company.name,
            "warehouse": warehouse,
            "pos_profile": profile.name,
            "printer_profile": "jaltech-jal58m",
            "workspace_visible": 1,
            "allowed_users": []
            if frappe.session.user == "Administrator"
            else [{"user": frappe.session.user}],
        }
    ).insert()
    terminal_for(doc.name)
    return get_brand_context(doc.name)


@frappe.whitelist(methods=["POST"])
@sale.contract_errors
def terminal_for(brand):
    context = brand_context(brand)
    frappe.db.get_value("OMP Business Brand", brand, "name", for_update=True)
    name = frappe.db.get_value(
        "OMP POS Terminal",
        {"brand": brand, "user": frappe.session.user, "enabled": 1},
        for_update=True,
    )
    if not name:
        name = (
            frappe.get_doc(
                {
                    "doctype": "OMP POS Terminal",
                    "brand": brand,
                    "user": frappe.session.user,
                    "display_name": "Caja de " + context["display_name"],
                    "enabled": 1,
                }
            )
            .insert()
            .name
        )
    return {"terminal": name, **context}


@frappe.whitelist(methods=["GET"])
def overview(brand):
    context = brand_context(brand)
    if not frappe.has_permission("Sales Invoice", "read"):
        frappe.throw("No tiene permiso para consultar ventas", frappe.PermissionError)
    invoices = frappe.db.sql(
        """SELECT COUNT(*) AS count, COALESCE(SUM(grand_total),0) AS total FROM `tabSales Invoice` WHERE pos_profile=%s AND docstatus=1 AND posting_date=%s""",
        (context["pos_profile"], nowdate()),
        as_dict=True,
    )[0]
    recent = frappe.get_list(
        "Sales Invoice",
        filters={"pos_profile": context["pos_profile"], "docstatus": 1},
        fields=["name", "posting_date", "grand_total", "currency", "customer"],
        order_by="creation desc",
        limit=10,
    )
    for row in recent:
        row.grand_total = str(sale.money(row.grand_total))
    return {
        "count": invoices["count"],
        "total": str(sale.money(invoices["total"])),
        "currency": frappe.db.get_value("POS Profile", context["pos_profile"], "currency"),
        "recent": recent,
    }


@frappe.whitelist(methods=["GET"])
def inventory(brand, text=""):
    context = brand_context(brand)
    pattern = "%" + clean_text(text).replace("%", "\\%").replace("_", "\\_") + "%"
    stocks = frappe.get_all(
        "Bin",
        filters={"warehouse": context["warehouse"]},
        fields=["item_code", "actual_qty"],
        limit=1000,
    )
    quantities = {row.item_code: row.actual_qty for row in stocks}
    rows = frappe.get_list(
        "Item",
        filters={"disabled": 0, "item_name": ["like", pattern]},
        or_filters={"omp_business_brand": brand, "name": ["in", list(quantities) or [""]]},
        fields=["name", "item_name", "stock_uom", "omp_business_brand"],
        order_by="item_name",
        limit=100,
    )
    rows = [row for row in rows if not row.omp_business_brand or row.omp_business_brand == brand]
    for row in rows:
        row["qty"] = quantities.get(row.name, 0)
        row["barcodes"] = frappe.get_all(
            "Item Barcode", filters={"parent": row.name}, pluck="barcode", limit=5
        )
        row["price"] = str(
            sale.money(
                frappe.db.get_value(
                    "Item Price",
                    {
                        "item_code": row.name,
                        "price_list": frappe.db.get_value(
                            "POS Profile", context["pos_profile"], "selling_price_list"
                        ),
                    },
                    "price_list_rate",
                )
            )
        )
    return {"items": rows, "warehouse": context["warehouse"]}


@frappe.whitelist(methods=["POST"])
@sale.contract_errors
def create_product(data):
    data = wire.mapping(
        data, ("brand", "code", "name", "barcode", "price", "item_group", "request_id")
    )
    context = brand_context(data["brand"])
    key = wire.digest(["product", frappe.session.user, wire.request_uuid(data["request_id"])])
    hashed = wire.digest(data)
    frappe.db.get_value("OMP Business Brand", data["brand"], "name", for_update=True)
    existing = frappe.db.get_value(
        "Item",
        {"omp_operation_key": key},
        ["name", "omp_payload_hash"],
        as_dict=True,
        for_update=True,
    )
    if existing:
        if existing.omp_payload_hash != hashed:
            sale.conflict("El intento pertenece a otro producto. Revisa el producto ya creado")
        frappe.get_doc("Item", existing.name).check_permission("read")
        return {"item_code": existing.name, "duplicate": True}
    code = clean_text(data["code"])
    name = clean_text(data["name"], required=True)
    if not code:
        from frappe.model.naming import getseries

        prefix = context["sku_prefix"]
        series = "OMP-SKU-" + prefix
        frappe.db.sql(
            "INSERT INTO tabSeries (name,current) VALUES (%s,0) ON DUPLICATE KEY UPDATE name=name",
            (series,),
        )
        for _ in range(1000):
            code = sku_code(prefix, name, getseries(series, 5))
            if not frappe.db.exists("Item", code):
                break
        else:
            sale.conflict("No se pudo asignar un SKU. Revisa el prefijo del negocio")
    if frappe.db.exists("Item", code):
        raise ValueError("El código interno ya existe. Use otro o abra el producto existente")
    item = frappe.get_doc(
        {
            "doctype": "Item",
            "item_code": code,
            "item_name": name,
            "item_group": wire.identifier(data["item_group"]),
            "stock_uom": "Nos",
            "is_stock_item": 1,
            "is_sales_item": 1,
            "omp_business_brand": data["brand"],
            "omp_operation_key": key,
            "omp_payload_hash": hashed,
            "barcodes": [{"barcode": clean_text(data["barcode"])}] if data["barcode"] else [],
        }
    ).insert()
    profile = frappe.get_doc("POS Profile", context["pos_profile"])
    frappe.get_doc(
        {
            "doctype": "Item Price",
            "item_code": item.name,
            "price_list": profile.selling_price_list,
            "price_list_rate": float(wire.amount(data["price"])),
            "currency": profile.currency,
            "uom": item.stock_uom,
        }
    ).insert()
    return {"item_code": item.name, "duplicate": False}


@frappe.whitelist(methods=["POST"])
@sale.contract_errors
def receive_stock(data):
    data = wire.mapping(data, ("brand", "item_code", "qty", "cost", "request_id"))
    context = brand_context(data["brand"])
    request = wire.request_uuid(data["request_id"])
    qty = wire.items([{"item_code": data["item_code"], "qty": data["qty"]}])[0]["qty"]
    cost = wire.amount(data["cost"])
    key = wire.digest([frappe.session.user, request])
    hashed = wire.digest(data)
    frappe.db.get_value("OMP Business Brand", data["brand"], "name", for_update=True)
    tombstone = frappe.db.get_value("OMP Inventory Tombstone", key, "name", for_update=True)
    if tombstone:
        sale.conflict("El intento fue bloqueado. Crea una entrada nueva con los datos correctos")
    existing = frappe.db.get_value(
        "Stock Entry",
        {"omp_operation_key": key},
        ["name", "omp_payload_hash"],
        as_dict=True,
        for_update=True,
    )
    if existing:
        if existing.omp_payload_hash != hashed:
            sale.conflict("El intento ya pertenece a otra entrada")
        doc = frappe.get_doc("Stock Entry", existing.name, for_update=True)
        doc.check_permission("read")
        if doc.docstatus != 1:
            sale.conflict("La entrada original no está enviada")
        return {"stock_entry": existing.name, "duplicate": True}
    item = frappe.get_doc("Item", wire.identifier(data["item_code"]))
    item.check_permission("read")
    if (
        not item.is_stock_item
        or item.disabled
        or item.has_batch_no
        or item.has_serial_no
        or (item.get("omp_business_brand") and item.omp_business_brand != data["brand"])
    ):
        raise ValueError("El producto no admite esta entrada en este negocio")
    company = frappe.get_doc("Company", context["company"])
    doc = frappe.get_doc(
        {
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Receipt",
            "company": company.name,
            "omp_operation_key": key,
            "omp_payload_hash": hashed,
            "items": [
                {
                    "item_code": item.name,
                    "qty": qty,
                    "t_warehouse": context["warehouse"],
                    "basic_rate": float(cost),
                    "expense_account": company.stock_adjustment_account,
                    "cost_center": company.cost_center,
                }
            ],
        }
    ).insert()
    doc.submit()
    return {"stock_entry": doc.name, "duplicate": False}


@frappe.whitelist(methods=["POST"])
@sale.contract_errors
def resolve_stock(data):
    data = wire.mapping(data, ("brand", "item_code", "qty", "cost", "request_id"))
    brand_context(data["brand"])
    key = wire.digest([frappe.session.user, wire.request_uuid(data["request_id"])])
    hashed = wire.digest(data)
    frappe.db.get_value("OMP Business Brand", data["brand"], "name", for_update=True)
    existing = frappe.db.get_value(
        "Stock Entry",
        {"omp_operation_key": key},
        ["name", "omp_payload_hash"],
        as_dict=True,
        for_update=True,
    )
    if existing:
        if existing.omp_payload_hash != hashed:
            sale.conflict("El intento pertenece a otra entrada")
        doc = frappe.get_doc("Stock Entry", existing.name, for_update=True)
        doc.check_permission("read")
        if doc.docstatus != 1:
            sale.conflict("La entrada original no está enviada; revisa su cancelación")
        return {"status": "completed", "stock_entry": doc.name}
    prior = frappe.db.get_value("OMP Inventory Tombstone", key, "payload_hash", for_update=True)
    if prior and prior != hashed:
        sale.conflict("El intento pertenece a otros datos")
    if not prior:
        sale.journal(
            "OMP Inventory Tombstone",
            key,
            {"actor": frappe.session.user, "brand": data["brand"], "payload_hash": hashed},
        )
    return {"status": "abandoned"}


@frappe.whitelist(methods=["GET"])
def team():
    require_admin()
    members = frappe.get_all(
        "Has Role",
        filters={"role": ["in", ["OMP Administrator", "OMP Cashier"]], "parenttype": "User"},
        pluck="parent",
    )
    if not members:
        return []
    return frappe.get_list(
        "User",
        filters={"name": ["in", list(set(members))]},
        fields=["name", "full_name", "enabled"],
        order_by="full_name",
        limit=100,
    )


@frappe.whitelist(methods=["POST"])
@sale.contract_errors
def create_user(data):
    require_admin()
    data = wire.mapping(data, ("email", "full_name", "password", "role", "brands"))
    email = validate_email_address(clean_text(data["email"], required=True), throw=True)
    if data["role"] not in ("admin", "cashier") or not isinstance(data["brands"], list):
        raise ValueError("Perfil inválido")
    if (
        not isinstance(data["password"], str)
        or len(data["password"]) < 12
        or len(data["password"]) > 128
    ):
        raise ValueError("Use una contraseña de 12 a 128 caracteres")
    for brand in data["brands"]:
        brand_context(brand)
    if frappe.db.exists("User", email):
        raise ValueError("Ya existe una cuenta con ese correo")
    roles = ADMIN_ROLES if data["role"] == "admin" else ("OMP Cashier", "Sales User")
    user = frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": clean_text(data["full_name"], required=True),
            "new_password": data["password"],
            "send_welcome_email": 0,
            "language": settings()["interface_language"],
            "roles": [{"role": role} for role in roles],
        }
    ).insert()
    for brand in data["brands"]:
        doc = frappe.get_doc("OMP Business Brand", brand)
        if email not in [r.user for r in doc.allowed_users]:
            doc.append("allowed_users", {"user": email})
            doc.save()
        profile = frappe.get_doc("POS Profile", doc.pos_profile)
        if email not in [r.user for r in profile.applicable_for_users]:
            profile.append("applicable_for_users", {"user": email})
            profile.save()
        frappe.get_doc(
            {
                "doctype": "OMP POS Terminal",
                "brand": brand,
                "user": email,
                "display_name": "Caja de " + doc.display_name,
                "enabled": 1,
            }
        ).insert()
        if data["role"] == "cashier" and not frappe.db.exists(
            "User Permission", {"user": email, "allow": "Company", "for_value": doc.company}
        ):
            frappe.get_doc(
                {
                    "doctype": "User Permission",
                    "user": email,
                    "allow": "Company",
                    "for_value": doc.company,
                    "apply_to_all_doctypes": 1,
                }
            ).insert()
    return {"user": user.name}
