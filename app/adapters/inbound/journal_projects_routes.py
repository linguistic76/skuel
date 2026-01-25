"""
Journal Projects Routes - Clean Architecture Factory
====================================================

Minimal factory that wires API and UI routes using DomainRouteConfig.
"""

from adapters.inbound.journal_projects_api import create_journal_projects_api_routes
from adapters.inbound.journal_projects_ui import create_journal_projects_ui_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

JOURNAL_PROJECTS_CONFIG = DomainRouteConfig(
    domain_name="journal-projects",
    primary_service_attr="journal_projects",
    api_factory=create_journal_projects_api_routes,
    ui_factory=create_journal_projects_ui_routes,
    api_related_services={
        # Format: {kwarg_name: container_attr}
        "journals_service": "journals",  # For entry lookup in feedback route
        "journal_feedback_service": "journal_feedback",  # For AI feedback generation
    },
)


def create_journal_projects_routes(app, rt, services, _sync_service=None):
    """Wire journal projects API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, JOURNAL_PROJECTS_CONFIG)


__all__ = ["create_journal_projects_routes"]
