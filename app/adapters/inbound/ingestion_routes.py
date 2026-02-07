"""
Ingestion Routes - Clean Architecture Factory
==============================================

Minimal factory that wires unified ingestion API and UI routes using DomainRouteConfig.

Handles both MD and YAML formats for all 14 entity types.
"""

from adapters.inbound.ingestion_api import create_ingestion_api_routes
from adapters.inbound.ingestion_ui import create_ingestion_ui_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

INGESTION_CONFIG = DomainRouteConfig(
    domain_name="ingestion",
    primary_service_attr="unified_ingestion",
    api_factory=create_ingestion_api_routes,
    ui_factory=create_ingestion_ui_routes,
    api_related_services={
        "user_service": "user_service",
    },
    ui_related_services={
        "user_service": "user_service",
    },
)


def create_ingestion_routes(app, rt, services):
    """Wire ingestion API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, INGESTION_CONFIG)


__all__ = ["create_ingestion_routes"]
