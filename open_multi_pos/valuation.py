"""Read native gross profit only after the company's repost queues are clear."""

from datetime import date
from decimal import Decimal

import frappe
from frappe.desk.query_report import get_report_doc, run
from frappe.utils import fmt_money, get_system_timezone, now_datetime

from open_multi_pos.checkout import contract_errors
from open_multi_pos.checkout_contract import identifier
from open_multi_pos.workspace import brand_context


@frappe.whitelist(methods=["POST"])
@contract_errors
def review(brand, from_date, to_date):
    observed_at = str(now_datetime())
    ctx = brand_context(identifier(brand))
    if not isinstance(from_date, str) or not isinstance(to_date, str):
        raise ValueError("Seleccione las fechas del informe")
    start, end = date.fromisoformat(from_date), date.fromisoformat(to_date)
    if (
        start.isoformat() != from_date
        or end.isoformat() != to_date
        or not 0 <= (end - start).days <= 366
    ):
        raise ValueError("Use un intervalo válido de hasta un año")
    report_doc = get_report_doc("Gross Profit")  # Native report roles and report permission.
    result = {
        "company": ctx["company"],
        "warehouse": ctx["warehouse"],
        "from_date": from_date,
        "to_date": to_date,
        "observed_at": observed_at,
        "time_zone": get_system_timezone(),
        "currency": frappe.db.get_value("Company", ctx["company"], "default_currency"),
        "jobs": [],
        "rows": [],
    }
    for doctype, completed in (
        ("Repost Item Valuation", ["Completed", "Skipped"]),
        ("Repost Accounting Ledger", ["Completed"]),
    ):
        jobs = frappe.get_list(
            doctype,
            filters={"docstatus": 1, "status": ["not in", completed]},
            or_filters=[
                ["company", "=", ctx["company"]],
                *([["company", "is", "not set"]] if doctype == "Repost Accounting Ledger" else []),
            ],
            fields=["name", "status"],
            order_by="creation asc",
            limit_page_length=51,
        )
        result["jobs"].extend({"doctype": doctype, **job} for job in jobs[:50])
        if len(jobs) > 50:
            result["more_jobs"] = True
    if result["jobs"]:
        return {**result, "status": "pending"}
    if report_doc.snapshot_report:
        return {**result, "status": "snapshot"}
    report = run(
        "Gross Profit",
        filters={
            "company": ctx["company"],
            "warehouse": ctx["warehouse"],
            "from_date": from_date,
            "to_date": to_date,
            "group_by": "Item Code",
        },
        ignore_prepared_report=True,
    )
    if report.get("snapshot_report"):
        return {**result, "status": "snapshot"}
    amounts = {"sales": "selling_amount", "cost": "buying_amount", "margin": "gross_profit"}
    for row in report["result"]:
        values = {key: str(Decimal(str(row.get(field) or 0))) for key, field in amounts.items()}
        result["rows"].append(
            {
                "item_code": row.get("item_code") or "",
                "item_name": row.get("item_name") or "",
                "qty": "" if row.get("qty") is None else str(Decimal(str(row["qty"]))),
                "amounts": values,
                "formatted": {
                    key: fmt_money(value, currency=result["currency"])
                    for key, value in values.items()
                },
                "percent": str(Decimal(str(row.get("gross_profit_%") or 0))),
            }
        )
    return {**result, "status": "current"}
