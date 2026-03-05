"""
Finance Reporting Service
=========================

Specialized service for financial reporting and summaries.

Handles:
- Monthly reports
- Expense summaries grouped by various dimensions
- Tax reporting
- Financial analysis and insights

This is part of the Finance domain's 5-sub-service architecture.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import TYPE_CHECKING, Any

from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.finance.finance_pure import ExpenseCategory, ExpensePure
    from core.ports.domain_protocols import FinancesOperations


class FinanceReportingService:
    """
    Financial reporting service.

    Generates reports, summaries, and analyses of expense data.
    Works with FinanceCoreService to access expense records.
    """

    def __init__(self, backend: FinancesOperations) -> None:
        """
        Initialize reporting service.

        Args:
            backend: Protocol-based backend for finance operations
        """
        self.backend = backend
        self.logger = get_logger(__name__)

    # ========================================================================
    # MONTHLY REPORTS
    # ========================================================================

    @with_error_handling("generate_monthly_report", error_type="database")
    async def generate_monthly_report(self, user_uid: str, year: int, month: int) -> Result[dict]:
        """
        Generate monthly financial report.

        Args:
            user_uid: User UID
            year: Report year
            month: Report month (1-12)

        Returns:
            Result containing monthly report dictionary with:
            - year: int
            - month: int
            - total_expenses: float
            - expense_count: int
            - by_category: dict[str, float]
            - by_payment_method: dict[str, float]
            - average_expense: float
            - tax_deductible_total: float
        """
        # Calculate date range
        _, last_day = monthrange(year, month)
        from_date = date(year, month, 1)
        to_date = date(year, month, last_day)

        # Get all expenses for the month (protocol-compliant call)
        result = await self.backend.find_expenses_by_date_range(start=from_date, end=to_date)

        if result.is_error:
            return Result.fail(result.expect_error())

        # Service-layer filtering: filter by user_uid
        all_expenses = result.value
        expenses = [e for e in all_expenses if getattr(e, "user_uid", None) == user_uid]

        # Calculate totals by category
        by_category: dict[str, float] = {}
        by_payment_method: dict[str, float] = {}
        total = 0.0

        for expense in expenses:
            # By category
            cat = expense.category.value if expense.category else "uncategorized"
            by_category[cat] = by_category.get(cat, 0.0) + expense.amount

            # By payment method
            method = expense.payment_method.value if expense.payment_method else "unknown"
            by_payment_method[method] = by_payment_method.get(method, 0.0) + expense.amount

            total += expense.amount

        report = {
            "year": year,
            "month": month,
            "total_expenses": total,
            "expense_count": len(expenses),
            "by_category": by_category,
            "by_payment_method": by_payment_method,
            "average_expense": total / len(expenses) if expenses else 0,
            "tax_deductible_total": sum(e.amount for e in expenses if e.tax_deductible),
        }

        return Result.ok(report)

    # ========================================================================
    # EXPENSE SUMMARIES
    # ========================================================================

    @with_error_handling("get_expense_summary", error_type="database")
    async def get_expense_summary(
        self,
        user_uid: str,
        from_date: date | None = None,
        to_date: date | None = None,
        group_by: str = "category",
    ) -> Result[dict]:
        """
        Get expense summary grouped by specified field.

        Args:
            user_uid: User UID
            from_date: Optional start date filter
            to_date: Optional end date filter
            group_by: Grouping dimension ("category", "payment_method", "status")

        Returns:
            Result containing summary dictionary with:
            - from_date: str | None
            - to_date: str | None
            - grouped_by: str
            - groups: dict[str, dict] - group data with total, count, items
            - grand_total: float
            - total_count: int
        """
        # Get expenses
        if from_date and to_date:
            # Protocol-compliant call
            result = await self.backend.find_expenses_by_date_range(start=from_date, end=to_date)
            if result.is_error:
                return Result.fail(result.expect_error())

            # Service-layer filtering: filter by user_uid
            all_expenses = result.value
            expenses = [e for e in all_expenses if getattr(e, "user_uid", None) == user_uid]
        else:
            # Get all expenses for user
            result = await self.backend.find_by(user_uid=user_uid)
            if result.is_error:
                return Result.fail(result.expect_error())
            expenses = result.value

        # Group expenses
        grouped: dict[str, Any] = {}
        for expense in expenses:
            if group_by == "category":
                key = expense.category.value if expense.category else "uncategorized"
            elif group_by == "payment_method":
                key = expense.payment_method.value if expense.payment_method else "unknown"
            elif group_by == "status":
                key = expense.status.value if expense.status else "unknown"
            else:
                key = "all"

            if key not in grouped:
                grouped[key] = {"total": 0.0, "count": 0, "items": []}

            grouped[key]["total"] += expense.amount
            grouped[key]["count"] += 1
            grouped[key]["items"].append(expense.uid)

        # Calculate grand total
        grand_total = sum(g["total"] for g in grouped.values())

        summary = {
            "from_date": from_date.isoformat() if from_date else None,
            "to_date": to_date.isoformat() if to_date else None,
            "grouped_by": group_by,
            "groups": grouped,
            "grand_total": grand_total,
            "total_count": sum(g["count"] for g in grouped.values()),
        }

        return Result.ok(summary)

    # ========================================================================
    # TAX REPORTING
    # ========================================================================

    @with_error_handling("get_tax_deductible_expenses", error_type="database")
    async def get_tax_deductible_expenses(
        self, user_uid: str, year: int
    ) -> Result[list[ExpensePure]]:
        """
        Get all tax-deductible expenses for a year.

        Args:
            user_uid: User UID
            year: Tax year

        Returns:
            Result containing list of tax-deductible ExpensePure
        """
        from_date = date(year, 1, 1)
        to_date = date(year, 12, 31)

        # Get tax-deductible expenses
        result = await self.backend.find_by(user_uid=user_uid, tax_deductible=True)

        if result.is_error:
            return Result.fail(result.expect_error())

        expenses = result.value

        # Filter by year
        yearly_expenses = [e for e in expenses if from_date <= e.expense_date <= to_date]

        return Result.ok(yearly_expenses)

    # ========================================================================
    # CATEGORY ANALYSIS
    # ========================================================================

    @with_error_handling("get_expenses_by_category", error_type="database")
    async def get_expenses_by_category(
        self,
        user_uid: str,
        category: ExpenseCategory,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> Result[list[ExpensePure]]:
        """
        Find expenses by category and optional date range.

        Args:
            user_uid: User UID
            category: Expense category
            from_date: Optional start date
            to_date: Optional end date

        Returns:
            Result containing list of ExpensePure
        """
        # Protocol-compliant call (category only)
        result = await self.backend.find_expenses_by_category(category)

        if result.is_error:
            return Result.fail(result.expect_error())

        expenses = result.value

        # Service-layer filtering: filter by user_uid and date range
        expenses = [e for e in expenses if getattr(e, "user_uid", None) == user_uid]

        if from_date and to_date:
            expenses = [e for e in expenses if from_date <= e.expense_date <= to_date]

        return Result.ok(expenses)
