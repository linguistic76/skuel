"""
Goals Routes - Configuration-Driven Registration
==================================================

Factory that wires goals API and UI routes using DomainRouteConfig.

Architecture:
    - API Routes: goals_api.py (CRUD, query, intelligence)
    - UI Routes:  goals_ui.py  (list, detail, cross-domain views)
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from adapters.inbound.goals_api import create_goals_api_routes
from adapters.inbound.goals_ui import create_goals_ui_routes

if TYPE_CHECKING:
    from services_bootstrap import Services


GOALS_CONFIG = DomainRouteConfig(
    domain_name="goals",
    primary_service_attr="goals",
    api_factory=create_goals_api_routes,
    ui_factory=create_goals_ui_routes,
)


def create_goals_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> RouteList:
    """Wire goals API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, GOALS_CONFIG)


__all__ = ["create_goals_routes"]
