"""
MOC Routes - Configuration-Driven Registration
===============================================

Factory that wires MOC API and UI routes using DomainRouteConfig.

MOC is KU-based: a KU "is" a MOC when it has outgoing ORGANIZES relationships.
Provides non-linear knowledge navigation complementing Learning Paths.

Architecture:
    - API Routes: moc_api.py (9 endpoints: organize, unorganize, reorder, etc.)
    - UI Routes: moc_ui.py (dashboard, detail views, section navigation)
"""

from adapters.inbound.moc_api import create_moc_api_routes
from adapters.inbound.moc_ui import create_moc_ui_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

MOC_CONFIG = DomainRouteConfig(
    domain_name="moc",
    primary_service_attr="moc",
    api_factory=create_moc_api_routes,
    ui_factory=create_moc_ui_routes,
    api_related_services={
        "user_service": "user_service",
    },
    ui_related_services={
        "user_service": "user_service",
    },
)


def create_moc_routes(app, rt, services, _sync_service=None):
    """Wire MOC API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, MOC_CONFIG)


__all__ = ["create_moc_routes"]
