import unittest

from open_multi_pos.fiscal import DisabledFiscalProvider
from open_multi_pos.hardware import BrowserPrinterAdapter, PrinterProfile, printer_profiles
from open_multi_pos.receipts import money, qr_data_url
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
            self.assertIn(f"size: {profile.paper_mm}mm 150mm", html)
            self.assertIn(f"width:{profile.printable_mm}mm", html)
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

    def test_fiscal_is_disabled(self):
        result = DisabledFiscalProvider().status()
        self.assertFalse(result.issued)
        self.assertEqual(result.status, "not_configured")
