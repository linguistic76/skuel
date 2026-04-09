"""
Learning Loop Routes — PathStep Engagement Fragments
======================================================

HTMX fragment endpoints for the learning loop: exercises with
submission/feedback status, user submissions, and teacher feedback.

These fragments are loaded by the PathStep detail page
(/explore/ps/{uid}) for authenticated users.

Routes:
- GET  /learning-loop/ps/{ps_uid}/exercises                — Exercise list with status
- GET  /learning-loop/ps/{ps_uid}/submissions-and-feedback — Submissions + feedback
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from ui.learning_loop.exercise_status import render_exercise_list
from ui.learning_loop.submissions_section import render_ps_submissions_and_feedback
from ui.patterns.error_banner import render_inline_error

if TYPE_CHECKING:
    from core.orchestrator.explore_orchestrator import ExploreOrchestrator


def create_learning_loop_routes(
    _app: FastHTMLApp,
    rt: RouteDecorator,
    orchestrator: "ExploreOrchestrator",
) -> None:
    """Register /learning-loop/* HTMX fragment routes.

    Args:
        _app: FastHTML application instance.
        rt: Route decorator.
        orchestrator: ExploreOrchestrator for cross-service reads.
    """

    @rt("/learning-loop/ps/{ps_uid}/exercises")
    async def get_ps_exercises(request: Request, ps_uid: str) -> Any:
        """HTMX fragment: exercises for a PathStep with submission/feedback status."""
        user_uid = require_authenticated_user(request)
        result = await orchestrator.get_exercises_for_path_step_with_status(ps_uid, user_uid)
        if result.is_error:
            return render_inline_error("Could not load exercises")
        return render_exercise_list(result.value or [], from_ps=ps_uid)

    @rt("/learning-loop/ps/{ps_uid}/submissions-and-feedback")
    async def get_ps_submissions_and_feedback(request: Request, ps_uid: str) -> Any:
        """HTMX fragment: user's submissions + feedback for this PathStep."""
        user_uid = require_authenticated_user(request)
        result = await orchestrator.get_submissions_for_path_step(user_uid, ps_uid)
        if result.is_error:
            return render_inline_error("Could not load submissions")
        return render_ps_submissions_and_feedback(result.value or [])


__all__ = ["create_learning_loop_routes"]
