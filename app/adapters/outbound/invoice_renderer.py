"""
Invoice Renderer
================

Renders InvoicePure domain models to HTML and PDF.

Architecture:
    This is an outbound adapter — it transforms domain models into
    presentation formats (HTML, PDF) using external tools (WeasyPrint).
    The core service delegates here; presentation and rendering logic
    stays out of the service layer.
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.finance.invoice import InvoicePure


# Status badge colors keyed by InvoiceStatus value
_STATUS_COLORS: dict[str, str] = {
    "draft": "#6b7280",
    "sent": "#3b82f6",
    "pending": "#f59e0b",
    "paid": "#10b981",
    "overdue": "#ef4444",
    "cancelled": "#9ca3af",
}


def render_invoice_html(invoice: InvoicePure) -> str:
    """
    Render an invoice to an HTML string suitable for WeasyPrint PDF conversion.

    All user-supplied text is HTML-escaped to prevent injection.

    Args:
        invoice: Invoice domain model

    Returns:
        Complete HTML document string
    """
    # Build line items table rows
    items_html = ""
    for item in invoice.items:
        items_html += f"""
            <tr>
                <td>{html.escape(item.description)}</td>
                <td class="text-right">{item.quantity:.2f}</td>
                <td class="text-right">${item.unit_price:.2f}</td>
                <td class="text-right">${item.amount:.2f}</td>
            </tr>
            """

    # Format dates
    invoice_date_str = invoice.invoice_date.strftime("%B %d, %Y")
    due_date_str = invoice.due_date.strftime("%B %d, %Y") if invoice.due_date else "N/A"

    # Invoice type label
    type_label = "INVOICE" if invoice.is_outgoing() else "BILL"
    direction_label = "Bill To:" if invoice.is_outgoing() else "From:"

    # Status badge color
    status_color = _STATUS_COLORS.get(invoice.status.value, "#6b7280")

    # Notes section (escaped)
    notes_html = ""
    if invoice.notes:
        escaped_notes = html.escape(invoice.notes)
        notes_html = (
            f"<div class='notes'>"
            f"<div class='notes-label'>Notes</div>"
            f"<div>{escaped_notes}</div>"
            f"</div>"
        )

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: 'Helvetica Neue', Arial, sans-serif;
            margin: 0;
            padding: 40px;
            color: #1f2937;
            font-size: 14px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 40px;
            border-bottom: 2px solid #e5e7eb;
            padding-bottom: 20px;
        }}
        .title {{
            font-size: 28px;
            font-weight: bold;
            color: #111827;
        }}
        .invoice-number {{
            font-size: 12px;
            color: #6b7280;
            margin-top: 4px;
        }}
        .status-badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            color: white;
            background-color: {status_color};
        }}
        .info-section {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 30px;
        }}
        .info-block {{
            max-width: 45%;
        }}
        .info-label {{
            font-size: 12px;
            color: #6b7280;
            text-transform: uppercase;
            margin-bottom: 4px;
        }}
        .info-value {{
            font-size: 16px;
            font-weight: 500;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        th {{
            background-color: #f9fafb;
            border-bottom: 2px solid #e5e7eb;
            padding: 12px 8px;
            text-align: left;
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
            color: #6b7280;
        }}
        td {{
            border-bottom: 1px solid #e5e7eb;
            padding: 12px 8px;
        }}
        .text-right {{
            text-align: right;
        }}
        .totals {{
            margin-top: 30px;
            text-align: right;
        }}
        .total-row {{
            display: flex;
            justify-content: flex-end;
            margin-bottom: 8px;
        }}
        .total-label {{
            width: 120px;
            text-align: right;
            padding-right: 20px;
            color: #6b7280;
        }}
        .total-value {{
            width: 120px;
            text-align: right;
            font-weight: 500;
        }}
        .grand-total {{
            font-size: 18px;
            font-weight: bold;
            border-top: 2px solid #111827;
            padding-top: 8px;
            margin-top: 8px;
        }}
        .notes {{
            margin-top: 40px;
            padding: 16px;
            background-color: #f9fafb;
            border-radius: 8px;
        }}
        .notes-label {{
            font-size: 12px;
            color: #6b7280;
            text-transform: uppercase;
            margin-bottom: 8px;
        }}
        .footer {{
            margin-top: 60px;
            text-align: center;
            font-size: 12px;
            color: #9ca3af;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <div class="title">{type_label}</div>
            <div class="invoice-number">{html.escape(invoice.uid)}</div>
        </div>
        <div>
            <span class="status-badge">{invoice.status.value.upper()}</span>
        </div>
    </div>

    <div class="info-section">
        <div class="info-block">
            <div class="info-label">{direction_label}</div>
            <div class="info-value">{html.escape(invoice.counterparty)}</div>
        </div>
        <div class="info-block" style="text-align: right;">
            <div class="info-label">Invoice Date</div>
            <div class="info-value">{invoice_date_str}</div>
            <div class="info-label" style="margin-top: 12px;">Due Date</div>
            <div class="info-value">{due_date_str}</div>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>Description</th>
                <th class="text-right">Qty</th>
                <th class="text-right">Unit Price</th>
                <th class="text-right">Amount</th>
            </tr>
        </thead>
        <tbody>
            {items_html}
        </tbody>
    </table>

    <div class="totals">
        <div class="total-row">
            <div class="total-label">Subtotal</div>
            <div class="total-value">${invoice.subtotal:.2f}</div>
        </div>
        <div class="total-row grand-total">
            <div class="total-label">Total</div>
            <div class="total-value">${invoice.total:.2f}</div>
        </div>
    </div>

    {notes_html}

    <div class="footer">
        Generated by SKUEL Finance
    </div>
</body>
</html>
        """


def render_invoice_pdf(invoice: InvoicePure) -> bytes:
    """
    Render an invoice to PDF bytes via WeasyPrint.

    Args:
        invoice: Invoice domain model

    Returns:
        PDF file content as bytes
    """
    html_content = render_invoice_html(invoice)

    from weasyprint import HTML  # type: ignore[import-untyped]

    return HTML(string=html_content).write_pdf()


__all__ = ["render_invoice_html", "render_invoice_pdf"]
