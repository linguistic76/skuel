"""
Finance Hub UI Routes
=====================

Component-based UI rendering for the Finance Hub.

After the ADR-052 Phase 5 demolition only the invoice module survives — this
exposes the single `/finance/invoices` page.

SECURITY: All Finance UI routes require ADMIN role.
"""

__version__ = "4.0"

from typing import Any

from adapters.inbound.auth import make_service_getter, require_admin
from adapters.inbound.fasthtml_types import Request
from core.utils.logging import get_logger
from ui.finance import create_finance_page

logger = get_logger("skuel.routes.finance.ui")


# ============================================================================
# FINANCE HUB ROUTES
# ============================================================================


def create_finance_ui_routes(_app, rt, finance_service, user_service: Any = None) -> list[Any]:
    """
    Create Finance Hub UI routes.

    SECURITY: All Finance UI routes require ADMIN role.
    Finance is its own domain group (not Activity, not Curriculum).
    Admin users can see all finance data (no ownership checks).

    Routes:
        GET /finance/invoices  - Invoice management

    Args:
        _app: FastHTML application instance
        rt: Router instance
        finance_service: Finance service instance
        user_service: User service instance (for role verification)

    """

    get_user_service = make_service_getter(user_service)

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

        return create_finance_page(
            content=content,
            active_section="invoices",
            title="Invoices",
            request=request,
        )

    logger.info("Finance Hub UI routes registered")

    return []


# Export
__all__ = ["create_finance_ui_routes"]
