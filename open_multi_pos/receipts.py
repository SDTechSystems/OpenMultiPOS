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
    return f"$ {grouped},{fraction:02d}"


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
        f"<p>{escape(p['label'])}: {money(p['amount'])}</p>" for p in receipt["payments"]
    )
    local_time = datetime.fromisoformat(receipt["created_at"]).astimezone(
        ZoneInfo("America/Bogota")
    )
    qr, modules = qr_image(brand["qr_url"])
    module_dots = max(3, min(6, int(profile.dots * 0.7 / modules)))
    qr_mm = modules * module_dots / profile.dpi * 25.4
    return f'''<!doctype html><html lang="es-CO"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Recibo interno demo</title>
<style>
@page {{ size: {profile.paper_mm}mm auto; margin: 0; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; color:#111; background:#fff; font:600 14px/1.4 Arial,sans-serif; }}
article {{ width:{profile.printable_mm}mm; margin:3mm auto; overflow-wrap:anywhere; }}
header,footer {{ text-align:center; }} h1 {{ font-size:18px; margin:4px 0; }}
p {{ margin:4px 0; }} .symbol {{ font-size:26px; font-weight:bold; }}
.badge {{ border:1px solid #111; padding:4px; font-size:11px; }}
table {{ width:100%; border-collapse:collapse; margin:12px 0; }}
th {{ text-align:left; border-bottom:1px dashed #111; }}
td {{ padding:5px 0; vertical-align:top; }} td:last-child,th:last-child {{ text-align:right; }}
.total {{ border-top:1px dashed #111; padding-top:8px; font-size:17px; font-weight:bold; }}
img {{ width:{qr_mm:.6f}mm; height:{qr_mm:.6f}mm; image-rendering:pixelated; }}
small {{ font-size:11px; }} footer {{ margin-top:12px; padding-bottom:8mm; }}
</style></head><body><article aria-label="Recibo interno de demostración">
<header><div class="symbol" aria-label="Símbolo de marca demo">{escape(brand["symbol"])}</div>
<h1>{escape(brand["name"])}</h1><p>{escape(brand["subtitle"])}</p>
<p class="badge">DEMOSTRACIÓN · RECIBO INTERNO<br>SIN VALIDEZ FISCAL</p></header>
<p>Operación {escape(receipt["id"])}</p><p>{local_time:%d/%m/%Y %H:%M} · America/Bogota</p>
<p>Cajero: {escape(receipt["cashier"])}</p><p>Almacén: {escape(brand["warehouse"])}</p>
<table><thead><tr><th scope="col">Artículo</th><th scope="col">COP</th></tr></thead><tbody>{rows}</tbody></table>
<p class="total">Total {money(receipt["total"])} COP</p>
<p>Demo sin impuestos. Valores ficticios.</p>{payments}<p>Cambio: {money(receipt["change"])}</p>
<footer><p>{escape(brand["footer"])}</p><img src="{qr}" alt="QR comercial de demostración">
<p><small>{escape(brand["qr_url"])}</small></p><p><small>Perfil: {escape(profile.id)} · plantilla v1</small></p>
</footer></article></body></html>'''
