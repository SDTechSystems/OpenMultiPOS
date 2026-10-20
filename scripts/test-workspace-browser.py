"""Windows Chrome / Linux Chromium workspace E2E using isolated fictional fixtures."""

import argparse
import importlib.util
import json
import secrets
import subprocess
import sys
import unittest
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import frappe
from frappe.sessions import delete_session
from frappe.utils.password import update_password
from pypdf import PdfReader

spec = importlib.util.spec_from_file_location(
    "workspace_fixtures", Path(__file__).with_name("test-workspace-http.py")
)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


class WorkspaceBrowser(fixtures.WorkspaceHTTP):
    def test_browser(self):
        # Only fictional companies, actors and products appear in exported images.
        prior_visible = frappe.get_all(
            "OMP Business Brand", filters={"workspace_visible": 1}, pluck="name"
        )
        sessions = set(frappe.db.sql("SELECT sid FROM tabSessions", pluck=True))
        old = frappe.db.sql(
            "SELECT password, encrypted FROM __Auth WHERE doctype='User' AND name=%s AND fieldname='password'",
            self.user,
            as_dict=True,
        )
        for name in prior_visible:
            frappe.db.set_value(
                "OMP Business Brand",
                name,
                "workspace_visible",
                int(name in {b["brand"] for b in self.businesses[:2]}),
            )
        password = secrets.token_urlsafe(32)
        update_password(self.user, password)
        frappe.db.commit()
        items = [
            self.product(b, barcode="OMP-FICTIONAL-" + uuid4().hex[:8]) for b in self.businesses[:2]
        ]
        try:
            script = Path(__file__).with_name("workspace-smoke.cjs").resolve()
            if OPTIONS.node.endswith(".exe"):
                script = subprocess.check_output(["wslpath", "-w", str(script)], text=True).strip()
            before = self.counts()
            result = subprocess.run(
                [OPTIONS.node, str(script)],
                input=json.dumps(
                    {
                        "base": OPTIONS.base_url,
                        "site": OPTIONS.site,
                        "user": self.user,
                        "password": password,
                        "businesses": self.businesses[:2],
                        "items": items,
                        "newCode": "OMP-MANUAL-" + uuid4().hex[:8],
                        "newBarcode": "OMP-FAKE-" + uuid4().hex[:8],
                    }
                ),
                text=True,
                capture_output=True,
                timeout=240,
            )
            if result.stdout:
                print(result.stdout.strip(), flush=True)
            self.assertEqual(result.returncode, 0, result.stderr[-4000:])
            after = self.counts()
            self.assertEqual(after["Sales Invoice"] - before["Sales Invoice"], 2)
            self.assertEqual(after["Stock Entry"] - before["Stock Entry"], 1)
            pdf = PdfReader(
                Path(__file__).resolve().parent.parent
                / "test-results/workspace/compact-receipt.pdf"
            )
            self.assertEqual(len(pdf.pages), 1)
            self.assertAlmostEqual(float(pdf.pages[0].mediabox.width) * 25.4 / 72, 48, delta=0.5)
            self.assertLess(float(pdf.pages[0].mediabox.height) * 25.4 / 72, 130)
        finally:
            frappe.set_user("Administrator")
            frappe.db.rollback()
            frappe.db.set_value(
                "OMP Business Brand", self.businesses[2]["brand"], "workspace_visible", 1
            )
            for name in prior_visible:
                frappe.db.set_value("OMP Business Brand", name, "workspace_visible", 1)
            if old:
                frappe.db.sql(
                    "UPDATE __Auth SET password=%s, encrypted=%s WHERE doctype='User' AND name=%s AND fieldname='password'",
                    (old[0].password, old[0].encrypted, self.user),
                )
            else:
                frappe.db.sql(
                    "DELETE FROM __Auth WHERE doctype='User' AND name=%s AND fieldname='password'",
                    self.user,
                )
            for sid in set(frappe.db.sql("SELECT sid FROM tabSessions", pluck=True)) - sessions:
                delete_session(sid, reason="Fin de prueba ficticia del espacio administrativo")
            frappe.db.commit()
            frappe.clear_cache()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench", required=True, type=Path)
    parser.add_argument("--site", default="omp.localhost")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--node", default="node")
    OPTIONS = parser.parse_args()
    OPTIONS.bench = OPTIONS.bench.expanduser().resolve()
    address = urlparse(OPTIONS.base_url)
    if (
        address.scheme != "http"
        or address.hostname not in ("127.0.0.1", "localhost")
        or address.username
        or address.password
        or address.path
    ):
        parser.error("Se requiere una URL HTTP loopback sin ruta")
    fixtures.OPTIONS = OPTIONS
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.TestSuite([WorkspaceBrowser("test_browser")])
    )
    sys.exit(not result.wasSuccessful())
