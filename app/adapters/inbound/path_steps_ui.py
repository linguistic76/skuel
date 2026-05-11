"""
Path Steps UI Routes — Browser + Learning State Actions
=========================================================

GET /path-steps — top-level PathStep browser (lists all curriculum PathSteps).
POST mutation endpoints for HTMX learning state actions (start, mark-read, bookmark).
Detail view lives at /explore/ps/{uid} (explore_ui.py).
"""

from typing import Any

from fasthtml.common import A, Div, P, Request, Span

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.csrf import csrf_protected
from core.services.ps_engagement.engagement import Engagement
from core.services.ps_engagement.ps_engagement_service import (
    PsEngagementService,
    ReviewDecision,
)
from core.services.ps_service import PsService
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonT
from ui.explore.ps_completion_review import render_review_error, render_review_form
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.patterns.empty_state import EmptyState
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.page_header import PageHeader

# Container id used by HTMX swaps for the engagement action group.
# Defined here so both renderer and handlers stay in sync.
_ENGAGEMENT_ACTIONS_ID = "ps-engagement-actions"

logger = get_logger("skuel.routes.path_steps.ui")


# ============================================================================
# Helpers
# ============================================================================


def _start_step_button(uid: str, is_in_progress: bool, is_mastered: bool) -> Any:
    """Render the enrollment/start button based on learning state."""
    if is_mastered:
        return Badge("Mastered", variant=BadgeT.success, size=Size.sm)
    if is_in_progress:
        return Badge("In Progress", variant=BadgeT.secondary, size=Size.sm)
    return Button(
        "Start Learning",
        variant=ButtonT.primary,
        size=Size.sm,
        hx_post=f"/api/path-steps/{uid}/start",
        hx_swap="outerHTML",
        hx_target="this",
    )


def _parse_review_form(form: Any) -> dict[str, ReviewDecision]:
    """Build the review dict from the inline review form's payload.

    The form carries one ``template_uids`` hidden field per spawned template
    (every row contributes one — Starlette returns them as a multi-value
    list via ``getlist``). For each template UID, the corresponding
    ``keep_{template_uid}`` checkbox is present in the form payload only
    when the user left it checked; missing == discard. Templates absent
    from the form (defensive) default to "keep" — matches the service's
    forgiving default.
    """
    template_uids = form.getlist("template_uids") if hasattr(form, "getlist") else []
    review: dict[str, ReviewDecision] = {}
    for template_uid in template_uids:
        review[template_uid] = "keep" if f"keep_{template_uid}" in form else "discard"
    return review


def render_engagement_actions(uid: str, engagement: Engagement | None) -> Any:
    """Render the Engage/Complete/Abandon button group for a PathStep.

    The group's outer div carries id="ps-engagement-actions" — HTMX handlers
    return this same wrapper so swaps replace it in place. When engaged, the
    Complete button hx-GETs the review form into the same wrapper; Cancel on
    that form hx-GETs ``/explore/ps/{uid}/engagement-actions`` to restore the
    button row.
    """
    if engagement is None:
        body: Any = Button(
            "Engage with this Path Step",
            variant=ButtonT.primary,
            size=Size.sm,
            hx_post=f"/explore/ps/{uid}/engage",
            hx_swap="outerHTML",
            hx_target=f"#{_ENGAGEMENT_ACTIONS_ID}",
        )
    else:
        body = Div(
            Badge("Engaged", variant=BadgeT.success, size=Size.sm),
            Button(
                "Complete",
                variant=ButtonT.primary,
                size=Size.sm,
                hx_get=f"/explore/ps/{uid}/complete-review",
                hx_swap="outerHTML",
                hx_target=f"#{_ENGAGEMENT_ACTIONS_ID}",
            ),
            Button(
                "Abandon",
                variant=ButtonT.ghost,
                size=Size.sm,
                hx_post=f"/explore/ps/{uid}/abandon",
                hx_swap="outerHTML",
                hx_target=f"#{_ENGAGEMENT_ACTIONS_ID}",
                hx_confirm="Abandon this engagement? Spawned activities will be removed.",
            ),
            cls="flex items-center gap-3",
        )
    return Div(body, id=_ENGAGEMENT_ACTIONS_ID, cls="flex items-center gap-2")


# ============================================================================
# Route factory
# ============================================================================


def create_path_steps_ui_routes(
    _app: Any,
    rt: Any,
    ps_service: PsService,
    ps_engagement_service: PsEngagementService | None = None,
) -> list[Any]:
    """Create Path Steps UI routes.

    GET /path-steps lists all curriculum PathSteps. Detail view lives at
    /explore/ps/{uid} (merged discovery page). POST mutation endpoints remain
    here for HTMX learning state actions, plus the Engage/Abandon engagement
    flow (HTML-returning peers of the JSON API at /api/ps/{uid}/...).

    ``ps_engagement_service`` is optional so curriculum-only deployments
    without the engagement subsystem still get the read/learning routes.
    """

    # ========================================================================
    # BROWSER
    # ========================================================================

    @rt("/path-steps")
    async def path_steps_browser(request: Request) -> Any:
        """PathSteps browser — shell renders immediately, content loads via HTMX."""
        content = Div(
            PageHeader("Path Steps", subtitle="Curriculum content units (composed of Kus)"),
            content_loading_placeholder("/path-steps/content", "path-steps-content"),
            id="main-content",
        )
        return await BasePage(
            content=content,
            title="Path Steps",
            request=request,
            active_page="path-steps",
        )

    @rt("/path-steps/content")
    async def path_steps_content_fragment(request: Request) -> Any:
        """HTMX fragment: PathStep list."""
        result = await ps_service.list_steps(limit=50)
        items: list[Any] = []
        if not result.is_error and result.value:
            items = list(result.value)
        return Div(_path_step_list(items), id="path-steps-content")

    # ========================================================================
    # LEARNING STATE HTMX ACTIONS
    # ========================================================================

    @rt("/api/path-steps/{uid}/start", methods=["POST"])
    @csrf_protected
    async def start_step(request: Request, uid: str) -> Any:
        """Start a path step (mark as in-progress). Returns updated button HTML.

        Enforces a limit of 2 simultaneously enrolled PathSteps.
        """
        user_uid = require_authenticated_user(request)

        # Enforce enrollment limit (max 2 in-progress PathSteps)
        count_result = await ps_service.mastery.count_in_progress_steps(user_uid)
        if not count_result.is_error and (count_result.value or 0) >= 2:
            return Button(
                "Limit reached (2)",
                variant=ButtonT.error,
                size=Size.sm,
                disabled=True,
                title="You can enrol in at most 2 Path Steps at once",
            )

        result = await ps_service.mastery.mark_in_progress(user_uid, uid)

        if result.is_error:
            return Button(
                "Error",
                variant=ButtonT.error,
                size=Size.sm,
                disabled=True,
            )

        return Badge("In Progress", variant=BadgeT.secondary, size=Size.sm)

    @rt("/api/path-steps/{uid}/mark-read", methods=["POST"])
    @csrf_protected
    async def mark_step_as_read(request: Request, uid: str) -> Any:
        """Mark path step as read. Returns updated button HTML."""
        user_uid = require_authenticated_user(request)

        result = await ps_service.mastery.mark_as_read(user_uid, uid)

        if result.is_error:
            return Button(
                "Error",
                variant=ButtonT.error,
                size=Size.sm,
                disabled=True,
            )

        return Button(
            "Marked as Read",
            variant=ButtonT.success,
            size=Size.sm,
            disabled=True,
        )

    @rt("/api/path-steps/{uid}/bookmark", methods=["POST"])
    @csrf_protected
    async def toggle_step_bookmark(request: Request, uid: str) -> Any:
        """Toggle path step bookmark. Returns updated button HTML."""
        user_uid = require_authenticated_user(request)

        result = await ps_service.mastery.toggle_bookmark(user_uid, uid)

        if result.is_error:
            return Button(
                "Error",
                variant=ButtonT.error,
                size=Size.sm,
                disabled=True,
            )

        is_bookmarked = result.value

        return Button(
            "Bookmarked" if is_bookmarked else "Bookmark",
            variant=ButtonT.secondary if is_bookmarked else ButtonT.ghost,
            size=Size.sm,
            hx_post=f"/api/path-steps/{uid}/bookmark",
            hx_swap="outerHTML",
            hx_target="this",
        )

    # ========================================================================
    # ENGAGEMENT HTMX ACTIONS (slice 1: engage + abandon)
    # ========================================================================

    if ps_engagement_service is not None:

        @rt("/explore/ps/{uid}/engage", methods=["POST"])
        @csrf_protected
        async def engage_path_step(request: Request, uid: str) -> Any:
            """Open an engagement with this PathStep. Returns updated action group."""
            user_uid = require_authenticated_user(request)
            result = await ps_engagement_service.engage_pathstep(user_uid, uid)
            if result.is_error:
                # Re-read state so the rendered group still reflects reality
                # (e.g. an "already engaged" race resolves to the engaged view).
                active = await ps_engagement_service.find_active(user_uid, uid)
                engagement = active.value if active.is_ok else None
                return render_engagement_actions(uid, engagement)
            return render_engagement_actions(uid, result.value)

        @rt("/explore/ps/{uid}/abandon", methods=["POST"])
        @csrf_protected
        async def abandon_path_step(request: Request, uid: str) -> Any:
            """Abandon the active engagement. Returns updated action group."""
            user_uid = require_authenticated_user(request)
            result = await ps_engagement_service.abandon_pathstep(user_uid, uid)
            if result.is_error:
                active = await ps_engagement_service.find_active(user_uid, uid)
                engagement = active.value if active.is_ok else None
                return render_engagement_actions(uid, engagement)
            # After abandon, find_active returns None (state="abandoned" is
            # filtered out) — render_engagement_actions(None) shows Engage again.
            return render_engagement_actions(uid, None)

        @rt("/explore/ps/{uid}/engagement-actions")
        async def get_engagement_actions(request: Request, uid: str) -> Any:
            """Re-render the engagement-actions group from current state.

            Used by the review form's Cancel button to bail out without
            mutating the engagement edge.
            """
            user_uid = require_authenticated_user(request)
            active = await ps_engagement_service.find_active(user_uid, uid)
            engagement = active.value if active.is_ok else None
            return render_engagement_actions(uid, engagement)

        @rt("/explore/ps/{uid}/complete-review")
        async def get_complete_review(request: Request, uid: str) -> Any:
            """Fetch the inline review form for the active engagement."""
            user_uid = require_authenticated_user(request)
            active = await ps_engagement_service.find_active(user_uid, uid)
            if active.is_error or active.value is None:
                # No active engagement — restore the engagement-actions group.
                return render_engagement_actions(uid, active.value if active.is_ok else None)
            items_result = await ps_engagement_service.list_review_items(user_uid, uid)
            if items_result.is_error:
                return render_review_error(
                    uid,
                    "Could not load the activities spawned by this PathStep. Please try again.",
                )
            return render_review_form(uid, items_result.value)

        @rt("/explore/ps/{uid}/complete", methods=["POST"])
        @csrf_protected
        async def complete_path_step(request: Request, uid: str) -> Any:
            """Apply the keep/discard review and close the engagement."""
            user_uid = require_authenticated_user(request)
            form = await request.form()
            review = _parse_review_form(form)

            result = await ps_engagement_service.complete_pathstep(user_uid, uid, review)
            if result.is_error:
                err = result.expect_error()
                return render_review_error(uid, err.display_message or "Completion failed.")
            # Engagement is now state='completed' — find_active returns None,
            # so the Engage button reappears.
            return render_engagement_actions(uid, None)

    engagement_routes_note = (
        (
            ", /explore/ps/{uid}/engage, /explore/ps/{uid}/abandon, "
            "/explore/ps/{uid}/complete-review, /explore/ps/{uid}/complete, "
            "/explore/ps/{uid}/engagement-actions"
        )
        if ps_engagement_service is not None
        else " (engagement routes skipped — ps_engagement_service unavailable)"
    )
    logger.info(
        "Path Steps UI routes registered: "
        "/path-steps, /path-steps/content, "
        "/api/path-steps/{uid}/start, /api/path-steps/{uid}/mark-read, "
        "/api/path-steps/{uid}/bookmark" + engagement_routes_note
    )

    return []


def _path_step_list(items: list[Any]) -> Any:
    """Render PathSteps with a teal 'Path Step' badge per row.

    Mirrors the visual treatment in library_ui.py so PathStep rows look
    consistent everywhere.
    """
    if not items:
        return EmptyState(title="No path steps found")

    count_note = Span(
        f"{len(items)} path step{'s' if len(items) != 1 else ''}",
        cls="text-xs text-muted-foreground mb-3 block",
    )

    rows = []
    for step in items:
        uid = getattr(step, "uid", "")
        title = getattr(step, "title", None) or uid or "Untitled"
        description = getattr(step, "description", "") or ""
        truncated = description[:120] + ("…" if len(description) > 120 else "")

        rows.append(
            Div(
                Div(
                    Badge(
                        "Path Step",
                        variant=None,
                        cls="bg-teal-100 text-teal-800 border-teal-200",
                        size=Size.sm,
                    ),
                    A(
                        title,
                        href=f"/explore/ps/{uid}" if uid else "#",
                        cls="text-sm font-medium text-foreground hover:text-primary hover:underline ml-2",
                    ),
                    cls="flex items-center",
                ),
                P(truncated, cls="text-xs text-muted-foreground mt-0.5") if description else None,
                cls="py-2.5 border-b border-border/50 last:border-0",
            )
        )
    return Div(count_note, Div(*rows))


__all__ = ["create_path_steps_ui_routes"]
