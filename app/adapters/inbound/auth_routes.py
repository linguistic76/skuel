"""
Authentication Routes - Clean Architecture Factory
===================================================

Minimal factory that wires authentication API and UI routes using DomainRouteConfig.
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.auth_api import create_auth_api_routes
from adapters.inbound.auth_ui import create_auth_ui_routes
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

if TYPE_CHECKING:
    from services_bootstrap import Services


AUTH_CONFIG = DomainRouteConfig(
    domain_name="auth",
    primary_service_attr="graph_auth",
    api_factory=create_auth_api_routes,
    ui_factory=create_auth_ui_routes,
    api_related_services={
        "user_service": "user_service",
    },
    ui_related_services={
        "user_service": "user_service",
    },
)


def create_auth_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> None:
    """Wire authentication API and UI routes using configuration-driven registration."""
    register_domain_routes(app, rt, services, AUTH_CONFIG)


__all__ = ["create_auth_routes"]
