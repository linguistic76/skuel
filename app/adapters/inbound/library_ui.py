"""
Library UI Route — /library
============================

Unified learning hub with sidebar navigation:

- Exercises   — Exercises assigned via group membership, with submission/feedback status
- Resources   — Admin-curated content (books, talks, films, podcasts)
- Ku          — User's bookmarked knowledge units
- Path Steps  — User's enrolled path steps

Each section is a standalone route wrapped in SidebarPage.
Most tabs use dual-mode (fragment + full page); Path Steps uses shell-first.

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import A, Div, P, Span

from adapters.inbound.auth import get_current_user, require_authenticated_user
from adapters.inbound.fasthtml_types import Request, RouteDecorator
from adapters.inbound.result_helpers import require_found
from core.models.type_hints import UserUID
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.models.user_entry.user_entry import UserEntry
    from core.orchestrator.library_orchestrator import LibraryOrchestrator
from ui.components import ButtonT
from ui.feedback import Badge, BadgeT, StatusBadge
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.learning_loop.exercise_status import (
    exercise_status_badge,
    exercise_status_key,
    render_exercise_list,
)
from ui.library.media_badge import media_badge
from ui.library.nav import render_library_sidebar_page
from ui.library.resource_detail import render_resource_detail, render_resource_not_found
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_error_banner
from ui.patterns.hub import HubPreviewCard, HubPreviewEmpty, HubPreviewGrid, MocCard
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.page_header import PageHeader
from ui.primitives import ButtonLink

logger = get_logger("skuel.routes.library")


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


def _submission_item(sub: "UserEntry") -> Div:
    """Single row for a user's exercise submission."""
    status = sub.status.value

    return Div(
        Div(
            Badge(
                "Submission",
                variant=None,
                cls="bg-sky-100 text-sky-800 border-sky-200",
                size=Size.sm,
            ),
            Span(sub.title or sub.uid, cls="text-sm font-medium text-foreground ml-2 mr-auto"),
            _sub_status_badge(status),
            ButtonLink(
                "View →",
                href=f"/gradebook/{sub.uid}",
                cls=ButtonT.ghost,
                size="sm",
            ),
            cls="flex items-center gap-2",
        ),
        cls="py-2.5 border-b border-border/50 last:border-0",
    )


def render_submissions_list(submissions: "list[UserEntry]") -> Div:
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

    from ui.primitives import safe_external_url

    rows = []
    for r in resources:
        author_text = r.author or ""
        year_text = f" ({r.publication_year})" if r.publication_year else ""
        attribution = f"{author_text}{year_text}".strip()

        # Scheme-allowlisted: a javascript:/data: source_url gets no link.
        safe_url = safe_external_url(r.source_url)
        link_btn = (
            ButtonLink(
                "Open →",
                href=safe_url,
                target="_blank",
                rel="noopener noreferrer",
                cls=(ButtonT.ghost, "ml-auto"),
                size="sm",
            )
            if safe_url
            else None
        )

        row = Div(
            Div(
                media_badge(r.media_type),
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
    orchestrator: "LibraryOrchestrator",
) -> None:
    """Create /library hub routes.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        orchestrator: LibraryOrchestrator for unified access to services
    """

    # ========================================================================
    # LIBRARY MOC ROOT
    # ========================================================================

    @rt("/library")
    async def library_moc(request: Request) -> Any:
        """Library MOC — links to all 4 sub-pages, no sidebar."""
        require_authenticated_user(request)

        content = Div(
            PageHeader("Library", subtitle="Browse your learning content and resources"),
            Div(
                MocCard(
                    "Exercises",
                    "Exercises assigned via group membership, with submission and feedback status.",
                    "/library/exercises",
                    "book-open",
                    "bg-blue-50",
                ),
                MocCard(
                    "Resources",
                    "Admin-curated content — books, talks, films, podcasts, and articles.",
                    "/library/resources",
                    "bookmark",
                    "bg-amber-50",
                ),
                MocCard(
                    "Ku",
                    "Your bookmarked atomic knowledge units from the curriculum graph.",
                    "/library/ku",
                    "brain",
                    "bg-violet-50",
                ),
                MocCard(
                    "Path Steps",
                    "Your enrolled path steps — structured learning content and exercises.",
                    "/library/path-steps",
                    "map",
                    "bg-emerald-50",
                ),
                cls="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-6",
            ),
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
        """Exercises with submission/feedback status via group membership."""
        user_uid = require_authenticated_user(request)

        result = await orchestrator.get_student_exercises_with_status(user_uid)
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

        result = await orchestrator.list_exercise_submissions(user_uid)
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
        result = await orchestrator.list_resources()
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
    # RESOURCE DETAIL — the citation click destination
    # ========================================================================

    @rt("/library/resources/get")
    async def library_resource_detail(request: Request, uid: str = "") -> Any:
        """Per-Resource descriptor page — the citation click destination.

        PUBLIC read: Resource is SHARED/CURATED content, so this matches the
        /library/resources list (no auth gate). The chips that link here live on
        public PathStep/Ku pages, so the destination must be public too.

        Full-page navigation (the chip is a plain <a href>), not an HTMX
        fragment — reading-first BasePage matching /explore/ku and /explore/ps.
        """
        found = require_found(await orchestrator.get_resource(uid), "Resource", uid)
        if found.is_error:
            logger.info("Library: resource detail miss for uid=%s", uid)
            content: Any = render_resource_not_found(uid)
        else:
            # Reverse-traverse CITES_RESOURCE for the "Cited by" section. A citer
            # fetch error must not 500 the page — degrade to no section.
            cited = await orchestrator.get_citing_entities(uid)
            if cited.is_error:
                logger.info("Library: cited-by fetch failed for uid=%s", uid)
            cited_by = cited.value if not cited.is_error else []
            content = render_resource_detail(found.value, cited_by=cited_by)

        return await BasePage(
            content=content,
            title="Resource",
            page_type=PageType.CUSTOM,
            request=request,
            active_page="library",
        )

    # ========================================================================
    # HTMX FRAGMENT: KU TAB
    # ========================================================================

    @rt("/library/ku")
    async def library_ku(request: Request) -> Any:
        """Ku the user has bookmarked (PINNED relationship)."""
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

    async def _build_ku_fragment(user: UserUID) -> Any:
        """Build the Ku bookmarks fragment content."""
        result = await orchestrator.get_bookmarked_kus(user)
        if result.is_error:
            logger.error(f"Library: failed to load Kus: {result.error}")
            return render_error_banner("Failed to load knowledge units", str(result.error))

        kus = result.value or []
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
        """Path Steps the user is enrolled in — shell renders immediately, content loads via HTMX."""
        return await render_library_sidebar_page(
            content=Div(
                content_loading_placeholder(
                    "/library/path-steps/content",
                    "library-path-steps-content",
                    loading_text="Loading path steps...",
                )
            ),
            active="path-steps",
            request=request,
        )

    @rt("/library/path-steps/content")
    async def library_path_steps_content(request: Request) -> Any:
        """HTMX fragment: enrolled Path Steps content."""
        user = get_current_user(request)
        if not user:
            return EmptyState(
                title="Sign in to see your enrolled Path Steps",
                description="Start a Path Step on the Path Steps page to track your progress here.",
            )
        return await _build_path_steps_fragment(user)

    async def _build_path_steps_fragment(user: UserUID) -> Any:
        """Build the enrolled Path Steps fragment content."""
        result = await orchestrator.get_enrolled_path_steps(user)
        if result.is_error:
            logger.error(f"Library: failed to load PathSteps: {result.error}")
            return render_error_banner("Failed to load path steps", str(result.error))

        steps = result.value or []
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
        result = await orchestrator.get_student_exercises_with_status(user_uid, limit=3)
        if result.is_error:
            return HubPreviewEmpty("exercises")
        rows = result.value or []
        if not rows:
            return HubPreviewEmpty("exercises")
        cards = []
        for row in rows:
            status_key = exercise_status_key(row)
            badge = exercise_status_badge(status_key)
            cards.append(
                HubPreviewCard(
                    title=row["title"] or row["uid"],
                    href=f"/exercises/get?uid={row['uid']}",
                    badge=badge,
                    description=row["description"],
                )
            )
        return HubPreviewGrid(cards)

    @rt("/api/library/resources/preview")
    async def library_resources_preview(request: Request) -> Any:
        """HTMX fragment: top 3 resources with media badge for hub preview."""
        result = await orchestrator.list_resources(limit=3)
        if result.is_error:
            return HubPreviewEmpty("resources")
        resources = result.value or []
        if not resources:
            return HubPreviewEmpty("resources")
        cards = []
        for res in resources:
            media_type = getattr(res, "media_type", None)
            badge = media_badge(media_type) if media_type else None
            cards.append(
                HubPreviewCard(
                    title=getattr(res, "title", res.uid) or res.uid,
                    href="/library/resources",
                    badge=badge,
                    description=res.description or res.summary,
                )
            )
        return HubPreviewGrid(cards)

    @rt("/api/library/ku/preview")
    async def library_ku_preview(request: Request) -> Any:
        """HTMX fragment: top 3 bookmarked Ku for hub preview."""
        user = get_current_user(request)
        if not user:
            return HubPreviewEmpty("bookmarked Ku")
        result = await orchestrator.get_bookmarked_kus(user, limit=3)
        if result.is_error:
            return HubPreviewEmpty("bookmarked Ku")
        kus = result.value or []
        if not kus:
            return HubPreviewEmpty("bookmarked Ku")
        cards = [
            HubPreviewCard(
                title=getattr(ku, "title", ku.uid) or ku.uid,
                href=f"/explore/ku/{ku.uid}",
                description=ku.description or ku.summary,
            )
            for ku in kus[:3]
        ]
        return HubPreviewGrid(cards)

    @rt("/api/library/path-steps/preview")
    async def library_path_steps_preview(request: Request) -> Any:
        """HTMX fragment: top 3 enrolled path steps for hub preview."""
        user = get_current_user(request)
        if not user:
            return HubPreviewEmpty("enrolled path steps")
        result = await orchestrator.get_enrolled_path_steps(user, limit=3)
        if result.is_error:
            return HubPreviewEmpty("enrolled path steps")
        steps = result.value or []
        if not steps:
            return HubPreviewEmpty("enrolled path steps")
        cards = [
            HubPreviewCard(
                title=getattr(step, "title", step.uid) or step.uid,
                href=f"/explore/ps/{step.uid}",
                description=step.description or step.summary,
            )
            for step in steps[:3]
        ]
        return HubPreviewGrid(cards)
