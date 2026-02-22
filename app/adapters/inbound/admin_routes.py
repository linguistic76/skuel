"""
Admin Routes - Clean Architecture Factory
==========================================

Minimal factory that wires admin API routes using DomainRouteConfig.
"""

from adapters.inbound.admin_api import create_admin_api_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

ADMIN_CONFIG = DomainRouteConfig(
    domain_name="admin",
    primary_service_attr="user_service",
    api_factory=create_admin_api_routes,
    ui_factory=None,  # No UI routes for admin
    api_related_services={
        "graph_auth": "graph_auth",
    },
)


def create_admin_routes(app, rt, services, _sync_service=None):
    """Wire admin API routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, ADMIN_CONFIG)


__all__ = ["create_admin_routes"]
