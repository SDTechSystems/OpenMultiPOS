"""Native warranty checks on a disposable site with fictional sales only."""

import argparse
import importlib.util
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import frappe
from frappe.utils import nowdate

spec = importlib.util.spec_from_file_location(
    "return_fixtures", Path(__file__).with_name("test-returns-http.py")
)
returns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(returns)
fixtures = returns.fixtures


class WarrantiesHTTP(returns.ReturnsHTTP):
    def prepared(self, brand=None):
        brand, _, invoice = self.sold(brand)
        info = self.result(
            "warranties.inspect", {"brand": brand["brand"], "invoice": invoice}, post=True
        )
        return {
            "brand": brand["brand"],
            "invoice": invoice,
            "row": info["items"][0]["row"],
            "date": nowdate(),
            "complaint": "Reclamación ficticia <sin HTML>",
            "request_id": str(uuid4()),
        }

    def create(self, data):
        return self.result("warranties.create", {"data": data}, post=True)

    def update(self, data, record, **changes):
        return {
            "brand": data["brand"],
            "claim": record["claim"],
            "modified": record["modified"],
            "status": "Work In Progress",
            "notes": "Revisión ficticia",
            **changes,
        }

    def test_01_native_claim_replay_and_no_stock_or_accounting(self):
        data = self.prepared()
        before = self.counts()
        result = self.create(data)
        replay = self.create(data)
        self.assertEqual(result["record"]["claim"], replay["record"]["claim"])
        self.assertEqual(result["record"]["complaint"], data["complaint"])
        self.assertEqual(self.counts(), before)
        doc = frappe.get_doc("Warranty Claim", result["record"]["claim"])
        self.assertEqual(doc.omp_sales_invoice, data["invoice"])
        self.assertEqual(doc.omp_invoice_item, data["row"])
        self.assertEqual(doc.status, "Open")
        self.assertFalse(doc.warranty_expiry_date)
        self.assertFalse(doc.warranty_amc_status)
        listed = self.result(
            "warranties.listing", {"brand": data["brand"], "claim": doc.name}, post=True
        )
        self.assertEqual(listed[0]["claim"], doc.name)
        self.assertEqual(
            self.result(
                "warranties.status",
                {"brand": data["brand"], "request_id": data["request_id"]},
                post=True,
            )["record"]["claim"],
            doc.name,
        )

    def test_02_payload_binding_and_business_isolation(self):
        data = self.prepared()
        record = self.create(data)["record"]
        self.assertEqual(
            self.request(
                "warranties.create", {"data": {**data, "complaint": "Otro motivo"}}, post=True
            ).status_code,
            409,
        )
        for brand in self.businesses[1:]:
            for method, args in (
                ("listing", {"claim": record["claim"]}),
                ("status", {"request_id": data["request_id"]}),
                ("inspect", {"invoice": data["invoice"]}),
            ):
                self.assertEqual(
                    self.request(
                        "warranties." + method, {"brand": brand["brand"], **args}, post=True
                    ).status_code,
                    403,
                )

    def test_03_abandonment_fences_late_create(self):
        data = self.prepared()
        args = {"brand": data["brand"], "request_id": data["request_id"]}
        self.assertEqual(self.result("warranties.status", args, post=True)["status"], "not_found")
        for _ in range(2):
            self.assertEqual(
                self.result("warranties.abandon", args, post=True)["status"], "abandoned"
            )
        self.assertEqual(
            self.request("warranties.create", {"data": data}, post=True).status_code, 409
        )
        self.assertEqual(self.result("warranties.status", args, post=True)["status"], "abandoned")
        completed = self.prepared()
        result = self.create(completed)
        self.assertEqual(
            self.result(
                "warranties.abandon",
                {"brand": completed["brand"], "request_id": completed["request_id"]},
                post=True,
            )["record"]["claim"],
            result["record"]["claim"],
        )

    def test_04_concurrent_create_and_abandon(self):
        data = self.prepared()
        frappe.db.rollback()
        before = frappe.db.count("Warranty Claim")
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(self.request, "warranties.create", {"data": data}, post=True),
                pool.submit(
                    self.request,
                    "warranties.abandon",
                    {"brand": data["brand"], "request_id": data["request_id"]},
                    post=True,
                ),
            ]
            codes = [f.result().status_code for f in futures]
        self.assertTrue(all(code in (200, 409) for code in codes), codes)
        state = self.result(
            "warranties.abandon",
            {"brand": data["brand"], "request_id": data["request_id"]},
            post=True,
        )
        frappe.db.rollback()
        self.assertEqual(
            frappe.db.count("Warranty Claim") - before, int(state["status"] == "completed")
        )
        if state["status"] == "completed":
            self.assertEqual(self.create(data)["record"]["claim"], state["record"]["claim"])
        else:
            self.assertEqual(
                self.request("warranties.create", {"data": data}, post=True).status_code, 409
            )

    def test_05_updates_detect_stale_edits_and_recover_response(self):
        data = self.prepared()
        record = self.create(data)["record"]
        before = self.counts()
        args = self.update(data, record)
        current = self.result("warranties.update", args, post=True)
        self.assertEqual(current["status"], "Work In Progress")
        self.assertEqual(
            self.result("warranties.update", args, post=True)["modified"], current["modified"]
        )
        self.assertEqual(
            self.request(
                "warranties.update", {**args, "notes": "Edición obsoleta"}, post=True
            ).status_code,
            409,
        )
        closed = self.result(
            "warranties.update", self.update(data, current, status="Closed"), post=True
        )
        self.assertTrue(closed["resolved_at"])
        reopened = self.result(
            "warranties.update", self.update(data, closed, status="Open"), post=True
        )
        self.assertFalse(reopened["resolved_at"])
        self.assertEqual(self.counts(), before)

    def test_06_invalid_inputs_never_create_a_claim(self):
        data = self.prepared()
        for field, value in (
            ("row", "missing-row"),
            ("date", "2999-01-01"),
            ("date", "bad"),
            ("date", 42),
            ("complaint", ""),
            ("complaint", "x" * 2001),
            ("request_id", "not-a-uuid"),
        ):
            with self.subTest(field=field, value=str(value)[:30]):
                self.assertEqual(
                    self.request(
                        "warranties.create", {"data": {**data, field: value}}, post=True
                    ).status_code,
                    417,
                )
        self.assertEqual(
            self.request(
                "warranties.create", {"data": {**data, "company": "forged"}}, post=True
            ).status_code,
            417,
        )

    def test_07_native_link_changes_and_deletion_are_blocked(self):
        data = self.prepared()
        record = self.create(data)["record"]
        headers = {"Host": fixtures.OPTIONS.site, "Authorization": self.authorization}
        endpoint = fixtures.OPTIONS.base_url + "/api/resource/Warranty%20Claim/" + record["claim"]
        changed = fixtures.requests.put(
            endpoint, headers=headers, json={"omp_invoice_item": "forged"}, timeout=40
        )
        self.assertEqual(changed.status_code, 403, changed.text[-1000:])
        deleted = fixtures.requests.delete(endpoint, headers=headers, timeout=40)
        self.assertEqual(deleted.status_code, 403, deleted.text[-1000:])
        self.assertEqual(self.create(data)["record"]["claim"], record["claim"])

    def test_08_cancelled_source_keeps_existing_history(self):
        data = self.prepared()
        record = self.create(data)["record"]
        frappe.db.rollback()
        frappe.get_doc("Sales Invoice", data["invoice"]).cancel()
        frappe.db.commit()
        self.assertEqual(self.create(data)["record"]["claim"], record["claim"])
        self.assertEqual(
            self.request(
                "warranties.create", {"data": {**data, "request_id": str(uuid4())}}, post=True
            ).status_code,
            409,
        )
        self.assertEqual(
            self.result("warranties.update", self.update(data, record), post=True)["status"],
            "Work In Progress",
        )

    def test_09_guest_cashier_and_revoked_business_are_denied(self):
        data = self.prepared()
        methods = [
            ("listing", {"brand": data["brand"]}),
            ("inspect", {"brand": data["brand"], "invoice": data["invoice"]}),
            ("status", {"brand": data["brand"], "request_id": data["request_id"]}),
            ("abandon", {"brand": data["brand"], "request_id": data["request_id"]}),
            ("create", {"data": data}),
        ]
        for method, args in methods:
            self.assertEqual(
                self.request("warranties." + method, args, post=True, guest=True).status_code, 403
            )
        frappe.db.rollback()
        user = frappe.get_doc("User", self.user)
        roles = [row.role for row in user.roles]
        user.set("roles", [{"role": "OMP Cashier"}, {"role": "Sales User"}])
        user.save()
        frappe.db.commit()
        try:
            for method, args in methods:
                self.assertEqual(
                    self.request("warranties." + method, args, post=True).status_code, 403
                )
        finally:
            frappe.db.rollback()
            user = frappe.get_doc("User", self.user)
            user.set("roles", [{"role": role} for role in roles])
            user.save()
            frappe.db.commit()
        frappe.db.set_value("OMP Business Brand", data["brand"], "enabled", 0)
        frappe.db.commit()
        try:
            self.assertEqual(
                self.request("warranties.create", {"data": data}, post=True).status_code, 403
            )
        finally:
            frappe.db.set_value("OMP Business Brand", data["brand"], "enabled", 1)
            frappe.db.commit()


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
            WarrantiesHTTP(name)
            for name in sorted(n for n in WarrantiesHTTP.__dict__ if n.startswith("test_"))
        )
    )
    sys.exit(not result.wasSuccessful())
