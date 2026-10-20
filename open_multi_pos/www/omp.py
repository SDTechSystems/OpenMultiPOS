import frappe
from frappe.sessions import get_csrf_token

from open_multi_pos.workspace import require_admin

no_cache = 1
sitemap = 0


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/omp"
        raise frappe.Redirect
    require_admin()
    context.no_cache = 1
    context.csrf_token = get_csrf_token()
    context.workspace_user = frappe.session.user
