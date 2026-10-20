import unittest

from open_multi_pos.fiscal import DisabledFiscalProvider
from open_multi_pos.hardware import BrowserPrinterAdapter, PrinterProfile, printer_profiles
from open_multi_pos.receipts import money, qr_data_url, render_compact_receipt, render_receipt
from open_multi_pos.validation import cents, safe_qr_url


class ReceiptTests(unittest.TestCase):
    def test_precise_money(self):
        self.assertEqual(cents("123.45"), 12345)
        self.assertEqual(cents("0.01"), 1)
        self.assertEqual(money(123456789), "$ 1.234.567,89")
        for value in (1.1, True, "NaN", "Infinity", "-1", "1e5", "1.001", "2,50"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                cents(value)

    def test_qr_rejects_scripts_credentials_control_characters(self):
        for url in (
            "javascript:alert(1)",
            "http://example.com",
            "https://a:b@example.com",
            "https://example.com\n",
            "https://example.com:99999",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                safe_qr_url(url)
        self.assertTrue(
            qr_data_url("https://example.com/demo").startswith("data:image/svg+xml;base64,")
        )

    def test_alternative_profiles_and_escaped_receipt(self):
        receipt = {
            "id": "DEMO-1",
            "brand": {
                "name": "<script>alert(1)</script>",
                "symbol": "A",
                "subtitle": "Demo",
                "warehouse": "A",
                "footer": '<img onerror="alert(1)">',
                "qr_url": "https://example.com/demo",
            },
            "created_at": "2026-10-18T17:00:00+00:00",
            "cashier": "Demo",
            "items": [{"name": "Vela & jabón", "qty": 1, "rate": 100, "amount": 100}],
            "payments": [],
            "total": 100,
            "change": 0,
        }
        for profile in printer_profiles().values():
            html = BrowserPrinterAdapter().preview(receipt, profile)
            self.assertIn(f"size: {profile.driver_page_mm}mm 150mm", html)
            self.assertIn(f"width:{profile.content_mm}mm", html)
            self.assertIn("SIN VALIDEZ FISCAL", html)
            self.assertNotIn("<script>", html)
            self.assertIn("&lt;script&gt;", html)
            self.assertIn("18/10/2026 12:00", html)
            self.assertFalse(profile.physically_verified)
            self.assertFalse(profile.native_qr)
        self.assertEqual(printer_profiles()["jaltech-jal58m"].cut, "manual")

    def test_invalid_profile_rejected(self):
        with self.assertRaises(ValueError):
            PrinterProfile("bad", "Bad", 57, 80, 384, 203)

    def test_native_snapshot_escapes_names_and_payment_labels(self):
        receipt = {
            "id": "NATIVE-<1>",
            "created_at": "2026-10-19T17:00:00+00:00",
            "brand": {
                "name": "<b>Marca</b>",
                "footer": "<script>alert(1)</script>",
                "qr_url": "https://example.com/native",
            },
            "items": [
                {"name": "<img onerror=alert(1)>", "qty": 1, "rate": 100000, "amount": 100000}
            ],
            "payments": [{"mode_of_payment": "<svg onload=alert(1)>", "amount": 119000}],
            "total": 119000,
            "taxes": 19000,
            "change": 0,
        }
        html = render_receipt(receipt, printer_profiles()["generic-58"], native=True)
        self.assertNotIn("<svg onload", html)
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;svg onload", html)
        self.assertIn("Impuestos: $ 190", html)
        self.assertIn("SIN VALIDEZ FISCAL", html)
        self.assertNotIn("DEMO ·", html)
        self.assertIn("/assets/open_multi_pos/receipt-print.js", html)

    def test_fiscal_is_disabled(self):
        result = DisabledFiscalProvider().status()
        self.assertFalse(result.issued)
        self.assertEqual(result.status, "not_configured")

    def test_compact_receipt_flags_escape_currency_and_negative_money(self):
        part = {
            "id": "FAKE-1",
            "created_at": "2026-10-20T05:30:00+00:00",
            "time_zone": "America/Bogota",
            "brand": {
                "name": "<Negocio>",
                "footer": "Gracias",
                "qr_url": "https://example.com/fake",
                "receipt_details": {
                    "phone": "000-000",
                    "address": "<img onerror=alert(1)>",
                    "receipt_show_phone": 0,
                    "receipt_show_address": 1,
                    "receipt_show_qr": 0,
                    "receipt_show_footer": 0,
                },
            },
            "items": [{"name": "<Producto>", "qty": 1, "rate": 100, "amount": 100}],
            "payments": [{"kind": "Cash", "amount": 100}],
            "taxes": 0,
            "total": 100,
        }
        group = {"id": "fake", "currency": "USD", "sales": [part, part], "total": 200, "change": 0}
        html = render_compact_receipt(group)
        self.assertNotIn("000-000", html)
        self.assertNotIn("<img onerror=alert(1)>", html)
        self.assertIn("&lt;img onerror=alert(1)&gt;", html)
        self.assertNotIn("<img src=", html)
        self.assertNotIn("Gracias", html)
        self.assertNotIn("Impuestos", html)
        self.assertEqual(html.count("Subtotal"), 2)
        self.assertIn("USD", html)
        self.assertIn("20/10/2026 00:30", html)
        self.assertIn("padding:.5mm 0 1mm", html)
        self.assertEqual(money(-101), "-$ 1,01")
