"""
Transfer UI Routes — Submissions + Reports Dual-Pane
=====================================================

The /transfer page shows outgoing submissions (left) and incoming
reports (right) side-by-side on desktop, stacked on mobile.

Routes:
- GET /transfer — Dual-pane landing page

Both panes load data via existing HTMX endpoints from study_ui.py.
"""

from typing import Any

from fasthtml.common import Div, H3, P
from starlette.requests import Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import RouteDecorator, RouteList
from core.utils.logging import get_logger
from ui.layouts.base_page import BasePage
from ui.patterns.dual_pane import DualPaneLayout
from ui.patterns.page_header import PageHeader

logger = get_logger("skuel.routes.transfer")


def create_transfer_ui_routes(
    _app: Any,
    rt: RouteDecorator,
    services: Any,
) -> RouteList:
    """Register /transfer UI routes."""

    @rt("/transfer")
    async def transfer_landing(request: Request) -> Any:
        """Transfer hub — submissions + reports dual-pane."""
        require_authenticated_user(request)

        left_pane = Div(
            H3("My Submissions", cls="text-lg font-semibold mb-3"),
            Div(
                P("Loading submissions...", cls="text-center text-muted-foreground"),
                id="submissions-yours-list",
                **{
                    "hx-get": "/submissions/list",
                    "hx-trigger": "load",
                    "hx-swap": "outerHTML",
                },
            ),
            cls="min-h-[200px]",
        )

        right_pane = Div(
            H3("Exercise Reports", cls="text-lg font-semibold mb-3"),
            Div(
                P("Loading reports...", cls="text-center text-muted-foreground"),
                id="feedback-list",
                **{
                    "hx-get": "/reports/list",
                    "hx-trigger": "load",
                    "hx-swap": "outerHTML",
                },
            ),
            cls="min-h-[200px]",
        )

        content = Div(
            PageHeader("Transfer", subtitle="Submissions sent and reports received"),
            DualPaneLayout(left_pane, right_pane),
        )

        return await BasePage(
            content=content,
            title="Transfer",
            request=request,
            active_page="transfer",
        )

    logger.info("Transfer UI routes created (/transfer)")
    return []  # Routes registered via @rt() decorators
