import frappe
from frappe.model.document import Document

from open_multi_pos.hardware import printer_profiles
from open_multi_pos.sku import business_initials, validate_prefix
from open_multi_pos.validation import safe_qr_url


class OMPBusinessBrand(Document):
    def validate(self):
        try:
            self.sku_prefix = validate_prefix(
                self.get("sku_prefix") or business_initials(self.display_name)
            )
        except ValueError as exc:
            frappe.throw(str(exc))
        warehouse = frappe.get_doc("Warehouse", self.warehouse)
        profile = frappe.get_doc("POS Profile", self.pos_profile)
        if warehouse.company != self.company or profile.company != self.company:
            frappe.throw("Empresa de marca, almacén y perfil POS debe coincidir")
        if profile.warehouse != self.warehouse:
            frappe.throw("Almacén debe coincidir con el perfil POS")
        if self.printer_profile not in printer_profiles():
            frappe.throw("Perfil de impresora desconocido")
        if self.qr_url:
            try:
                safe_qr_url(self.qr_url)
            except ValueError as exc:
                frappe.throw(str(exc))
        users = [row.user for row in self.allowed_users]
        if len(users) != len(set(users)) or any(
            user in ("Guest", "Administrator") for user in users
        ):
            frappe.throw("Usuarios repetidos o reservados en la lista de acceso")
