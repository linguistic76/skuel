"""Choices route registration.

Wires Choices UI and API routes into the application.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.inbound.choices_api import create_choices_api_routes
from adapters.inbound.choices_ui import create_choices_ui_routes
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
    from services_bootstrap import Services

logger = get_logger("skuel.routes.choices")


def create_choices_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: Services,
) -> RouteList:
    """Register all choices routes (UI + API)."""
    choices_service = services.choices
    if choices_service is None:
        logger.warning("ChoicesService not available — choice routes not registered")
        return []

    routes: list = []
    routes.extend(create_choices_ui_routes(app, rt, choices_service))
    routes.extend(create_choices_api_routes(app, rt, choices_service))

    logger.info("Choice routes registered")
    return routes
