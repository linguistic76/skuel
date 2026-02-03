"""
LifePath Routes - Clean Architecture Factory
=============================================

Factory that wires LifePath API and UI routes using DomainRouteConfig.

Domain #14: The Destination - "Everything flows toward the life path"

Philosophy:
    "The user's vision is understood via the words user uses to communicate,
    the UserContext is determined via user's actions."
"""

from adapters.inbound.lifepath_api import create_lifepath_api_routes
from adapters.inbound.lifepath_ui import create_lifepath_ui_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

LIFEPATH_CONFIG = DomainRouteConfig(
    domain_name="lifepath",
    primary_service_attr="lifepath",
    api_factory=create_lifepath_api_routes,
    ui_factory=create_lifepath_ui_routes,
    api_related_services={},  # Self-contained, no additional services
)


def create_lifepath_routes(app, rt, services, _sync_service=None):
    """Wire lifepath API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, LIFEPATH_CONFIG)


__all__ = ["create_lifepath_routes"]
