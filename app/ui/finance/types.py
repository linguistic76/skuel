"""Finance UI view model types.

Frozen dataclasses for invoice views.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class InvoiceRow:
    """A single invoice in the invoice table."""

    uid: str
    invoice_type: str
    counterparty: str
    invoice_date: str
    total: float
    status: str
    due_date: str | None = None
    is_overdue: bool = False


@dataclass(frozen=True)
class InvoiceStats:
    """Invoice statistics for the stats cards."""

    total_count: int = 0
    outgoing_total: float = 0.0
    incoming_total: float = 0.0
    overdue_count: int = 0
    outstanding_total: float = 0.0
