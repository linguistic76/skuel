"""Goals route registration.

Wires Goals UI and API routes into the application.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.inbound.goals_api import create_goals_api_routes
from adapters.inbound.goals_ui import create_goals_ui_routes
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
    from services_bootstrap import Services

logger = get_logger("skuel.routes.goals")


def create_goals_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: Services,
) -> RouteList:
    """Register all goals routes (UI + API)."""
    goals_service = services.goals
    if goals_service is None:
        logger.warning("GoalsService not available — goal routes not registered")
        return []

    routes: list = []
    routes.extend(create_goals_ui_routes(app, rt, goals_service))
    routes.extend(create_goals_api_routes(app, rt, goals_service))

    logger.info("Goal routes registered")
    return routes
