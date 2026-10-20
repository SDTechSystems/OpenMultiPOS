"""Escaped, immutable receipt snapshots; never an electronic fiscal invoice."""

import base64
from datetime import datetime
from html import escape
from io import BytesIO
from zoneinfo import ZoneInfo

import qrcode
import qrcode.image.svg

from open_multi_pos.hardware import PrinterProfile, printer_profiles
from open_multi_pos.validation import safe_qr_url


def money(amount: int) -> str:
    sign = "-" if amount < 0 else ""
    whole, fraction = divmod(abs(amount), 100)
    grouped = f"{whole:,}".replace(",", ".")
    return f"{sign}$ {grouped}" + (f",{fraction:02d}" if fraction else "")


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


def render_receipt(receipt: dict, profile: PrinterProfile, *, native: bool = False) -> str:
    brand = receipt["brand"]
    currency = escape(receipt.get("currency", "COP"))
    rows = "".join(
        f"<tr><td>{escape(line['name'])}<br><small>{line['qty']} × {money(line['rate'])}</small>"
        f"</td><td>{money(line['amount'])}</td></tr>"
        for line in receipt["items"]
    )
    payments = "".join(
        f"<p>{escape(p['mode_of_payment'] if native else p['label'].replace('(registro demo)', '').strip())}: {money(p['amount'])}</p>"
        for p in receipt["payments"]
        if p["amount"] > 0
    )
    local_time = datetime.fromisoformat(receipt["created_at"]).astimezone(
        ZoneInfo(receipt.get("time_zone", "America/Bogota"))
    )
    qr, modules = qr_image(brand["qr_url"])
    module_dots = max(3, min(4, int(profile.content_mm / 25.4 * profile.dpi * 0.55 / modules)))
    qr_mm = modules * module_dots / profile.dpi * 25.4
    change = f"<p>Cambio: {money(receipt['change'])}</p>" if receipt["change"] else ""
    title = "Recibo interno" if native else "Recibo interno demo"
    badge = "RECIBO INTERNO" if native else "DEMO · RECIBO INTERNO"
    label = "Recibo interno guardado" if native else "Recibo interno de demostración"
    qr_label = "QR comercial" if native else "QR comercial de demostración"
    script = "/assets/open_multi_pos/receipt-print.js" if native else "/receipt-print.js"
    taxes = f"<p>Impuestos: {money(receipt['taxes'])}</p>" if native else ""
    return f'''<!doctype html><html lang="es-CO"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<script src="{script}" defer></script>
<style>
@page {{ size: {profile.driver_page_mm}mm 150mm; margin: 0; }}
* {{ box-sizing: border-box; }}
html {{ width:{profile.driver_page_mm}mm; margin:0 auto; }}
body {{ width:100%; margin:0; color:#000; background:#fff; font:600 12px/1.25 Arial,sans-serif; }}
article {{ width:{profile.content_mm}mm; margin:0 auto; padding:2mm 0; overflow-wrap:anywhere; }}
header,footer {{ text-align:center; }} h1 {{ font-size:17px; margin:0 0 2px; }}
p {{ margin:2px 0; }} .meta {{ font-size:11px; text-align:center; }}
.badge {{ font-size:10px; margin-bottom:5px; }}
table {{ width:100%; table-layout:fixed; border-collapse:collapse; margin:6px 0; }}
th:first-child {{ width:65%; }}
th {{ text-align:left; border-bottom:1px dashed #000; font-size:11px; }}
td {{ padding:3px 0; vertical-align:top; }} td:last-child,th:last-child {{ text-align:right; overflow-wrap:anywhere; }}
.total {{ border-top:1px dashed #000; padding-top:4px; font-size:16px; font-weight:bold; }}
img {{ display:block; margin:3px auto 0; width:{qr_mm:.6f}mm; height:{qr_mm:.6f}mm; image-rendering:pixelated; }}
small {{ font-size:11px; }} footer {{ margin-top:5px; padding-bottom:2mm; }}
tr, footer {{ break-inside:avoid; }}
</style></head><body data-paper-mm="{profile.driver_page_mm}" data-printable-mm="{profile.printable_mm}" data-margin-mm="{profile.margin_mm}" data-dots="{profile.dots}" data-dpi="{profile.dpi}"><article aria-label="{label}">
<header><h1>{escape(brand["name"])}</h1>
<p class="badge">{badge}<br>SIN VALIDEZ FISCAL</p></header>
<p class="meta">{escape(receipt["id"])}<br>{local_time:%d/%m/%Y %H:%M} · {currency}</p>
<table><thead><tr><th scope="col">Artículo</th><th scope="col">{currency}</th></tr></thead><tbody>{rows}</tbody></table>
{taxes}<p class="total">Total {money(receipt["total"])}</p>{payments}{change}
<footer><small>{escape(brand["footer"])}</small><img src="{qr}" alt="{qr_label}"></footer>
</article></body></html>'''


def render_compact_receipt(receipt: dict) -> str:
    """Current 48 mm Windows page, short top margin, no browser headers."""
    profile = printer_profiles()["jaltech-jal58m"]
    sections = []
    for part in receipt["sales"]:
        brand = part["brand"]
        details = brand.get("receipt_details", {})
        contact = []
        for field in ("legal_name", "tax_id", "phone", "email", "address"):
            if details.get("receipt_show_" + field) and details.get(field):
                value = ("NIT " if field == "tax_id" else "") + str(details[field])
                contact.append("<p>" + escape(value) + "</p>")
        lines = "".join(
            "<tr><td>"
            + escape(row["name"])
            + "<small>"
            + str(int(row["qty"]))
            + " × "
            + money(row["rate"])
            + "</small></td><td>"
            + money(row["amount"])
            + "</td></tr>"
            for row in part["items"]
        )
        payments = []
        for pay in part["payments"]:
            label = {"Cash": "Efectivo", "Bank": "Transferencia"}.get(
                pay.get("kind"), pay.get("mode_of_payment", "Pago")
            )
            if pay["amount"]:
                payments.append(escape(label) + " " + money(pay["amount"]))
        qr = ""
        if details.get("receipt_show_qr", 1) and brand.get("qr_url"):
            data, _ = qr_image(brand["qr_url"])
            qr = '<img src="' + data + '" alt="QR del negocio">'
        footer = (
            "<p>" + escape(brand.get("footer", "")) + "</p>"
            if details.get("receipt_show_footer", 1) and brand.get("footer")
            else ""
        )
        taxes = "<p>Impuestos " + money(part.get("taxes", 0)) + "</p>" if part.get("taxes") else ""
        subtotal = (
            '<p class="subtotal">Subtotal ' + money(part["total"]) + "</p>"
            if len(receipt["sales"]) > 1
            else ""
        )
        sections.append(
            "<section><h2>"
            + escape(brand["name"])
            + '</h2><div class="details">'
            + "".join(contact)
            + '</div><p class="reference">'
            + escape(part["id"])
            + "</p><table><thead><tr><th>Producto</th><th>Importe</th></tr></thead><tbody>"
            + lines
            + "</tbody></table>"
            + taxes
            + subtotal
            + '<p class="payments">'
            + " / ".join(payments)
            + "</p>"
            + footer
            + qr
            + "</section>"
        )
    when = datetime.fromisoformat(receipt["sales"][0]["created_at"]).astimezone(
        ZoneInfo(receipt["sales"][0].get("time_zone", "America/Bogota"))
    )
    change = "<p>Cambio " + money(receipt["change"]) + "</p>" if receipt.get("change") else ""
    currency = escape(receipt["currency"])
    return f"""<!doctype html><html lang="es-CO"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Recibo interno</title><script src="/assets/open_multi_pos/receipt-print.js" defer></script><style>
@page {{size:48mm 150mm;margin:0}}*{{box-sizing:border-box}}html{{width:48mm;margin:0 auto}}body{{margin:0;color:#000;background:#fff;font:600 12px/1.17 Arial,sans-serif}}article{{width:{profile.content_mm}mm;margin:0 auto;padding:.5mm 0 1mm;overflow-wrap:anywhere}}header,h2,.details{{text-align:center}}header{{font-size:9px;margin-bottom:1.2mm}}h2{{font-size:15px;margin:0 0 .5mm}}p{{margin:.5mm 0}}.reference,.details,.payments{{font-size:10px}}table{{width:100%;table-layout:fixed;border-collapse:collapse}}th{{font-size:10px;text-align:left;border-bottom:1px dashed}}th:first-child{{width:66%}}td{{padding:.7mm 0;vertical-align:top}}th:last-child,td:last-child{{text-align:right}}small{{display:block;font-size:10px}}section{{padding:0 0 1mm;margin:0 0 1mm;border-bottom:1px dashed}}.total{{font-size:16px;margin-top:1mm}}.subtotal{{font-size:12px;font-weight:700}}img{{display:block;width:23mm;height:23mm;margin:1mm auto 0}}tr{{break-inside:avoid}}h2{{break-after:avoid}}</style></head><body data-paper-mm="48"><article aria-label="Recibo interno guardado"><header>RECIBO INTERNO SIN VALIDEZ FISCAL<br>{when:%d/%m/%Y %H:%M} {currency}</header>{"".join(sections)}<p class="total">Total {money(receipt["total"])} {currency}</p>{change}</article></body></html>"""
