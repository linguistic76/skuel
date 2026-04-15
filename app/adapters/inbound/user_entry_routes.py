"""
UserEntry Routes (ADR-054 Commit 5b)
=====================================

Wires the ``user_entry`` domain's API + UI surface via ``DomainRouteConfig``,
then re-registers the cross-cutting extension factories and the three sibling
sub-UIs (exercise_reports, activity_reports, revised_exercises) that used to
live under ``submissions_routes``. Commit 5b turns this file into the single
entry point for the unified submission/journal experience.

See: /home/mike/.claude/plans/starry-waddling-coral.md
     /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from adapters.inbound.auth import make_service_getter
from adapters.inbound.exercise_report_api import create_exercise_report_api_routes
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.progress_report_api import create_progress_report_api_routes
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from adapters.inbound.submissions_sharing_api import create_submissions_sharing_api_routes
from adapters.inbound.user_entry_api import create_user_entry_api_routes
from adapters.inbound.user_entry_ui import create_user_entry_ui_routes
from core.utils.logging import get_logger

logger = get_logger("skuel.routes.user_entry")

USER_ENTRY_CONFIG = DomainRouteConfig(
    domain_name="user_entry",
    primary_service_attr="user_entry",
    api_factory=create_user_entry_api_routes,
    api_related_services={
        "processing_service": "user_entry_processor",
    },
    ui_factory=create_user_entry_ui_routes,
    ui_related_services={
        "orchestrator": "user_entry_orchestrator",
        "exercise_report_service": "exercise_report",
    },
)


def create_user_entry_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Any, _sync_service: Any = None
) -> None:
    """Register UserEntry API + UI routes, plus cross-cutting extensions."""
    register_domain_routes(app, rt, services, USER_ENTRY_CONFIG)

    # -------------------------------------------------------------------------
    # Extension: sharing routes (UnifiedSharingService + SubmissionsService)
    # -------------------------------------------------------------------------
    if (
        services
        and getattr(services, "sharing", None)
        and getattr(services, "submissions_core", None)
    ):
        create_submissions_sharing_api_routes(
            app,
            rt,
            services.sharing,
            services.submissions_core,
        )
        logger.info("UserEntry: submission sharing routes registered (Portfolio feature)")

    # -------------------------------------------------------------------------
    # Extension: progress report generation routes
    # -------------------------------------------------------------------------
    progress_report_generator = getattr(services, "progress_report_generator", None)
    if progress_report_generator and getattr(services, "submissions", None):
        schedule_service = getattr(services, "progress_schedule", None)
        activity_report_svc = getattr(services, "activity_report", None)
        review_queue_svc = getattr(services, "review_queue", None)
        create_progress_report_api_routes(
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
        logger.info("UserEntry: progress + activity report routes registered")

    # -------------------------------------------------------------------------
    # Extension: activity review UI (admin-only)
    # -------------------------------------------------------------------------
    activity_review_orch = getattr(services, "activity_review_orchestrator", None)
    if activity_review_orch:
        from adapters.inbound.activity_review_ui import create_activity_review_ui_routes

        create_activity_review_ui_routes(app, rt, activity_review_orch)
        logger.info("UserEntry: activity review UI routes registered")

    # -------------------------------------------------------------------------
    # Extension: exercise-report assessment routes (teacher-only)
    # -------------------------------------------------------------------------
    if services and getattr(services, "submissions_core", None):
        get_user_service = make_service_getter(services.user)
        create_exercise_report_api_routes(
            app,
            rt,
            services.submissions_core,
            user_service_getter=get_user_service,
        )
        logger.info("UserEntry: exercise report assessment routes registered")

    # -------------------------------------------------------------------------
    # Extension: batch transcription/processing API (admin-only)
    # -------------------------------------------------------------------------
    batch_transcription_svc = getattr(services, "batch_transcription", None)
    if batch_transcription_svc:
        from adapters.inbound.batch_transcription_api import (
            create_batch_transcription_api_routes,
        )

        create_batch_transcription_api_routes(
            app,
            rt,
            batch_transcription_service=batch_transcription_svc,
            batch_processing_service=getattr(services, "batch_processing", None),
            user_service=getattr(services, "user_service", None),
        )
        logger.info("UserEntry: batch transcription API routes registered (admin-only)")

    # -------------------------------------------------------------------------
    # Sibling UI sub-factories: report-facing pages live in GradeBook sidebar
    # -------------------------------------------------------------------------
    user_entry_orch = getattr(services, "user_entry_orchestrator", None)
    if user_entry_orch:
        from adapters.inbound.activity_reports_ui import create_activity_reports_ui_routes
        from adapters.inbound.exercise_reports_ui import create_exercise_reports_ui_routes
        from adapters.inbound.revised_exercises_ui import create_revised_exercises_ui_routes

        create_exercise_reports_ui_routes(app, rt, orchestrator=user_entry_orch)
        create_activity_reports_ui_routes(app, rt, orchestrator=user_entry_orch)
        create_revised_exercises_ui_routes(app, rt, orchestrator=user_entry_orch)
        logger.info("UserEntry: exercise/activity/revised-exercise UI sub-factories registered")


__all__ = ["USER_ENTRY_CONFIG", "create_user_entry_routes"]
