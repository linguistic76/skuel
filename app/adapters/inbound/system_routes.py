"""
System Routes - Clean Architecture Factory
==========================================

Minimal factory that wires System API and UI routes using DomainRouteConfig.

This replaces the monolithic system_routes_impl.py with clean separation:
- system_api.py: Pure JSON API endpoints (health, metrics, diagnostics)
- system_ui.py: Component-based system UI (home page, 404 page)
- This file: Minimal wiring factory
"""

from adapters.inbound.system_api import create_system_api_routes
from adapters.inbound.system_ui import create_system_ui_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

SYSTEM_CONFIG = DomainRouteConfig(
    domain_name="system",
    primary_service_attr="system_service",
    api_factory=create_system_api_routes,
    ui_factory=create_system_ui_routes,
    api_related_services={
        "user_service": "user_service",
    },
    ui_related_services={},
)


def create_system_routes(app, rt, services):
    """Wire system API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, SYSTEM_CONFIG)


__all__ = ["create_system_routes"]
