"""
Finance Services Module
======================

Standalone bookkeeping services following Core + Facade pattern.

Purpose: Simple expense/income tracking, budgets, reports, invoices.
Finance is a standalone domain - no cross-domain intelligence or
unified architecture complexity.

Core Service:
- FinanceCoreService: Basic CRUD operations for expenses with event publishing

Specialized Sub-Services:
- FinanceBudgetService: Budget management
- FinanceReportingService: Reports and summaries
- FinanceInvoiceService: Invoice management

Facade Service:
- FinanceService: Orchestrates all finance operations
"""

from core.services.finance.finance_budget_service import FinanceBudgetService
from core.services.finance.finance_core_service import FinanceCoreService
from core.services.finance.finance_reporting_service import FinanceReportingService

__all__ = [
    "FinanceBudgetService",
    "FinanceCoreService",
    "FinanceReportingService",
]
