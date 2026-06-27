"""Journals domain routes.

Shell page for PR 1 — establishes /journals in the Tasks+ sidebar.
Full workflow (DNWF for FOUNDER tier, continuous for STANDARD) lands in PR 2.

Route:
    GET /journals  — authenticated shell page
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.responses import Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from services_bootstrap._container import Services


logger = get_logger("skuel.routes.journals")


def create_journals_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: Services,
) -> None:
    """Register Journal domain routes."""

    assert services.user is not None, "UserService must be wired before journals routes"
    user_service = services.user

    @rt("/journals")
    async def journals_page(request: Request) -> Any:
        """Render the Journal landing page."""
        user_uid = require_authenticated_user(request)

        from ui.activities.nav import render_activity_sidebar_page
        from ui.journals import JournalsPage

        user_result = await user_service.get_user(user_uid)
        if user_result.is_error or user_result.value is None:
            return Response("Could not load user", status_code=500)

        return await render_activity_sidebar_page(
            content=JournalsPage(user_result.value),
            active="journals",
            request=request,
            title="Journal",
        )
