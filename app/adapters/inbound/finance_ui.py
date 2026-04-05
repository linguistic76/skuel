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

from typing import Any

from fasthtml.common import Div, Span

from adapters.inbound.auth import make_service_getter, require_admin
from adapters.inbound.fasthtml_types import Request
from core.models.finance.finance_request import BudgetCreateRequest, ExpenseCreateRequest
from core.utils.logging import get_logger
from ui.buttons import ButtonLink, ButtonT
from ui.finance import create_finance_page
from ui.finance.section_views import FinanceSectionViews
from ui.layout import Size
from ui.patterns.card_generator import CardGenerator
from ui.patterns.form_generator import FormGenerator

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

        action_buttons = Div(
            ButtonLink(
                "View",
                href=f"/finance/expenses/{uid}",
                variant=ButtonT.outline,
                size=Size.sm,
            ),
            ButtonLink(
                "Edit",
                href=f"/finance/expenses/{uid}/edit",
                variant=ButtonT.ghost,
                size=Size.sm,
            ),
            cls="flex gap-2",
        )

        return CardGenerator.from_dataclass(
            expense,
            display_fields=display_fields,
            field_renderers={"amount": render_amount},
            actions=action_buttons,
            card_attrs={"id": f"expense-{uid}", "cls": "border border-border p-4"},
        )

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

        action_buttons = Div(
            ButtonLink(
                "View",
                href=f"/finance/budgets/{uid}",
                variant=ButtonT.outline,
                size=Size.sm,
            ),
            ButtonLink(
                "Edit",
                href=f"/finance/budgets/{uid}/edit",
                variant=ButtonT.ghost,
                size=Size.sm,
            ),
            cls="flex gap-2",
        )

        return CardGenerator.from_dataclass(
            budget,
            display_fields=display_fields,
            field_renderers={"amount_limit": render_amount_limit},
            actions=action_buttons,
            card_attrs={"id": f"budget-{uid}", "cls": "border border-border p-4"},
        )


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

    get_user_service = make_service_getter(user_service)

    # =========================================================================
    # DASHBOARD ROUTE
    # =========================================================================

    @rt("/finance")
    @require_admin(get_user_service)
    async def finance_dashboard(request: Request, current_user) -> Any:
        """Finance Hub dashboard with overview stats and quick actions."""
        logger.info(f"Finance dashboard accessed by {current_user.uid}")

        ctx_result = await finance_service.get_dashboard_context()
        ctx = ctx_result.value

        content = FinanceSectionViews.render_dashboard(
            total_spent=ctx["total_spent"],
            total_budget=ctx["total_budget"],
            budget_utilization=ctx["budget_utilization"],
            health_status=ctx["health_status"],
            recent_expenses=ctx["recent_expenses"],
            budget_alerts=ctx["budget_alerts"],
        )

        return await create_finance_page(
            content=content,
            active_section="dashboard",
            admin_username=current_user.display_name or current_user.username,
            title="Finance Dashboard",
            budget_health=ctx["budget_health"],
            request=request,
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

        ctx_result = await finance_service.get_expenses_context()
        if ctx_result.is_error:
            return await BasePage(
                content=render_error_banner(
                    "Unable to load expenses. Please try again later.",
                    ctx_result.error.message if ctx_result.error else "Service unavailable",
                ),
                title="Expenses",
                request=request,
            )

        ctx = ctx_result.value

        content = FinanceSectionViews.render_expenses_list(
            expenses=ctx["expenses"],
            categories=ctx["categories"],
            total_count=ctx["total_count"],
        )

        return await create_finance_page(
            content=content,
            active_section="expenses",
            admin_username=current_user.display_name or current_user.username,
            title="Expenses",
            request=request,
        )

    # =========================================================================
    # BUDGETS ROUTE
    # =========================================================================

    @rt("/finance/budgets")
    @require_admin(get_user_service)
    async def finance_budgets(request: Request, current_user) -> Any:
        """Budget management page with list and create form."""
        logger.info(f"Finance budgets accessed by {current_user.uid}")

        ctx_result = await finance_service.get_budgets_context()
        ctx = ctx_result.value

        content = FinanceSectionViews.render_budgets_list(
            budgets=ctx["budgets"],
            total_budgeted=ctx["total_budgeted"],
            total_spent=ctx["total_spent"],
        )

        return await create_finance_page(
            content=content,
            active_section="budgets",
            admin_username=current_user.display_name or current_user.username,
            title="Budgets",
            request=request,
        )

    # =========================================================================
    # REPORTS ROUTE
    # =========================================================================

    @rt("/finance/reports")
    @require_admin(get_user_service)
    async def finance_reports(request: Request, current_user) -> Any:
        """Financial reports page with monthly summaries and tax info."""
        logger.info(f"Finance reports accessed by {current_user.uid}")

        ctx_result = await finance_service.get_reports_context()
        ctx = ctx_result.value

        content = FinanceSectionViews.render_reports(
            monthly_summary=ctx["monthly_summary"],
            category_breakdown=ctx["category_breakdown"],
            tax_summary=ctx["tax_summary"],
        )

        return await create_finance_page(
            content=content,
            active_section="reports",
            admin_username=current_user.display_name or current_user.username,
            title="Reports",
            request=request,
        )

    # =========================================================================
    # ANALYTICS ROUTE
    # =========================================================================

    @rt("/finance/analytics")
    @require_admin(get_user_service)
    async def finance_analytics(request: Request, current_user) -> Any:
        """Spending analytics page with health score and patterns."""
        logger.info(f"Finance analytics accessed by {current_user.uid}")

        ctx_result = await finance_service.get_analytics_context()
        ctx = ctx_result.value

        content = FinanceSectionViews.render_analytics(
            health_score=ctx["health_score"],
            health_tier=ctx["health_tier"],
            spending_pattern=ctx["spending_pattern"],
            budget_adherence=ctx["budget_adherence"],
        )

        return await create_finance_page(
            content=content,
            active_section="analytics",
            admin_username=current_user.display_name or current_user.username,
            title="Analytics",
            request=request,
        )

    # =========================================================================
    # INVOICES ROUTE
    # =========================================================================

    @rt("/finance/invoices")
    @require_admin(get_user_service)
    async def finance_invoices(request: Request, current_user) -> Any:
        """Invoice management page with list and create form."""
        logger.info(f"Finance invoices accessed by {current_user.uid}")

        from ui.finance.invoice_views import InvoiceViews
        from ui.finance.types import InvoiceRow, InvoiceStats

        ctx_result = await finance_service.get_invoices_context()
        ctx = ctx_result.value

        invoices = [InvoiceRow(**inv) for inv in ctx["invoices"]]
        stats = InvoiceStats(**ctx["stats"])

        content = InvoiceViews.render_invoices_list(invoices=invoices, stats=stats)

        return await create_finance_page(
            content=content,
            active_section="invoices",
            admin_username=current_user.display_name or current_user.username,
            title="Invoices",
            request=request,
        )

    logger.info("Finance Hub UI routes registered")

    return []


# Export
__all__ = ["FinanceUIComponents", "create_finance_ui_routes"]
