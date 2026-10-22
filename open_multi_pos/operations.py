"""Private, local operations CLI. No whitelisted methods and no public backups."""

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

TABLES = (
    "Sales Invoice",
    "Sales Invoice Item",
    "Sales Invoice Payment",
    "Sales Taxes and Charges",
    "Stock Entry",
    "Stock Entry Detail",
    "Stock Ledger Entry",
    "GL Entry",
    "Bin",
    "Item",
    "Item Price",
    "Item Barcode",
    "OMP Business Brand",
    "OMP POS Terminal",
    "OMP Checkout Request",
    "OMP Sale Batch",
    "OMP Return Request",
    "OMP Import Request",
    "OMP Inventory Tombstone",
    "OMP Landed Cost Tombstone",
    "Landed Cost Voucher",
    "Landed Cost Item",
    "Landed Cost Taxes and Charges",
    "Landed Cost Purchase Receipt",
    "Landed Cost Vendor Invoice",
    "POS Opening Entry",
    "POS Closing Entry",
)
SERVICES = ("openmultipos-web", "openmultipos-worker", "openmultipos-scheduler")


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".new-" + uuid4().hex)
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, default=str)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o600)
    temporary.replace(path)


def private_root(path):
    path = Path(path).expanduser().absolute()
    # Native backup utilities interpolate paths into their shell commands.
    if not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(path)) or path.resolve() != path:
        raise ValueError("El destino debe ser una ruta Linux sin enlaces ni espacios.")
    if str(path).startswith(("/mnt/", "/tmp/")):
        raise ValueError("Usa almacenamiento privado persistente de Linux.")
    if any((parent / ".git").exists() for parent in (path, *path.parents)):
        raise ValueError("Los respaldos no pueden estar dentro de un repositorio.")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.stat().st_mode & 0o077:
        raise ValueError("El directorio de respaldo debe tener permisos 700.")
    return path


def file_snapshot(site_path):
    result = {}
    for folder in ("public/files", "private/files"):
        base = site_path / folder
        if base.is_symlink():
            raise ValueError("No se permiten directorios de archivos enlazados.")
        for path in sorted(base.rglob("*")):
            if path.is_symlink():
                raise ValueError("No se permiten enlaces en los archivos de la copia.")
            if path.is_file():
                result[str(path.relative_to(site_path))] = digest(path)
    return result


def reconciliation():
    import frappe

    # Decimal aggregation stays in MariaDB; no floating-point money arithmetic.
    gl = frappe.db.sql("""
        SELECT count(*) FROM (
          SELECT company, voucher_type, voucher_no
          FROM `tabGL Entry` GROUP BY company, voucher_type, voucher_no
          HAVING abs(sum(debit) - sum(credit)) > 0.005
        ) unmatched
    """)[0][0]
    stock = frappe.db.sql("""
        SELECT count(*) FROM (
          SELECT b.item_code, b.warehouse FROM tabBin b
          LEFT JOIN (
            SELECT item_code, warehouse, sum(actual_qty) qty
            FROM `tabStock Ledger Entry` WHERE is_cancelled=0
            GROUP BY item_code, warehouse
          ) s ON s.item_code=b.item_code AND s.warehouse=b.warehouse
          WHERE abs(b.actual_qty - coalesce(s.qty, 0)) > 0.000001
          UNION
          SELECT s.item_code, s.warehouse FROM `tabStock Ledger Entry` s
          LEFT JOIN tabBin b ON b.item_code=s.item_code AND b.warehouse=s.warehouse
          WHERE s.is_cancelled=0 AND b.name IS NULL
          GROUP BY s.item_code, s.warehouse HAVING abs(sum(s.actual_qty)) > 0.000001
        ) unmatched
    """)[0][0]
    missing = frappe.db.sql("""
        SELECT count(*) FROM `tabSales Invoice` i
        WHERE i.docstatus=1 AND i.is_opening != 'Yes' AND i.base_grand_total != 0
          AND NOT EXISTS (SELECT 1 FROM `tabGL Entry` g
            WHERE g.voucher_type='Sales Invoice' AND g.voucher_no=i.name AND g.is_cancelled=0)
    """)[0][0]
    return {
        "unbalanced_gl_vouchers": gl,
        "stock_bin_mismatches": stock,
        "submitted_invoices_without_gl": missing,
    }


def snapshot():
    import frappe
    from frappe.utils.password import get_decrypted_password

    result = {"tables": {}, "reconciliation": reconciliation()}
    for doctype in TABLES:
        checksum, count = hashlib.sha256(), 0
        # Fixed, internal table names only. Stream to avoid loading the ledger.
        with frappe.db.unbuffered_cursor():
            for row in frappe.db.sql(
                f"SELECT * FROM `tab{doctype}` ORDER BY name", as_dict=True, as_iterator=True
            ):
                checksum.update(json.dumps(dict(row), sort_keys=True, default=str).encode())
                checksum.update(b"\n")
                count += 1
        result["tables"][doctype] = {"count": count, "sha256": checksum.hexdigest()}
    probe = frappe.db.sql(
        "SELECT doctype, name, fieldname FROM __Auth WHERE encrypted=1 ORDER BY doctype,name,fieldname LIMIT 1",
        as_dict=True,
    )
    if probe:
        row = probe[0]
        value = get_decrypted_password(row.doctype, row.name, row.fieldname)
        result["encrypted_secret_probe"] = {
            **row,
            "sha256": hashlib.sha256(value.encode()).hexdigest(),
        }
    result["files"] = file_snapshot(Path(frappe.get_site_path()).resolve())
    return result


def verify_bundle(bundle):
    bundle = Path(bundle).absolute()
    if bundle.resolve() != bundle or not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(bundle)):
        raise ValueError("La copia no puede usar enlaces.")
    if bundle.is_symlink() or bundle.stat().st_mode & 0o077:
        raise ValueError("La copia debe ser privada.")
    manifest = json.loads((bundle / "manifest.json").read_text())
    if manifest.get("format") != 1 or set(manifest.get("artifacts", {})) != {
        "database",
        "public",
        "private",
        "config",
        "snapshot",
    }:
        raise ValueError("Manifest de respaldo incompleto.")
    for record in manifest["artifacts"].values():
        name = record["name"]
        if Path(name).name != name or not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise ValueError("Ruta inválida en manifest.")
        path = bundle / name
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
            raise ValueError("Archivo de respaldo no seguro.")
        if path.stat().st_size != record["bytes"] or digest(path) != record["sha256"]:
            raise ValueError("La copia está incompleta o fue modificada.")
    return manifest


@contextlib.contextmanager
def backup_lock(root):
    descriptor = os.open(root / ".backup.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(descriptor)


@contextlib.contextmanager
def quiesce(enabled):
    active = []
    try:
        if enabled:
            for unit in SERVICES:
                if (
                    subprocess.run(
                        ["systemctl", "--user", "is-active", "--quiet", unit], check=False
                    ).returncode
                    == 0
                ):
                    active.append(unit)
            if not active:
                raise RuntimeError(
                    "No se encontraron servicios activos; usa --offline solo con procesos detenidos."
                )
            subprocess.run(["systemctl", "--user", "stop", *active], check=True)
        yield
    finally:
        if active:
            subprocess.run(["systemctl", "--user", "start", *active], check=True)


def backup(site, root, *, systemd=True):
    import frappe
    from frappe.utils.backups import BackupGenerator

    root = private_root(root)
    site_path = Path(frappe.get_site_path()).resolve()
    if root.is_relative_to(site_path) or site_path.is_relative_to(root):
        raise ValueError("El respaldo debe estar separado del sitio.")
    bundle = root / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid4().hex[:8])
    bundle.mkdir(mode=0o700)
    with backup_lock(root), quiesce(systemd):
        frappe.db.rollback()
        # Stopped web/worker/scheduler processes make DB + files consistent.
        before = snapshot()
        if any(before["reconciliation"].values()):
            raise RuntimeError(
                "La conciliación detectó diferencias. Conserva el sitio y revisa antes de respaldar."
            )
        write_json(bundle / "snapshot.json", before)
        # Use the native generator without new_backup's cleanup of unrelated
        # legacy backups in the source site's private/backups directory.
        odb = BackupGenerator(
            frappe.conf.db_name,
            frappe.conf.db_user,
            frappe.conf.db_password,
            backup_path=str(bundle),
            ignore_conf=True,
            db_type=frappe.conf.db_type,
            db_host=frappe.conf.db_host,
            db_port=frappe.conf.db_port,
            db_socket=frappe.conf.db_socket,
        )
        odb.get_backup(ignore_files=False, force=True)
        # Native encryption creates its key while backing up; capture config afterwards.
        shutil.copyfile(site_path / "site_config.json", bundle / "site-config.json")
        artifacts = {
            "database": odb.backup_path_db,
            "public": odb.backup_path_files,
            "private": odb.backup_path_private_files,
            "config": str(bundle / "site-config.json"),
            "snapshot": str(bundle / "snapshot.json"),
        }
        if frappe.get_system_settings("encrypt_backup"):
            # Upstream can report encryption failure without raising. Verify
            # decryption before accepting an encrypted backup as successful.
            conf = json.loads((bundle / "site-config.json").read_text())
            for kind in ("database", "public", "private"):
                subprocess.run(
                    [
                        "gpg",
                        "--batch",
                        "--pinentry-mode",
                        "loopback",
                        "--passphrase-fd",
                        "0",
                        "--decrypt",
                        artifacts[kind],
                    ],
                    input=conf["backup_encryption_key"].encode(),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    check=True,
                    timeout=240,
                )
        # Start a fresh read view: the comparison must not reuse MariaDB's
        # earlier repeatable-read snapshot when detecting concurrent writes.
        frappe.db.rollback()
        after = snapshot()
        if before != after:
            raise RuntimeError("El sitio cambió durante la copia; la copia no se acepta.")
        manifest = {
            "format": 1,
            "id": bundle.name,
            "site": site,
            "created_at": datetime.now(UTC).isoformat(),
            "encrypted": bool(frappe.get_system_settings("encrypt_backup")),
            "artifacts": {},
        }
        for kind, value in artifacts.items():
            path = Path(value)
            path.chmod(0o600)
            manifest["artifacts"][kind] = {
                "name": path.name,
                "bytes": path.stat().st_size,
                "sha256": digest(path),
            }
        for path in bundle.iterdir():
            if path.is_file():
                path.chmod(0o600)
        write_json(bundle / "manifest.json", manifest)
        verify_bundle(bundle)
        write_json(
            root / "latest-backup.json",
            {
                "id": bundle.name,
                "site": site,
                "created_at": manifest["created_at"],
                "status": "verified",
            },
        )
    return {"backup": bundle.name, "status": "verified"}


def safe_extract(archive, target, folder, source_site):
    """Native archives include <site>/<public|private>/files; reject links/devices."""
    with tarfile.open(archive) as tar:
        for member in tar:
            parts = Path(member.name).parts
            if any(part == ".." for part in parts) or member.name.startswith("/"):
                raise ValueError("Ruta insegura en archivo de respaldo.")
            # Frappe may save either relative paths or absolute paths with
            # tar's leading slash removed. Preserve only the site-relative tail.
            start = next(
                (
                    i
                    for i in range(len(parts) - 2)
                    if parts[i : i + 3] == (source_site, folder, "files")
                ),
                None,
            )
            if start is None or not (member.isdir() or member.isfile()):
                raise ValueError("Entrada inesperada en archivo de respaldo.")
            destination = target.joinpath(*parts[start + 1 :])
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if member.isdir():
                destination.mkdir(exist_ok=True, mode=0o700)
            else:
                with tar.extractfile(member) as source, destination.open("xb") as output:
                    shutil.copyfileobj(source, output)
                destination.chmod(0o600)


def restore_drill(bench, site, bundle, db_admin_file=None):
    import frappe
    from frappe.installer import _new_site, update_site_config

    bundle = Path(bundle).absolute()
    manifest = verify_bundle(bundle)
    if not re.fullmatch(r"omp-restore-[a-f0-9]{8,32}\.localhost", site):
        raise ValueError("Usa un sitio nuevo omp-restore-<8 a 32 hex>.localhost.")
    target = bench / "sites" / site
    if target.exists() or target.is_symlink() or site == manifest["site"]:
        raise ValueError("Nunca se restaura sobre un sitio existente.")
    records = manifest["artifacts"]
    conf = json.loads((bundle / records["config"]["name"]).read_text())
    admin = {"username": "root", "password": None}
    if db_admin_file:
        credentials = Path(db_admin_file)
        if credentials.stat().st_mode & 0o077:
            raise ValueError("El archivo de credenciales debe tener permisos 600.")
        admin.update(json.loads(credentials.read_text()))
    # Random DB name, unrelated to the source. Verify absence before native setup
    # (whose internal force flag is required by Frappe's restore implementation).
    db_name = "omp_restore_" + uuid4().hex[:16]
    import pymysql

    socket = None if admin.get("host") else admin.get("socket", "/run/mysqld/mysqld.sock")
    connection = pymysql.connect(
        user=admin["username"],
        password=admin["password"] or "",
        unix_socket=socket,
        host=admin.get("host", "localhost"),
        port=admin.get("port", 3306),
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s",
                (db_name,),
            )
            if cursor.fetchone():
                raise ValueError("La base de restauración ya existe.")
    finally:
        connection.close()
    target.mkdir(mode=0o700)
    isolated = {
        "db_name": db_name,
        "db_type": "mariadb",
        "db_socket": socket,
        "db_host": admin.get("host"),
        "db_port": admin.get("port", 3306),
        "db_password": uuid4().hex,
        "maintenance_mode": 1,
        "pause_scheduler": 1,
        "disable_scheduler": 1,
        "mute_emails": 1,
        "allow_tests": False,
        **{key: conf[key] for key in ("encryption_key", "backup_encryption_key") if key in conf},
    }
    write_json(target / "site_config.json", isolated)
    frappe.init(site, sites_path=str(bench / "sites"))
    # Stage only the verified native artifacts. Native encrypted backups are
    # decrypted with stdin, never with a passphrase in process arguments.
    stage = target / "private" / "restore-staging"
    stage.mkdir(parents=True, mode=0o700)
    for kind in ("database", "public", "private"):
        source = bundle / records[kind]["name"]
        destination = stage / source.name
        if manifest["encrypted"]:
            subprocess.run(
                [
                    "gpg",
                    "--batch",
                    "--yes",
                    "--pinentry-mode",
                    "loopback",
                    "--passphrase-fd",
                    "0",
                    "-o",
                    str(destination),
                    "-d",
                    str(source),
                ],
                input=conf["backup_encryption_key"].encode(),
                check=True,
                capture_output=True,
            )
        else:
            shutil.copyfile(source, destination)
        destination.chmod(0o600)
    # Reuse native SQL validation and version validation before import.
    from frappe.installer import is_downgrade, validate_database_sql

    sql = str(stage / records["database"]["name"])
    if is_downgrade(sql):
        raise ValueError("No se permite restaurar sobre una versión anterior.")
    validate_database_sql(sql, _raise=True)
    # Native installer prompts on an empty password. Socket authentication
    # ignores this nonsecret placeholder (verified by the connection above).
    _new_site(
        db_name,
        site,
        db_root_username=admin["username"],
        db_root_password=admin["password"] or "unix-socket-authentication",
        admin_password=uuid4().hex,
        source_sql=sql,
        force=True,
        db_socket=isolated["db_socket"],
        db_host=isolated["db_host"],
        db_port=isolated["db_port"],
        mariadb_user_host_login_scope="%" if admin.get("host") else None,
        db_type="mariadb",
    )
    for key in ("maintenance_mode", "pause_scheduler", "disable_scheduler", "mute_emails"):
        update_site_config(key, 1)
    for kind in ("public", "private"):
        safe_extract(stage / records[kind]["name"], target, kind, manifest["site"])
    frappe.connect()
    frappe.set_user("Administrator")
    expected = json.loads((bundle / records["snapshot"]["name"]).read_text())
    restored = snapshot()
    if expected != restored:
        write_json(
            target / "private" / "restore-differences.json",
            {"expected": expected, "actual": restored},
        )
        raise RuntimeError("La restauración no concilia; el sitio permanece aislado.")
    shutil.rmtree(stage)
    result = {
        "backup": manifest["id"],
        "source_site": manifest["site"],
        "status": "passed",
        "checked_at": datetime.now(UTC).isoformat(),
        "tables": len(TABLES),
        "files": len(restored["files"]),
        "reconciliation": restored["reconciliation"],
    }
    write_json(target / "private" / "restore-result.json", result)
    write_json(bundle.parent / "latest-restore.json", result)
    # A privileged drill returns the clone/status to the backup owner's account.
    owner = bundle.stat()
    if os.geteuid() == 0:
        for path in (target, *target.rglob("*"), bundle.parent / "latest-restore.json"):
            if not path.is_symlink():
                os.chown(path, owner.st_uid, owner.st_gid)
    return result


def recovery_status():
    """Only timestamps leave the local server; paths and manifests stay private."""
    import frappe

    root = Path(
        frappe.conf.get("omp_recovery_path")
        or Path(frappe.utils.get_bench_path()).parent / "recovery"
    )
    result = {"backup_at": None, "restore_at": None, "backup_recent": False}
    try:
        latest = json.loads((root / "latest-backup.json").read_text())
        if latest.get("site") != frappe.local.site or latest.get("status") != "verified":
            return result
        result["backup_at"] = latest["created_at"]
        age = (datetime.now(UTC) - datetime.fromisoformat(latest["created_at"])).total_seconds()
        result["backup_recent"] = 0 <= age <= 36 * 3600
        restored = json.loads((root / "latest-restore.json").read_text())
        if restored.get("status") == "passed" and restored.get("source_site") == frappe.local.site:
            result["restore_at"] = restored["checked_at"]
    except (OSError, KeyError, ValueError):
        pass
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Respaldo privado y ensayo aislado de recuperación"
    )
    parser.add_argument("--bench", type=Path, required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    backup_parser = sub.add_parser("backup")
    backup_parser.add_argument("--site", required=True)
    backup_parser.add_argument("--root", type=Path, required=True)
    backup_parser.add_argument(
        "--offline",
        action="store_true",
        help="Solo con web/worker/scheduler detenidos por el operador",
    )
    verify = sub.add_parser("verify")
    verify.add_argument("--bundle", type=Path, required=True)
    restore = sub.add_parser("restore-drill")
    restore.add_argument("--site", required=True)
    restore.add_argument("--bundle", type=Path, required=True)
    restore.add_argument("--db-admin-file", type=Path)
    options = parser.parse_args()
    os.umask(0o077)
    bench = options.bench.expanduser().resolve()
    os.chdir(bench / "sites")
    import frappe

    try:
        if options.action == "verify":
            manifest = verify_bundle(options.bundle)
            result = {"backup": manifest["id"], "status": "verified"}
        elif options.action == "restore-drill":
            result = restore_drill(bench, options.site, options.bundle, options.db_admin_file)
        else:
            frappe.init(options.site, sites_path=str(bench / "sites"))
            frappe.connect()
            frappe.set_user("Administrator")
            result = backup(options.site, options.root, systemd=not options.offline)
        print(json.dumps(result))
    finally:
        frappe.destroy()


if __name__ == "__main__":
    main()
