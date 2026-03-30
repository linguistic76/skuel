"""Principles route registration.

Wires Principles UI and API routes into the application.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.inbound.principles_api import create_principles_api_routes
from adapters.inbound.principles_ui import create_principles_ui_routes
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
    from services_bootstrap import Services

logger = get_logger("skuel.routes.principles")


def create_principles_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: Services,
) -> RouteList:
    """Register all principles routes (UI + API)."""
    principles_service = services.principles
    if principles_service is None:
        logger.warning("PrinciplesService not available — principle routes not registered")
        return []

    routes: list = []
    routes.extend(create_principles_ui_routes(app, rt, principles_service))
    routes.extend(create_principles_api_routes(app, rt, principles_service))

    logger.info("Principle routes registered")
    return routes
