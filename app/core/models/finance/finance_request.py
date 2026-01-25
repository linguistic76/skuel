"""
Finance Request Models (Pydantic)
==================================

Pydantic models for Finance API boundaries (Tier 1 of three-tier architecture).
Handles validation and serialization at the API layer.

Based on finance_schemas.py but aligned with three-tier pattern.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Type literals for strict validation
ExpenseStatusLiteral = Literal["pending", "cleared", "reconciled", "disputed", "cancelled"]
PaymentMethodLiteral = Literal[
    "cash",
    "credit_card",
    "debit_card",
    "bank_transfer",
    "check",
    "paypal",
    "venmo",
    "crypto",
    "other",
]
ExpenseCategoryLiteral = Literal["personal", "2222", "skuel"]
RecurrencePatternLiteral = Literal[
    "daily", "weekly", "biweekly", "monthly", "quarterly", "semiannual", "annual"
]
BudgetPeriodLiteral = Literal["weekly", "monthly", "quarterly", "yearly"]


# ============================================================================
# EXPENSE REQUEST MODELS
# ============================================================================


class ExpenseCreateRequest(BaseModel):
    """Request model for creating an expense"""

    # Core fields
    amount: float = Field(gt=0, description="Expense amount")
    description: str = Field(min_length=1, max_length=200, description="Expense description")
    expense_date: date = Field(description="Date of expense")

    # Classification
    category: ExpenseCategoryLiteral = Field(description="Main expense category")
    subcategory: str | None = Field(default=None, max_length=50, description="Subcategory")

    # Payment info
    payment_method: PaymentMethodLiteral = Field(default="other", description="Payment method")
    vendor: str | None = Field(default=None, max_length=100, description="Vendor name")
    currency: str = Field(default="USD", max_length=3, description="Currency code")

    # Tax and reimbursement
    tax_deductible: bool = Field(default=False, description="Is tax deductible")
    reimbursable: bool = Field(default=False, description="Is reimbursable")
    tax_amount: float = Field(default=0.0, ge=0, description="Tax amount")

    # Documentation
    receipt_url: str | None = Field(default=None, description="Receipt URL")
    notes: str | None = Field(default=None, max_length=500, description="Additional notes")

    # Tags for flexible categorization
    tags: list[str] = Field(default_factory=list, description="Additional tags")

    # Recurring setup
    is_recurring: bool = Field(default=False, description="Is this a recurring expense")
    recurrence_pattern: RecurrencePatternLiteral | None = Field(default=None)
    recurrence_end_date: date | None = Field(default=None)

    # Budget association
    budget_uid: str | None = Field(default=None, description="Associated budget UID")

    @field_validator("subcategory")
    @classmethod
    def validate_subcategory(cls, v: str | None, info) -> str | None:
        """Validate subcategory based on category"""
        if v is None:
            return v

        category = info.data.get("category")
        if not category:
            return v

        # Define valid subcategories per category
        valid_subcategories = {
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

        if category in valid_subcategories and v not in valid_subcategories[category]:
            raise ValueError(f"Invalid subcategory '{v}' for category '{category}'")

        return v

    @field_validator("recurrence_end_date")
    @classmethod
    def validate_recurrence_end_date(cls, v: date | None, info) -> date | None:
        """Ensure recurrence_end_date is after expense_date if recurring"""
        if v is None:
            return v

        is_recurring = info.data.get("is_recurring")
        if not is_recurring:
            return None  # Clear end date if not recurring

        expense_date = info.data.get("expense_date")
        if expense_date and v <= expense_date:
            raise ValueError("recurrence_end_date must be after expense_date")

        return v


class ExpenseUpdateRequest(BaseModel):
    """Request model for updating an expense"""

    # All fields optional for updates
    amount: float | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, min_length=1, max_length=200)
    expense_date: date | None = Field(default=None)

    # Classification
    category: ExpenseCategoryLiteral | None = Field(default=None)
    subcategory: str | None = Field(default=None, max_length=50)

    # Payment info
    payment_method: PaymentMethodLiteral | None = Field(default=None)
    vendor: str | None = Field(default=None, max_length=100)

    # Status
    status: ExpenseStatusLiteral | None = Field(default=None)

    # Tax and reimbursement
    tax_deductible: bool | None = Field(default=None)
    reimbursable: bool | None = Field(default=None)
    tax_amount: float | None = Field(default=None, ge=0)

    # Documentation
    receipt_url: str | None = Field(default=None)
    notes: str | None = Field(default=None, max_length=500)

    # Other fields
    tags: list[str] | None = Field(default=None)
    budget_uid: str | None = Field(default=None)


# ============================================================================
# BUDGET REQUEST MODELS
# ============================================================================


class BudgetCreateRequest(BaseModel):
    """Request model for creating a budget"""

    name: str = Field(min_length=1, max_length=100, description="Budget name")
    period: BudgetPeriodLiteral = Field(description="Budget period type")
    amount_limit: float = Field(gt=0, description="Budget limit amount")

    # Time bounds
    start_date: date = Field(description="Budget start date")
    end_date: date | None = Field(default=None, description="Budget end date")

    # Categories
    categories: list[ExpenseCategoryLiteral] = Field(
        default_factory=list, description="Categories included in budget"
    )

    # Currency
    currency: str = Field(default="USD", max_length=3, description="Currency code")

    # Configuration
    alert_threshold: float = Field(
        default=0.8, ge=0.1, le=1.0, description="Alert threshold (0.1-1.0)"
    )
    notes: str | None = Field(default=None, max_length=500)
    tags: list[str] = Field(default_factory=list, description="Budget tags")

    @field_validator("end_date")
    @classmethod
    def validate_end_date(cls, v: date | None, info) -> date | None:
        """Ensure end_date is after start_date"""
        if v is None:
            return v

        start_date = info.data.get("start_date")
        if start_date and v <= start_date:
            raise ValueError("end_date must be after start_date")

        return v


class BudgetUpdateRequest(BaseModel):
    """Request model for updating a budget"""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    amount_limit: float | None = Field(default=None, gt=0)
    end_date: date | None = Field(default=None)
    categories: list[ExpenseCategoryLiteral] | None = Field(default=None)
    alert_threshold: float | None = Field(default=None, ge=0.1, le=1.0)
    notes: str | None = Field(default=None, max_length=500)
    tags: list[str] | None = Field(default=None)


# ============================================================================
# FILTER REQUEST MODELS
# ============================================================================


class ExpenseFilterRequest(BaseModel):
    """Request model for filtering expenses"""

    # Date filters
    start_date: date | None = Field(default=None)
    end_date: date | None = Field(default=None)

    # Amount filters
    min_amount: float | None = Field(default=None, ge=0)
    max_amount: float | None = Field(default=None, gt=0)

    # Category filters
    categories: list[ExpenseCategoryLiteral] | None = Field(default=None)
    subcategories: list[str] | None = Field(default=None)

    # Status filter
    status: ExpenseStatusLiteral | None = Field(default=None)

    # Other filters
    is_recurring: bool | None = Field(default=None)
    tax_deductible: bool | None = Field(default=None)
    reimbursable: bool | None = Field(default=None)
    vendor: str | None = Field(default=None)
    payment_method: PaymentMethodLiteral | None = Field(default=None)

    # Search
    search_query: str | None = Field(default=None, max_length=100)

    # Tags
    tags: list[str] | None = Field(default=None)

    # Budget association
    budget_uid: str | None = Field(default=None)

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, v: date | None, info) -> date | None:
        """Ensure end_date is after start_date"""
        if v is None:
            return v

        start_date = info.data.get("start_date")
        if start_date and v < start_date:
            raise ValueError("end_date must be after or equal to start_date")

        return v

    @field_validator("max_amount")
    @classmethod
    def validate_amount_range(cls, v: float | None, info) -> float | None:
        """Ensure max_amount is greater than min_amount"""
        if v is None:
            return v

        min_amount = info.data.get("min_amount")
        if min_amount is not None and v <= min_amount:
            raise ValueError("max_amount must be greater than min_amount")

        return v


class BudgetFilterRequest(BaseModel):
    """Request model for filtering budgets"""

    # Period filter
    period: BudgetPeriodLiteral | None = Field(default=None)

    # Date filters
    active_on_date: date | None = Field(
        default=None, description="Find budgets active on this date"
    )

    # Category filter
    categories: list[ExpenseCategoryLiteral] | None = Field(default=None)

    # Status filters
    include_exceeded: bool = Field(default=True, description="Include exceeded budgets")
    only_near_limit: bool = Field(default=False, description="Only show budgets near limit")

    # Tags
    tags: list[str] | None = Field(default=None)

    # Search
    search_query: str | None = Field(default=None, max_length=100)


# ============================================================================
# REPORT REQUEST MODELS
# ============================================================================


class ExpenseReportRequest(BaseModel):
    """Request model for expense reports"""

    report_type: Literal["summary", "detailed", "category_breakdown", "trend_analysis"] = Field(
        default="summary", description="Type of report to generate"
    )

    # Time period
    start_date: date = Field(description="Report start date")
    end_date: date = Field(description="Report end date")

    # Grouping
    group_by: Literal["day", "week", "month", "quarter", "year", "category", "vendor"] | None = (
        Field(default=None, description="How to group the data")
    )

    # Filters
    categories: list[ExpenseCategoryLiteral] | None = Field(default=None)
    include_recurring: bool = Field(default=True)
    include_cancelled: bool = Field(default=False)

    # Options
    include_tax_summary: bool = Field(default=False)
    include_budget_comparison: bool = Field(default=False)

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, v: date, info) -> date:
        """Ensure end_date is after start_date"""
        start_date = info.data.get("start_date")
        if start_date and v <= start_date:
            raise ValueError("end_date must be after start_date")

        return v


class BudgetAnalysisRequest(BaseModel):
    """Request model for budget analysis"""

    budget_uid: str = Field(description="Budget UID to analyze")

    # Time period (optional, defaults to budget period)
    start_date: date | None = Field(default=None)
    end_date: date | None = Field(default=None)

    # Analysis options
    include_projections: bool = Field(default=False, description="Include spending projections")
    include_category_breakdown: bool = Field(default=True)
    include_trend_analysis: bool = Field(default=False)
    include_recommendations: bool = Field(default=False)
