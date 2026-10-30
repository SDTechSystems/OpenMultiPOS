"""Native warranty claims over HTTP. Fictional disposable fixtures only."""

import argparse
import importlib.util
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import frappe
from frappe.utils import add_days, nowdate

spec = importlib.util.spec_from_file_location(
    "workspace_fixtures", Path(__file__).with_name("test-workspace-http.py")
)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


class WarrantyHTTP(fixtures.WorkspaceHTTP):
    def sold(self, brand=None):
        brand = brand or self.businesses[0]
        code = self.product(brand)
        sale = self.result("checkout.checkout", {"data": self.sale(brand, code)}, post=True)
        return brand, code, sale["invoice"]

    def payload(self, brand, invoice, **changes):
        info = self.result(
            "warranty.inspect", {"brand": brand["brand"], "invoice": invoice}, post=True
        )
        return {
            "brand": brand["brand"],
            "invoice": invoice,
            "row": info["items"][0]["row"],
            "request_id": str(uuid4()),
            "complaint": "Falla ficticia <b>sin</b> marcado\nSegunda línea",
            "complaint_date": nowdate(),
            **changes,
        }

    def counts(self):
        frappe.db.rollback()
        return {
            dt: frappe.db.count(dt)
            for dt in (
                "Warranty Claim",
                "Sales Invoice",
                "Stock Ledger Entry",
                "GL Entry",
                "Stock Entry",
                "Payment Entry",
            )
        }

    def change(self, brand, claim, **changes):
        return {
            "brand": brand["brand"],
            "claim": claim["claim"],
            "modified": claim["modified"],
            "status": claim["claim_status"],
            "resolution_details": claim["resolution_details"],
            "note": "",
            **changes,
        }

    def test_01_create_links_sale_and_item_without_ledger_effects(self):
        brand, code, invoice = self.sold()
        data = self.payload(brand, invoice)
        before = self.counts()
        result = self.result("warranty.create", {"data": data}, post=True)
        self.assertFalse(result["duplicate"])
        self.assertEqual(result["claim_status"], "Open")
        self.assertEqual(result["complaint"], data["complaint"])
        after = self.counts()
        self.assertEqual(after["Warranty Claim"], before["Warranty Claim"] + 1)
        self.assertEqual(
            {k: v for k, v in after.items() if k != "Warranty Claim"},
            {k: v for k, v in before.items() if k != "Warranty Claim"},
        )
        doc = frappe.get_doc("Warranty Claim", result["claim"])
        self.assertEqual(doc.item_code, code)
        self.assertEqual(doc.company, brand["company"])
        self.assertEqual(doc.omp_business_brand, brand["brand"])
        self.assertEqual(doc.omp_sales_invoice, invoice)
        self.assertEqual(doc.customer, frappe.db.get_value("Sales Invoice", invoice, "customer"))
        self.assertNotIn("<b>", doc.complaint)
        self.assertFalse(doc.warranty_expiry_date)
        self.assertFalse(doc.warranty_amc_status)
        listed = self.result("warranty.claims", {"brand": brand["brand"]})
        self.assertIn(result["claim"], [r["name"] for r in listed])
        info = self.result(
            "warranty.inspect", {"brand": brand["brand"], "invoice": invoice}, post=True
        )
        self.assertEqual([c["name"] for c in info["claims"]], [result["claim"]])

    def test_02_replay_recovers_and_changed_payload_conflicts(self):
        brand, _, invoice = self.sold()
        data = self.payload(brand, invoice)
        first = self.result("warranty.create", {"data": data}, post=True)
        before = self.counts()
        replay = self.result("warranty.create", {"data": data}, post=True)
        self.assertTrue(replay["duplicate"])
        self.assertEqual(replay["claim"], first["claim"])
        status = self.result(
            "warranty.status",
            {"brand": brand["brand"], "request_id": data["request_id"]},
            post=True,
        )
        self.assertEqual(status["claim"], first["claim"])
        self.assertEqual(
            self.request(
                "warranty.create", {"data": {**data, "complaint": "Otra falla"}}, post=True
            ).status_code,
            409,
        )
        self.assertEqual(self.counts(), before)

    def test_03_concurrent_create_registers_once(self):
        brand, _, invoice = self.sold()
        data = self.payload(brand, invoice)
        before = self.counts()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda _: self.request("warranty.create", {"data": data}, post=True), range(2)
                )
            )
        self.assertTrue(all(r.status_code in (200, 409) for r in responses))
        result = self.result("warranty.create", {"data": data}, post=True)
        self.assertEqual(self.counts()["Warranty Claim"], before["Warranty Claim"] + 1)
        self.assertEqual(
            frappe.db.count("Warranty Claim", {"omp_sales_invoice": invoice}), 1, result
        )

    def test_04_abandon_blocks_late_create_and_recovers_saved(self):
        brand, _, invoice = self.sold()
        data = self.payload(brand, invoice)
        ref = {"brand": brand["brand"], "request_id": data["request_id"]}
        self.assertEqual(self.result("warranty.status", ref, post=True)["status"], "not_found")
        self.assertEqual(self.result("warranty.abandon", ref, post=True)["status"], "abandoned")
        before = self.counts()
        self.assertEqual(
            self.request("warranty.create", {"data": data}, post=True).status_code, 409
        )
        self.assertEqual(self.result("warranty.status", ref, post=True)["status"], "abandoned")
        self.assertEqual(self.counts(), before)
        saved = self.payload(brand, invoice)
        created = self.result("warranty.create", {"data": saved}, post=True)
        recovered = self.result(
            "warranty.abandon",
            {"brand": brand["brand"], "request_id": saved["request_id"]},
            post=True,
        )
        self.assertEqual(recovered["claim"], created["claim"])

    def test_05_follow_up_close_and_concurrent_edit(self):
        brand, _, invoice = self.sold()
        claim = self.result("warranty.create", {"data": self.payload(brand, invoice)}, post=True)
        before = self.counts()
        progress = self.result(
            "warranty.update",
            {
                "data": self.change(
                    brand, claim, status="Work In Progress", note="Revisión <i>ficticia</i>"
                )
            },
            post=True,
        )
        self.assertEqual(progress["claim_status"], "Work In Progress")
        self.assertEqual(progress["notes"][-1]["text"], "Revisión <i>ficticia</i>")
        stale = self.change(brand, claim, status="Cancelled")
        self.assertEqual(
            self.request("warranty.update", {"data": stale}, post=True).status_code, 409
        )
        self.assertEqual(
            self.request(
                "warranty.update",
                {"data": self.change(brand, progress, status="Closed")},
                post=True,
            ).status_code,
            417,
        )
        closed = self.result(
            "warranty.update",
            {
                "data": self.change(
                    brand, progress, status="Closed", resolution_details="Cambio ficticio"
                )
            },
            post=True,
        )
        self.assertEqual(closed["claim_status"], "Closed")
        self.assertTrue(closed["resolution_date"])
        self.assertEqual(closed["resolved_by"], self.user)
        after = self.counts()
        self.assertEqual(after, before)
        self.assertEqual(
            [
                r["name"]
                for r in self.result(
                    "warranty.claims", {"brand": brand["brand"], "status": "Closed"}
                )
            ].count(claim["claim"]),
            1,
        )

    def test_06_dates_rows_and_foreign_sales_are_rejected(self):
        brand, _, invoice = self.sold()
        before = self.counts()
        for changes in (
            {"complaint_date": add_days(nowdate(), 1)},
            {"complaint_date": "2000-01-01"},
            {"row": "fila-inexistente"},
        ):
            with self.subTest(changes=changes):
                response = self.request(
                    "warranty.create", {"data": self.payload(brand, invoice, **changes)}, post=True
                )
                self.assertIn(response.status_code, (409, 417))
        shared = self.businesses[2]
        self.assertEqual(shared["company"], brand["company"])
        foreign = self.payload(brand, invoice, brand=shared["brand"])
        self.assertEqual(
            self.request("warranty.create", {"data": foreign}, post=True).status_code, 403
        )
        self.assertEqual(
            self.request(
                "warranty.inspect", {"brand": shared["brand"], "invoice": invoice}, post=True
            ).status_code,
            403,
        )
        self.assertEqual(self.counts(), before)

    def test_07_other_business_claims_are_isolated(self):
        brand, _, invoice = self.sold()
        claim = self.result("warranty.create", {"data": self.payload(brand, invoice)}, post=True)
        shared = self.businesses[2]
        self.assertNotIn(
            claim["claim"],
            [r["name"] for r in self.result("warranty.claims", {"brand": shared["brand"]})],
        )
        self.assertEqual(
            self.request(
                "warranty.detail",
                {"brand": shared["brand"], "claim_name": claim["claim"]},
                post=True,
            ).status_code,
            403,
        )
        self.assertEqual(
            self.request(
                "warranty.update",
                {"data": self.change(shared, claim, note="Intento ajeno")},
                post=True,
            ).status_code,
            403,
        )

    def test_08_guest_cashier_and_revoked_business_are_denied(self):
        brand, _, invoice = self.sold()
        data = self.payload(brand, invoice)
        claim = self.result("warranty.create", {"data": data}, post=True)
        ref = {"brand": brand["brand"], "request_id": data["request_id"]}
        calls = (
            ("warranty.create", {"data": {**data, "request_id": str(uuid4())}}),
            ("warranty.update", {"data": self.change(brand, claim, note="x")}),
            ("warranty.status", ref),
            ("warranty.abandon", ref),
            ("warranty.inspect", {"brand": brand["brand"], "invoice": invoice}),
            ("warranty.detail", {"brand": brand["brand"], "claim_name": claim["claim"]}),
        )
        before = self.counts()
        for method, args in calls:
            self.assertIn(self.request(method, args, post=True, guest=True).status_code, (401, 403))
        self.assertIn(
            self.request("warranty.claims", {"brand": brand["brand"]}, guest=True).status_code,
            (401, 403),
        )
        frappe.db.set_value("OMP Business Brand", brand["brand"], "enabled", 0)
        frappe.db.commit()
        try:
            for method, args in calls:
                self.assertEqual(self.request(method, args, post=True).status_code, 403, method)
        finally:
            frappe.db.set_value("OMP Business Brand", brand["brand"], "enabled", 1)
            frappe.db.commit()
        user = frappe.get_doc("User", self.user)
        roles = [r.role for r in user.roles]
        user.set("roles", [{"role": "OMP Cashier"}, {"role": "Sales User"}])
        user.save()
        frappe.db.commit()
        frappe.clear_cache(user=self.user)
        try:
            for method, args in calls:
                self.assertEqual(self.request(method, args, post=True).status_code, 403, method)
            self.assertEqual(
                self.request("warranty.claims", {"brand": brand["brand"]}).status_code, 403
            )
        finally:
            user = frappe.get_doc("User", self.user)
            user.set("roles", [{"role": r} for r in roles])
            user.save()
            frappe.db.commit()
            frappe.clear_cache(user=self.user)
        self.assertEqual(self.counts(), before)

    def test_09_cancelled_sale_cannot_receive_new_claims(self):
        brand, _, invoice = self.sold()
        data = self.payload(brand, invoice)
        frappe.db.rollback()
        frappe.get_doc("Sales Invoice", invoice).cancel()
        frappe.db.commit()
        before = self.counts()
        self.assertIn(
            self.request("warranty.create", {"data": data}, post=True).status_code, (403, 409)
        )
        self.assertEqual(self.counts(), before)


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
            WarrantyHTTP(name)
            for name in sorted(n for n in WarrantyHTTP.__dict__ if n.startswith("test_"))
        )
    )
    sys.exit(not result.wasSuccessful())
