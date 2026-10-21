import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from open_multi_pos.demo.server import make_server
from open_multi_pos.demo.store import DemoStore


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.server = make_server(DemoStore(Path(cls.tmp.name) / "http.sqlite3"), port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.tmp.cleanup()

    def request(self, path, data=None, headers=None):
        request = Request(self.base + path, data=data, headers=headers or {})
        try:
            with urlopen(request) as response:
                return response.status, response.read(), response.headers
        except HTTPError as exc:
            with exc:
                return exc.code, exc.read(), exc.headers

    def test_host_rebinding_rejected(self):
        status, _, _ = self.request("/api/context", headers={"Host": "attacker.example"})
        self.assertEqual(status, 403)

    def test_cross_brand_api_rejected(self):
        status, _, _ = self.request("/api/catalog?brand=tech", headers={"X-Demo-User": "cashier"})
        self.assertEqual(status, 403)

    def test_origin_and_token_required_for_mutation(self):
        status, _, _ = self.request("/api/checkout", b"{}", {"Content-Type": "application/json"})
        self.assertEqual(status, 403)
        token = json.loads(self.request("/api/context")[1])["token"]
        status, _, _ = self.request(
            "/api/checkout",
            b"{}",
            {
                "Content-Type": "application/json",
                "Origin": "https://attacker.example",
                "X-Demo-Token": token,
            },
        )
        self.assertEqual(status, 403)

    def test_sale_via_http_and_receipt(self):
        token = json.loads(self.request("/api/context")[1])["token"]
        data = {
            "brand": "tech",
            "terminal": str(uuid4()),
            "transaction_id": str(uuid4()),
            "items": [{"sku": "USB-01", "qty": 1}],
            "cash": "18000",
        }
        headers = {"Content-Type": "application/json", "Origin": self.base, "X-Demo-Token": token}
        status, body, _ = self.request("/api/checkout", json.dumps(data).encode(), headers)
        self.assertEqual(status, 200)
        sale_id = json.loads(body)["receipt"]["id"]
        status, html, response_headers = self.request(
            f"/api/receipt?id={sale_id}&profile=generic-80"
        )
        self.assertEqual(status, 200)
        self.assertIn(b"80mm", html)
        self.assertIn("script-src 'self'", response_headers["Content-Security-Policy"])
        self.assertNotIn("Access-Control-Allow-Origin", response_headers)

    def test_static_paths_do_not_expose_files(self):
        status, _, _ = self.request("/../../LICENSE")
        self.assertEqual(status, 404)

    def test_invalid_json_object_is_rejected(self):
        token = json.loads(self.request("/api/context")[1])["token"]
        headers = {"Content-Type": "application/json", "Origin": self.base, "X-Demo-Token": token}
        self.assertEqual(self.request("/api/checkout", b"[]", headers)[0], 400)
