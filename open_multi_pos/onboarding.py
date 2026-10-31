"""Resumable setup using native documents, private progress and fenced retries."""

import json

import frappe
from frappe.utils import nowdate

from open_multi_pos import checkout as native
from open_multi_pos import checkout_contract as wire
from open_multi_pos import workspace
from open_multi_pos.operations import recovery_status

REQUEST = "OMP Setup Request"
PROGRESS = "OMP Setup Progress"
STEPS = ("account", "preferences", "businesses", "inventory", "receipt", "recovery")


def lock():
    workspace.require_admin()
    # A permanent metadata row serializes initial claims and setup writes across administrators.
    frappe.db.get_value("DocType", REQUEST, "name", for_update=True)


def progress():
    value = frappe.db.get_value(PROGRESS, "Workspace", "state_json", for_update=True)
    return json.loads(value) if value else {"active": False, "step": "account", "receipts": {}}


def save_progress(value):
    text = wire.canonical(value)
    if frappe.db.exists(PROGRESS, "Workspace"):
        frappe.db.set_value(PROGRESS, "Workspace", "state_json", text)
    else:
        native.journal(PROGRESS, "Workspace", {"state_json": text})


def first_claimed(state):
    return bool(
        state.get("first_admin")
        or frappe.db.sql(
            "SELECT u.name FROM tabUser u INNER JOIN `tabHas Role` r ON r.parent=u.name AND r.parenttype='User' WHERE r.role='OMP Administrator' LIMIT 1 FOR UPDATE"
        )
    )


def record(request_id):
    key = wire.digest(["setup", frappe.session.user, wire.request_uuid(request_id)])
    return key, frappe.db.get_value(
        REQUEST,
        key,
        ["action", "status", "payload_hash", "target_doctype", "target_name"],
        as_dict=True,
        for_update=True,
    )


def outcome(row):
    if row.status == "Abandoned":
        return {"status": "abandoned"}
    if not frappe.db.exists(row.target_doctype, row.target_name) or not frappe.has_permission(
        row.target_doctype, "read", row.target_name
    ):
        return {"status": "completed", "restricted": True, "result": {}}
    field = "brand" if row.action == "business" else "user"
    return {"status": "completed", "result": {field: row.target_name}}


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def apply(action, request_id, data, first=False):
    lock()
    if not frappe.is_setup_complete():
        raise ValueError("Completa primero la configuración nativa de ERPNext desde Escritorio")
    if action not in ("user", "business", "claim") or type(first) is not bool:
        raise ValueError("Acción de preparación inválida")
    if action == "business":
        data = wire.mapping(data, ("display_name", "company", "legal_name", "abbr", "currency"))
        if first:
            raise ValueError("El alta de un negocio no es una cuenta inicial")
    elif action == "user":
        data = wire.mapping(data, ("email", "full_name", "password", "role", "brands"))
        if first and data["role"] != "admin":
            raise ValueError("La primera cuenta debe ser administrativa")
    else:
        data = wire.mapping(data, ())
        if frappe.session.user == "Administrator":
            raise ValueError("Crea una cuenta personal antes de continuar")
    # A replay never changes a password, and the journal cannot become a fast password verifier.
    fingerprint = wire.digest([action, first, {k: v for k, v in data.items() if k != "password"}])
    key, row = record(request_id)
    if row:
        if row.status == "Abandoned" or row.payload_hash != fingerprint or row.action != action:
            native.conflict("Este intento ya se resolvió o tiene otro contenido")
        return outcome(row)
    state = progress()
    if (first or action == "claim") and first_claimed(state):
        native.conflict("La cuenta inicial ya fue configurada. Revisa los perfiles en Equipo")
    if action == "business":
        name = workspace.create_business(data)["brand"]
        doctype = "OMP Business Brand"
    elif action == "user":
        name = workspace.create_user(data)["user"]
        doctype = "User"
    else:
        user = frappe.get_doc("User", frappe.session.user)
        user.check_permission("write")
        user.add_roles(*workspace.ADMIN_ROLES)
        name, doctype = user.name, "User"
    if first or action == "claim":
        state["first_admin"] = name
        save_progress(state)
    row = native.journal(
        REQUEST,
        key,
        {
            "actor": frappe.session.user,
            "action": action,
            "status": "Completed",
            "payload_hash": fingerprint,
            "target_doctype": doctype,
            "target_name": name,
        },
    )
    return outcome(row)


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def status(request_id):
    lock()
    _, row = record(request_id)
    return outcome(row) if row else {"status": "not_found"}


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def abandon(request_id):
    lock()
    key, row = record(request_id)
    if row:
        return outcome(row)
    native.journal(
        REQUEST, key, {"actor": frappe.session.user, "action": "business", "status": "Abandoned"}
    )
    return {"status": "abandoned"}


def receipt_hash(brand):
    return wire.digest([workspace.business(brand), workspace.settings()])


def readiness(state):
    boot = workspace.boot()
    brands = boot["businesses"]
    inventory = []
    for brand in brands:
        profile = frappe.get_doc("POS Profile", brand["pos_profile"])
        # Only an actual owned stock item, positive stock and a current selling price count.
        rows = frappe.db.sql(
            """SELECT i.name FROM tabItem i JOIN tabBin b ON b.item_code=i.name
            JOIN `tabItem Price` p ON p.item_code=i.name
            WHERE i.omp_business_brand=%s AND i.disabled=0 AND i.is_stock_item=1
            AND i.is_sales_item=1 AND i.has_variants=0 AND i.has_serial_no=0 AND i.has_batch_no=0
            AND b.warehouse=%s AND b.actual_qty>0 AND p.price_list=%s AND p.currency=%s
            AND p.price_list_rate>0 AND (p.valid_from IS NULL OR p.valid_from<=%s)
            AND (p.valid_upto IS NULL OR p.valid_upto>=%s) LIMIT 1""",
            (
                brand["brand"],
                brand["warehouse"],
                profile.selling_price_list,
                profile.currency,
                nowdate(),
                nowdate(),
            ),
        )
        if rows:
            inventory.append(brand["brand"])
    receipts = {brand["brand"]: receipt_hash(brand["brand"]) for brand in brands}
    recovery = recovery_status()
    human = bool(
        frappe.db.sql(
            "SELECT u.name FROM tabUser u INNER JOIN `tabHas Role` r ON r.parent=u.name AND r.parenttype='User' WHERE u.enabled=1 AND u.name NOT IN ('Administrator','Guest') AND r.role='OMP Administrator' LIMIT 1 FOR UPDATE"
        )
    )
    hashes = {"preferences": wire.digest(boot["settings"]), "receipt": wire.digest(receipts)}
    checks = {
        "account": human,
        "preferences": state.get("preferences") == hashes["preferences"],
        "businesses": len(brands) >= 2,
        "inventory": bool(inventory),
        "receipt": len(receipts) >= 2
        and all(
            state.get("receipts", {}).get(brand) == fingerprint
            for brand, fingerprint in receipts.items()
        ),
        "recovery": bool(recovery["backup_recent"] and recovery["restore_at"]),
    }
    return {
        "active": bool(state.get("active")),
        "complete": bool(state.get("complete")),
        "step": state.get("step", "account"),
        "checks": checks,
        "hashes": hashes,
        "first_claimed": first_claimed(state),
        "native_ready": bool(frappe.is_setup_complete()),
        "can_claim_current": frappe.session.user != "Administrator",
        "brands": [
            {
                "brand": brand["brand"],
                "name": brand["display_name"],
                "receipt_hash": receipts[brand["brand"]],
                "receipt_reviewed": state.get("receipts", {}).get(brand["brand"])
                == receipts[brand["brand"]],
                "inventory_present": brand["brand"] in inventory,
            }
            for brand in brands
        ],
        "preferences": boot["settings"],
        "recovery": recovery,
    }


@frappe.whitelist(methods=["POST"])
def state():
    lock()
    return readiness(progress())


@frappe.whitelist(methods=["POST"])
@native.contract_errors
def update(step, fingerprint=None, brand=None, finish=False):
    lock()
    if step not in STEPS or type(finish) is not bool:
        raise ValueError("Paso de preparación inválido")
    value = progress()
    current = readiness(value)
    if fingerprint is not None:
        if step == "preferences":
            if fingerprint != current["hashes"]["preferences"]:
                native.conflict("Las preferencias cambiaron. Vuelve a revisarlas")
            value["preferences"] = fingerprint
        elif step == "receipt":
            brand = wire.identifier(brand)
            actual = receipt_hash(brand)
            if fingerprint != actual:
                native.conflict("El perfil o el equipo cambió. Vuelve a revisar la muestra")
            value.setdefault("receipts", {})[brand] = actual
        else:
            raise ValueError("Este paso no admite una confirmación manual")
    value.update({"active": True, "step": step, "complete": False})
    current = readiness(value)
    if finish:
        if not current["native_ready"] or not all(current["checks"].values()):
            native.conflict("Completa los requisitos pendientes antes de terminar")
        value.update({"active": False, "complete": True})
    save_progress(value)
    return readiness(value)
