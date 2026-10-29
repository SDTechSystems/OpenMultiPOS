"""Build the Windows client offline with Mono and the Markdown renderer already in Frappe."""

import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
from base64 import b64encode
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import markdown2


def build(destination):
    repo = Path(__file__).resolve().parents[1]
    destination.mkdir(parents=True, exist_ok=False)
    portable = destination / "OpenMultiPOS-Client-0.1.0"
    portable.mkdir()
    manifest = json.loads((repo / "open_multi_pos/public/manual/manifest.json").read_text())
    articles = []
    docs = [repo / "docs/manual.md", repo / "docs/online-access.md"]
    docs += sorted(path for path in (repo / "docs").rglob("*.md") if path not in docs)
    anchors = {
        path.resolve(): "doc-"
        + path.relative_to(repo / "docs").with_suffix("").as_posix().replace("/", "--")
        for path in docs
    }
    for doc in docs:
        rendered = markdown2.markdown(doc.read_text(), extras=["tables", "fenced-code-blocks"])

        def image(match, doc=doc):
            path = (doc.parent / html.unescape(match[1])).resolve()
            relative = path.relative_to(repo).as_posix()
            expected = manifest["images"].get(relative)
            content = path.read_bytes()
            if not expected or hashlib.sha256(content).hexdigest() != expected:
                raise ValueError("Una imagen del manual no está aprobada por su manifest")
            return 'src="data:image/png;base64,' + b64encode(content).decode() + '"'

        def link(match, doc=doc):
            name = html.unescape(match[1]).split("#", 1)[0]
            if ":" not in name and name.endswith(".md"):
                target = (doc.parent / name).resolve()
                if target in anchors:
                    return 'href="#' + anchors[target] + '"'
            return match[0]

        rendered = re.sub(r'src="([^"]+)"', image, rendered)
        rendered = re.sub(r'href="([^"]+)"', link, rendered)
        articles.append('<article id="' + anchors[doc.resolve()] + '">' + rendered + "</article>")
    manual = (
        """<!doctype html><html lang="es-CO"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Manual OpenMultiPOS</title>
<style>body{font:16px/1.6 'Segoe UI',sans-serif;max-width:1000px;margin:auto;padding:24px;color:#182536}img{max-width:100%;height:auto}table{border-collapse:collapse}td,th{border:1px solid #d5dfe9;padding:8px}pre{overflow:auto;padding:12px;background:#f3f6fa}article{margin:40px 0;border-top:1px solid #d5dfe9}a{color:#245fa4}nav{position:sticky;top:0;background:white;padding:8px}@media print{nav{display:none}article{break-before:page}}</style>
<nav><a href="#doc-manual">Manual de uso</a> · <a href="#doc-online-access">Datos compartidos</a> · <a href="#doc-recovery">Respaldos</a></nav>
<p>Manual OpenMultiPOS 0.1.0. La edición del cliente requiere un servidor ya configurado. La edición completa incluye su controlador y una imagen limpia. Las capturas usan datos ficticios. La aceptación visual y en Windows limpio sigue pendiente.</p>
"""
        + "\n".join(articles)
        + "</html>"
    )
    (portable / "Manual.html").write_text(manual)
    for source, name in (
        ("LICENSE", "LICENSE"),
        ("windows/Configurar.cmd", "Configurar.cmd"),
        ("windows/LEEME.txt", "LEEME.txt"),
    ):
        shutil.copyfile(repo / source, portable / name)
    source_dir = portable / "source"
    source_dir.mkdir()
    for path in (repo / "windows").iterdir():
        if path.is_file():
            shutil.copyfile(path, source_dir / path.name)
    shutil.copyfile(__file__, source_dir / Path(__file__).name)
    subprocess.run(
        [
            "mcs",
            "-target:winexe",
            "-sdk:4.8",
            "-platform:x64",
            "-optimize+",
            "-r:System.Windows.Forms",
            "-r:System.Drawing",
            "-out:" + str(portable / "OpenMultiPOS.exe"),
            str(repo / "windows/Client.cs"),
        ],
        check=True,
    )
    subprocess.run(["mono", str(portable / "OpenMultiPOS.exe"), "--self-test"], check=True)
    installer = destination / "OpenMultiPOS-Client-Setup-0.1.0.exe"
    resources = (
        ("OpenMultiPOS.exe", "client"),
        ("Manual.html", "manual"),
        ("LICENSE", "license"),
        ("Configurar.cmd", "configure"),
    )
    subprocess.run(
        [
            "mcs",
            "-target:winexe",
            "-sdk:4.8",
            "-platform:x64",
            "-optimize+",
            "-r:System.Windows.Forms",
            "-out:" + str(installer),
            *["-resource:" + str(portable / name) + "," + key for name, key in resources],
            str(repo / "windows/Installer.cs"),
        ],
        check=True,
    )
    subprocess.run(["mono", str(installer), "--self-test"], check=True)
    info = {
        "version": "0.1.0",
        "scope": "client-only; requires an existing OpenMultiPOS server",
        "windows_acceptance": "pending",
        "signed": False,
        "compiler": subprocess.check_output(["mcs", "--version"], text=True).strip(),
        "markdown_renderer": "markdown2 " + markdown2.__version__,
        "requires": ["Windows 10/11 x64", ".NET Framework 4.8", "Chrome/Edge"],
        "sources_sha256": {
            path.relative_to(repo).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [
                repo / "windows/Client.cs",
                repo / "windows/Installer.cs",
                Path(__file__).resolve(),
            ]
        },
        "manual_sha256": hashlib.sha256((portable / "Manual.html").read_bytes()).hexdigest(),
    }
    (portable / "build-info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n")
    archive = destination / "OpenMultiPOS-Client-Portable-0.1.0.zip"
    with ZipFile(archive, "w", ZIP_DEFLATED) as output:
        for path in sorted(portable.rglob("*")):
            if path.is_file():
                output.write(path, path.relative_to(destination))
    sums = []
    for path in (portable / "OpenMultiPOS.exe", portable / "Manual.html", installer, archive):
        sums.append(
            hashlib.sha256(path.read_bytes()).hexdigest()
            + "  "
            + path.relative_to(destination).as_posix()
        )
    (destination / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n")
    print("Cliente compilado y contratos de URL aprobados. Aceptación en Windows pendiente.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    build(parser.parse_args().output.resolve())
