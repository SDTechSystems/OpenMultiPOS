"""Restart recovery with real sessions and durable operations. Disposable site only."""

import argparse
import importlib.util
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from uuid import uuid4

import frappe
import requests
from frappe.sessions import delete_session
from frappe.utils.password import update_password

spec = importlib.util.spec_from_file_location(
    "workspace_fixtures", Path(__file__).with_name("test-workspace-http.py")
)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


class Runtime:
    def __init__(self, bench, systemd):
        self.bench, self.systemd, self.processes = bench, systemd, []
        self.log = tempfile.TemporaryFile()

    def start(self):
        if self.systemd:
            subprocess.run(
                ["systemctl", "--user", "restart", "openmultipos-web", "openmultipos-worker"],
                check=True,
            )
        else:
            for command in (
                [
                    str(self.bench / "env/bin/gunicorn"),
                    "--chdir",
                    "sites",
                    "--bind",
                    "127.0.0.1:8001",
                    "--workers",
                    "2",
                    "--threads",
                    "2",
                    "frappe.app:application_with_statics()",
                ],
                [
                    str(self.bench / "env/bin/python"),
                    "-m",
                    "frappe.utils.bench_helper",
                    "frappe",
                    "worker",
                    "--queue",
                    "short,default,long",
                    "--quiet",
                ],
            ):
                self.processes.append(
                    subprocess.Popen(
                        command,
                        cwd=self.bench,
                        stdin=subprocess.DEVNULL,
                        stdout=self.log,
                        stderr=self.log,
                        start_new_session=True,
                    )
                )
        for _ in range(90):
            try:
                if (
                    requests.get(
                        OPTIONS.base_url + "/api/method/ping",
                        headers={"Host": OPTIONS.site},
                        timeout=2,
                    ).status_code
                    == 200
                ):
                    return
            except requests.RequestException:
                pass
            time.sleep(0.5)
        raise RuntimeError("El servicio no se recuperó.")

    def stop(self):
        if self.systemd:
            subprocess.run(
                ["systemctl", "--user", "stop", "openmultipos-web", "openmultipos-worker"],
                check=True,
            )
        else:
            for process in self.processes:
                os.killpg(process.pid, signal.SIGTERM)
            for process in self.processes:
                process.wait(timeout=40)
            self.processes.clear()

    def restart(self):
        self.stop()
        if OPTIONS.restart_databases:
            frappe.db.close()
            subprocess.run(
                [
                    "/mnt/c/Windows/System32/wsl.exe",
                    "-d",
                    "Ubuntu",
                    "-u",
                    "root",
                    "--",
                    "systemctl",
                    "restart",
                    "mariadb",
                    "redis-server",
                ],
                check=True,
            )
            frappe.connect()
        self.start()


class RecoveryHTTP(fixtures.WorkspaceHTTP):
    def test_committed_and_uncommitted_operations_survive_restart(self):
        password = secrets.token_urlsafe(32)
        old = frappe.db.sql(
            "SELECT password,encrypted FROM __Auth WHERE doctype='User' AND name=%s AND fieldname='password'",
            self.user,
            as_dict=True,
        )
        sessions = set(frappe.db.sql("SELECT sid FROM tabSessions", pluck=True))
        update_password(self.user, password)
        frappe.db.commit()
        cookie = requests.Session()
        cookie.headers["Host"] = OPTIONS.site
        try:
            login = cookie.post(
                OPTIONS.base_url + "/api/method/login",
                json={"usr": self.user, "pwd": password},
                timeout=30,
            )
            self.assertEqual(login.status_code, 200)
            page = cookie.get(OPTIONS.base_url + "/omp", timeout=30)
            csrf = re.search(r'name="csrf-token" content="([^"]+)"', page.text)[1]
            cookie.headers["X-Frappe-CSRF-Token"] = csrf
            sid = cookie.cookies.get("sid")

            def call(method, data, post=True):
                response = cookie.request(
                    "POST" if post else "GET",
                    OPTIONS.base_url + "/api/method/open_multi_pos." + method,
                    **({"json": data} if post else {"params": data}),
                    timeout=40,
                )
                self.assertEqual(response.status_code, 200, response.text[-500:])
                return response.json()["message"]

            brand = self.businesses[0]
            product = {
                "brand": brand["brand"],
                "name": "Producto ficticio recuperación",
                "code": "",
                "barcode": "",
                "price": "2500",
                "item_group": "Products",
                "request_id": str(uuid4()),
            }
            committed = call("workspace.create_product", {"data": product})
            code = committed["item_code"]
            stock = self.stock_payload(brand, code)
            stock_result = call("workspace.receive_stock", {"data": stock})
            sale = {"request_id": str(uuid4()), "sales": [self.sale(brand, code)]}
            sale_result = call("batch.checkout", {"data": sale})
            # The client retains the requests as if each committed response was lost.
            unsent = {**product, "request_id": str(uuid4())}
            with tempfile.TemporaryDirectory() as directory:
                journal = Path(directory) / "pending.json"
                journal.write_text(
                    json.dumps({"product": product, "stock": stock, "sale": sale, "unsent": unsent})
                )
                before = self.counts()
                RUNTIME.restart()
                pending = json.loads(journal.read_text())
            self.assertEqual(cookie.cookies.get("sid"), sid)
            self.assertEqual(call("workspace.boot", {}, post=False)["user"], self.user)
            self.assertEqual(
                call("workspace.create_product", {"data": pending["product"]}),
                {**committed, "duplicate": True},
            )
            self.assertEqual(
                call("workspace.receive_stock", {"data": pending["stock"]}),
                {**stock_result, "duplicate": True},
            )
            self.assertEqual(
                call("batch.get_status", {"request_id": sale["request_id"]}, post=False)["status"],
                "completed",
            )
            self.assertEqual(
                call("batch.checkout", {"data": pending["sale"]}),
                {**sale_result, "duplicate": True},
            )
            self.assertEqual(
                before, self.counts(), "Recuperar no debe duplicar factura, stock ni GL"
            )
            first = call("workspace.create_product", {"data": pending["unsent"]})
            self.assertEqual(
                call("workspace.create_product", {"data": pending["unsent"]}),
                {**first, "duplicate": True},
            )
            self.assertNotEqual(first["item_code"], code)
            self.assertTrue(call("batch.receipt", {"request_id": sale["request_id"]}))
        finally:
            frappe.set_user("Administrator")
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
                delete_session(sid, reason="Fin del ensayo ficticio de recuperación")
            frappe.db.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench", required=True, type=Path)
    parser.add_argument("--site", default="omp.localhost")
    parser.add_argument("--systemd", action="store_true")
    parser.add_argument("--restart-databases", action="store_true")
    OPTIONS = parser.parse_args()
    OPTIONS.bench = OPTIONS.bench.expanduser().resolve()
    if OPTIONS.restart_databases and not OPTIONS.systemd:
        parser.error("El reinicio MariaDB/Redis requiere --systemd en WSL.")
    OPTIONS.base_url = "http://127.0.0.1:" + ("8000" if OPTIONS.systemd else "8001")
    fixtures.OPTIONS = OPTIONS
    RUNTIME = Runtime(OPTIONS.bench, OPTIONS.systemd)
    try:
        RUNTIME.start()
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.TestSuite(
                [RecoveryHTTP("test_committed_and_uncommitted_operations_survive_restart")]
            )
        )
        sys.exit(not result.wasSuccessful())
    finally:
        if not OPTIONS.systemd:
            RUNTIME.stop()
