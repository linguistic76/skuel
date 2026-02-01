"""
Finance Hub UI Routes
=====================

Component-based UI rendering for the Finance Hub with sidebar navigation.

Features:
- Dashboard: Overview with stats, quick actions, recent expenses
- Expenses: Full expense tracking with filters and forms
- Budgets: Budget management with utilization tracking
- Reports: Monthly summaries, tax reports, category breakdowns
- Analytics: Spending patterns, financial health score

SECURITY: All Finance UI routes require ADMIN role.
"""

__version__ = "3.0"

from datetime import date
from typing import Any

from fasthtml.common import A
from starlette.requests import Request

from components.card_generator import CardGenerator
from components.form_generator import FormGenerator
from core.auth import require_admin
from core.constants import QueryLimit
from core.models.finance.finance_request import BudgetCreateRequest, ExpenseCreateRequest
from core.ui.daisy_components import Card, Div, Span
from core.utils.logging import get_logger
from ui.finance import create_finance_page
from ui.finance.section_views import FinanceSectionViews

logger = get_logger("skuel.routes.finance.ui")


# ============================================================================
# FINANCE UI COMPONENTS (kept for form/card generation)
# ============================================================================


class FinanceUIComponents:
    """
    Finance UI component definitions using FormGenerator and CardGenerator.

    These are reusable components for forms and cards.
    """

    @staticmethod
    def render_create_expense_form() -> Any:
        """Create expense form using FormGenerator."""
        return FormGenerator.from_model(
            ExpenseCreateRequest,
            action="/api/expenses",
            method="POST",
            include_fields=[
                "amount",
                "description",
                "expense_date",
                "category",
                "subcategory",
                "payment_method",
                "vendor",
                "tax_deductible",
            ],
            form_attrs={"id": "expense-create-form", "cls": "space-y-4"},
            submit_label="Add Expense",
        )

    @staticmethod
    def render_create_budget_form() -> Any:
        """Create budget form using FormGenerator."""
        return FormGenerator.from_model(
            BudgetCreateRequest,
            action="/api/budgets",
            method="POST",
            include_fields=[
                "name",
                "period",
                "amount_limit",
                "start_date",
                "categories",
                "alert_threshold",
            ],
            form_attrs={"id": "budget-create-form", "cls": "space-y-4"},
            submit_label="Create Budget",
        )

    @staticmethod
    def render_expense_card(expense, compact=False) -> Any:
        """Individual expense card using CardGenerator."""
        uid = expense.get("uid", "") if isinstance(expense, dict) else expense.uid

        def render_amount(value) -> Any:
            return Span(f"${value:,.2f}", cls="text-2xl font-bold text-green-600")

        display_fields = (
            ["amount", "description", "category"]
            if compact
            else [
                "amount",
                "description",
                "expense_date",
                "category",
                "subcategory",
                "payment_method",
                "vendor",
                "status",
            ]
        )

        card = CardGenerator.from_dataclass(
            expense,
            display_fields=display_fields,
            field_renderers={"amount": render_amount},
            card_attrs={"id": f"expense-{uid}", "cls": "border border-gray-200 p-4"},
        )

        buttons = [
            A(
                "View",
                href=f"/finance/expenses/{uid}",
                cls="btn btn-sm btn-outline",
            ),
            A(
                "Edit",
                href=f"/finance/expenses/{uid}/edit",
                cls="btn btn-sm btn-ghost",
            ),
        ]

        return Card(Div(card, Div(*buttons, cls="flex gap-2 mt-3"), cls="p-4"))

    @staticmethod
    def render_budget_card(budget, compact=False) -> Any:
        """Individual budget card using CardGenerator."""
        uid = budget.get("uid", "") if isinstance(budget, dict) else budget.uid

        def render_amount_limit(value) -> Any:
            return Span(f"${value:,.2f} limit", cls="text-xl font-semibold text-blue-600")

        display_fields = (
            ["name", "amount_limit", "period"]
            if compact
            else [
                "name",
                "amount_limit",
                "period",
                "start_date",
                "end_date",
                "categories",
                "alert_threshold",
            ]
        )

        card = CardGenerator.from_dataclass(
            budget,
            display_fields=display_fields,
            field_renderers={"amount_limit": render_amount_limit},
            card_attrs={"id": f"budget-{uid}", "cls": "border border-gray-200 p-4"},
        )

        buttons = [
            A(
                "View",
                href=f"/finance/budgets/{uid}",
                cls="btn btn-sm btn-outline",
            ),
            A(
                "Edit",
                href=f"/finance/budgets/{uid}/edit",
                cls="btn btn-sm btn-ghost",
            ),
        ]

        return Card(Div(card, Div(*buttons, cls="flex gap-2 mt-3"), cls="p-4"))


# ============================================================================
# FINANCE HUB ROUTES
# ============================================================================


def create_finance_ui_routes(_app, rt, finance_service, user_service: Any = None) -> list[Any]:
    """
    Create Finance Hub UI routes with sidebar navigation.

    SECURITY: All Finance UI routes require ADMIN role.
    Finance is its own domain group (not Activity, not Curriculum).
    Admin users can see all finance data (no ownership checks).

    Routes:
        GET /finance           - Dashboard overview
        GET /finance/expenses  - Expense tracking
        GET /finance/budgets   - Budget management
        GET /finance/reports   - Financial reports
        GET /finance/analytics - Spending analytics

    Args:
        _app: FastHTML application instance
        rt: Router instance
        finance_service: Finance service instance
        user_service: User service instance (for role verification)

    """

    # Named function for user service getter (SKUEL012 compliance)
    def get_user_service():
        return user_service

    # =========================================================================
    # DASHBOARD ROUTE
    # =========================================================================

    @rt("/finance")
    @require_admin(get_user_service)
    async def finance_dashboard(request: Request, current_user) -> Any:
        """Finance Hub dashboard with overview stats and quick actions."""
        logger.info(f"Finance dashboard accessed by {current_user.uid}")

        # Fetch data for dashboard
        total_spent = 0.0
        total_budget = 0.0
        recent_expenses = []
        budget_alerts = []

        try:
            # Fetch expenses
            expenses_result = await finance_service.list_expenses(limit=QueryLimit.DEFAULT)
            if expenses_result and expenses_result.is_ok and expenses_result.value:
                expenses_list, _ = expenses_result.value
                for expense in expenses_list:
                    if hasattr(expense, "amount") and expense.amount:
                        total_spent += expense.amount
                # Get recent expenses for dashboard
                recent_expenses = [
                    {
                        "description": exp.description,
                        "amount": exp.amount,
                        "category": getattr(exp, "category", ""),
                        "expense_date": str(getattr(exp, "expense_date", "")),
                    }
                    for exp in expenses_list[:5]
                ]

            # Fetch budgets
            budgets_result = await finance_service.get_active_budgets()
            if budgets_result and budgets_result.is_ok and budgets_result.value:
                for budget in budgets_result.value:
                    if hasattr(budget, "amount_limit") and budget.amount_limit:
                        total_budget += budget.amount_limit
                    # Check for alerts
                    spent = getattr(budget, "amount_spent", 0) or 0
                    limit = getattr(budget, "amount_limit", 1) or 1
                    if limit > 0 and spent / limit >= 0.8:
                        budget_alerts.append(
                            {
                                "type": "warning" if spent / limit < 1.0 else "critical",
                                "message": f"{budget.name}: {spent / limit * 100:.0f}% used",
                            }
                        )

        except Exception as e:
            logger.warning(f"Could not fetch finance data for dashboard: {e}")

        # Calculate utilization
        budget_utilization = (total_spent / total_budget * 100) if total_budget > 0 else 0
        health_status = (
            "Good"
            if budget_utilization < 80
            else ("Warning" if budget_utilization < 100 else "Over Budget")
        )

        # Determine budget health for sidebar
        budget_health = (
            "healthy"
            if budget_utilization < 80
            else ("warning" if budget_utilization < 100 else "critical")
        )

        # Render dashboard view
        content = FinanceSectionViews.render_dashboard(
            total_spent=total_spent,
            total_budget=total_budget,
            budget_utilization=budget_utilization,
            health_status=health_status,
            recent_expenses=recent_expenses,
            budget_alerts=budget_alerts,
        )

        return create_finance_page(
            content=content,
            active_section="dashboard",
            admin_username=current_user.display_name or current_user.username,
            title="Finance Dashboard",
            budget_health=budget_health,
        )

    # =========================================================================
    # EXPENSES ROUTE
    # =========================================================================

    @rt("/finance/expenses")
    @require_admin(get_user_service)
    async def finance_expenses(request: Request, current_user) -> Any:
        """Expense tracking page with list and create form."""
        from ui.layouts.base_page import BasePage
        from ui.patterns.error_banner import render_error_banner

        logger.info(f"Finance expenses accessed by {current_user.uid}")

        try:
            expenses_result = await finance_service.list_expenses(limit=QueryLimit.COMPREHENSIVE)

            # Check for errors FIRST, show user-friendly message (main content failure)
            if not expenses_result or expenses_result.is_error:
                error_msg = expenses_result.error.message if expenses_result else "Service unavailable"
                return BasePage(
                    content=render_error_banner(
                        "Unable to load expenses. Please try again later.",
                        error_msg
                    ),
                    title="Expenses",
                    request=request
                )

            # Safe to access value
            expenses_list, total_count = expenses_result.value or ([], 0)
            expenses = [
                {
                    "uid": exp.uid,
                    "description": exp.description,
                    "amount": exp.amount,
                    "category": getattr(exp, "category", ""),
                    "expense_date": str(getattr(exp, "expense_date", "")),
                    "status": getattr(exp, "status", "PENDING"),
                }
                for exp in expenses_list
            ]
        except Exception as e:
            logger.error(f"Unexpected error fetching expenses: {e}")
            return BasePage(
                content=render_error_banner(
                    "An unexpected error occurred. Please try again later.",
                    str(e)
                ),
                title="Expenses",
                request=request
            )

        # Categories for filter
        categories = [
            {"name": "Personal", "code": "PERSONAL"},
            {"name": "House (2222)", "code": "2222"},
            {"name": "SKUEL", "code": "SKUEL"},
        ]

        content = FinanceSectionViews.render_expenses_list(
            expenses=expenses,
            categories=categories,
            total_count=total_count,
        )

        return create_finance_page(
            content=content,
            active_section="expenses",
            admin_username=current_user.display_name or current_user.username,
            title="Expenses",
        )

    # =========================================================================
    # BUDGETS ROUTE
    # =========================================================================

    @rt("/finance/budgets")
    @require_admin(get_user_service)
    async def finance_budgets(request: Request, current_user) -> Any:
        """Budget management page with list and create form."""
        logger.info(f"Finance budgets accessed by {current_user.uid}")

        budgets = []
        total_budgeted = 0.0
        total_spent = 0.0

        try:
            budgets_result = await finance_service.get_active_budgets()
            if budgets_result and budgets_result.is_ok and budgets_result.value:
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
        except Exception as e:
            logger.warning(f"Could not fetch budgets: {e}")

        content = FinanceSectionViews.render_budgets_list(
            budgets=budgets,
            total_budgeted=total_budgeted,
            total_spent=total_spent,
        )

        return create_finance_page(
            content=content,
            active_section="budgets",
            admin_username=current_user.display_name or current_user.username,
            title="Budgets",
        )

    # =========================================================================
    # REPORTS ROUTE
    # =========================================================================

    @rt("/finance/reports")
    @require_admin(get_user_service)
    async def finance_reports(request: Request, current_user) -> Any:
        """Financial reports page with monthly summaries and tax info."""
        logger.info(f"Finance reports accessed by {current_user.uid}")

        monthly_summary = {"total": 0.0, "count": 0, "average": 0.0}
        category_breakdown = []
        tax_summary = {"total": 0.0, "count": 0}

        try:
            # Get current month's expenses
            today = date.today()
            month_start = date(today.year, today.month, 1)

            expenses_result = await finance_service.list_expenses(limit=QueryLimit.COMPREHENSIVE)
            if expenses_result and expenses_result.is_ok and expenses_result.value:
                expenses_list, _ = expenses_result.value
                month_expenses = []
                category_totals = {}
                tax_total = 0.0
                tax_count = 0

                for exp in expenses_list:
                    exp_date = getattr(exp, "expense_date", None)
                    amount = getattr(exp, "amount", 0) or 0

                    # Monthly calculation
                    if exp_date and exp_date >= month_start:
                        month_expenses.append(exp)

                    # Category breakdown
                    cat = str(getattr(exp, "category", "Other"))
                    category_totals[cat] = category_totals.get(cat, 0) + amount

                    # Tax deductible
                    if getattr(exp, "tax_deductible", False):
                        tax_total += amount
                        tax_count += 1

                # Calculate monthly summary
                month_total = sum(getattr(e, "amount", 0) or 0 for e in month_expenses)
                monthly_summary = {
                    "total": month_total,
                    "count": len(month_expenses),
                    "average": month_total / len(month_expenses) if month_expenses else 0,
                }

                # Build category breakdown
                total_all = sum(category_totals.values())
                category_icons = {"PERSONAL": "👤", "2222": "🏠", "SKUEL": "📚"}
                from core.utils.sort_functions import get_negative_second_item

                for cat, amount in sorted(category_totals.items(), key=get_negative_second_item):
                    category_breakdown.append(
                        {
                            "name": cat,
                            "icon": category_icons.get(cat, "📁"),
                            "amount": amount,
                            "percentage": (amount / total_all * 100) if total_all > 0 else 0,
                        }
                    )

                tax_summary = {"total": tax_total, "count": tax_count}

        except Exception as e:
            logger.warning(f"Could not generate reports: {e}")

        content = FinanceSectionViews.render_reports(
            monthly_summary=monthly_summary,
            category_breakdown=category_breakdown,
            tax_summary=tax_summary,
        )

        return create_finance_page(
            content=content,
            active_section="reports",
            admin_username=current_user.display_name or current_user.username,
            title="Reports",
        )

    # =========================================================================
    # ANALYTICS ROUTE
    # =========================================================================

    @rt("/finance/analytics")
    @require_admin(get_user_service)
    async def finance_analytics(request: Request, current_user) -> Any:
        """Spending analytics page with health score and patterns."""
        logger.info(f"Finance analytics accessed by {current_user.uid}")

        health_score = 0.75  # Default
        health_tier = "Good"
        spending_pattern = "Balanced"
        budget_adherence = 85.0

        try:
            # Calculate financial health based on budget adherence
            budgets_result = await finance_service.get_active_budgets()
            if budgets_result and budgets_result.is_ok and budgets_result.value:
                total_limit = 0.0
                total_spent = 0.0

                for budget in budgets_result.value:
                    limit = getattr(budget, "amount_limit", 0) or 0
                    spent = getattr(budget, "amount_spent", 0) or 0
                    total_limit += limit
                    total_spent += spent

                if total_limit > 0:
                    utilization = total_spent / total_limit
                    budget_adherence = (
                        max(0, 100 - (utilization - 1) * 100) if utilization > 1 else 100
                    )

                    # Calculate health score (inverse of over-spending)
                    if utilization <= 0.6:
                        health_score = 0.95
                        health_tier = "Excellent"
                    elif utilization <= 0.8:
                        health_score = 0.80
                        health_tier = "Good"
                    elif utilization <= 1.0:
                        health_score = 0.60
                        health_tier = "Fair"
                    elif utilization <= 1.2:
                        health_score = 0.40
                        health_tier = "Poor"
                    else:
                        health_score = 0.20
                        health_tier = "Critical"

            # Determine spending pattern (simplified)
            expenses_result = await finance_service.list_expenses(limit=QueryLimit.DEFAULT)
            if expenses_result and expenses_result.is_ok and expenses_result.value:
                expenses_list, expense_count = expenses_result.value
                if expense_count > 50:
                    spending_pattern = "Habitual"
                elif expense_count > 20:
                    spending_pattern = "Value Focused"
                else:
                    spending_pattern = "Minimalist"

        except Exception as e:
            logger.warning(f"Could not calculate analytics: {e}")

        content = FinanceSectionViews.render_analytics(
            health_score=health_score,
            health_tier=health_tier,
            spending_pattern=spending_pattern,
            budget_adherence=budget_adherence,
        )

        return create_finance_page(
            content=content,
            active_section="analytics",
            admin_username=current_user.display_name or current_user.username,
            title="Analytics",
        )

    # =========================================================================
    # INVOICES ROUTE
    # =========================================================================

    @rt("/finance/invoices")
    @require_admin(get_user_service)
    async def finance_invoices(request: Request, current_user) -> Any:
        """Invoice management page with list and create form."""
        logger.info(f"Finance invoices accessed by {current_user.uid}")

        invoices = []
        stats = {
            "total_count": 0,
            "outgoing_total": 0.0,
            "incoming_total": 0.0,
            "overdue_count": 0,
            "outstanding_total": 0.0,
        }

        try:
            # Get invoice stats
            stats_result = await finance_service.get_invoice_stats()
            if stats_result and stats_result.is_ok and stats_result.value:
                stats = stats_result.value

            # Get invoice list
            invoices_result = await finance_service.list_invoices(limit=50)
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
        except Exception as e:
            logger.warning(f"Could not fetch invoices: {e}")

        # Import and render invoice views
        from ui.finance.invoice_views import InvoiceViews

        content = InvoiceViews.render_invoices_list(invoices=invoices, stats=stats)

        return create_finance_page(
            content=content,
            active_section="invoices",
            admin_username=current_user.display_name or current_user.username,
            title="Invoices",
        )

    logger.info("Finance Hub UI routes registered")
    return []


# Export
__all__ = ["FinanceUIComponents", "create_finance_ui_routes"]
