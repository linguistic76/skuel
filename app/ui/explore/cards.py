"""
Explore Card & Search Panel Components
=======================================

Pure rendering functions for the Explore discovery grid.
No async, no service calls — receives pre-fetched data.
"""

import json
from typing import Any

from fasthtml.common import FT, Button, Div, Form, Input, NotStr, Option, P, Select, Span
from fasthtml.common import A as Anchor

from core.models.enums.entity_enums import EntityType
from core.models.enums.learning_enums import LearningLevel
from core.models.search.filter_enums import SearchSortOrder
from ui.feedback import Badge, BadgeT
from ui.layout import Size

# One grid page of the library catalog (bento cards per "Load more" fetch).
LIBRARY_PAGE_SIZE = 24

# Tag chips shown before the "+N more" expander (vocabulary arrives ranked
# most-used first, so the visible row is the densest facets, not A-C).
VISIBLE_TAG_CHIPS = 24

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
    item: dict[str, Any],
    learning_state: str = "",
    is_pinned: bool = False,
) -> Div:
    """Render a single explore card for bento grid layout.

    Args:
        item: SearchRouter faceted-search result dict — raw Neo4j node
            properties plus the ``_domain`` stamp (EntityType values:
            "ku" / "path_step"). Enum-backed properties (complexity,
            learning_level) arrive as their stored string values.
        learning_state: Learning state label (e.g., "Studying", "In Progress").
        is_pinned: Whether the entity is bookmarked/pinned.
    """
    uid = str(item.get("uid", ""))
    title = item.get("title") or uid
    is_ku = item.get("_domain") == EntityType.KU.value

    # Type pill
    if is_ku:
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
    full_desc = item.get("description") or ""
    desc = full_desc[:120]
    if len(full_desc) > 120:
        desc += "..."

    # Metadata badges — Ku is a lightweight reference node (no display metadata);
    # PathStep carries complexity / time / level.
    meta_parts: list[Any] = []
    if not is_ku:
        if item.get("complexity"):
            meta_parts.append(Span(str(item["complexity"]), cls="text-xs text-muted-foreground"))
        if item.get("estimated_time_minutes"):
            meta_parts.append(
                Span(f"{item['estimated_time_minutes']} min", cls="text-xs text-muted-foreground")
            )
        if item.get("learning_level"):
            meta_parts.append(
                Span(str(item["learning_level"]), cls="text-xs text-muted-foreground")
            )

    # Tag chips (max 3)
    tags = (item.get("tags") or ())[:3]
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


def render_load_more(next_offset: int) -> Button:
    """Sentinel "Load more" button — last child of the card grid.

    Replaces itself (outerHTML swap) with the next page of bare cards plus a
    fresh sentinel, so pages append in place. Filter state rides along via
    ``hx_include`` on the search form; the offset is the button's own
    ``hx_vals`` (filter-triggered requests carry no offset input, so any
    filter change naturally resets to page one).
    """
    return Button(
        "Load more",
        type="button",
        hx_get="/api/explore/search",
        hx_target="this",
        hx_swap="outerHTML",
        hx_include="#explore-search-form",
        hx_vals=json.dumps({"offset": next_offset}),
        cls=(
            "col-span-full justify-self-center mt-2 px-4 py-2 text-sm rounded-lg "
            "border border-border text-muted-foreground hover:border-foreground "
            "hover:text-foreground transition-colors cursor-pointer"
        ),
    )


def _tag_chip(tag: str, active_tag: str, in_overflow: bool) -> Span:
    """One clickable tag chip; overflow chips render x-cloaked behind the expander."""
    overflow_attrs: dict[str, str | bool] = (
        {"x-show": "showAllTags", "x-cloak": True} if in_overflow else {}
    )
    return Span(
        f"#{tag}",
        cls=(
            "cursor-pointer text-xs px-2 py-0.5 rounded-full border transition-colors select-none "
            + (
                "border-foreground text-foreground bg-accent"
                if tag == active_tag
                else "border-border text-muted-foreground hover:border-foreground hover:text-foreground"
            )
        ),
        # json.dumps → properly-escaped JS string literal so tags containing
        # quotes/specials can't break out of (or inject into) the Alpine expression.
        **{"x-on:click": f"setTag({json.dumps(tag)})"},
        **overflow_attrs,
    )


# Shared select styling for the library facet bar (search box keeps its own,
# fuller styling in Row 1).
DROPDOWN_CLS = (
    "text-sm border border-border rounded-md px-2 py-1.5 bg-background "
    "text-foreground focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer"
)

# Every named control in the library facet bar. Used to build the NOUS
# dropdown's hx-include: HTMX auto-serializes the triggering control, so NOUS
# carries every OTHER filter EXCEPT its stale dependent (nous_subtopic), which a
# fresh NOUS topic invalidates. Mirrors /search's _get_hx_include contract.
_LIBRARY_FILTER_NAMES = ("q", "type", "nous", "nous_subtopic", "sort", "learning_level", "tag")


def _explore_hx_include(*exclude: str) -> str:
    """CSV of ``[name='…']`` selectors for every library filter minus ``exclude``."""
    excluded = set(exclude)
    return ", ".join(f"[name='{n}']" for n in _LIBRARY_FILTER_NAMES if n not in excluded)


NOUS_SUBTOPIC_COLUMN_ID = "explore-nous-subtopic-column"


def render_explore_subtopic_inner(subtopics: list[str], *, nous_selected: bool = True) -> Select:
    """Inner sub-topic ``<select>`` for the library cascade (HTMX-swapped fragment).

    Mirrors the /search cascade contract (ui.search.components.render_nous_subtopic_inner)
    but styled for the library panel and wired to the anonymous /api/explore/*
    endpoints. Sub-topics narrow WITHIN a chosen NOUS topic, so:
      * ``nous_selected=False`` (initial render, or the "All Nous" option) → a
        disabled "Choose a Nous first" placeholder, never the flat cross-topic list.
      * a chosen topic with no co-occurring sub-topics → a disabled "All Sub-topics"
        (fail-soft: the column stays present so the HTMX target never vanishes).
    Both non-selected states carry only the empty value, so no stale sub-topic
    ever rides a search request. Changing it re-runs /api/explore/search.
    """
    if not nous_selected:
        options = [Option("Choose a Nous first", value="")]
    else:
        options = [Option("All Sub-topics", value="")] + [
            Option(sub.replace("-", " ").title(), value=sub) for sub in subtopics
        ]
    return Select(
        *options,
        name="nous_subtopic",
        cls=DROPDOWN_CLS,
        disabled=not nous_selected or not subtopics,
        hx_get="/api/explore/search",
        hx_target="#explore-grid",
        hx_trigger="change",
        hx_include="closest form",
    )


def render_explore_search_panel(
    all_tags: list[str],
    nous_topics: list[str] | None = None,
    nous_subtopics: list[str] | None = None,
    active_tag: str = "",
) -> Div:
    """Search + filter panel for the explore index.

    Adapts the /search facet bar to the public curriculum catalog: TYPE (Ku /
    Path Step), NOUS topic + the dependent SUB-TOPIC cascade, a full SORT, and a
    "More filters" disclosure (learning level). Every facet is anonymous-safe —
    the NOUS/sub-topic vocabularies are graph-derived and unscoped, and the
    cascade fetches the anonymous /api/explore/subtopics endpoint (never the
    auth-gated /search/subtopics). Tags stay the primary discovery UX as chips.

    Args:
        all_tags: Available tag strings (without leading #), pre-ranked by the
            caller (most-used first via SearchRouter.tag_frequencies). The
            first VISIBLE_TAG_CHIPS render immediately; the rest sit behind a
            "+N more" expander so the full vocabulary stays reachable.
        nous_topics: NOUS topic vocabulary (graph-derived). Empty → the NOUS
            dropdown offers only "All Nous" (facet fails soft to no filtering).
        nous_subtopics: Flat sub-topic vocabulary — a RENDER GATE only. Empty →
            the SUB-TOPIC column is omitted entirely (mechanism ships ahead of
            vault content); the actual per-topic options come from the cascade.
        active_tag: Pre-selected tag from the URL (e.g. from ?tag=attention).
            Threaded into the Alpine factory so sort/search HTMX requests
            preserve the filter rather than resetting to tag=''.
    """
    nous_topics = nous_topics or []
    nous_subtopics = nous_subtopics or []
    type_options = [
        Option("All Types", value=""),
        Option("Ku", value="ku"),
        Option("Path Step", value="ps"),
    ]

    # SORT mirrors /search \u2014 values are canonical SearchSortOrder members, parsed
    # back via SearchSortOrder.from_string in the route. "Relevance" is only
    # meaningful alongside a query; it falls back to newest-first when browsing.
    sort_options = [
        Option("Relevance", value=SearchSortOrder.RELEVANCE.value),
        Option("Newest First", value=SearchSortOrder.CREATED_DESC.value),
        Option("Oldest First", value=SearchSortOrder.CREATED_ASC.value),
        Option("Recently Updated", value=SearchSortOrder.UPDATED_DESC.value),
        Option("Title A\u2013Z", value=SearchSortOrder.TITLE_ASC.value),
    ]

    nous_options = [Option("All Nous", value="")] + [
        Option(topic.title(), value=topic) for topic in nous_topics
    ]

    learning_level_options = [Option("All Levels", value="")] + [
        Option(level.value.title(), value=level.value) for level in LearningLevel
    ]

    visible_tags = all_tags[:VISIBLE_TAG_CHIPS]
    overflow_tags = all_tags[VISIBLE_TAG_CHIPS:]

    tag_chips: list[FT] = [_tag_chip(tag, active_tag, in_overflow=False) for tag in visible_tags]
    tag_chips += [_tag_chip(tag, active_tag, in_overflow=True) for tag in overflow_tags]
    if overflow_tags:
        tag_chips.append(
            Button(
                type="button",
                cls=(
                    "cursor-pointer text-xs px-2 py-0.5 rounded-full border border-dashed "
                    "border-border text-muted-foreground hover:border-foreground "
                    "hover:text-foreground transition-colors select-none"
                ),
                **{
                    "x-on:click": "showAllTags = !showAllTags",
                    "x-text": f"showAllTags ? 'Show fewer' : '+{len(overflow_tags)} more'",
                },
            )
        )

    # NOUS: changing the topic invalidates the old sub-topic, so this request
    # carries every OTHER filter EXCEPT nous_subtopic (HTMX auto-includes NOUS
    # itself). The sub-topic column resets independently via its own trigger.
    nous_select = Select(
        *nous_options,
        name="nous",
        cls=DROPDOWN_CLS,
        hx_get="/api/explore/search",
        hx_target="#explore-grid",
        hx_trigger="change",
        hx_include=_explore_hx_include("nous", "nous_subtopic"),
    )

    # SUB-TOPIC cascade column — render GATE: only appears once the vault carries
    # any nous_subtopic data. Stable container re-fetches the anonymous
    # /api/explore/subtopics fragment when NOUS changes (pure HTMX, no Alpine).
    subtopic_column = (
        Div(
            render_explore_subtopic_inner([], nous_selected=False),
            id=NOUS_SUBTOPIC_COLUMN_ID,
            hx_get="/api/explore/subtopics",
            hx_trigger="change from:[name='nous']",
            hx_target=f"#{NOUS_SUBTOPIC_COLUMN_ID}",
            hx_swap="innerHTML",
            hx_include="[name='nous']",
        )
        if nous_subtopics
        else None
    )

    learning_level_select = Select(
        *learning_level_options,
        name="learning_level",
        cls=DROPDOWN_CLS,
        hx_get="/api/explore/search",
        hx_target="#explore-grid",
        hx_trigger="change",
        hx_include="closest form",
    )

    # Desktop/mobile-agnostic disclosure — mirrors /search's "More filters".
    more_filters_toggle = Button(
        "More filters",
        type="button",
        cls=(
            "text-sm px-2 py-1.5 rounded-md border border-dashed border-border "
            "text-muted-foreground hover:border-foreground hover:text-foreground "
            "transition-colors cursor-pointer shrink-0"
        ),
        **{
            "x-on:click": "moreFilters = !moreFilters",
            "x-text": "moreFilters ? 'Fewer filters' : 'More filters'",
        },
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
            # Row 2: facet dropdowns — TYPE · NOUS · SUB-TOPIC · SORT + More filters
            Div(
                Select(
                    *type_options,
                    name="type",
                    cls=DROPDOWN_CLS,
                    hx_get="/api/explore/search",
                    hx_target="#explore-grid",
                    hx_trigger="change",
                    hx_include="closest form",
                ),
                nous_select,
                subtopic_column,
                Select(
                    *sort_options,
                    name="sort",
                    cls=DROPDOWN_CLS,
                    hx_get="/api/explore/search",
                    hx_target="#explore-grid",
                    hx_trigger="change",
                    hx_include="closest form",
                ),
                more_filters_toggle,
                cls="flex flex-wrap items-center gap-2",
            ),
            # Row 2b: "More filters" advanced disclosure (learning level).
            # style=display:none avoids a flash before Alpine resolves x-show.
            Div(
                learning_level_select,
                cls="flex flex-wrap items-center gap-2 pt-1",
                style="display:none",
                x_show="moreFilters",
            ),
            # Row 3: tags — nested Alpine scope for the expander; setTag stays
            # reachable from the parent exploreSearch scope. Starts expanded
            # when the active tag would otherwise be hidden in the overflow.
            Div(
                *tag_chips,
                cls="flex flex-wrap gap-1.5",
                **(
                    {
                        "x_data": "{ showAllTags: "
                        + json.dumps(bool(active_tag) and active_tag in overflow_tags)
                        + " }"
                    }
                    if overflow_tags
                    else {}
                ),
            )
            if tag_chips
            else None,
            # Hidden input for active tag
            Input(name="tag", type="hidden", **{"x-bind:value": "activeTag"}),
            cls="flex flex-col gap-3",
            id="explore-search-form",
        ),
        cls="p-4 mb-5 border border-border rounded-xl bg-background flex flex-col gap-3",
        x_data=f"exploreSearch({json.dumps(active_tag)})",
        x_init="init()",
    )
