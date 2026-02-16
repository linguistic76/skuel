"""
Assignment Routes - Configuration-Driven Registration
============================================================

Wires Assignment API and UI routes using DomainRouteConfig.
Assignments provide reusable LLM instruction templates for any submission type.
"""

from adapters.inbound.assignments_api import create_assignments_api_routes
from adapters.inbound.assignments_ui import create_assignments_ui_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

ASSIGNMENTS_CONFIG = DomainRouteConfig(
    domain_name="assignments",
    primary_service_attr="assignments",
    api_factory=create_assignments_api_routes,
    ui_factory=create_assignments_ui_routes,
    api_related_services={
        "transcript_service": "content_enrichment",
        "report_feedback_service": "report_feedback",
        "user_service": "user_service",
    },
    ui_related_services={
        "transcript_service": "content_enrichment",
        "user_service": "user_service",
    },
)


def create_assignments_routes(app, rt, services, _sync_service=None):
    """Wire assignment API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, ASSIGNMENTS_CONFIG)


__all__ = ["create_assignments_routes"]
