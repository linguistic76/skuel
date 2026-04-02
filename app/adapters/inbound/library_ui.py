"""
Library UI Route — /library
============================

Unified learning hub with seven tabs:

- Exercises       — Exercises assigned via group membership, with submission/feedback status
- Submissions     — User's exercise submissions with status badges
- Resources       — Admin-curated content (books, talks, films, podcasts)
- Ku              — All atomic knowledge units (links to /ku/{uid})
- Path Steps      — All curriculum path steps (links to /path-steps/{uid}/details)
- Exercise Reports — Teacher/AI feedback (reuses /reports/list fragment)
- Activity Reports — Activity domain analysis (reuses /reports/activity-list fragment)

HTMX fragment endpoints:
  GET /library/exercises    — exercises with submission/feedback status (Exercises tab)
  GET /library/submissions  — user's exercise submissions (Submissions tab)
  GET /library/resources    — Resource entity list (Resources tab)
  GET /library/ku           — all Ku (Ku tab)
  GET /library/path-steps   — all PathSteps (Path Steps tab)

Tab content for Exercise Reports and Activity Reports is HTMX-loaded from
existing fragment endpoints in exercise_reports_ui.py and activity_reports_ui.py.

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from fasthtml.common import A, Div, P, Span

from adapters.inbound.auth import get_current_user, require_authenticated_user
from adapters.inbound.fasthtml_types import Request, RouteDecorator, RouteList
from core.models.enums.entity_enums import EntityType
from core.ports.query_types import ExerciseStatusRow
from core.utils.logging import get_logger
from ui.layouts.base_page import BasePage
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_error_banner
from ui.patterns.page_header import PageHeader

logger = get_logger("skuel.routes.library")


# ============================================================================
# TYPE BADGE HELPERS
# ============================================================================

_EXERCISE_BADGE_CLS = "bg-amber-100 text-amber-800 border border-amber-200 text-xs font-medium px-2 py-0.5 rounded-full"

_MEDIA_BADGE_CLS: dict[str, str] = {
    "book": "bg-green-100 text-green-800 border border-green-200",
    "talk": "bg-blue-100 text-blue-800 border border-blue-200",
    "film": "bg-purple-100 text-purple-800 border border-purple-200",
    "podcast": "bg-orange-100 text-orange-800 border border-orange-200",
    "article": "bg-yellow-100 text-yellow-800 border border-yellow-200",
    "music": "bg-pink-100 text-pink-800 border border-pink-200",
}
_MEDIA_BADGE_DEFAULT = "bg-muted text-muted-foreground border border-border"

_KU_BADGE_CLS = "bg-violet-100 text-violet-800 border border-violet-200 text-xs font-medium px-2 py-0.5 rounded-full"
_PS_BADGE_CLS = (
    "bg-teal-100 text-teal-800 border border-teal-200 text-xs font-medium px-2 py-0.5 rounded-full"
)


def _exercise_badge() -> Span:
    """Colored pill badge for exercise type."""
    return Span("Exercise", cls=_EXERCISE_BADGE_CLS)


def _media_badge(media_type: str | None) -> Span:
    """Colored pill badge showing resource media type."""
    label = (media_type or "content").title()
    base_cls = _MEDIA_BADGE_CLS.get(media_type or "", _MEDIA_BADGE_DEFAULT)
    return Span(label, cls=f"{base_cls} text-xs font-medium px-2 py-0.5 rounded-full border")


# ============================================================================
# EXERCISES FRAGMENT RENDERER
# ============================================================================

_STATUS_PILL: dict[str, tuple[str, str]] = {
    # key -> (label, CSS classes)
    "not_submitted": (
        "Not Submitted",
        "bg-muted text-muted-foreground border border-border text-xs font-medium px-2 py-0.5 rounded-full",
    ),
    "submitted": (
        "Submitted",
        "bg-blue-100 text-blue-800 border border-blue-200 text-xs font-medium px-2 py-0.5 rounded-full",
    ),
    "feedback_available": (
        "Feedback Available",
        "bg-green-100 text-green-800 border border-green-200 text-xs font-medium px-2 py-0.5 rounded-full",
    ),
    "revision_requested": (
        "Revision Requested",
        "bg-amber-100 text-amber-800 border border-amber-200 text-xs font-medium px-2 py-0.5 rounded-full",
    ),
}


def _exercise_status_key(row: "ExerciseStatusRow") -> str:
    """Derive display status key from exercise row fields."""
    if row["has_report"]:
        if (row["report_outcome"] or "").lower() == "needs_revision":
            return "revision_requested"
        return "feedback_available"
    if row["has_submission"]:
        return "submitted"
    return "not_submitted"


def _exercise_action_link(row: "ExerciseStatusRow") -> A:
    """Return the primary action link for an exercise row."""
    status = _exercise_status_key(row)
    uid = row["uid"]
    if status == "not_submitted":
        return A(
            "Submit →",
            href=f"/submit?exercise_uid={uid}",
            cls="text-xs text-primary hover:underline shrink-0",
        )
    if status == "submitted":
        return A(
            "View Submission →",
            href=f"/submissions/{row['submission_uid']}",
            cls="text-xs text-primary hover:underline shrink-0",
        )
    # feedback_available or revision_requested
    return A(
        "View Report →",
        href=f"/exercise-reports/{row['report_uid']}",
        cls="text-xs text-primary hover:underline shrink-0",
    )


def _exercise_item(row: "ExerciseStatusRow") -> Div:
    """Single row for an assigned exercise showing submission/feedback status."""
    snippet = (row["description"] or "")[:120]
    if len(row["description"] or "") > 120:
        snippet += "…"

    status_key = _exercise_status_key(row)
    status_label, status_cls = _STATUS_PILL[status_key]

    return Div(
        Div(
            _exercise_badge(),
            A(
                row["title"] or row["uid"],
                href=f"/exercises/get?uid={row['uid']}",
                cls="text-sm font-medium text-foreground hover:text-primary hover:underline ml-2 mr-auto",
            ),
            Span(status_label, cls=status_cls),
            A(
                "Download",
                href=f"/api/exercises/md?uid={row['uid']}",
                cls="text-xs text-muted-foreground hover:underline shrink-0",
            ),
            _exercise_action_link(row),
            cls="flex items-center gap-2",
        ),
        P(snippet, cls="text-xs text-muted-foreground mt-0.5") if snippet else None,
        cls="py-2.5 border-b border-border/50 last:border-0",
    )


def render_exercise_list(exercises: list["ExerciseStatusRow"]) -> Div:
    """Render exercises the user is registered with, with submission/feedback status."""
    if not exercises:
        return EmptyState(
            title="No exercises yet",
            description="Exercises appear here when you enroll in a Path Step or are assigned one by a teacher.",
        )

    count_note = Span(
        f"{len(exercises)} exercise{'s' if len(exercises) != 1 else ''}",
        cls="text-xs text-muted-foreground mb-3 block",
    )
    rows = [_exercise_item(ex) for ex in exercises]
    return Div(count_note, Div(*rows))


# ============================================================================
# SUBMISSIONS FRAGMENT RENDERER
# ============================================================================

_SUB_STATUS_BADGE: dict[str, str] = {
    "submitted": "bg-blue-100 text-blue-800 border border-blue-200",
    "processing": "bg-yellow-100 text-yellow-800 border border-yellow-200",
    "completed": "bg-green-100 text-green-800 border border-green-200",
    "reviewed": "bg-violet-100 text-violet-800 border border-violet-200",
    "approved": "bg-green-100 text-green-800 border border-green-200",
    "revision_needed": "bg-amber-100 text-amber-800 border border-amber-200",
}
_SUB_STATUS_DEFAULT = "bg-muted text-muted-foreground border border-border"


def _sub_status_badge(status: str | None) -> Span:
    label = (status or "submitted").replace("_", " ").title()
    cls_base = _SUB_STATUS_BADGE.get(status or "", _SUB_STATUS_DEFAULT)
    return Span(label, cls=f"{cls_base} text-xs font-medium px-2 py-0.5 rounded-full")


def _submission_item(sub: Any) -> Div:
    """Single row for a user's exercise submission."""
    sub_uid = (
        getattr(sub, "uid", None) or sub.get("uid", "")
        if isinstance(sub, dict)
        else getattr(sub, "uid", "")
    )
    title = (
        getattr(sub, "title", None)
        or (sub.get("title") if isinstance(sub, dict) else None)
        or sub_uid
    )
    raw_status = getattr(sub, "status", None)
    from enum import Enum

    status = raw_status.value if isinstance(raw_status, Enum) else raw_status

    return Div(
        Div(
            Span(
                "Submission",
                cls="bg-sky-100 text-sky-800 border border-sky-200 text-xs font-medium px-2 py-0.5 rounded-full",
            ),
            Span(title, cls="text-sm font-medium text-foreground ml-2 mr-auto"),
            _sub_status_badge(status),
            A(
                "View →",
                href=f"/submissions/{sub_uid}",
                cls="text-xs text-primary hover:underline shrink-0",
            ),
            cls="flex items-center gap-2",
        ),
        cls="py-2.5 border-b border-border/50 last:border-0",
    )


def render_submissions_list(submissions: list[Any]) -> Div:
    """Render the user's exercise submissions for the Library Submissions tab."""
    if not submissions:
        return EmptyState(
            title="No submissions yet",
            description="Your submitted work will appear here. Submit an exercise from the Exercises tab.",
        )

    count_note = Span(
        f"{len(submissions)} submission{'s' if len(submissions) != 1 else ''}",
        cls="text-xs text-muted-foreground mb-3 block",
    )
    rows = [_submission_item(s) for s in submissions]
    return Div(count_note, Div(*rows))


# ============================================================================
# RESOURCES FRAGMENT RENDERER
# ============================================================================


def render_resource_list(resources: list[Any]) -> Div:
    """Render the Resource entity list."""
    if not resources:
        return EmptyState(
            title="No resources yet",
            description="Admin-curated content (books, talks, films) will appear here once added.",
        )

    rows = []
    for r in resources:
        author_text = r.author or ""
        year_text = f" ({r.publication_year})" if r.publication_year else ""
        attribution = f"{author_text}{year_text}".strip()

        link_btn = (
            A(
                "Open →",
                href=r.source_url,
                target="_blank",
                rel="noopener noreferrer",
                cls="text-xs text-primary hover:underline ml-auto shrink-0",
            )
            if r.source_url
            else None
        )

        row = Div(
            Div(
                _media_badge(r.media_type),
                Span(
                    r.title or r.uid,
                    cls="text-sm font-medium text-foreground ml-2",
                ),
                link_btn,
                cls="flex items-center gap-1",
            ),
            P(attribution, cls="text-xs text-muted-foreground mt-0.5") if attribution else None,
            P(
                (r.description or "")[:140] + ("…" if len(r.description or "") > 140 else ""),
                cls="text-xs text-muted-foreground mt-0.5",
            )
            if r.description
            else None,
            cls="py-2.5 border-b border-border/50 last:border-0",
        )
        rows.append(row)

    return Div(*rows)


# ============================================================================
# PAGE-LEVEL TAB COMPONENTS
# ============================================================================


def _tab_button(label: str, tab_id: str) -> Any:
    """Top-level tab button (Alpine.js state)."""
    return A(
        label,
        role="tab",
        cls="px-3 py-1.5 text-xs font-medium cursor-pointer transition-colors rounded-t border-b-2",
        **{
            ":aria-selected": f"activeTab === '{tab_id}'",
            "@click": f"activeTab = '{tab_id}'; htmx.trigger('#lib-tab-panel-{tab_id}', 'tab-activate')",
            ":class": (
                f"activeTab === '{tab_id}' "
                "? 'border-primary text-primary bg-background' "
                ": 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'"
            ),
        },
    )


def _tab_panel(tab_id: str, hx_get: str, default: bool = False) -> Div:
    """Tab panel with HTMX lazy-loaded content."""
    attrs: dict[str, str] = {
        "x-show": f"activeTab === '{tab_id}'",
        "hx-get": hx_get,
        "hx-trigger": "load" if default else "tab-activate once",
        "hx-swap": "innerHTML",
    }
    if not default:
        attrs["x-cloak"] = ""

    return Div(
        P("Loading...", cls="text-center text-muted-foreground py-4"),
        id=f"lib-tab-panel-{tab_id}",
        role="tabpanel",
        **attrs,
    )


def _library_tabs() -> Div:
    """Seven-tab library component."""
    return Div(
        Div(
            _tab_button("Exercises", "exercises"),
            _tab_button("Submissions", "submissions"),
            _tab_button("Resources", "resources"),
            _tab_button("Ku", "ku"),
            _tab_button("Path Steps", "path-steps"),
            _tab_button("Exercise Reports", "exercise-reports"),
            _tab_button("Activity Reports", "activity-reports"),
            role="tablist",
            cls="flex gap-1 border-b border-border mb-3",
        ),
        _tab_panel("exercises", "/library/exercises", default=True),
        _tab_panel("submissions", "/library/submissions"),
        _tab_panel("resources", "/library/resources"),
        _tab_panel("ku", "/library/ku"),
        _tab_panel("path-steps", "/library/path-steps"),
        _tab_panel("exercise-reports", "/reports/list"),
        _tab_panel("activity-reports", "/reports/activity-list"),
        **{"x-data": "{ activeTab: 'exercises' }"},
        cls="mt-3",
    )


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_library_ui_routes(
    _app: Any,
    rt: RouteDecorator,
    exercises_service: Any = None,
    resource_service: Any = None,
    ku_service: Any = None,
    ps_service: Any = None,
    submissions_service: Any = None,
    user_relationship_service: Any = None,
    **_kwargs: Any,
) -> RouteList:
    """Create /library hub routes.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        exercises_service: ExerciseService for fetching registered exercises
        resource_service: ResourceService for Resource listing
        ku_service: KuService for Ku listing
        ps_service: PsService for PathStep listing
        submissions_service: SubmissionsService for the Submissions tab
        user_relationship_service: UserRelationshipService for pinned Ku lookup
        **_kwargs: Ignored — accepts legacy keyword args for backwards-compatible call sites
    """

    # ========================================================================
    # LIBRARY HUB PAGE
    # ========================================================================

    @rt("/library")
    async def library_page(request: Request) -> Any:
        """Library hub: Exercises | Resources | Exercise Reports | Activity Reports.

        Public: shared curriculum content (Resources) is readable without authentication.
        Exercises tab requires authentication (user-specific group membership data).
        """
        content = Div(
            PageHeader(
                "Library",
                subtitle="Your exercises, curated resources, and learning reports",
            ),
            _library_tabs(),
        )
        return await BasePage(
            content=content,
            title="Library",
            request=request,
            active_page="library",
        )

    # ========================================================================
    # HTMX FRAGMENT: EXERCISES TAB
    # ========================================================================

    @rt("/library/exercises")
    async def library_exercises(request: Request) -> Any:
        """HTMX fragment: exercises with submission/feedback status via group membership."""
        user_uid = require_authenticated_user(request)

        if not exercises_service:
            return render_error_banner("Exercise service unavailable")

        result = await exercises_service.get_student_exercises_with_status(user_uid)
        if result.is_error:
            logger.error(f"Library: failed to load student exercises: {result.error}")
            return render_error_banner("Failed to load exercises", str(result.error))

        return render_exercise_list(result.value or [])

    # ========================================================================
    # HTMX FRAGMENT: SUBMISSIONS TAB
    # ========================================================================

    @rt("/library/submissions")
    async def library_submissions(request: Request) -> Any:
        """HTMX fragment: user's exercise submissions."""
        user_uid = require_authenticated_user(request)

        if not submissions_service:
            return render_error_banner("Submissions service unavailable")

        result = await submissions_service.list_submissions(
            user_uid, entity_type=EntityType.EXERCISE_SUBMISSION, limit=50
        )
        if result.is_error:
            logger.error(f"Library: failed to load submissions: {result.error}")
            return render_error_banner("Failed to load submissions", str(result.error))

        return render_submissions_list(result.value or [])

    # ========================================================================
    # HTMX FRAGMENT: RESOURCES TAB
    # ========================================================================

    @rt("/library/resources")
    async def library_resources(request: Request) -> Any:
        """HTMX fragment: admin-curated Resource entity list. Public: shared content."""
        if not resource_service:
            return render_error_banner("Resource service unavailable")

        result = await resource_service.list_all()
        if result.is_error:
            logger.error(f"Library: failed to load Resources: {result.error}")
            return render_error_banner("Failed to load resources", str(result.error))

        return render_resource_list(result.value or [])

    # ========================================================================
    # HTMX FRAGMENT: KU TAB
    # ========================================================================

    @rt("/library/ku")
    async def library_ku(request: Request) -> Any:
        """HTMX fragment: Ku the user has bookmarked (PINNED relationship)."""
        if not ku_service:
            return render_error_banner("Knowledge service unavailable")

        user = get_current_user(request)
        if not user:
            return EmptyState(
                title="Sign in to see your bookmarked Ku",
                description="Bookmark Ku on the Knowledge page to track what matters to you.",
            )

        # Resolve pinned UIDs
        pinned_uids: set[str] = set()
        if user_relationship_service:
            pins_result = await user_relationship_service.get_pinned_entities(user)
            if not pins_result.is_error:
                pinned_uids = set(pins_result.value or [])

        if not pinned_uids:
            return EmptyState(
                title="No bookmarked Ku yet",
                description="Pin Ku on the Knowledge page to track what matters to you.",
            )

        # Fetch all Kus and filter to pinned
        result = await ku_service.core.list(limit=500)
        if result.is_error:
            logger.error(f"Library: failed to load Kus: {result.error}")
            return render_error_banner("Failed to load knowledge units", str(result.error))

        kus = [ku for ku in (result.value or []) if ku.uid in pinned_uids]
        if not kus:
            return EmptyState(
                title="No bookmarked Ku yet",
                description="Pin Ku on the Knowledge page to track what matters to you.",
            )

        count_note = Span(
            f"{len(kus)} bookmarked Ku",
            cls="text-xs text-muted-foreground mb-3 block",
        )
        rows = [
            Div(
                Div(
                    Span("Ku", cls=_KU_BADGE_CLS),
                    A(
                        getattr(ku, "title", ku.uid),
                        href=f"/ku/{ku.uid}",
                        cls="text-sm font-medium text-foreground hover:text-primary hover:underline ml-2",
                    ),
                    cls="flex items-center",
                ),
                P(
                    (getattr(ku, "description", "") or "")[:120]
                    + ("…" if len(getattr(ku, "description", "") or "") > 120 else ""),
                    cls="text-xs text-muted-foreground mt-0.5 ml-0",
                )
                if getattr(ku, "description", None)
                else None,
                cls="py-2.5 border-b border-border/50 last:border-0",
            )
            for ku in kus
        ]
        return Div(count_note, Div(*rows))

    # ========================================================================
    # HTMX FRAGMENT: PATH STEPS TAB
    # ========================================================================

    @rt("/library/path-steps")
    async def library_path_steps(request: Request) -> Any:
        """HTMX fragment: Path Steps the user is enrolled in (IN_PROGRESS)."""
        if not ps_service:
            return render_error_banner("Path Steps service unavailable")

        user = get_current_user(request)
        if not user:
            return EmptyState(
                title="Sign in to see your enrolled Path Steps",
                description="Start a Path Step on the Path Steps page to track your progress here.",
            )

        # Resolve enrolled UIDs
        enrolled_uids: set[str] = set()
        uids_result = await ps_service.mastery.get_in_progress_step_uids(user)
        if not uids_result.is_error:
            enrolled_uids = set(uids_result.value or [])

        if not enrolled_uids:
            return EmptyState(
                title="No enrolled Path Steps yet",
                description="Start a Path Step on the Path Steps page to track your progress here.",
            )

        # Fetch all steps and filter to enrolled
        result = await ps_service.core.list(limit=200)
        if result.is_error:
            logger.error(f"Library: failed to load PathSteps: {result.error}")
            return render_error_banner("Failed to load path steps", str(result.error))

        raw = result.value or []
        all_steps = raw if isinstance(raw, list) else raw[0]
        steps = [s for s in all_steps if s.uid in enrolled_uids]
        if not steps:
            return EmptyState(
                title="No enrolled Path Steps yet",
                description="Start a Path Step on the Path Steps page to track your progress here.",
            )

        count_note = Span(
            f"{len(steps)} enrolled path step{'s' if len(steps) != 1 else ''}",
            cls="text-xs text-muted-foreground mb-3 block",
        )
        rows = [
            Div(
                Div(
                    Span("Path Step", cls=_PS_BADGE_CLS),
                    A(
                        getattr(step, "title", step.uid),
                        href=f"/path-steps/{step.uid}/details",
                        cls="text-sm font-medium text-foreground hover:text-primary hover:underline ml-2",
                    ),
                    cls="flex items-center",
                ),
                P(
                    (getattr(step, "description", "") or "")[:120]
                    + ("…" if len(getattr(step, "description", "") or "") > 120 else ""),
                    cls="text-xs text-muted-foreground mt-0.5 ml-0",
                )
                if getattr(step, "description", None)
                else None,
                cls="py-2.5 border-b border-border/50 last:border-0",
            )
            for step in steps
        ]
        return Div(count_note, Div(*rows))

    return []
