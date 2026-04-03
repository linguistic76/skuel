"""
Explore UI Routes — Discovery Page for Ku + PathStep
=====================================================

Unified exploration surface where Ku and PathStep entities intermingle
in a discovery-first bento card layout with search and filtering.

Routes:
- GET  /explore              — Discovery index with search + bento card grid
- GET  /api/explore/search   — HTMX fragment: filtered card grid
- GET  /explore/ku/{uid}     — Ku detail page with sidebar
- GET  /explore/ps/{uid}     — PathStep detail page with sidebar
"""

from typing import Any

from fasthtml.common import (
    H3,
    Div,
    Form,
    Input,
    Li,
    NotStr,
    Option,
    P,
    Request,
    Select,
    Span,
    Ul,
)
from fasthtml.common import A as Anchor

from adapters.inbound.auth import get_current_user, is_authenticated, require_authenticated_user
from adapters.inbound.ku_ui import (
    _exercises_for_ku_section,
    _ku_learning_buttons,
)
from adapters.inbound.path_steps_ui import _start_step_button
from core.models.ku.ku import Ku
from core.models.pathways.path_step import PathStep
from core.utils.logging import get_logger
from core.utils.markdown_renderer import render_markdown_with_toc
from ui.buttons import Button, ButtonLink, ButtonT
from ui.cards import Card, CardBody
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.patterns.breadcrumbs import Breadcrumbs
from ui.patterns.metadata_badge import metadata_badge
from ui.patterns.page_header import PageHeader
from ui.patterns.pin_button import PinButton
from ui.patterns.relationships import EntityRelationshipsSection
from ui.patterns.sidebar import SidebarItem, SidebarLink, SidebarPage

logger = get_logger("skuel.routes.explore")

# Type pill badge classes (reused from library_ui.py color scheme)
_KU_PILL_CLS = (
    "bg-violet-100 text-violet-800 border border-violet-200 "
    "text-xs font-medium px-2 py-0.5 rounded-full shrink-0"
)
_PS_PILL_CLS = (
    "bg-teal-100 text-teal-800 border border-teal-200 "
    "text-xs font-medium px-2 py-0.5 rounded-full shrink-0"
)

# Search SVG icon (shared)
_SEARCH_ICON = NotStr(
    '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" '
    'viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
    'class="text-muted-foreground shrink-0">'
    '<circle cx="11" cy="11" r="8"/>'
    '<path d="m21 21-4.35-4.35"/>'
    "</svg>"
)


# =============================================================================
# Card rendering
# =============================================================================


def _explore_card(
    item: Any,
    entity_type: str,
    learning_state: str = "",
    is_pinned: bool = False,
) -> Div:
    """Render a single explore card for bento grid layout.

    Args:
        item: Ku or PathStep entity.
        entity_type: "ku" or "ps".
        learning_state: Learning state label (e.g., "Studying", "In Progress").
        is_pinned: Whether the entity is bookmarked/pinned.
    """
    uid = item.uid
    title = item.title or uid

    # Type pill
    if entity_type == "ku":
        pill = Span("Ku", cls=_KU_PILL_CLS)
        detail_href = f"/explore/ku/{uid}"
    else:
        pill = Span("Path Step", cls=_PS_PILL_CLS)
        detail_href = f"/explore/ps/{uid}"

    # Truncated description
    desc = (getattr(item, "description", "") or "")[:120]
    if len(getattr(item, "description", "") or "") > 120:
        desc += "..."

    # Metadata badges
    meta_parts: list[Any] = []
    if entity_type == "ku":
        if getattr(item, "ku_category", None):
            meta_parts.append(Badge(item.ku_category, variant=BadgeT.neutral, size=Size.sm))
        if getattr(item, "namespace", None):
            meta_parts.append(Span(item.namespace, cls="text-xs text-muted-foreground"))
    else:
        if getattr(item, "complexity", None):
            meta_parts.append(
                Span(
                    str(item.complexity.value),
                    cls="text-xs text-muted-foreground",
                )
            )
        if getattr(item, "estimated_time_minutes", None):
            meta_parts.append(
                Span(f"{item.estimated_time_minutes} min", cls="text-xs text-muted-foreground")
            )
        if getattr(item, "learning_level", None):
            meta_parts.append(
                Span(str(item.learning_level.value), cls="text-xs text-muted-foreground")
            )

    # Tag chips (max 3)
    tags = (getattr(item, "tags", None) or ())[:3]
    tag_chips = [
        Span(
            f"#{tag}",
            cls="text-xs text-muted-foreground/70",
        )
        for tag in tags
    ]

    # Learning state badge
    state_badge = None
    if learning_state:
        state_badge = Badge(learning_state, variant=BadgeT.secondary, size=Size.sm)

    return Div(
        # Header: pill + title
        Div(
            pill,
            Anchor(
                title,
                href=detail_href,
                cls="font-medium text-foreground hover:text-primary transition-colors line-clamp-1",
            ),
            cls="flex items-center gap-2",
        ),
        # Description
        P(desc, cls="text-sm text-muted-foreground mt-1.5 line-clamp-2") if desc else None,
        # Footer: metadata + tags + state
        Div(
            *meta_parts,
            *tag_chips,
            state_badge,
            cls="flex flex-wrap items-center gap-2 mt-2",
        )
        if meta_parts or tag_chips or state_badge
        else None,
        cls="p-4 border border-border rounded-lg bg-background hover:border-foreground/20 transition-colors",
    )


# =============================================================================
# Search panel
# =============================================================================


def _explore_search_panel(all_tags: list[str]) -> Div:
    """Search + filter panel for the explore index.

    Uses HTMX to stream filtered results into #explore-grid.
    Alpine.js tracks query state for tag selection.
    """
    type_options = [
        Option("All Types", value=""),
        Option("Ku", value="ku"),
        Option("Path Step", value="ps"),
    ]

    sort_options = [
        Option("Newest First", value="created_at"),
        Option("Title A\u2013Z", value="title"),
    ]

    tag_chips = [
        Span(
            f"#{tag}",
            cls="cursor-pointer text-xs px-2 py-0.5 rounded-full border border-border "
            "text-muted-foreground hover:border-foreground hover:text-foreground "
            "transition-colors select-none",
            x_on_click=f"setTag('{tag}')",
        )
        for tag in all_tags[:24]
    ]

    dropdown_cls = (
        "text-sm border border-border rounded-md px-2 py-1.5 bg-background "
        "text-foreground focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer"
    )

    return Div(
        Form(
            # Row 1: search input
            Div(
                Span(
                    _SEARCH_ICON,
                    cls="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none",
                ),
                Input(
                    name="q",
                    type="search",
                    placeholder="Search knowledge units and path steps...",
                    autocomplete="off",
                    cls="w-full pl-9 pr-4 py-2 text-sm border border-border rounded-lg "
                    "bg-background focus:outline-none focus:ring-1 focus:ring-primary "
                    "focus:border-primary",
                    x_model="query",
                    x_ref="searchInput",
                    hx_get="/api/explore/search",
                    hx_target="#explore-grid",
                    hx_trigger="input delay:250ms",
                    hx_include="closest form",
                ),
                cls="relative",
            ),
            # Row 2: dropdowns
            Div(
                Select(
                    *type_options,
                    name="type",
                    cls=dropdown_cls,
                    hx_get="/api/explore/search",
                    hx_target="#explore-grid",
                    hx_trigger="change",
                    hx_include="closest form",
                ),
                Select(
                    *sort_options,
                    name="sort",
                    cls=dropdown_cls,
                    hx_get="/api/explore/search",
                    hx_target="#explore-grid",
                    hx_trigger="change",
                    hx_include="closest form",
                ),
                cls="flex flex-wrap gap-2",
            ),
            # Row 3: tags
            Div(*tag_chips, cls="flex flex-wrap gap-1.5") if tag_chips else None,
            # Hidden input for active tag
            Input(name="tag", type="hidden", x_bind_value="activeTag"),
            cls="flex flex-col gap-3",
        ),
        cls="p-4 mb-5 border border-border rounded-xl bg-background flex flex-col gap-3",
        x_data="exploreSearch()",
        x_init="init()",
    )


# =============================================================================
# Data loading helpers
# =============================================================================


def _created_at_key(item: Any) -> str:
    val = getattr(item, "created_at", None)
    if val is None:
        return ""
    # Neo4j DateTime objects may have mixed timezone awareness — stringify for safe comparison
    return str(val)


def _title_key(item: Any) -> str:
    return (getattr(item, "title", None) or "").lower()


def _filter_items(
    items: list[tuple[Any, str]],
    q: str,
    type_filter: str,
    tag: str,
    sort: str,
) -> list[tuple[Any, str]]:
    """Filter and sort unified (item, entity_type) list."""
    results = items

    if type_filter:
        results = [(item, et) for item, et in results if et == type_filter]

    if tag:
        tag_lower = tag.lower()
        results = [
            (item, et)
            for item, et in results
            if any(t.lower() == tag_lower for t in (getattr(item, "tags", None) or ()))
        ]

    if q:
        q_lower = q.lower()
        results = [
            (item, et)
            for item, et in results
            if q_lower in (getattr(item, "title", None) or "").lower()
            or q_lower in (getattr(item, "description", None) or "").lower()
            or any(q_lower in t.lower() for t in (getattr(item, "tags", None) or ()))
        ]

    if sort == "title":
        results.sort(key=lambda x: _title_key(x[0]))
    else:
        results.sort(key=lambda x: _created_at_key(x[0]), reverse=True)

    return results


# =============================================================================
# Route factory
# =============================================================================


def create_explore_ui_routes(
    _app: Any,
    rt: Any,
    ku_service: Any,
    ps_service: Any,
    user_relationship_service: Any = None,
    exercises_service: Any = None,
) -> list[Any]:
    """Create /explore UI routes.

    Args:
        ku_service: KuService (services.ku).
        ps_service: PsService (services.ps).
        user_relationship_service: For pinned entities.
        exercises_service: For REQUIRES_KNOWLEDGE reverse lookup.
    """

    # -----------------------------------------------------------------
    # Shared data loader
    # -----------------------------------------------------------------

    async def _load_explore_data(
        request: Request,
    ) -> tuple[list[tuple[Any, str]], set[str], dict[str, str]]:
        """Load all Ku + PS, pins, and learning states.

        Returns:
            (unified_items, pinned_uids, learning_states)
            where unified_items is list of (entity, "ku"|"ps") tuples,
            and learning_states maps uid -> state label.
        """
        items: list[tuple[Any, str]] = []

        # Load Kus
        if ku_service and getattr(ku_service, "core", None):
            result = await ku_service.core.list(limit=500)
            if not result.is_error and result.value:
                items.extend((ku, "ku") for ku in result.value)

        # Load PathSteps
        if ps_service and getattr(ps_service, "core", None):
            result = await ps_service.core.list(limit=200)
            if not result.is_error and result.value:
                raw = result.value if isinstance(result.value, list) else result.value[0]
                items.extend((ps, "ps") for ps in raw)

        pinned_uids: set[str] = set()
        learning_states: dict[str, str] = {}

        if is_authenticated(request):
            user_uid = require_authenticated_user(request)

            # Pinned entities
            if user_relationship_service:
                pins_result = await user_relationship_service.get_pinned_entities(user_uid)
                if not pins_result.is_error and pins_result.value:
                    pinned_uids = set(pins_result.value)

            # Ku learning states
            if ku_service:
                states_result = await ku_service.get_user_learning_states(user_uid)
                if states_result.is_ok and states_result.value:
                    for rec in states_result.value:
                        ku_uid = rec.get("uid", "")
                        if rec.get("is_understood"):
                            learning_states[ku_uid] = "Understood"
                        elif rec.get("is_studying"):
                            learning_states[ku_uid] = "Studying"

            # PS learning states
            if ps_service:
                in_progress_result = await ps_service.mastery.get_in_progress_step_uids(user_uid)
                if not in_progress_result.is_error and in_progress_result.value:
                    for ps_uid in in_progress_result.value:
                        learning_states[ps_uid] = "In Progress"

        return items, pinned_uids, learning_states

    # -----------------------------------------------------------------
    # GET /explore — Discovery index
    # -----------------------------------------------------------------

    @rt("/explore")
    async def explore_index(request: Request) -> Any:
        """Explore page — discovery-first bento card grid of Ku + PathStep."""
        items, pinned_uids, learning_states = await _load_explore_data(request)

        # Collect tags from all items
        all_tags = sorted(
            {t for item, _ in items for t in (getattr(item, "tags", None) or ())} - {""}
        )

        # Default sort: newest first
        items.sort(key=lambda x: _created_at_key(x[0]), reverse=True)

        # Render card grid
        cards = [
            _explore_card(
                item,
                entity_type=et,
                learning_state=learning_states.get(item.uid, ""),
                is_pinned=item.uid in pinned_uids,
            )
            for item, et in items
        ]

        grid = (
            Div(
                *cards,
                cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
                id="explore-grid",
            )
            if cards
            else Div(
                P(
                    "No content yet. Ingest Ku or PathStep YAML files to populate this page.",
                    cls="text-muted-foreground italic py-8 text-center",
                ),
                id="explore-grid",
            )
        )

        content = Div(
            PageHeader("Explore", subtitle="Discover knowledge units and path steps"),
            _explore_search_panel(all_tags),
            grid,
        )

        return await BasePage(
            content=content,
            title="Explore",
            request=request,
            active_page="explore",
        )

    # -----------------------------------------------------------------
    # GET /api/explore/search — HTMX fragment
    # -----------------------------------------------------------------

    @rt("/api/explore/search")
    async def explore_search(
        request: Request,
        q: str = "",
        type: str = "",
        tag: str = "",
        sort: str = "created_at",
    ) -> Any:
        """Return filtered card grid HTML fragment for HTMX swap."""
        items, pinned_uids, learning_states = await _load_explore_data(request)

        filtered = _filter_items(items, q.strip(), type, tag, sort)

        if not filtered:
            return Div(
                P(
                    "No results match your search.",
                    cls="text-muted-foreground italic py-8 text-center",
                ),
            )

        cards = [
            _explore_card(
                item,
                entity_type=et,
                learning_state=learning_states.get(item.uid, ""),
                is_pinned=item.uid in pinned_uids,
            )
            for item, et in filtered
        ]

        return Div(
            *cards,
            cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
        )

    # -----------------------------------------------------------------
    # GET /explore/ku/{uid} — Ku detail page
    # -----------------------------------------------------------------

    @rt("/explore/ku/{uid}")
    async def explore_ku_detail(request: Request, uid: str) -> Any:
        """Ku detail page within explore context.

        Public: shared curriculum content is readable without authentication.
        Learning state tracking requires authentication.
        """
        user_uid: str | None = get_current_user(request)

        ku_result = await ku_service.get_ku(uid) if ku_service else None

        if not ku_result or ku_result.is_error or not ku_result.value:
            return await BasePage(
                content=Div(
                    Card(
                        CardBody(
                            H3("Knowledge Unit Not Found", cls="text-lg font-bold"),
                            P(f"No KU with identifier: {uid}", cls="text-muted-foreground mt-2"),
                            ButtonLink(
                                "\u2190 Back to Explore",
                                href="/explore",
                                variant=ButtonT.ghost,
                                size=Size.sm,
                                cls="mt-4",
                            ),
                        ),
                    ),
                    cls="max-w-4xl mx-auto p-8",
                ),
                title="KU Not Found",
                request=request,
            )

        ku = ku_result.value
        content_body = ku.description or ""

        # Learning state
        learning_state: dict[str, bool] = {"is_studying": False, "is_understood": False}
        is_pinned = False
        if user_uid:
            state_result = await ku_service.get_ku_learning_state(user_uid, uid)
            if state_result.is_ok:
                learning_state = state_result.value
            if user_relationship_service:
                pins_result = await user_relationship_service.get_pinned_entities(user_uid)
                if pins_result.is_ok and pins_result.value:
                    is_pinned = uid in set(pins_result.value)

        # Sidebar — related Kus (same namespace) + more to explore
        related_kus: list[Ku] = []
        more_items: list[tuple[Any, str]] = []
        if ku_service and getattr(ku_service, "core", None):
            all_kus_result = await ku_service.core.list(limit=20)
            if all_kus_result.is_ok and all_kus_result.value:
                for k in all_kus_result.value:
                    if k.uid == uid:
                        continue
                    if (
                        getattr(ku, "namespace", None)
                        and getattr(k, "namespace", None) == ku.namespace
                        and len(related_kus) < 5
                    ):
                        related_kus.append(k)
                    elif len(more_items) < 5:
                        more_items.append((k, "ku"))

        if ps_service and getattr(ps_service, "core", None) and len(more_items) < 5:
            ps_result = await ps_service.core.list(limit=5)
            if ps_result.is_ok and ps_result.value:
                raw = ps_result.value if isinstance(ps_result.value, list) else ps_result.value[0]
                for s in raw:
                    if len(more_items) >= 5:
                        break
                    more_items.append((s, "ps"))

        # Render markdown with TOC
        content_html, toc_html = render_markdown_with_toc(content_body)
        has_toc = bool(toc_html and toc_html.strip())

        # Metadata badges
        metadata_items = []
        if getattr(ku, "domain", None):
            domain_label = getattr(ku.domain, "value", str(ku.domain))
            metadata_items.append(metadata_badge("Domain:", domain_label, BadgeT.primary))
        if getattr(ku, "namespace", None):
            metadata_items.append(metadata_badge("Namespace:", ku.namespace))
        if getattr(ku, "ku_category", None):
            metadata_items.append(metadata_badge("Category:", ku.ku_category))

        metadata_section = (
            Div(*metadata_items, cls="flex flex-wrap gap-2") if metadata_items else None
        )

        # Tags
        tags_section = None
        if getattr(ku, "tags", None):
            tag_badges = [Badge(tag, variant=BadgeT.outline, size=Size.sm) for tag in ku.tags]
            tags_section = Div(*tag_badges, cls="flex flex-wrap gap-1 mt-3")

        # Exercises
        exercises_for_ku: list[dict] = []
        if exercises_service:
            exercises_result = await exercises_service.get_exercises_for_curriculum(uid)
            exercises_for_ku = exercises_result.value if exercises_result.is_ok else []

        # Breadcrumbs
        breadcrumb_path = [
            {"uid": "explore", "title": "Explore", "url": "/explore"},
            {"uid": uid, "title": ku.title, "url": ""},
        ]

        reading_content = Div(
            NotStr(content_html or "No content available."),
            cls="prose prose-lg max-w-none",
        )

        # Action buttons
        if user_uid:
            ku_action_area: Any = Div(
                _ku_learning_buttons(
                    uid, learning_state["is_studying"], learning_state["is_understood"]
                ),
                PinButton(entity_uid=uid, is_pinned=is_pinned),
                cls="flex gap-2 items-center border-t border-border pt-6 mt-8",
            )
        else:
            ku_action_area = Div(
                ButtonLink(
                    "Log in to track your progress",
                    href="/login",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                ),
                cls="border-t border-border pt-6 mt-8",
            )

        # Metadata footer
        metadata_footer_items = []
        if metadata_section:
            metadata_footer_items.append(metadata_section)
        if tags_section:
            metadata_footer_items.append(tags_section)

        metadata_footer = (
            Div(*metadata_footer_items, cls="border-t border-border pt-6 mt-8")
            if metadata_footer_items
            else Div()
        )

        main_column = Div(
            Breadcrumbs(path=breadcrumb_path, show_home=False),
            reading_content,
            ku_action_area,
            metadata_footer,
            _exercises_for_ku_section(exercises_for_ku),
            Div(
                EntityRelationshipsSection(entity_uid=uid, entity_type="ku"),
                cls="mt-8",
            ),
            cls="flex-1 min-w-0 max-w-4xl",
        )

        if has_toc:
            toc_sidebar = Div(
                Div(
                    H3("Contents", cls="font-semibold text-sm mb-3"),
                    Div(NotStr(toc_html), cls="prose prose-sm max-w-none toc-nav"),
                    cls="sticky top-20 p-5 max-h-[calc(100vh-6rem)] overflow-y-auto",
                ),
                cls="hidden lg:block w-56 shrink-0 border-l border-border",
            )
            content = Div(main_column, toc_sidebar, cls="flex gap-6")
        else:
            content = main_column

        # Sidebar sections
        sidebar_items: list[SidebarItem] = []
        sidebar_extra: list[Any] = []
        if related_kus:
            sidebar_extra.append(
                Li(
                    P(
                        "Related",
                        cls="text-xs font-semibold uppercase text-muted-foreground px-4 pt-3 pb-1",
                    ),
                    Ul(
                        *[
                            SidebarLink(text=k.title, href=f"/explore/ku/{k.uid}")
                            for k in related_kus
                        ],
                        cls="list-none p-0",
                    ),
                )
            )
        if more_items:
            sidebar_extra.append(
                Li(
                    P(
                        "More to Explore",
                        cls="text-xs font-semibold uppercase text-muted-foreground px-4 pt-3 pb-1",
                    ),
                    Ul(
                        *[
                            SidebarLink(
                                text=getattr(item, "title", item.uid),
                                href=f"/explore/{'ku' if et == 'ku' else 'ps'}/{item.uid}",
                            )
                            for item, et in more_items
                        ],
                        cls="list-none p-0",
                    ),
                )
            )

        return await SidebarPage(
            content=content,
            items=sidebar_items,
            active="",
            title="Explore",
            storage_key="explore-detail-sidebar",
            extra_sidebar_sections=sidebar_extra or None,
            page_title=ku.title,
            request=request,
            active_page="explore",
            title_href="/explore",
            default_collapsed=True,
        )

    # -----------------------------------------------------------------
    # GET /explore/ps/{uid} — PathStep detail page
    # -----------------------------------------------------------------

    @rt("/explore/ps/{uid}")
    async def explore_ps_detail(request: Request, uid: str) -> Any:
        """PathStep detail page within explore context.

        Public: shared curriculum content is readable without authentication.
        Learning state tracking requires authentication.
        """
        user_uid: str | None = get_current_user(request)

        result = await ps_service.get_with_content(uid)
        if result.is_error:
            return await BasePage(
                content=Div(
                    Card(
                        CardBody(
                            H3("Path Step Not Found", cls="text-lg font-bold"),
                            P(
                                f"No path step with identifier: {uid}",
                                cls="text-muted-foreground mt-2",
                            ),
                            ButtonLink(
                                "\u2190 Back to Explore",
                                href="/explore",
                                variant=ButtonT.ghost,
                                size=Size.sm,
                                cls="mt-4",
                            ),
                        ),
                    ),
                    cls="max-w-4xl mx-auto p-8",
                ),
                title="Path Step Not Found",
                request=request,
            )

        step, content_body = result.value
        if not content_body and getattr(step, "content", None):
            content_body = str(step.content)

        # Learning state
        is_marked_read = False
        is_bookmarked = False
        is_in_progress = False
        is_mastered = False
        if user_uid:
            await ps_service.mastery.record_view(user_uid, uid)
            state_result = await ps_service.mastery.get_learning_state(user_uid, uid)
            is_marked_read = state_result.value.is_marked_as_read if state_result.is_ok else False
            is_bookmarked = state_result.value.is_bookmarked if state_result.is_ok else False
            is_in_progress = (
                state_result.value.state.value == "in_progress" if state_result.is_ok else False
            )
            is_mastered = (
                state_result.value.state.value == "mastered" if state_result.is_ok else False
            )

        # Sidebar — related content for contextual navigation
        sidebar_steps: list[PathStep] = []
        if user_uid:
            in_progress_result = await ps_service.mastery.get_in_progress_step_uids(user_uid)
            if in_progress_result.is_ok and in_progress_result.value:
                in_progress_uids = [u for u in in_progress_result.value if u != uid][:5]
                if in_progress_uids:
                    batch_result = await ps_service.get_steps_batch(in_progress_uids)
                    if batch_result.is_ok and batch_result.value:
                        sidebar_steps = list(batch_result.value)

        more_items: list[tuple[Any, str]] = []
        available_result = await ps_service.list_steps(limit=6)
        if available_result.is_ok and available_result.value:
            in_progress_uid_set = {s.uid for s in sidebar_steps} | {uid}
            for s in available_result.value:
                if s.uid not in in_progress_uid_set and len(more_items) < 3:
                    more_items.append((s, "ps"))

        if ku_service and getattr(ku_service, "core", None) and len(more_items) < 5:
            ku_result = await ku_service.core.list(limit=5)
            if ku_result.is_ok and ku_result.value:
                for k in ku_result.value:
                    if len(more_items) >= 5:
                        break
                    more_items.append((k, "ku"))

        # Render markdown with TOC
        content_html, toc_html = render_markdown_with_toc(content_body or "")
        has_toc = bool(toc_html and toc_html.strip())

        # Breadcrumbs
        breadcrumb_path = [
            {"uid": "explore", "title": "Explore", "url": "/explore"},
            {"uid": uid, "title": step.title, "url": ""},
        ]

        # Metadata badges
        metadata_items = []
        if step.domain:
            domain_label = getattr(step.domain, "value", str(step.domain))
            metadata_items.append(metadata_badge("Domain:", domain_label, BadgeT.primary))
        if step.complexity:
            metadata_items.append(metadata_badge("Complexity:", str(step.complexity.value)))
        if step.learning_level:
            metadata_items.append(metadata_badge("Level:", str(step.learning_level.value)))
        if step.estimated_time_minutes:
            metadata_items.append(metadata_badge("Time:", f"{step.estimated_time_minutes} min"))
        if step.estimated_hours:
            metadata_items.append(metadata_badge("Hours:", f"{step.estimated_hours:.1f}h"))

        metadata_section = (
            Div(*metadata_items, cls="flex flex-wrap gap-2 mb-4") if metadata_items else Div()
        )

        # Learning objectives
        objectives_section = Div()
        if step.learning_objectives:
            objectives_section = Div(
                H3("Learning Objectives", cls="text-base font-semibold mb-2"),
                Ul(
                    *[
                        Li(obj, cls="text-sm text-muted-foreground")
                        for obj in step.learning_objectives
                    ],
                    cls="list-disc pl-5 space-y-1 mb-6",
                ),
            )

        # Tags
        tags_section = Div()
        if step.tags:
            tag_badges = [Badge(tag, variant=BadgeT.outline, size=Size.sm) for tag in step.tags]
            tags_section = Div(*tag_badges, cls="flex flex-wrap gap-1 mt-3")

        # Reading content
        reading_content = Div(
            NotStr(content_html or "No content available."),
            cls="prose prose-lg max-w-none",
        )

        # Exercises
        exercises_section: Any = Div()
        exercises_result = await ps_service.get_exercises_for_path_step(uid)
        if exercises_result.is_ok and exercises_result.value:
            exercise_links = []
            for ex in exercises_result.value:
                ex_uid = ex.get("uid", "")
                ex_title = ex.get("title") or ex_uid
                ex_time = ex.get("estimated_time_minutes")
                time_note = f" \u00b7 {ex_time} min" if ex_time else ""
                exercise_links.append(
                    Li(
                        ButtonLink(
                            f"{ex_title}{time_note} \u2192",
                            href=f"/exercises/get?uid={ex_uid}&from_ps={uid}",
                            variant=ButtonT.ghost,
                            size=Size.sm,
                        ),
                        cls="list-none",
                    )
                )
            exercises_section = Div(
                H3("Exercises", cls="text-base font-semibold mb-2 mt-8"),
                Ul(*exercise_links, cls="list-none p-0 space-y-1"),
                cls="border-t border-border pt-6 mt-8",
            )

        # Action buttons
        if user_uid:
            mark_read_btn = Button(
                "Marked as Read" if is_marked_read else "Mark as Read",
                variant=ButtonT.success if is_marked_read else ButtonT.primary,
                size=Size.sm,
                hx_post=f"/api/path-steps/{uid}/mark-read",
                hx_swap="outerHTML",
                hx_target="this",
                disabled=is_marked_read,
            )
            bookmark_btn = Button(
                "Bookmarked" if is_bookmarked else "Bookmark",
                variant=ButtonT.secondary if is_bookmarked else ButtonT.ghost,
                size=Size.sm,
                hx_post=f"/api/path-steps/{uid}/bookmark",
                hx_swap="outerHTML",
                hx_target="this",
            )
            action_area: Any = Div(
                _start_step_button(uid, is_in_progress, is_mastered),
                mark_read_btn,
                bookmark_btn,
                cls="flex gap-2 border-t border-border pt-6 mt-8",
            )
        else:
            action_area = Div(
                ButtonLink(
                    "Log in to track your progress",
                    href="/login",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                ),
                cls="border-t border-border pt-6 mt-8",
            )

        # Main content column
        main_column = Div(
            Breadcrumbs(path=breadcrumb_path, show_home=False),
            metadata_section,
            objectives_section,
            reading_content,
            exercises_section,
            action_area,
            Div(tags_section, cls="border-t border-border pt-6 mt-8") if step.tags else Div(),
            EntityRelationshipsSection(entity_uid=uid, entity_type="ps"),
            cls="flex-1 min-w-0 max-w-4xl",
        )

        if has_toc:
            toc_sidebar = Div(
                Div(
                    H3("Contents", cls="font-semibold text-sm mb-3"),
                    Div(NotStr(toc_html), cls="prose prose-sm max-w-none toc-nav"),
                    cls="sticky top-20 p-5 max-h-[calc(100vh-6rem)] overflow-y-auto",
                ),
                cls="hidden lg:block w-56 shrink-0 border-l border-border",
            )
            content = Div(main_column, toc_sidebar, cls="flex gap-6")
        else:
            content = main_column

        # Sidebar sections
        ps_sidebar_items: list[SidebarItem] = []
        ps_sidebar_extra: list[Any] = []
        if sidebar_steps:
            ps_sidebar_extra.append(
                Li(
                    P(
                        "In Progress",
                        cls="text-xs font-semibold uppercase text-muted-foreground px-4 pt-3 pb-1",
                    ),
                    Ul(
                        *[
                            SidebarLink(text=s.title, href=f"/explore/ps/{s.uid}")
                            for s in sidebar_steps
                        ],
                        cls="list-none p-0",
                    ),
                )
            )
        if more_items:
            ps_sidebar_extra.append(
                Li(
                    P(
                        "More to Explore",
                        cls="text-xs font-semibold uppercase text-muted-foreground px-4 pt-3 pb-1",
                    ),
                    Ul(
                        *[
                            SidebarLink(
                                text=getattr(item, "title", item.uid),
                                href=f"/explore/{'ku' if et == 'ku' else 'ps'}/{item.uid}",
                            )
                            for item, et in more_items
                        ],
                        cls="list-none p-0",
                    ),
                )
            )

        return await SidebarPage(
            content=content,
            items=ps_sidebar_items,
            active="",
            title="Explore",
            storage_key="explore-detail-sidebar",
            extra_sidebar_sections=ps_sidebar_extra or None,
            page_title=step.title,
            request=request,
            active_page="explore",
            title_href="/explore",
            default_collapsed=True,
        )

    logger.info(
        "Explore UI routes registered: /explore, /api/explore/search, "
        "/explore/ku/{uid}, /explore/ps/{uid}"
    )

    return []  # Routes registered via @rt() decorators


__all__ = ["create_explore_ui_routes"]
