"""HTTP surface of the cashier; internal native services keep their own permissions."""

import re

import frappe

from open_multi_pos.permissions import manager
from open_multi_pos.upstream_gate import REVIEWED, deny
from open_multi_pos.xpos_routes import INVOICE_DOCTYPES, METHOD_OVERRIDES

READ_DOCTYPES = {
    "OMP Business Brand",
    "POS Profile",
    "Sales Invoice",
    "POS Invoice",
    "Item",
    "Customer",
    "Bin",
    "OMP POS Terminal",
    "POS Opening Entry",
    "POS Closing Entry",
}
EMPTY_LISTS = {"Sales Order", "Quotation", "Delivery Note"}
CASHIER_METHODS = {
    "open_multi_pos." + name
    for name in (
        "cashier.terminals",
        "cashier.context",
        "cashier.search",
        "cashier.receipt",
        "checkout.quote",
        "checkout.checkout",
        "checkout.get_status",
        "checkout.abandon_checkout",
        "checkout.open_shift",
        "checkout.shift_summary",
        "checkout.close_shift",
    )
}
SESSION_METHODS = {
    "login",
    "logout",
    "ping",
    "frappe.auth.get_logged_user",
    "frappe.core.doctype.user.user.update_password",
    "frappe.core.doctype.user.user.test_password_strength",
}
DOWNLOAD_METHODS = {"download_file", "frappe.handler.download_file"}
LEGACY_DOWNLOADS = {
    "frappe.utils.file_manager.download_file",
    "frappe.core.doctype.file.file.download_file",
}
HTML_PRINT = "frappe.www.printview.get_html_and_style"
PDF_PRINT = "frappe.utils.print_format.download_pdf"
FIELD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def bare_field(value):
    if not isinstance(value, str) or not FIELD.fullmatch(value):
        deny()


def checked_list(doctype, args):
    if not isinstance(doctype, str) or doctype not in READ_DOCTYPES | EMPTY_LISTS:
        deny()
    if any(key in args for key in ("parent", "expand", "expand_links", "group_by", "run_method")):
        deny()
    fields = frappe.parse_json(args.get("fields"))
    if fields is None or fields == "":
        fields = ["name"]
    if not isinstance(fields, list) or len(fields) > 64:
        deny()
    for field in fields:
        if field != "*":
            bare_field(field)
    for key in ("limit", "limit_page_length"):
        if key in args:
            try:
                size = int(args[key])
            except (TypeError, ValueError, OverflowError):
                deny()
            if not 1 <= size <= 100:
                deny()
    order = args.get("order_by")
    if order and (
        not isinstance(order, str)
        or not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*(?: +(asc|desc))?(?:, *[A-Za-z_][A-Za-z0-9_]*(?: +(asc|desc))?)*",
            order,
            re.I,
        )
    ):
        deny()
    for key in ("filters", "or_filters"):
        filters = frappe.parse_json(args.get(key))
        if filters is None:
            continue
        if isinstance(filters, dict):
            if len(filters) > 64:
                deny()
            for field in filters:
                bare_field(field)
        elif isinstance(filters, list):
            if len(filters) > 64:
                deny()
            for item in filters:
                if not isinstance(item, list) or len(item) not in (3, 4):
                    deny()
                if len(item) == 4 and item[0] != doctype:
                    deny()
                bare_field(item[-3])
        else:
            deny()


def checked_print(doctype, name):
    from open_multi_pos.xpos_security import checked_invoice

    if doctype not in INVOICE_DOCTYPES or not isinstance(name, str) or not name:
        deny()
    checked_invoice(doctype, name).check_permission("print")


def checked_download(url, fid=None):
    if not isinstance(url, str) or not url.startswith(("/private/files/", "/files/")):
        deny()
    if fid is not None and not isinstance(fid, str):
        deny()
    filters = {"file_url": url}
    if fid:
        filters["name"] = fid
    for row in frappe.get_all(
        "File", filters=filters, fields=["name", "attached_to_doctype", "attached_to_name"]
    ):
        if row.attached_to_doctype not in {"Item", *INVOICE_DOCTYPES} or not row.attached_to_name:
            continue
        try:
            parent = frappe.get_doc(row.attached_to_doctype, row.attached_to_name)
            if parent.has_permission("read") and frappe.get_doc("File", row.name).is_downloadable():
                return
        except frappe.DoesNotExistError:
            frappe.clear_last_message()
            continue
    deny()


def rpc(method, *, version2=False):
    if not isinstance(method, str):
        deny()
    args = frappe.form_dict
    adapters = {METHOD_OVERRIDES[name] for name in REVIEWED}
    allowed = CASHIER_METHODS | SESSION_METHODS | REVIEWED | adapters
    if method in allowed:
        expected = METHOD_OVERRIDES[method] if method in REVIEWED else method
        if frappe.override_whitelisted_method(method) != expected:
            deny()
        return  # Native whitelisting, verbs, CSRF and service authorization still run.
    if method in DOWNLOAD_METHODS | LEGACY_DOWNLOADS:
        if method in LEGACY_DOWNLOADS and version2:
            deny()  # Native v2 cannot resolve the legacy short override target.
        expected = "download_file" if method in LEGACY_DOWNLOADS else method
        if frappe.override_whitelisted_method(method) != expected:
            deny()
        checked_download(args.get("file_url"))
    elif method == "frappe.client.get_list":
        if frappe.override_whitelisted_method(method) != method:
            deny()
        checked_list(args.get("doctype"), args)
    elif method in (HTML_PRINT, PDF_PRINT):
        if frappe.override_whitelisted_method(method) != method:
            deny()
        if method == HTML_PRINT:
            checked_print(args.get("doc"), args.get("name"))
        else:
            if "doc" in args:
                deny()
            checked_print(args.get("doctype"), args.get("name"))
    else:
        deny()


def authorize():
    user = frappe.session.user
    if manager(user) or "OMP Cashier" not in frappe.get_roles(user):
        return
    args, request = frappe.form_dict, frappe.request
    if args.get("cmd"):
        rpc(args.cmd)  # Frappe dispatches cmd before API paths, pages and private files.
        return
    path = request.path
    if path.startswith("/api/"):
        from frappe.api import API_URL_MAP, v1, v2
        from werkzeug.exceptions import HTTPException

        try:
            endpoint, values = API_URL_MAP.bind_to_environ(request.environ).match()
        except HTTPException:
            deny()
        if endpoint in (v1.handle_rpc_call, v2.handle_rpc_call):
            if values.get("doctype"):
                deny()
            method = values["method"]
            rpc(
                method.split("/", 1)[0] if endpoint == v1.handle_rpc_call else method,
                version2=endpoint == v2.handle_rpc_call,
            )
        elif endpoint in (v2.login, v2.logout, frappe.ping):
            return
        elif endpoint in (v1.document_list, v2.document_list):
            checked_list(values["doctype"], args)
        elif endpoint in (v1.read_doc, v2.read_doc):
            if values["doctype"] not in READ_DOCTYPES or any(
                key in args for key in ("expand", "expand_links", "run_method")
            ):
                deny()
        else:
            deny()
        return
    if path.startswith("/private/files/"):
        checked_download(path, args.get("fid"))
        return
    page = path.strip("/ ")
    if page.endswith(".html"):
        page = page[:-5]
    if page in {"", "omp", "desk", "app"} or page.startswith(("desk/", "app/")):
        from werkzeug.exceptions import HTTPException
        from werkzeug.utils import redirect

        response = redirect("/omp_pos", code=303)
        response.headers["Cache-Control"] = "no-store"
        raise HTTPException(response=response)
    if page in {"omp_pos", "login", "update-password", "message"}:
        return
    if page == "printview":
        if "doc" in args:
            deny()
        checked_print(args.get("doctype"), args.get("name"))
    elif page.partition("/")[0] in INVOICE_DOCTYPES:
        if "doc" in args:
            deny()
        doctype, _, name = page.partition("/")
        checked_print(doctype, name)
    elif not path.startswith(("/assets/", "/files/")):
        deny()
