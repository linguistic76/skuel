"""
Finance Invoice Service
=======================

Invoice management service for Finance domain.

This service handles:
- Invoice CRUD operations
- PDF generation (delegated to outbound adapter)
- Invoice status management

Architecture Pattern:
--------------------
Finance is its OWN domain group (not Activity, not Curriculum).
This is a sub-service under the FinanceService facade.

Security:
---------
Finance is admin-only. Route-level security is enforced via @require_admin.
No ownership verification needed - admin sees all finance data.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from adapters.outbound.invoice_renderer import render_invoice_pdf
from core.models.finance.invoice import (
    InvoicePure,
    InvoiceStatus,
    InvoiceType,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.base_protocols import BackendOperations

logger = get_logger("finance.invoice")


class FinanceInvoiceService:
    """
    Invoice management service.

    Handles CRUD operations and PDF generation for invoices.
    """

    def __init__(
        self,
        backend: BackendOperations[InvoicePure],
    ) -> None:
        """
        Initialize invoice service.

        Args:
            backend: Protocol-based backend for invoice operations
        """
        self.backend = backend
        self.logger = get_logger("finance.invoice")

    @property
    def entity_label(self) -> str:
        """Return the graph label for Invoice entities."""
        return "Invoice"

    # ========================================================================
    # CRUD OPERATIONS
    # ========================================================================

    async def create(self, invoice: InvoicePure) -> Result[InvoicePure]:
        """
        Create a new invoice.

        Args:
            invoice: InvoicePure domain model

        Returns:
            Result containing created invoice
        """
        # Validate
        validation_error = self._validate_create(invoice)
        if validation_error is not None:
            return Result.fail(validation_error)

        self.logger.info(
            f"Creating invoice for {invoice.counterparty}, "
            f"type={invoice.invoice_type.value}, total=${invoice.total:.2f}"
        )

        result = await self.backend.create(invoice)

        if result.is_ok:
            self.logger.info(f"Created invoice {invoice.uid}")

        return result

    async def get(self, uid: str) -> Result[InvoicePure | None]:
        """
        Get an invoice by UID.

        Args:
            uid: Invoice UID

        Returns:
            Result containing InvoicePure or None if not found
        """
        return await self.backend.get(uid)

    async def list_invoices(
        self,
        limit: int = 50,
        offset: int = 0,
        invoice_type: InvoiceType | None = None,
        status: InvoiceStatus | None = None,
    ) -> Result[list[InvoicePure]]:
        """
        List invoices with optional filters.

        Args:
            limit: Maximum number of results
            offset: Pagination offset
            invoice_type: Optional filter by type (outgoing/incoming)
            status: Optional filter by status

        Returns:
            Result containing list of invoices
        """
        filters: dict[str, Any] = {}

        if invoice_type is not None:
            filters["invoice_type"] = invoice_type.value

        if status is not None:
            filters["status"] = status.value

        result = await self.backend.list(limit=limit, offset=offset, filters=filters or None)

        if result.is_error:
            return Result.fail(result.error)

        # Extract just the list from (list, count) tuple
        # Handle case where database has no Invoice nodes yet
        value = result.value
        if isinstance(value, tuple) and len(value) >= 2:
            invoices, _count = value
        else:
            invoices = value if isinstance(value, list) else []
        return Result.ok(invoices)

    async def update(
        self,
        uid: str,
        updates: dict[str, Any],
    ) -> Result[InvoicePure]:
        """
        Update an existing invoice.

        Args:
            uid: Invoice UID
            updates: Dictionary of fields to update

        Returns:
            Result containing updated invoice
        """
        # Get existing invoice
        existing_result = await self.backend.get(uid)
        if existing_result.is_error:
            return Result.fail(existing_result.error)

        if existing_result.value is None:
            return Result.fail(Errors.not_found("Invoice", uid))

        # Add updated_at timestamp
        updates["updated_at"] = datetime.now().isoformat()

        self.logger.info(f"Updating invoice {uid}")

        return await self.backend.update(uid, updates)

    async def delete(self, uid: str) -> Result[bool]:
        """
        Delete an invoice.

        Args:
            uid: Invoice UID

        Returns:
            Result containing True if deleted
        """
        self.logger.info(f"Deleting invoice {uid}")
        return await self.backend.delete(uid)

    # ========================================================================
    # STATUS MANAGEMENT
    # ========================================================================

    async def mark_sent(self, uid: str) -> Result[InvoicePure]:
        """
        Mark an outgoing invoice as sent.

        Args:
            uid: Invoice UID

        Returns:
            Result containing updated invoice
        """
        existing_result = await self.backend.get(uid)
        if existing_result.is_error:
            return Result.fail(existing_result.error)

        if existing_result.value is None:
            return Result.fail(Errors.not_found("Invoice", uid))

        invoice = existing_result.value

        if invoice.invoice_type != InvoiceType.OUTGOING:
            return Result.fail(
                Errors.business("invoice_sent", "Only outgoing invoices can be marked as sent")
            )

        return await self.update(uid, {"status": InvoiceStatus.SENT.value})

    async def mark_paid(self, uid: str) -> Result[InvoicePure]:
        """
        Mark an invoice as paid.

        Args:
            uid: Invoice UID

        Returns:
            Result containing updated invoice
        """
        return await self.update(uid, {"status": InvoiceStatus.PAID.value})

    # ========================================================================
    # PDF GENERATION
    # ========================================================================

    async def generate_pdf(self, uid: str) -> Result[bytes]:
        """
        Generate PDF for an invoice.

        Delegates to outbound adapter for HTML rendering and PDF conversion.

        Args:
            uid: Invoice UID

        Returns:
            Result containing PDF bytes
        """
        # Get invoice
        result = await self.backend.get(uid)
        if result.is_error:
            return Result.fail(result.error)

        if result.value is None:
            return Result.fail(Errors.not_found("Invoice", uid))

        invoice = result.value

        try:
            pdf_bytes = render_invoice_pdf(invoice)
            self.logger.info(f"Generated PDF for invoice {uid}")
            return Result.ok(pdf_bytes)

        except ImportError:
            return Result.fail(Errors.system("WeasyPrint not installed. Run: uv add weasyprint"))
        except Exception as e:
            self.logger.error(f"PDF generation failed for {uid}: {e}")
            return Result.fail(Errors.system(f"PDF generation failed: {e}"))

    # ========================================================================
    # VALIDATION
    # ========================================================================

    def _validate_create(self, invoice: InvoicePure) -> Result[None] | None:
        """
        Validate invoice creation.

        Args:
            invoice: Invoice to validate

        Returns:
            None if valid, Result.fail() if invalid
        """
        # Must have at least one line item
        if not invoice.items:
            return Result.fail(
                Errors.validation(
                    message="Invoice must have at least one line item",
                    field="items",
                    value=[],
                )
            )

        # All line items must have positive amounts
        for i, item in enumerate(invoice.items):
            if item.quantity <= 0:
                return Result.fail(
                    Errors.validation(
                        message=f"Line item {i + 1}: quantity must be positive",
                        field=f"items[{i}].quantity",
                        value=item.quantity,
                    )
                )
            if item.unit_price < 0:
                return Result.fail(
                    Errors.validation(
                        message=f"Line item {i + 1}: unit price cannot be negative",
                        field=f"items[{i}].unit_price",
                        value=item.unit_price,
                    )
                )

        return None

    # ========================================================================
    # STATISTICS
    # ========================================================================

    async def get_invoice_stats(self) -> Result[dict[str, Any]]:
        """
        Get invoice statistics.

        Returns:
            Result containing stats dictionary
        """
        result = await self.backend.list(limit=1000, offset=0, filters=None)

        if result.is_error:
            return Result.fail(result.error)

        # Handle case where database has no Invoice nodes yet
        value = result.value
        if isinstance(value, tuple) and len(value) >= 2:
            invoices, _count = value
        else:
            invoices = value if isinstance(value, list) else []

        total_count = len(invoices)
        outgoing_total = 0.0
        incoming_total = 0.0
        overdue_count = 0
        pending_total = 0.0

        for inv in invoices:
            if inv.invoice_type == InvoiceType.OUTGOING:
                outgoing_total += inv.total
            else:
                incoming_total += inv.total

            if inv.is_overdue():
                overdue_count += 1

            if inv.status in (InvoiceStatus.PENDING, InvoiceStatus.SENT):
                pending_total += inv.total

        return Result.ok(
            {
                "total_count": total_count,
                "outgoing_total": outgoing_total,
                "incoming_total": incoming_total,
                "overdue_count": overdue_count,
                "outstanding_total": pending_total,
            }
        )


__all__ = ["FinanceInvoiceService"]
