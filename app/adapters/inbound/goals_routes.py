"""
Goals Routes - Clean Architecture Factory
=========================================

Minimal factory that wires API and UI routes using DomainRouteConfig.
"""

from adapters.inbound.goals_api import create_goals_api_routes
from adapters.inbound.goals_ui import create_goals_ui_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

GOALS_CONFIG = DomainRouteConfig(
    domain_name="goals",
    primary_service_attr="goals",
    api_factory=create_goals_api_routes,
    ui_factory=create_goals_ui_routes,
    api_related_services={
        # Format: {kwarg_name: container_attr}
        # Each entry is passed to api_factory as: kwarg_name=getattr(services, container_attr)
        "user_service": "user_service",  # user_service=services.user_service
        "habits_service": "habits",  # habits_service=services.habits
    },
)


def create_goals_routes(app, rt, services, _sync_service=None):
    """Wire goals API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, GOALS_CONFIG)


__all__ = ["create_goals_routes"]
