"""Full native backup/restore with fictional file and encrypted-secret probes."""

import argparse
import json
import os
import secrets
import signal
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import frappe
import requests

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--bench", type=Path, required=True)
parser.add_argument("--site", default="omp.localhost")
parser.add_argument("--db-admin-file", type=Path)
parser.add_argument("--wsl-root", action="store_true")
parser.add_argument("--systemd", action="store_true")
options = parser.parse_args()
bench = options.bench.expanduser().resolve()
root = bench.parent / "recovery"
root.mkdir(mode=0o700, exist_ok=True)
os.umask(0o077)
os.chdir(bench / "sites")
frappe.init(options.site, sites_path=str(bench / "sites"))
frappe.connect()
frappe.set_user("Administrator")
if not frappe.conf.get("allow_tests"):
    raise RuntimeError("Solo se permite en un sitio desechable.")
user = "omp-recovery-secret@example.invalid"
if not frappe.db.exists("User", user):
    frappe.get_doc(
        {
            "doctype": "User",
            "email": user,
            "first_name": "Recuperación ficticia",
            "enabled": 0,
            "send_welcome_email": 0,
        }
    ).insert()
doc = frappe.get_doc("User", user)
doc.api_key, doc.api_secret = secrets.token_hex(16), secrets.token_hex(24)
doc.save()
frappe.db.commit()
files = []
for folder in ("public/files", "private/files"):
    path = bench / "sites" / options.site / folder / ("omp-recovery-" + uuid4().hex + ".txt")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Contenido ficticio de recuperación.\n")
    path.chmod(0o600)
    files.append(path)
frappe.destroy()
command = [str(bench / "env/bin/python"), "-m", "open_multi_pos.operations", "--bench", str(bench)]


def execute(args, filename, *, privileged=False, expect=0):
    prefix = (
        ["/mnt/c/Windows/System32/wsl.exe", "-d", "Ubuntu", "-u", "root", "--"]
        if privileged
        else []
    )
    with (root / filename).open("w") as log:
        result = subprocess.run(
            prefix + command + args,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=240,
        )
    if result.returncode != expect:
        raise RuntimeError("Falló una etapa de recuperación; detalles solo en el log privado.")


server = None
try:
    execute(
        [
            "backup",
            "--site",
            options.site,
            "--root",
            str(root),
            *([] if options.systemd else ["--offline"]),
        ],
        "backup-drill.log",
    )
    bundle = root / json.loads((root / "latest-backup.json").read_text())["id"]
    execute(["verify", "--bundle", str(bundle)], "verify-drill.log")
    target = "omp-restore-" + uuid4().hex[:12] + ".localhost"
    restore_args = ["restore-drill", "--site", target, "--bundle", str(bundle)]
    if options.db_admin_file:
        restore_args += ["--db-admin-file", str(options.db_admin_file.resolve())]
    execute(restore_args, "restore-drill.log", privileged=options.wsl_root)
    # A second restore cannot overwrite the verified clone.
    execute(restore_args, "refused-overwrite.log", privileged=options.wsl_root, expect=1)
    with (root / "isolation-http.log").open("w") as log:
        server = subprocess.Popen(
            [
                str(bench / "env/bin/gunicorn"),
                "--chdir",
                "sites",
                "--bind",
                "127.0.0.1:8002",
                "frappe.app:application_with_statics()",
            ],
            cwd=bench,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
        response = None
        for _ in range(40):
            try:
                response = requests.get(
                    "http://127.0.0.1:8002/api/method/ping", headers={"Host": target}, timeout=2
                )
                break
            except requests.RequestException:
                time.sleep(0.25)
        if response is None or response.status_code != 503:
            raise AssertionError("La copia restaurada no está aislada del acceso HTTP.")
    result = json.loads((root / "latest-restore.json").read_text())
    if (
        result["status"] != "passed"
        or result["files"] < 2
        or any(result["reconciliation"].values())
    ):
        raise AssertionError("La copia restaurada no concilia.")
    print(
        json.dumps(
            {
                "restore": "passed",
                "tables": result["tables"],
                "file_probes": 2,
                "encrypted_secret": "preserved",
                "existing_site_overwrite": "refused",
                "http_isolation": 503,
            }
        )
    )
finally:
    if server:
        os.killpg(server.pid, signal.SIGTERM)
        server.wait(timeout=30)
    for path in files:
        path.unlink(missing_ok=True)
