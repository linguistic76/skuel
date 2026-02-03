"""
Visualization Routes - Clean Architecture Factory
=================================================

Minimal factory that wires visualization API routes using DomainRouteConfig.
"""

from adapters.inbound.visualization_api import create_visualization_api_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

VISUALIZATION_CONFIG = DomainRouteConfig(
    domain_name="visualization",
    primary_service_attr="visualization",
    api_factory=create_visualization_api_routes,
    ui_factory=None,  # No UI routes for visualization
    api_related_services={
        "tasks_service": "tasks",
        "habits_service": "habits",
        "calendar_service": "calendar",
        "goals_service": "goals",
    },
)


def create_visualization_routes(app, rt, services, _sync_service=None):
    """Wire visualization API routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, VISUALIZATION_CONFIG)


__all__ = ["create_visualization_routes"]
