"""
System Routes - Clean Architecture Factory
==========================================

Minimal factory that wires System API and UI routes using DomainRouteConfig.

This replaces the monolithic system_routes_impl.py with clean separation:
- system_api.py: Pure JSON API endpoints (health, metrics, diagnostics)
- system_ui.py: Component-based system UI (home page, 404 page)
- This file: Minimal wiring factory
"""

from typing import TYPE_CHECKING

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from adapters.inbound.system_api import create_system_api_routes
from adapters.inbound.system_ui import create_system_ui_routes

if TYPE_CHECKING:
    from services_bootstrap import Services

SYSTEM_CONFIG = DomainRouteConfig(
    domain_name="system",
    primary_service_attr="system",
    api_factory=create_system_api_routes,
    ui_factory=create_system_ui_routes,
    api_related_services={
        "user_service": "user",
    },
    ui_related_services={},
)


def create_system_routes(app: FastHTMLApp, rt: RouteDecorator, services: "Services | None") -> None:
    """Wire system API and UI routes using configuration-driven registration."""
    register_domain_routes(app, rt, services, SYSTEM_CONFIG)


__all__ = ["create_system_routes"]
