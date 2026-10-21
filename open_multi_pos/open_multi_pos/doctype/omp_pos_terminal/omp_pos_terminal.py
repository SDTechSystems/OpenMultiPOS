from uuid import uuid4

import frappe
from frappe.model.document import Document


class OMPPOSTerminal(Document):
    def autoname(self):
        self.name = str(uuid4())

    def validate(self):
        if not self.is_new():
            previous = frappe.db.get_value(self.doctype, self.name, ["brand", "user"], as_dict=True)
            if previous and (previous.brand != self.brand or previous.user != self.user):
                frappe.throw("Cree otra terminal para cambiar negocio o usuario")
        if not frappe.db.get_value("User", self.user, "enabled"):
            frappe.throw("La terminal requiere un usuario habilitado")
