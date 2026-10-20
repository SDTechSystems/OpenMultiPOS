"""Cookie/CSRF browser E2E on a disposable Bench, with fictional native fixtures.

Ephemeral login passwords go to the child over stdin, never arguments/logs/files.
Original hashes are restored and new sessions removed, also after a failed test.
"""

import argparse
import importlib.util
import json
import secrets
import subprocess
import sys
import unittest
from pathlib import Path

import frappe
from frappe.sessions import delete_session
from frappe.utils.password import update_password
from pypdf import PdfReader

spec = importlib.util.spec_from_file_location(
    "omp_native_fixtures", Path(__file__).with_name("test-native-checkout-http.py")
)
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


class NativeCashierBrowser(native.NativeCheckoutHTTPTests):
    def test_browser(self):
        self.stock(quantity=20)
        self.stock(self.nb, quantity=20)
        logins = []
        originals = []
        sessions = set(frappe.db.sql("SELECT sid FROM tabSessions", pluck=True))
        item = frappe.get_doc("Item", self.na["item"])
        prior_barcodes = [row.as_dict() for row in item.barcodes]
        barcode = "OMP-DEMO-7700000000011"
        if not any(row.barcode == barcode for row in item.barcodes):
            item.append("barcodes", {"barcode": barcode})
            item.save()
        try:
            for config in (self.na, self.nb):
                user = config["user"]
                frappe.get_doc("User", user).add_roles(native.fixtures.PRINT_ROLE)
                old = frappe.db.sql(
                    "SELECT password, encrypted FROM __Auth WHERE doctype='User' AND name=%s AND fieldname='password'",
                    user,
                    as_dict=True,
                )
                originals.append((user, old))
                password = secrets.token_urlsafe(32)
                update_password(user, password)
                logins.append({**config, "password": password})
            frappe.db.commit()
            before = self.counts()
            script = Path(__file__).with_name("native-cashier-smoke.cjs").resolve()
            if OPTIONS.node.endswith(".exe"):
                script = subprocess.check_output(["wslpath", "-w", str(script)], text=True).strip()
            result = subprocess.run(
                [OPTIONS.node, str(script)],
                input=json.dumps(
                    {
                        "base": OPTIONS.base_url,
                        "site": OPTIONS.site,
                        "logins": logins,
                        "barcode": barcode,
                    }
                ),
                text=True,
                capture_output=True,
                timeout=240,
            )
            # The JS harness prints only assertion names, never login/request bodies.
            if result.stdout:
                print(result.stdout.strip(), flush=True)
            self.assertEqual(result.returncode, 0, result.stderr[-4000:])
            after = self.counts()
            self.assertEqual(after["Sales Invoice"] - before["Sales Invoice"], 4)
            self.assertEqual(after["Stock Ledger Entry"] - before["Stock Ledger Entry"], 4)
            self.assertGreater(after["GL Entry"], before["GL Entry"])
            for width in (48, 58, 80):
                pdf = PdfReader(
                    Path(__file__).resolve().parent.parent
                    / f"test-results/native-cashier/native-{width}.pdf"
                )
                self.assertEqual(len(pdf.pages), 1)
                self.assertAlmostEqual(
                    float(pdf.pages[0].mediabox.width) * 25.4 / 72, width, delta=0.5
                )
                self.assertLess(float(pdf.pages[0].mediabox.height) * 25.4 / 72, 180)
        finally:
            frappe.set_user("Administrator")
            frappe.db.rollback()
            for user, old in originals:
                if old:
                    frappe.db.sql(
                        "UPDATE __Auth SET password=%s, encrypted=%s WHERE doctype='User' AND name=%s AND fieldname='password'",
                        (old[0].password, old[0].encrypted, user),
                    )
                else:
                    frappe.db.sql(
                        "DELETE FROM __Auth WHERE doctype='User' AND name=%s AND fieldname='password'",
                        user,
                    )
            for sid in set(frappe.db.sql("SELECT sid FROM tabSessions", pluck=True)) - sessions:
                delete_session(sid, reason="Fin de prueba ficticia OpenMultiPOS")
            item = frappe.get_doc("Item", self.na["item"])
            item.set("barcodes", prior_barcodes)
            item.save()
            frappe.db.commit()
            for config in self.native:
                opening = frappe.db.get_value(
                    "OMP POS Terminal", config["terminal"], "opening_entry"
                )
                if (
                    opening
                    and frappe.db.get_value("POS Opening Entry", opening, "status") == "Open"
                ):
                    self.openings.append((config, opening))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench", required=True, type=Path)
    parser.add_argument("--site", default="omp.localhost")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--node", default="node")
    OPTIONS = parser.parse_args()
    OPTIONS.bench = OPTIONS.bench.expanduser().resolve()
    address = native.fixtures.urlparse(OPTIONS.base_url)
    if (
        address.scheme != "http"
        or address.hostname not in ("127.0.0.1", "localhost")
        or address.path
        or address.username
        or address.password
    ):
        parser.error("Se requiere una URL HTTP loopback sin ruta.")
    native.fixtures.OPTIONS = OPTIONS
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.TestSuite([NativeCashierBrowser("test_browser")])
    )
    sys.exit(not result.wasSuccessful())
