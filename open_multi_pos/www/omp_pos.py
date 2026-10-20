import frappe
from frappe.sessions import get_csrf_token

from open_multi_pos.cashier import require_cashier

no_cache = 1
sitemap = 0


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/omp_pos"
        raise frappe.Redirect
    require_cashier()
    context.no_cache = 1
    context.csrf_token = get_csrf_token()
    context.cashier_user = frappe.session.user
