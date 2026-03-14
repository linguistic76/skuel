"""
Context Routes - Configuration-Driven Registration
=================================================

Wires Context-Aware API routes using DomainRouteConfig pattern.
"""

from adapters.inbound.context_aware_api import create_context_aware_api_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

CONTEXT_CONFIG = DomainRouteConfig(
    domain_name="context",
    primary_service_attr="context_service",
    api_factory=create_context_aware_api_routes,
    ui_factory=None,  # No UI routes — profile page handles context display
    api_related_services={},
)


def create_context_aware_routes(app, rt, services, _sync_service=None):
    """
    Wire context-aware API and UI routes using configuration-driven registration.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Service container with context service
        _sync_service: Optional sync service (unused, for signature compatibility)

    Returns:
        List of all registered route functions
    """
    return register_domain_routes(app, rt, services, CONTEXT_CONFIG)


__all__ = ["create_context_aware_routes"]
