"""
Report Projects Routes - Clean Architecture Factory
====================================================

Wires Report Project API and UI routes using DomainRouteConfig.

Migrated from journal_projects_routes.py (February 2026 — Journal merged into Reports).
Report Projects provide reusable LLM instruction templates for any report type.
"""

from adapters.inbound.journal_projects_api import create_journal_projects_api_routes
from adapters.inbound.journal_projects_ui import create_journal_projects_ui_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

REPORT_PROJECTS_CONFIG = DomainRouteConfig(
    domain_name="journal-projects",  # Keep URL path for now (UI links)
    primary_service_attr="report_projects",
    api_factory=create_journal_projects_api_routes,
    ui_factory=create_journal_projects_ui_routes,
    api_related_services={
        "journals_service": "transcript_processor",  # For entry lookup in feedback route
        "journal_feedback_service": "report_feedback",  # For AI feedback generation
    },
    ui_related_services={
        "journals_service": "transcript_processor",  # For entry lookup in view_entry_with_feedback
    },
)


def create_report_projects_routes(app, rt, services, _sync_service=None):
    """Wire report projects API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, REPORT_PROJECTS_CONFIG)


__all__ = ["create_report_projects_routes"]
