"""SQLite demo only: no real invoices, tax engine, payment confirmation or ERP ledger."""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from open_multi_pos.validation import cents, require_brand_access

BRANDS = [
    {
        "id": "atelier",
        "name": "Taller Aurora",
        "subtitle": "Artesanía · perfil ficticio",
        "symbol": "A",
        "warehouse": "Demo Artesanía",
        "company": "Entidad Demo",
        "color": "#255e48",
        "footer": "Gracias por apoyar lo hecho a mano",
        "qr_url": "https://example.com/atelier",
    },
    {
        "id": "tech",
        "name": "Nexo Digital",
        "subtitle": "Tecnología · perfil ficticio",
        "symbol": "N",
        "warehouse": "Demo Tecnología",
        "company": "Entidad Demo",
        "color": "#254d88",
        "footer": "Gracias por tu visita",
        "qr_url": "https://example.com/tech",
    },
]
USERS = {
    "owner": {"name": "Administrador demo", "brands": ["atelier", "tech"]},
    "cashier": {"name": "Cajero artesanía demo", "brands": ["atelier"]},
}
PRODUCTS = [
    ("atelier", "VEL-01", "Vela botánica", "7700000000011", 2800000, 15, "Velas"),
    ("atelier", "JAB-01", "Jabón de hierbas", "7700000000028", 1400000, 24, "Cuidado"),
    ("atelier", "INC-01", "Incienso de sándalo", "7700000000035", 1000000, 30, "Aromas"),
    ("atelier", "VEL-02", "Vela de lavanda", "7700000000042", 3200000, 8, "Velas"),
    ("tech", "MOU-01", "Mouse inalámbrico", "7700000000059", 4500000, 10, "Accesorios"),
    ("tech", "USB-01", "Cable USB-C", "7700000000066", 1800000, 20, "Conectividad"),
    ("tech", "CAR-01", "Cargador compacto", "7700000000073", 6500000, 7, "Energía"),
    ("tech", "HUB-01", "Hub de cuatro puertos", "7700000000080", 7900000, 5, "Conectividad"),
]


class ConflictError(ValueError):
    pass


class DemoStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS brands (id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS products (
                    brand TEXT, sku TEXT, name TEXT, barcode TEXT, price INTEGER,
                    stock INTEGER CHECK(stock >= 0), category TEXT, PRIMARY KEY(brand, sku));
                CREATE TABLE IF NOT EXISTS sales (
                    id TEXT PRIMARY KEY, user TEXT, terminal TEXT, transaction_id TEXT,
                    fingerprint TEXT, brand TEXT, snapshot TEXT,
                    UNIQUE(user, terminal, transaction_id));
            """)
            for brand in BRANDS:
                db.execute(
                    "INSERT OR IGNORE INTO brands VALUES (?,?)", (brand["id"], json.dumps(brand))
                )
            db.executemany("INSERT OR IGNORE INTO products VALUES (?,?,?,?,?,?,?)", PRODUCTS)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def allowed(self, user: str) -> list[str]:
        if user not in USERS:
            raise PermissionError("Usuario demo desconocido")
        return USERS[user]["brands"]

    def catalog(self, user: str, brand: str) -> list[dict]:
        require_brand_access(brand, self.allowed(user))
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute("SELECT * FROM products WHERE brand=? ORDER BY sku", (brand,))
            ]

    def context(self, user: str) -> dict:
        allowed = self.allowed(user)
        with self.connect() as db:
            placeholders = ",".join("?" for _ in allowed)
            brands = [
                json.loads(r[0])
                for r in db.execute(
                    f"SELECT data FROM brands WHERE id IN ({placeholders})", allowed
                )
            ]
        return {"brands": brands, "user": USERS[user]["name"], "mode": "demo", "currency": "COP"}

    def checkout(self, user: str, data: dict) -> dict:
        if not isinstance(data, dict):
            raise ValueError("Se esperaba un objeto")
        brand = data.get("brand")
        require_brand_access(brand, self.allowed(user))  # Always before deduplication.
        try:
            transaction_id = str(UUID(data["transaction_id"]))
            terminal = str(UUID(data["terminal"]))
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ValueError("Terminal y transacción requieren UUID válidos") from exc
        items = data.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 100:
            raise ValueError("El carrito debe contener entre 1 y 100 líneas")
        normalized = []
        seen = set()
        for line in items:
            if not isinstance(line, dict):
                raise ValueError("Línea inválida")
            sku, qty = line.get("sku"), line.get("qty")
            if (
                not isinstance(sku, str)
                or sku in seen
                or type(qty) is not int
                or not 1 <= qty <= 999
            ):
                raise ValueError("SKU único y cantidad entera entre 1 y 999 requeridos")
            seen.add(sku)
            normalized.append({"sku": sku, "qty": qty})
        normalized.sort(key=lambda line: line["sku"])
        cash = cents(data.get("cash", "0"))
        transfer = cents(data.get("transfer", "0"))
        payload = {"brand": brand, "items": normalized, "cash": cash, "transfer": transfer}
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT fingerprint, snapshot FROM sales WHERE user=? AND terminal=? AND transaction_id=?",
                (user, terminal, transaction_id),
            ).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise ConflictError("La clave de transacción ya se usó con otros datos")
                return {"receipt": json.loads(previous["snapshot"]), "duplicate": True}
            lines = []
            for item in normalized:
                row = db.execute(
                    "SELECT * FROM products WHERE brand=? AND sku=?", (brand, item["sku"])
                ).fetchone()
                if not row:
                    raise ValueError("Producto no pertenece al negocio")
                if row["stock"] < item["qty"]:
                    raise ConflictError(f"Stock insuficiente: {row['name']}")
                lines.append(
                    {
                        "sku": row["sku"],
                        "name": row["name"],
                        "qty": item["qty"],
                        "rate": row["price"],
                        "amount": row["price"] * item["qty"],
                    }
                )
            total = sum(line["amount"] for line in lines)
            if transfer > total or cash + transfer < total:
                raise ValueError("Pago insuficiente o transferencia superior al total")
            snapshot = {
                "id": f"DEMO-{uuid4().hex[:12].upper()}",
                "brand": json.loads(
                    db.execute("SELECT data FROM brands WHERE id=?", (brand,)).fetchone()[0]
                ),
                "created_at": datetime.now(UTC).isoformat(),
                "cashier": USERS[user]["name"],
                "items": lines,
                "total": total,
                "payments": [
                    {"label": "Efectivo", "amount": cash},
                    {"label": "Transferencia (registro demo)", "amount": transfer},
                ],
                "change": cash + transfer - total,
                "fiscal_status": "not_configured",
            }
            for line in lines:
                db.execute(
                    "UPDATE products SET stock=stock-? WHERE brand=? AND sku=?",
                    (line["qty"], brand, line["sku"]),
                )
            db.execute(
                "INSERT INTO sales VALUES (?,?,?,?,?,?,?)",
                (
                    snapshot["id"],
                    user,
                    terminal,
                    transaction_id,
                    fingerprint,
                    brand,
                    json.dumps(snapshot),
                ),
            )
            return {"receipt": snapshot, "duplicate": False}

    def receipt(self, user: str, sale_id: str) -> dict:
        self.allowed(user)
        with self.connect() as db:
            row = db.execute("SELECT brand, snapshot FROM sales WHERE id=?", (sale_id,)).fetchone()
            if not row:
                raise ValueError("Recibo no encontrado")
            require_brand_access(row["brand"], self.allowed(user))
            return json.loads(row["snapshot"])
