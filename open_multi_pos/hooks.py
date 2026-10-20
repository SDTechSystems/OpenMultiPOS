from open_multi_pos.xpos_routes import METHOD_OVERRIDES as _METHOD_OVERRIDES

app_name = "open_multi_pos"
app_title = "OpenMultiPOS"
app_publisher = "OpenMultiPOS contributors"
app_description = "Marcas y contexto de impresión para ERPNext"
app_email = ""
app_license = "GPL-3.0-only"
required_apps = ["erpnext"]
after_install = "open_multi_pos.setup.ensure_cashier_role"
after_migrate = "open_multi_pos.setup.ensure_cashier_role"

permission_query_conditions = {
    "OMP Business Brand": "open_multi_pos.permissions.brand_query",
    "POS Profile": "open_multi_pos.permissions.profile_query",
    "Sales Invoice": "open_multi_pos.permissions.sales_invoice_query",
    "POS Invoice": "open_multi_pos.permissions.pos_invoice_query",
}
has_permission = {
    "OMP Business Brand": "open_multi_pos.permissions.brand_permission",
    "POS Profile": "open_multi_pos.permissions.profile_permission",
    "Sales Invoice": "open_multi_pos.permissions.invoice_permission",
    "POS Invoice": "open_multi_pos.permissions.invoice_permission",
}

# Frappe applies these adapters to both API v1 and v2 method dispatch.
override_whitelisted_methods = _METHOD_OVERRIDES

# Runs after cookie/API authentication and before website rendering.
auth_hooks = ["open_multi_pos.xpos_security.authorize_print_page"]
