"""Additional brand restrictions; native role/company permissions still apply."""

import frappe


def manager(user: str) -> bool:
    return user == "Administrator" or "System Manager" in frappe.get_roles(user)


def brand_query(user=None):
    user = user or frappe.session.user
    if user == "Guest":
        return "1=0"
    if manager(user):
        return ""
    return (
        "`tabOMP Business Brand`.enabled=1 AND EXISTS ("
        "SELECT 1 FROM `tabOMP Brand User` grant_row "
        "WHERE grant_row.parent=`tabOMP Business Brand`.name "
        "AND grant_row.parenttype='OMP Business Brand' "
        "AND grant_row.parentfield='allowed_users' "
        f"AND grant_row.user={frappe.db.escape(user)})"
    )


def brand_permission(doc, user=None, ptype="read"):
    user = user or frappe.session.user
    if user == "Guest":
        return False
    if manager(user):
        return True  # This hook can restrict only; native checks still run.
    if ptype != "read":
        return False
    return bool(doc.enabled and any(row.user == user for row in doc.allowed_users))


def profile_query(user=None):
    user = user or frappe.session.user
    if user == "Guest":
        return "1=0"
    if manager(user) or "OMP Cashier" not in frappe.get_roles(user):
        return ""
    escaped = frappe.db.escape(user)
    return (
        "`tabPOS Profile`.disabled=0 AND EXISTS ("
        "SELECT 1 FROM `tabOMP Business Brand` b "
        "INNER JOIN `tabOMP Brand User` u ON u.parent=b.name "
        "AND u.parenttype='OMP Business Brand' AND u.parentfield='allowed_users' "
        f"WHERE b.pos_profile=`tabPOS Profile`.name AND b.enabled=1 AND u.user={escaped}) "
        "AND (NOT EXISTS (SELECT 1 FROM `tabPOS Profile User` p "
        "WHERE p.parent=`tabPOS Profile`.name AND p.parenttype='POS Profile' "
        "AND p.parentfield='applicable_for_users') OR EXISTS ("
        "SELECT 1 FROM `tabPOS Profile User` p WHERE p.parent=`tabPOS Profile`.name "
        "AND p.parenttype='POS Profile' AND p.parentfield='applicable_for_users' "
        f"AND p.user={escaped}))"
    )


def profile_permission(doc, user=None, ptype="read"):
    user = user or frappe.session.user
    if user == "Guest":
        return False
    if manager(user) or "OMP Cashier" not in frappe.get_roles(user):
        return True  # Existing native roles remain authoritative.
    if ptype != "read" or doc.disabled:
        return False
    if doc.applicable_for_users and user not in [row.user for row in doc.applicable_for_users]:
        return False
    return bool(
        frappe.db.sql(
            "SELECT b.name FROM `tabOMP Business Brand` b "
            "INNER JOIN `tabOMP Brand User` u ON u.parent=b.name "
            "AND u.parenttype='OMP Business Brand' AND u.parentfield='allowed_users' "
            "WHERE b.pos_profile=%s AND b.enabled=1 AND u.user=%s LIMIT 1",
            (doc.name, user),
        )
    )


def _invoice_brand_condition(table, user):
    escaped = frappe.db.escape(user)
    return (
        f"{table}.is_pos=1 AND EXISTS ("
        "SELECT 1 FROM `tabOMP Business Brand` b "
        "JOIN `tabOMP Brand User` u ON u.parent=b.name "
        "AND u.parenttype='OMP Business Brand' AND u.parentfield='allowed_users' "
        "JOIN `tabPOS Profile` p ON p.name=b.pos_profile "
        "JOIN `tabWarehouse` w ON w.name=p.warehouse "
        f"WHERE b.pos_profile={table}.pos_profile AND b.enabled=1 AND p.disabled=0 "
        f"AND u.user={escaped} AND b.company=p.company AND b.warehouse=p.warehouse "
        f"AND w.company=p.company AND {table}.company=p.company "
        f"AND {table}.set_warehouse=p.warehouse "
        "AND (NOT EXISTS (SELECT 1 FROM `tabPOS Profile User` a "
        "WHERE a.parent=p.name AND a.parenttype='POS Profile' "
        "AND a.parentfield='applicable_for_users') OR EXISTS ("
        "SELECT 1 FROM `tabPOS Profile User` a WHERE a.parent=p.name "
        "AND a.parenttype='POS Profile' AND a.parentfield='applicable_for_users' "
        f"AND a.user={escaped})))"
    )


def _invoice_query(doctype, user):
    user = user or frappe.session.user
    if user == "Guest":
        return "1=0"
    if manager(user) or "OMP Cashier" not in frappe.get_roles(user):
        return ""
    return _invoice_brand_condition(f"`tab{doctype}`", user)


def sales_invoice_query(user=None):
    return _invoice_query("Sales Invoice", user)


def pos_invoice_query(user=None):
    return _invoice_query("POS Invoice", user)


def invoice_permission(doc, user=None, ptype="read"):
    user = user or frappe.session.user
    if user == "Guest":
        return False
    if manager(user) or "OMP Cashier" not in frappe.get_roles(user):
        return True  # This hook restricts cashiers; native role permissions still apply.
    if ptype not in ("read", "print") or doc.doctype not in ("Sales Invoice", "POS Invoice"):
        return False
    table = f"`tab{doc.doctype}`"  # Fixed allowlist above, never a client-supplied table.
    allowed = frappe.db.sql(
        f"SELECT {table}.name FROM {table} WHERE {table}.name=%s AND "
        + _invoice_brand_condition(table, user)
        + " LIMIT 1",
        (doc.name,),
    )
    if not allowed:
        return False
    if ptype == "print" and "xpos" in frappe.get_installed_apps():
        from xpos.api.auth import user_has_pos_permission

        if doc.docstatus == 2:
            return False
        if doc.docstatus == 0 and not user_has_pos_permission(
            "print_draft_invoice", user=user, pos_profile=doc.pos_profile
        ):
            return False
        if doc.get("print_count") and not user_has_pos_permission(
            "allow_reprint_invoice", user=user, pos_profile=doc.pos_profile
        ):
            return False
    return True
