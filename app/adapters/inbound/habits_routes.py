"""
Habits Routes - Clean Architecture Factory
==========================================

Minimal factory that wires API and UI routes using DomainRouteConfig.
"""

from adapters.inbound.habits_api import create_habits_api_routes
from adapters.inbound.habits_ui import create_habits_ui_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

HABITS_CONFIG = DomainRouteConfig(
    domain_name="habits",
    primary_service_attr="habits",
    api_factory=create_habits_api_routes,
    ui_factory=create_habits_ui_routes,
    api_related_services={
        # Format: {kwarg_name: container_attr}
        # Each entry is passed to api_factory as: kwarg_name=getattr(services, container_attr)
        "user_service": "user_service",  # user_service=services.user_service
        "goals_service": "goals",  # goals_service=services.goals
    },
)


def create_habits_routes(app, rt, services, _sync_service=None):
    """Wire habits API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, HABITS_CONFIG)


__all__ = ["create_habits_routes"]
