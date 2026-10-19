"""Printer capabilities are independent of brand and sales persistence."""

import json
from dataclasses import asdict, dataclass
from importlib.resources import files
from typing import Protocol


@dataclass(frozen=True)
class PrinterProfile:
    id: str
    name: str
    paper_mm: int
    printable_mm: int
    dots: int
    dpi: int
    cut: str = "none"
    native_qr: bool = False
    physically_verified: bool = False

    def __post_init__(self):
        if not 30 <= self.printable_mm <= self.paper_mm <= 120:
            raise ValueError("Ancho de impresión inválido")
        if not 200 <= self.dots <= 1200 or not 100 <= self.dpi <= 600:
            raise ValueError("Resolución inválida")
        if self.cut not in ("none", "manual", "automatic"):
            raise ValueError("Tipo de corte inválido")


def printer_profiles() -> dict[str, PrinterProfile]:
    data = json.loads(files("open_multi_pos").joinpath("profiles/printers.json").read_text())
    return {row["id"]: PrinterProfile(**row) for row in data}


def profile_list() -> list[dict]:
    return [asdict(profile) for profile in printer_profiles().values()]


class PrinterAdapter(Protocol):
    def preview(self, receipt: dict, profile: PrinterProfile) -> str:
        """Render a snapshot without changing sales or claiming paper was printed."""
        ...


class BrowserPrinterAdapter:
    """Preview HTML for the browser/system driver, with no device commands."""

    def preview(self, receipt: dict, profile: PrinterProfile) -> str:
        from open_multi_pos.receipts import render_receipt

        return render_receipt(receipt, profile)
