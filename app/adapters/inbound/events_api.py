"""Events API routes.

Provides HTMX-compatible endpoints for event status updates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from core.utils.logging import get_logger
from ui.activities.events_views import EventCard
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import (
        FastHTMLApp,
        RouteDecorator,
        RouteList,
    )
    from core.services.events_service import EventsService

logger = get_logger("skuel.routes.events_api")


def create_events_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    events_service: EventsService,
) -> RouteList:
    """Register Events API routes."""
    routes: list[Any] = []

    @rt("/api/events/{uid}/status", methods=["POST"])
    async def update_event_status(request: Request, uid: str) -> Any:
        """Update event status (HTMX endpoint). Returns updated EventCard."""
        user_uid = require_authenticated_user(request)

        # Verify ownership
        event_result = await events_service.get_event(uid)
        if event_result.is_error:
            return render_error_banner("Event not found")
        event = event_result.value
        if event.user_uid != user_uid:
            return render_error_banner("Event not found")

        # Get new status from form data
        form = await request.form()
        new_status = form.get("status")

        if not new_status:
            return render_error_banner("Missing status value")

        result = await events_service.update(uid, {"status": new_status})
        if result.is_error:
            error = result.expect_error()
            return render_error_banner(error.user_message or error.message)

        return EventCard(result.value)

    routes.extend([update_event_status])
    return routes
