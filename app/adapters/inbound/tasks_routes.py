"""Tasks route registration.

Wires Tasks UI and API routes into the application.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.inbound.tasks_api import create_tasks_api_routes
from adapters.inbound.tasks_ui import create_tasks_ui_routes
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
    from services_bootstrap import Services

logger = get_logger("skuel.routes.tasks")


def create_tasks_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    services: Services,
) -> RouteList:
    """Register all tasks routes (UI + API)."""
    tasks_service = services.tasks
    if tasks_service is None:
        logger.warning("TasksService not available — task routes not registered")
        return []

    routes: list = []
    routes.extend(create_tasks_ui_routes(app, rt, tasks_service))
    routes.extend(create_tasks_api_routes(app, rt, tasks_service))

    logger.info("Task routes registered")
    return routes
