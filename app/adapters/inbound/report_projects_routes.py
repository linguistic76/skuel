"""
Report Projects Routes - Configuration-Driven Registration
============================================================

Wires Report Project API and UI routes using DomainRouteConfig.
Report Projects provide reusable LLM instruction templates for any report type.
"""

from adapters.inbound.report_projects_api import create_report_projects_api_routes
from adapters.inbound.report_projects_ui import create_report_projects_ui_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

REPORT_PROJECTS_CONFIG = DomainRouteConfig(
    domain_name="report-projects",
    primary_service_attr="report_projects",
    api_factory=create_report_projects_api_routes,
    ui_factory=create_report_projects_ui_routes,
    api_related_services={
        "transcript_service": "transcript_processor",
        "report_feedback_service": "report_feedback",
    },
    ui_related_services={
        "transcript_service": "transcript_processor",
    },
)


def create_report_projects_routes(app, rt, services, _sync_service=None):
    """Wire report projects API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, REPORT_PROJECTS_CONFIG)


__all__ = ["create_report_projects_routes"]
