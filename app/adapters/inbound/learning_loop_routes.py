"""Learning Loop Routes — Orchestrator for GradeBook UI + PathStep Learning Loop Fragments
===========================================================================================

Wires the decomposed submission and report UI routes:
- submissions_ui.py → /submit, /gradebook, /gradebook/{uid}, fragments (GradeBook sidebar)
- exercise_reports_ui.py → /exercise-reports, /reports/list (GradeBook sidebar)
- activity_reports_ui.py → /activity-reports, /submit-activity-report, fragments (GradeBook sidebar)
- revised_exercises_ui.py → /revised-exercises, /revised-exercises/detail (GradeBook sidebar)

Also provides HTMX fragment endpoints for the PathStep detail page:
- /learning-loop/ps/{ps_uid}/exercises → exercises with status pills
- /learning-loop/ps/{ps_uid}/submissions-and-feedback → submissions + feedback (single query)

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from fasthtml.common import H3, Div

from adapters.inbound.activity_reports_ui import create_activity_reports_ui_routes
from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.exercise_reports_ui import create_exercise_reports_ui_routes
from adapters.inbound.fasthtml_types import FastHTMLApp, Request, RouteDecorator
from adapters.inbound.revised_exercises_ui import create_revised_exercises_ui_routes
from adapters.inbound.submissions_ui import create_submissions_ui_routes
from core.utils.logging import get_logger
from ui.learning_loop.exercise_status import render_exercise_list
from ui.learning_loop.feedback_section import render_ps_feedback
from ui.learning_loop.submissions_section import render_ps_submissions
from ui.patterns.error_banner import render_inline_error

logger = get_logger("skuel.routes.learning_loop")


def create_learning_loop_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Any, _sync_service: Any = None
) -> None:
    """Wire learning loop routes via decomposed UI files."""

    # Submissions UI
    create_submissions_ui_routes(
        app,
        rt,
        submissions_service=services.submissions,
        processing_service=getattr(services, "submissions_processor", None),
        exercises_service=getattr(services, "exercises", None),
        submissions_search_service=getattr(services, "submissions_search", None),
        submissions_core_service=getattr(services, "submissions_core", None),
        teacher_review_service=getattr(services, "teacher_review", None),
        user_service=getattr(services, "user_service", None),
    )

    # Exercise Reports UI
    create_exercise_reports_ui_routes(
        app,
        rt,
        submissions_core_service=getattr(services, "submissions_core", None),
    )

    # Activity Reports UI
    create_activity_reports_ui_routes(
        app,
        rt,
        submissions_service=services.submissions,
        activity_report_service=getattr(services, "activity_report", None),
    )

    # Revised Exercises UI
    create_revised_exercises_ui_routes(
        app,
        rt,
        revised_exercise_service=getattr(services, "revised_exercises", None),
    )

    # ========================================================================
    # PATHSTEP LEARNING LOOP FRAGMENTS (HTMX)
    # ========================================================================

    exercises_service = getattr(services, "exercises", None)
    submissions_search_service = getattr(services, "submissions_search", None)

    @rt("/learning-loop/ps/{ps_uid}/exercises")
    async def get_ps_exercises(request: Request, ps_uid: str) -> Any:
        """HTMX fragment: exercises for a PathStep with submission/feedback status."""
        user_uid = require_authenticated_user(request)
        if exercises_service is None:
            return render_inline_error("Exercise service unavailable")
        result = await exercises_service.get_exercises_for_path_step_with_status(ps_uid, user_uid)
        if result.is_error:
            return render_inline_error("Could not load exercises")
        return render_exercise_list(result.value or [], from_ps=ps_uid)

    @rt("/learning-loop/ps/{ps_uid}/submissions-and-feedback")
    async def get_ps_submissions_and_feedback(request: Request, ps_uid: str) -> Any:
        """HTMX fragment: user's submissions + feedback for this PathStep (single query)."""
        user_uid = require_authenticated_user(request)
        if submissions_search_service is None:
            return render_inline_error("Submissions service unavailable")
        result = await submissions_search_service.get_submissions_for_path_step(user_uid, ps_uid)
        if result.is_error:
            return render_inline_error("Could not load submissions")
        rows = result.value or []
        return Div(
            H3("My Submissions", cls="text-base font-semibold mb-2 mt-6"),
            render_ps_submissions(rows),
            H3("Feedback", cls="text-base font-semibold mb-2 mt-6"),
            render_ps_feedback(rows),
        )

    logger.info("Learning loop routes wired (submissions + reports + PS fragments)")
