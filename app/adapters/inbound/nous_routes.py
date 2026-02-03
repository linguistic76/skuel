"""
Nous Routes - Clean Architecture Factory
=========================================

Minimal factory that wires Nous UI routes using DomainRouteConfig.

This is a UI-only domain (no API routes).
"""

from adapters.inbound.nous_ui import create_nous_ui_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

NOUS_CONFIG = DomainRouteConfig(
    domain_name="nous",
    primary_service_attr="ku",
    api_factory=None,  # UI-only domain (no API routes)
    ui_factory=create_nous_ui_routes,
    api_related_services={},
    ui_related_services={},
)


def create_nous_routes(app, rt, services, _sync_service=None):
    """Wire Nous UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, NOUS_CONFIG)


__all__ = ["create_nous_routes"]
