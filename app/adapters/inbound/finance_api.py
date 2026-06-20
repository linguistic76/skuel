"""
Finance API Routes
==================

Pure JSON API endpoints for finance operations.

After the ADR-052 Phase 5 demolition only the invoice module survives — these
routes cover invoice CRUD, stats, and PDF download. No UI components.
"""

__version__ = "2.0"

from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import make_service_getter, require_admin
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.form_helpers import parse_json_body
from adapters.inbound.result_helpers import require_found
from adapters.inbound.route_factories import parse_int_query_param
from core.ports.query_types import InvoiceStats
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.services.finance_service import FinanceService

logger = get_logger("skuel.routes.finance.api")


# ============================================================================
# API ROUTE CREATION
# ============================================================================


def create_finance_api_routes(
    app: Any, rt: Any, finance_service: "FinanceService", user_service: Any = None
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

    get_user_service = make_service_getter(user_service)

    # ========================================================================
    # INVOICE ROUTES (Admin-Only)
    # ========================================================================

    @rt("/api/invoices", methods=["GET"])
    @require_admin(get_user_service)
    @boundary_handler()
    async def list_invoices_route(request, current_user) -> Result[dict[str, Any]]:
        """List all invoices with optional filters (admin only)"""
        # Get query params
        invoice_type = request.query_params.get("type")  # outgoing or incoming
        status = request.query_params.get("status")
        limit = parse_int_query_param(request.query_params, "limit", 50, minimum=1, maximum=500)

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
        return Result.fail(result)

    @rt("/api/invoices", methods=["POST"])
    @csrf_protected
    @require_admin(get_user_service)
    @boundary_handler()
    async def create_invoice_route(request, current_user) -> Result[dict[str, Any]]:
        """Create a new invoice (admin only)"""
        from core.models.finance.invoice import (
            InvoiceCreateRequest,
            invoice_create_request_to_dto,
            invoice_dto_to_pure,
        )

        parsed = await parse_json_body(request, InvoiceCreateRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        invoice_request = parsed.value

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
        return Result.fail(result)

    # IMPORTANT: Static routes (/stats) must come BEFORE parameterized routes (/{uid})
    @rt("/api/invoices/stats")
    @require_admin(get_user_service)
    @boundary_handler()
    async def get_invoice_stats_route(request, current_user) -> Result[InvoiceStats]:
        """Get invoice statistics (admin only)"""
        result = await finance_service.get_invoice_stats()

        if result.is_ok:
            return Result.ok(result.value)
        return result

    @rt("/api/invoices/get")
    @require_admin(get_user_service)
    @boundary_handler()
    async def get_invoice_route(request, current_user, uid: str) -> Result[dict[str, Any]]:
        """Get a specific invoice by UID (admin only)"""
        found = require_found(await finance_service.get_invoice(uid), "Invoice", uid)
        if found.is_error:
            return Result.fail(found)
        return Result.ok(
            {
                "invoice": found.value.to_dto().to_dict(),
            }
        )

    @rt("/api/invoices/pdf")
    @require_admin(get_user_service)
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

    logger.info("Finance API routes registered")

    return []


# Export
__all__ = ["create_finance_api_routes"]
