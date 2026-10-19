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
