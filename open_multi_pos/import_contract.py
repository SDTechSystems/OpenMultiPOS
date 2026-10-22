"""Bounded CSV contract; business validation happens on the server."""

import csv
import io
import re
from decimal import Decimal

COLUMNS = ("accion", "sku", "nombre", "codigo_barras", "grupo", "precio", "cantidad", "costo")
MAX_ROWS = 100
MAX_BYTES = 256 * 1024


def amount(value, *, required=False):
    if not value:
        if required:
            raise ValueError("Complete el importe obligatorio")
        return ""
    value = value.replace(",", ".")
    if not re.fullmatch(r"[0-9]{1,9}(\.[0-9]{1,2})?", value) or Decimal(value) <= 0:
        raise ValueError(
            "Use un importe positivo con hasta dos decimales, sin separadores de miles"
        )
    return str(Decimal(value).quantize(Decimal(".01")))


def parse(text):
    if (
        not isinstance(text, str)
        or not text.strip()
        or len(text.encode("utf-8")) > MAX_BYTES
        or "\x00" in text
    ):
        raise ValueError("Seleccione un CSV UTF-8 de hasta 256 KiB")
    text = text.lstrip("\ufeff")
    try:
        delimiter = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;\t").delimiter
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
        headers = [h.strip().lower() for h in next(reader)]
        if len(headers) != len(COLUMNS) or set(headers) != set(COLUMNS):
            raise ValueError("Las columnas deben ser: " + ", ".join(COLUMNS))
        rows, errors = [], []
        count = 0
        for values in reader:
            if not any(v.strip() for v in values):
                continue
            count += 1
            if count > MAX_ROWS:
                raise ValueError("Divida el archivo en grupos de hasta 100 filas")
            line = reader.line_num
            try:
                if len(values) != len(headers):
                    raise ValueError("La cantidad de columnas no coincide con la cabecera")
                data = dict(zip(headers, (v.strip() for v in values), strict=True))
                if any(len(v) > 140 or any(ord(c) < 32 for c in v) for v in data.values()):
                    raise ValueError("Use campos de hasta 140 caracteres, sin saltos ni controles")
                if any(v.startswith(("=", "+", "@")) for v in data.values()):
                    raise ValueError("Escriba valores, sin fórmulas de hoja de cálculo")
                action = data["accion"].lower()
                if action not in ("crear", "actualizar", "ingresar"):
                    raise ValueError("Acción admitida: crear, actualizar o ingresar")
                if action != "crear" and not data["sku"]:
                    raise ValueError("El SKU es obligatorio para actualizar o ingresar unidades")
                if action == "crear" and (not data["nombre"] or not data["grupo"]):
                    raise ValueError("Nombre y grupo son obligatorios al crear")
                if not re.fullmatch(r"[0-9]{1,5}", data["cantidad"] or "0"):
                    raise ValueError("Cantidad debe ser un entero entre 0 y 10000")
                qty = int(data["cantidad"] or "0")
                if qty > 10000:
                    raise ValueError("Cantidad debe ser un entero entre 0 y 10000")
                if action == "ingresar" and (
                    qty == 0 or any(data[k] for k in ("nombre", "grupo", "codigo_barras", "precio"))
                ):
                    raise ValueError(
                        "Ingresar solo usa SKU, cantidad y costo; deje los campos de catálogo vacíos"
                    )
                price = amount(data["precio"], required=action == "crear")
                cost = amount(data["costo"], required=qty > 0)
                if not qty and cost:
                    raise ValueError("Deje costo vacío cuando no ingresará unidades")
                rows.append(
                    {
                        **data,
                        "accion": action,
                        "precio": price,
                        "cantidad": qty,
                        "costo": cost,
                        "line": line,
                    }
                )
            except ValueError as exc:
                errors.append({"line": line, "message": str(exc)})
        if not count:
            raise ValueError("Agregue al menos una fila de productos")
        return rows, errors
    except (csv.Error, StopIteration) as exc:
        raise ValueError("No se pudo leer el CSV. Revise comillas, separador y cabecera") from exc
