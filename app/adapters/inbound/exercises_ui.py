"""
Exercises UI Routes - Transparent Feedback System
===================================================

UI for exercises (instruction templates) following SKUEL's transparency principles:
- Visible, editable instructions
- User-controlled model selection
- Side-by-side entry + feedback view
- No black boxes

Uses SKUEL Tailwind components for clean, consistent design.

Formerly assignments_ui.py — renamed per of Ku hierarchy refactoring.
"""

from typing import Any

from fasthtml.common import Div, P

from adapters.inbound.auth import make_service_getter, require_authenticated_user, require_teacher
from adapters.inbound.boundary import ui_boundary_handler
from core.utils.logging import get_logger
from ui.components import ButtonT
from ui.exercises.cards import render_exercises_list
from ui.exercises.detail import render_exercise_student_detail, render_exercise_view
from ui.exercises.editor import render_exercise_editor
from ui.layouts.base_page import BasePage
from ui.patterns.error_banner import render_error_banner, render_inline_error
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.page_header import PageHeader
from ui.primitives import ButtonLink
from ui.tokens import Container, Spacing

logger = get_logger("skuel.routes.exercises.ui")


# ============================================================================
# ROUTE HANDLERS
# ============================================================================


def create_exercises_ui_routes(
    app,
    rt,
    exercises_service,
    transcript_service=None,
    user_service=None,
    **related_services: Any,
) -> list[Any]:
    """
    Create exercises UI routes.

    Dashboard is open to all authenticated users (exercises are shared curriculum).
    Create/edit/delete routes are TEACHER+ gated.
    """

    get_user_service = make_service_getter(user_service)

    @app.get("/exercises")
    @ui_boundary_handler("Error loading exercises")
    def exercises_dashboard(request) -> Any:
        """Exercises dashboard — shell renders immediately, content loads via HTMX."""
        require_authenticated_user(request)

        content = Div(
            PageHeader(
                "Exercises",
                subtitle="Practice with exercises linked to path steps and knowledge units",
            ),
            content_loading_placeholder("/exercises/content", "exercises-content"),
            id="main-content",
        )
        return BasePage(
            content=content,
            title="Exercises",
            request=request,
            active_page="curriculum",
        )

    @app.get("/exercises/content")
    @ui_boundary_handler("Error loading exercises", fragment_id="exercises-content")
    async def exercises_content_fragment(request) -> Any:
        """HTMX fragment: exercises list."""
        user_uid = require_authenticated_user(request)
        result = await exercises_service.list_user_exercises(user_uid)
        exercises = [] if result.is_error else result.value
        return Div(render_exercises_list(exercises), id="exercises-content")

    @app.get("/exercises/new")
    @require_teacher(get_user_service)
    def new_exercise_form(request, current_user=None) -> Any:
        """New exercise form — ownership comes from the session at POST time."""
        return render_exercise_editor(mode="create")

    @app.get("/exercises/{uid}/edit")
    @require_teacher(get_user_service)
    @ui_boundary_handler("Error loading exercise")
    async def edit_exercise_form(_request, uid: str, current_user=None) -> Any:
        """Edit exercise form."""
        result = await exercises_service.get_exercise(uid)

        if result.is_error or not result.value:
            return render_inline_error("Exercise not found")

        exercise = result.value

        return render_exercise_editor(exercise=exercise, mode="edit")

    @app.get("/exercises/{uid}/view")
    @require_teacher(get_user_service)
    @ui_boundary_handler("Error viewing exercise")
    async def view_exercise(_request, uid: str, current_user=None) -> Any:
        """View exercise with transparency and required Ku foundation."""
        result = await exercises_service.get_exercise(uid)

        if result.is_error or not result.value:
            return render_inline_error("Exercise not found")

        exercise = result.value

        knowledge_result = await exercises_service.get_required_knowledge(uid)
        required_knowledge = knowledge_result.value if knowledge_result.is_ok else []

        return render_exercise_view(exercise, required_knowledge=required_knowledge)

    @app.get("/exercises/get")
    @ui_boundary_handler("Error loading exercise")
    def exercise_detail(request, uid: str, from_ps: str = "") -> Any:
        """Student-facing exercise detail page — shell renders immediately, content loads via HTMX."""
        require_authenticated_user(request)

        if not uid:
            return BasePage(
                Div(
                    PageHeader("Exercise Not Found"),
                    P("Missing exercise UID.", cls="text-base-content/70"),
                    ButtonLink(
                        "← Back to Curriculum",
                        href="/profile?tab=curriculum",
                        cls=ButtonT.ghost,
                    ),
                    cls=f"{Container.STANDARD} {Spacing.PAGE}",
                ),
                title="Exercise Not Found",
                request=request,
                active_page="library",
            )

        fragment_url = f"/exercises/get/content?uid={uid}"
        if from_ps:
            fragment_url += f"&from_ps={from_ps}"

        content = content_loading_placeholder(fragment_url, "exercise-detail-content")
        return BasePage(
            content,
            title="Exercise",
            request=request,
            active_page="library",
        )

    @app.get("/exercises/get/content")
    @ui_boundary_handler("Error loading exercise", fragment_id="exercise-detail-content")
    async def exercise_detail_content_fragment(request, uid: str, from_ps: str = "") -> Any:
        """HTMX fragment: exercise detail content."""
        require_authenticated_user(request)
        result = await exercises_service.get_exercise(uid)
        if result.is_error or not result.value:
            return Div(
                render_error_banner("Exercise not found"),
                ButtonLink(
                    "← Back to Curriculum", href="/profile?tab=curriculum", cls=ButtonT.ghost
                ),
                id="exercise-detail-content",
            )
        exercise = result.value
        return render_exercise_student_detail(exercise, from_ps=from_ps)

    logger.info("Exercises UI routes registered")

    return []


__all__ = ["create_exercises_ui_routes"]
