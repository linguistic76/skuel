"""
Choices Routes - Configuration-Driven Registration
====================================================

Factory that wires choices API and UI routes using DomainRouteConfig.

Architecture:
    - API Routes: choices_api.py (CRUD, query, intelligence)
    - UI Routes:  choices_ui.py  (list, detail, cross-domain views)
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from adapters.inbound.choices_api import create_choices_api_routes
from adapters.inbound.choices_ui import create_choices_ui_routes

if TYPE_CHECKING:
    from services_bootstrap import Services


CHOICES_CONFIG = DomainRouteConfig(
    domain_name="choices",
    primary_service_attr="choices",
    api_factory=create_choices_api_routes,
    ui_factory=create_choices_ui_routes,
)


def create_choices_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> RouteList:
    """Wire choices API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, CHOICES_CONFIG)


__all__ = ["create_choices_routes"]
