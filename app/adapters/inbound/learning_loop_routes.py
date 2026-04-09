"""
Learning Loop Routes — Engagement Pages + Fragments
=====================================================

Detail pages for Ku and PathStep entities (where users engage with
content, track learning state, and interact with exercises) plus
HTMX fragment endpoints for the learning loop.

The PathStep detail page (/explore/ps/{uid}) is the learning loop
anchor — authenticated users see exercises with status, submissions,
and teacher feedback loaded via HTMX fragments.

Routes:
- GET  /explore/ku/{uid}          — Ku detail page with sidebar
- GET  /explore/ku/{uid}/content  — HTMX fragment: Ku detail content
- GET  /explore/ps/{uid}          — PathStep detail page with sidebar
- GET  /explore/ps/{uid}/content  — HTMX fragment: PathStep detail content
- GET  /learning-loop/ps/{ps_uid}/exercises                — Exercise list with status
- GET  /learning-loop/ps/{ps_uid}/submissions-and-feedback — Submissions + feedback
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Request

from adapters.inbound.auth import get_current_user, require_authenticated_user
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from core.utils.logging import get_logger
from core.utils.markdown_renderer import render_markdown_with_toc
from ui.explore.ku_detail import render_ku_detail_content, render_ku_not_found
from ui.explore.nav import render_explore_sidebar_page
from ui.explore.ps_detail import render_ps_detail_content, render_ps_not_found
from ui.learning_loop.exercise_status import render_exercise_list
from ui.learning_loop.submissions_section import render_ps_submissions_and_feedback
from ui.patterns.error_banner import render_inline_error
from ui.patterns.loading import content_loading_placeholder

if TYPE_CHECKING:
    from core.orchestrator.explore_orchestrator import ExploreOrchestrator

logger = get_logger("skuel.routes.learning_loop")


# =============================================================================
# Detail pages — Ku and PathStep engagement
# =============================================================================


def create_learning_loop_detail_routes(
    _app: FastHTMLApp,
    rt: RouteDecorator,
    orchestrator: "ExploreOrchestrator",
) -> None:
    """Register /explore/ku/{uid} and /explore/ps/{uid} detail routes.

    These are the engagement pages where users read content, track
    learning state, and access exercises/submissions.

    Args:
        _app: FastHTML application instance.
        rt: Route decorator.
        orchestrator: ExploreOrchestrator for cross-service reads.
    """

    # -----------------------------------------------------------------
    # GET /explore/ku/{uid} — Ku detail page
    # -----------------------------------------------------------------

    @rt("/explore/ku/{uid}")
    async def explore_ku_detail(request: Request, uid: str) -> Any:
        """Ku detail page — shell renders immediately, content loads via HTMX."""
        user_uid = get_current_user(request)
        sidebar_data = await orchestrator.get_sidebar_data(user_uid) if user_uid else None
        content = content_loading_placeholder(f"/explore/ku/{uid}/content", "ku-detail-content")
        return await render_explore_sidebar_page(
            content=content,
            sidebar_data=sidebar_data,
            request=request,
            current_uid=uid,
            current_entity_type="ku",
        )

    @rt("/explore/ku/{uid}/content")
    async def explore_ku_content_fragment(request: Request, uid: str) -> Any:
        """HTMX fragment: Ku detail content with learning state and exercises."""
        user_uid: str | None = get_current_user(request)

        ku_result = await orchestrator.get_ku(uid)

        if not ku_result or ku_result.is_error or not ku_result.value:
            return render_ku_not_found(uid)

        ku = ku_result.value

        # Learning state
        learning_state: dict[str, bool] = {"is_studying": False, "is_understood": False}
        is_pinned = False
        if user_uid:
            state_result = await orchestrator.get_ku_learning_state(user_uid, uid)
            if state_result.is_ok:
                learning_state = state_result.value
            pins_result = await orchestrator.get_pinned_entities(user_uid)
            if pins_result.is_ok and pins_result.value:
                is_pinned = uid in set(pins_result.value)

        # Exercises
        exercises_result = await orchestrator.get_exercises_for_curriculum(uid)
        exercises_for_ku = exercises_result.value if exercises_result.is_ok else []

        # Render markdown
        content_html, toc_html = render_markdown_with_toc(ku.description or "")

        return render_ku_detail_content(
            ku=ku,
            uid=uid,
            content_html=content_html,
            toc_html=toc_html,
            learning_state=learning_state,
            is_pinned=is_pinned,
            user_uid=user_uid,
            exercises_for_ku=exercises_for_ku,
        )

    # -----------------------------------------------------------------
    # GET /explore/ps/{uid} — PathStep detail page (learning loop anchor)
    # -----------------------------------------------------------------

    @rt("/explore/ps/{uid}")
    async def explore_ps_detail(request: Request, uid: str) -> Any:
        """PathStep detail page — shell renders immediately, content loads via HTMX."""
        user_uid = get_current_user(request)
        sidebar_data = await orchestrator.get_sidebar_data(user_uid) if user_uid else None
        content = content_loading_placeholder(f"/explore/ps/{uid}/content", "ps-detail-content")
        return await render_explore_sidebar_page(
            content=content,
            sidebar_data=sidebar_data,
            request=request,
            current_uid=uid,
            current_entity_type="ps",
        )

    @rt("/explore/ps/{uid}/content")
    async def explore_ps_content_fragment(request: Request, uid: str) -> Any:
        """HTMX fragment: PathStep detail content with learning state and learning loop."""
        user_uid: str | None = get_current_user(request)

        result = await orchestrator.get_ps_with_content(uid)
        if result.is_error:
            return render_ps_not_found(uid)

        step, content_body = result.value
        if not content_body and getattr(step, "content", None):
            content_body = str(step.content)

        # Learning state
        is_marked_read = False
        is_bookmarked = False
        is_in_progress = False
        is_mastered = False
        if user_uid:
            await orchestrator.record_ps_view(user_uid, uid)
            state_result = await orchestrator.get_ps_learning_state(user_uid, uid)
            is_marked_read = state_result.value.is_marked_as_read if state_result.is_ok else False
            is_bookmarked = state_result.value.is_bookmarked if state_result.is_ok else False
            is_in_progress = (
                state_result.value.state.value == "in_progress" if state_result.is_ok else False
            )
            is_mastered = (
                state_result.value.state.value == "mastered" if state_result.is_ok else False
            )

        # Exercises for unauthenticated users
        exercises: list[dict] = []
        if not user_uid:
            exercises_result = await orchestrator.get_exercises_for_path_step(uid)
            if exercises_result.is_ok and exercises_result.value:
                exercises = exercises_result.value

        # Render markdown
        content_html, toc_html = render_markdown_with_toc(content_body or "")

        return render_ps_detail_content(
            step=step,
            uid=uid,
            content_html=content_html,
            toc_html=toc_html,
            is_marked_read=is_marked_read,
            is_bookmarked=is_bookmarked,
            is_in_progress=is_in_progress,
            is_mastered=is_mastered,
            user_uid=user_uid,
            exercises=exercises,
        )

    logger.info(
        "Learning loop detail routes registered: /explore/ku/{uid}, /explore/ps/{uid} "
        "(shell-first with /content fragments)"
    )


# =============================================================================
# HTMX fragment routes — exercises + submissions
# =============================================================================


def create_learning_loop_fragment_routes(
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

    logger.info(
        "Learning loop fragment routes registered: /learning-loop/ps/{ps_uid}/*"
    )


# =============================================================================
# Combined factory — convenience for explore_routes.py
# =============================================================================


def create_learning_loop_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    orchestrator: "ExploreOrchestrator",
) -> None:
    """Register all learning loop routes (detail pages + fragments).

    This is the single entry point called by explore_routes.py.
    """
    create_learning_loop_detail_routes(app, rt, orchestrator)
    create_learning_loop_fragment_routes(app, rt, orchestrator)


__all__ = [
    "create_learning_loop_routes",
    "create_learning_loop_detail_routes",
    "create_learning_loop_fragment_routes",
]
