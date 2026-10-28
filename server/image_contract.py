"""Reject application sites, database schemas and reusable passwords before image export."""

import argparse
import json
from pathlib import Path

BENCH = Path("home/openmultipos/.local/share/openmultipos/bench")


def validate(root):
    root = Path(root)
    if not (root / "etc/openmultipos-build-environment").is_file():
        raise ValueError("La imagen no pertenece al entorno de construcción dedicado")
    sites = root / BENCH / "sites"
    allowed = {"assets", "apps.txt", "apps.json", "common_site_config.json"}
    if not sites.is_dir() or any(path.name not in allowed for path in sites.iterdir()):
        raise ValueError("La imagen contiene un sitio o archivos no admitidos")
    config_file = sites / "common_site_config.json"
    if config_file.is_symlink():
        raise ValueError("La configuración no puede ser un enlace")
    config = json.loads(config_file.read_text())
    if any(
        word in key.lower()
        for key in config
        for word in ("password", "secret", "encryption", "token")
    ):
        raise ValueError("La configuración contiene credenciales reutilizables")
    for key in ("redis_cache", "redis_queue", "redis_socketio"):
        value = config.get(key, "")
        if "@" in value:
            raise ValueError("La conexión Redis contiene credenciales")
    database = root / "var/lib/mysql"
    if database.is_dir():
        for path in database.iterdir():
            if path.is_symlink() or (
                path.is_dir() and path.name not in {"mysql", "sys", "performance_schema"}
            ):
                raise ValueError("La imagen contiene una base de datos ajena al sistema")
    shadow = root / "etc/shadow"
    for line in shadow.read_text().splitlines():
        fields = line.split(":")
        if len(fields) < 2 or not fields[1].startswith(("!", "*")):
            raise ValueError("La imagen contiene una cuenta Linux con contraseña reutilizable")
    return {"site_count": 0, "application_databases": 0, "reusable_linux_passwords": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    options = parser.parse_args()
    print(json.dumps(validate(options.root), sort_keys=True))


if __name__ == "__main__":
    main()
