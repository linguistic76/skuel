"""
Finance API Routes
==================

Pure JSON API endpoints for finance operations (CRUD, analytics, bulk operations).
No UI components - only API logic.
"""

__version__ = "1.0"

from datetime import date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.services.protocols import FinancesOperations

# Pydantic schemas for boundary
from core.auth import require_admin
from core.infrastructure.routes.analytics_route_factory import AnalyticsRouteFactory
from core.infrastructure.routes.crud_route_factory import CRUDRouteFactory
from core.models.enums import UserRole
from core.models.finance.finance_request import (
    BudgetCreateRequest as BudgetCreateSchema,
)
from core.models.finance.finance_request import (
    BudgetUpdateRequest as BudgetUpdateSchema,
)
from core.models.finance.finance_request import (
    ExpenseCreateRequest as ExpenseCreateSchema,
)
from core.models.finance.finance_request import (
    ExpenseUpdateRequest as ExpenseUpdateSchema,
)
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.routes.finance.api")


# ============================================================================
# API ROUTE CREATION
# ============================================================================


def create_finance_api_routes(
    app: Any, rt: Any, finance_service: "FinancesOperations", user_service: Any = None
) -> list[Any]:
    """
    Create finance API routes (JSON endpoints only).

    SECURITY: All Finance routes require ADMIN role.
    Finance is its own domain group (not Activity, not Curriculum).
    Admin users can see/modify all finance data (no ownership checks).

    Args:
        app: FastHTML application instance
        rt: Router instance
        finance_service: Finance service instance
        user_service: User service instance (for role verification)

    """

    # User service getter for role checks
    def user_service_getter():
        return user_service

    # ========================================================================
    # EXPENSE CRUD ROUTES (Factory-Generated, Admin-Only)
    # ========================================================================

    expense_factory = CRUDRouteFactory(
        service=finance_service,
        domain_name="expenses",
        create_schema=ExpenseCreateSchema,
        update_schema=ExpenseUpdateSchema,
        uid_prefix="expense",
        require_role=UserRole.ADMIN,  # Role-based access (overrides scope)
        user_service_getter=user_service_getter,
    )
    expense_factory.register_routes(app, rt)

    # ========================================================================
    # EXPENSE DOMAIN-SPECIFIC ROUTES (Admin-Only)
    # ========================================================================

    @rt("/api/expenses/date-range")
    @require_admin(user_service_getter)
    @boundary_handler()
    async def get_expenses_by_date_range_route(request, current_user) -> Result[Any]:
        """Get expenses within a date range (admin only)"""
        params = dict(request.query_params)

        # Required parameters
        start_date = date.fromisoformat(params["start_date"])
        end_date = date.fromisoformat(params["end_date"])

        # Optional parameters
        limit = int(params.get("limit", 100))
        offset = int(params.get("offset", 0))

        # Call service with admin's user_uid (service filters by user)
        result = await finance_service.get_expenses_by_date_range(
            user_uid=current_user.uid,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

        if result.is_ok:
            expenses, total_count = result.value
            return Result.ok(
                {
                    "expenses": expenses,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "count": total_count,
                }
            )
        else:
            error = result.error
            return Result.fail(
                Errors.system(
                    message=error.user_message or error.message if error else "Unknown error"
                )
            )

    @rt("/api/expenses/search")
    @require_admin(user_service_getter)
    @boundary_handler()
    async def search_expenses_route(request, current_user) -> Result[Any]:
        """Search expenses with text query (admin only)"""
        try:
            params = dict(request.query_params)

            # Required parameter
            query = params.get("query", "").strip()
            if not query:
                return Result.fail(Errors.validation("Query parameter is required", field="query"))

            # Optional parameters
            limit = int(params.get("limit", 50))
            offset = int(params.get("offset", 0))

            # Call service (admin sees all)
            result = await finance_service.search_expenses(
                user_uid=current_user.uid, query=query, limit=limit, offset=offset
            )

            if result.is_ok:
                expenses = result.value
                return Result.ok(
                    {
                        "expenses": expenses,
                        "query": query,
                        "count": len(expenses) if expenses else 0,
                    }
                )
            else:
                error = result.error
                return Result.fail(
                    Errors.system(
                        message=error.user_message or error.message if error else "Unknown error"
                    )
                )

        except Exception as e:
            logger.error(f"Error in search expenses route: {e}")
            return Result.fail(
                Errors.system(message=f"Failed to search expenses: {e!s}", exception=e)
            )

    # ========================================================================
    # EXPENSE STATUS OPERATIONS (Admin-Only)
    # ========================================================================
    # SECURITY: Admin role required - no ownership checks (admin sees all)

    @rt("/api/expenses/clear")
    @require_admin(user_service_getter)
    @boundary_handler()
    async def clear_expense_route(request, current_user, uid: str) -> Result[Any]:
        """Mark expense as cleared (admin only)."""
        result = await finance_service.clear_expense(uid)

        if result.is_ok:
            logger.info(f"Expense cleared via API by admin: {uid}")
            return Result.ok(result.value)
        else:
            error = result.error
            return Result.fail(
                Errors.system(
                    message=error.user_message or error.message if error else "Unknown error"
                )
            )

    @rt("/api/expenses/reconcile")
    @require_admin(user_service_getter)
    @boundary_handler()
    async def reconcile_expense_route(request, current_user, uid: str) -> Result[Any]:
        """Mark expense as reconciled (admin only)."""
        result = await finance_service.reconcile_expense(expense_uid=uid, reconciliation_data={})

        if result.is_ok:
            logger.info(f"Expense reconciled via API by admin: {uid}")
            return Result.ok(result.value)
        else:
            error = result.error
            return Result.fail(
                Errors.system(
                    message=error.user_message or error.message if error else "Unknown error"
                )
            )

    @rt("/api/expenses/receipt")
    @require_admin(user_service_getter)
    @boundary_handler()
    async def attach_receipt_route(request, current_user, uid: str) -> Result[Any]:
        """Attach receipt to expense (admin only)."""
        body = await request.json()
        receipt_url = body.get("receipt_url")
        if not receipt_url:
            return Result.fail(Errors.validation("receipt_url is required"))

        result = await finance_service.attach_receipt(uid, receipt_url)

        if result.is_ok:
            logger.info(f"Receipt attached to expense via API by admin: {uid}")
            return Result.ok(result.value)
        else:
            error = result.error
            return Result.fail(
                Errors.system(
                    message=error.user_message or error.message if error else "Unknown error"
                )
            )

    # ========================================================================
    # BUDGET CRUD ROUTES (Factory-Generated, Admin-Only)
    # ========================================================================

    budget_factory = CRUDRouteFactory(
        service=finance_service,
        domain_name="budgets",
        create_schema=BudgetCreateSchema,
        update_schema=BudgetUpdateSchema,
        uid_prefix="budget",
        require_role=UserRole.ADMIN,  # Role-based access (overrides scope)
        user_service_getter=user_service_getter,
    )
    budget_factory.register_routes(app, rt)

    # ========================================================================
    # BUDGET DOMAIN-SPECIFIC ROUTES (Admin-Only)
    # ========================================================================

    @rt("/api/budgets/active")
    @require_admin(user_service_getter)
    @boundary_handler()
    async def get_active_budgets_route(request, current_user) -> Result[Any]:
        """Get active budgets (admin only)"""
        result = await finance_service.get_active_budgets()

        if result.is_ok:
            budgets = result.value
            return Result.ok({"budgets": budgets, "count": len(budgets) if budgets else 0})
        else:
            error = result.error
            return Result.fail(
                Errors.system(
                    message=error.user_message or error.message if error else "Unknown error"
                )
            )

    @rt("/api/budgets/recalculate")
    @require_admin(user_service_getter)
    @boundary_handler()
    async def recalculate_budget_route(request, current_user, uid: str) -> Result[Any]:
        """Recalculate budget spending from expenses (admin only)."""
        try:
            result = await finance_service.recalculate_budget(uid)

            if result.is_ok:
                logger.info(f"Budget recalculated via API by admin: {uid}")
                return Result.ok(result.value)
            else:
                error = result.error
                error_msg = error.user_message or error.message if error else "Unknown error"
                if "not found" in error_msg.lower():
                    return Result.fail(Errors.not_found(resource="Budget", identifier=uid))
                return Result.fail(Errors.system(message=error_msg))

        except Exception as e:
            logger.error(f"Error in recalculate budget route: {e}")
            return Result.fail(
                Errors.system(message=f"Failed to recalculate budget: {e!s}", exception=e)
            )

    # ========================================================================
    # ANALYTICS API ROUTES (Factory-Generated, Admin-Only)
    # ========================================================================

    async def handle_spending_summary(service, params):
        """Handler for spending summary analytics"""
        start_date = date.fromisoformat(params["start_date"])
        end_date = date.fromisoformat(params["end_date"])

        result = await service.get_spending_summary(start_date, end_date)

        if result.is_ok:
            return {
                "summary": result.value,
                "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            }
        return result

    async def handle_category_breakdown(service, params):
        """Handler for category breakdown analytics"""
        start_date = date.fromisoformat(params["start_date"])
        end_date = date.fromisoformat(params["end_date"])

        result = await service.get_category_breakdown(start_date, end_date)

        if result.is_ok:
            return {
                "categories": result.value,
                "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            }
        return result

    async def handle_spending_trends(service, params):
        """Handler for spending trends analytics"""
        start_date = date.fromisoformat(params["start_date"])
        end_date = date.fromisoformat(params["end_date"])
        granularity = params.get("granularity", "daily")

        result = await service.get_spending_trends(start_date, end_date, granularity)

        if result.is_ok:
            return {
                "trends": result.value,
                "granularity": granularity,
                "period": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
            }
        return result

    analytics_factory = AnalyticsRouteFactory(
        service=finance_service,
        domain_name="finance",
        analytics_config={
            "summary": {
                "path": "/api/finance/analytics/summary",
                "handler": handle_spending_summary,
                "description": "Get comprehensive spending summary",
                "require_params": ["start_date", "end_date"],
            },
            "categories": {
                "path": "/api/finance/analytics/categories",
                "handler": handle_category_breakdown,
                "description": "Get spending breakdown by category",
                "require_params": ["start_date", "end_date"],
            },
            "trends": {
                "path": "/api/finance/analytics/trends",
                "handler": handle_spending_trends,
                "description": "Get spending trends over time",
                "require_params": ["start_date", "end_date"],
            },
        },
        require_role=UserRole.ADMIN,
        user_service_getter=user_service_getter,
    )
    analytics_factory.register_routes(app, rt)

    # ========================================================================
    # INVOICE ROUTES (Admin-Only)
    # ========================================================================

    @rt("/api/invoices")
    @require_admin(user_service_getter)
    @boundary_handler()
    async def list_invoices_route(request, current_user) -> Result[Any]:
        """List all invoices with optional filters (admin only)"""
        # Get query params
        invoice_type = request.query_params.get("type")  # outgoing or incoming
        status = request.query_params.get("status")
        limit = int(request.query_params.get("limit", "50"))

        result = await finance_service.list_invoices(
            limit=limit,
            invoice_type=invoice_type,
            status=status,
        )

        if result.is_ok:
            invoices = result.value or []
            return Result.ok(
                {
                    "invoices": [inv.to_dto().to_dict() for inv in invoices],
                    "count": len(invoices),
                }
            )
        return result

    @rt("/api/invoices", methods=["POST"])
    @require_admin(user_service_getter)
    @boundary_handler()
    async def create_invoice_route(request, current_user) -> Result[Any]:
        """Create a new invoice (admin only)"""
        from core.models.finance.invoice import (
            InvoiceCreateRequest,
            invoice_create_request_to_dto,
            invoice_dto_to_pure,
        )

        body = await request.json()

        try:
            invoice_request = InvoiceCreateRequest(**body)
        except Exception as e:
            return Result.fail(Errors.validation(f"Invalid invoice data: {e}"))

        # Convert request to domain model
        dto = invoice_create_request_to_dto(invoice_request, current_user.uid)
        invoice = invoice_dto_to_pure(dto)

        result = await finance_service.create_invoice(invoice)

        if result.is_ok:
            logger.info(f"Invoice {result.value.uid} created by admin")
            return Result.ok(
                {
                    "invoice": result.value.to_dto().to_dict(),
                    "message": "Invoice created successfully",
                }
            )
        return result

    # IMPORTANT: Static routes (/stats) must come BEFORE parameterized routes (/{uid})
    @rt("/api/invoices/stats")
    @require_admin(user_service_getter)
    @boundary_handler()
    async def get_invoice_stats_route(request, current_user) -> Result[Any]:
        """Get invoice statistics (admin only)"""
        result = await finance_service.get_invoice_stats(user_uid=current_user.uid)

        if result.is_ok:
            return Result.ok(result.value)
        return result

    @rt("/api/invoices/get")
    @require_admin(user_service_getter)
    @boundary_handler()
    async def get_invoice_route(request, current_user, uid: str) -> Result[Any]:
        """Get a specific invoice by UID (admin only)"""
        result = await finance_service.get_invoice(uid)

        if result.is_ok:
            if result.value is None:
                return Result.fail(Errors.not_found("Invoice", uid))
            return Result.ok(
                {
                    "invoice": result.value.to_dto().to_dict(),
                }
            )
        return result

    @rt("/api/invoices/pdf")
    @require_admin(user_service_getter)
    async def download_invoice_pdf_route(request, current_user, uid: str):
        """Download invoice as PDF (admin only)"""
        from starlette.responses import Response

        result = await finance_service.generate_invoice_pdf(uid)

        if result.is_error:
            error = result.error
            return Response(
                content=f"Error: {error.message if error else 'Unknown error'}",
                status_code=500,
                media_type="text/plain",
            )

        return Response(
            content=result.value,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="invoice-{uid}.pdf"',
            },
        )

    # ========================================================================
    # BULK OPERATIONS (Admin-Only)
    # ========================================================================

    @rt("/api/expenses/bulk/categorize")
    @require_admin(user_service_getter)
    @boundary_handler()
    async def bulk_categorize_expenses_route(request, current_user) -> Result[Any]:
        """Bulk categorize multiple expenses (admin only)"""
        body = await request.json()

        expense_uids = body.get("expense_uids", [])
        category = body.get("category")
        subcategory = body.get("subcategory")

        if not expense_uids or not category:
            return Result.fail(Errors.validation("expense_uids and category are required"))

        from core.models.finance.finance_pure import ExpenseCategory

        category_enum = ExpenseCategory(category)

        # Call service
        result = await finance_service.bulk_categorize(expense_uids, category_enum, subcategory)

        if result.is_ok:
            expenses = result.value
            logger.info(
                f"Bulk categorized {len(expenses) if expenses else 0} expenses to {category} by admin"
            )
            return Result.ok(
                {
                    "expenses": expenses,
                    "updated_count": len(expenses) if expenses else 0,
                    "category": category,
                    "subcategory": subcategory,
                }
            )
        else:
            error = result.error
            return Result.fail(
                Errors.system(
                    message=error.user_message or error.message if error else "Unknown error"
                )
            )

    logger.info("Finance API routes registered")
    return []


# Export
__all__ = ["create_finance_api_routes"]
