"""
Tasks Routes - Configuration-Driven Registration
==================================================

Factory that wires tasks API and UI routes using DomainRouteConfig.

Architecture:
    - API Routes: tasks_api.py (CRUD, query, intelligence)
    - UI Routes:  tasks_ui.py  (list, detail, cross-domain views)
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from adapters.inbound.tasks_api import create_tasks_api_routes
from adapters.inbound.tasks_ui import create_tasks_ui_routes

if TYPE_CHECKING:
    from services_bootstrap import Services


TASKS_CONFIG = DomainRouteConfig(
    domain_name="tasks",
    primary_service_attr="tasks",
    api_factory=create_tasks_api_routes,
    ui_factory=create_tasks_ui_routes,
)


def create_tasks_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> RouteList:
    """Wire tasks API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, TASKS_CONFIG)


__all__ = ["create_tasks_routes"]
