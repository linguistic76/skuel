"""Workbench Route Configuration — hub, preview endpoints, and history stub.

The Workbench is the user's hub for getting work into SKUEL:
upload activity data, submit exercises, and view upload history.

Routes:
- GET /workbench — hub page (no sidebar)
- GET /api/workbench/upload/preview — HTMX preview for upload block
- GET /api/workbench/submit/preview — HTMX preview for submit block
- GET /api/workbench/history/preview — HTMX preview for history block
- GET /workbench/history — upload history page (stub)
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div, P

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from core.utils.logging import get_logger
from ui.patterns.hub import HubPreviewEmpty
from ui.workbench.nav import render_workbench_sidebar_page

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from services_bootstrap._container import Services

logger = get_logger("skuel.routes.workbench")


def create_workbench_routes(
    app: "FastHTMLApp",
    rt: "RouteDecorator",
    services: "Services",
) -> None:
    """Register Workbench hub, preview, and child routes."""

    # ========================================================================
    # HUB PAGE
    # ========================================================================

    @rt("/workbench")
    async def workbench_hub(request: Request) -> Any:
        """Workbench hub — entry point with domain blocks, no sidebar."""
        require_authenticated_user(request)
        from ui.layouts.base_page import BasePage
        from ui.workbench.hub import WorkbenchHub

        return await BasePage(
            content=WorkbenchHub(),
            title="Workbench",
            request=request,
            active_page="workbench",
        )

    # ========================================================================
    # HTMX PREVIEW ENDPOINTS
    # ========================================================================

    @rt("/api/workbench/upload/preview")
    async def upload_preview(request: Request) -> Any:
        """HTMX preview: recent uploads summary."""
        require_authenticated_user(request)
        return HubPreviewEmpty("uploads")

    @rt("/api/workbench/submit/preview")
    async def submit_preview(request: Request) -> Any:
        """HTMX preview: pending exercises to submit."""
        require_authenticated_user(request)
        return HubPreviewEmpty("submissions")

    @rt("/api/workbench/history/preview")
    async def history_preview(request: Request) -> Any:
        """HTMX preview: upload history summary."""
        require_authenticated_user(request)
        return Div(
            P("Coming soon", cls="text-sm text-foreground/40 text-center py-3"),
        )

    # ========================================================================
    # HISTORY PAGE (STUB)
    # ========================================================================

    @rt("/workbench/history")
    async def workbench_history(request: Request) -> Any:
        """Upload history — stub page."""
        require_authenticated_user(request)
        from ui.patterns.empty_state import EmptyState
        from ui.patterns.page_header import PageHeader

        content = Div(
            PageHeader(
                "Upload History",
                subtitle="Track your uploaded activity data and exercise submissions",
            ),
            EmptyState(
                "Upload history is coming soon",
                description="This page will show your upload history with the ability to view, re-upload, and manage your contributions.",
            ),
            cls="max-w-3xl mx-auto px-4",
        )
        return await render_workbench_sidebar_page(
            content=content,
            active="history",
            request=request,
        )

    logger.info("Workbench routes registered")


__all__ = ["create_workbench_routes"]
