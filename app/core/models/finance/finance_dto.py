"""
Finance DTO Models
==================

Data Transfer Objects for Finance domain (Tier 2 of three-tier architecture).
Mutable dataclasses for transferring data between layers.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any

# Finance enums consolidated in /core/models/enums/finance_enums.py (January 2026)
from core.models.enums.finance_enums import (
    BudgetPeriod,
    ExpenseCategory,
    ExpenseStatus,
    PaymentMethod,
    RecurrencePattern,
)

# ============================================================================
# EXPENSE DTOs
# ============================================================================


@dataclass
class ExpenseDTO:
    """
    Mutable DTO for expense data transfer between layers.

    Used to move data between:
    - API layer (Pydantic) and Service layer
    - Service layer and Repository/Backend layer
    - Service layer and Domain model (Pure)
    """

    # Identity
    uid: str

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
    account_uid: str | None = (None,)
    vendor: str | None = None

    # Status
    status: ExpenseStatus = ExpenseStatus.PENDING

    # Tax and reimbursement
    tax_deductible: bool = False
    reimbursable: bool = False
    tax_amount: float = 0.0

    # Documentation
    receipt_url: str | None = (None,)
    notes: str | None = None

    # Recurring expense fields
    is_recurring: bool = False
    recurrence_pattern: RecurrencePattern | None = (None,)
    recurrence_end_date: date | None = (None,)
    parent_expense_uid: str | None = None

    # Budget tracking
    budget_uid: str | None = (None,)
    budget_category: str | None = None

    # Metadata
    tags: list[str] = (field(default_factory=list),)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Audit fields
    created_at: datetime = (field(default_factory=datetime.now),)
    updated_at: datetime = (field(default_factory=datetime.now),)
    created_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert DTO to dictionary for serialization"""
        from dataclasses import asdict

        from core.models.dto_helpers import (
            convert_dates_to_iso,
            convert_datetimes_to_iso,
            convert_enums_to_values,
        )

        data = asdict(self)

        # Convert enums to values
        convert_enums_to_values(
            data, ["category", "payment_method", "status", "recurrence_pattern"]
        )

        # Convert dates to ISO format
        convert_dates_to_iso(data, ["expense_date", "recurrence_end_date"])

        # Convert datetimes to ISO format
        convert_datetimes_to_iso(data, ["created_at", "updated_at"])

        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExpenseDTO":
        """Create DTO from dictionary"""
        from core.models.dto_helpers import (
            parse_date_fields,
            parse_datetime_fields,
            parse_enum_field,
        )

        # Parse dates
        parse_date_fields(data, ["expense_date", "recurrence_end_date"])

        # Parse datetimes
        parse_datetime_fields(data, ["created_at", "updated_at"])

        # Parse enums
        parse_enum_field(data, "category", ExpenseCategory)
        parse_enum_field(data, "payment_method", PaymentMethod)
        parse_enum_field(data, "status", ExpenseStatus)
        parse_enum_field(data, "recurrence_pattern", RecurrencePattern)

        return cls(**data)


# ============================================================================
# BUDGET DTOs
# ============================================================================


@dataclass
class BudgetDTO:
    """
    Mutable DTO for budget data transfer between layers.
    """

    # Identity
    uid: str
    name: str

    # Budget configuration
    period: BudgetPeriod
    amount_limit: float
    currency: str

    # Time bounds
    start_date: date
    end_date: date | None = None

    # Ownership
    user_uid: str | None = None

    # Categories covered
    categories: list[ExpenseCategory] = field(default_factory=list)

    # Current tracking
    amount_spent: float = 0.0
    expense_count: int = 0

    # Alerts
    alert_threshold: float = 0.8
    is_exceeded: bool = False

    # Metadata
    notes: str | None = (None,)

    tags: list[str] = field(default_factory=list)

    # Audit
    created_at: datetime = (field(default_factory=datetime.now),)
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert DTO to dictionary for serialization"""
        return {
            "uid": self.uid,
            "name": self.name,
            "user_uid": self.user_uid,
            "period": self.period.value if isinstance(self.period, Enum) else self.period,
            "amount_limit": self.amount_limit,
            "currency": self.currency,
            "start_date": self.start_date.isoformat()
            if isinstance(self.start_date, date)
            else self.start_date,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "categories": [cat.value if isinstance(cat, Enum) else cat for cat in self.categories],
            "amount_spent": self.amount_spent,
            "expense_count": self.expense_count,
            "alert_threshold": self.alert_threshold,
            "is_exceeded": self.is_exceeded,
            "notes": self.notes,
            "tags": self.tags,
            "created_at": self.created_at.isoformat()
            if isinstance(self.created_at, datetime)
            else self.created_at,
            "updated_at": self.updated_at.isoformat()
            if isinstance(self.updated_at, datetime)
            else self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BudgetDTO":
        """Create DTO from dictionary"""
        # Convert string dates to date objects
        if "start_date" in data and isinstance(data["start_date"], str):
            data["start_date"] = date.fromisoformat(data["start_date"])
        if "end_date" in data and isinstance(data["end_date"], str):
            data["end_date"] = date.fromisoformat(data["end_date"])

        # Convert string datetimes to datetime objects
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data and isinstance(data["updated_at"], str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])

        # Convert string enums to Enum objects
        if "period" in data and isinstance(data["period"], str):
            data["period"] = BudgetPeriod(data["period"])
        if "categories" in data:
            data["categories"] = [
                ExpenseCategory(cat) if isinstance(cat, str) else cat for cat in data["categories"]
            ]

        return cls(**data)


# ============================================================================
# REPORT DTOs
# ============================================================================


@dataclass
class ExpenseReportDTO:
    """DTO for expense report data"""

    report_type: str
    start_date: date
    end_date: date

    # Summary stats
    total_amount: float = 0.0
    total_count: int = 0
    average_amount: float = 0.0

    # Category breakdown
    category_totals: dict[str, float] = (field(default_factory=dict),)
    category_counts: dict[str, int] = field(default_factory=dict)

    # Time series data
    daily_totals: dict[str, float] = (field(default_factory=dict),)
    monthly_totals: dict[str, float] = field(default_factory=dict)

    # Top items
    largest_expenses: list[ExpenseDTO] = (field(default_factory=list),)
    most_frequent_vendors: dict[str, int] = field(default_factory=dict)

    # Tax summary
    tax_deductible_total: float = 0.0
    tax_amount_total: float = 0.0

    # Budget comparison
    budget_comparisons: list[dict[str, Any]] = field(default_factory=list)

    # Metadata
    generated_at: datetime = (field(default_factory=datetime.now),)
    filters_applied: dict[str, Any] = field(default_factory=dict)


@dataclass
class BudgetAnalysisDTO:
    """DTO for budget analysis data"""

    budget_uid: str
    budget_name: str
    period: BudgetPeriod

    # Period analyzed
    analysis_start: date
    analysis_end: date

    # Current status
    amount_limit: float
    amount_spent: float
    amount_remaining: float
    utilization_percentage: float

    # Projections
    projected_end_amount: float | None = (None,)

    projected_over_under: float | None = (None,)
    days_until_exceeded: int | None = None

    # Category breakdown
    category_spending: dict[str, float] = (field(default_factory=dict),)
    category_percentages: dict[str, float] = field(default_factory=dict)

    # Trend analysis
    daily_average: float = 0.0
    weekly_average: float = 0.0
    spending_trend: str = "stable"  # "increasing", "decreasing", "stable"

    # Recommendations
    recommendations: list[str] = field(default_factory=list)

    # Metadata
    generated_at: datetime = field(default_factory=datetime.now)
