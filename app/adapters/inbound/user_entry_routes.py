"""
UserEntry Routes (ADR-054)
==========================

Wires the ``user_entry`` domain's API + UI surface via ``DomainRouteConfig``,
then re-registers the cross-cutting extension factories and the three sibling
sub-UIs (entry_reports, activity_reports, revised_exercises) that used to
live under the legacy ``submissions_routes``. This is the single entry point
for the unified submission/journal experience.

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
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
        "grounding_service": "entry_grounding",
    },
    ui_factory=create_user_entry_ui_routes,
    ui_related_services={
        "orchestrator": "user_entry_orchestrator",
        "entry_report_service": "entry_report",
        "groups_service": "groups",
        "batch_transcription_service": "batch_transcription",
        "processing_service": "user_entry_processor",
        "user_service": "user",
        "intelligence_tier": "intelligence_tier",
    },
)


def create_user_entry_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Any, _sync_service: Any = None
) -> None:
    """Register UserEntry API + UI routes, plus cross-cutting extensions."""
    register_domain_routes(app, rt, services, USER_ENTRY_CONFIG)

    # -------------------------------------------------------------------------
    # Extension: activity review UI (admin-only)
    # -------------------------------------------------------------------------
    activity_review_orch = getattr(services, "activity_review_orchestrator", None)
    if activity_review_orch:
        from adapters.inbound.activity_review_ui import create_activity_review_ui_routes

        create_activity_review_ui_routes(app, rt, activity_review_orch)
        logger.info("UserEntry: activity review UI routes registered")

    # -------------------------------------------------------------------------
    # Extension: batch transcription API (admin-only, Tier 1 only)
    # -------------------------------------------------------------------------
    batch_transcription_svc = getattr(services, "batch_transcription", None)
    if batch_transcription_svc:
        from adapters.inbound.batch_transcription_api import (
            create_batch_transcription_api_routes,
        )

        assert services.journal_batch is not None, (
            "JournalBatchService must be wired before batch transcription routes"
        )
        create_batch_transcription_api_routes(
            app,
            rt,
            batch_transcription_service=batch_transcription_svc,
            journal_batch=services.journal_batch,
            user_service=getattr(services, "user", None),
        )
        logger.info("UserEntry: batch transcription API routes registered (admin-only)")

    # -------------------------------------------------------------------------
    # Sibling UI sub-factories: report-facing pages live in GradeBook sidebar
    # -------------------------------------------------------------------------
    user_entry_orch = getattr(services, "user_entry_orchestrator", None)
    if user_entry_orch:
        from adapters.inbound.activity_reports_ui import create_activity_reports_ui_routes
        from adapters.inbound.entry_reports_ui import create_entry_reports_ui_routes
        from adapters.inbound.revised_exercises_ui import create_revised_exercises_ui_routes

        create_entry_reports_ui_routes(app, rt, orchestrator=user_entry_orch)
        create_activity_reports_ui_routes(app, rt, orchestrator=user_entry_orch)
        create_revised_exercises_ui_routes(app, rt, orchestrator=user_entry_orch)
        logger.info("UserEntry: exercise/activity/revised-exercise UI sub-factories registered")


__all__ = ["USER_ENTRY_CONFIG", "create_user_entry_routes"]
