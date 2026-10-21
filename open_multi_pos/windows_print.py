"""Explicit local ESC/POS raster diagnostics through an existing Windows queue.

No network service, automatic retry, driver installation, cutter or cash drawer.
The legacy GS v 0 command must be tested for each printer/firmware.
"""

import argparse
import ctypes
import json
import sys
from ctypes import wintypes
from pathlib import Path


def parse_pbm(data: bytes) -> tuple[int, int, bytes]:
    """Accept our bounded binary P4 raster format, never arbitrary printer commands."""
    header, separator, raster = data.partition(b"\n")
    if header != b"P4" or not separator:
        raise ValueError("Se requiere PBM P4 binario")
    dimensions, separator, raster = raster.partition(b"\n")
    try:
        width, height = (int(value) for value in dimensions.split())
    except (ValueError, TypeError) as exc:
        raise ValueError("Dimensiones PBM inválidas") from exc
    if not separator or not 8 <= width <= 1200 or width % 8 or not 1 <= height <= 30000:
        raise ValueError("Raster fuera de límites")
    if len(raster) != width // 8 * height:
        raise ValueError("Raster PBM truncado o con datos adicionales")
    return width, height, raster


def escpos_raster(data: bytes, max_dots: int, block_rows: int = 128) -> bytes:
    width, height, raster = parse_pbm(data)
    if width > max_dots or not 1 <= block_rows <= 128:
        raise ValueError("Raster excede ancho físico o tamaño de bloque permitido")
    stride = width // 8
    output = bytearray(b"\x1b@\x1ba\x00")  # Initialize and left-align the raster canvas.
    for start in range(0, height, block_rows):
        rows = min(block_rows, height - start)
        output.extend(b"\x1dv0\x00")
        output.extend(stride.to_bytes(2, "little"))
        output.extend(rows.to_bytes(2, "little"))
        output.extend(raster[start * stride : (start + rows) * stride])
    output.extend(b"\n")  # Small final feed only; never cut or open drawer.
    return bytes(output)


class DocInfo(ctypes.Structure):
    _fields_ = [
        ("name", wintypes.LPWSTR),
        ("output", wintypes.LPWSTR),
        ("datatype", wintypes.LPWSTR),
    ]


def submit_windows(printer: str, payload: bytes) -> int:
    """Return a spooler job ID, NOT proof of physical printing. Never retry automatically."""
    if sys.platform != "win32":
        raise OSError("Este adaptador requiere Windows")
    if not printer or printer.startswith("\\\\") or "\x00" in printer:
        raise ValueError("Se requiere una cola local explícita")
    spool = ctypes.WinDLL("winspool.drv", use_last_error=True)
    signatures = {
        "OpenPrinterW": (
            [wintypes.LPWSTR, ctypes.POINTER(wintypes.HANDLE), ctypes.c_void_p],
            wintypes.BOOL,
        ),
        "StartDocPrinterW": (
            [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(DocInfo)],
            wintypes.DWORD,
        ),
        "StartPagePrinter": ([wintypes.HANDLE], wintypes.BOOL),
        "WritePrinter": (
            [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)],
            wintypes.BOOL,
        ),
        "EndPagePrinter": ([wintypes.HANDLE], wintypes.BOOL),
        "EndDocPrinter": ([wintypes.HANDLE], wintypes.BOOL),
        "AbortPrinter": ([wintypes.HANDLE], wintypes.BOOL),
        "ClosePrinter": ([wintypes.HANDLE], wintypes.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        method = getattr(spool, name)
        method.argtypes = arguments
        method.restype = result

    def check(result):
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())
        return result

    handle = wintypes.HANDLE()
    check(spool.OpenPrinterW(printer, ctypes.byref(handle), None))
    started = False
    try:
        info = DocInfo("OpenMultiPOS - raster demo", None, "RAW")
        job = check(spool.StartDocPrinterW(handle, 1, ctypes.byref(info)))
        started = True
        check(spool.StartPagePrinter(handle))
        buffer = ctypes.create_string_buffer(payload)
        written = wintypes.DWORD()
        check(spool.WritePrinter(handle, buffer, len(payload), ctypes.byref(written)))
        if written.value != len(payload):
            raise OSError("Envío parcial; revisar la cola antes de reintentar")
        check(spool.EndPagePrinter(handle))
        check(spool.EndDocPrinter(handle))
        started = False
        return job
    finally:
        if started:
            spool.AbortPrinter(handle)
        spool.ClosePrinter(handle)


def main():
    parser = argparse.ArgumentParser(description="Diagnóstico ESC/POS local con raster ficticio")
    parser.add_argument("bitmap", type=Path)
    parser.add_argument("--printer", required=True)
    parser.add_argument("--max-dots", type=int, required=True)
    parser.add_argument("--raster-command", choices=["gs-v-0"], required=True)
    args = parser.parse_args()
    data = args.bitmap.read_bytes()
    width, height, _ = parse_pbm(data)
    job = submit_windows(args.printer, escpos_raster(data, args.max_dots))
    print(
        json.dumps(
            {
                "status": "submitted",
                "job_id": job,
                "width_dots": width,
                "height_dots": height,
                "physically_confirmed": False,
            }
        )
    )


if __name__ == "__main__":
    main()
