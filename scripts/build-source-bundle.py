"""Package verified dependency sources without collector logs or private local paths."""

import argparse
import hashlib
import json
import re
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def local_file(root, relative):
    path = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Ruta de fuente inválida")
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("La fuente debe ser un archivo regular dentro del conjunto")
    return path


def dsc_files(root, package, version):
    for path in sorted((root / "ubuntu" / package).glob("*.dsc")):
        path = local_file(root, path.relative_to(root))
        text = path.read_text()
        if re.search(r"^Source: " + re.escape(package) + r"$", text, re.M) and re.search(
            r"^Version: " + re.escape(version) + r"$", text, re.M
        ):
            block = re.search(r"^Checksums-Sha256:\n((?: [^\n]+\n)+)", text, re.M)
            if not block:
                raise ValueError("El dsc no tiene sumas SHA256")
            result = {
                path.relative_to(root).as_posix(): digest(local_file(root, path.relative_to(root)))
            }
            for line in block[1].splitlines():
                checksum, size, name = line.split()
                relative = (path.parent.relative_to(root) / name).as_posix()
                source = local_file(root, relative)
                if source.stat().st_size != int(size) or digest(source) != checksum:
                    raise ValueError("Una fuente Ubuntu no coincide con su dsc")
                result[relative] = checksum
            return result
    raise ValueError("Falta la versión exacta de una fuente Ubuntu")


def collect(root):
    def read(name):
        return json.loads(local_file(root, name).read_text())

    files = {}
    components = []
    for entry in read("ubuntu-source-status.json"):
        package, version = entry["package"], entry["version"]
        if not re.fullmatch(r"[a-z0-9][a-z0-9+.-]*", package):
            raise ValueError("Nombre de paquete Ubuntu inválido")
        names = dsc_files(root, package, version)
        components.append(
            {"kind": "ubuntu", "name": package, "version": version, "files": list(names)}
        )
        files.update(names)
    runtime = read("python-runtime-source-status.json")
    recovery = {(e["name"], e["version"]): e for e in read("recovery-status.json")["results"]}
    for entry in runtime["results"]:
        downloads = entry.get("downloads", []) if entry.get("state") == "complete" else []
        if not downloads:
            replacement = recovery.get((entry["name"], entry["version"]))
            if not replacement or replacement.get("state") not in (
                "verified_sdist",
                "verified_wheel",
            ):
                raise ValueError("Falta una fuente runtime verificada")
            downloads = [replacement]
        names = []
        for item in downloads:
            name = item["file"]
            path = local_file(root, name)
            if path.stat().st_size != item["size"] or digest(path) != item["sha256"]:
                raise ValueError("La descarga runtime cambió después de verificarse")
            files[name] = item["sha256"]
            names.append(name)
        components.append(
            {
                "kind": entry["kind"],
                "name": entry["name"],
                "version": entry["version"],
                "files": list(names),
            }
        )
    # Match exact manifests, rather than inferring coverage from a success count.
    expected = set()
    for manifest in ("bench-packages.json", "tools-packages.json"):
        for entry in read("manifests/" + manifest):
            if "editable_project_location" not in entry:
                expected.add((re.sub(r"[-_.]+", "-", entry["name"]).lower(), entry["version"]))
    actual = {
        (re.sub(r"[-_.]+", "-", e["name"]).lower(), e["version"])
        for e in components
        if e["kind"] == "python"
    }
    if actual != expected:
        raise ValueError("La cobertura no coincide con los entornos de la imagen")
    return files, components


def build(root, destination, *, part_bytes=1500 * 1024 * 1024):
    files, components = collect(root)
    destination.mkdir(parents=True, exist_ok=False)
    parts = []
    archive = None
    size = 0
    try:
        for name in sorted(files):
            path = local_file(root, name)
            if path.stat().st_size > part_bytes:
                raise ValueError("Una fuente supera el tamaño admitido de cada parte")
            if archive is None or size + path.stat().st_size > part_bytes:
                if archive:
                    archive.close()
                target = destination / f"Sources-{len(parts) + 1:02d}.zip"
                archive = ZipFile(target, "x", ZIP_STORED, allowZip64=True)
                parts.append(target)
                size = 0
            archive.write(path, name)
            size += path.stat().st_size
    finally:
        if archive:
            archive.close()
    catalog = {
        "schema": 1,
        "components": components,
        "files": files,
        "limits": [
            "barcodenumber 0.5.0: fuente Python y GPL3 del wheel publicado; COPYRIGHT referido no incluido por upstream; repositorio oficial no disponible.",
            "No se afirma revisión legal externa ni validación OpenPGP de recuperaciones Launchpad.",
        ],
    }
    (destination / "sources.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
    )
    (destination / "LEEME.txt").write_text(
        "Fuentes de las dependencias de la imagen OpenMultiPOS. Cada ZIP se extrae por separado en la misma carpeta. No contiene registros del recolector ni configuraciones del negocio. Los archivos se distribuyen con sus licencias originales. Los cuatro proyectos editables completos y sus scripts están en la imagen; source.zip acompaña el programa Windows. Consulte sources.json para versiones, hashes y límites conocidos. Los fuentes Ubuntu incluyen dsc, originales y cambios de Debian; use dpkg-source -x para reconstruirlos. Python conserva sdists y el wheel Python de barcodenumber; no se ejecutaron estas fuentes al empaquetar.\n"
    )
    paths = [*parts, destination / "sources.json", destination / "LEEME.txt"]
    (destination / "SHA256SUMS.txt").write_text(
        "\n".join(digest(p) + "  " + p.name for p in paths) + "\n"
    )
    print(json.dumps({"components": len(components), "files": len(files), "parts": len(parts)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.sources.resolve(), args.output.resolve())
