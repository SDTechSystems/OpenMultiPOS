"""Read-only upstream permission probe, exclusively against the integration fixtures."""

import frappe
from frappe.client import get as get_document


def receipt_context_probe():
    if not frappe.conf.get("allow_tests"):
        raise RuntimeError("Solo se permite en un sitio de pruebas.")
    previous_user = frappe.session.user
    result = {"native_profile_access_denied": False, "xpos_adapter_access_denied": False}
    try:
        frappe.set_user("omp-cashier-a@example.invalid")
        try:
            get_document("POS Profile", "OMP Test Profile B")
        except frappe.PermissionError:
            result["native_profile_access_denied"] = True
        method = frappe.get_attr(
            frappe.override_whitelisted_method("xpos.api.print_formats.get_receipt_context")
        )
        try:
            method("OMP Test Profile B")
        except frappe.PermissionError:
            result["xpos_adapter_access_denied"] = True
        # Never print the returned receipt/company context, even for this probe.
        return result
    finally:
        frappe.set_user(previous_user)
