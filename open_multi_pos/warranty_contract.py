"""Strict, Frappe-free input contract for native warranty claims."""

import html
import re
from datetime import date

from open_multi_pos import checkout_contract as wire

# Native Warranty Claim statuses. Labels are shown by the workspace.
STATUSES = ("Open", "Work In Progress", "Closed", "Cancelled")


def text(value, *, maximum, required=False):
    if (
        not isinstance(value, str)
        or len(value) > maximum
        or any(ord(c) < 32 and c not in "\r\n\t" for c in value)
    ):
        raise ValueError("Texto inválido o demasiado largo")
    value = value.replace("\r", "").strip()
    if required and not value:
        raise ValueError("Complete los campos obligatorios")
    return value


def iso_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Fecha inválida (AAAA-MM-DD)")
    return date.fromisoformat(value).isoformat()


def creation(data):
    data = wire.mapping(
        data, ("brand", "invoice", "row", "request_id", "complaint", "complaint_date")
    )
    return {
        "brand": wire.identifier(data["brand"]),
        "invoice": wire.identifier(data["invoice"]),
        "row": wire.identifier(data["row"]),
        "request_id": wire.request_uuid(data["request_id"]),
        "complaint": text(data["complaint"], maximum=2000, required=True),
        "complaint_date": iso_date(data["complaint_date"]),
    }


def change(data):
    data = wire.mapping(
        data, ("brand", "claim", "modified", "status", "resolution_details", "note")
    )
    if data["status"] not in STATUSES:
        raise ValueError("Estado no admitido")
    result = {
        "brand": wire.identifier(data["brand"]),
        "claim": wire.identifier(data["claim"]),
        "modified": wire.identifier(data["modified"]),
        "status": data["status"],
        "resolution_details": text(data["resolution_details"], maximum=2000),
        "note": text(data["note"], maximum=1000),
    }
    if result["status"] == "Closed" and not result["resolution_details"]:
        raise ValueError("Describe la solución antes de cerrar la reclamación")
    return result


def to_html(value):
    # Native Text Editor fields store HTML; never pass user text through unescaped.
    return "<p>" + html.escape(value).replace("\n", "<br>") + "</p>" if value else ""


def from_html(value):
    value = re.sub(r"(?i)<br\s*/?>|</p>\s*<p[^>]*>", "\n", value or "")
    return html.unescape(re.sub(r"<[^>]*>", "", value)).strip()
