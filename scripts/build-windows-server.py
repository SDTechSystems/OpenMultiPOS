"""Assemble private Windows acceptance candidates from an audited clean WSL image."""

import argparse
import hashlib
import json
import re
import runpy
import shutil
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check_image(image, manifest, audit):
    metadata = json.loads(manifest.read_text())
    proof = json.loads(audit.read_text())
    checksum = digest(image)
    if (
        metadata.get("schema") != 1
        or metadata.get("sha256") != checksum
        or proof.get("sha256") != checksum
        or not re.fullmatch(r"[a-f0-9]{40}", str(metadata.get("source_revision", "")))
        or metadata.get("source_revision") != proof.get("source_revision")
        or proof.get("sites") != 0
        or proof.get("application_schemas") != 0
        or proof.get("reusable_identity") is not False
    ):
        raise ValueError("La imagen y su revisión limpia deben coincidir con el informe")
    return metadata


def build(destination, image, manifest, audit, *, archive=True):
    metadata = check_image(image, manifest, audit)
    repo = Path(__file__).resolve().parents[1]
    destination.mkdir(parents=True, exist_ok=False)
    client = destination / "client"
    client_builder = runpy.run_path(str(repo / "scripts/build-windows-client.py"))
    client_builder["build"](client)
    portable = destination / "OpenMultiPOS-Server-0.1.0"
    runpy.run_path(str(repo / "scripts/build-windows-controller.py"))["build"](
        portable, client / "OpenMultiPOS-Client-0.1.0/Manual.html"
    )
    shutil.copyfile(image, portable / "OpenMultiPOS-Server.wsl")
    shutil.copyfile(manifest, portable / "server-image.json")
    shutil.copyfile(repo / "windows/SERVIDOR.txt", portable / "LEEME.txt")
    for path in client_builder["public_windows_sources"](repo):
        shutil.copyfile(path, portable / "source" / path.name)
    # Public source only; no ignored build outputs or private fixtures.
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=repo).decode().split("\0")
    with ZipFile(portable / "source.zip", "w", ZIP_DEFLATED) as source:
        for relative in sorted(filter(None, files)):
            path = repo / relative
            if path.is_symlink() or not path.is_file():
                raise ValueError("Las fuentes deben ser archivos públicos regulares")
            source.write(path, relative)
    installer = portable / "OpenMultiPOS-Server-Setup-0.1.0.exe"
    resources = (
        "OpenMultiPOS-Server-Control.exe",
        "Manual.html",
        "LICENSE",
        "LEEME.txt",
        "source.zip",
    )
    subprocess.run(
        [
            "mcs",
            "-target:winexe",
            "-main:ServerInstaller",
            "-sdk:4.8",
            "-platform:x64",
            "-optimize+",
            "-r:System.Windows.Forms",
            "-r:System.Drawing",
            "-r:System.Web.Extensions",
            "-out:" + str(installer),
            *["-resource:" + str(portable / name) + "," + name for name in resources],
            str(repo / "windows/ServerInstaller.cs"),
            str(repo / "windows/Server.cs"),
        ],
        check=True,
    )
    subprocess.run(["mono", str(installer), "--self-test"], check=True)
    info = {
        "version": "0.1.0",
        "scope": "complete server acceptance candidate; not approved for production or sharing",
        "edition": "Servidor propio",
        "data_location": "recipient computer; independent WSL installation",
        "default_remote_server": None,
        "signed": False,
        "image": metadata,
        "windows_gui_acceptance": "pending",
        "clean_windows_acceptance": "pending",
        "corresponding_source_review": "pending",
        "requires": ["Windows x64", ".NET Framework 4.8", "WSL2", "virtualization", "30 GB free"],
    }
    (portable / "build-info.json").write_text(json.dumps(info, indent=2) + "\n")
    sums = [
        digest(path) + "  " + path.relative_to(portable).as_posix()
        for path in sorted(portable.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS.txt"
    ]
    (portable / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n")
    if archive:
        # The .wsl is already compressed. Avoid a second costly compression pass.
        archive_path = destination / "OpenMultiPOS-Server-Portable-0.1.0.zip"
        with ZipFile(archive_path, "w", ZIP_STORED, allowZip64=True) as output:
            for path in sorted(portable.rglob("*")):
                if path.is_file():
                    output.write(path, path.relative_to(destination))
        (destination / "SHA256SUMS.txt").write_text(
            digest(archive_path) + "  " + archive_path.name + "\n"
        )
    print("Candidato privado completo. Aceptación Windows y revisión de fuentes pendientes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--no-archive", action="store_true", help="Build only the extracted folder")
    args = parser.parse_args()
    build(args.output, args.image, args.manifest, args.audit, archive=not args.no_archive)
