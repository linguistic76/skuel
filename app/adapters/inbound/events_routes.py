"""Events route registration.

Wires Events UI and API routes into the application.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.inbound.events_api import create_events_api_routes
from adapters.inbound.events_ui import create_events_ui_routes
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
    from services_bootstrap import Services

logger = get_logger("skuel.routes.events")


def create_events_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: Services,
) -> RouteList:
    """Register all events routes (UI + API)."""
    events_service = services.events
    if events_service is None:
        logger.warning("EventsService not available — event routes not registered")
        return []

    routes: list = []
    routes.extend(create_events_ui_routes(app, rt, events_service))
    routes.extend(create_events_api_routes(app, rt, events_service))

    logger.info("Event routes registered")
    return routes
