"""Native resumable setup cookie/CSRF browser flow using fictional disposable fixtures."""

import argparse
import importlib.util
import json
import secrets
import subprocess
import sys
import unittest
from pathlib import Path
from urllib.parse import urlparse

import frappe
from frappe.sessions import delete_session
from frappe.utils.password import update_password

spec = importlib.util.spec_from_file_location(
    "onboarding_fixtures", Path(__file__).with_name("test-onboarding-http.py")
)
onboarding = importlib.util.module_from_spec(spec)
spec.loader.exec_module(onboarding)


class OnboardingBrowser(onboarding.OnboardingHTTP):
    def test_browser(self):
        new_user = "omp-browser-" + secrets.token_hex(8) + "@example.invalid"
        self.created_users.append(new_user)
        new_password = secrets.token_urlsafe(32)
        old = frappe.db.sql(
            "SELECT password, encrypted FROM __Auth WHERE doctype='User' AND name=%s AND fieldname='password'",
            self.user,
            as_dict=True,
        )
        sessions = set(frappe.db.sql("SELECT sid FROM tabSessions", pluck=True))
        password = secrets.token_urlsafe(32)
        update_password(self.user, password)
        frappe.db.commit()
        try:
            before = frappe.db.count("User", {"name": new_user})
            result = subprocess.run(
                [OPTIONS.node, str(Path(__file__).with_name("onboarding-smoke.cjs").resolve())],
                input=json.dumps(
                    {
                        "base": OPTIONS.base_url,
                        "site": OPTIONS.site,
                        "user": self.user,
                        "password": password,
                        "new_user": new_user,
                        "new_password": new_password,
                    }
                ),
                text=True,
                capture_output=True,
                timeout=180,
            )
            if result.stdout:
                print(result.stdout.strip(), flush=True)
            self.assertEqual(result.returncode, 0, result.stderr[-4000:])
            frappe.db.rollback()
            self.assertEqual(frappe.db.count("User", {"name": new_user}), before + 1)
        finally:
            frappe.db.rollback()
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
                delete_session(sid, reason="Fin de prueba ficticia de garantías")
            frappe.db.commit()


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
    onboarding.fixtures.OPTIONS = OPTIONS
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.TestSuite([OnboardingBrowser("test_browser")])
    )
    sys.exit(not result.wasSuccessful())
