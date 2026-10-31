"""Seal a site-free build distribution before its cold export."""

import argparse
import configparser
import hashlib
import json
import os
import pwd
import re
import shutil
import subprocess
from pathlib import Path

from server.image_contract import validate


def remove(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("La limpieza debe permanecer dentro de la imagen")
    path = root / relative
    if path.parent.resolve() != path.parent:
        raise ValueError("No se limpian rutas con padres enlazados")
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def replace(path, content):
    temporary = path.with_name(path.name + ".omp-new")
    with temporary.open("x") as stream:
        stream.write(content)
    temporary.chmod(0o644)
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    options = parser.parse_args()
    if os.geteuid() != 0 or not re.fullmatch(r"[a-f0-9]{40}", options.revision):
        parser.error("Se requiere root y una revisión pública exacta")
    root = Path("/")
    validate(root)
    for service in ("mariadb", "redis-server", "nginx"):
        if subprocess.run(["systemctl", "is-active", "--quiet", service]).returncode == 0:
            raise ValueError("Detén los servicios antes de sellar la imagen")
    home = Path(pwd.getpwnam("openmultipos").pw_dir)
    base = home / ".local/share/openmultipos"
    source = Path("/opt/openmultipos/source")
    target = Path("/usr/local/lib/openmultipos")
    target.mkdir(parents=True, exist_ok=True)
    for name in ("first_run.py", "image_contract.py"):
        shutil.copyfile(source / "server" / name, target / name)
        (target / name).chmod(0o644)
    manifest = Path("/usr/share/openmultipos")
    manifest.mkdir(parents=True, exist_ok=True)
    lock = json.loads((source / "upstream.lock.json").read_text())
    for app, metadata in lock["dependencies"].items():
        directory = base / "bench/apps" / app
        actual = subprocess.check_output(
            [
                "git",
                "-c",
                "safe.directory=" + str(directory),
                "-C",
                str(directory),
                "rev-parse",
                "HEAD",
            ],
            text=True,
        ).strip()
        if actual != metadata["commit"]:
            raise ValueError("Una dependencia no coincide con su revisión fijada")
    packages = subprocess.check_output(
        ["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\t${Architecture}\n"], text=True
    )
    (manifest / "packages.tsv").write_text(packages)
    sources = subprocess.check_output(
        ["dpkg-query", "-W", "-f=${source:Package}\t${source:Version}\n"], text=True
    )
    (manifest / "source-packages.tsv").write_text(
        "\n".join(sorted(set(sources.splitlines()))) + "\n"
    )
    for name in ("bench", "tools"):
        output = subprocess.check_output(
            [
                "runuser",
                "-u",
                "openmultipos",
                "--",
                str(
                    base / name / "env/bin/python" if name == "bench" else base / "tools/bin/python"
                ),
                "-m",
                "pip",
                "list",
                "--format=json",
            ],
            text=True,
        )
        (manifest / (name + "-packages.json")).write_text(output)
    (manifest / "source.json").write_text(
        json.dumps(
            {
                "revision": options.revision,
                "upstream": lock["dependencies"],
                "protocol": 1,
                "first_run_sha256": hashlib.sha256(
                    (target / "first_run.py").read_bytes()
                ).hexdigest(),
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    shutil.copyfile(source / "LICENSE", manifest / "LICENSE")
    (manifest / "THIRD-PARTY.txt").write_text(
        "Código completo de Frappe, ERPNext y X POS: directorios apps del Bench. Licencias/avisos de paquetes Ubuntu: /usr/share/doc/*/copyright. Metadatos y licencias Python: *.dist-info. Node incluye LICENSE. Manifiestos de versiones: este directorio. La imagen usa software GPL y MIT; consulta las licencias y las fuentes incluidas.\n"
    )
    config = configparser.ConfigParser()
    config.read("/etc/wsl.conf")
    config["network"] = {
        "hostname": "openmultipos",
        "generateHosts": "true",
        "generateResolvConf": "true",
    }
    config["user"] = {"default": "openmultipos"}
    with Path("/etc/wsl.conf").open("w") as stream:
        config.write(stream)
    # Stop journal writers before removing build-host identifiers.
    subprocess.run(
        [
            "systemctl",
            "stop",
            "systemd-journald.service",
            "systemd-journald.socket",
            "systemd-journald-dev-log.socket",
            "systemd-journald-audit.socket",
            "systemd-random-seed.service",
        ],
        check=True,
    )
    for relative in (
        "var/log",
        "var/cache/apt/archives",
        "var/lib/systemd/random-seed",
        "var/lib/dbus/machine-id",
        "root/.cache",
        "root/.npm",
        "root/.bash_history",
        "root/.rnd",
        "etc/ssh/ssh_host_ed25519_key",
        "etc/ssh/ssh_host_rsa_key",
        "etc/ssh/ssh_host_ecdsa_key",
        "etc/ssl/private/ssl-cert-snakeoil.key",
        "etc/ssl/certs/ssl-cert-snakeoil.pem",
    ):
        remove(root, relative)
    for relative in (".cache", ".npm", ".yarn", ".bash_history"):
        remove(root, str(home.relative_to(root) / relative))
    for path in Path("/etc/ssh").glob("ssh_host_*"):
        remove(root, str(path.relative_to(root)))
    Path("/var/log").mkdir(mode=0o755)
    Path("/var/log/nginx").mkdir(mode=0o755)
    replace(Path("/etc/machine-id"), "")
    replace(Path("/etc/hostname"), "openmultipos\n")
    replace(Path("/etc/hosts"), "127.0.0.1 localhost\n127.0.1.1 openmultipos\n::1 localhost\n")
    replace(Path("/etc/resolv.conf"), "# Generated by WSL at first launch\n")
    if Path("/etc/machine-id").read_text() or any(Path("/etc/ssl/private").glob("*")):
        raise ValueError("La imagen conserva identidad o claves TLS privadas")
    validate(root)
    os.sync()
    print("Imagen sellada sin sitio. Apaga esta distribución y expórtala sin volver a arrancarla.")


if __name__ == "__main__":
    main()
