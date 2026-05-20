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

import uuid
from datetime import date
from typing import Any

from fasthtml.common import Div
from pydantic import ValidationError
from starlette.responses import HTMLResponse

from adapters.inbound.auth import make_service_getter, require_admin
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from core.models.finance.finance_request import BudgetCreateRequest, ExpenseCreateRequest
from core.services.conversion_service import ConversionServiceV2
from core.utils.logging import get_logger
from ui.finance import FinanceUIComponents, create_finance_page
from ui.finance.section_views import FinanceSectionViews

logger = get_logger("skuel.routes.finance.ui")


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

    # =========================================================================
    # FORM-ENCODED CREATE HANDLERS
    # =========================================================================
    # The JSON API at /api/{expenses,budgets}/create requires a JSON body, but
    # the HTMX forms in section_views.py post application/x-www-form-urlencoded.
    # These handlers bridge that gap: normalize the form payload, validate
    # against the Pydantic schema, and redirect back to the section page.

    def _form_error_banner(message: str) -> Div:
        return Div(
            message,
            cls="bg-error/10 border border-error/20 rounded-lg p-3 text-error mb-3 text-sm",
        )

    @rt("/finance/expenses/create", methods=["POST"])
    @csrf_protected
    @require_admin(get_user_service)
    async def process_expense_create(request: Request, current_user) -> Any:
        """Form-encoded create endpoint for the expense form."""
        form = await request.form()
        data: dict[str, Any] = {
            k: (v.strip() if isinstance(v, str) else v) for k, v in form.items()
        }

        # Form uses uppercase labels for category — schema expects lowercase Literal.
        category = data.get("category")
        if isinstance(category, str):
            data["category"] = category.lower()

        try:
            schema = ExpenseCreateRequest.model_validate(data)
        except ValidationError as e:
            logger.warning(f"Expense form validation failed: {e}")
            return _form_error_banner(f"Could not create expense: {e.errors()[0]['msg']}")

        uid = f"expense:{uuid.uuid4().hex[:12]}"
        entity = ConversionServiceV2.expense_create_to_pure(schema, uid, user_uid=current_user.uid)

        result = await finance_service.create(entity)
        if result.is_error:
            err = result.expect_error()
            logger.error(f"Expense create failed: {err.message}")
            return _form_error_banner(f"Could not create expense: {err.message}")

        logger.info(f"Expense created via form by admin {current_user.uid}: {uid}")
        return HTMLResponse("", status_code=200, headers={"HX-Redirect": "/finance/expenses"})

    @rt("/finance/budgets/create", methods=["POST"])
    @csrf_protected
    @require_admin(get_user_service)
    async def process_budget_create(request: Request, current_user) -> Any:
        """Form-encoded create endpoint for the budget form."""
        form = await request.form()
        data: dict[str, Any] = {
            k: (v.strip() if isinstance(v, str) else v) for k, v in form.items()
        }

        # Form uses uppercase Period; schema expects lowercase Literal.
        period = data.get("period")
        if isinstance(period, str):
            data["period"] = period.lower()

        # Form sends a single category; schema expects categories: list[Literal].
        category = data.pop("category", None)
        if isinstance(category, str) and category:
            data["categories"] = [category.lower()]

        # Form doesn't expose start_date; default to today.
        data.setdefault("start_date", date.today().isoformat())

        try:
            schema = BudgetCreateRequest.model_validate(data)
        except ValidationError as e:
            logger.warning(f"Budget form validation failed: {e}")
            return _form_error_banner(f"Could not create budget: {e.errors()[0]['msg']}")

        uid = f"budget:{uuid.uuid4().hex[:12]}"
        entity = ConversionServiceV2.budget_create_to_pure(schema, uid, user_uid=current_user.uid)

        result = await finance_service.create_budget(entity)
        if result.is_error:
            err = result.expect_error()
            logger.error(f"Budget create failed: {err.message}")
            return _form_error_banner(f"Could not create budget: {err.message}")

        logger.info(f"Budget created via form by admin {current_user.uid}: {uid}")
        return HTMLResponse("", status_code=200, headers={"HX-Redirect": "/finance/budgets"})

    logger.info("Finance Hub UI routes registered")

    return []


# Export
__all__ = ["FinanceUIComponents", "create_finance_ui_routes"]
