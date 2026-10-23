from open_multi_pos.xpos_routes import METHOD_OVERRIDES as _METHOD_OVERRIDES

app_name = "open_multi_pos"
app_title = "OpenMultiPOS"
app_publisher = "OpenMultiPOS contributors"
app_description = "Marcas, caja nativa y contexto de impresión para ERPNext"
app_email = ""
app_license = "GPL-3.0-only"
required_apps = ["erpnext"]
before_install = "open_multi_pos.setup.create_cashier_role"
after_install = "open_multi_pos.setup.ensure_cashier_role"
after_migrate = "open_multi_pos.setup.ensure_cashier_role"

permission_query_conditions = {
    "OMP Business Brand": "open_multi_pos.permissions.brand_query",
    "POS Profile": "open_multi_pos.permissions.profile_query",
    "Sales Invoice": "open_multi_pos.permissions.sales_invoice_query",
    "POS Invoice": "open_multi_pos.permissions.pos_invoice_query",
    "Item": "open_multi_pos.permissions.item_query",
    "Customer": "open_multi_pos.permissions.customer_query",
    "Bin": "open_multi_pos.permissions.bin_query",
    "Sales Order": "open_multi_pos.permissions.deny_cashier_query",
    "Quotation": "open_multi_pos.permissions.deny_cashier_query",
    "Delivery Note": "open_multi_pos.permissions.deny_cashier_query",
    "OMP POS Terminal": "open_multi_pos.checkout_permissions.terminal_query",
    "POS Opening Entry": "open_multi_pos.checkout_permissions.opening_query",
    "POS Closing Entry": "open_multi_pos.checkout_permissions.closing_query",
}
has_permission = {
    "OMP Business Brand": "open_multi_pos.permissions.brand_permission",
    "POS Profile": "open_multi_pos.permissions.profile_permission",
    "Sales Invoice": "open_multi_pos.permissions.invoice_permission",
    "POS Invoice": "open_multi_pos.permissions.invoice_permission",
    "Item": "open_multi_pos.permissions.item_permission",
    "Customer": "open_multi_pos.permissions.customer_permission",
    "Bin": "open_multi_pos.permissions.bin_permission",
    "Sales Order": "open_multi_pos.permissions.deny_cashier_permission",
    "Quotation": "open_multi_pos.permissions.deny_cashier_permission",
    "Delivery Note": "open_multi_pos.permissions.deny_cashier_permission",
    "OMP POS Terminal": "open_multi_pos.checkout_permissions.terminal_permission",
    "POS Opening Entry": "open_multi_pos.checkout_permissions.shift_permission",
    "POS Closing Entry": "open_multi_pos.checkout_permissions.shift_permission",
}

# Frappe applies these adapters to both API v1 and v2 method dispatch.
override_whitelisted_methods = _METHOD_OVERRIDES

# Runs after cookie/API authentication and before website rendering.
auth_hooks = [
    "open_multi_pos.upstream_gate.authorize_request",
    "open_multi_pos.xpos_security.authorize_print_page",
]

doc_events = {
    doctype: {
        event: "open_multi_pos.checkout_permissions.guard_native_write"
        for event in ("before_validate", "before_cancel", "before_update_after_submit")
    }
    for doctype in ("Sales Invoice", "POS Opening Entry", "POS Closing Entry")
}

# OMP estimates may be edited natively; guided submission preserves their reviewed snapshot.
doc_events["Landed Cost Voucher"] = {"before_submit": "open_multi_pos.landed_costs.guard_submit"}

doc_events["Warranty Claim"] = {
    "validate": "open_multi_pos.warranties.guard_links",
    "on_trash": "open_multi_pos.warranties.guard_delete",
}

# Administrators may operate one personal opening per workspace business.
# Native closing queries already scope invoices by profile AND owner.
extend_doctype_class = {
    "POS Opening Entry": ["open_multi_pos.opening.WorkspaceOpeningMixin"],
    "Sales Invoice": ["open_multi_pos.opening.WorkspaceInvoiceMixin"],
}

extend_bootinfo = [
    "open_multi_pos.localization.extend_boot",
    "open_multi_pos.upstream_gate.filter_boot",
]

# Extend the native Printing section without changing ERPNext sources.
doctype_js = {"Print Settings": "public/print-settings-preview.js"}
