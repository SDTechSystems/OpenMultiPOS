import re
from decimal import Decimal
from urllib.parse import urlsplit


def cents(value: str) -> int:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,9}(\.[0-9]{1,2})?", value):
        raise ValueError("Importe inválido: use pesos con hasta dos decimales y punto decimal")
    return int(Decimal(value) * 100)


def safe_qr_url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 180 or any(ord(c) < 33 for c in value):
        raise ValueError("URL de QR inválida")
    try:
        url = urlsplit(value)
        valid = (
            url.scheme == "https"
            and bool(url.hostname)
            and not url.username
            and not url.password
            and url.port in (None, 443)
        )
    except ValueError as exc:
        raise ValueError("URL de QR inválida") from exc
    if not valid:
        raise ValueError("El QR comercial requiere una URL HTTPS sin credenciales")
    return value


def require_brand_access(brand: str, allowed: list[str]) -> None:
    if brand not in allowed:
        raise PermissionError("No tiene acceso a este negocio")
