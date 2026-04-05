"""
Library UI Route — /library
============================

Unified learning hub with sidebar navigation:

- Exercises   — Exercises assigned via group membership, with submission/feedback status
- Resources   — Admin-curated content (books, talks, films, podcasts)
- Ku          — User's bookmarked knowledge units
- Path Steps  — User's enrolled path steps

Each section is a standalone route wrapped in SidebarPage.
Dual-purpose: returns fragment for HTMX requests, full sidebar page for direct navigation.

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from fasthtml.common import A, Div, P, Span

from adapters.inbound.auth import get_current_user, require_authenticated_user
from adapters.inbound.fasthtml_types import Request, RouteDecorator
from core.models.enums.entity_enums import EntityType
from core.utils.logging import get_logger
from ui.buttons import ButtonLink, ButtonT
from ui.feedback import Badge, BadgeT, StatusBadge
from ui.layout import Size
from ui.learning_loop.exercise_status import (
    exercise_status_badge,
    exercise_status_key,
    render_exercise_list,
)
from ui.library.nav import render_library_sidebar_page
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_error_banner
from ui.patterns.hub import HubPreviewCard, HubPreviewEmpty, HubPreviewGrid

logger = get_logger("skuel.routes.library")


# ============================================================================
# TYPE BADGE HELPERS
# ============================================================================

_MEDIA_BADGE_MAP: dict[str, tuple[BadgeT | None, str]] = {
    "book": (BadgeT.success, ""),
    "talk": (BadgeT.info, ""),
    "film": (None, "bg-purple-100 text-purple-800 border-purple-200"),
    "podcast": (None, "bg-orange-100 text-orange-800 border-orange-200"),
    "article": (BadgeT.warning, ""),
    "music": (None, "bg-pink-100 text-pink-800 border-pink-200"),
}


def _media_badge(media_type: str | None) -> Any:
    """Colored pill badge showing resource media type."""
    label = (media_type or "content").title()
    variant, custom_cls = _MEDIA_BADGE_MAP.get(media_type or "", (BadgeT.neutral, ""))
    return Badge(label, variant=variant, cls=custom_cls, size=Size.sm)


# ============================================================================
# SUBMISSIONS FRAGMENT RENDERER
# ============================================================================

# Submission statuses that are valid EntityStatus values
_ENTITY_STATUSES = {"submitted", "processing", "completed"}

_EXTRA_STATUS_MAP: dict[str, tuple[str, BadgeT | None, str]] = {
    "reviewed": ("Reviewed", BadgeT.accent, ""),
    "approved": ("Approved", BadgeT.success, ""),
    "revision_needed": (
        "Revision Needed",
        None,
        "bg-amber-100 text-amber-800 border-amber-200",
    ),
}


def _sub_status_badge(status: str | None) -> Any:
    s = status or "submitted"
    if s in _ENTITY_STATUSES:
        return StatusBadge(s, size=Size.sm)
    label, variant, custom_cls = _EXTRA_STATUS_MAP.get(
        s, (s.replace("_", " ").title(), BadgeT.neutral, "")
    )
    return Badge(label, variant=variant, cls=custom_cls, size=Size.sm)


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
            Badge(
                "Submission",
                variant=None,
                cls="bg-sky-100 text-sky-800 border-sky-200",
                size=Size.sm,
            ),
            Span(title, cls="text-sm font-medium text-foreground ml-2 mr-auto"),
            _sub_status_badge(status),
            ButtonLink(
                "View →",
                href=f"/gradebook/{sub_uid}",
                variant=ButtonT.ghost,
                size=Size.sm,
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
            ButtonLink(
                "Open →",
                href=r.source_url,
                target="_blank",
                rel="noopener noreferrer",
                variant=ButtonT.ghost,
                size=Size.sm,
                cls="ml-auto",
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
) -> None:
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
    async def library_hub(request: Request) -> Any:
        """Library hub — entry point with container navigation, no sidebar."""
        require_authenticated_user(request)
        from ui.layouts.base_page import BasePage
        from ui.library.hub import LibraryHub

        return await BasePage(
            content=LibraryHub(),
            title="Library",
            request=request,
            active_page="library",
        )

    # ========================================================================
    # HTMX FRAGMENT: EXERCISES TAB
    # ========================================================================

    @rt("/library/exercises")
    async def library_exercises(request: Request) -> Any:
        """Exercises with submission/feedback status via group membership."""
        user_uid = require_authenticated_user(request)

        if not exercises_service:
            fragment = render_error_banner("Exercise service unavailable")
        else:
            result = await exercises_service.get_student_exercises_with_status(user_uid)
            if result.is_error:
                logger.error(f"Library: failed to load student exercises: {result.error}")
                fragment = render_error_banner("Failed to load exercises", str(result.error))
            else:
                fragment = render_exercise_list(result.value or [])

        if request.headers.get("HX-Request"):
            return fragment
        return await render_library_sidebar_page(
            content=Div(fragment), active="exercises", request=request
        )

    # ========================================================================
    # HTMX FRAGMENT: SUBMISSIONS TAB
    # ========================================================================

    @rt("/library/submissions")
    async def library_submissions(request: Request) -> Any:
        """User's exercise submissions."""
        user_uid = require_authenticated_user(request)

        if not submissions_service:
            fragment = render_error_banner("Submissions service unavailable")
        else:
            result = await submissions_service.list_submissions(
                user_uid, entity_type=EntityType.EXERCISE_SUBMISSION, limit=50
            )
            if result.is_error:
                logger.error(f"Library: failed to load submissions: {result.error}")
                fragment = render_error_banner("Failed to load submissions", str(result.error))
            else:
                fragment = render_submissions_list(result.value or [])

        if request.headers.get("HX-Request"):
            return fragment
        return await render_library_sidebar_page(
            content=Div(fragment), active="exercises", request=request
        )

    # ========================================================================
    # HTMX FRAGMENT: RESOURCES TAB
    # ========================================================================

    @rt("/library/resources")
    async def library_resources(request: Request) -> Any:
        """Admin-curated Resource entity list. Public: shared content."""
        if not resource_service:
            fragment = render_error_banner("Resource service unavailable")
        else:
            result = await resource_service.list_all()
            if result.is_error:
                logger.error(f"Library: failed to load Resources: {result.error}")
                fragment = render_error_banner("Failed to load resources", str(result.error))
            else:
                fragment = render_resource_list(result.value or [])

        if request.headers.get("HX-Request"):
            return fragment
        return await render_library_sidebar_page(
            content=Div(fragment), active="resources", request=request
        )

    # ========================================================================
    # HTMX FRAGMENT: KU TAB
    # ========================================================================

    @rt("/library/ku")
    async def library_ku(request: Request) -> Any:
        """Ku the user has bookmarked (PINNED relationship)."""
        if not ku_service:
            fragment = render_error_banner("Knowledge service unavailable")
        else:
            user = get_current_user(request)
            if not user:
                fragment = EmptyState(
                    title="Sign in to see your bookmarked Ku",
                    description="Bookmark Ku on the Knowledge page to track what matters to you.",
                )
            else:
                fragment = await _build_ku_fragment(user)

        if request.headers.get("HX-Request"):
            return fragment
        return await render_library_sidebar_page(
            content=Div(fragment), active="ku", request=request
        )

    async def _build_ku_fragment(user: str) -> Any:
        """Build the Ku bookmarks fragment content."""
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

        # Fetch only the pinned Kus by UID
        result = await ku_service.core.backend.get_many(list(pinned_uids))  # type: ignore[union-attr]
        if result.is_error:
            logger.error(f"Library: failed to load Kus: {result.error}")
            return render_error_banner("Failed to load knowledge units", str(result.error))

        kus = [ku for ku in (result.value or []) if ku is not None]
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
                    Badge("Ku", variant=BadgeT.accent, size=Size.sm),
                    A(
                        getattr(ku, "title", ku.uid),
                        href=f"/explore/ku/{ku.uid}",
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
        """Path Steps the user is enrolled in (IN_PROGRESS)."""
        if not ps_service:
            fragment = render_error_banner("Path Steps service unavailable")
        else:
            user = get_current_user(request)
            if not user:
                fragment = EmptyState(
                    title="Sign in to see your enrolled Path Steps",
                    description="Start a Path Step on the Path Steps page to track your progress here.",
                )
            else:
                fragment = await _build_path_steps_fragment(user)

        if request.headers.get("HX-Request"):
            return fragment
        return await render_library_sidebar_page(
            content=Div(fragment), active="path-steps", request=request
        )

    async def _build_path_steps_fragment(user: str) -> Any:
        """Build the enrolled Path Steps fragment content."""
        # Resolve enrolled UIDs
        enrolled_uids: set[str] = set()
        uids_result = await ps_service.mastery.get_in_progress_step_uids(user)  # type: ignore[union-attr]
        if not uids_result.is_error:
            enrolled_uids = set(uids_result.value or [])

        if not enrolled_uids:
            return EmptyState(
                title="No enrolled Path Steps yet",
                description="Start a Path Step on the Path Steps page to track your progress here.",
            )

        # Fetch only the enrolled PathSteps by UID
        result = await ps_service.core.backend.get_many(list(enrolled_uids))  # type: ignore[union-attr]
        if result.is_error:
            logger.error(f"Library: failed to load PathSteps: {result.error}")
            return render_error_banner("Failed to load path steps", str(result.error))

        steps = [s for s in (result.value or []) if s is not None]
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
                    Badge(
                        "Path Step",
                        variant=None,
                        cls="bg-teal-100 text-teal-800 border-teal-200",
                        size=Size.sm,
                    ),
                    A(
                        getattr(step, "title", step.uid),
                        href=f"/explore/ps/{step.uid}",
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

    # ========================================================================
    # HUB PREVIEW ENDPOINTS (HTMX lazy-loaded from /library hub)
    # ========================================================================

    @rt("/api/library/exercises/preview")
    async def library_exercises_preview(request: Request) -> Any:
        """HTMX fragment: top 3 exercises with status pill for hub preview."""
        user_uid = require_authenticated_user(request)
        if not exercises_service:
            return HubPreviewEmpty("exercises")
        result = await exercises_service.get_student_exercises_with_status(user_uid)
        if result.is_error:
            return HubPreviewEmpty("exercises")
        rows = result.value or []
        if not rows:
            return HubPreviewEmpty("exercises")
        cards = []
        for row in rows[:3]:
            status_key = exercise_status_key(row)
            badge = exercise_status_badge(status_key)
            cards.append(
                HubPreviewCard(
                    title=row["title"] or row["uid"],
                    href=f"/exercises/get?uid={row['uid']}",
                    badge=badge,
                )
            )
        return HubPreviewGrid(cards)

    @rt("/api/library/resources/preview")
    async def library_resources_preview(request: Request) -> Any:
        """HTMX fragment: top 3 resources with media badge for hub preview."""
        if not resource_service:
            return HubPreviewEmpty("resources")
        result = await resource_service.list_all()
        if result.is_error:
            return HubPreviewEmpty("resources")
        resources = result.value or []
        if not resources:
            return HubPreviewEmpty("resources")
        cards = []
        for res in resources[:3]:
            media_type = getattr(res, "media_type", None)
            badge = _media_badge(media_type) if media_type else None
            cards.append(
                HubPreviewCard(
                    title=getattr(res, "title", res.uid) or res.uid,
                    href="/library/resources",
                    badge=badge,
                )
            )
        return HubPreviewGrid(cards)

    @rt("/api/library/ku/preview")
    async def library_ku_preview(request: Request) -> Any:
        """HTMX fragment: top 3 bookmarked Ku for hub preview."""
        user = get_current_user(request)
        if not user or not ku_service or not user_relationship_service:
            return HubPreviewEmpty("bookmarked Ku")
        pins_result = await user_relationship_service.get_pinned_entities(user)
        if pins_result.is_error:
            return HubPreviewEmpty("bookmarked Ku")
        pinned_uids = list(pins_result.value or [])
        if not pinned_uids:
            return HubPreviewEmpty("bookmarked Ku")
        result = await ku_service.core.backend.get_many(pinned_uids[:3])  # type: ignore[union-attr]
        if result.is_error:
            return HubPreviewEmpty("bookmarked Ku")
        kus = [ku for ku in (result.value or []) if ku is not None]
        if not kus:
            return HubPreviewEmpty("bookmarked Ku")
        cards = [
            HubPreviewCard(
                title=getattr(ku, "title", ku.uid) or ku.uid,
                href=f"/explore/ku/{ku.uid}",
                badge=Badge("Ku", variant=BadgeT.accent, size=Size.sm),
            )
            for ku in kus[:3]
        ]
        return HubPreviewGrid(cards)

    @rt("/api/library/path-steps/preview")
    async def library_path_steps_preview(request: Request) -> Any:
        """HTMX fragment: top 3 enrolled path steps for hub preview."""
        user = get_current_user(request)
        if not user or not ps_service:
            return HubPreviewEmpty("enrolled path steps")
        uids_result = await ps_service.mastery.get_in_progress_step_uids(user)  # type: ignore[union-attr]
        if uids_result.is_error:
            return HubPreviewEmpty("enrolled path steps")
        enrolled_uids = list(uids_result.value or [])
        if not enrolled_uids:
            return HubPreviewEmpty("enrolled path steps")
        result = await ps_service.core.backend.get_many(enrolled_uids[:3])  # type: ignore[union-attr]
        if result.is_error:
            return HubPreviewEmpty("enrolled path steps")
        steps = [s for s in (result.value or []) if s is not None]
        if not steps:
            return HubPreviewEmpty("enrolled path steps")
        cards = [
            HubPreviewCard(
                title=getattr(step, "title", step.uid) or step.uid,
                href=f"/explore/ps/{step.uid}",
                badge=Badge(
                    "Path Step",
                    variant=None,
                    cls="bg-teal-100 text-teal-800 border-teal-200",
                    size=Size.sm,
                ),
            )
            for step in steps[:3]
        ]
        return HubPreviewGrid(cards)
