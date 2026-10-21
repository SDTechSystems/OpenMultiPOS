"""Strict wire contracts; ERPNext remains the authority for prices and taxes."""

import hashlib
import json
import re
from decimal import Decimal
from uuid import UUID


def mapping(value, required, optional=()):
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict) or set(value) - set(required) - set(optional):
        raise ValueError("Campos no admitidos")
    if set(required) - set(value):
        raise ValueError("Faltan campos obligatorios")
    return value


def identifier(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 140 or any(ord(c) < 32 for c in value):
        raise ValueError("Identificador inválido")
    return value


def request_uuid(value):
    value = identifier(value)
    parsed = UUID(value)
    if parsed.version != 4 or str(parsed) != value:
        raise ValueError("Se requiere un UUID v4 canónico")
    return value


def amount(value, *, zero=False):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,9}(\.[0-9]{1,2})?", value):
        raise ValueError("Importe decimal inválido")
    number = Decimal(value)
    if number < 0 or (not zero and number == 0):
        raise ValueError("El importe debe ser positivo")
    return number


def items(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 50:
        raise ValueError("Se requieren entre 1 y 50 artículos")
    result, seen = [], set()
    for row in value:
        row = mapping(row, ("item_code", "qty"))
        code = identifier(row["item_code"])
        qty = row["qty"]
        if type(qty) is not int or not 1 <= qty <= 10000 or code in seen:
            raise ValueError("Cantidad entera inválida o artículo repetido")
        result.append({"item_code": code, "qty": qty})
        seen.add(code)
    return sorted(result, key=lambda row: row["item_code"])


def payments(value, *, zero=False):
    if not isinstance(value, list) or not 1 <= len(value) <= 10:
        raise ValueError("Se requieren entre 1 y 10 medios de pago")
    result, seen = [], set()
    for row in value:
        row = mapping(row, ("mode_of_payment", "amount"), ("reference_no",))
        mode = identifier(row["mode_of_payment"])
        if mode in seen:
            raise ValueError("Medio de pago repetido")
        reference = row.get("reference_no", "")
        if reference:
            identifier(reference)
        elif not isinstance(reference, str):
            raise ValueError("Referencia inválida")
        result.append(
            {
                "mode_of_payment": mode,
                "amount": str(amount(row["amount"], zero=zero).quantize(Decimal(".01"))),
                "reference_no": reference,
            }
        )
        seen.add(mode)
    return sorted(result, key=lambda row: row["mode_of_payment"])


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def operation_key(terminal, request_id):
    return digest([identifier(terminal), request_uuid(request_id)])
