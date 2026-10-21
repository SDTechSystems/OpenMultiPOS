"""Private, request-local permission capability for server-built native documents."""

from contextlib import contextmanager
from contextvars import ContextVar

import frappe

from open_multi_pos.permissions import manager

_documents = ContextVar("omp_native_documents", default=())


@contextmanager
def native_documents(*docs):
    token = _documents.set((*_documents.get(), *docs))
    try:
        yield
    finally:
        _documents.reset(token)


def service_document(doc, user, ptype):
    if user != frappe.session.user or ptype not in ("read", "create", "write", "submit"):
        return False
    return any(
        doc is allowed or (isinstance(allowed, tuple) and (doc.doctype, doc.name) == allowed)
        for allowed in _documents.get()
    )


def guard_native_write(doc, method=None):
    user = frappe.session.user
    if manager(user) or "OMP Cashier" not in frappe.get_roles(user):
        return
    if not service_document(doc, user, "write"):
        # A native DocShare can add write permission after a boolean hook denies
        # it. Enforce the service boundary again before any financial validation.
        frappe.throw(
            "Use el servicio de caja para modificar documentos financieros", frappe.PermissionError
        )


def terminal_permission(doc, user=None, ptype="read"):
    user = user or frappe.session.user
    if manager(user):
        return True
    if ptype != "read" or not doc.enabled or doc.user != user:
        return False
    from open_multi_pos.api import get_brand_context

    try:
        get_brand_context(doc.brand)
    except (frappe.PermissionError, frappe.ValidationError):
        return False
    return True


def terminal_query(user=None):
    user = user or frappe.session.user
    if manager(user):
        return ""
    escaped = frappe.db.escape(user)
    return (
        f"`tabOMP POS Terminal`.enabled=1 AND `tabOMP POS Terminal`.user={escaped} "
        "AND EXISTS (SELECT 1 FROM `tabOMP Business Brand` b "
        "JOIN `tabOMP Brand User` u ON u.parent=b.name "
        "AND u.parenttype='OMP Business Brand' AND u.parentfield='allowed_users' "
        f"WHERE b.name=`tabOMP POS Terminal`.brand AND b.enabled=1 AND u.user={escaped})"
    )


def shift_permission(doc, user=None, ptype="read"):
    user = user or frappe.session.user
    if manager(user) or "OMP Cashier" not in frappe.get_roles(user):
        return True
    if service_document(doc, user, ptype):
        return True
    if ptype != "read" or doc.user != user:
        return False
    from open_multi_pos.xpos_security import authorized_profile

    try:
        authorized_profile(doc.pos_profile)
    except frappe.PermissionError:
        return False
    return True


def _shift_query(table, user):
    user = user or frappe.session.user
    if manager(user) or "OMP Cashier" not in frappe.get_roles(user):
        return ""
    from open_multi_pos.permissions import profile_query

    return (
        f"{table}.user={frappe.db.escape(user)} AND {table}.pos_profile IN "
        "(SELECT `tabPOS Profile`.name FROM `tabPOS Profile` WHERE " + profile_query(user) + ")"
    )


def opening_query(user=None):
    return _shift_query("`tabPOS Opening Entry`", user)


def closing_query(user=None):
    return _shift_query("`tabPOS Closing Entry`", user)
