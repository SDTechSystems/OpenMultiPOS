"""No networking, issuance or fiscal identifiers are enabled."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class FiscalResult:
    status: str = "not_configured"
    issued: bool = False
    message: str = "Módulo fiscal desactivado; recibo interno únicamente"


class FiscalProvider(Protocol):
    def status(self) -> FiscalResult: ...


class DisabledFiscalProvider:
    def status(self) -> FiscalResult:
        return FiscalResult()
