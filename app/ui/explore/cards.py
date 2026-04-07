"""
Explore Card & Search Panel Components
=======================================

Pure rendering functions for the Explore discovery grid.
No async, no service calls — receives pre-fetched data.
"""

from typing import Any

from fasthtml.common import A as Anchor
from fasthtml.common import Div, Form, Input, NotStr, Option, P, Select, Span

from ui.feedback import Badge, BadgeT
from ui.layout import Size

# Search SVG icon (shared)
SEARCH_ICON = NotStr(
    '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" '
    'viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
    'class="text-muted-foreground shrink-0">'
    '<circle cx="11" cy="11" r="8"/>'
    '<path d="m21 21-4.35-4.35"/>'
    "</svg>"
)


def render_explore_card(
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
        pill = Badge("Ku", variant=BadgeT.accent, size=Size.sm, cls="shrink-0")
        detail_href = f"/explore/ku/{uid}"
    else:
        pill = Badge(
            "Path Step",
            variant=None,
            cls="bg-teal-100 text-teal-800 border-teal-200 shrink-0",
            size=Size.sm,
        )
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


def render_explore_search_panel(all_tags: list[str]) -> Div:
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
                    SEARCH_ICON,
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
