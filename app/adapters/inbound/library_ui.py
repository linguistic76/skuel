"""
Library UI Route — /library
============================

Unified learning hub with four tabs:

- Curriculum   — Ku + PathStep + Exercise, flat list with type badges,
                 Alpine.js client-side toggle filter (All | Ku | Path Steps | Exercises)
- Resources    — Admin-curated content (books, talks, films, podcasts)
- Exercise Reports — Teacher/AI feedback (reuses /reports/list fragment)
- Activity Reports — Activity domain analysis (reuses /reports/activity-list fragment)

HTMX fragment endpoints:
  GET /library/curriculum  — combined curriculum list (served to Curriculum tab)
  GET /library/resources   — Resource entity list (served to Resources tab)

Tab content for Exercise Reports and Activity Reports is HTMX-loaded from
existing fragment endpoints in exercise_reports_ui.py and activity_reports_ui.py.

See: /docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md
"""

from typing import Any

from fasthtml.common import A, Button, Div, P, Span

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request, RouteDecorator, RouteList
from core.utils.logging import get_logger
from ui.layouts.base_page import BasePage
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_error_banner
from ui.patterns.page_header import PageHeader

logger = get_logger("skuel.routes.library")


# ============================================================================
# TYPE BADGE HELPERS
# ============================================================================

# CSS classes per entity type — colour-coded for visual discrimination
_TYPE_BADGE_CLS: dict[str, str] = {
    "ku": "bg-blue-100 text-blue-800 border border-blue-200 text-xs font-medium px-2 py-0.5 rounded-full",
    "path_step": "bg-purple-100 text-purple-800 border border-purple-200 text-xs font-medium px-2 py-0.5 rounded-full",
    "exercise": "bg-amber-100 text-amber-800 border border-amber-200 text-xs font-medium px-2 py-0.5 rounded-full",
}

_TYPE_LABELS: dict[str, str] = {
    "ku": "Ku",
    "path_step": "Path Step",
    "exercise": "Exercise",
}

_MEDIA_BADGE_CLS: dict[str, str] = {
    "book": "bg-green-100 text-green-800 border border-green-200",
    "talk": "bg-blue-100 text-blue-800 border border-blue-200",
    "film": "bg-purple-100 text-purple-800 border border-purple-200",
    "podcast": "bg-orange-100 text-orange-800 border border-orange-200",
    "article": "bg-yellow-100 text-yellow-800 border border-yellow-200",
    "music": "bg-pink-100 text-pink-800 border border-pink-200",
}
_MEDIA_BADGE_DEFAULT = "bg-muted text-muted-foreground border border-border"


def _type_badge(entity_type: str) -> Span:
    """Colored pill badge showing entity type."""
    cls = _TYPE_BADGE_CLS.get(entity_type, _TYPE_BADGE_CLS["ku"])
    label = _TYPE_LABELS.get(entity_type, entity_type.replace("_", " ").title())
    return Span(label, cls=cls)


def _media_badge(media_type: str | None) -> Span:
    """Colored pill badge showing resource media type."""
    label = (media_type or "content").title()
    base_cls = _MEDIA_BADGE_CLS.get(media_type or "", _MEDIA_BADGE_DEFAULT)
    return Span(label, cls=f"{base_cls} text-xs font-medium px-2 py-0.5 rounded-full border")


# ============================================================================
# CURRICULUM FRAGMENT RENDERER
# ============================================================================


def _curriculum_item(
    uid: str,
    title: str,
    description: str | None,
    entity_type: str,
    detail_href: str,
) -> Div:
    """Single row in the curriculum list.

    Uses data-type for Alpine.js x-show filter without JavaScript arrays.
    """
    snippet = (description or "")[:120]
    if len(description or "") > 120:
        snippet += "…"

    return Div(
        Div(
            _type_badge(entity_type),
            A(
                title,
                href=detail_href,
                cls="text-sm font-medium text-foreground hover:text-primary hover:underline ml-2",
            ),
            cls="flex items-center",
        ),
        P(snippet, cls="text-xs text-muted-foreground mt-0.5 ml-0") if snippet else None,
        cls="py-2.5 border-b border-border/50 last:border-0",
        **{
            "data-type": entity_type,
            "x-show": "activeFilter === 'all' || $el.dataset.type === activeFilter",
        },
    )


def _filter_toggle(label: str, value: str, badge_cls: str) -> Button:
    """Toggle button for the type filter row."""
    active_cls = "ring-2 ring-offset-1 ring-primary/40 bg-accent"
    inactive_cls = "hover:bg-accent/60"
    return Button(
        Span(label, cls="text-xs font-medium"),
        type="button",
        cls=f"flex items-center gap-1.5 px-3 py-1 rounded-full border border-border transition-all {inactive_cls}",
        **{
            "@click": f"activeFilter = '{value}'",
            ":class": f"activeFilter === '{value}' ? '{active_cls}' : '{inactive_cls}'",
        },
    )


def render_curriculum_list(kus: list[Any], path_steps: list[Any], exercises: list[Any]) -> Div:
    """
    Render the combined curriculum list with Alpine.js type filter.

    Shows only the user's bookmarked Kus (max 5), enrolled PathSteps (max 2),
    and exercises associated with those PathSteps.

    All three entity types are rendered together; the filter toggles control
    visibility client-side — no extra server round-trips on filter change.
    """
    if not kus and not path_steps and not exercises:
        return EmptyState(
            title="No personal curriculum yet",
            description="Mark up to 5 Kus as studying and enrol in up to 2 Path Steps to see them here.",
        )

    filter_row = Div(
        _filter_toggle("All", "all", ""),
        _filter_toggle("Ku", "ku", _TYPE_BADGE_CLS["ku"]),
        _filter_toggle("Path Steps", "path_step", _TYPE_BADGE_CLS["path_step"]),
        _filter_toggle("Exercises", "exercise", _TYPE_BADGE_CLS["exercise"]),
        cls="flex gap-2 mb-4 flex-wrap",
    )

    ku_items = [
        _curriculum_item(
            uid=ku.uid,
            title=ku.title or ku.uid,
            description=ku.description,
            entity_type="ku",
            detail_href=f"/ku/{ku.uid}",
        )
        for ku in kus
    ]

    ps_items = [
        _curriculum_item(
            uid=ps.uid,
            title=ps.title or ps.uid,
            description=ps.description,
            entity_type="path_step",
            detail_href=f"/path-steps/get?uid={ps.uid}",
        )
        for ps in path_steps
    ]

    ex_items = [
        _curriculum_item(
            uid=ex["uid"],
            title=ex.get("title") or ex["uid"],
            description=ex.get("description"),
            entity_type="exercise",
            detail_href=f"/exercises/get?uid={ex['uid']}",
        )
        for ex in exercises
    ]

    total = len(ku_items) + len(ps_items) + len(ex_items)
    count_note = Span(
        f"{total} items — {len(ku_items)} Ku · {len(ps_items)} Path Steps · {len(ex_items)} Exercises",
        cls="text-xs text-muted-foreground mb-3 block",
    )

    return Div(
        count_note,
        filter_row,
        Div(*ku_items, *ps_items, *ex_items),
        **{"x-data": "{ activeFilter: 'all' }"},
    )


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
    """Four-tab library component."""
    return Div(
        Div(
            _tab_button("Curriculum", "curriculum"),
            _tab_button("Resources", "resources"),
            _tab_button("Exercise Reports", "exercise-reports"),
            _tab_button("Activity Reports", "activity-reports"),
            role="tablist",
            cls="flex gap-1 border-b border-border mb-3",
        ),
        _tab_panel("curriculum", "/library/curriculum", default=True),
        _tab_panel("resources", "/library/resources"),
        _tab_panel("exercise-reports", "/reports/list"),
        _tab_panel("activity-reports", "/reports/activity-list"),
        **{"x-data": "{ activeTab: 'curriculum' }"},
        cls="mt-3",
    )


# ============================================================================
# ROUTE CREATION
# ============================================================================


def create_library_ui_routes(
    _app: Any,
    rt: RouteDecorator,
    ku_service: Any = None,
    ps_service: Any = None,
    exercises_service: Any = None,
    resource_service: Any = None,
    user_service: Any = None,
) -> RouteList:
    """Create /library hub routes.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        ku_service: KuService for Ku listing
        ps_service: PsService for PathStep listing
        exercises_service: ExerciseService for Exercise listing
        resource_service: ResourceService for Resource listing
        user_service: UserService for building UserContext (bookmarks + enrollments)
    """

    # ========================================================================
    # LIBRARY HUB PAGE
    # ========================================================================

    @rt("/library")
    async def library_page(request: Request) -> Any:
        """Library hub: Curriculum | Resources | Exercise Reports | Activity Reports."""
        require_authenticated_user(request)
        content = Div(
            PageHeader(
                "Library",
                subtitle="Curriculum, curated resources, and your learning reports",
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
    # HTMX FRAGMENT: CURRICULUM TAB
    # ========================================================================

    @rt("/library/curriculum")
    async def library_curriculum(request: Request) -> Any:
        """HTMX fragment: user's bookmarked Kus + enrolled PathSteps + associated Exercises."""
        user_uid = require_authenticated_user(request)

        kus: list[Any] = []
        path_steps: list[Any] = []
        exercises: list[Any] = []

        # --- Resolve user's studying Ku UIDs and enrolled PathStep UIDs ---
        studying_ku_uids: list[str] = []
        enrolled_ps_uids: list[str] = []

        if user_service:
            ctx_result = await user_service.get_rich_unified_context(user_uid)
            if ctx_result.is_error:
                logger.error(f"Library: failed to load user context: {ctx_result.error}")
            else:
                ctx = ctx_result.value
                enrolled_ps_uids = list(ctx.current_ps_uids)[:2]

        # Always fetch studying Ku UIDs from ku_service (source of truth for is_studying flag)
        if ku_service:
            studying_result = await ku_service.get_studying_ku_uids(user_uid)
            if studying_result.is_error:
                logger.error(f"Library: failed to load studying Kus: {studying_result.error}")
            else:
                studying_ku_uids = (studying_result.value or [])[:5]

        # --- Fetch studying Kus (max 5) ---
        if ku_service and studying_ku_uids:
            for ku_uid in studying_ku_uids:
                ku_result = await ku_service.get_ku(ku_uid)
                if not ku_result.is_error and ku_result.value:
                    kus.append(ku_result.value)

        # --- Fetch enrolled PathSteps (max 2) ---
        if ps_service and enrolled_ps_uids:
            batch_result = await ps_service.get_steps_batch(enrolled_ps_uids)
            if batch_result.is_error:
                logger.error(f"Library: failed to load PathSteps: {batch_result.error}")
            else:
                path_steps = [ps for ps in (batch_result.value or []) if ps is not None]

        # --- Fetch exercises for enrolled PathSteps ---
        if exercises_service and enrolled_ps_uids:
            ex_result = await exercises_service.get_exercises_for_path_steps(enrolled_ps_uids)
            if ex_result.is_error:
                logger.error(f"Library: failed to load exercises for PathSteps: {ex_result.error}")
            else:
                exercises = ex_result.value or []

        return render_curriculum_list(kus, path_steps, exercises)

    # ========================================================================
    # HTMX FRAGMENT: RESOURCES TAB
    # ========================================================================

    @rt("/library/resources")
    async def library_resources(request: Request) -> Any:
        """HTMX fragment: admin-curated Resource entity list."""
        require_authenticated_user(request)

        if not resource_service:
            return render_error_banner("Resource service unavailable")

        result = await resource_service.list_all()
        if result.is_error:
            logger.error(f"Library: failed to load Resources: {result.error}")
            return render_error_banner("Failed to load resources", str(result.error))

        return render_resource_list(result.value or [])

    return []
