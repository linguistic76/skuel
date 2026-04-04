"""
Principles Routes - Configuration-Driven Registration
=======================================================

Factory that wires principles API and UI routes using DomainRouteConfig.

Architecture:
    - API Routes: principles_api.py (CRUD, query, intelligence)
    - UI Routes:  principles_ui.py  (list, detail, cross-domain views)
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from adapters.inbound.principles_api import create_principles_api_routes
from adapters.inbound.principles_ui import create_principles_ui_routes

if TYPE_CHECKING:
    from services_bootstrap import Services


PRINCIPLES_CONFIG = DomainRouteConfig(
    domain_name="principles",
    primary_service_attr="principles",
    api_factory=create_principles_api_routes,
    ui_factory=create_principles_ui_routes,
)


def create_principles_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> RouteList:
    """Wire principles API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, PRINCIPLES_CONFIG)


__all__ = ["create_principles_routes"]
