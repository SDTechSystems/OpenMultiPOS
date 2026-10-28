"""Resumable setup over real HTTP on a disposable, fictional site."""

import argparse
import importlib.util
import json
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import frappe

spec = importlib.util.spec_from_file_location(
    "workspace_fixtures", Path(__file__).with_name("test-workspace-http.py")
)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


class OnboardingHTTP(fixtures.WorkspaceHTTP):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.old_progress = frappe.db.get_value("OMP Setup Progress", "Workspace", "state_json")
        cls.created_users = []
        cls.addClassCleanup(cls.restore_setup)

    @classmethod
    def restore_setup(cls):
        frappe.db.rollback()
        frappe.set_user("Administrator")
        if cls.old_progress:
            frappe.db.set_value("OMP Setup Progress", "Workspace", "state_json", cls.old_progress)
        elif frappe.db.exists("OMP Setup Progress", "Workspace"):
            frappe.delete_doc("OMP Setup Progress", "Workspace")
        for email in cls.created_users:
            if frappe.db.exists("User", email):
                frappe.db.set_value("User", email, "enabled", 0)
        frappe.db.commit()

    def apply_data(self, **changes):
        data = {
            "display_name": "Preparación ficticia " + uuid4().hex[:8],
            "company": self.businesses[0]["company"],
            "legal_name": "",
            "abbr": "",
            "currency": "COP",
        }
        return {"action": "business", "request_id": str(uuid4()), "data": data, **changes}

    def test_01_concurrent_retry_is_one_native_business(self):
        data = self.apply_data()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(lambda _: self.request("onboarding.apply", data, post=True), range(2))
            )
        for response in responses:
            self.assertIn(response.status_code, (200, 409), response.text[-1600:])
        completed = [
            response.json()["message"] for response in responses if response.status_code == 200
        ]
        self.assertTrue(completed)
        replay = self.result("onboarding.apply", data, post=True)
        self.assertTrue(all(value == replay for value in completed))
        brand = replay["result"]["brand"]
        frappe.db.rollback()
        self.assertEqual(
            frappe.db.count("OMP Business Brand", {"display_name": data["data"]["display_name"]}), 1
        )
        context = self.result("workspace.business", {"brand": brand})
        self.businesses.append(context)
        self.assertEqual(
            self.result("onboarding.status", {"request_id": data["request_id"]}, post=True)[
                "result"
            ]["brand"],
            brand,
        )
        data["data"]["display_name"] += " cambiado"
        self.assertEqual(self.request("onboarding.apply", data, post=True).status_code, 409)

    def test_02_abandon_fences_late_writes(self):
        data = self.apply_data()
        args = {"request_id": data["request_id"]}
        self.assertEqual(self.result("onboarding.status", args, post=True)["status"], "not_found")
        self.assertEqual(self.result("onboarding.abandon", args, post=True)["status"], "abandoned")
        self.assertEqual(self.request("onboarding.apply", data, post=True).status_code, 409)
        frappe.db.rollback()
        self.assertFalse(
            frappe.db.exists("OMP Business Brand", {"display_name": data["data"]["display_name"]})
        )

    def test_03_password_is_never_journaled_or_reset_by_replay(self):
        email = "omp-setup-" + uuid4().hex[:10] + "@example.invalid"
        self.created_users.append(email)
        password = "Fictional-only-" + uuid4().hex
        data = self.apply_data(
            action="user",
            data={
                "email": email,
                "full_name": "Cuenta ficticia",
                "password": password,
                "role": "admin",
                "brands": [],
            },
        )
        result = self.result("onboarding.apply", data, post=True)
        data["data"]["password"] = "Different-only-" + uuid4().hex
        self.assertEqual(self.result("onboarding.apply", data, post=True), result)
        frappe.db.rollback()
        from frappe.utils.password import check_password

        self.assertEqual(check_password(email, password), email)
        rows = frappe.get_all("OMP Setup Request", filters={"target_name": email}, fields=["*"])
        self.assertEqual(len(rows), 1)
        self.assertNotIn(password, json.dumps(rows, default=str))
        self.assertNotIn(data["data"]["password"], json.dumps(rows, default=str))

    def test_04_cursor_and_current_preferences_are_server_checked(self):
        current = self.result("onboarding.state", post=True)
        self.assertTrue(current["checks"]["account"])
        self.assertTrue(current["checks"]["businesses"])
        self.assertEqual(
            self.request(
                "onboarding.update", {"step": "preferences", "fingerprint": "stale"}, post=True
            ).status_code,
            409,
        )
        result = self.result(
            "onboarding.update",
            {"step": "preferences", "fingerprint": current["hashes"]["preferences"]},
            post=True,
        )
        self.assertTrue(result["checks"]["preferences"])
        resumed = self.result("onboarding.state", post=True)
        self.assertTrue(resumed["active"])
        self.assertEqual(resumed["step"], "preferences")
        self.assertEqual(
            self.request(
                "onboarding.update", {"step": "recovery", "finish": True}, post=True
            ).status_code,
            409,
        )

    def test_05_stock_and_receipt_confirmation_use_native_state(self):
        self.product()
        current = self.result("onboarding.state", post=True)
        self.assertTrue(current["checks"]["inventory"])
        brand = next(
            row for row in current["brands"] if row["brand"] == self.businesses[0]["brand"]
        )
        result = self.result(
            "onboarding.update",
            {"step": "receipt", "brand": brand["brand"], "fingerprint": brand["receipt_hash"]},
            post=True,
        )
        self.assertTrue(
            next(row for row in result["brands"] if row["brand"] == brand["brand"])[
                "receipt_reviewed"
            ]
        )
        frappe.db.rollback()
        old = frappe.db.get_value("OMP Business Brand", brand["brand"], "receipt_footer")
        try:
            frappe.db.set_value(
                "OMP Business Brand", brand["brand"], "receipt_footer", "Cambio ficticio"
            )
            frappe.db.commit()
            result = self.result("onboarding.state", post=True)
            self.assertFalse(
                next(row for row in result["brands"] if row["brand"] == brand["brand"])[
                    "receipt_reviewed"
                ]
            )
            self.assertEqual(
                self.request(
                    "onboarding.update",
                    {
                        "step": "receipt",
                        "brand": brand["brand"],
                        "fingerprint": brand["receipt_hash"],
                    },
                    post=True,
                ).status_code,
                409,
            )
        finally:
            frappe.db.set_value("OMP Business Brand", brand["brand"], "receipt_footer", old)
            frappe.db.commit()

    def test_06_guest_and_get_cannot_mutate_setup(self):
        for method, args in (
            ("state", {}),
            ("update", {"step": "account"}),
            ("apply", self.apply_data()),
            ("status", {"request_id": str(uuid4())}),
            ("abandon", {"request_id": str(uuid4())}),
        ):
            self.assertIn(
                self.request("onboarding." + method, args, post=True, guest=True).status_code,
                (401, 403),
            )
            self.assertEqual(self.request("onboarding." + method, args).status_code, 403)

    def test_07_first_account_is_claimed_once_even_after_disabling(self):
        frappe.db.rollback()
        saved = frappe.db.get_value("OMP Setup Progress", "Workspace", "state_json")
        holders = frappe.get_all(
            "Has Role", filters={"parenttype": "User", "role": "OMP Administrator"}, pluck="parent"
        )
        self.assertTrue(
            all(email.endswith(".invalid") for email in holders),
            "Only fictional users may be altered",
        )
        roles = {
            email: [row.role for row in frappe.get_doc("User", email).roles] for email in holders
        }
        email = "omp-first-" + uuid4().hex[:10] + "@example.invalid"
        self.created_users.append(email)
        data = self.apply_data(
            action="user",
            first=True,
            data={
                "email": email,
                "full_name": "Primera cuenta ficticia",
                "password": "Fictional-only-" + uuid4().hex,
                "role": "admin",
                "brands": [],
            },
        )
        try:
            if saved:
                frappe.db.set_value("OMP Setup Progress", "Workspace", "state_json", "{}")
            for holder, values in roles.items():
                user = frappe.get_doc("User", holder)
                user.set(
                    "roles", [{"role": role} for role in values if role != "OMP Administrator"]
                )
                user.save()
                frappe.clear_cache(user=holder)
            frappe.db.commit()
            result = self.result("onboarding.apply", data, post=True)
            self.assertEqual(result["result"]["user"], email)
            self.assertEqual(self.result("onboarding.apply", data, post=True), result)
            frappe.db.rollback()
            frappe.db.set_value("User", email, "enabled", 0)
            frappe.db.commit()
            data["request_id"] = str(uuid4())
            data["data"]["email"] = "omp-unwanted-" + uuid4().hex[:8] + "@example.invalid"
            self.assertEqual(self.request("onboarding.apply", data, post=True).status_code, 409)
        finally:
            frappe.db.rollback()
            for holder, values in roles.items():
                user = frappe.get_doc("User", holder)
                user.set("roles", [{"role": role} for role in values])
                user.save()
                frappe.clear_cache(user=holder)
            if saved:
                frappe.db.set_value("OMP Setup Progress", "Workspace", "state_json", saved)
            elif frappe.db.exists("OMP Setup Progress", "Workspace"):
                frappe.delete_doc("OMP Setup Progress", "Workspace")
            frappe.db.commit()

    def test_08_finish_requires_current_receipts_and_recovery_records(self):
        # Synthetic service records exercise the gate; CI separately restores a real backup.
        root = Path(frappe.conf.get("omp_recovery_path") or "")
        self.assertEqual(
            root.name, "omp-setup-recovery", "A dedicated fixture recovery path is required"
        )
        root.mkdir(mode=0o700, exist_ok=True)
        files = [root / "latest-backup.json", root / "latest-restore.json"]
        self.assertFalse(
            any(path.exists() for path in files), "Never replace an existing service record"
        )
        current = self.result("onboarding.state", post=True)
        self.result(
            "onboarding.update",
            {"step": "preferences", "fingerprint": current["hashes"]["preferences"]},
            post=True,
        )
        for brand in current["brands"]:
            self.result(
                "onboarding.update",
                {"step": "receipt", "brand": brand["brand"], "fingerprint": brand["receipt_hash"]},
                post=True,
            )
        self.assertEqual(
            self.request(
                "onboarding.update", {"step": "recovery", "finish": True}, post=True
            ).status_code,
            409,
        )
        timestamp = datetime.now(UTC).isoformat()
        try:
            for path, value in zip(
                files,
                (
                    {"site": fixtures.OPTIONS.site, "status": "verified", "created_at": timestamp},
                    {
                        "source_site": fixtures.OPTIONS.site,
                        "status": "passed",
                        "checked_at": timestamp,
                    },
                ),
                strict=True,
            ):
                with path.open("x") as stream:
                    json.dump(value, stream)
                path.chmod(0o600)
            completed = self.result(
                "onboarding.update", {"step": "recovery", "finish": True}, post=True
            )
            self.assertTrue(all(completed["checks"].values()))
            self.assertTrue(completed["complete"])
            self.assertFalse(completed["active"])
            self.assertFalse(self.result("workspace.boot")["setup_active"])
        finally:
            for path in files:
                path.unlink(missing_ok=True)

    def test_09_cashier_cannot_access_setup_or_private_journals(self):
        frappe.db.rollback()
        user = frappe.get_doc("User", self.user)
        roles = [row.role for row in user.roles]
        try:
            user.set("roles", [{"role": "OMP Cashier"}, {"role": "Sales User"}])
            user.save()
            frappe.db.commit()
            frappe.clear_cache(user=self.user)
            for method, args in (
                ("state", {}),
                ("update", {"step": "account"}),
                ("apply", self.apply_data()),
                ("status", {"request_id": str(uuid4())}),
                ("abandon", {"request_id": str(uuid4())}),
            ):
                self.assertEqual(
                    self.request("onboarding." + method, args, post=True).status_code, 403
                )
            frappe.set_user(self.user)
            for doctype in ("OMP Setup Request", "OMP Setup Progress"):
                self.assertFalse(frappe.has_permission(doctype, "read"))
        finally:
            frappe.set_user("Administrator")
            user = frappe.get_doc("User", self.user)
            user.set("roles", [{"role": role} for role in roles])
            user.save()
            frappe.db.commit()
            frappe.clear_cache(user=self.user)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench", required=True, type=Path)
    parser.add_argument("--site", default="omp.localhost")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    fixtures.OPTIONS = parser.parse_args()
    fixtures.OPTIONS.bench = fixtures.OPTIONS.bench.expanduser().resolve()
    address = urlparse(fixtures.OPTIONS.base_url)
    if (
        address.scheme != "http"
        or address.hostname not in ("127.0.0.1", "localhost")
        or address.username
        or address.password
        or address.path
    ):
        parser.error("Se requiere una URL HTTP loopback sin ruta")
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.TestSuite(
            OnboardingHTTP(name)
            for name in sorted(n for n in OnboardingHTTP.__dict__ if n.startswith("test_"))
        )
    )
    sys.exit(not result.wasSuccessful())
