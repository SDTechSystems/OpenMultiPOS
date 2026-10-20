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
