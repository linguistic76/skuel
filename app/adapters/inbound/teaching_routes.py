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
        "submissions_service": "submissions",
        "revised_exercise_service": "revised_exercises",
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
        # 2. UI routes via TeacherOrchestrator
        create_teaching_ui_routes(
            _app=app,
            rt=rt,
            orchestrator=services.teacher_orchestrator,
            user_service=services.user,
        )

        # 3. Forms UI routes (separate concern)
        create_teaching_forms_ui_routes(
            _app=app,
            rt=rt,
            form_template_service=services.form_templates,
            form_submission_service=services.form_submissions,
            user_service=services.user,
        )


__all__ = ["create_teaching_routes"]
