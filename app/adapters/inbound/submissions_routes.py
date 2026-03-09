"""Submissions Routes - File Submission and Processing Pipeline
================================================================

Wires Submissions API, UI, Sharing, and Journals routes using DomainRouteConfig
(Multi-Factory variant).

Standard factories (via DomainRouteConfig):
- create_submissions_api_routes: Upload, list, process, download, content management
- create_submissions_ui_routes: Dashboard, detail view, HTMX fragments

Extension factories (manual):
- create_submissions_sharing_api_routes: Share, unshare, visibility, portfolio
- journals UI: /journals/* user journaling interface (EntityType.JOURNAL is a Submission subtype)

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
from adapters.inbound.submission_report_api import create_submission_report_api_routes
from adapters.inbound.journals_ui import create_journals_ui_routes
from adapters.inbound.progress_report_api import create_progress_report_api_routes
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
        "_exercises_service": "assignments",
        "_submissions_search_service": "submissions_search",
        "_submissions_core_service": "submissions_core",
        "_activity_report_service": "activity_report",
        "_teacher_review_service": "teacher_review",
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
        "submissions_core_service": "submissions_core",
    },
)


def create_submissions_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Any, _sync_service=None
) -> RouteList:
    """
    Wire submissions API, UI, and sharing routes using configuration-driven registration.

    Uses DomainRouteConfig for standard API + UI routes (shared primary service).
    Sharing routes appended manually: their primary service (sharing)
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

    # Extension: sharing routes use UnifiedSharingService
    if services and services.sharing:
        sharing_routes = create_submissions_sharing_api_routes(
            app,
            rt,
            services.sharing,
            services.submissions_core,
        )
        routes.extend(sharing_routes or [])
        logger.info("Submission sharing routes registered (Portfolio feature)")

    # Extension: progress report generation routes
    progress_report_generator = getattr(services, "progress_report_generator", None)
    if progress_report_generator and services.submissions:
        schedule_service = getattr(services, "progress_schedule", None)
        activity_report_svc = getattr(services, "activity_report", None)
        review_queue_svc = getattr(services, "review_queue", None)
        progress_routes = create_progress_report_api_routes(
            app,
            rt,
            progress_report_generator,
            services.submissions,
            schedule_service=schedule_service,
            activity_report=activity_report_svc,
            review_queue=review_queue_svc,
            user_service=getattr(services, "user_service", None),
            context_builder=getattr(activity_report_svc, "context_builder", None),
        )
        routes.extend(progress_routes or [])
        logger.info("Progress report + activity report routes registered")

    # Extension: activity review UI routes (admin-only)
    activity_report_svc = getattr(services, "activity_report", None)
    if activity_report_svc:
        from adapters.inbound.activity_review_ui import create_activity_review_ui_routes

        ar_routes = create_activity_review_ui_routes(
            app,
            rt,
            activity_report_svc,
            review_queue=getattr(services, "review_queue", None),
            user_service=getattr(services, "user_service", None),
            context_builder=getattr(activity_report_svc, "context_builder", None),
        )
        routes.extend(ar_routes or [])
        logger.info("Activity review UI routes registered")

    # Extension: assessment routes (require TEACHER role)
    if services and services.submissions_core:

        def get_user_service():
            return services.user_service

        assessment_routes = create_submission_report_api_routes(
            app,
            rt,
            services.submissions_core,
            user_service_getter=get_user_service,
        )
        routes.extend(assessment_routes or [])
        logger.info("Submission report assessment routes registered")

    # Extension: journals UI routes (EntityType.JOURNAL is a Submission subtype)
    if getattr(services, "submissions_processor", None):
        journal_routes = register_domain_routes(app, rt, services, JOURNALS_CONFIG)
        routes.extend(journal_routes or [])
        logger.info("Journals UI routes registered (user journaling)")

    return routes


__all__ = ["create_submissions_routes"]
