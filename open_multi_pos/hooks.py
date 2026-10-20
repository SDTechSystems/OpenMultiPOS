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
}
has_permission = {
    "OMP Business Brand": "open_multi_pos.permissions.brand_permission",
    "POS Profile": "open_multi_pos.permissions.profile_permission",
}
