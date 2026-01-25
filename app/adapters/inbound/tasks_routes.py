"""
Tasks Routes - Clean Architecture Factory
=========================================

Minimal factory that wires API and UI routes using DomainRouteConfig.
"""

from adapters.inbound.tasks_api import create_tasks_api_routes
from adapters.inbound.tasks_ui import create_tasks_ui_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

TASKS_CONFIG = DomainRouteConfig(
    domain_name="tasks",
    primary_service_attr="tasks",
    api_factory=create_tasks_api_routes,
    ui_factory=create_tasks_ui_routes,
    api_related_services={
        # Format: {kwarg_name: container_attr}
        # Each entry is passed to api_factory as: kwarg_name=getattr(services, container_attr)
        "user_service": "user_service",  # user_service=services.user_service
        "goals_service": "goals",  # goals_service=services.goals
        "habits_service": "habits",  # habits_service=services.habits
    },
)


def create_tasks_routes(app, rt, services, _sync_service=None):
    """Wire tasks API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, TASKS_CONFIG)


__all__ = ["create_tasks_routes"]
