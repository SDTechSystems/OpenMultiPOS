"""Reviewed HTTP routing policy for the commits in upstream.lock.json."""

INVOICE_DOCTYPES = ("Sales Invoice", "POS Invoice")
INVOICE_API_PREFIX = "xpos.api.invoices."
# These routes require a reviewed native checkout/return/listing contract before
# exposure. No setting or caller-supplied argument can bypass this temporary gate.
BLOCKED_INVOICE_METHODS = (
    "create_invoice",
    "save_draft_invoice",
    "discard_draft_invoice",
    "delete_draft_invoice",
    "finalize_fiscal_invoice",
    "get_draft_invoices",
    "get_unsettled_invoices",
    "get_past_orders",
    "get_invoices",
    "search_invoices_for_return",
    "get_invoice_for_return",
    "get_last_invoice_rates",
    "search_invoices_for_repeat",
    "get_invoice_for_repeat",
)


METHOD_OVERRIDES = {
    "xpos.api.print_formats.get_receipt_context": "open_multi_pos.xpos_security.get_receipt_context",
    "xpos.api.print_formats.mark_invoice_printed": "open_multi_pos.xpos_security.mark_invoice_printed",
    "xpos.api.invoices.get_invoice_details": "open_multi_pos.xpos_security.get_invoice_details",
    **{
        INVOICE_API_PREFIX + name: "open_multi_pos.xpos_security.unavailable_invoice_operation"
        for name in BLOCKED_INVOICE_METHODS
    },
}
