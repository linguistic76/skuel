"""
Invoice UI Views
================

UI components for the Invoice section of the Finance Hub.
"""

from typing import Any

from fasthtml.common import (
    H2,
    H3,
    A,
    Button,
    Div,
    Form,
    Input,
    Label,
    Option,
    Select,
    Span,
    Table,
    Tbody,
    Td,
    Textarea,
    Th,
    Thead,
    Tr,
)


class InvoiceViews:
    """Invoice section UI components."""

    @staticmethod
    def render_invoices_list(invoices: list[dict[str, Any]], stats: dict[str, Any]) -> Div:
        """
        Render the invoice list page with stats and create form.

        Args:
            invoices: List of invoice dictionaries
            stats: Invoice statistics

        Returns:
            Div containing the invoice list UI
        """
        return Div(
            # Page header
            Div(
                H2("Invoices", cls="text-2xl font-bold text-foreground"),
                Span(
                    f"{stats.get('total_count', 0)} total",
                    cls="text-sm text-muted-foreground",
                ),
                cls="flex items-center justify-between mb-6",
            ),
            # Stats cards
            InvoiceViews._render_stats_cards(stats),
            # Filter bar
            InvoiceViews._render_filter_bar(),
            # Two-column layout: list + create form
            Div(
                # Invoice list
                Div(
                    InvoiceViews._render_invoice_table(invoices),
                    cls="lg:col-span-2",
                ),
                # Create form
                Div(
                    InvoiceViews._render_create_form(),
                    cls="lg:col-span-1",
                ),
                cls="grid grid-cols-1 lg:grid-cols-3 gap-6",
            ),
            cls="space-y-6",
        )

    @staticmethod
    def _render_stats_cards(stats: dict[str, Any]) -> Div:
        """Render invoice statistics cards."""
        cards = [
            {
                "label": "Total Invoices",
                "value": str(stats.get("total_count", 0)),
                "icon": "📄",
            },
            {
                "label": "Outstanding",
                "value": f"${stats.get('outstanding_total', 0):,.2f}",
                "icon": "💰",
            },
            {
                "label": "Overdue",
                "value": str(stats.get("overdue_count", 0)),
                "icon": "⚠️" if stats.get("overdue_count", 0) > 0 else "✓",
                "alert": stats.get("overdue_count", 0) > 0,
            },
        ]

        return Div(
            *[
                Div(
                    Div(
                        Span(card["icon"], cls="text-2xl"),
                        Div(
                            Span(card["value"], cls="text-2xl font-bold"),
                            Span(card["label"], cls="text-sm text-muted-foreground"),
                            cls="flex flex-col",
                        ),
                        cls="flex items-center gap-3",
                    ),
                    cls=f"bg-muted p-4 rounded-lg border {'border-red-300' if card.get('alert') else 'border-border'}",
                )
                for card in cards
            ],
            cls="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6",
        )

    @staticmethod
    def _render_filter_bar() -> Div:
        """Render filter controls."""
        return Div(
            # Type filter
            Div(
                Label("Type", cls="text-sm font-medium text-muted-foreground"),
                Select(
                    Option("All Types", value=""),
                    Option("Outgoing (To Clients)", value="outgoing"),
                    Option("Incoming (From Vendors)", value="incoming"),
                    cls="mt-1 block w-full rounded-md border-border bg-background px-3 py-2 text-sm",
                    name="type",
                    hx_get="/finance/invoices",
                    hx_target="#invoice-list",
                    hx_trigger="change",
                    hx_include="[name='status']",
                ),
                cls="flex-1",
            ),
            # Status filter
            Div(
                Label("Status", cls="text-sm font-medium text-muted-foreground"),
                Select(
                    Option("All Statuses", value=""),
                    Option("Draft", value="draft"),
                    Option("Sent", value="sent"),
                    Option("Pending", value="pending"),
                    Option("Paid", value="paid"),
                    Option("Overdue", value="overdue"),
                    cls="mt-1 block w-full rounded-md border-border bg-background px-3 py-2 text-sm",
                    name="status",
                    hx_get="/finance/invoices",
                    hx_target="#invoice-list",
                    hx_trigger="change",
                    hx_include="[name='type']",
                ),
                cls="flex-1",
            ),
            cls="flex gap-4 mb-6 p-4 bg-muted rounded-lg",
        )

    @staticmethod
    def _render_invoice_table(invoices: list[dict[str, Any]]) -> Div:
        """Render invoice table."""
        if not invoices:
            return Div(
                Div(
                    Span("📄", cls="text-4xl mb-2"),
                    H3("No Invoices Yet", cls="text-lg font-semibold"),
                    Span(
                        "Create your first invoice using the form.",
                        cls="text-sm text-muted-foreground",
                    ),
                    cls="flex flex-col items-center justify-center py-12",
                ),
                cls="bg-background rounded-lg border border-border",
                id="invoice-list",
            )

        # Status badge colors
        status_colors = {
            "draft": "bg-muted text-foreground/80",
            "sent": "bg-info/20 text-info",
            "pending": "bg-warning/20 text-warning",
            "paid": "bg-success/20 text-success",
            "overdue": "bg-error/20 text-error",
            "cancelled": "bg-secondary text-muted-foreground",
        }

        rows = []
        for inv in invoices:
            status = inv.get("status", "draft")
            status_class = status_colors.get(status, "bg-muted text-foreground/80")
            type_icon = "📤" if inv.get("invoice_type") == "outgoing" else "📥"

            rows.append(
                Tr(
                    Td(
                        Div(
                            Span(type_icon, cls="mr-2"),
                            Span(inv.get("uid", "")[:20] + "...", cls="font-mono text-xs"),
                            cls="flex items-center",
                        ),
                        cls="py-3 px-4",
                    ),
                    Td(
                        inv.get("counterparty", "Unknown"),
                        cls="py-3 px-4 font-medium",
                    ),
                    Td(
                        f"${inv.get('total', 0):,.2f}",
                        cls="py-3 px-4 text-right font-semibold",
                    ),
                    Td(
                        inv.get("due_date", "N/A"),
                        cls="py-3 px-4 text-muted-foreground",
                    ),
                    Td(
                        Span(
                            status.upper(),
                            cls=f"px-2 py-1 rounded-full text-xs font-medium {status_class}",
                        ),
                        cls="py-3 px-4",
                    ),
                    Td(
                        Div(
                            A(
                                "View",
                                href=f"/api/invoices/{inv.get('uid')}",
                                cls="text-sm text-primary hover:underline mr-3",
                            ),
                            A(
                                "PDF",
                                href=f"/api/invoices/{inv.get('uid')}/pdf",
                                cls="text-sm text-primary hover:underline",
                                download=True,
                            ),
                            cls="flex items-center gap-2",
                        ),
                        cls="py-3 px-4",
                    ),
                    cls="border-b border-border hover:bg-muted",
                )
            )

        return Div(
            Table(
                Thead(
                    Tr(
                        Th(
                            "Invoice",
                            cls="py-3 px-4 text-left text-sm font-semibold text-muted-foreground",
                        ),
                        Th(
                            "Counterparty",
                            cls="py-3 px-4 text-left text-sm font-semibold text-muted-foreground",
                        ),
                        Th(
                            "Amount",
                            cls="py-3 px-4 text-right text-sm font-semibold text-muted-foreground",
                        ),
                        Th(
                            "Due Date",
                            cls="py-3 px-4 text-left text-sm font-semibold text-muted-foreground",
                        ),
                        Th(
                            "Status",
                            cls="py-3 px-4 text-left text-sm font-semibold text-muted-foreground",
                        ),
                        Th(
                            "Actions",
                            cls="py-3 px-4 text-left text-sm font-semibold text-muted-foreground",
                        ),
                        cls="bg-muted",
                    ),
                ),
                Tbody(*rows),
                cls="w-full",
            ),
            cls="bg-background rounded-lg border border-border overflow-hidden",
            id="invoice-list",
        )

    @staticmethod
    def _render_create_form() -> Div:
        """Render the create invoice form."""
        return Div(
            H3("Create Invoice", cls="text-lg font-semibold mb-4"),
            Form(
                # Invoice type
                Div(
                    Label("Type", cls="block text-sm font-medium text-muted-foreground mb-1"),
                    Div(
                        Label(
                            Input(
                                type="radio",
                                name="invoice_type",
                                value="outgoing",
                                checked=True,
                                cls="mr-2",
                            ),
                            "Outgoing (To Client)",
                            cls="flex items-center text-sm",
                        ),
                        Label(
                            Input(
                                type="radio",
                                name="invoice_type",
                                value="incoming",
                                cls="mr-2",
                            ),
                            "Incoming (From Vendor)",
                            cls="flex items-center text-sm",
                        ),
                        cls="flex gap-4",
                    ),
                    cls="mb-4",
                ),
                # Counterparty
                Div(
                    Label(
                        "Client/Vendor Name",
                        cls="block text-sm font-medium text-muted-foreground mb-1",
                    ),
                    Input(
                        type="text",
                        name="counterparty",
                        placeholder="Enter name...",
                        required=True,
                        cls="w-full px-3 py-2 border border-border rounded-md text-sm",
                    ),
                    cls="mb-4",
                ),
                # Dates
                Div(
                    Div(
                        Label(
                            "Invoice Date",
                            cls="block text-sm font-medium text-muted-foreground mb-1",
                        ),
                        Input(
                            type="date",
                            name="invoice_date",
                            required=True,
                            cls="w-full px-3 py-2 border border-border rounded-md text-sm",
                        ),
                        cls="flex-1",
                    ),
                    Div(
                        Label(
                            "Due Date", cls="block text-sm font-medium text-muted-foreground mb-1"
                        ),
                        Input(
                            type="date",
                            name="due_date",
                            cls="w-full px-3 py-2 border border-border rounded-md text-sm",
                        ),
                        cls="flex-1",
                    ),
                    cls="flex gap-4 mb-4",
                ),
                # Line items section
                Div(
                    Label("Line Items", cls="block text-sm font-medium text-muted-foreground mb-2"),
                    Div(
                        # First line item (always visible)
                        InvoiceViews._render_line_item_row(0),
                        id="line-items-container",
                        cls="space-y-2",
                    ),
                    Button(
                        "+ Add Line Item",
                        type="button",
                        cls="mt-2 text-sm text-primary hover:underline",
                        onclick="addLineItem()",
                    ),
                    cls="mb-4",
                ),
                # Notes
                Div(
                    Label("Notes", cls="block text-sm font-medium text-muted-foreground mb-1"),
                    Textarea(
                        name="notes",
                        placeholder="Optional notes...",
                        rows=2,
                        cls="w-full px-3 py-2 border border-border rounded-md text-sm",
                    ),
                    cls="mb-4",
                ),
                # Submit button
                Button(
                    "Create Invoice",
                    type="submit",
                    cls="w-full bg-primary text-white py-2 px-4 rounded-md hover:bg-primary/90 font-medium",
                ),
                action="/api/invoices",
                method="POST",
                cls="space-y-2",
            ),
            # JavaScript for dynamic line items
            Div(
                """
                <script>
                let lineItemCount = 1;

                function addLineItem() {
                    const container = document.getElementById('line-items-container');
                    const newItem = document.createElement('div');
                    newItem.className = 'grid grid-cols-12 gap-2 items-end';
                    newItem.innerHTML = `
                        <div class="col-span-6">
                            <input type="text" name="items[${lineItemCount}][description]" placeholder="Description" required
                                class="w-full px-2 py-1 border border-border rounded text-sm" />
                        </div>
                        <div class="col-span-2">
                            <input type="number" name="items[${lineItemCount}][quantity]" placeholder="Qty" step="0.01" min="0.01" required
                                class="w-full px-2 py-1 border border-border rounded text-sm" />
                        </div>
                        <div class="col-span-3">
                            <input type="number" name="items[${lineItemCount}][unit_price]" placeholder="Unit $" step="0.01" min="0" required
                                class="w-full px-2 py-1 border border-border rounded text-sm" />
                        </div>
                        <div class="col-span-1">
                            <button type="button" onclick="this.parentElement.parentElement.remove()" class="text-red-500 hover:text-red-700 text-sm">X</button>
                        </div>
                    `;
                    container.appendChild(newItem);
                    lineItemCount++;
                }
                </script>
                """,
            ),
            cls="bg-muted p-6 rounded-lg border border-border",
        )

    @staticmethod
    def _render_line_item_row(index: int) -> Div:
        """Render a single line item row."""
        return Div(
            Div(
                Input(
                    type="text",
                    name=f"items[{index}][description]",
                    placeholder="Description",
                    required=True,
                    cls="w-full px-2 py-1 border border-border rounded text-sm",
                ),
                cls="col-span-6",
            ),
            Div(
                Input(
                    type="number",
                    name=f"items[{index}][quantity]",
                    placeholder="Qty",
                    step="0.01",
                    min="0.01",
                    required=True,
                    cls="w-full px-2 py-1 border border-border rounded text-sm",
                ),
                cls="col-span-2",
            ),
            Div(
                Input(
                    type="number",
                    name=f"items[{index}][unit_price]",
                    placeholder="Unit $",
                    step="0.01",
                    min="0",
                    required=True,
                    cls="w-full px-2 py-1 border border-border rounded text-sm",
                ),
                cls="col-span-3",
            ),
            Div(
                Span(
                    "", cls="text-muted-foreground"
                ),  # Placeholder for delete button (first item can't be deleted)
                cls="col-span-1",
            ),
            cls="grid grid-cols-12 gap-2 items-end",
        )


__all__ = ["InvoiceViews"]
