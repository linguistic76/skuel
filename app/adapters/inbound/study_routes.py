"""Study Routes — Student Workspace Hub Orchestrator
=====================================================

Wires the /study workspace routes with all needed submission services.
Sub-pages are top-level routes (/submit, /submissions, etc.) with shared sidebar.

Routes:
- GET /study — Dashboard landing (no sidebar)
- GET /submit — File upload form
- GET /submissions — My submitted work
- GET /exercise-reports — Teacher assessments
- GET /activity-reports — Activity feedback
- GET /generate-reports — Progress report generation
- GET /submissions/{uid} — Submission detail
- HTMX fragments for all above

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from adapters.inbound.study_ui import create_study_ui_routes
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.study")


STUDY_CONFIG = DomainRouteConfig(
    domain_name="study",
    primary_service_attr="submissions",
    api_factory=create_study_ui_routes,
    api_related_services={
        "processing_service": "submissions_processor",
        "user_service": "user_service",
        "exercises_service": "exercises",
        "submissions_search_service": "submissions_search",
        "submissions_core_service": "submissions_core",
        "activity_report_service": "activity_report",
        "teacher_review_service": "teacher_review",
    },
)


def create_study_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Any, _sync_service: Any = None
) -> RouteList:
    """Wire study routes via DomainRouteConfig."""
    return register_domain_routes(app, rt, services, STUDY_CONFIG)
