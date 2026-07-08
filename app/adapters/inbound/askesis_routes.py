"""
Askesis Routes - Configuration-Driven Registration
=================================================

Wires Askesis API and UI routes using DomainRouteConfig pattern.

Benefits:
- Consistent with other domain route files
- Soft-fail service validation
- Minimal boilerplate
- Clean separation of concerns

Version: 2.0 (Migrated to DomainRouteConfig pattern)
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.askesis_api import create_askesis_api_routes
from adapters.inbound.askesis_ui import create_askesis_ui_routes
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

if TYPE_CHECKING:
    from services_bootstrap import Services


# Configuration for Askesis routes
ASKESIS_CONFIG = DomainRouteConfig(
    domain_name="askesis",
    primary_service_attr="askesis",  # services.askesis
    api_factory=create_askesis_api_routes,
    ui_factory=create_askesis_ui_routes,
    api_related_services={
        "intelligence_tier": "intelligence_tier",
        "user_service": "user",
    },
    ui_related_services={
        "intelligence_tier": "intelligence_tier",
        "user_service": "user",
        "ku_service": "ku",  # NOUS topic vocabulary for the composer scope control
        "search_router": "search_router",  # NOUS sub-topic vocabulary (Ku+PS merge)
    },
)


def create_askesis_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> None:
    """
    Wire askesis API and UI routes using configuration-driven registration.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Service container with askesis service
        _sync_service: Optional sync service (unused, for signature compatibility)
    """
    register_domain_routes(app, rt, services, ASKESIS_CONFIG)


__all__ = ["create_askesis_routes"]
