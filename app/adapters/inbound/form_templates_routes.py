"""
Form Template Routes - Configuration-Driven Registration
==========================================================

Wires FormTemplate API routes using DomainRouteConfig.
Admin-only CRUD + lesson linking.
"""

from adapters.inbound.form_templates_api import create_form_templates_api_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes

FORM_TEMPLATES_CONFIG = DomainRouteConfig(
    domain_name="form_templates",
    primary_service_attr="form_templates",
    api_factory=create_form_templates_api_routes,
    ui_factory=None,  # No dedicated UI routes — forms render inline in lessons
    api_related_services={
        "user_service": "user_service",
    },
)


def create_form_templates_routes(app, rt, services, _sync_service=None):
    """Wire form template API routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, FORM_TEMPLATES_CONFIG)


__all__ = ["create_form_templates_routes"]
