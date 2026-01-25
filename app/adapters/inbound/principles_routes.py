"""
Principles Routes - Clean Architecture Factory
=============================================

Minimal factory that wires API and UI routes using DomainRouteConfig.
"""

from adapters.inbound.principles_api import create_principles_api_routes
from adapters.inbound.principles_ui import create_principles_ui_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

PRINCIPLES_CONFIG = DomainRouteConfig(
    domain_name="principles",
    primary_service_attr="principles",
    api_factory=create_principles_api_routes,
    ui_factory=create_principles_ui_routes,
    api_related_services={
        # Format: {kwarg_name: container_attr}
        # Each entry is passed to api_factory as: kwarg_name=getattr(services, container_attr)
        "user_service": "user_service",  # user_service=services.user_service
        "goals_service": "goals",  # goals_service=services.goals
        "habits_service": "habits",  # habits_service=services.habits
    },
)


def create_principles_routes(app, rt, services, _sync_service=None):
    """Wire principles API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, PRINCIPLES_CONFIG)


__all__ = ["create_principles_routes"]
