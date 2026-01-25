"""
Finance Pure Domain Models
===========================

Pure, immutable domain models for Finance (Tier 3 of three-tier architecture).
Frozen dataclasses with business logic, no framework dependencies.

Finance is a standalone bookkeeping domain. Simple, focused on tracking
expenses, budgets, actuals, revenue, and invoices. No cross-domain
intelligence or unified architecture complexity.
"""

from __future__ import annotations

__version__ = "3.0"  # Simplified standalone bookkeeping (January 2026)

from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

# Finance enums consolidated in /core/models/enums/finance_enums.py (January 2026)
from core.models.enums.finance_enums import (
    BudgetPeriod,
    ExpenseCategory,
    ExpenseStatus,
    PaymentMethod,
    RecurrencePattern,
)

if TYPE_CHECKING:
    from core.models.finance.finance_dto import BudgetDTO, ExpenseDTO


# Subcategory mappings for validation
EXPENSE_SUBCATEGORIES = {
    "personal": [
        "housing",
        "food",
        "transportation",
        "healthcare",
        "clothing",
        "entertainment",
        "hobbies",
        "subscriptions",
    ],
    "2222": [
        "equipment",
        "software",
        "services",
        "contractors",
        "office",
        "utilities",
        "marketing",
        "legal",
    ],
    "skuel": [
        "development",
        "infrastructure",
        "ai_services",
        "databases",
        "monitoring",
        "security",
        "documentation",
        "testing",
    ],
}


# ============================================================================
# EXPENSE PURE MODEL
# ============================================================================


@dataclass(frozen=True)
class ExpensePure:
    """
    Pure immutable expense domain model.

    Represents a single financial transaction/expense.
    All fields are immutable - use factory methods to create modified copies.
    """

    # Identity
    uid: str
    user_uid: str  # REQUIRED - expense ownership

    # Core expense data
    amount: float
    currency: str
    description: str
    expense_date: date

    # Classification
    category: ExpenseCategory
    subcategory: str | None = None

    # Payment info
    payment_method: PaymentMethod = PaymentMethod.OTHER
    account_uid: str | None = None
    vendor: str | None = None

    # Status
    status: ExpenseStatus = ExpenseStatus.PENDING

    # Tax and reimbursement
    tax_deductible: bool = False
    reimbursable: bool = False
    tax_amount: float = 0.0

    # Documentation
    receipt_url: str | None = None
    notes: str | None = None

    # Recurring expense fields
    is_recurring: bool = False
    recurrence_pattern: RecurrencePattern | None = None
    recurrence_end_date: date | None = None  # type: ignore[assignment]
    parent_expense_uid: str | None = None

    # Budget tracking
    budget_uid: str | None = None
    budget_category: str | None = None

    # Metadata
    tags: list[str] = None  # type: ignore[assignment]
    metadata: dict[str, Any] = None  # type: ignore[assignment]

    # Audit fields
    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]
    created_by: str | None = None

    def __post_init__(self) -> None:
        """Initialize default values for mutable fields"""
        # Use object.__setattr__ since dataclass is frozen
        if self.tags is None:
            object.__setattr__(self, "tags", [])
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", datetime.now())

    # ========================================================================
    # DTO CONVERSION - THREE-TIER ARCHITECTURE
    # ========================================================================

    @classmethod
    def from_dto(cls, dto: ExpenseDTO) -> ExpensePure:
        """
        Create immutable ExpensePure from mutable ExpenseDTO.

        This method maintains consistency with the three-tier architecture
        pattern used across all SKUEL domains.

        Args:
            dto: ExpenseDTO instance (mutable, from database/API layer)

        Returns:
            Immutable ExpensePure domain model

        Note:
            Internally delegates to expense_dto_to_pure converter function.
            This class method exists to satisfy DomainModelProtocol for
            type-safe generic operations (UniversalNeo4jBackend, BaseService).

        Example:
            dto = ExpenseDTO.from_dict(data)
            expense = ExpensePure.from_dto(dto)
        """
        from core.models.finance.finance_converters import expense_dto_to_pure

        return expense_dto_to_pure(dto)

    def to_dto(self) -> ExpenseDTO:
        """
        Convert immutable ExpensePure to mutable ExpenseDTO.

        Used for database operations and API serialization.

        Returns:
            Mutable ExpenseDTO instance

        Note:
            Internally delegates to expense_pure_to_dto converter function.
            This instance method exists to satisfy DomainModelProtocol for
            type-safe generic operations.

        Example:
            expense = ExpensePure(...)
            dto = expense.to_dto()  # Can modify DTO fields
        """
        from core.models.finance.finance_converters import expense_pure_to_dto

        return expense_pure_to_dto(self)

    # ========================================================================
    # DOMAIN METHODS
    # ========================================================================

    def with_status(self, status: ExpenseStatus) -> ExpensePure:
        """Create new expense with updated status"""
        from .finance_converters import expense_dto_to_pure, expense_pure_to_dto

        dto = expense_pure_to_dto(self)
        dto.status = status
        dto.updated_at = datetime.now()
        return expense_dto_to_pure(dto)

    def with_receipt(self, receipt_url: str) -> ExpensePure:
        """Attach receipt to expense"""
        from .finance_converters import expense_dto_to_pure, expense_pure_to_dto

        dto = expense_pure_to_dto(self)
        dto.receipt_url = receipt_url
        dto.updated_at = datetime.now()
        return expense_dto_to_pure(dto)

    def reconcile(self) -> ExpensePure:
        """Mark expense as reconciled"""
        return self.with_status(ExpenseStatus.RECONCILED)

    def clear(self) -> ExpensePure:
        """Mark expense as cleared"""
        return self.with_status(ExpenseStatus.CLEARED)

    def cancel(self) -> ExpensePure:
        """Cancel the expense"""
        return self.with_status(ExpenseStatus.CANCELLED)

    # ========================================================================
    # DOMAIN LOGIC
    # ========================================================================

    def is_large_expense(self, threshold: float = 500.0) -> bool:
        """Check if expense exceeds threshold"""
        return self.amount > threshold

    def is_recent(self, days: int = 30) -> bool:
        """Check if expense is within recent days"""
        delta = date.today() - self.expense_date
        return delta.days <= days

    def is_future(self) -> bool:
        """Check if expense is in the future"""
        return self.expense_date > date.today()

    def is_tax_relevant(self) -> bool:
        """Check if expense has tax implications"""
        return self.tax_deductible or self.tax_amount > 0

    def is_business_expense(self) -> bool:
        """Check if this is a business-related expense"""
        return (
            self.category in [ExpenseCategory.TWO222, ExpenseCategory.SKUEL] or self.tax_deductible
        )

    def get_total_amount(self) -> float:
        """Get total amount including tax"""
        return self.amount + self.tax_amount

    def days_until_due(self) -> int:
        """Days until expense is due (for future expenses)"""
        if self.is_future():
            return (self.expense_date - date.today()).days
        return 0

    def days_overdue(self) -> int:
        """Days overdue (for pending past expenses)"""
        if not self.is_future() and self.status == ExpenseStatus.PENDING:
            return (date.today() - self.expense_date).days
        return 0


# ============================================================================
# BUDGET PURE MODEL
# ============================================================================


@dataclass(frozen=True)
class BudgetPure:
    """
    Pure immutable budget domain model.

    Represents a budget for tracking expense limits.
    """

    # Identity
    uid: str
    user_uid: str  # REQUIRED - budget ownership
    name: str

    # Budget configuration
    period: BudgetPeriod
    amount_limit: float
    currency: str

    # Time bounds
    start_date: date
    end_date: date | None = None  # type: ignore[assignment]

    # Categories covered
    categories: list[ExpenseCategory] = None  # type: ignore[assignment]

    # Current tracking
    amount_spent: float = 0.0
    expense_count: int = 0

    # Alerts
    alert_threshold: float = 0.8
    is_exceeded: bool = False

    # Metadata
    notes: str | None = (None,)

    tags: list[str] = None  # type: ignore[assignment]

    # Audit
    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        """Initialize default values"""
        if self.categories is None:
            object.__setattr__(self, "categories", [])
        if self.tags is None:
            object.__setattr__(self, "tags", [])
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", datetime.now())

    # ========================================================================
    # DOMAIN METHODS
    # ========================================================================

    def get_remaining(self) -> float:
        """Get remaining budget amount"""
        return max(0, self.amount_limit - self.amount_spent)

    def get_utilization(self) -> float:
        """Get budget utilization percentage (0-1)"""
        if self.amount_limit == 0:
            return 0.0
        return min(1.0, self.amount_spent / self.amount_limit)

    def is_near_limit(self) -> bool:
        """Check if budget is near the alert threshold"""
        return self.get_utilization() >= self.alert_threshold

    def with_expense_added(self, amount: float) -> BudgetPure:
        """Add an expense to the budget tracking"""
        from .finance_converters import budget_dto_to_pure, budget_pure_to_dto

        dto = budget_pure_to_dto(self)
        dto.amount_spent = self.amount_spent + amount
        dto.expense_count = self.expense_count + 1
        dto.is_exceeded = dto.amount_spent > self.amount_limit
        dto.updated_at = datetime.now()
        return budget_dto_to_pure(dto)

    # ========================================================================
    # DTO CONVERSION - THREE-TIER ARCHITECTURE
    # ========================================================================

    @classmethod
    def from_dto(cls, dto: BudgetDTO) -> BudgetPure:
        """
        Create immutable BudgetPure from mutable BudgetDTO.

        This method maintains consistency with the three-tier architecture
        pattern used across all SKUEL domains.

        Args:
            dto: BudgetDTO instance (mutable, from database/API layer)

        Returns:
            Immutable BudgetPure domain model

        Note:
            Internally delegates to budget_dto_to_pure converter function.
            This class method exists to satisfy DomainModelProtocol for
            type-safe generic operations (UniversalNeo4jBackend, BaseService).

        Example:
            dto = BudgetDTO.from_dict(data)
            budget = BudgetPure.from_dto(dto)
        """
        from .finance_converters import budget_dto_to_pure

        return budget_dto_to_pure(dto)

    def to_dto(self) -> BudgetDTO:
        """
        Convert immutable BudgetPure to mutable BudgetDTO.

        Used for database operations and API serialization.

        Returns:
            Mutable BudgetDTO instance

        Note:
            Internally delegates to budget_pure_to_dto converter function.

        Example:
            dto = budget.to_dto()
        """
        from .finance_converters import budget_pure_to_dto

        return budget_pure_to_dto(self)


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================


def create_expense(
    uid: str,
    user_uid: str,
    amount: float,
    description: str,
    category: ExpenseCategory,
    expense_date: date | None = None,
    currency: str = "USD",
    payment_method: PaymentMethod = PaymentMethod.OTHER,
    vendor: str | None = None,
) -> ExpensePure:
    """Factory function to create a new expense"""
    if not user_uid:
        raise ValueError("user_uid is REQUIRED for expense creation (fail-fast)")

    return ExpensePure(
        uid=uid,
        user_uid=user_uid,
        amount=amount,
        currency=currency,
        description=description,
        expense_date=expense_date or date.today(),
        category=category,
        payment_method=payment_method,
        vendor=vendor,
        status=ExpenseStatus.PENDING,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def create_recurring_expense(
    uid: str,
    user_uid: str,
    amount: float,
    description: str,
    category: ExpenseCategory,
    recurrence_pattern: RecurrencePattern,
    start_date: date,
    end_date: date | None = None,
    currency: str = "USD",
) -> ExpensePure:
    """Factory function to create a recurring expense template"""
    if not user_uid:
        raise ValueError("user_uid is REQUIRED for expense creation (fail-fast)")

    return ExpensePure(
        uid=uid,
        user_uid=user_uid,
        amount=amount,
        currency=currency,
        description=description,
        expense_date=start_date,
        category=category,
        is_recurring=True,
        recurrence_pattern=recurrence_pattern,
        recurrence_end_date=end_date,
        status=ExpenseStatus.PENDING,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def create_budget(
    uid: str,
    user_uid: str,
    name: str,
    period: BudgetPeriod,
    amount_limit: float,
    start_date: date,
    categories: list[ExpenseCategory] | None = None,
    currency: str = "USD",
) -> BudgetPure:
    """Factory function to create a new budget"""
    if not user_uid:
        raise ValueError("user_uid is REQUIRED for budget creation (fail-fast)")

    return BudgetPure(
        uid=uid,
        user_uid=user_uid,
        name=name,
        period=period,
        amount_limit=amount_limit,
        currency=currency,
        start_date=start_date,
        categories=categories or [],
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
