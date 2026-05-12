"""Events API routes.

Provides HTMX-compatible endpoints for event status updates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.inbound.route_factories import (
    ActivityStatusApiConfig,
    create_activity_status_api_routes,
)
from ui.activities.events_views import EventCard

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.events_service import EventsService
    from core.utils.result_simplified import Result


def create_events_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    events_service: EventsService,
    **_kwargs: Any,
) -> list[Any]:
    """Register Events API routes."""

    async def update(uid: str, new_status: str) -> Result[Any]:
        return await events_service.update(uid, {"status": new_status})

    return create_activity_status_api_routes(
        rt,
        ActivityStatusApiConfig(
            domain_name="events",
            singular="event",
            service=events_service,
            update_status=update,
            card_fn=EventCard,
        ),
    )
