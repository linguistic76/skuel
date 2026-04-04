"""
Habits Routes - Configuration-Driven Registration
===================================================

Factory that wires habits API and UI routes using DomainRouteConfig.

Architecture:
    - API Routes: habits_api.py (CRUD, query, intelligence)
    - UI Routes:  habits_ui.py  (list, detail, cross-domain views)
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from adapters.inbound.habits_api import create_habits_api_routes
from adapters.inbound.habits_ui import create_habits_ui_routes

if TYPE_CHECKING:
    from services_bootstrap import Services


HABITS_CONFIG = DomainRouteConfig(
    domain_name="habits",
    primary_service_attr="habits",
    api_factory=create_habits_api_routes,
    ui_factory=create_habits_ui_routes,
)


def create_habits_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> RouteList:
    """Wire habits API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, HABITS_CONFIG)


__all__ = ["create_habits_routes"]
