"""
Exercises UI Routes — the learner's exercise page
==================================================

An exercise is authored only in the content vault (ADR-091 S4), so the UI has
no authoring surface: ``/exercises/get`` is the one page, open to any signed-in
learner in the exercise's audience, with its instructions shown in full
(no black box) and the doors to download the worksheet and turn in work.
"""

from typing import Any

from fasthtml.common import FT, Div, P

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import ui_boundary_handler
from adapters.inbound.route_factories import refuse, refuse_not_found
from core.utils.logging import get_logger
from ui.components import ButtonT
from ui.exercises.detail import render_exercise_student_detail
from ui.layouts.base_page import BasePage
from ui.patterns.error_banner import render_error_banner
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.page_header import PageHeader
from ui.primitives import ButtonLink
from ui.tokens import Container, Spacing

logger = get_logger("skuel.routes.exercises.ui")


# ============================================================================
# ROUTE HANDLERS
# ============================================================================


def create_exercises_ui_routes(app, rt, exercises_service) -> None:
    """Create the learner's exercise page and its content fragment."""

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
                        "← Back to Library",
                        href="/library",
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
        """HTMX fragment: exercise detail content.

        This fragment is where the read actually happens — the /exercises/get
        shell only echoes the uid into this URL — so the domain's declared
        audience is applied here; a uid naming no exercise renders the
        not-found banner with a 404.
        """
        user_uid = require_authenticated_user(request)

        def render_refusal(message: str) -> FT:
            return Div(
                render_error_banner(message),
                ButtonLink("← Back to Library", href="/library", cls=ButtonT.ghost),
                id="exercise-detail-content",
            )

        result = await exercises_service.get_exercise_for_user(uid, user_uid)
        if result.is_error:
            return refuse(result.expect_error(), render_refusal, "Exercise")
        if not result.value:
            # The audience check answers None, not an error: the not-found decision.
            return refuse_not_found(render_refusal("Exercise not found"))
        exercise = result.value
        return render_exercise_student_detail(exercise, from_ps=from_ps)

    logger.info("Exercises UI routes registered")


__all__ = ["create_exercises_ui_routes"]
