"""
Finance Models Module
=====================

Three-tier architecture for Finance domain:
- Request models (Pydantic) for API validation
- DTOs for data transfer between layers
- Pure models for domain logic
"""

# Pure domain models
# Converters
from .finance_converters import (
    budget_create_request_to_dto,
    budget_dto_to_pure,
    budget_dto_to_response,
    budget_pure_to_dto,
    budget_update_request_to_dto,
    expense_create_request_to_dto,
    expense_dto_to_pure,
    expense_dto_to_response,
    expense_pure_to_dto,
    expense_update_request_to_dto,
)

# DTOs
from .finance_dto import BudgetAnalysisDTO, BudgetDTO, ExpenseDTO, ExpenseReportDTO
from .finance_pure import (
    EXPENSE_SUBCATEGORIES,
    BudgetPeriod,
    BudgetPure,
    ExpenseCategory,
    ExpensePure,
    ExpenseStatus,
    PaymentMethod,
    RecurrencePattern,
    create_budget,
    create_expense,
    create_recurring_expense,
)

# Request models (Pydantic)
from .finance_request import (
    BudgetAnalysisRequest,
    BudgetCreateRequest,
    BudgetFilterRequest,
    BudgetUpdateRequest,
    ExpenseCreateRequest,
    ExpenseFilterRequest,
    ExpenseReportRequest,
    ExpenseUpdateRequest,
)

# No aliases needed - use ExpensePure and BudgetPure directly

__all__ = [
    "EXPENSE_SUBCATEGORIES",
    "Budget",  # Alias
    "BudgetAnalysisDTO",
    "BudgetAnalysisRequest",
    "BudgetCreateRequest",
    "BudgetDTO",
    "BudgetFilterRequest",
    "BudgetPeriod",
    "BudgetPure",
    "BudgetUpdateRequest",
    "Expense",  # Alias
    "ExpenseCategory",
    # Request models
    "ExpenseCreateRequest",
    # DTOs
    "ExpenseDTO",
    "ExpenseFilterRequest",
    # Pure models
    "ExpensePure",
    "ExpenseReportDTO",
    "ExpenseReportRequest",
    # Enums
    "ExpenseStatus",
    "ExpenseUpdateRequest",
    # Intelligence Models
    "FinancialHealthScore",
    "FinancialHealthTier",
    # Invoice models
    "InvoiceCreateRequest",
    "InvoiceDTO",
    "InvoicePure",
    "InvoiceStatus",
    "InvoiceType",
    "InvoiceUpdateRequest",
    "LineItem",
    "LineItemInput",
    "PaymentMethod",
    "RecurrencePattern",
    "SpendingPattern",
    "SpendingVelocity",
    "budget_create_request_to_dto",
    "budget_dto_to_pure",
    "budget_dto_to_response",
    "budget_pure_to_dto",
    "budget_update_request_to_dto",
    "create_budget",
    # Factory functions
    "create_expense",
    "create_invoice",
    "create_recurring_expense",
    # Converters
    "expense_create_request_to_dto",
    "expense_dto_to_pure",
    "expense_dto_to_response",
    "expense_pure_to_dto",
    "expense_update_request_to_dto",
    "invoice_create_request_to_dto",
    "invoice_dto_to_pure",
    "invoice_dto_to_response",
    "invoice_pure_to_dto",
    "invoice_update_request_to_dto",
]

# Intelligence models
from .finance_intelligence import (
    FinancialHealthScore,
    FinancialHealthTier,
    SpendingPattern,
    SpendingVelocity,
)

# Invoice models
from .invoice import (
    InvoiceCreateRequest,
    InvoiceDTO,
    InvoicePure,
    InvoiceStatus,
    InvoiceType,
    InvoiceUpdateRequest,
    LineItem,
    LineItemInput,
    create_invoice,
    invoice_create_request_to_dto,
    invoice_dto_to_pure,
    invoice_dto_to_response,
    invoice_pure_to_dto,
    invoice_update_request_to_dto,
)
