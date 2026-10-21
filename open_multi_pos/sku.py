"""Deterministic SKU components; the native database allocates the final number."""

import re
import unicodedata


def ascii_words(value: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.findall(r"[A-Za-z0-9]+", plain)


def business_initials(name: str) -> str:
    words = [
        word
        for word in ascii_words(name)
        if word.lower() not in {"de", "del", "la", "las", "el", "los", "y"}
    ]
    prefix = "".join(
        word if word.isupper() and len(word) <= 3 else word[0] for word in words
    ).upper()[:8]
    return prefix if prefix and prefix[0].isalpha() else "N" + prefix[:7]


def validate_prefix(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z][A-Z0-9]{0,7}", value):
        raise ValueError(
            "El prefijo de SKU debe tener entre 1 y 8 letras o números, empezar por una letra y usar mayúsculas"
        )
    return value


def product_segment(name: str) -> str:
    return "-".join(ascii_words(name)).upper()[:24].rstrip("-") or "PRODUCTO"


def sku_code(prefix: str, name: str, number: str) -> str:
    return f"{validate_prefix(prefix)}-{product_segment(name)}-{number}"
