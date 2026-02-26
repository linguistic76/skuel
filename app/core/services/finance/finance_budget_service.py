"""
Finance Budget Service
=====================

Specialized service for budget management operations.

Handles:
- Budget creation and validation
- Active budget queries
- Budget status calculation
- Budget-expense relationship tracking

This is part of the Finance domain's 5-sub-service architecture.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.finance.finance_pure import BudgetPure, ExpenseCategory
    from core.ports.domain_protocols import FinancesOperations


class FinanceBudgetService:
    """
    Budget management service.

    Handles budget creation, tracking, and status calculations.
    Works with FinanceCoreService to analyze expense-budget relationships.


    Source Tag: "finance_budget_explicit"
    - Format: "finance_budget_explicit" for user-created relationships
    - Format: "finance_budget_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from finance metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (uses pure Cypher)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(self, backend: FinancesOperations) -> None:
        """
        Initialize budget service.

        Args:
            backend: Protocol-based backend for finance operations
        """
        self.backend = backend
        self.logger = get_logger(__name__)

    # ========================================================================
    # BUDGET CRUD OPERATIONS
    # ========================================================================

    @with_error_handling("create_budget", error_type="database")
    async def create_budget(self, budget: BudgetPure) -> Result[BudgetPure]:
        """
        Create a new budget.

        Args:
            budget: Budget to create

        Returns:
            Result containing created BudgetPure
        """
        # Validate budget
        if budget.amount_limit <= 0:
            return Result.fail(
                Errors.validation(message="Budget limit must be positive", field="limit")
            )

        # Validate end_date if provided
        if budget.end_date and budget.end_date <= budget.start_date:
            return Result.fail(
                Errors.validation(message="End date must be after start date", field="end_date")
            )

        # Check for overlapping budgets in any of the budget's categories
        all_budgets = []
        if budget.categories:
            for category in budget.categories:
                result = await self.backend.find_budgets_by_category(category)
                if result.is_ok:
                    all_budgets.extend(result.value)

        # Service-layer filtering: check for date overlap
        # Only check overlap if budget has an end_date
        existing = []
        if budget.end_date:
            existing = [
                b
                for b in all_budgets
                if b.start_date <= budget.end_date
                and (b.end_date is None or b.end_date >= budget.start_date)
            ]

        if existing:
            return Result.fail(
                Errors.business(
                    "budget_overlap", "Overlapping budget exists for this category and period"
                )
            )

        # Convert to dict for backend
        budget_dict = {
            "uid": budget.uid,
            "user_uid": budget.user_uid,
            "amount_limit": budget.amount_limit,
            "start_date": budget.start_date.isoformat(),
            "end_date": budget.end_date.isoformat() if budget.end_date else None,
            "categories": [cat.value for cat in budget.categories] if budget.categories else [],
        }

        # Create budget (returns UID)
        create_result = await self.backend.create_budget(budget_dict)
        if create_result.is_error:
            return Result.fail(create_result.expect_error())

        budget_uid = create_result.value

        # Retrieve created budget
        get_result = await self.backend.get_budget(budget_uid)
        if get_result.is_error:
            return Result.fail(get_result.expect_error())

        created = get_result.value
        if not created:
            return Result.fail(
                Errors.system(
                    message="Budget creation succeeded but retrieval failed",
                    operation="create_budget",
                )
            )

        self.logger.info(f"Budget created: {created.uid}")
        return Result.ok(created)

    @with_error_handling("get_budget", error_type="database", uid_param="uid")
    async def get_budget(self, uid: str) -> Result[BudgetPure]:
        """
        Get a budget by UID.

        Args:
            uid: Budget UID

        Returns:
            Result containing BudgetPure
        """
        budget = await self.backend.get_budget(uid)
        if not budget:
            return Result.fail(Errors.not_found("Budget", uid))
        return Result.ok(budget)

    @with_error_handling("get_active_budgets", error_type="database")
    async def get_active_budgets(self, as_of_date: date | None = None) -> Result[list[BudgetPure]]:
        """
        Get all active budgets.

        Args:
            as_of_date: Date to check (defaults to today)

        Returns:
            Result containing list of active BudgetPure
        """
        check_date = as_of_date or date.today()

        # Protocol-compliant call (no parameters)
        result = await self.backend.get_active_budgets()

        if result.is_error:
            return result

        all_budgets = result.value

        # Service-layer filtering: filter by active status as of check_date
        # Budget is active if start_date <= check_date and (end_date is None or check_date <= end_date)
        budgets = [
            b
            for b in all_budgets
            if b.start_date <= check_date and (b.end_date is None or check_date <= b.end_date)
        ]

        return Result.ok(budgets)

    # ========================================================================
    # BUDGET STATUS CALCULATIONS
    # ========================================================================

    @with_error_handling("calculate_budget_status", error_type="database", uid_param="budget_uid")
    async def calculate_budget_status(self, budget_uid: str) -> Result[dict]:
        """
        Calculate current status of a budget.

        Requires access to expense data, so coordinates with backend
        to fetch both budget and related expenses.

        Args:
            budget_uid: Budget UID

        Returns:
            Result containing budget status dictionary with:
            - budget_uid: str
            - category: str
            - limit: float
            - spent: float
            - remaining: float
            - percentage_used: float
            - is_over_budget: bool
            - days_elapsed: int
            - days_remaining: int
            - daily_burn_rate: float
            - projected_total: float
            - projected_over_under: float
            - expense_count: int
        """
        # Get budget
        result = await self.get_budget(budget_uid)
        if result.is_error:
            return Result.fail(result.expect_error())

        budget = result.value

        # Budget status requires an end_date for time-based metrics
        if budget.end_date is None:
            return Result.fail(
                Errors.validation(
                    message="Budget must have an end_date to calculate status metrics",
                    field="end_date",
                )
            )

        # Get expenses for all categories in budget
        all_expenses = []
        if budget.categories:
            for category in budget.categories:
                result = await self.backend.find_expenses_by_category(category)
                if result.is_ok:
                    all_expenses.extend(result.value)

        # Service-layer filtering: filter by date range and user
        # Include expenses from start_date onwards, up to end_date if specified
        expenses = [
            e
            for e in all_expenses
            if budget.start_date <= e.expense_date
            and (budget.end_date is None or e.expense_date <= budget.end_date)
            and getattr(e, "user_uid", None) == budget.user_uid
        ]

        # Calculate totals
        total_spent = sum(e.amount for e in expenses)
        remaining = budget.amount_limit - total_spent
        percentage_used = (
            (total_spent / budget.amount_limit * 100) if budget.amount_limit > 0 else 0
        )

        # Calculate days
        total_days = (budget.end_date - budget.start_date).days + 1
        elapsed_days = (date.today() - budget.start_date).days + 1
        remaining_days = max(0, (budget.end_date - date.today()).days + 1)

        # Calculate burn rate
        daily_burn_rate = total_spent / elapsed_days if elapsed_days > 0 else 0
        projected_total = daily_burn_rate * total_days

        status = {
            "budget_uid": budget_uid,
            "categories": [cat.value for cat in budget.categories] if budget.categories else [],
            "limit": budget.amount_limit,
            "spent": total_spent,
            "remaining": remaining,
            "percentage_used": percentage_used,
            "is_over_budget": total_spent > budget.amount_limit,
            "days_elapsed": elapsed_days,
            "days_remaining": remaining_days,
            "daily_burn_rate": daily_burn_rate,
            "projected_total": projected_total,
            "projected_over_under": projected_total - budget.amount_limit,
            "expense_count": len(expenses),
        }

        return Result.ok(status)

    @with_error_handling("get_budgets_by_category", error_type="database")
    async def get_budgets_by_category(
        self,
        category: ExpenseCategory,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> Result[list[BudgetPure]]:
        """
        Get budgets for a specific category.

        Args:
            category: Expense category
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Result containing list of BudgetPure
        """
        # Protocol-compliant call
        result = await self.backend.find_budgets_by_category(category)

        if result.is_error:
            return result

        budgets = result.value

        # Service-layer filtering: filter by date range if provided
        if start_date and end_date:
            budgets = [
                b
                for b in budgets
                if b.start_date <= end_date and (b.end_date is None or b.end_date >= start_date)
            ]

        return Result.ok(budgets)
