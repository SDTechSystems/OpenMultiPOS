"""Scoped multi-business openings; all native accounting validation remains active."""

import frappe

from open_multi_pos.api import get_brand_context
from open_multi_pos.permissions import manager


class WorkspaceOpeningMixin:
    def workspace_opening(self):
        if self.user != frappe.session.user or not manager(self.user):
            return False
        brand = frappe.db.get_value(
            "OMP Business Brand",
            {"pos_profile": self.pos_profile, "enabled": 1, "workspace_visible": 1},
            "name",
        )
        if not brand:
            return False
        get_brand_context(brand)
        # Also serialize direct Desk openings with the checkout service.
        frappe.db.get_value("POS Profile", self.pos_profile, "name", for_update=True)
        return True

    def check_open_pos_exists(self):
        if not self.workspace_opening():
            return super().check_open_pos_exists()
        if frappe.db.get_value(
            "POS Opening Entry",
            {"pos_profile": self.pos_profile, "user": self.user, "status": "Open"},
            "name",
            for_update=True,
        ):
            frappe.throw(
                "Ya tienes una caja abierta para este negocio. Usa esa apertura antes de crear otra."
            )

    def check_user_already_assigned(self):
        if not self.workspace_opening():
            return super().check_user_already_assigned()


class WorkspaceInvoiceMixin:
    def validate_pos_opening_entry(self):
        if not manager(frappe.session.user):
            return super().validate_pos_opening_entry()
        brand = frappe.db.get_value(
            "OMP Business Brand",
            {"pos_profile": self.pos_profile, "enabled": 1, "workspace_visible": 1},
            "name",
        )
        if not brand:
            return super().validate_pos_opening_entry()
        context = get_brand_context(brand)
        if self.company != context["company"] or self.owner != frappe.session.user:
            frappe.throw(
                "La factura no pertenece al usuario y negocio activos", frappe.PermissionError
            )
        rows = frappe.db.get_values(
            "POS Opening Entry",
            filters={
                "pos_profile": self.pos_profile,
                "user": frappe.session.user,
                "status": "Open",
                "docstatus": 1,
            },
            fieldname=["name", "period_start_date", "company"],
            as_dict=True,
            for_update=True,
        )
        if len(rows) != 1 or rows[0].company != self.company:
            frappe.throw("Debe existir una apertura personal para este negocio")
        if frappe.utils.get_date_str(rows[0].period_start_date) != frappe.utils.today():
            frappe.throw("Cierra la apertura anterior y abre la caja de hoy")
