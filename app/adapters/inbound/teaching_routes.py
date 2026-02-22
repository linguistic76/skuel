"""
Teaching Routes - Clean Architecture Factory
===============================================

Wires Teaching review API + UI routes using DomainRouteConfig.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from adapters.inbound.teaching_api import create_teaching_api_routes
from adapters.inbound.teaching_ui import create_teaching_ui_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

TEACHING_CONFIG = DomainRouteConfig(
    domain_name="teaching",
    primary_service_attr="teacher_review",
    api_factory=create_teaching_api_routes,
    ui_factory=create_teaching_ui_routes,
    api_related_services={
        "user_service": "user_service",
    },
    ui_related_services={
        "user_service": "user_service",
    },
)


def create_teaching_routes(app, rt, services, _sync_service=None):
    """Wire teaching API + UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, TEACHING_CONFIG)


__all__ = ["create_teaching_routes"]
