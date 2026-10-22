"""Fail closed for legacy X POS HTTP entry points; native Desk remains available."""

import re

import frappe

from open_multi_pos.xpos_routes import METHOD_OVERRIDES

# Only the three document-authorizing adapters are usable. Invoice operations
# already mapped to unavailable_invoice_operation stay denied here as well.
REVIEWED = {
    method
    for method, adapter in METHOD_OVERRIDES.items()
    if not adapter.endswith(".unavailable_invoice_operation")
}
DOCUMENT_RUNNERS = {
    "run_doc_method",
    "frappe.handler.run_doc_method",
    "frappe.api.v2.run_doc_method",
}
# Raw report queries bypass record hooks; cashiers only use /omp_pos.
CASHIER_DENIED_METHODS = {
    "frappe.desk.query_report.run",
    "frappe.desk.query_report.background_enqueue_run",
    "frappe.desk.query_report.export_query",
    "frappe.desk.reportview.export_query",
}


def deny():
    frappe.throw(
        "Esta función de X POS no está habilitada. Usa Administración o Caja de OpenMultiPOS.",
        frappe.PermissionError,
    )


def check_method(method):
    if isinstance(method, str) and (method == "xpos" or method.startswith("xpos.")):
        if method not in REVIEWED:
            deny()
        # Do not silently fall back to upstream if installation order changes.
        if frappe.override_whitelisted_method(method) != METHOD_OVERRIDES[method]:
            deny()


def check_controller(doctype, method, *, module_function=False):
    if not isinstance(doctype, str) or not isinstance(method, str):
        return
    if not frappe.db.exists("DocType", doctype):
        return  # Preserve the framework's normal missing-document response.
    if module_function:
        from frappe.modules.utils import load_doctype_module

        if load_doctype_module(doctype).__name__.startswith("xpos."):
            deny()
    else:
        from frappe.model.base_document import get_controller

        function = getattr(get_controller(doctype), method, None)
        if getattr(function, "__module__", "").startswith("xpos."):
            deny()


def authorize_request():
    """Runs after authentication, before v1/v2 RPC, document methods or pages."""
    path = frappe.request.path.rstrip("/")
    if path == "/xpos" or path == "/xpos.html" or path.startswith("/xpos/"):
        deny()  # Includes the old offline service worker and manifest route.
    args = frappe.form_dict
    method = args.get("cmd")
    if not method:
        matched = re.fullmatch(r"/api/(?:v[12]/)?method/(.+)", path)
        if matched:
            method = matched[1]
            if path.startswith("/api/v2/") and "/" in method:
                doctype, method = method.split("/", 1)
                check_controller(doctype, method, module_function=True)
            else:
                method = method.split("/", 1)[0]  # Native v1 compatibility rule.
    check_method(method)
    if isinstance(method, str) and method in CASHIER_DENIED_METHODS:
        from open_multi_pos.permissions import manager

        user = frappe.session.user
        if not manager(user) and "OMP Cashier" in frappe.get_roles(user):
            deny()
    if isinstance(method, str) and method in DOCUMENT_RUNNERS:
        document = args.get("document") or args.get("docs") or {}
        if isinstance(document, str):
            document = frappe.parse_json(document)
        doctype = args.get("dt") or (
            document.get("doctype") if isinstance(document, dict) else None
        )
        check_controller(doctype, args.get("method"))
    matched = re.fullmatch(r"/api/v2/document/([^/]+)/.+/method/([^/]+)", path)
    if matched:
        check_controller(matched[1], matched[2])
    matched = re.fullmatch(r"/api/(?:v1/)?resource/([^/]+)/.+", path)
    if matched and args.get("run_method"):
        check_controller(matched[1], args.get("run_method"))


def filter_boot(bootinfo):
    """Remove settings upstream injects without a native read permission check."""
    from open_multi_pos.permissions import manager

    if manager(frappe.session.user):
        return
    keys = {
        "selling_settings",
        "accounts_setting",
        "buying_settings",
        "stock_settings",
        "pos_settings",
    }
    for key in list(bootinfo):
        if key in keys or key.startswith("xpos_"):
            bootinfo.pop(key, None)
