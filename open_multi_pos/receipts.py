"""Escaped, immutable receipt snapshots; never an electronic fiscal invoice."""

import base64
from datetime import datetime
from html import escape
from io import BytesIO
from zoneinfo import ZoneInfo

import qrcode
import qrcode.image.svg

from open_multi_pos.hardware import PrinterProfile
from open_multi_pos.validation import safe_qr_url


def money(amount: int) -> str:
    whole, fraction = divmod(amount, 100)
    grouped = f"{whole:,}".replace(",", ".")
    return f"$ {grouped}" + (f",{fraction:02d}" if fraction else "")


def qr_image(url: str) -> tuple[str, int]:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4, box_size=4)
    qr.add_data(safe_qr_url(url))
    qr.make(fit=True)
    image = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    output = BytesIO()
    image.save(output)
    svg = output.getvalue().replace(b"<svg ", b'<svg shape-rendering="crispEdges" ', 1)
    return "data:image/svg+xml;base64," + base64.b64encode(svg).decode("ascii"), len(
        qr.get_matrix()
    )


def qr_data_url(url: str) -> str:
    return qr_image(url)[0]


def render_receipt(receipt: dict, profile: PrinterProfile) -> str:
    brand = receipt["brand"]
    rows = "".join(
        f"<tr><td>{escape(line['name'])}<br><small>{line['qty']} × {money(line['rate'])}</small>"
        f"</td><td>{money(line['amount'])}</td></tr>"
        for line in receipt["items"]
    )
    payments = "".join(
        f"<p>{escape(p['label'].replace('(registro demo)', '').strip())}: {money(p['amount'])}</p>"
        for p in receipt["payments"]
        if p["amount"] > 0
    )
    local_time = datetime.fromisoformat(receipt["created_at"]).astimezone(
        ZoneInfo("America/Bogota")
    )
    qr, modules = qr_image(brand["qr_url"])
    module_dots = max(3, min(4, int(profile.dots * 0.55 / modules)))
    qr_mm = modules * module_dots / profile.dpi * 25.4
    change = f"<p>Cambio: {money(receipt['change'])}</p>" if receipt["change"] else ""
    return f'''<!doctype html><html lang="es-CO"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Recibo interno demo</title>
<script src="/receipt-print.js" defer></script>
<style>
@page {{ size: {profile.paper_mm}mm 150mm; margin: 0; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; color:#000; background:#fff; font:600 12px/1.25 Arial,sans-serif; }}
article {{ width:{profile.printable_mm}mm; margin:2mm auto; overflow-wrap:anywhere; }}
header,footer {{ text-align:center; }} h1 {{ font-size:17px; margin:0 0 2px; }}
p {{ margin:2px 0; }} .meta {{ font-size:11px; text-align:center; }}
.badge {{ font-size:10px; margin-bottom:5px; }}
table {{ width:100%; border-collapse:collapse; margin:6px 0; }}
th {{ text-align:left; border-bottom:1px dashed #000; font-size:11px; }}
td {{ padding:3px 0; vertical-align:top; }} td:last-child,th:last-child {{ text-align:right; white-space:nowrap; }}
.total {{ border-top:1px dashed #000; padding-top:4px; font-size:16px; font-weight:bold; }}
img {{ display:block; margin:3px auto 0; width:{qr_mm:.6f}mm; height:{qr_mm:.6f}mm; image-rendering:pixelated; }}
small {{ font-size:11px; }} footer {{ margin-top:5px; padding-bottom:2mm; }}
tr, footer {{ break-inside:avoid; }}
@media print {{ article {{ margin:2mm 0; }} }}
</style></head><body data-paper-mm="{profile.paper_mm}"><article aria-label="Recibo interno de demostración">
<header><h1>{escape(brand["name"])}</h1>
<p class="badge">DEMO · RECIBO INTERNO<br>SIN VALIDEZ FISCAL</p></header>
<p class="meta">{escape(receipt["id"])}<br>{local_time:%d/%m/%Y %H:%M} · COP</p>
<table><thead><tr><th scope="col">Artículo</th><th scope="col">COP</th></tr></thead><tbody>{rows}</tbody></table>
<p class="total">Total {money(receipt["total"])}</p>{payments}{change}
<footer><small>{escape(brand["footer"])}</small><img src="{qr}" alt="QR comercial de demostración"></footer>
</article></body></html>'''
