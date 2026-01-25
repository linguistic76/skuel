"""
Choices Routes - Clean Architecture Factory
==========================================

Minimal factory that wires API and UI routes using DomainRouteConfig.
"""

from adapters.inbound.choice_ui import create_choice_ui_routes
from adapters.inbound.choices_api import create_choices_api_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

CHOICES_CONFIG = DomainRouteConfig(
    domain_name="choices",
    primary_service_attr="choices",
    api_factory=create_choices_api_routes,
    ui_factory=create_choice_ui_routes,
    api_related_services={
        # Format: {kwarg_name: container_attr}
        # Each entry is passed to api_factory as: kwarg_name=getattr(services, container_attr)
        "user_service": "user_service",  # user_service=services.user_service
        "goals_service": "goals",  # goals_service=services.goals
    },
)


def create_choices_routes(app, rt, services, _sync_service=None):
    """Wire choices API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, CHOICES_CONFIG)


__all__ = ["create_choices_routes"]
