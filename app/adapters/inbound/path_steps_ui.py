"""
Path Steps UI Routes — Browser + Learning State Actions
=========================================================

GET /path-steps — top-level PathStep browser (lists all curriculum PathSteps).
POST mutation endpoints for HTMX learning state actions (start, mark-read, bookmark).
Detail view lives at /explore/ps/{uid} (explore_ui.py).
"""

from typing import Any, cast

from fasthtml.common import A, Div, P, Request, Span
from starlette.datastructures import FormData

from adapters.inbound.auth import get_current_user, require_authenticated_user
from adapters.inbound.auth.roles import get_user_role
from adapters.inbound.boundary import result_to_response
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.result_helpers import require_found
from core.models.enums import UserRole
from core.models.enums.learning_enums import KnowledgeStatus
from core.ports.query_types import Violation
from core.services.ps_engagement.engagement import Engagement
from core.services.ps_engagement.ps_engagement_service import (
    PsEngagementService,
    ReviewDecision,
)
from core.services.ps_service import PsService
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from ui.components import Button, ButtonT
from ui.explore.ps_completion_review import render_review_error, render_review_form
from ui.explore.ps_publish_state import (
    render_publish_state,
    render_publish_violations,
    render_status_badge,
)
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
        cls=ButtonT.primary,
        size="sm",
        hx_post=f"/api/path-steps/{uid}/start",
        hx_swap="outerHTML",
        hx_target="this",
    )


def _parse_review_form(form: FormData) -> dict[str, ReviewDecision]:
    """Build the review dict from the inline review form's payload.

    The form carries one ``template_uids`` hidden field per spawned template
    (every row contributes one — Starlette returns them as a multi-value
    list via ``getlist``). For each template UID, the corresponding
    ``keep_{template_uid}`` checkbox is present in the form payload only
    when the user left it checked; missing == discard. Templates absent
    from the form (defensive) default to "keep" — matches the service's
    forgiving default.
    """
    template_uids = form.getlist("template_uids")
    review: dict[str, ReviewDecision] = {}
    for template_uid in template_uids:
        if not isinstance(template_uid, str):
            continue
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
            cls=ButtonT.primary,
            size="sm",
            hx_post=f"/explore/ps/{uid}/engage",
            hx_swap="outerHTML",
            hx_target=f"#{_ENGAGEMENT_ACTIONS_ID}",
        )
    else:
        body = Div(
            Badge("Engaged", variant=BadgeT.success, size=Size.sm),
            Button(
                "Complete",
                cls=ButtonT.primary,
                size="sm",
                hx_get=f"/explore/ps/{uid}/complete-review",
                hx_swap="outerHTML",
                hx_target=f"#{_ENGAGEMENT_ACTIONS_ID}",
            ),
            Button(
                "Abandon",
                cls=ButtonT.ghost,
                size="sm",
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
    user_service: Any = None,
    tasks_service: Any = None,
) -> list[Any]:
    """Create Path Steps UI routes.

    GET /path-steps lists all curriculum PathSteps. Detail view lives at
    /explore/ps/{uid} (merged discovery page). POST mutation endpoints remain
    here for HTMX learning state actions, plus the Engage/Abandon engagement
    flow (HTML-returning peers of the JSON API at /api/ps/{uid}/...).

    ``ps_engagement_service`` is optional so curriculum-only deployments
    without the engagement subsystem still get the read/learning routes.
    ``user_service`` is required for the teacher publish flow (slice 2);
    when absent, the publish routes are skipped.
    ``tasks_service`` is required for the tasks-from-this-step fragment;
    when absent, the /explore/ps/{uid}/tasks route is skipped.
    """

    # ========================================================================
    # BROWSER
    # ========================================================================

    @rt("/path-steps")
    def path_steps_browser(request: Request) -> Any:
        """PathSteps browser — shell renders immediately, content loads via HTMX."""
        content = Div(
            PageHeader("Path Steps", subtitle="Curriculum content units (composed of Kus)"),
            content_loading_placeholder("/path-steps/content", "path-steps-content"),
            id="main-content",
        )
        return BasePage(
            content=content,
            title="Path Steps",
            request=request,
            active_page="path-steps",
        )

    @rt("/path-steps/content")
    async def path_steps_content_fragment(request: Request) -> Any:
        """HTMX fragment: PathStep list, with enrollment badges for the current user."""
        result = await ps_service.list_steps(limit=50)
        items: list[Any] = []
        if not result.is_error and result.value:
            items = list(result.value)

        # Curriculum lists are anonymous-readable; badges only when logged in.
        enrolled_uids: set[str] = set()
        user_uid = get_current_user(request)
        if user_uid:
            enrolled_result = await ps_service.mastery.get_in_progress_step_uids(user_uid)
            if not enrolled_result.is_error and enrolled_result.value:
                enrolled_uids = set(enrolled_result.value)

        return Div(_path_step_list(items, enrolled_uids), id="path-steps-content")

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
                cls=ButtonT.destructive,
                size="sm",
                disabled=True,
                title="You can enrol in at most 2 Path Steps at once",
            )

        result = await ps_service.mastery.mark_in_progress(user_uid, uid)

        if result.is_error:
            return Button(
                "Error",
                cls=ButtonT.destructive,
                size="sm",
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
                cls=ButtonT.destructive,
                size="sm",
                disabled=True,
            )

        return Button(
            "Marked as Read",
            cls=ButtonT.primary,
            size="sm",
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
                cls=ButtonT.destructive,
                size="sm",
                disabled=True,
            )

        is_bookmarked = result.value

        return Button(
            "Bookmarked" if is_bookmarked else "Bookmark",
            cls=ButtonT.secondary if is_bookmarked else ButtonT.ghost,
            size=Size.sm,
            hx_post=f"/api/path-steps/{uid}/bookmark",
            hx_swap="outerHTML",
            hx_target="this",
        )

    # ========================================================================
    # READING-FIRST PROGRESS + BOOKMARK (ps-detail.js Alpine component)
    # ========================================================================

    @rt("/explore/ps/{uid}/progress", methods=["POST"])
    @csrf_protected
    async def update_ps_progress(request: Request, uid: str) -> Any:
        """Advance PathStep learning state. Called by ps-detail.js (hx-swap=none).

        state=learning, review=false → new enrollment (mark_in_progress, cap enforced, fires PathStepEnrolled)
        state=learning, review=true  → Review again (mark_as_learning, no cap, no event)
        state=read                   → mark_as_read
        Alpine updates the UI optimistically; on success the empty response is
        discarded. Failures (enrollment cap, write errors) return an error status
        with X-Toast headers — ps-detail.js rolls the optimistic state back and
        surfaces the toast (G7: no more silent failures).
        """
        user_uid = require_authenticated_user(request)
        form = await request.form()
        state = str(form.get("state", ""))
        review = str(form.get("review", "")) == "true"
        if state not in ("read", "learning"):  # skuel-lint: disable=SKUEL014 -- form state
            # A malformed POST must not look like success — the old
            # fall-through returned 200 and the caller's optimistic UI stuck.
            return result_to_response(
                Result.fail(
                    Errors.validation(
                        f"Unknown progress state {state!r} — expected 'read' or 'learning'",
                        field="state",
                    )
                )
            )
        result: Result[bool] | None = None
        if state == "read":
            result = await ps_service.mastery.mark_as_read(user_uid, uid)
        elif state == "learning":  # skuel-lint: disable=SKUEL014 -- form state, not domain
            if review:
                result = await ps_service.mastery.mark_as_learning(user_uid, uid)
            else:
                count_result = await ps_service.mastery.count_in_progress_steps(user_uid)
                if not count_result.is_error and (count_result.value or 0) >= 2:
                    return result_to_response(
                        Result.fail(
                            Errors.business(
                                rule="ps_enrollment_cap",
                                message="You can study at most 2 Path Steps at once"
                                " - mark one as read to start another.",
                            )
                        )
                    )
                result = await ps_service.mastery.mark_in_progress(user_uid, uid)
        if result is not None and result.is_error:
            return result_to_response(result)
        return Div()  # hx-swap="none" — success response is discarded

    @rt("/explore/ps/{uid}/bookmark", methods=["POST"])
    @csrf_protected
    async def update_ps_bookmark(request: Request, uid: str) -> Any:
        """Set PathStep bookmark to explicit state. Called by ps-detail.js (hx-swap=none).

        Reads on=true|false from the form and applies it directly — idempotent
        on network retries. Alpine has already updated the UI optimistically.
        """
        user_uid = require_authenticated_user(request)
        form = await request.form()
        desired = str(form.get("on", "")).lower() == "true"
        result = await ps_service.mastery.set_bookmark(user_uid, uid, desired)
        if result.is_error:
            # G7: a failed write must reach the user (X-Toast via the global
            # listener), not vanish behind the optimistic star.
            return result_to_response(result)
        return Div()  # hx-swap="none" — success response is discarded

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
            active = require_found(
                await ps_engagement_service.find_active(user_uid, uid), "Engagement", uid
            )
            if active.is_error:
                # No active engagement — restore the engagement-actions group.
                return render_engagement_actions(uid, None)
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

    # ========================================================================
    # PUBLISH HTMX ACTIONS (slice 2: teacher draft → published flow)
    # ========================================================================

    if ps_engagement_service is not None and user_service is not None:

        async def _is_teacher(request: Request) -> bool:
            role = await get_user_role(request, user_service)
            return role is not None and role.has_permission(UserRole.TEACHER)

        async def _current_ps_status(uid: str) -> KnowledgeStatus | None:
            ps_result = await ps_service.core.get(uid)
            if ps_result.is_error or ps_result.value is None:
                return None
            status = getattr(ps_result.value, "status", None)
            if isinstance(status, KnowledgeStatus):
                return status
            if isinstance(status, str):
                try:
                    return KnowledgeStatus(status)
                except ValueError:
                    return None
            return None

        @rt("/explore/ps/{uid}/publish", methods=["POST"])
        @csrf_protected
        async def publish_path_step(request: Request, uid: str) -> Any:
            """Validate + publish a PathStep. Teacher-only.

            On success: returns the publish-state wrapper (now empty, since
            status flipped to PUBLISHED) plus an out-of-band swap of the
            ``#ps-status-badge`` to reflect the new status.

            On validation failure (``ps_validation_report``): returns the
            violations panel into the publish-state wrapper — the teacher
            sees every broken cross-template reference at once.
            """
            # require_authenticated_user raises 401 if the user isn't logged in;
            # the role check below produces a 403-equivalent empty wrapper for
            # authenticated non-teachers (matches the SHARED-content posture:
            # the button never rendered for them either).
            require_authenticated_user(request)
            if not await _is_teacher(request):
                return render_publish_state(uid, await _current_ps_status(uid), is_teacher=False)

            result = await ps_engagement_service.publish_pathstep(uid)
            if result.is_error:
                err = result.expect_error()
                violations = err.details.get("violations") if err.details else None
                if err.code == "BUSINESS_PS_TEMPLATE_VALIDATION" and isinstance(violations, list):
                    return render_publish_violations(uid, cast("list[Violation]", violations))
                # Other failures (not-found, infra) collapse to an empty
                # wrapper rather than a noisy banner — the teacher can retry
                # from the page; system errors surface elsewhere.
                return render_publish_state(uid, await _current_ps_status(uid), is_teacher=True)

            # Success: publish_pathstep returns the updated PS with status=PUBLISHED.
            # Tuple = (in-place wrapper, OOB badge). FastHTML serializes both.
            new_status = getattr(result.value, "status", KnowledgeStatus.PUBLISHED)
            return (
                render_publish_state(uid, new_status, is_teacher=True),
                render_status_badge(new_status, oob=True),
            )

        @rt("/explore/ps/{uid}/publish-state")
        async def get_publish_state(request: Request, uid: str) -> Any:
            """Restore the publish-state wrapper.

            Used by the Dismiss button on the validation-error panel and by
            any other client that needs to reset the wrapper to its from-page
            baseline (button if teacher+DRAFT, empty otherwise).
            """
            require_authenticated_user(request)
            is_teacher = await _is_teacher(request)
            return render_publish_state(uid, await _current_ps_status(uid), is_teacher=is_teacher)

    # ========================================================================
    # TASKS FRAGMENT (tasks spawned from this PathStep, authenticated users)
    # ========================================================================

    if tasks_service is not None:

        @rt("/explore/ps/{uid}/tasks")
        async def get_ps_tasks_fragment(request: Request, uid: str) -> Any:
            """HTMX fragment: tasks spawned from this PathStep for the current user.

            Returns compact task rows (status indicator + title link). Fires on
            page load and on the `ps-engaged` event so newly spawned tasks appear
            immediately after engagement.
            """
            user_uid = require_authenticated_user(request)
            result = await tasks_service.get_tasks_for_path_step(uid)
            tasks = [t for t in result.value if t.user_uid == user_uid] if result.is_ok else []
            return _ps_tasks_fragment(uid, tasks)

    engagement_routes_note = (
        (
            ", /explore/ps/{uid}/engage, /explore/ps/{uid}/abandon, "
            "/explore/ps/{uid}/complete-review, /explore/ps/{uid}/complete, "
            "/explore/ps/{uid}/engagement-actions"
        )
        if ps_engagement_service is not None
        else " (engagement routes skipped — ps_engagement_service unavailable)"
    )
    publish_routes_note = (
        ", /explore/ps/{uid}/publish, /explore/ps/{uid}/publish-state"
        if ps_engagement_service is not None and user_service is not None
        else " (publish routes skipped — user_service unavailable)"
    )
    tasks_routes_note = (
        ", /explore/ps/{uid}/tasks"
        if tasks_service is not None
        else " (tasks fragment skipped — tasks_service unavailable)"
    )
    logger.info(
        "Path Steps UI routes registered: "
        "/path-steps, /path-steps/content, "
        "/api/path-steps/{uid}/start, /api/path-steps/{uid}/mark-read, "
        "/api/path-steps/{uid}/bookmark"
        + engagement_routes_note
        + publish_routes_note
        + tasks_routes_note
    )

    return []


def _ps_tasks_fragment(uid: str, tasks: list[Any]) -> Any:
    """Replaceable HTMX fragment: tasks spawned from a PathStep for the current user.

    Returns a Div with id="ps-tasks-fragment" so HTMX outerHTML swap replaces
    the loading placeholder (or itself on refresh after engagement).
    """
    if not tasks:
        # Truthful empty state: this fragment renders for enrolled users too,
        # and most steps ship no task templates — "click Start learning" was
        # wrong on both axes for them.
        body: Any = P(
            "No tasks from this step yet. Steps that include task templates "
            "create them when you start learning.",
            cls="text-[13px] text-muted-foreground",
        )
    else:
        rows = []
        for task in tasks:
            status = getattr(task, "status", None)
            is_done = status is not None and str(status) in ("completed", "done")
            rows.append(
                Div(
                    Span(
                        cls=(
                            "w-2 h-2 rounded-full flex-none "
                            + ("bg-priority-low" if is_done else "bg-muted-foreground/50")
                        ),
                    ),
                    A(
                        getattr(task, "title", None) or task.uid,
                        href=f"/tasks/detail?uid={task.uid}",
                        cls=(
                            "text-[13px] font-medium hover:underline "
                            + (
                                "line-through text-muted-foreground"
                                if is_done
                                else "text-foreground/85"
                            )
                        ),
                    ),
                    cls="flex items-center gap-2.5 py-1.5",
                )
            )
        body = Div(*rows)

    # Retain hx-get + hx-trigger so the element stays listenable after the
    # outerHTML swap replaces the initial placeholder.  "load" is omitted here
    # (the placeholder fires that); only ps-engaged triggers subsequent reloads.
    return Div(
        body,
        id="ps-tasks-fragment",
        **{
            "hx-get": f"/explore/ps/{uid}/tasks",
            "hx-trigger": "ps-engaged",
            "hx-swap": "outerHTML",
        },
    )


def _path_step_list(items: list[Any], enrolled_uids: set[str]) -> Any:
    """Render PathSteps with a teal 'Path Step' badge per row.

    Rows whose uid is in ``enrolled_uids`` (the user's IN_PROGRESS edges)
    additionally get an 'Enrolled' badge. Mirrors the visual treatment in
    library_ui.py so PathStep rows look consistent everywhere.
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
                    Badge("Enrolled", variant=BadgeT.secondary, size=Size.sm, cls="ml-2")
                    if uid in enrolled_uids
                    else None,
                    cls="flex items-center",
                ),
                P(truncated, cls="text-xs text-muted-foreground mt-0.5") if description else None,
                cls="py-2.5 border-b border-border/50 last:border-0",
            )
        )
    return Div(count_note, Div(*rows))


__all__ = ["create_path_steps_ui_routes"]
