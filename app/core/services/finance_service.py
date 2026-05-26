"""
Finance Service (Facade)
========================

*Last updated: 2026-01-17*

Standalone facade service that orchestrates finance operations across specialized sub-services.

Architecture Pattern:
--------------------
Finance is a standalone bookkeeping domain. Simple, focused on tracking
expenses, budgets, actuals, revenue, and invoices. No cross-domain
intelligence or unified architecture complexity.

FinanceService (Standalone Facade)
    ├── FinanceCoreService - CRUD operations with event publishing
    ├── FinanceBudgetService - Budget management
    ├── FinanceReportingService - Reports and summaries
    └── FinanceInvoiceService - Invoice management (optional)

This facade:
- Provides unified API for all finance operations
- Delegates to specialized sub-services
- Handles event publishing for domain events
- Manages category configuration
- Orchestrates complex cross-service operations

Security:
---------
Finance is admin-only. Route-level security is enforced via @require_admin.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any, TypedDict

from core.constants import QueryLimit
from core.events import publish_event
from core.events.finance_events import (
    ExpenseCreated,
    ExpenseDeleted,
    ExpensePaid,
    ExpenseUpdated,
)
from core.models.finance.finance_pure import (
    BudgetPure,
    ExpenseCategory,
    ExpensePure,
    ExpenseStatus,
)
from core.models.finance.invoice import InvoicePure
from core.models.type_hints import UserUID
from core.ports.domain_protocols import FinancesOperations
from core.ports.query_types import InvoiceStats
from core.services.finance import (
    FinanceBudgetService,
    FinanceCoreService,
    FinanceReportingService,
)
from core.services.finance.finance_categories import (
    CategoryHierarchy,
    get_category,
    load_finance_categories,
    suggest_category,
    validate_category,
)
from core.services.finance.finance_invoice_service import FinanceInvoiceService
from core.services.finance_types import CategoryInfo, CategorySuggestion
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.finance_protocols import InvoiceRenderer
    from core.ports.infrastructure_protocols import EventBusOperations


# ============================================================================
# FINANCE CONTEXT TYPEDDICTS
# ============================================================================


class FinanceDashboardContext(TypedDict):
    """Return type for FinanceService.get_dashboard_context()."""

    total_spent: float
    total_budget: float
    budget_utilization: float
    health_status: str
    budget_health: str
    recent_expenses: list[dict[str, Any]]
    budget_alerts: list[dict[str, str]]


class FinanceBudgetsContext(TypedDict):
    """Return type for FinanceService.get_budgets_context()."""

    budgets: list[dict[str, Any]]
    total_budgeted: float
    total_spent: float


class FinanceReportsContext(TypedDict):
    """Return type for FinanceService.get_reports_context()."""

    monthly_summary: dict[str, Any]
    category_breakdown: list[dict[str, Any]]
    tax_summary: dict[str, Any]


class FinanceAnalyticsContext(TypedDict):
    """Return type for FinanceService.get_analytics_context()."""

    health_score: float
    health_tier: str
    spending_pattern: str
    budget_adherence: float


class FinanceExpensesContext(TypedDict):
    """Return type for FinanceService.get_expenses_context()."""

    expenses: list[dict[str, Any]]
    categories: list[dict[str, str]]
    total_count: int


class FinanceInvoicesContext(TypedDict):
    """Return type for FinanceService.get_invoices_context()."""

    invoices: list[dict[str, Any]]
    stats: dict[str, Any]


class FinanceService:
    """
    Finance facade service (standalone).

    Orchestrates all finance operations by delegating to specialized sub-services:
    - FinanceCoreService: Basic CRUD with event publishing
    - FinanceBudgetService: Budget management
    - FinanceReportingService: Reports and summaries
    - FinanceInvoiceService: Invoice management (optional)

    This facade provides:
    - Event publishing for domain events (expense created/updated/deleted)
    - Category management
    - Recurring expense creation
    - Unified API surface for all finance operations

    Finance is a standalone bookkeeping domain:
    - No BaseService inheritance
    - No cross-domain intelligence
    - No graph relationship configuration
    - Simple, focused on tracking expenses and budgets

    SKUEL Architecture:
    - Standalone service (no unified architecture patterns)
    """

    def __init__(
        self,
        backend: FinancesOperations,
        event_bus: EventBusOperations | None = None,
        invoice_backend: Any | None = None,
        invoice_renderer: InvoiceRenderer | None = None,
    ) -> None:
        """
        Initialize finance facade with all sub-services.

        FAIL-FAST ARCHITECTURE (per CLAUDE.md):
        Backend is REQUIRED. Services run at full capacity or fail immediately
        at startup.

        Args:
            backend: Protocol-based backend for finance operations - REQUIRED
            event_bus: Event bus for publishing domain events (optional)
            invoice_backend: Backend for invoice operations (optional)
            invoice_renderer: Outbound PDF renderer for invoices. REQUIRED when
                invoice_backend is provided — injected at the composition root so
                the service layer never imports the renderer (ADR-044/SKUEL022).
        """
        if not backend:
            raise ValueError("Finance backend is required")

        self.logger = get_logger("skuel.services.finance")

        # Initialize all sub-services
        self.core = FinanceCoreService(backend, event_bus)
        self.budget = FinanceBudgetService(backend)
        self.reporting = FinanceReportingService(backend)

        # Invoice service (optional - requires separate backend + renderer)
        self.invoice: FinanceInvoiceService | None = None
        if invoice_backend:
            if invoice_renderer is None:
                raise ValueError(
                    "invoice_renderer is required when invoice_backend is provided "
                    "(SKUEL fail-fast — no graceful degradation)."
                )
            self.invoice = FinanceInvoiceService(invoice_backend, invoice_renderer)
            self.logger.info("Invoice service initialized")

        # Store references for facade operations
        self.event_bus = event_bus

        # Load finance categories from YAML config
        self.categories: CategoryHierarchy = load_finance_categories()

        self.logger.debug("FinanceService initialized (standalone bookkeeping)")

    # ========================================================================
    # BACKEND ACCESS FOR ADVANCED QUERIES
    # ========================================================================

    @property
    def backend(self) -> FinancesOperations:
        """
        Access underlying backend for advanced queries.

        Use this for:
        - Statistical queries not covered by service methods
        - Ad-hoc filtering with find_by()
        - Read-only operations

        Prefer service methods when available (they include business logic).
        """
        return self.core.backend

    # ========================================================================
    # CORE CRUD OPERATIONS - Delegate to FinanceCoreService
    # ========================================================================

    async def get_expense(self, expense_uid: str) -> Result[ExpensePure]:
        """Get a specific expense by UID. Not found is an error."""
        return await self.core.get_expense(expense_uid)

    async def get(self, uid: str) -> Result[ExpensePure | None]:
        """Get entity by UID. Returns None if not found."""
        return await self.core.get(uid)

    async def verify_ownership(self, uid: str, user_uid: UserUID) -> Result[ExpensePure]:
        """
        Verify user owns the expense.

        Note: Finance is admin-only domain. This checks that the expense exists
        and belongs to the specified user. Admin sees all; users only see their own.
        """
        result = await self.core.get_expense(uid)
        if result.is_error:
            return result
        expense = result.value
        if expense.user_uid != user_uid:
            return Result.fail(Errors.not_found("Expense", uid))
        return Result.ok(expense)

    async def get_user_expenses(
        self, user_uid: UserUID, limit: int = 100, offset: int = 0
    ) -> Result[tuple[list[ExpensePure], int]]:
        """Get all expenses for a user."""
        return await self.core.get_user_expenses(user_uid, limit, offset)

    async def list_expenses(
        self, limit: int = 100, offset: int = 0, filters: dict | None = None
    ) -> Result[tuple[list[ExpensePure], int]]:
        """List expenses with optional filters."""
        return await self.core.list_expenses(limit, offset, filters)

    async def get_user_items_in_range(
        self, user_uid: UserUID, start_date: date, end_date: date, include_completed: bool = False
    ) -> Result[list[ExpensePure]]:
        """
        Get user's expenses in date range - standard interface for meta-services.

        Unified query API for meta-services (Calendar, Reports).
        Note: Expenses don't filter by completion status (all expenses included).
        """
        # Get all user expenses and filter by date range
        result = await self.core.get_user_expenses(user_uid, limit=1000)
        if result.is_error:
            return Result.fail(result)

        expenses, _total = result.value
        # Filter by date range - expenses use expense_date
        in_range = [e for e in expenses if start_date <= e.expense_date <= end_date]
        return Result.ok(in_range)

    # ========================================================================
    # CRUD WITH EVENT PUBLISHING - Facade-Level Operations
    # ========================================================================

    async def create(self, expense: ExpensePure) -> Result[ExpensePure]:
        """Create expense and publish ExpenseCreated event."""
        result = await self.core.create(expense)

        if result.is_ok:
            expense_created = result.value
            event = ExpenseCreated(
                expense_uid=expense_created.uid,
                user_uid=expense_created.user_uid,
                description=expense_created.description,
                amount=expense_created.amount,
                category=expense_created.category.value,
                expense_date=expense_created.expense_date,
            )
            await publish_event(self.event_bus, event, self.logger)

        return result

    async def update(self, uid: str, updates: dict) -> Result[ExpensePure]:
        """Update expense and publish ExpenseUpdated event."""
        result = await self.core.update(uid, updates)

        if result.is_ok:
            expense = result.value
            event = ExpenseUpdated(
                expense_uid=uid,
                user_uid=expense.user_uid,
                updated_fields=updates,
            )
            await publish_event(self.event_bus, event, self.logger)

        return result

    async def delete(self, uid: str) -> Result[bool]:
        """Delete expense and publish ExpenseDeleted event."""
        # Get expense before deletion for event data
        expense_result = await self.core.get(uid)
        expense_description = "Unknown"
        expense_amount = 0.0
        user_uid = "unknown"

        if expense_result.is_ok and expense_result.value is not None:
            expense = expense_result.value
            expense_description = expense.description
            expense_amount = expense.amount
            user_uid = expense.user_uid

        result = await self.core.delete(uid)

        if result.is_ok:
            event = ExpenseDeleted(
                expense_uid=uid,
                user_uid=UserUID(user_uid),
                description=expense_description,
                amount=expense_amount,
            )
            await publish_event(self.event_bus, event, self.logger)

        return result

    # ========================================================================
    # EXPENSE OPERATIONS - Delegate to FinanceCoreService
    # ========================================================================

    async def mark_expense_paid(
        self, uid: str, payment_date: date | None = None
    ) -> Result[ExpensePure]:
        """Mark an expense as paid."""
        result = await self.core.mark_expense_paid(uid, payment_date)

        # Publish ExpensePaid event in addition to ExpenseUpdated
        if result.is_ok:
            expense = result.value
            event = ExpensePaid(
                expense_uid=uid,
                user_uid=expense.user_uid,
                amount=expense.amount,
                payment_date=payment_date or date.today(),
            )
            await publish_event(self.event_bus, event, self.logger)

        return result

    async def attach_receipt(self, uid: str, receipt_link: str) -> Result[ExpensePure]:
        """Attach a receipt to an expense."""
        return await self.core.attach_receipt(uid, receipt_link)

    # ========================================================================
    # BUDGET OPERATIONS - Delegate to FinanceBudgetService
    # ========================================================================

    async def create_budget(self, budget: BudgetPure) -> Result[BudgetPure]:
        """Create a new budget."""
        return await self.budget.create_budget(budget)

    async def get_budget(self, uid: str) -> Result[BudgetPure]:
        """Get a budget by UID."""
        return await self.budget.get_budget(uid)

    async def get_active_budgets(self, as_of_date: date | None = None) -> Result[list[BudgetPure]]:
        """Get all active budgets."""
        return await self.budget.get_active_budgets(as_of_date)

    async def calculate_budget_status(self, budget_uid: str) -> Result[dict]:
        """Calculate current status of a budget."""
        return await self.budget.calculate_budget_status(budget_uid)

    async def get_budgets_by_category(
        self,
        category: ExpenseCategory,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> Result[list[BudgetPure]]:
        """Get budgets for a specific category."""
        return await self.budget.get_budgets_by_category(category, start_date, end_date)

    # ========================================================================
    # REPORTING OPERATIONS - Delegate to FinanceReportingService
    # ========================================================================

    async def generate_monthly_report(
        self, user_uid: UserUID, year: int, month: int
    ) -> Result[dict]:
        """Generate monthly financial report."""
        return await self.reporting.generate_monthly_report(user_uid, year, month)

    async def get_expense_summary(
        self,
        user_uid: UserUID,
        from_date: date | None = None,
        to_date: date | None = None,
        group_by: str = "category",
    ) -> Result[dict]:
        """Get expense summary grouped by specified field."""
        return await self.reporting.get_expense_summary(user_uid, from_date, to_date, group_by)

    async def get_tax_deductible_expenses(
        self, user_uid: UserUID, year: int
    ) -> Result[list[ExpensePure]]:
        """Get all tax-deductible expenses for a year."""
        return await self.reporting.get_tax_deductible_expenses(user_uid, year)

    async def find_expenses_by_category(
        self,
        user_uid: UserUID,
        category: ExpenseCategory,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> Result[list[ExpensePure]]:
        """Find expenses by category and optional date range."""
        return await self.reporting.get_expenses_by_category(user_uid, category, from_date, to_date)

    # ========================================================================
    # RECURRING EXPENSES - Facade-Level Orchestration
    # ========================================================================

    async def create_recurring_expense(
        self, template: ExpensePure, recurrence_pattern: str, occurrences: int = 12
    ) -> Result[list[ExpensePure]]:
        """
        Create recurring expenses from a template.

        This is a facade-level operation that orchestrates multiple
        create operations across a time series.
        """
        from datetime import timedelta

        created_expenses = []

        try:
            current_date = template.expense_date

            for i in range(occurrences):
                # Create expense copy
                expense_copy = ExpensePure(
                    uid=f"{template.uid}_recur_{i}",
                    user_uid=template.user_uid,
                    amount=template.amount,
                    currency=template.currency,
                    description=f"{template.description} (Recurring {i + 1}/{occurrences})",
                    expense_date=current_date,
                    category=template.category,
                    payment_method=template.payment_method,
                    is_recurring=True,
                    tax_deductible=template.tax_deductible,
                    status=ExpenseStatus.PENDING,
                )

                # Create the expense (with event publishing)
                result = await self.create(expense_copy)
                if result.is_ok:
                    created_expenses.append(result.value)

                # Calculate next date based on pattern
                if recurrence_pattern == "monthly":
                    if current_date.month == 12:
                        current_date = current_date.replace(year=current_date.year + 1, month=1)
                    else:
                        current_date = current_date.replace(month=current_date.month + 1)
                elif recurrence_pattern == "weekly":
                    current_date = current_date + timedelta(weeks=1)
                elif recurrence_pattern == "yearly":
                    current_date = current_date.replace(year=current_date.year + 1)

            return Result.ok(created_expenses)

        except (ValueError, TypeError, AttributeError) as e:
            return Result.fail(Errors.system(message=str(e), operation="create_recurring_expenses"))
        except Exception as e:  # safety-net: catch unexpected errors
            return Result.fail(Errors.system(message=str(e), operation="create_recurring_expenses"))

    # ========================================================================
    # CATEGORY MANAGEMENT METHODS
    # ========================================================================

    def get_all_categories(self) -> CategoryHierarchy:
        """Get complete category hierarchy."""
        return self.categories

    def get_main_categories(self) -> list[dict[str, str]]:
        """Get list of main expense categories."""
        return [
            {"name": cat.name, "code": cat.code, "description": cat.description or ""}
            for cat in self.categories.main_categories
        ]

    def get_subcategories_for(self, main_category_code: str) -> list[dict[str, Any]]:
        """Get subcategories for a main category."""
        subcats = self.categories.subcategories.get(main_category_code, ())
        return [
            {"name": sub.name, "code": sub.code, "tags": list(sub.tags), "parent": sub.parent_code}
            for sub in subcats
        ]

    def validate_expense_category(self, category_code: str) -> Result[bool]:
        """Validate that category code exists in configuration."""
        if validate_category(category_code):
            return Result.ok(True)
        else:
            available = list(self.categories.all_categories.keys())
            return Result.fail(
                Errors.validation(
                    f"Invalid category code: {category_code}",
                    field="category",
                    user_message=f"Category '{category_code}' not found. Available: {', '.join(available[:10])}",
                )
            )

    def suggest_category_for_expense(self, description: str) -> CategorySuggestion | None:
        """Suggest category based on expense description."""
        suggested_code = suggest_category(description)
        if suggested_code:
            category = get_category(suggested_code)
            if category:
                return CategorySuggestion(
                    code=category.code,
                    name=category.name,
                    parent=category.parent_code,
                    confidence="high"
                    if any(tag in description.lower() for tag in category.tags)
                    else "medium",
                )
        return None

    def get_category_info(self, category_code: str) -> CategoryInfo | None:
        """Get detailed information about a category."""
        category = get_category(category_code)
        if category:
            return CategoryInfo(
                name=category.name,
                code=category.code,
                description=category.description,
                tags=list(category.tags),
                parent=category.parent_code,
                path=f"{category.parent_code}.{category.code}"
                if category.parent_code
                else category.code,
            )
        return None

    # ========================================================================
    # EXPENSE SEARCH AND FILTERING - Query Methods
    # ========================================================================

    async def get_expenses_by_date_range(
        self,
        user_uid: UserUID,
        start_date: date,
        end_date: date,
        category: ExpenseCategory | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Result[tuple[list[ExpensePure], int]]:
        """
        Get expenses for a user within a date range.

        Args:
            user_uid: User identifier
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)
            category: Optional category filter
            limit: Max results to return
            offset: Pagination offset

        Returns:
            Tuple of (expenses, total_count)
        """
        # Build filter dictionary
        filters: dict[str, Any] = {
            "user_uid": user_uid,
            "expense_date__gte": start_date,
            "expense_date__lte": end_date,
        }

        if category:
            filters["category"] = category.value

        result = await self.backend.find_by(**filters, limit=limit)

        if result.is_error:
            return Result.fail(result)

        expenses = result.value
        # Count total (may need backend support for accurate count)
        total_count = len(expenses)

        return Result.ok((expenses[:limit], total_count))

    async def search_expenses(
        self,
        query: str,
        user_uid: UserUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Result[tuple[list[ExpensePure], int]]:
        """
        Search expenses by description text.

        Args:
            query: Search query string
            user_uid: Optional user filter
            limit: Max results
            offset: Pagination offset

        Returns:
            Tuple of (matching expenses, total_count)
        """
        # Get all expenses (with optional user filter)
        if user_uid:
            result = await self.core.get_user_expenses(user_uid, limit=1000, offset=0)
        else:
            result = await self.core.list_expenses(limit=1000, offset=0)

        if result.is_error:
            return Result.fail(result)

        expenses, _ = result.value

        # Filter by query string (case-insensitive)
        query_lower = query.lower()
        matching = [
            e
            for e in expenses
            if query_lower in e.description.lower()
            or (e.vendor and query_lower in e.vendor.lower())
            or (e.notes and query_lower in e.notes.lower())
        ]

        # Apply pagination
        total_count = len(matching)
        paginated = matching[offset : offset + limit]

        return Result.ok((paginated, total_count))

    # ========================================================================
    # EXPENSE STATUS OPERATIONS - Additional Status Methods
    # ========================================================================

    async def clear_expense(self, uid: str) -> Result[ExpensePure]:
        """
        Clear/void an expense (set status to CLEARED).

        A cleared expense is marked as processed but not fully paid.
        Typically used for partial payments or pending verification.

        Args:
            uid: Expense identifier

        Returns:
            Updated expense
        """
        return await self.update(uid, {"status": ExpenseStatus.CLEARED.value})

    async def reconcile_expense(self, uid: str) -> Result[ExpensePure]:
        """
        Mark an expense as reconciled.

        Reconciled expenses have been verified against bank statements
        or other financial records.

        Args:
            uid: Expense identifier

        Returns:
            Updated expense with reconciled status
        """
        updates = {
            "status": ExpenseStatus.PAID.value,
            "is_reconciled": True,
            "reconciled_at": datetime.now().isoformat(),
        }
        return await self.update(uid, updates)

    # ========================================================================
    # BUDGET OPERATIONS - Additional Budget Methods
    # ========================================================================

    async def recalculate_budget(self, budget_uid: str) -> Result[dict[str, Any]]:
        """
        Recalculate budget status with current expense data.

        This recomputes:
        - Total spent in budget period
        - Remaining amount
        - Spending rate per day
        - Projected end-of-period status

        Args:
            budget_uid: Budget identifier

        Returns:
            Dictionary with recalculated budget metrics
        """
        # Get budget status using existing method
        status_result = await self.budget.calculate_budget_status(budget_uid)

        if status_result.is_error:
            return Result.fail(status_result)

        status = status_result.value

        # Add recalculation metadata
        status["recalculated_at"] = datetime.now().isoformat()
        status["recalculation_type"] = "full"

        return Result.ok(status)

    # ========================================================================
    # BULK OPERATIONS - Batch Processing Methods
    # ========================================================================

    async def bulk_categorize(
        self,
        expense_uids: list[str],
        category: ExpenseCategory,
        subcategory: str | None = None,
    ) -> Result[dict[str, Any]]:
        """
        Bulk categorize multiple expenses.

        Args:
            expense_uids: List of expense UIDs to update
            category: New category for all expenses
            subcategory: Optional subcategory

        Returns:
            Summary of bulk operation (success count, failed UIDs, etc.)
        """
        success_count = 0
        failed_uids: list[str] = []
        errors: list[str] = []

        updates: dict[str, Any] = {"category": category.value}
        if subcategory:
            updates["subcategory"] = subcategory

        for uid in expense_uids:
            result = await self.update(uid, updates)
            if result.is_ok:
                success_count += 1
            else:
                failed_uids.append(uid)
                if result.error:
                    errors.append(f"{uid}: {result.error.message}")

        return Result.ok(
            {
                "total_requested": len(expense_uids),
                "success_count": success_count,
                "failed_count": len(failed_uids),
                "failed_uids": failed_uids,
                "errors": errors,
                "category_applied": category.value,
                "subcategory_applied": subcategory,
            }
        )

    # ========================================================================
    # UI CONTEXT METHODS — Pre-computed data for route handlers
    # ========================================================================

    async def get_dashboard_context(self) -> Result[FinanceDashboardContext]:
        """Build pre-computed dashboard context for the finance overview page.

        Returns dict with: total_spent, total_budget, budget_utilization,
        health_status, budget_health, recent_expenses, budget_alerts.
        """
        total_spent = 0.0
        total_budget = 0.0
        recent_expenses: list[dict[str, Any]] = []
        budget_alerts: list[dict[str, str]] = []

        try:
            expenses_result = await self.list_expenses(limit=QueryLimit.DEFAULT)
            if expenses_result.is_ok and expenses_result.value:
                expenses_list, _ = expenses_result.value
                for expense in expenses_list:
                    if expense.amount:
                        total_spent += expense.amount
                recent_expenses = [
                    {
                        "description": exp.description,
                        "amount": exp.amount,
                        "category": getattr(exp, "category", ""),
                        "expense_date": str(getattr(exp, "expense_date", "")),
                    }
                    for exp in expenses_list[:5]
                ]

            budgets_result = await self.get_active_budgets()
            if budgets_result.is_ok and budgets_result.value:
                for budget in budgets_result.value:
                    if budget.amount_limit:
                        total_budget += budget.amount_limit
                    spent = getattr(budget, "amount_spent", 0) or 0
                    limit = getattr(budget, "amount_limit", 1) or 1
                    if limit > 0 and spent / limit >= 0.8:
                        budget_alerts.append(
                            {
                                "type": "warning" if spent / limit < 1.0 else "critical",
                                "message": f"{budget.name}: {spent / limit * 100:.0f}% used",
                            }
                        )

        except (ValueError, TypeError, AttributeError) as e:
            self.logger.warning(f"Could not fetch finance data for dashboard: {e}")

        utilization = (total_spent / total_budget * 100) if total_budget > 0 else 0
        health_status = (
            "Good" if utilization < 80 else ("Warning" if utilization < 100 else "Over Budget")
        )
        budget_health = (
            "healthy" if utilization < 80 else ("warning" if utilization < 100 else "critical")
        )

        return Result.ok(
            {
                "total_spent": total_spent,
                "total_budget": total_budget,
                "budget_utilization": utilization,
                "health_status": health_status,
                "budget_health": budget_health,
                "recent_expenses": recent_expenses,
                "budget_alerts": budget_alerts,
            }
        )

    async def get_budgets_context(self) -> Result[FinanceBudgetsContext]:
        """Build pre-computed context for the budgets page.

        Returns dict with: budgets, total_budgeted, total_spent.
        """
        budgets: list[dict[str, Any]] = []
        total_budgeted = 0.0
        total_spent = 0.0

        try:
            budgets_result = await self.get_active_budgets()
            if budgets_result.is_ok and budgets_result.value:
                for budget in budgets_result.value:
                    limit = getattr(budget, "amount_limit", 0) or 0
                    spent = getattr(budget, "amount_spent", 0) or 0
                    total_budgeted += limit
                    total_spent += spent
                    budgets.append(
                        {
                            "uid": budget.uid,
                            "name": budget.name,
                            "amount_limit": limit,
                            "amount_spent": spent,
                            "period": getattr(budget, "period", "MONTHLY"),
                        }
                    )
        except (ValueError, TypeError, AttributeError) as e:
            self.logger.warning(f"Could not fetch budgets: {e}")

        return Result.ok(
            {
                "budgets": budgets,
                "total_budgeted": total_budgeted,
                "total_spent": total_spent,
            }
        )

    async def get_reports_context(self) -> Result[FinanceReportsContext]:
        """Build pre-computed context for the reports page.

        Returns dict with: monthly_summary, category_breakdown, tax_summary.
        """
        monthly_summary: dict[str, Any] = {"total": 0.0, "count": 0, "average": 0.0}
        category_breakdown: list[dict[str, Any]] = []
        tax_summary: dict[str, Any] = {"total": 0.0, "count": 0}

        try:
            today = date.today()
            month_start = date(today.year, today.month, 1)

            expenses_result = await self.list_expenses(limit=QueryLimit.COMPREHENSIVE)
            if expenses_result.is_ok and expenses_result.value:
                expenses_list, _ = expenses_result.value
                month_expenses: list[ExpensePure] = []
                category_totals: dict[str, float] = {}
                tax_total = 0.0
                tax_count = 0

                for exp in expenses_list:
                    exp_date = getattr(exp, "expense_date", None)
                    amount = getattr(exp, "amount", 0) or 0

                    if exp_date and exp_date >= month_start:
                        month_expenses.append(exp)

                    cat = str(getattr(exp, "category", "Other"))
                    category_totals[cat] = category_totals.get(cat, 0) + amount

                    if getattr(exp, "tax_deductible", False):
                        tax_total += amount
                        tax_count += 1

                month_total = sum(getattr(e, "amount", 0) or 0 for e in month_expenses)
                monthly_summary = {
                    "total": month_total,
                    "count": len(month_expenses),
                    "average": month_total / len(month_expenses) if month_expenses else 0,
                }

                total_all = sum(category_totals.values())
                from core.models.enums.finance_enums import ExpenseCategory
                from core.utils.sort_functions import get_negative_second_item

                for cat, amount in sorted(category_totals.items(), key=get_negative_second_item):
                    try:
                        icon = ExpenseCategory(cat.lower()).get_icon()
                    except ValueError:
                        icon = "📁"
                    category_breakdown.append(
                        {
                            "name": cat,
                            "icon": icon,
                            "amount": amount,
                            "percentage": (amount / total_all * 100) if total_all > 0 else 0,
                        }
                    )

                tax_summary = {"total": tax_total, "count": tax_count}

        except (ValueError, TypeError, AttributeError) as e:
            self.logger.warning(f"Could not generate reports: {e}")

        return Result.ok(
            {
                "monthly_summary": monthly_summary,
                "category_breakdown": category_breakdown,
                "tax_summary": tax_summary,
            }
        )

    async def get_analytics_context(self) -> Result[FinanceAnalyticsContext]:
        """Build pre-computed context for the analytics page.

        Returns dict with: health_score, health_tier, spending_pattern, budget_adherence.
        """
        health_score = 0.75
        health_tier = "Good"
        spending_pattern = "Balanced"
        budget_adherence = 85.0

        try:
            budgets_result = await self.get_active_budgets()
            if budgets_result.is_ok and budgets_result.value:
                total_limit = 0.0
                total_spent = 0.0

                for budget in budgets_result.value:
                    total_limit += getattr(budget, "amount_limit", 0) or 0
                    total_spent += getattr(budget, "amount_spent", 0) or 0

                if total_limit > 0:
                    utilization = total_spent / total_limit
                    budget_adherence = (
                        max(0, 100 - (utilization - 1) * 100) if utilization > 1 else 100
                    )

                    if utilization <= 0.6:
                        health_score, health_tier = 0.95, "Excellent"
                    elif utilization <= 0.8:
                        health_score, health_tier = 0.80, "Good"
                    elif utilization <= 1.0:
                        health_score, health_tier = 0.60, "Fair"
                    elif utilization <= 1.2:
                        health_score, health_tier = 0.40, "Poor"
                    else:
                        health_score, health_tier = 0.20, "Critical"

            expenses_result = await self.list_expenses(limit=QueryLimit.DEFAULT)
            if expenses_result.is_ok and expenses_result.value:
                _expenses_list, expense_count = expenses_result.value
                if expense_count > 50:
                    spending_pattern = "Habitual"
                elif expense_count > 20:
                    spending_pattern = "Value Focused"
                else:
                    spending_pattern = "Minimalist"

        except (ValueError, TypeError, AttributeError) as e:
            self.logger.warning(f"Could not calculate analytics: {e}")

        return Result.ok(
            {
                "health_score": health_score,
                "health_tier": health_tier,
                "spending_pattern": spending_pattern,
                "budget_adherence": budget_adherence,
            }
        )

    async def get_expenses_context(self) -> Result[FinanceExpensesContext]:
        """Build pre-computed context for the expenses page.

        Returns dict with: expenses (list of display dicts), categories, total_count.
        """
        expenses: list[dict[str, Any]] = []
        total_count = 0

        try:
            expenses_result = await self.list_expenses(limit=QueryLimit.COMPREHENSIVE)
            if expenses_result.is_ok and expenses_result.value:
                expenses_list, total_count = expenses_result.value
                expenses = [
                    {
                        "uid": exp.uid,
                        "description": exp.description,
                        "amount": exp.amount,
                        "category": str(getattr(exp, "category", "")),
                        "expense_date": str(getattr(exp, "expense_date", "")),
                        "status": str(getattr(exp, "status", "PENDING")),
                    }
                    for exp in expenses_list
                ]
        except (ValueError, TypeError, AttributeError) as e:
            self.logger.warning(f"Could not fetch expenses: {e}")
            return Result.fail(Errors.system(message=str(e), operation="get_expenses_context"))

        categories = self.get_main_categories()

        return Result.ok(
            {
                "expenses": expenses,
                "categories": categories,
                "total_count": total_count,
            }
        )

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
            if stats_result and stats_result.is_ok and stats_result.value:
                raw = stats_result.value
                stats = {
                    "total_count": raw.get("total_count", 0),
                    "outgoing_total": raw.get("outgoing_total", 0.0),
                    "incoming_total": raw.get("incoming_total", 0.0),
                    "overdue_count": raw.get("overdue_count", 0),
                    "outstanding_total": raw.get("outstanding_total", 0.0),
                }

            invoices_result = await self.list_invoices(limit=50)
            if invoices_result and invoices_result.is_ok and invoices_result.value:
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

    async def create_invoice(self, invoice: Any) -> Result[InvoicePure]:
        """
        Create a new invoice.

        Args:
            invoice: InvoicePure domain model

        Returns:
            Result containing created invoice
        """
        if not self.invoice:
            return Result.fail(Errors.system("Invoice service not initialized"))
        return await self.invoice.create(invoice)

    async def get_invoice(self, uid: str) -> Result[InvoicePure | None]:
        """
        Get an invoice by UID.

        Args:
            uid: Invoice UID

        Returns:
            Result containing invoice or None
        """
        if not self.invoice:
            return Result.fail(Errors.system("Invoice service not initialized"))
        return await self.invoice.get(uid)

    async def list_invoices(
        self,
        limit: int = 50,
        invoice_type: str | None = None,
        status: str | None = None,
    ) -> Result[list[Any]]:
        """
        List invoices with optional filters.

        Args:
            limit: Maximum number of results
            invoice_type: Optional filter ('outgoing' or 'incoming')
            status: Optional filter by status

        Returns:
            Result containing list of invoices
        """
        if not self.invoice:
            return Result.fail(Errors.system("Invoice service not initialized"))

        # Convert string filters to enums if provided
        from core.models.finance.invoice import InvoiceStatus, InvoiceType

        type_filter = InvoiceType(invoice_type) if invoice_type else None
        status_filter = InvoiceStatus(status) if status else None

        return await self.invoice.list_invoices(
            limit=limit,
            invoice_type=type_filter,
            status=status_filter,
        )

    async def generate_invoice_pdf(self, uid: str) -> Result[bytes]:
        """
        Generate PDF for an invoice.

        Args:
            uid: Invoice UID

        Returns:
            Result containing PDF bytes
        """
        if not self.invoice:
            return Result.fail(Errors.system("Invoice service not initialized"))
        return await self.invoice.generate_pdf(uid)

    async def get_invoice_stats(self) -> Result[InvoiceStats]:
        """
        Get invoice statistics.

        Returns:
            Result containing stats dictionary
        """
        if not self.invoice:
            return Result.fail(Errors.system("Invoice service not initialized"))
        return await self.invoice.get_invoice_stats()
