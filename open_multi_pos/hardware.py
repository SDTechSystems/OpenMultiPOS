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
    page_mm: int | None = None
    margin_mm: int = 2
    cut: str = "none"
    native_qr: bool = False
    physically_verified: bool = False

    def __post_init__(self):
        if not 30 <= self.printable_mm <= self.paper_mm <= 120:
            raise ValueError("Ancho de impresión inválido")
        if not 200 <= self.dots <= 1200 or not 100 <= self.dpi <= 600:
            raise ValueError("Resolución inválida")
        if not 30 <= self.driver_page_mm <= self.paper_mm:
            raise ValueError("Ancho lógico de controlador inválido")
        if not 0 <= self.margin_mm <= 5 or self.content_mm < 26:
            raise ValueError("Margen de impresión inválido")
        if self.cut not in ("none", "manual", "automatic"):
            raise ValueError("Tipo de corte inválido")

    @property
    def driver_page_mm(self) -> int:
        return self.paper_mm if self.page_mm is None else self.page_mm

    @property
    def content_mm(self) -> int:
        return min(self.printable_mm, self.driver_page_mm - 2 * self.margin_mm)


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
