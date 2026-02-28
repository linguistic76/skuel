"""Submissions Routes - File Submission and Processing Pipeline
================================================================

Wires Submissions API, UI, Sharing, and Journals routes using DomainRouteConfig
(Multi-Factory variant).

Standard factories (via DomainRouteConfig):
- create_submissions_api_routes: Upload, list, process, download, content management
- create_submissions_ui_routes: Dashboard, detail view, HTMX fragments

Extension factories (manual):
- create_submissions_sharing_api_routes: Share, unshare, visibility, portfolio
- journals UI: /journals/* admin upload interface (EntityType.JOURNAL is a Submission subtype)

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from adapters.inbound.feedback_assessment_api import create_feedback_assessment_api_routes
from adapters.inbound.journals_ui import create_journals_ui_routes
from adapters.inbound.progress_feedback_api import create_progress_feedback_api_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from adapters.inbound.submissions_api import create_submissions_api_routes
from adapters.inbound.submissions_sharing_api import create_submissions_sharing_api_routes
from adapters.inbound.submissions_ui import create_submissions_ui_routes
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.submissions")

SUBMISSIONS_CONFIG = DomainRouteConfig(
    domain_name="submissions",
    primary_service_attr="submissions",
    api_factory=create_submissions_api_routes,
    ui_factory=create_submissions_ui_routes,
    api_related_services={
        "processing_service": "submissions_processor",
        "submissions_search_service": "submissions_search",
        "submissions_core_service": "submissions_core",
        "teacher_review_service": "teacher_review",
    },
    ui_related_services={
        "_processing_service": "submissions_processor",
        "_report_projects_service": "assignments",
        "_submissions_search_service": "submissions_search",
        "_submissions_core_service": "submissions_core",
    },
)


def _journals_noop_api_factory(_app: Any, _rt: Any, _primary: Any, **_kw: Any) -> list[Any]:
    """No-op — journals reuse /api/submissions/* endpoints."""
    return []


JOURNALS_CONFIG = DomainRouteConfig(
    domain_name="journals",
    primary_service_attr="submissions",
    api_factory=_journals_noop_api_factory,
    ui_factory=create_journals_ui_routes,
    ui_related_services={
        "processing_service": "submissions_processor",
        "report_projects_service": "exercises",
        "user_service": "user_service",
        "journal_generator": "journal_generator",
    },
)


def create_submissions_routes(app: Any, rt: Any, services: Any, _sync_service=None) -> list[Any]:
    """
    Wire submissions API, UI, and sharing routes using configuration-driven registration.

    Uses DomainRouteConfig for standard API + UI routes (shared primary service).
    Sharing routes appended manually: their primary service (submissions_sharing)
    differs from the API/UI primary (submissions).

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Service container
        _sync_service: Unused, signature compatibility

    Returns:
        List of all registered route functions
    """
    routes = register_domain_routes(app, rt, services, SUBMISSIONS_CONFIG)

    # Extension: sharing routes use a different primary service
    if services and services.submissions_sharing:
        sharing_routes = create_submissions_sharing_api_routes(
            app,
            rt,
            services.submissions_sharing,
            services.submissions_core,
        )
        routes.extend(sharing_routes or [])
        logger.info("Submission sharing routes registered (Portfolio feature)")

    # Extension: progress feedback generation routes
    progress_feedback_generator = getattr(services, "progress_feedback_generator", None)
    if progress_feedback_generator and services.submissions:
        schedule_service = getattr(services, "progress_schedule", None)
        progress_routes = create_progress_feedback_api_routes(
            app,
            rt,
            progress_feedback_generator,
            services.submissions,
            schedule_service=schedule_service,
        )
        routes.extend(progress_routes or [])
        logger.info("Progress feedback routes registered")

    # Extension: assessment routes (require TEACHER role)
    if services and services.submissions_core:

        def get_user_service():
            return services.user_service

        assessment_routes = create_feedback_assessment_api_routes(
            app,
            rt,
            services.submissions_core,
            user_service_getter=get_user_service,
        )
        routes.extend(assessment_routes or [])
        logger.info("Feedback assessment routes registered")

    # Extension: journals UI routes (EntityType.JOURNAL is a Submission subtype)
    exercises_service = getattr(services, "exercises", None)
    if exercises_service and getattr(services, "submissions_processor", None):
        journal_routes = register_domain_routes(app, rt, services, JOURNALS_CONFIG)
        routes.extend(journal_routes or [])
        logger.info("Journals UI routes registered (Admin-only AI submission)")

    return routes


__all__ = ["create_submissions_routes"]
