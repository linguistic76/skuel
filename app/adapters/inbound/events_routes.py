"""
Events Routes - Configuration-Driven Registration
===================================================

Factory that wires events API and UI routes using DomainRouteConfig.

Architecture:
    - API Routes: events_api.py (CRUD, query, intelligence)
    - UI Routes:  events_ui.py  (list, detail, cross-domain views)
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from adapters.inbound.events_api import create_events_api_routes
from adapters.inbound.events_ui import create_events_ui_routes

if TYPE_CHECKING:
    from services_bootstrap import Services


EVENTS_CONFIG = DomainRouteConfig(
    domain_name="events",
    primary_service_attr="events",
    api_factory=create_events_api_routes,
    ui_factory=create_events_ui_routes,
)


def create_events_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> RouteList:
    """Wire events API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, EVENTS_CONFIG)


__all__ = ["create_events_routes"]
