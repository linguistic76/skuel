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
from adapters.inbound.auth.roles import get_user_role
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from core.models.enums import MasteryLevel
from core.models.shared.dual_track import DualTrackResult
from core.utils.logging import get_logger
from core.utils.markdown_renderer import render_markdown_with_toc
from ui.explore.ku_detail import render_ku_detail_content, render_ku_not_found
from ui.explore.ku_mastery import render_ku_mastery_result
from ui.explore.nav import render_explore_sidebar_page
from ui.explore.ps_detail import render_ps_detail_content, render_ps_not_found
from ui.learning_loop.exercise_status import render_exercise_list
from ui.learning_loop.submissions_section import render_ps_submissions_and_feedback
from ui.patterns.error_banner import render_inline_error
from ui.patterns.loading import content_loading_placeholder

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from core.orchestrator.explore_orchestrator import ExploreOrchestrator
    from core.services.ps_engagement.ps_engagement_service import PsEngagementService

logger = get_logger("skuel.routes.learning_loop")


# =============================================================================
# Knowledge dual-track (mastery) helpers — ADR-030
# =============================================================================


def _parse_mastery_level(raw: str) -> MasteryLevel | None:
    """Parse a raw form value into a MasteryLevel, or None when blank/invalid."""
    if not raw:
        return None
    try:
        return MasteryLevel(raw)
    except ValueError:
        logger.debug("Ku mastery check-in: ignoring invalid MasteryLevel value %r", raw)
        return None


async def _load_ku_mastery_checkins(
    user_service: Any, user_uid: str, ku_uid: str
) -> list[dict[str, Any]]:
    """Read the user's stored Knowledge dual-track check-ins for a Ku.

    The Knowledge dimension persists per-(user, Ku) on the :User node's
    ``knowledge_checkins`` log (a Ku is SHARED, so its mastery check-ins can't live
    on the shared :Ku node). Returns the log for this Ku, newest last.
    """
    if user_service is None:
        return []
    user_result = await user_service.get_user(user_uid)
    if user_result.is_ok and user_result.value:
        log: list[dict[str, Any]] = (user_result.value.knowledge_checkins or {}).get(ku_uid, [])
        return log
    return []


def _make_ku_mastery_store(
    user_service: Any, user_uid: str
) -> "Callable[[str, DualTrackResult[MasteryLevel]], Awaitable[None]]":
    """Build the dual-track ``store_callback(ku_uid, result)`` for the Knowledge
    dimension, with ``user_uid`` bound — persists per-(user, Ku) on the :User node."""

    async def _store(ku_uid: str, result: DualTrackResult[MasteryLevel]) -> None:
        await user_service.append_knowledge_checkin(ku_uid, result, user_uid=user_uid)

    return _store


# =============================================================================
# Detail pages — Ku and PathStep engagement
# =============================================================================


def create_learning_loop_detail_routes(
    _app: FastHTMLApp,
    rt: RouteDecorator,
    orchestrator: "ExploreOrchestrator",
    ps_engagement_service: "PsEngagementService | None" = None,
    user_service: Any = None,
) -> None:
    """Register /explore/ku/{uid} and /explore/ps/{uid} detail routes.

    These are the engagement pages where users read content, track
    learning state, and access exercises/submissions.

    Args:
        _app: FastHTML application instance.
        rt: Route decorator.
        orchestrator: ExploreOrchestrator for cross-service reads.
        ps_engagement_service: Read-only access for the active engagement
            edge on PS detail page load. Optional — engagement actions in
            the rendered detail collapse to "Engage" when this is None.
        user_service: Used to resolve the viewer's role for the teacher
            publish button on /explore/ps/{uid}. Optional — when absent,
            the publish state collapses to the empty-wrapper variant.
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
        user_uid = get_current_user(request)

        ku_result = await orchestrator.get_ku(uid)

        if not ku_result or ku_result.is_error or not ku_result.value:
            return render_ku_not_found(uid)

        ku = ku_result.value

        # Learning state
        learning_state: dict[str, bool] = {"is_studying": False, "is_understood": False}
        is_pinned = False
        mastery_checkins: list[dict] = []
        if user_uid:
            state_result = await orchestrator.get_ku_learning_state(user_uid, uid)
            if state_result.is_ok:
                learning_state = state_result.value
            pins_result = await orchestrator.get_pinned_entities(user_uid)
            if pins_result.is_ok and pins_result.value:
                is_pinned = uid in set(pins_result.value)
            mastery_checkins = await _load_ku_mastery_checkins(user_service, user_uid, uid)

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
            mastery_checkins=mastery_checkins,
        )

    # -----------------------------------------------------------------
    # POST /explore/ku/{uid}/mastery-checkin — Knowledge dual-track (ADR-030)
    # -----------------------------------------------------------------

    @rt("/explore/ku/{uid}/mastery-checkin", methods=["POST"])
    @csrf_protected
    async def explore_ku_mastery_checkin(request: Request, uid: str) -> Any:
        """HTMX POST: run + persist a Knowledge mastery dual-track check-in.

        POST + ``@csrf_protected`` because it mutates — appends a per-(user, Ku)
        check-in to the :User node's ``knowledge_checkins`` log (a Ku is SHARED, so
        its mastery check-ins live per-user, never on the shared :Ku node). The
        system side is the substance score, which needs the RICH user context
        (the activity→Ku channels), so we build it here.
        """
        user_uid = require_authenticated_user(request)
        if user_service is None:
            return render_inline_error("Mastery check-in is unavailable")

        form = await request.form()
        level = _parse_mastery_level(str(form.get("level", "")))
        if level is None:
            return render_inline_error("Please choose a mastery level")
        reflection = str(form.get("reflection", ""))

        ctx_result = await user_service.get_rich_unified_context(user_uid)
        if ctx_result.is_error:
            return render_inline_error("Could not load your context")

        result = await orchestrator.assess_ku_mastery(
            user_uid,
            uid,
            level,
            user_evidence=reflection,
            user_context=ctx_result.value,
            user_reflection=reflection or None,
            store_callback=_make_ku_mastery_store(user_service, user_uid),
        )
        if result.is_error:
            logger.warning(
                "Ku mastery assessment failed for %s (ku=%s): %s",
                user_uid,
                uid,
                result.expect_error().message,
            )
            return render_inline_error("Could not assess mastery right now")

        # Re-read so the trend includes the just-stored check-in.
        checkins = await _load_ku_mastery_checkins(user_service, user_uid, uid)
        return render_ku_mastery_result(result.value, checkins)

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
        user_uid = get_current_user(request)

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
        engagement = None
        user_role = None
        if user_uid and user_service is not None:
            user_role = await get_user_role(request, user_service)
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
            if ps_engagement_service is not None:
                engagement_result = await ps_engagement_service.find_active(user_uid, uid)
                if engagement_result.is_ok:
                    engagement = engagement_result.value

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
            engagement=engagement,
            user_role=user_role,
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

    logger.info("Learning loop fragment routes registered: /learning-loop/ps/{ps_uid}/*")


# =============================================================================
# Combined factory — convenience for explore_routes.py
# =============================================================================


def create_learning_loop_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    orchestrator: "ExploreOrchestrator",
    ps_engagement_service: "PsEngagementService | None" = None,
    user_service: Any = None,
) -> None:
    """Register all learning loop routes (detail pages + fragments).

    This is the single entry point called by explore_routes.py.
    """
    create_learning_loop_detail_routes(
        app, rt, orchestrator, ps_engagement_service, user_service=user_service
    )
    create_learning_loop_fragment_routes(app, rt, orchestrator)


__all__ = [
    "create_learning_loop_routes",
    "create_learning_loop_detail_routes",
    "create_learning_loop_fragment_routes",
]
