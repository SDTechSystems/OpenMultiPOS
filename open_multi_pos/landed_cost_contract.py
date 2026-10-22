"""Strict, Frappe-free input contract for native landed costs."""

import re
from decimal import Decimal

from open_multi_pos import checkout_contract as wire


def selection(data):
    data = wire.mapping(data, ("brand", "receipts", "charges", "basis"))
    if data["basis"] not in ("Amount", "Qty"):
        raise ValueError("Distribuya por importe o cantidad")
    receipts = data["receipts"]
    charges = data["charges"]
    if not isinstance(receipts, list) or not 1 <= len(receipts) <= 10:
        raise ValueError("Seleccione entre 1 y 10 documentos")
    if not isinstance(charges, list) or not 1 <= len(charges) <= 20:
        raise ValueError("Ingrese entre 1 y 20 costos")
    sources = []
    for row in receipts:
        row = wire.mapping(row, ("doctype", "name"))
        if row["doctype"] not in ("Purchase Receipt", "Purchase Invoice"):
            raise ValueError("Documento de compra no admitido")
        sources.append({"doctype": row["doctype"], "name": wire.identifier(row["name"])})
    if len({(r["doctype"], r["name"]) for r in sources}) != len(sources):
        raise ValueError("No repita una recepción")
    costs = []
    for row in charges:
        row = wire.mapping(row, ("account", "currency", "amount", "exchange_rate", "description"))
        rate = row["exchange_rate"]
        if not isinstance(rate, str) or not re.fullmatch(r"[0-9]{1,9}(\.[0-9]{1,9})?", rate):
            raise ValueError("Tasa explícita inválida (máximo 9 decimales)")
        if Decimal(rate) <= 0:
            raise ValueError("La tasa debe ser positiva")
        costs.append(
            {
                "account": wire.identifier(row["account"]),
                "currency": wire.identifier(row["currency"]),
                "description": wire.identifier(wire.identifier(row["description"]).strip()),
                "amount": str(wire.amount(row["amount"]).quantize(Decimal(".01"))),
                "exchange_rate": str(Decimal(rate).normalize()),
            }
        )
    return {
        "brand": wire.identifier(data["brand"]),
        "basis": data["basis"],
        "receipts": sorted(sources, key=lambda r: (r["doctype"], r["name"])),
        "charges": costs,
    }
