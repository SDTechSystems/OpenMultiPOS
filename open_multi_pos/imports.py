"""Previewed, atomic native catalog and stock imports for administrators."""

import json
from decimal import Decimal
from uuid import uuid4

import frappe
from frappe.utils import now_datetime, nowdate

from open_multi_pos import checkout as native
from open_multi_pos import checkout_contract as wire
from open_multi_pos.import_contract import parse
from open_multi_pos.workspace import brand_context, create_product


def context(brand):
    ctx = brand_context(wire.identifier(brand))
    revision = frappe.db.get_value("OMP Business Brand", ctx["brand"], "modified")
    frappe.db.get_value("POS Profile", ctx["pos_profile"], "name", for_update=True)
    frappe.db.get_value("OMP Business Brand", ctx["brand"], "name", for_update=True)
    current = frappe.get_doc("OMP Business Brand", ctx["brand"], for_update=True)
    if str(current.modified) != str(revision):
        native.conflict(
            "La configuración cambió durante la solicitud. Consulte el estado y reintente"
        )
    ctx = brand_context(brand)
    profile = frappe.get_doc("POS Profile", ctx["pos_profile"], for_update=True)
    if (
        profile.disabled
        or profile.company != ctx["company"]
        or profile.warehouse != ctx["warehouse"]
    ):
        native.conflict("El perfil POS cambió. Revise la configuración antes de importar")
    company = frappe.get_doc("Company", ctx["company"])
    prices = frappe.get_doc("Price List", profile.selling_price_list)
    prices.check_permission("read")
    if (
        not prices.enabled
        or not prices.selling
        or prices.currency != company.default_currency
        or profile.currency != company.default_currency
    ):
        raise ValueError("El perfil, la lista de precios y la empresa deben usar la misma moneda")
    if not frappe.has_permission("Item", "create") or not frappe.has_permission("Item", "write"):
        frappe.throw("No tiene permiso para importar productos", frappe.PermissionError)
    return ctx, profile, company


def key(request_id):
    return wire.digest(["import", frappe.session.user, wire.request_uuid(request_id)])


def locked_record(brand, request_id):
    name = key(request_id)
    frappe.db.sql(
        """INSERT INTO `tabOMP Import Request`
        (name,creation,modified,owner,modified_by,docstatus,actor,brand,request_id,status)
        VALUES (%s,%s,%s,%s,%s,0,%s,%s,%s,'Prepared') ON DUPLICATE KEY UPDATE name=name""",
        (
            name,
            now_datetime(),
            now_datetime(),
            frappe.session.user,
            frappe.session.user,
            frappe.session.user,
            brand,
            request_id,
        ),
    )
    record = frappe.get_doc("OMP Import Request", name, for_update=True)
    if record.actor != frappe.session.user or record.brand != brand:
        frappe.throw("Intento de otro negocio o usuario", frappe.PermissionError)
    return record


def completed(record):
    result = json.loads(record.result_json)
    for row in result["items"]:
        item = frappe.get_doc("Item", row["item_code"])
        item.check_permission("read")
        if item.omp_business_brand != record.brand:
            frappe.throw("El producto ya no pertenece a este negocio", frappe.PermissionError)
    if result.get("stock_entry"):
        doc = frappe.get_doc("Stock Entry", result["stock_entry"], for_update=True)
        doc.check_permission("read")
        if doc.docstatus != 1:
            native.conflict("La entrada original ya no está enviada. Revísela en ERPNext")
    return {
        "status": "completed",
        "request_id": record.request_id,
        "result": result,
        "duplicate": True,
    }


def view(record):
    if record.status == "Completed":
        return completed(record)
    if record.status == "Abandoned":
        return {"status": "abandoned", "request_id": record.request_id}
    if not record.plan_json:
        native.conflict("No hay una vista previa válida para este intento")
    return {
        "status": "prepared",
        "request_id": record.request_id,
        "plan": json.loads(record.plan_json),
        "plan_hash": record.plan_hash,
    }


def price_for(item, profile):
    rows = frappe.db.sql(
        "SELECT name FROM `tabItem Price` WHERE item_code=%s AND price_list=%s LIMIT 3 FOR UPDATE",
        (item.name, profile.selling_price_list),
        pluck=True,
    )
    if len(rows) > 1:
        raise ValueError("Hay varios precios para este SKU. Revise fechas y condiciones en ERPNext")
    if not rows:
        return None
    doc = frappe.get_doc("Item Price", rows[0], for_update=True)
    doc.check_permission("read")
    if (
        doc.currency != profile.currency
        or doc.uom != item.stock_uom
        or doc.get("customer")
        or doc.get("supplier")
        or doc.get("batch_no")
        or (doc.get("min_qty") or 0) > 0
        or (doc.get("packing_unit") or 0) > 1
        or (doc.valid_from and str(doc.valid_from) > nowdate())
        or (doc.valid_upto and str(doc.valid_upto) < nowdate())
    ):
        raise ValueError(
            "El precio tiene moneda, unidad o condiciones especiales. Revíselo en ERPNext"
        )
    return doc


def plan_rows(ctx, profile, rows, source_hash):
    entries, errors, seen_codes, seen_barcodes, seen_names = [], [], set(), set(), set()
    # Deterministic item locks match native stock's ordering across batches.
    for code in sorted({row["sku"] for row in rows if row["sku"]}):
        frappe.db.get_value("Item", code, "name", for_update=True)
    for row in rows:
        try:
            code, barcode = row["sku"], row["codigo_barras"]
            if code and code.casefold() in seen_codes:
                raise ValueError("SKU repetido en el archivo; conserve una sola fila por producto")
            if code:
                seen_codes.add(code.casefold())
            if barcode and barcode.casefold() in seen_barcodes:
                raise ValueError("Código de barras repetido en el archivo")
            if barcode:
                seen_barcodes.add(barcode.casefold())
            exists = bool(code and frappe.db.get_value("Item", code, "name", for_update=True))
            item, price = None, None
            if row["accion"] == "crear":
                if exists:
                    raise ValueError("El SKU ya existe. Use actualizar o ingresar si corresponde")
                normalized = row["nombre"].casefold()
                if normalized in seen_names:
                    raise ValueError("Nombre repetido entre productos nuevos; revise el archivo")
                seen_names.add(normalized)
                if frappe.db.sql(
                    "SELECT name FROM tabItem WHERE omp_business_brand=%s AND item_name=%s LIMIT 1 FOR UPDATE",
                    (ctx["brand"], row["nombre"]),
                ):
                    raise ValueError(
                        "Ya hay un producto del negocio con este nombre; revise su SKU"
                    )
            else:
                if not exists:
                    raise ValueError("No existe el SKU que desea actualizar o recibir")
                item = frappe.get_doc("Item", code, for_update=True)
                item.check_permission("read")
                item.check_permission("write")
                if item.get("omp_business_brand") != ctx["brand"]:
                    raise ValueError("El SKU no pertenece al negocio activo")
                if (
                    not native.simple_sale_item(item)
                    or not item.is_stock_item
                    or item.stock_uom != "Nos"
                ):
                    raise ValueError(
                        "El producto requiere gestión nativa de unidad, variante, serie o lote"
                    )
                price = price_for(item, profile)
            group = row["grupo"] or (item.item_group if item else "")
            group_doc = frappe.get_doc("Item Group", group)
            group_doc.check_permission("read")
            if group_doc.is_group or not native.group_allowed(
                "Item Group", group, profile.item_groups
            ):
                raise ValueError("Elija un grupo final habilitado en el perfil POS")
            if barcode:
                owner = frappe.db.get_value(
                    "Item Barcode", {"barcode": barcode}, "parent", for_update=True
                )
                if owner and owner != code:
                    raise ValueError(
                        "El código de barras ya está en uso; revíselo antes de importar"
                    )
            resolved_price = row["precio"] or (
                str(native.money(price.price_list_rate)) if price else ""
            )
            if not resolved_price and row["accion"] != "ingresar":
                raise ValueError(
                    "Complete precio: el producto no tiene precio en la lista de este negocio"
                )
            stock = (
                frappe.db.get_value(
                    "Bin",
                    {"item_code": code, "warehouse": ctx["warehouse"]},
                    "actual_qty",
                    for_update=True,
                )
                if item
                else 0
            )
            state = {
                "item_modified": str(item.modified) if item else "",
                "price_modified": str(price.modified) if price else "",
                "price_id": price.name if price else "",
                "barcode_owner": owner if barcode else "",
                "stock": str(stock or 0),
            }
            entries.append(
                {
                    **row,
                    "nombre": row["nombre"] or item.item_name,
                    "grupo": group,
                    "precio": resolved_price,
                    "sku_label": code or "SKU automático al aplicar",
                    "stock_before": str(stock or 0),
                    "stock_after": str(Decimal(str(stock or 0)) + row["cantidad"]),
                    "before": {
                        "name": item.item_name if item else "",
                        "group": item.item_group if item else "",
                        "price": str(native.money(price.price_list_rate)) if price else "",
                        "barcodes": [b.barcode for b in item.barcodes] if item else [],
                    },
                    "state": state,
                }
            )
        except (ValueError, frappe.DoesNotExistError) as exc:
            message = (
                str(exc)
                if isinstance(exc, ValueError)
                else "El grupo o documento de referencia no existe"
            )
            errors.append({"line": row["line"], "message": message})
    prior = frappe.db.sql(
        """SELECT request_id, modified FROM `tabOMP Import Request`
        WHERE brand=%s AND source_hash=%s AND status='Completed' ORDER BY modified DESC FOR UPDATE""",
        (ctx["brand"], source_hash),
        as_dict=True,
    )
    return {
        "brand": ctx["brand"],
        "business": ctx["display_name"],
        "warehouse": ctx["warehouse"],
        "currency": profile.currency,
        "profile_modified": str(profile.modified),
        "brand_modified": str(frappe.db.get_value("OMP Business Brand", ctx["brand"], "modified")),
        "rows": entries,
        "errors": errors,
        "previous_count": len(prior),
        "last_applied_at": str(prior[0].modified) if prior else "",
        "create_count": sum(r["accion"] == "crear" for r in rows),
        "update_count": sum(r["accion"] == "actualizar" for r in rows),
        "units": sum(r["cantidad"] for r in rows),
        "stock_value": str(
            sum((Decimal(r["costo"] or "0") * r["cantidad"] for r in rows), Decimal(0))
        ),
    }


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def preview(data):
    data = wire.mapping(data, ("brand", "request_id", "csv_text"))
    ctx, profile, _ = context(data["brand"])
    request_id = wire.request_uuid(data["request_id"])
    record = locked_record(ctx["brand"], request_id)
    if record.status == "Abandoned":
        return view(record)
    rows, errors = parse(data["csv_text"])
    source_hash = wire.digest(
        sorted(({k: v for k, v in row.items() if k != "line"} for row in rows), key=wire.canonical)
    )
    if record.source_hash:
        if record.source_hash != source_hash or wire.digest(
            json.loads(record.source_json)
        ) != wire.digest(rows):
            native.conflict(
                "Esta clave pertenece a otro archivo. Resuelva el intento antes de cambiarlo"
            )
        return view(record)
    plan = plan_rows(ctx, profile, rows, source_hash)
    plan["errors"] = errors + plan["errors"]
    if plan["errors"]:
        # Delete only our empty journal, never a financial/native document.
        frappe.db.delete("OMP Import Request", {"name": record.name})
        return {"status": "invalid", "errors": plan["errors"], "rows": plan["rows"]}
    frappe.db.set_value(
        "OMP Import Request",
        record.name,
        {
            "source_hash": source_hash,
            "source_json": wire.canonical(rows),
            "plan_json": wire.canonical(plan),
            "plan_hash": wire.digest(plan),
        },
    )
    return view(frappe.get_doc("OMP Import Request", record.name))


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def refresh(brand, request_id):
    ctx, profile, _ = context(brand)
    record = locked_record(brand, wire.request_uuid(request_id))
    if record.status != "Prepared":
        return view(record)
    if not record.source_json:
        native.conflict("Vuelva a seleccionar el archivo después de resolver este intento")
    plan = plan_rows(ctx, profile, json.loads(record.source_json), record.source_hash)
    if plan["errors"]:
        return {"status": "invalid", "errors": plan["errors"], "rows": plan["rows"]}
    frappe.db.set_value(
        "OMP Import Request",
        record.name,
        {"plan_json": wire.canonical(plan), "plan_hash": wire.digest(plan)},
    )
    return view(frappe.get_doc("OMP Import Request", record.name))


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def apply(data):
    data = wire.mapping(data, ("brand", "request_id", "plan_hash", "confirm_repeat"))
    if type(data["confirm_repeat"]) is not int or data["confirm_repeat"] not in (0, 1):
        raise ValueError("Confirme si corresponde a una recepción nueva")
    ctx, profile, company = context(data["brand"])
    record = locked_record(ctx["brand"], wire.request_uuid(data["request_id"]))
    if record.status == "Completed" and data["plan_hash"] != record.plan_hash:
        native.conflict("La clave corresponde a otra vista previa")
    if record.status != "Prepared":
        return view(record)
    if not record.source_json:
        native.conflict("Prepare y revise la vista previa antes de aplicar")
    plan = plan_rows(ctx, profile, json.loads(record.source_json), record.source_hash)
    if (
        plan["errors"]
        or record.plan_hash != data["plan_hash"]
        or wire.digest(plan) != record.plan_hash
    ):
        native.conflict("Los datos cambiaron. Actualice y revise la vista previa antes de aplicar")
    if plan["previous_count"] and not data["confirm_repeat"]:
        native.conflict(
            "Este contenido ya se aplicó. Confirme que corresponde a unidades o cambios nuevos"
        )
    result = {
        "items": [],
        "stock_entry": None,
        "warehouse": ctx["warehouse"],
        "currency": profile.currency,
    }
    stock_rows = []
    for row in plan["rows"]:
        if row["accion"] == "crear":
            code = create_product(
                {
                    "brand": ctx["brand"],
                    "code": row["sku"],
                    "name": row["nombre"],
                    "barcode": row["codigo_barras"],
                    "price": row["precio"],
                    "item_group": row["grupo"],
                    "request_id": str(uuid4()),
                }
            )["item_code"]
        else:
            code = row["sku"]
            if row["accion"] == "actualizar":
                item = frappe.get_doc("Item", code, for_update=True)
                item.item_name, item.item_group = row["nombre"], row["grupo"]
                if row["codigo_barras"] and row["codigo_barras"] not in [
                    r.barcode for r in item.barcodes
                ]:
                    item.append("barcodes", {"barcode": row["codigo_barras"]})
                item.save()
                price = price_for(item, profile)
                if price:
                    price.price_list_rate = Decimal(row["precio"])
                    price.save()
                else:
                    frappe.get_doc(
                        {
                            "doctype": "Item Price",
                            "item_code": code,
                            "price_list": profile.selling_price_list,
                            "price_list_rate": Decimal(row["precio"]),
                            "currency": profile.currency,
                            "uom": item.stock_uom,
                        }
                    ).insert()
        result["items"].append(
            {
                "line": row["line"],
                "item_code": code,
                "action": row["accion"],
                "qty": row["cantidad"],
            }
        )
        if row["cantidad"]:
            stock_rows.append(
                {
                    "item_code": code,
                    "qty": row["cantidad"],
                    "t_warehouse": ctx["warehouse"],
                    "basic_rate": Decimal(row["costo"]),
                    "expense_account": company.stock_adjustment_account,
                    "cost_center": company.cost_center,
                }
            )
    if stock_rows:
        doc = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "stock_entry_type": "Material Receipt",
                "company": company.name,
                "omp_operation_key": record.name,
                "omp_payload_hash": record.source_hash,
                "items": stock_rows,
            }
        ).insert()
        doc.submit()
        if native.money(doc.total_incoming_value) != native.money(plan["stock_value"]):
            native.conflict("La valoración nativa cambió; no se aplicó la importación")
        result["stock_entry"] = doc.name
    frappe.db.set_value(
        "OMP Import Request",
        record.name,
        {"status": "Completed", "result_json": wire.canonical(result)},
    )
    return {**completed(frappe.get_doc("OMP Import Request", record.name)), "duplicate": False}


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def status(brand, request_id):
    context(brand)
    name = key(request_id)
    if not frappe.db.exists("OMP Import Request", name):
        return {"status": "not_found", "request_id": request_id}
    record = frappe.get_doc("OMP Import Request", name, for_update=True)
    if record.brand != brand or record.actor != frappe.session.user:
        frappe.throw("Intento de otro negocio o usuario", frappe.PermissionError)
    return view(record)


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def abandon(brand, request_id):
    context(brand)
    record = locked_record(brand, wire.request_uuid(request_id))
    if record.status == "Completed":
        return completed(record)
    frappe.db.set_value("OMP Import Request", record.name, "status", "Abandoned")
    return {"status": "abandoned", "request_id": request_id}
