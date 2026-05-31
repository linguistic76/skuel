"""
Finance Service (Facade)
========================

Standalone facade for the surviving finance module: invoices.

Architecture Pattern:
--------------------
Finance is a standalone bookkeeping domain. After the ADR-052 Phase 5
demolition, the native expense/budget/reporting/categories module is gone;
SKUEL keeps only the invoice module (rendered to PDF via WeasyPrint) and the
Firefly III ledger sidecar. This facade now wraps a single sub-service.

FinanceService (Standalone Facade)
    └── FinanceInvoiceService - Invoice CRUD + PDF generation

Security:
---------
Finance is admin-only. Route-level security is enforced via @require_admin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

from core.models.finance.invoice import InvoicePure
from core.ports.query_types import InvoiceStats
from core.services.finance.finance_invoice_service import FinanceInvoiceService
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports.finance_protocols import InvoiceRenderer
    from core.ports.infrastructure_protocols import EventBusOperations


# ============================================================================
# FINANCE CONTEXT TYPEDDICTS
# ============================================================================


class FinanceInvoicesContext(TypedDict):
    """Return type for FinanceService.get_invoices_context()."""

    invoices: list[dict[str, Any]]
    stats: dict[str, Any]


class FinanceService:
    """
    Finance facade service (standalone, invoice-only).

    Orchestrates invoice operations by delegating to FinanceInvoiceService:
    - Invoice CRUD
    - PDF generation (delegated to outbound renderer)
    - Invoice statistics

    Finance is a standalone bookkeeping domain:
    - No BaseService inheritance
    - No cross-domain intelligence
    - No graph relationship configuration
    """

    def __init__(
        self,
        invoice_backend: Any,
        invoice_renderer: InvoiceRenderer,
        event_bus: EventBusOperations | None = None,
    ) -> None:
        """
        Initialize the invoice-only finance facade.

        FAIL-FAST ARCHITECTURE (per CLAUDE.md):
        Both the invoice backend and renderer are REQUIRED — no graceful
        degradation.

        Args:
            invoice_backend: Backend for invoice operations - REQUIRED
            invoice_renderer: Outbound PDF renderer for invoices. Injected at the
                composition root so the service layer never imports the renderer
                (ADR-044/SKUEL022).
            event_bus: Event bus for publishing domain events (optional)
        """
        if not invoice_backend:
            raise ValueError("Finance invoice backend is required")

        self.logger = get_logger("skuel.services.finance")
        self.event_bus = event_bus

        self.invoice = FinanceInvoiceService(invoice_backend, invoice_renderer)
        self.logger.debug("FinanceService initialized (invoice-only bookkeeping)")

    # ========================================================================
    # UI CONTEXT METHODS — Pre-computed data for route handlers
    # ========================================================================

    async def get_invoices_context(self) -> Result[FinanceInvoicesContext]:
        """Build pre-computed context for the invoices page.

        Returns dict with: invoices (list of display dicts), stats.
        """
        invoices: list[dict[str, Any]] = []
        stats: dict[str, Any] = {
            "total_count": 0,
            "outgoing_total": 0.0,
            "incoming_total": 0.0,
            "overdue_count": 0,
            "outstanding_total": 0.0,
        }

        try:
            stats_result = await self.get_invoice_stats()
            if stats_result.is_ok and stats_result.value:
                raw = stats_result.value
                stats = {
                    "total_count": raw.get("total_count", 0),
                    "outgoing_total": raw.get("outgoing_total", 0.0),
                    "incoming_total": raw.get("incoming_total", 0.0),
                    "overdue_count": raw.get("overdue_count", 0),
                    "outstanding_total": raw.get("outstanding_total", 0.0),
                }

            invoices_result = await self.list_invoices(limit=50)
            if invoices_result.is_ok and invoices_result.value:
                invoices = [
                    {
                        "uid": inv.uid,
                        "invoice_type": inv.invoice_type.value,
                        "counterparty": inv.counterparty,
                        "invoice_date": str(inv.invoice_date),
                        "due_date": str(inv.due_date) if inv.due_date else None,
                        "total": inv.total,
                        "status": inv.status.value,
                        "is_overdue": inv.is_overdue(),
                    }
                    for inv in invoices_result.value
                ]
        except (ValueError, TypeError, AttributeError) as e:
            self.logger.warning(f"Could not fetch invoices: {e}")

        return Result.ok(
            {
                "invoices": invoices,
                "stats": stats,
            }
        )

    # ========================================================================
    # INVOICE OPERATIONS - Delegate to FinanceInvoiceService
    # ========================================================================

    async def create_invoice(self, invoice: InvoicePure) -> Result[InvoicePure]:
        """Create a new invoice."""
        return await self.invoice.create(invoice)

    async def get_invoice(self, uid: str) -> Result[InvoicePure | None]:
        """Get an invoice by UID."""
        return await self.invoice.get(uid)

    async def list_invoices(
        self,
        limit: int = 50,
        invoice_type: str | None = None,
        status: str | None = None,
    ) -> Result[list[InvoicePure]]:
        """List invoices with optional filters.

        Args:
            limit: Maximum number of results
            invoice_type: Optional filter ('outgoing' or 'incoming')
            status: Optional filter by status
        """
        from core.models.finance.invoice import InvoiceStatus, InvoiceType

        type_filter = InvoiceType(invoice_type) if invoice_type else None
        status_filter = InvoiceStatus(status) if status else None

        return await self.invoice.list_invoices(
            limit=limit,
            invoice_type=type_filter,
            status=status_filter,
        )

    async def generate_invoice_pdf(self, uid: str) -> Result[bytes]:
        """Generate PDF bytes for an invoice."""
        return await self.invoice.generate_pdf(uid)

    async def get_invoice_stats(self) -> Result[InvoiceStats]:
        """Get invoice statistics."""
        return await self.invoice.get_invoice_stats()


__all__ = ["FinanceInvoicesContext", "FinanceService"]
