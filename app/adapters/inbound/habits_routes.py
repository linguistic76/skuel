"""Habits route registration.

Wires Habits UI and API routes into the application.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.inbound.habits_api import create_habits_api_routes
from adapters.inbound.habits_ui import create_habits_ui_routes
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
    from services_bootstrap import Services

logger = get_logger("skuel.routes.habits")


def create_habits_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: Services,
) -> RouteList:
    """Register all habits routes (UI + API)."""
    habits_service = services.habits
    if habits_service is None:
        logger.warning("HabitsService not available — habit routes not registered")
        return []

    routes: list = []
    routes.extend(create_habits_ui_routes(app, rt, habits_service))
    routes.extend(create_habits_api_routes(app, rt, habits_service))

    logger.info("Habit routes registered")
    return routes
