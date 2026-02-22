"""
Journals Routes — Admin-Only AI Submission
=============================================

Wires Journal UI routes using DomainRouteConfig.
No separate API factory — reuses existing /api/reports/* endpoints.

Admin uploads files → processed by AI using Assignment instructions.
"""

from typing import Any

from adapters.inbound.journals_ui import create_journals_ui_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes


def _noop_api_factory(_app: Any, _rt: Any, _primary: Any, **_kw: Any) -> list[Any]:
    """No-op API factory — journals reuse /api/reports/* endpoints."""
    return []


JOURNALS_CONFIG = DomainRouteConfig(
    domain_name="journals",
    primary_service_attr="reports",
    api_factory=_noop_api_factory,
    ui_factory=create_journals_ui_routes,
    ui_related_services={
        "processing_service": "report_processor",
        "report_projects_service": "assignments",
        "user_service": "user_service",
        "journal_generator": "journal_generator",
    },
)


def create_journals_routes(app, rt, services, _sync_service=None):
    """Wire journal UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, JOURNALS_CONFIG)


__all__ = ["create_journals_routes"]
