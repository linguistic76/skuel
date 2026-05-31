"""
Finance Services Module
======================

Standalone bookkeeping services. After the ADR-052 Phase 5 demolition the
native expense/budget/reporting/categories module is gone; only the invoice
module survives (rendered to PDF, with a Firefly III ledger sidecar).

Sub-Service:
- FinanceInvoiceService: Invoice CRUD + PDF generation

Facade Service:
- FinanceService (core.services.finance_service): wraps FinanceInvoiceService
"""

from core.services.finance.finance_invoice_service import FinanceInvoiceService

__all__ = [
    "FinanceInvoiceService",
]
