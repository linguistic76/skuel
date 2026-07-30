"""
Teaching Routes — Orchestrator-Driven Registration
=====================================================

Wires Teaching review API + UI routes:

- API routes       → DomainRouteConfig (mutations need TeacherReviewService directly)
- UI routes        → TeacherOrchestrator (read-model facade, like Library hub)
- Forms UI routes  → Direct wiring (form services)

See: /docs/decisions/ADR-040-teacher-exercise-workflow.md
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from adapters.inbound.teaching_api import create_teaching_api_routes
from adapters.inbound.teaching_forms_ui import create_teaching_forms_ui_routes
from adapters.inbound.teaching_ui import create_teaching_ui_routes
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from services_bootstrap import Services

logger = get_logger("skuel.routes.teaching")

# API routes still use DomainRouteConfig — mutations need TeacherReviewService directly.
TEACHING_API_CONFIG = DomainRouteConfig(
    domain_name="teaching",
    primary_service_attr="teacher_review",
    api_factory=create_teaching_api_routes,
    ui_factory=None,  # UI wired separately via orchestrator
    api_related_services={
        "user_service": "user",
        "exercises_service": "exercises",
        "user_entry_service": "user_entry",
        "revised_exercise_service": "revised_exercises",
        "entry_report_service": "entry_report",
    },
)


def create_teaching_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> None:
    """Wire teaching API + UI routes.

    API: DomainRouteConfig (mutations need TeacherReviewService directly)
    UI:  TeacherOrchestrator (read-model facade)
    """
    # 1. API routes via DomainRouteConfig
    register_domain_routes(app, rt, services, TEACHING_API_CONFIG)

    if services:
        # Teaching UI requires the orchestrator — it is always constructed
        # alongside services (compose.py). Fail loudly if it is missing rather
        # than passing None into routes that would crash on first request.
        orchestrator = services.teacher_orchestrator
        if orchestrator is None:
            raise RuntimeError(
                "TeacherOrchestrator missing from Services — required to wire teaching UI routes"
            )

        # Forms submission detail gates on teacher-over-student authority, so the
        # review service is a hard requirement, not an enhancement.
        teacher_review = services.teacher_review
        if teacher_review is None:
            raise RuntimeError(
                "TeacherReviewService missing from Services — required to verify "
                "teacher authority on forms submission detail"
            )

        # 2. UI routes via TeacherOrchestrator
        create_teaching_ui_routes(
            _app=app,
            rt=rt,
            orchestrator=orchestrator,
            user_service=services.user,
            entry_report_service=services.entry_report,
        )

        # 3. Forms UI routes (separate concern)
        create_teaching_forms_ui_routes(
            _app=app,
            rt=rt,
            form_template_service=services.form_templates,
            form_submission_service=services.form_submissions,
            user_service=services.user,
            # Submission detail verifies teacher authority over the submitting
            # student, not just the TEACHER role — see ADR-040.
            teacher_review_service=teacher_review,
        )


__all__ = ["create_teaching_routes"]
