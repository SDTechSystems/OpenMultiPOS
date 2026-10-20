"""Prepare a new development Bench from verified upstream commits, never a live site."""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def run(command, cwd=None):
    result = subprocess.run([str(arg) for arg in command], cwd=cwd)
    if result.returncode:
        raise SystemExit(f"Falló {command[0]}; revisar la salida anterior.")


def commit(path):
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench", required=True, type=Path)
    parser.add_argument("--sources", required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    target, sources = args.bench.expanduser().resolve(), args.sources.expanduser().resolve()
    if target.exists():
        parser.error("El destino Bench ya existe; no se sobrescribe ni actualiza automáticamente.")
    if (sources / "open_multi_pos").exists():
        parser.error("La instantánea open_multi_pos ya existe; usar otro directorio de fuentes.")
    if target == sources or target in sources.parents or sources in target.parents:
        parser.error("Bench y fuentes deben ser directorios independientes.")
    if any(not re.fullmatch(r"[A-Za-z0-9_./-]+", str(path)) for path in (target, sources)):
        parser.error("Bench requiere rutas Linux sin espacios ni caracteres de shell.")
    if sys.version_info[:2] != (3, 14):
        parser.error("Se requiere Python 3.14.")
    for tool in ("git", "bench", "node", "yarn", "pkg-config", "redis-server"):
        if not shutil.which(tool):
            parser.error(f"Falta la herramienta {tool}.")
    node_major = int(subprocess.check_output(["node", "--version"], text=True).split(".")[0][1:])
    if node_major < 24:
        parser.error("Se requiere Node >=24.")
    lock = json.loads((repo / "upstream.lock.json").read_text())
    sources.mkdir(parents=True, exist_ok=True)
    for name, dependency in lock["dependencies"].items():
        path = sources / name
        if not path.exists():
            run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "--branch",
                    dependency["branch"],
                    dependency["repository"],
                    path,
                ]
            )
            if commit(path) != dependency["commit"]:
                run(["git", "-C", path, "fetch", "--depth", "1", "origin", dependency["commit"]])
                run(["git", "-C", path, "checkout", "--detach", dependency["commit"]])
        if commit(path) != dependency["commit"]:
            parser.error(f"SHA incorrecto en {name}; no se modifica un checkout existente.")
        print(f"Verificado {name}: {dependency['commit']}", flush=True)

    target.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "bench",
            "init",
            target,
            "--frappe-path",
            sources / "frappe",
            "--python",
            sys.executable,
            "--skip-assets",
            "--no-backups",
        ]
    )
    for name in ("erpnext", "xpos"):
        run(["bench", "get-app", "--skip-assets", sources / name], cwd=target)
    # Bench interpolates paths into shell commands. Export source to a safe Linux
    # path so a Windows checkout containing spaces is supported without patching core.
    snapshot = sources / "open_multi_pos"
    snapshot.mkdir()
    names = (
        subprocess.check_output(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=repo
        )
        .decode()
        .split("\0")
    )
    for name in filter(None, names):
        source = repo / name
        if source.is_symlink():
            parser.error("No se exportan enlaces simbólicos del checkout.")
        if source.is_file():
            destination = snapshot / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    run(["git", "init", "--quiet", snapshot])
    run(["git", "add", "--all"], cwd=snapshot)
    run(
        [
            "git",
            "-c",
            "user.name=OpenMultiPOS",
            "-c",
            "user.email=dev@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "Local development snapshot",
        ],
        cwd=snapshot,
    )
    run(["bench", "get-app", "--skip-assets", snapshot], cwd=target)
    for name, dependency in lock["dependencies"].items():
        if commit(target / "apps" / name) != dependency["commit"]:
            raise SystemExit(f"SHA inesperado en la instalación {name}.")
    print("Bench preparado. Crear un sitio local desechable según docs/development.md.")


if __name__ == "__main__":
    main()
