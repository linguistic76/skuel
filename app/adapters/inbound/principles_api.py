"""Principles API routes.

Provides HTMX-compatible endpoints for principle status updates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import require_authenticated_user
from core.utils.logging import get_logger
from ui.activities.principles_views import PrincipleCard
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from starlette.requests import Request

    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
    from core.services.principles_service import PrinciplesService

logger = get_logger("skuel.routes.principles_api")


def create_principles_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    principles_service: PrinciplesService,
) -> RouteList:
    """Register Principles API routes."""
    routes: list[Any] = []

    @rt("/api/principles/{uid}/status", methods=["POST"])
    async def update_principle_status(request: Request, uid: str) -> Any:
        """Update principle status (HTMX endpoint). Returns updated PrincipleCard."""
        user_uid = require_authenticated_user(request)

        # Verify ownership
        principle_result = await principles_service.get_principle(uid)
        if principle_result.is_error:
            return render_error_banner("Principle not found")
        principle = principle_result.value
        if principle.user_uid != user_uid:
            return render_error_banner("Principle not found")

        # Get new status from form data
        form = await request.form()
        new_status = form.get("status")

        if not new_status:
            return render_error_banner("Missing status value")

        result = await principles_service.core.update(uid, {"status": new_status})
        if result.is_error:
            error = result.expect_error()
            return render_error_banner(error.user_message or error.message)

        return PrincipleCard(result.value)

    routes.extend([update_principle_status])
    return routes
