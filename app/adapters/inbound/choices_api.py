"""Choices API routes.

Provides HTMX-compatible endpoints for choice status updates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import require_authenticated_user
from core.utils.logging import get_logger
from ui.activities.choices_views import ChoiceCard
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import (
        FastHTMLApp,
        Request,
        RouteDecorator,
        RouteList,
    )
    from core.services.choices_service import ChoicesService

logger = get_logger("skuel.routes.choices_api")


def create_choices_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    choices_service: ChoicesService,
) -> RouteList:
    """Register Choices API routes."""
    routes: list[Any] = []

    @rt("/api/choices/{uid}/status", methods=["POST"])
    async def update_choice_status(request: Request, uid: str) -> Any:
        """Update choice status (HTMX endpoint). Returns updated ChoiceCard."""
        user_uid = require_authenticated_user(request)

        # Verify ownership
        choice_result = await choices_service.get_choice(uid)
        if choice_result.is_error:
            return render_error_banner("Choice not found")
        choice = choice_result.value
        if choice.user_uid != user_uid:
            return render_error_banner("Choice not found")

        # Get new status from form data
        form = await request.form()
        new_status = form.get("status")

        if not new_status:
            return render_error_banner("Missing status value")

        result = await choices_service.core.update(uid, {"status": new_status})
        if result.is_error:
            error = result.expect_error()
            return render_error_banner(error.user_message or error.message)

        return ChoiceCard(result.value)

    routes.extend([update_choice_status])
    return routes
