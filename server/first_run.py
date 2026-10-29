"""Private server initialization and controls for the dedicated WSL appliance."""

import argparse
import fcntl
import getpass
import json
import os
import pwd
import secrets
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

SITE = "omp.localhost"
STATE = Path("/var/lib/openmultipos")
SOCKET = "/run/mysqld/mysqld.sock"
SERVICES = ("omp-cache", "omp-queue", "omp-web", "omp-worker", "omp-scheduler", "omp-realtime")


def unit(home, command, *, directory="bench", extra=""):
    base = home / ".local/share/openmultipos"
    return f"""[Unit]
Description=OpenMultiPOS private server
After=mariadb.service omp-cache.service omp-queue.service
[Service]
User=openmultipos
Group=openmultipos
WorkingDirectory={base / directory}
Environment=HOME={home}
Environment=PATH={base}/tools/bin:/opt/openmultipos/node/bin:/usr/bin:/bin
RuntimeDirectory=openmultipos
RuntimeDirectoryMode=0700
RuntimeDirectoryPreserve=yes
UMask=0077
NoNewPrivileges=yes
ProtectSystem=full
ExecStart={command}
Restart=on-failure
RestartSec=5
{extra}
[Install]
WantedBy=multi-user.target
"""


def configurations(home):
    base = home / ".local/share/openmultipos"
    result = {
        "/etc/mysql/mariadb.conf.d/99-openmultipos.cnf": "[mysqld]\nskip-networking\ncharacter-set-server=utf8mb4\ncollation-server=utf8mb4_unicode_ci\n",
        "/etc/nginx/nginx.conf": f"""user openmultipos;
worker_processes auto;
pid /run/nginx.pid;
events {{ worker_connections 1024; }}
http {{
 include /etc/nginx/mime.types;
 default_type application/octet-stream;
 map $http_upgrade $connection_upgrade {{ default upgrade; '' close; }}
 map $http_x_forwarded_proto $omp_scheme {{ default $scheme; https https; }}
 server {{
  listen 127.0.0.1:8089;
  server_name localhost;
  client_max_body_size 25m;
  location /assets/ {{ alias {base}/bench/sites/assets/; expires 1h; }}
  location /socket.io {{
   proxy_pass http://unix:/run/openmultipos/realtime.sock;
   proxy_http_version 1.1;
   proxy_set_header Upgrade $http_upgrade;
   proxy_set_header Connection $connection_upgrade;
   proxy_set_header Host $http_host;
   proxy_set_header X-Frappe-Site-Name {SITE};
   proxy_set_header X-Forwarded-Proto $omp_scheme;
  }}
  location / {{
   proxy_pass http://unix:/run/openmultipos/web.sock;
   proxy_set_header Host $http_host;
   proxy_set_header X-Frappe-Site-Name {SITE};
   proxy_set_header X-Forwarded-For $remote_addr;
   proxy_set_header X-Forwarded-Proto $omp_scheme;
   proxy_read_timeout 120s;
  }}
 }}
}}
""",
    }
    for kind in ("cache", "queue"):
        persistent = kind == "queue"
        command = (
            f"/usr/bin/redis-server --port 0 --unixsocket /run/openmultipos/redis-{kind}.sock "
            f'--unixsocketperm 600 --save "" --appendonly {"yes" if persistent else "no"} '
            f"--dir {base}/redis-{kind}"
        )
        result[f"/etc/systemd/system/omp-{kind}.service"] = unit(
            home, command, directory=f"redis-{kind}"
        ).replace(
            "After=mariadb.service omp-cache.service omp-queue.service", "After=local-fs.target"
        )
    commands = {
        "web": f'{base}/bench/env/bin/gunicorn --bind unix:/run/openmultipos/web.sock --workers 2 --threads 2 --timeout 120 "frappe.app:application_with_statics()"',
        "worker": f"{base}/tools/bin/bench worker --queue short,default,long --quiet",
        "scheduler": f"{base}/tools/bin/bench schedule",
        "realtime": "/opt/openmultipos/node/bin/node apps/frappe/socketio.js",
    }
    for name, command in commands.items():
        result[f"/etc/systemd/system/omp-{name}.service"] = unit(
            home, command, directory="bench/sites" if name == "web" else "bench"
        )
    return result


def run(*args, **kwargs):
    subprocess.run(args, check=True, **kwargs)


def save(path, value):
    temporary = path.with_suffix(".new")
    with temporary.open("w") as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o600)
    temporary.replace(path)
    descriptor = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def app(home, source, payload, log):
    base = home / ".local/share/openmultipos"
    run(
        "runuser",
        "-u",
        "openmultipos",
        "--",
        "env",
        "-i",
        f"HOME={home}",
        "LANG=C.UTF-8",
        f"PATH={base}/tools/bin:/opt/openmultipos/node/bin:/usr/bin:/bin",
        str(base / "bench/env/bin/python"),
        "-c",
        source,
        input=json.dumps(payload),
        text=True,
        stdout=log,
        stderr=subprocess.STDOUT,
    )


PREPARE = """
import json,os,sys
from pathlib import Path
value=json.load(sys.stdin)
base=Path.home()/'.local/share/openmultipos'
for kind in ('cache','queue'):
 (base/('redis-'+kind)).mkdir(mode=0o700,exist_ok=True)
path=base/'bench/sites/common_site_config.json'
config=json.loads(path.read_text())
config.update(redis_cache='unix:///run/openmultipos/redis-cache.sock',redis_queue='unix:///run/openmultipos/redis-queue.sock',redis_socketio='unix:///run/openmultipos/redis-queue.sock',socketio_uds='/run/openmultipos/realtime.sock',default_site='omp.localhost',serve_default_site=True)
path.write_text(json.dumps(config))
path.chmod(0o600)
"""

INSTALL = """
import json,os,sys
from pathlib import Path
import frappe
from frappe.installer import _new_site,install_app
value=json.load(sys.stdin)
base=Path.home()/'.local/share/openmultipos/bench'
os.chdir(base/'sites')
site=Path('omp.localhost')
if not site.exists():
 frappe.init(str(site), new_site=True)
 _new_site(db_name=value['db_name'],site=str(site),db_root_username='omp_bootstrap',db_root_password=value['root_password'],admin_password=value['admin_password'],db_password=value['db_password'],db_socket=value['socket'],db_type='mariadb',mariadb_user_host_login_scope='localhost')
else:
 config=json.loads((site/'site_config.json').read_text())
 if config.get('db_name') != value['db_name']:
  raise RuntimeError('El sitio no pertenece a este intento de preparación')
 frappe.init(str(site))
 frappe.connect()
frappe.set_user('Administrator')
for name in ('erpnext','xpos','open_multi_pos'):
 install_app(name)
frappe.db.set_single_value('System Settings','language','es')
frappe.db.set_single_value('System Settings','time_zone','America/Bogota')
frappe.db.commit()
from frappe.utils.password import get_encryption_key
get_encryption_key()
frappe.destroy()
"""


RETIRE = """
import json,os,re,sys
from pathlib import Path
import MySQLdb
value=json.load(sys.stdin)
name=value['db_name']
if not re.fullmatch(r'_omp_[0-9a-f]{24}',name):
 raise ValueError('Identidad de preparación inválida')
base=Path.home()/'.local/share/openmultipos'
site=base/'bench/sites/omp.localhost'
archive=base/'incomplete'/name
for path in (site,archive):
 if path.resolve()!=path:
  raise ValueError('No se permiten enlaces en la preparación')
if site.exists() and archive.exists():
 raise ValueError('Hay dos copias del intento; se conservan sin cambios')
source=site if site.exists() else archive
if source.exists():
 config=source/'site_config.json'
 if config.is_file():
  config=json.loads(config.read_text())
  if config.get('db_name')!=name or config.get('db_password')!=value['db_password']:
   raise ValueError('El sitio no pertenece al intento registrado')
 elif any(path.is_file() and path.stat().st_size for path in source.rglob('*')):
  raise ValueError('El sitio contiene archivos sin prueba de propiedad')
 for directory in ('public/files','private/files'):
  if any(path.is_file() for path in (source/directory).rglob('*')):
   raise ValueError('El sitio contiene archivos de usuario; se conserva')
connection=MySQLdb.connect(unix_socket=value['socket'],user='omp_bootstrap',passwd=value['root_password'])
cursor=connection.cursor()
cursor.execute('SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s',(name,))
tables={row[0] for row in cursor.fetchall()}
for table in ('tabCompany','tabCustomer','tabSupplier','tabContact','tabAddress','tabItem','tabSales Invoice','tabStock Ledger Entry','tabGL Entry'):
 if table in tables:
  cursor.execute(f'SELECT COUNT(*) FROM `{name}`.`{table}`')
  if cursor.fetchone()[0]:
   raise ValueError('Hay datos comerciales; se conserva el sitio')
if 'tabUser' in tables:
 cursor.execute(f"SELECT COUNT(*) FROM `{name}`.tabUser WHERE name NOT IN ('Administrator','Guest')")
 if cursor.fetchone()[0]:
  raise ValueError('Hay cuentas personales; se conserva el sitio')
connection.close()
if site.exists():
 archive.parent.mkdir(mode=0o700,exist_ok=True)
 descriptor=os.open(base,os.O_DIRECTORY);os.fsync(descriptor);os.close(descriptor)
 site.rename(archive)
 for directory in (site.parent,archive.parent):
  descriptor=os.open(directory,os.O_DIRECTORY);os.fsync(descriptor);os.close(descriptor)
"""


def setup(home, state, password, *, recover=False):
    if state.get("installed"):
        if recover:
            raise ValueError("El sitio ya está instalado; no se reinicia su preparación")
        return
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise ValueError("Usa una contraseña inicial de 12 a 128 caracteres")
    if recover:
        if not state.get("db_name") or len(state.get("previous", [])) >= 3:
            raise ValueError("Revisa los intentos conservados antes de reiniciar la preparación")
        state["retiring"] = True
        save(STATE / "bootstrap.json", state)
    if not state:
        if (home / ".local/share/openmultipos/bench/sites" / SITE).exists():
            raise ValueError(
                "Ya existe un sitio sin registro de instalación; se conserva sin cambios"
            )
        state.update(db_name="_omp_" + secrets.token_hex(12), db_password=secrets.token_hex(32))
        save(STATE / "bootstrap.json", state)
    for name, content in configurations(home).items():
        path = Path(name)
        path.write_text(content)
        path.chmod(0o644)
    with (STATE / "setup.log").open("a") as log:
        app(home, PREPARE, {}, log)
        run("systemctl", "daemon-reload", stdout=log, stderr=log)
        run("systemctl", "disable", "mariadb", *SERVICES, "nginx", stdout=log, stderr=log)
        run("systemctl", "unmask", "mariadb", stdout=log, stderr=log)
        run("systemctl", "start", "mariadb", "omp-cache", "omp-queue", stdout=log, stderr=log)
        temporary = secrets.token_hex(32)
        sql = f"CREATE USER IF NOT EXISTS 'omp_bootstrap'@'localhost' IDENTIFIED BY '{temporary}'; ALTER USER 'omp_bootstrap'@'localhost' IDENTIFIED BY '{temporary}'; GRANT ALL PRIVILEGES ON *.* TO 'omp_bootstrap'@'localhost' WITH GRANT OPTION;"
        try:
            run(
                "mariadb",
                "--protocol=socket",
                "-uroot",
                input=sql,
                text=True,
                stdout=log,
                stderr=log,
            )
            if state.get("retiring"):
                app(home, RETIRE, {**state, "root_password": temporary, "socket": SOCKET}, log)
                previous = state.get("previous", []) + [
                    {"db_name": state["db_name"], "db_password": state["db_password"]}
                ]
                state.clear()
                state.update(
                    db_name="_omp_" + secrets.token_hex(12),
                    db_password=secrets.token_hex(32),
                    previous=previous,
                )
                save(STATE / "bootstrap.json", state)
            app(
                home,
                INSTALL,
                {**state, "root_password": temporary, "admin_password": password, "socket": SOCKET},
                log,
            )
        finally:
            run(
                "mariadb",
                "--protocol=socket",
                "-uroot",
                input="DROP USER IF EXISTS 'omp_bootstrap'@'localhost';",
                text=True,
                stdout=log,
                stderr=log,
            )
        app(
            home,
            "import os; from pathlib import Path; os.chdir(Path.home()/'.local/share/openmultipos/bench/sites'); from frappe.migrate import SiteMigration; SiteMigration().run(site='omp.localhost')",
            {},
            log,
        )
    state["installed"] = True
    save(STATE / "bootstrap.json", state)


def public_status(state):
    return {
        "protocol": 1,
        "installed": bool(state.get("installed")),
        "recoverable": bool(state.get("db_name") and not state.get("installed")),
        "retained_attempts": len(state.get("previous", [])),
    }


BACKUP = """
import json,os,sys,tempfile
from pathlib import Path
from uuid import uuid4
import frappe
from open_multi_pos.operations import backup,restore_drill
value=json.load(sys.stdin)
base=Path.home()/'.local/share/openmultipos'
bench=base/'bench'
os.chdir(bench/'sites')
frappe.init('omp.localhost',sites_path=str(bench/'sites'))
frappe.connect()
frappe.set_user('Administrator')
try:
 root=base/'recovery'
 result=backup('omp.localhost',root,systemd=False)
finally:
 frappe.destroy()
if value.get('check'):
 descriptor,path=tempfile.mkstemp(prefix='.drill-admin-',dir=root)
 try:
  with os.fdopen(descriptor,'w') as stream:
   json.dump({'username':value['username'],'password':value['password'],'socket':value['socket']},stream)
  restore_drill(bench,'omp-restore-'+uuid4().hex[:16]+'.localhost',root/result['backup'],Path(path))
 finally:
  Path(path).unlink(missing_ok=True)
  frappe.destroy()
"""


def backup_site(home, state, *, check=False):
    if not state.get("installed"):
        raise ValueError("Prepara el sitio antes de crear una copia")
    # The same lifetime lock prevents another controller starting during the copy.
    with (STATE / "server.lock").open("a") as lifetime:
        fcntl.flock(lifetime, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for service in ("nginx", *SERVICES, "mariadb"):
            if (
                subprocess.run(
                    ["systemctl", "is-active", "--quiet", service], check=False
                ).returncode
                == 0
            ):
                raise ValueError("Detén el servidor desde su controlador antes de respaldar")
        with (STATE / "recovery.log").open("a") as log:
            password = secrets.token_hex(32) if check else ""
            username = "omp_drill_" + secrets.token_hex(8)
            created = False
            try:
                run(
                    "systemctl",
                    "start",
                    "mariadb",
                    "omp-cache",
                    "omp-queue",
                    stdout=log,
                    stderr=log,
                )
                if check:
                    run(
                        "mariadb",
                        "--protocol=socket",
                        "-uroot",
                        text=True,
                        input=f"CREATE USER '{username}'@'localhost' IDENTIFIED BY '{password}';",
                        stdout=log,
                        stderr=log,
                    )
                    created = True
                    run(
                        "mariadb",
                        "--protocol=socket",
                        "-uroot",
                        text=True,
                        input=f"GRANT ALL PRIVILEGES ON *.* TO '{username}'@'localhost' WITH GRANT OPTION;",
                        stdout=log,
                        stderr=log,
                    )
                app(
                    home,
                    BACKUP,
                    {"check": check, "username": username, "password": password, "socket": SOCKET},
                    log,
                )
            finally:
                try:
                    if created:
                        run(
                            "mariadb",
                            "--protocol=socket",
                            "-uroot",
                            text=True,
                            input=f"DROP USER IF EXISTS '{username}'@'localhost';",
                            stdout=log,
                            stderr=log,
                        )
                finally:
                    run(
                        "systemctl",
                        "stop",
                        "omp-queue",
                        "omp-cache",
                        "mariadb",
                        stdout=log,
                        stderr=log,
                    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("setup", "recover", "start", "serve", "stop", "status", "backup", "restore-check"),
    )
    parser.add_argument("--stdin", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--events", action="store_true", help=argparse.SUPPRESS)
    options = parser.parse_args()
    if os.geteuid() != 0 or not Path("/etc/openmultipos-build-environment").is_file():
        parser.error("Se requiere la distribución dedicada de OpenMultiPOS y permisos root")
    os.umask(0o077)
    STATE.mkdir(mode=0o700, exist_ok=True)
    with (STATE / "bootstrap.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = STATE / "bootstrap.json"
        state = json.loads(path.read_text()) if path.exists() else {}
        home = Path(pwd.getpwnam("openmultipos").pw_dir)
        if options.action in ("setup", "recover"):
            password = (
                ""
                if state.get("installed")
                else (
                    json.load(sys.stdin)["password"]
                    if options.stdin
                    else getpass.getpass("Contraseña inicial de Administrator: ")
                )
            )
            setup(home, state, password, recover=options.action == "recover")
            print("Sitio preparado. Inicia el servidor y completa el asistente nativo de ERPNext.")
        elif options.action in ("backup", "restore-check"):
            backup_site(home, state, check=options.action == "restore-check")
            print(
                "Copia verificada. Puedes iniciar el servidor."
                if options.action == "backup"
                else "Copia y restauración aislada verificadas. Puedes iniciar el servidor."
            )
        elif options.action in ("start", "serve"):
            server_lock = None
            if options.action == "serve":
                server_lock = (STATE / "server.lock").open("a")
                fcntl.flock(server_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if not state.get("installed"):
                parser.error("Completa primero la preparación del sitio")
            run("nginx", "-t")
            run("systemctl", "unmask", "nginx")
            run("systemctl", "disable", "mariadb", *SERVICES, "nginx")
            run("systemctl", "start", "mariadb", *SERVICES, "nginx")
            for _attempt in range(60):
                try:
                    with urlopen("http://127.0.0.1:8089/api/method/ping", timeout=2) as response:
                        if json.load(response).get("message") == "pong":
                            break
                except (OSError, ValueError):
                    pass
                time.sleep(0.5)
            else:
                raise RuntimeError(
                    "El servidor no respondió. Revisa los servicios antes de abrir caja"
                )
            print("Abre http://localhost:8089/omp e inicia sesión como Administrator.", flush=True)
            if options.action == "serve":
                fcntl.flock(lock, fcntl.LOCK_UN)
                print(
                    json.dumps({"event": "ready", "protocol": 1})
                    if options.events
                    else "Servidor activo. Escribe stop para detenerlo.",
                    flush=True,
                )
                try:
                    for line in sys.stdin:
                        if line.strip() == "stop":
                            break
                except KeyboardInterrupt:
                    pass
                finally:
                    run("systemctl", "stop", "nginx", *reversed(SERVICES), "mariadb")
                    server_lock.close()
        elif options.action == "stop":
            run("systemctl", "disable", "mariadb", *SERVICES, "nginx")
            run("systemctl", "stop", "nginx", *reversed(SERVICES), "mariadb")
        else:
            print(json.dumps(public_status(state)))


if __name__ == "__main__":
    try:
        main()
    except BlockingIOError:
        print("Hay otra preparación o un controlador del servidor activo.", file=sys.stderr)
        sys.exit(1)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except (OSError, RuntimeError, subprocess.CalledProcessError):
        print(
            "No se pudo completar la operación. El sitio se conserva; revisa el registro local y los servicios.",
            file=sys.stderr,
        )
        sys.exit(1)
