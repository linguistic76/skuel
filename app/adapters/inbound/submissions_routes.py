"""Submissions Routes — API + UI Orchestrator
=============================================

Wires Submissions API routes (DomainRouteConfig) and all submission-adjacent
UI routes (/submit, /gradebook, /exercise-reports, /activity-reports, /revised-exercises).

Standard factories (via DomainRouteConfig):
- create_submissions_api_routes: Upload, list, process, download, content management

Extension factories (manual):
- create_submissions_sharing_api_routes: Share, unshare, visibility, portfolio

UI sub-factories (registered directly):
- create_submissions_ui_routes → /submit, /submissions/history, /gradebook
- create_exercise_reports_ui_routes → /exercise-reports
- create_activity_reports_ui_routes → /activity-reports
- create_revised_exercises_ui_routes → /revised-exercises

Journals have their own standalone route config — see journals_routes.py.

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from adapters.inbound.auth import make_service_getter
from adapters.inbound.exercise_report_api import create_exercise_report_api_routes
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.progress_report_api import create_progress_report_api_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from adapters.inbound.submissions_api import create_submissions_api_routes
from adapters.inbound.submissions_sharing_api import create_submissions_sharing_api_routes
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.submissions")

SUBMISSIONS_CONFIG = DomainRouteConfig(
    domain_name="submissions",
    primary_service_attr="submissions",
    api_factory=create_submissions_api_routes,
    api_related_services={
        "processing_service": "submissions_processor",
        "submissions_search_service": "submissions_search",
        "submissions_core_service": "submissions_core",
        "teacher_review_service": "teacher_review",
        "user_service": "user_service",
    },
)


def create_submissions_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Any, _sync_service=None
) -> None:
    """
    Wire submissions API and sharing routes using configuration-driven registration.
    UI routes are top-level (/submit, /gradebook, etc.) — old paths redirect 301.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        services: Service container
        _sync_service: Unused, signature compatibility
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
    activity_review_orch = getattr(services, "activity_review_orchestrator", None)
    if activity_review_orch:
        from adapters.inbound.activity_review_ui import create_activity_review_ui_routes

        ar_routes = create_activity_review_ui_routes(app, rt, activity_review_orch)
        routes.extend(ar_routes or [])
        logger.info("Activity review UI routes registered")

    # Extension: assessment routes (require TEACHER role)
    if services and services.submissions_core:
        get_user_service = make_service_getter(services.user_service)

        assessment_routes = create_exercise_report_api_routes(
            app,
            rt,
            services.submissions_core,
            user_service_getter=get_user_service,
        )
        routes.extend(assessment_routes or [])
        logger.info("Exercise report assessment routes registered")

    # Extension: batch transcription/processing API routes (admin-only)
    batch_transcription_svc = getattr(services, "batch_transcription", None)
    if batch_transcription_svc:
        from adapters.inbound.batch_transcription_api import (
            create_batch_transcription_api_routes,
        )

        batch_routes = create_batch_transcription_api_routes(
            app,
            rt,
            batch_transcription_service=batch_transcription_svc,
            batch_processing_service=getattr(services, "batch_processing", None),
            user_service=getattr(services, "user_service", None),
        )
        routes.extend(batch_routes or [])
        logger.info("Batch transcription API routes registered (admin-only)")


def create_submissions_ui_orchestrator(app: FastHTMLApp, rt: RouteDecorator, services: Any) -> None:
    """Wire all submission-adjacent UI routes."""
    from adapters.inbound.activity_reports_ui import create_activity_reports_ui_routes
    from adapters.inbound.exercise_reports_ui import create_exercise_reports_ui_routes
    from adapters.inbound.revised_exercises_ui import create_revised_exercises_ui_routes
    from adapters.inbound.submissions_ui import create_submissions_ui_routes

    create_submissions_ui_routes(
        app,
        rt,
        orchestrator=services.submissions_orchestrator,
    )
    create_exercise_reports_ui_routes(
        app,
        rt,
        orchestrator=services.submissions_orchestrator,
    )
    create_activity_reports_ui_routes(
        app,
        rt,
        orchestrator=services.submissions_orchestrator,
    )
    create_revised_exercises_ui_routes(
        app,
        rt,
        orchestrator=services.submissions_orchestrator,
    )
    logger.info(
        "Submission UI routes registered (submissions + exercise/activity reports + revisions)"
    )


__all__ = ["create_submissions_routes", "create_submissions_ui_orchestrator"]
