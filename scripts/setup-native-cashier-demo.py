"""Leave a fictional review terminal on the disposable local Bench.

Run AFTER permission/native HTTP suites, never against an operational site.
Credentials stay in a mode-600 local file, never stdout or repository assets.
"""

import argparse
import json
import os
import secrets
import tempfile
from pathlib import Path

import frappe
from frappe.permissions import add_permission
from frappe.utils import get_system_timezone
from frappe.utils.password import update_password


def setup(options):
    os.chdir(options.bench / "sites")
    frappe.init(options.site, sites_path=str(options.bench / "sites"))
    frappe.connect()
    frappe.set_user("Administrator")
    try:
        if not frappe.conf.get("allow_tests"):
            raise RuntimeError("Solo se permite en sitio desechable con allow_tests.")
        if get_system_timezone() != "America/Bogota":
            raise RuntimeError("Configure System Settings.time_zone = America/Bogota primero.")
        source = frappe.get_doc("POS Profile", "OMP Native Profile A")
        if source.company != "OMP Test Company A" or source.customer != "OMP HTTP Customer":
            raise RuntimeError("Primero ejecute las suites Bench y HTTP con fixtures ficticios.")
        user, profile_name = "omp-demo-cashier@example.invalid", "OMP Demo Profile"
        price_list, customer, item = "OMP Demo COP", "OMP Demo Customer", "OMP-NATIVE-STOCK-A"
        if not frappe.db.exists("Price List", price_list):
            frappe.get_doc(
                {
                    "doctype": "Price List",
                    "price_list_name": price_list,
                    "currency": "COP",
                    "selling": 1,
                }
            ).insert()
        if not frappe.db.exists("Item Price", {"item_code": item, "price_list": price_list}):
            frappe.get_doc(
                {
                    "doctype": "Item Price",
                    "item_code": item,
                    "price_list": price_list,
                    "price_list_rate": 1000,
                    "currency": "COP",
                    "uom": "Nos",
                }
            ).insert()
        if not frappe.db.exists("Customer", customer):
            template = frappe.get_doc("Customer", source.customer)
            frappe.get_doc(
                {
                    "doctype": "Customer",
                    "customer_name": customer,
                    "customer_type": "Individual",
                    "customer_group": template.customer_group,
                    "territory": template.territory,
                    "default_price_list": price_list,
                }
            ).insert()
        warehouse = frappe.db.get_value(
            "Warehouse", {"warehouse_name": "OMP Demo Warehouse", "company": source.company}
        )
        if not warehouse:
            warehouse = (
                frappe.get_doc(
                    {
                        "doctype": "Warehouse",
                        "warehouse_name": "OMP Demo Warehouse",
                        "company": source.company,
                        "parent_warehouse": frappe.db.get_value(
                            "Warehouse", source.warehouse, "parent_warehouse"
                        ),
                    }
                )
                .insert()
                .name
            )
        role = "OMP Demo Receipt Printer"
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role}).insert()
        add_permission("Sales Invoice", role, ptype="read")
        rule = frappe.db.get_value("Custom DocPerm", {"parent": "Sales Invoice", "role": role})
        frappe.db.set_value("Custom DocPerm", rule, "print", 1)
        if not frappe.db.exists("User", user):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": user,
                    "first_name": "Cajero ficticio OMP",
                    "send_welcome_email": 0,
                    "enabled": 1,
                    "roles": [{"role": name} for name in ("Sales User", "OMP Cashier", role)],
                }
            ).insert()
        if not frappe.db.exists(
            "User Permission", {"user": user, "allow": "Company", "for_value": source.company}
        ):
            frappe.get_doc(
                {
                    "doctype": "User Permission",
                    "user": user,
                    "allow": "Company",
                    "for_value": source.company,
                    "apply_to_all_doctypes": 1,
                }
            ).insert()
        if not frappe.db.exists("POS Profile", profile_name):
            profile = frappe.copy_doc(source)
            profile.name = profile_name
            profile.disabled = 0
            profile.warehouse = warehouse
            profile.set("applicable_for_users", [{"user": user}])
            profile.insert()
        configured = frappe.get_doc("POS Profile", profile_name)
        if configured.company != source.company or configured.warehouse != warehouse:
            raise RuntimeError(
                "El perfil de revisión existente debe usar su almacén ficticio separado."
            )
        if configured.customer != customer or configured.selling_price_list != price_list:
            configured.customer = customer
            configured.selling_price_list = price_list
            configured.save()
        brand = frappe.db.get_value("OMP Business Brand", {"pos_profile": profile_name})
        if not brand:
            brand = (
                frappe.get_doc(
                    {
                        "doctype": "OMP Business Brand",
                        "display_name": "Marca ficticia OMP",
                        "company": source.company,
                        "warehouse": warehouse,
                        "pos_profile": profile_name,
                        "printer_profile": "generic-58",
                        "receipt_footer": "Gracias · demostración ficticia",
                        "qr_url": "https://example.com/omp-demo",
                        "allowed_users": [{"user": user}],
                    }
                )
                .insert()
                .name
            )
        terminal = frappe.db.get_value("OMP POS Terminal", {"brand": brand, "user": user})
        if not terminal:
            terminal = (
                frappe.get_doc(
                    {
                        "doctype": "OMP POS Terminal",
                        "display_name": "Caja ficticia de revisión",
                        "brand": brand,
                        "user": user,
                        "enabled": 1,
                    }
                )
                .insert()
                .name
            )
        # Native vouchers only. Top up the fictional SKU without replacing stock.
        current = (
            frappe.db.get_value("Bin", {"item_code": item, "warehouse": warehouse}, "actual_qty")
            or 0
        )
        if current < 20:
            company = frappe.get_doc("Company", source.company)
            doc = frappe.get_doc(
                {
                    "doctype": "Stock Entry",
                    "stock_entry_type": "Material Receipt",
                    "company": source.company,
                    "items": [
                        {
                            "item_code": item,
                            "qty": 20 - current,
                            "t_warehouse": warehouse,
                            "basic_rate": 100,
                            "expense_account": company.stock_adjustment_account,
                            "cost_center": company.cost_center,
                        }
                    ],
                }
            )
            doc.insert()
            doc.submit()
        if frappe.db.get_single_value("POS Settings", "invoice_type") != "Sales Invoice":
            raise RuntimeError("Configure Sales Invoice antes de preparar la caja de revisión.")
        path = options.credentials.expanduser().absolute()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.is_symlink():
            raise RuntimeError("El archivo privado no puede ser un enlace simbólico.")
        credentials = json.loads(path.read_text()) if path.exists() else {}
        password = (
            credentials.get("cashier_password") if credentials.get("cashier_user") == user else None
        )
        password = password or secrets.token_urlsafe(32)
        update_password(user, password)
        credentials.update(cashier_user=user, cashier_password=password, cashier_terminal=terminal)
        # Atomic replacement preserves the existing administrator credential.
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as target:
            json.dump(credentials, target, indent=2)
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
            temporary = target.name
        os.replace(temporary, path)
        frappe.db.commit()
        frappe.clear_cache()
        print(
            "Caja ficticia preparada: /omp_pos. Credenciales guardadas en archivo privado; SKU OMP-NATIVE-STOCK-A."
        )
    finally:
        frappe.db.rollback()
        frappe.destroy()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench", required=True, type=Path)
    parser.add_argument("--site", default="omp.localhost")
    parser.add_argument(
        "--credentials",
        type=Path,
        default=Path.home() / ".local/share/openmultipos/private/development-credentials.json",
    )
    setup(parser.parse_args())
