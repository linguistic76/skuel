"""
Article Routes - Configuration-Driven Registration
====================================================

Wires Article API and UI routes using DomainRouteConfig pattern.

Version: 3.0 (Renamed from KU to Article)
"""

from adapters.inbound.article_api import create_article_api_routes
from adapters.inbound.article_ui import create_article_ui_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

ARTICLE_CONFIG = DomainRouteConfig(
    domain_name="article",
    primary_service_attr="article",  # services.article
    api_factory=create_article_api_routes,
    ui_factory=create_article_ui_routes,
    api_related_services={
        "user_service": "user_service",
    },
)


def create_article_routes(app, rt, services, _sync_service=None):
    """Wire Article API and UI routes."""
    return register_domain_routes(app, rt, services, ARTICLE_CONFIG)


__all__ = ["create_article_routes"]
