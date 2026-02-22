"""
Groups Routes - Clean Architecture Factory
============================================

Wires Group API and UI routes using DomainRouteConfig.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from adapters.inbound.groups_api import create_groups_api_routes
from adapters.inbound.groups_ui import create_groups_ui_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

GROUPS_CONFIG = DomainRouteConfig(
    domain_name="groups",
    primary_service_attr="group_service",
    api_factory=create_groups_api_routes,
    ui_factory=create_groups_ui_routes,
    api_related_services={
        "user_service": "user_service",
    },
)


def create_groups_routes(app, rt, services, _sync_service=None):
    """Wire group API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, GROUPS_CONFIG)


__all__ = ["create_groups_routes"]
