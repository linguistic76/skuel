"""
Search UI Components
====================

FastHTML components for the search page: query box (+ optional Ask verb),
horizontal filter bar (off-canvas drawer on mobile), active-filter badges,
results grid, and pagination.

Design Philosophy:
    "Users can handle complexity, but they need visual calm to process it."

Built entirely from the shared component library (ui.components / ui.feedback /
ui.primitives) — no raw-HTML strings. Two other files key off the markup here:
`searchFilters` in static/js/skuel.js (Alpine state: drawer, More-filters
toggle, active-filter count, Ask href) and static/css/search.css (layout hooks:
.search-filters, .filter-primary, .filter-advanced, .context-filters, ...).
Keep class names and ``name=`` attributes in sync with both.
"""

import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from fasthtml.common import H3, H4, A, Div, Option, P, Span, Template
from fasthtml.common import Button as HtmlButton

if TYPE_CHECKING:
    from fasthtml.common import FT

from core.models.enums import (
    ContentType,
    EducationalLevel,
    EntityType,
    EventType,
    LearningLevel,
    SELCategory,
)
from core.models.search.filter_enums import SearchSortOrder
from core.models.search_request import FacetCount, SearchResponse
from ui.components import (
    Button,
    ButtonT,
    Card,
    Checkbox,
    Icon,
    Input,
    Label,
    Select,
)
from ui.enum_helpers import (
    get_content_icon,
    get_educational_icon,
    get_sel_icon,
)
from ui.feedback import Badge, BadgeT
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.empty_state import EmptyState
from ui.patterns.entity_links import entity_detail_href
from ui.primitives import ButtonLink
from ui.tokens import Container

# ============================================================================
# PAGE LAYOUT COMPONENTS
# ============================================================================


def render_search_page_with_navbar(
    request: Any = None,
    nous_topics: list[str] | None = None,
    nous_subtopics: list[str] | None = None,
    all_tags: list[str] | None = None,
    ask_enabled: bool = False,
) -> Any:
    """
    Main search page with horizontal filters above the search bar.

    Design inspired by:
    - Askesis: Clean filter organization
    - Register: Centered content, generous whitespace
    - Login: Clean typography, minimal colors

    Args:
        request: Starlette request for auto-detection of auth/admin
        nous_topics: NOUS topic vocabulary derived from the graph
            (route fetches via KuService.list_nous_topics)
        nous_subtopics: NOUS sub-topic vocabulary (2nd level) derived from the
            graph (route fetches via SearchRouter.list_nous_subtopics). Render
            gate only — the control starts disabled until a NOUS topic is
            chosen. Empty until the vault carries `nous_subtopic:` data — the
            control fails soft to nothing on an empty list.
        all_tags: Tag vocabulary derived from the graph (route fetches via
            SearchRouter.list_tags — Ku + PathStep distinct tags). Fails soft
            to no Tags control on an empty list.
        ask_enabled: FULL-tier gate for the "Ask" button (hands the query +
            nous facet to scoped Askesis). Hidden in CORE tier.

    Returns:
        Complete HTML page using unified BasePage layout
    """
    content = _render_search_layout(
        nous_topics or [], nous_subtopics or [], all_tags or [], ask_enabled
    )

    return BasePage(
        content=content,
        title="Search",
        page_type=PageType.STANDARD,
        request=request,
        active_page="search",
        extra_css=["/static/css/search.css"],
    )


def _render_search_layout(
    nous_topics: list[str],
    nous_subtopics: list[str],
    all_tags: list[str],
    ask_enabled: bool = False,
) -> Div:
    """
    Horizontal search layout: query box, a compact filter bar, then full-width results.

    The query box (+ Ask verb) spans the top. Below it sits a horizontal filter bar —
    the everyday dropdowns (Type / Nous / Sub-topic / Sort) inline, with the advanced
    facets (learning progress, graph relationships, semantic search, Tier 2 context
    filters) behind a "More filters" toggle. On narrow viewports that whole filter set
    collapses into an off-canvas drawer opened by a "Filters" button (see search.css
    `.search-filters`). Alpine.js (`searchFilters`) drives the toggle, drawer, and
    filter visibility.
    """
    return Div(
        Div(
            # Search Input (+ Ask verb when FULL tier) — spans the top
            _render_search_input(ask_enabled),
            # Filter bar (desktop) / mobile trigger + backdrop + drawer
            *_render_filter_panel(nous_topics, nous_subtopics, all_tags),
            # Active Filter Badges — below the bar, above the results
            _render_active_filter_badges(),
            # Results — full width
            Div(
                Div(
                    P("🔍", cls="text-5xl mb-4"),
                    P("Enter a search query to begin", cls="text-xl"),
                    P(
                        "Use the filters above to refine your results",
                        cls="text-sm mt-2 text-muted-foreground",
                    ),
                    cls="text-center text-muted-foreground py-16",
                ),
                id="search-results",
                cls="min-w-0",
            ),
            cls=f"search-main {Container.WIDE} px-4 py-8",
        ),
        cls="search-container",
        x_data="searchFilters()",
    )


# ============================================================================
# FILTER BAR COMPONENTS (Horizontal Layout)
# ============================================================================


# All filter parameter names for hx-include (excluding current filter)
ALL_FILTER_NAMES = [
    "query",
    # Scope
    "entity_type",
    "sort_order",
    # Common
    "status",
    "priority",
    # Domain-specific
    "frequency",
    "event_type",
    "urgency",
    "strength",
    # Knowledge
    "sel_category",
    "learning_level",
    "content_type",
    "educational_level",
    # NOUS topic
    "nous",
    # NOUS sub-topic (2nd taxonomy level)
    "nous_subtopic",
    # Tag facet (exact values; vocabulary via SearchRouter.list_tags)
    "tags",
    # Learning progress
    "not_yet_viewed",
    "viewed_not_mastered",
    "ready_to_review",
    # Graph relationships
    "ready_to_learn",
    "builds_on_mastered",
    "in_active_path",
    "supports_goals",
    "builds_on_habits",
    "applied_in_tasks",
    "aligned_with_principles",
    "next_logical_step",
    # Semantic enhancement toggles — part of the request like any other facet, so
    # they must ride along on every re-fire (filter change OR pagination). Omitting
    # them here silently dropped them whenever any other control triggered a search.
    "enable_semantic_boost",
    "enable_learning_aware",
    "prefer_unmastered",
]


def _get_hx_include(*exclude: str) -> str:
    """Build hx-include string for HTMX, excluding the named filter(s)."""
    excluded = set(exclude)
    names = [n for n in ALL_FILTER_NAMES if n not in excluded]
    return ", ".join(f"[name='{n}']" for n in names)


def _filter_select(
    name: str,
    options: list[tuple[str, str]],
    *,
    exclude: tuple[str, ...] | None = None,
    attrs: dict[str, Any] | None = None,  # boundary: fasthtml-elements
    **extra: Any,
) -> Any:
    """One faceted-search dropdown: changing it re-runs /search/results.

    HTMX serializes the triggering control itself, so ``hx-include`` carries
    every OTHER filter (``exclude`` defaults to the control's own name — pass a
    wider tuple to also drop dependents, e.g. nous drops nous_subtopic).

    ``attrs`` carries hyphenated attributes (``x-bind:disabled``) that cannot be
    spelled as keywords; a bare ``**{...}`` would instead be read as a candidate
    for ``exclude``, and ``Select``'s own typed keywords (``disabled: bool``)
    reject a narrower value type — hence the FastHTML-boundary ``Any``.
    """
    return Select(
        *[Option(label, value=value) for value, label in options],
        name=name,
        id=name,
        hx_get="/search/results",
        hx_trigger="change",
        hx_target="#search-results",
        hx_include=_get_hx_include(*(exclude if exclude is not None else (name,))),
        **(attrs or {}),
        **extra,
    )


def _bar_label(text: str, *, fr: str) -> Any:
    """Uppercase micro-label above a primary filter-bar dropdown."""
    return Label(
        Span(text, cls="text-xs font-semibold uppercase tracking-wide"),
        fr=fr,
        cls="block py-1",
    )


def _primary_field(label_text: str, control: Any, *, fr: str) -> Div:
    """Label + control column in the primary filter row."""
    return Div(
        _bar_label(label_text, fr=fr),
        control,
        cls="space-y-1 flex-1 min-w-[150px]",
    )


def _render_filter_panel(
    nous_topics: list[str], nous_subtopics: list[str], all_tags: list[str]
) -> tuple[Any, Any, Any]:
    """
    Build the filter surface: (mobile trigger, mobile backdrop, filter panel).

    One set of filter inputs — never duplicated — so ``hx-include``'s ``[name='…']``
    selectors match each control exactly once (a duplicate would double-submit params).
    CSS reshapes the same markup: a static inline bar at ≥1024px, a slide-in drawer
    below that (see search.css). Alpine (`searchFilters`) drives the mobile ``Filters``
    trigger (``filtersOpen``), the desktop ``More filters`` disclosure (``moreFilters``),
    and the live active-filter count on the trigger badge (``filterCount``).

    Layers:
      * Primary row — Type / Nous / Sub-topic / Sort, always visible.
      * Advanced — learning-progress + graph-relationship + semantic checkboxes and the
        Tier 2 context filters; toggled by ``More filters`` on desktop, always shown
        inside the mobile drawer.
    """
    # Mobile: open-filters trigger (hidden on desktop, where the bar is inline)
    mobile_trigger = Div(
        Button(
            Icon("filter", size=16, cls="inline-block"),
            Span("Filters"),
            Badge(
                variant=BadgeT.primary,
                size=Size.sm,
                style="display:none",
                x_show="filterCount > 0",
                x_text="filterCount",
            ),
            type="button",
            size="sm",
            cls=(ButtonT.default, "gap-2"),
            **{"x-on:click": "filtersOpen = true"},
        ),
        cls="lg:hidden mb-4",
    )

    # Mobile drawer backdrop
    backdrop = Div(
        cls="filters-backdrop lg:hidden",
        style="display:none",
        x_show="filtersOpen",
        **{
            "x-on:click": "filtersOpen = false",
            "x-transition:enter": "transition-opacity ease-out duration-200",
            "x-transition:enter-start": "opacity-0",
            "x-transition:enter-end": "opacity-100",
            "x-transition:leave": "transition-opacity ease-in duration-150",
            "x-transition:leave-start": "opacity-100",
            "x-transition:leave-end": "opacity-0",
        },
    )

    # Drawer header (mobile only)
    drawer_header = Div(
        Span("Filters", cls="text-sm font-semibold uppercase tracking-wide"),
        Button(
            "✕",
            type="button",
            size="sm",
            cls=(ButtonT.ghost, "w-8 px-0 rounded-full"),
            aria_label="Close filters",
            **{"x-on:click": "filtersOpen = false"},
        ),
        cls="search-filters-header lg:hidden",
    )

    # Primary dropdowns + the desktop More-filters disclosure
    primary_row = Div(
        _primary_field("Type", _render_entity_type_select(), fr="entity_type"),
        _primary_field("Nous", _render_nous_select(nous_topics), fr="nous"),
        _render_nous_subtopic_select(nous_subtopics),
        _primary_field("Sort", _render_sort_select(), fr="sort_order"),
        # Desktop: reveal/hide the advanced facets (mobile drawer always shows them)
        Button(
            Icon("sliders-horizontal", size=16, cls="inline-block"),
            Span("More filters", x_text="moreFilters ? 'Fewer filters' : 'More filters'"),
            type="button",
            size="sm",
            cls=(ButtonT.ghost, "more-filters-toggle gap-2 shrink-0"),
            style="display:none",
            x_show="isDesktop",
            **{"x-on:click": "moreFilters = !moreFilters"},
        ),
        cls="filter-primary",
    )

    # Advanced facets: desktop toggles via moreFilters; mobile drawer always shows.
    advanced = Div(
        Div(
            _advanced_group("Learning Progress", _learning_progress_checkboxes()),
            _advanced_group("Graph Relationships", _relationship_checkboxes()),
            _advanced_group(
                "Semantic Search",
                _semantic_search_checkboxes(),
                badge=Badge("NEW", variant=BadgeT.primary, size=Size.xs, cls="ml-1"),
            ),
            cls="grid grid-cols-1 md:grid-cols-3 gap-6",
        ),
        _render_tags_filter(all_tags),
        _render_context_filters(),
        cls="filter-advanced",
        style="display:none",
        x_show="isDesktop ? moreFilters : true",
        **{
            "x-transition:enter": "transition ease-out duration-200",
            "x-transition:enter-start": "opacity-0 -translate-y-1",
            "x-transition:enter-end": "opacity-100 translate-y-0",
        },
    )

    # Drawer footer (mobile only)
    drawer_footer = Div(
        Button(
            "Clear all",
            type="button",
            size="sm",
            cls=(ButtonT.ghost, "text-destructive"),
            **{"x-on:click": "clearAllFilters()"},
        ),
        Button(
            "Show results",
            type="button",
            size="sm",
            cls=(ButtonT.primary, "flex-1"),
            **{"x-on:click": "filtersOpen = false"},
        ),
        cls="search-filters-footer lg:hidden",
    )

    # Filter panel: inline bar on desktop, off-canvas drawer on mobile.
    # x-on:change recomputes the active-filter count as any control changes;
    # x-on:htmx:after-swap re-tallies after the dependent sub-topic column is
    # swapped (changing NOUS resets nous_subtopic via an HTMX innerHTML swap,
    # which emits no `change` — without this the count would stay stale).
    panel = Div(
        drawer_header,
        primary_row,
        advanced,
        drawer_footer,
        cls="search-filters",
        **{
            ":class": "{ 'is-open': filtersOpen }",
            # Capture phase: adoptScope must land before the changed control's
            # OWN htmx listener serializes the request, and before the
            # bubble-phase tally below. See searchFilters.adoptScope.
            "x-on:change.capture": "adoptScope($event)",
            "x-on:change": "updateFilterCount()",
            "x-on:htmx:after-swap": "updateFilterCount()",
        },
    )

    return mobile_trigger, backdrop, panel


# Type dropdown vocabulary — the 6 Activity Domains, and nothing else.
#
# The facet redesign (deferred-work.md § "`/search` Facet Redesign") makes this
# ONE surface with ONE job: your lived activity, plus the knowledge behind it.
# Ku is still a live result type — `SEARCH_PAGE_ENTITY_TYPES` in
# adapters/inbound/search_routes.py scopes the RESULTS to these six plus Ku —
# but it is reached through the **Nous** facet, not through this dropdown.
# PathStep, LearningPath and UserEntry left the results in PR #1155; this is the
# matching half, so the dropdown can no longer offer a type the page refuses.
#
# Values are canonical `EntityType` values, per the emission rule
# (ENUM_ARCHITECTURE § Canonical Values vs Aliases): aliases like "ps" stay valid
# INPUT (EntityType.from_string resolves them, so old bookmarks keep working),
# but the system itself emits canonical values only. Taking them from the enum
# rather than typing them makes that true by construction, and makes them
# compare 1:1 against the results' `_domain` stamps in _render_domain_breakdown
# — no translation layer.
#
# ⚠️ This is one of three sites encoding the type vocabulary; the other two are
# `SEARCH_PAGE_ENTITY_TYPES` (the result scope) and `entityTypeFilters` in
# static/js/skuel.js (the facet-group map). tests/unit/test_search_page_scope.py
# derives each from the others so they cannot drift apart silently.
_ENTITY_TYPE_OPTIONS = [
    ("", "All Types"),
    (EntityType.TASK.value, "Tasks"),
    (EntityType.GOAL.value, "Goals"),
    (EntityType.HABIT.value, "Habits"),
    (EntityType.EVENT.value, "Events"),
    (EntityType.CHOICE.value, "Choices"),
    (EntityType.PRINCIPLE.value, "Principles"),
]


# ---------------------------------------------------------------------------
# Mutually exclusive scope facets
# ---------------------------------------------------------------------------
_TYPE_SELECTED = "entityType !== ''"
_TYPE_DISABLED_HINT = (
    "Nous searches knowledge, which carries no activity type — "
    "set Nous to “All Nous” to filter by type"
)
_NOUS_DISABLED_HINT = (
    "A type filter searches your activity, which carries no Nous — "
    "set Type to “All Types” to filter by Nous"
)

# `/search` carries TWO scope facets and only one may be active at a time.
#
# Type narrows to an Activity Domain; Nous narrows to a knowledge topic. Their
# INTERSECTION IS EMPTY BY CONSTRUCTION, not by data: `nous` is an array property
# only curriculum nodes carry, and the faceted sweep applies it as a WHERE clause
# to every swept domain, so `Type=Task, Nous=body` can only ever return zero rows
# — a facet guaranteed to return nothing, the defect class the redesign refuses
# elsewhere (deferred-work.md § "`/search` Facet Redesign", consequence 1).
#
# The mechanism is `disabled`, not clearing the other control, because it makes
# the impossible state UNREACHABLE rather than merely corrected: htmx omits
# disabled elements from a request (`shouldInclude`), so the unused scope is
# absent from the query string rather than sent blank. Same idiom as the
# sub-topic column's "Choose a Nous first" gate.
#
# ⚠️ Alpine's x-model listener and htmx's change trigger are NOT ordered, and
# the request that ENTERS a mode is serialized before the other control is
# disabled — measured in a headless browser, not assumed: choosing a NOUS topic
# sends `entity_type=` (blank, still enabled), and only the next request omits
# it. That is harmless by construction, because a mode is only ever entered from
# the both-empty state (`search_page` seeds no filter values), and blank is
# dropped at `SearchRequest.from_form_params`. What the disabled attribute
# prevents is the control that could carry a CONFLICTING value ever being
# reachable — it was disabled by the PREVIOUS interaction, with a full frame to
# settle.


def _hint_when(condition: str, hint: str) -> str:
    """An Alpine expression yielding ``hint`` while ``condition`` holds, else nothing.

    ``false`` rather than ``''``: Alpine REMOVES an attribute bound to
    false/null (``x-bind`` → ``removeAttribute``), so the enabled control carries
    no empty ``title``. ``json.dumps`` renders the hint as a JS string literal so
    an apostrophe in the copy cannot terminate it.
    """
    return f"{condition} ? {json.dumps(hint, ensure_ascii=False)} : false"


def _render_entity_type_select() -> Any:
    """Entity Type dropdown for the primary filter row.

    Disabled in knowledge mode (a NOUS topic is chosen) — see the
    *Mutually exclusive scope facets* comment above.
    """
    return _filter_select(
        "entity_type",
        _ENTITY_TYPE_OPTIONS,
        x_model="entityType",
        attrs={
            "x-bind:disabled": "isKnowledgeMode",
            "x-bind:title": _hint_when("isKnowledgeMode", _TYPE_DISABLED_HINT),
        },
    )


def _render_nous_select(nous_topics: list[str]) -> Any:
    """NOUS topic dropdown for Tier 1 filter bar — and `/search`'s door to Ku.

    Options are DERIVED from the graph (KuService.list_nous_topics), never
    hardcoded — the facet cannot drift from the vault vocabulary.

    Choosing a topic puts the page in KNOWLEDGE MODE: it is a scope, not a hint.
    Only curriculum nodes carry a `nous` property, so the facet's own WHERE
    clause narrows the result set to Ku — which is why Ku left the Type dropdown
    and is reached here instead, and why the four knowledge context filters
    (SEL Category, Learning Level, Content Type, Educational Level) become
    visible from this control rather than from a type choice
    (`searchFilters.isKnowledgeMode` in static/js/skuel.js). Disabled while a
    Type is selected — see the *Mutually exclusive scope facets* comment block.

    Changing NOUS fires TWO concurrent HTMX requests: this select re-runs
    ``/search/results`` AND the dependent sub-topic column re-fetches
    ``/search/subtopics`` (via ``change from:[name='nous']``). This request
    EXCLUDES ``nous_subtopic`` from its include set on purpose — a new NOUS
    topic invalidates the old sub-topic, so results must re-scope by NOUS alone
    rather than carry a now-orphaned sub-topic value while the column resets.
    """
    options = [("", "All Nous")] + [(topic, topic.title()) for topic in nous_topics]
    return _filter_select(
        "nous",
        options,
        exclude=("nous", "nous_subtopic"),
        x_model="nousTopic",
        attrs={
            "x-bind:disabled": _TYPE_SELECTED,
            "x-bind:title": _hint_when(_TYPE_SELECTED, _NOUS_DISABLED_HINT),
        },
    )


NOUS_SUBTOPIC_COLUMN_ID = "nous-subtopic-column"


def render_nous_subtopic_inner(
    nous_subtopics: list[str], *, nous_selected: bool = True
) -> tuple["FT", "FT"]:
    """Inner label + select for the sub-topic column (the HTMX-swapped fragment).

    Options are DERIVED from the graph, never hardcoded (content boundary). The
    ``/search/subtopics`` endpoint re-renders THIS fragment scoped to the chosen
    NOUS topic. Sub-topics go DEEPER into one topic, so the control is gated on
    a topic being chosen: with ``nous_selected=False`` (initial render, or the
    "All Nous" option) the select is disabled with a "Choose a Nous first"
    placeholder instead of offering the flat cross-topic vocabulary.

    Fail-soft: a chosen NOUS topic with no authored sub-topics yields just a
    disabled "All Sub-topics" option — the column stays present and stable so
    the dependent HTMX target never vanishes mid-interaction, it simply has
    nothing to narrow by. (Disabled selects don't serialize, and both states
    carry only the empty value, so no stale sub-topic ever rides a request.)
    """
    if not nous_selected:
        options = [("", "Choose a Nous first")]
    else:
        options = [("", "All Sub-topics")] + [
            (sub, sub.replace("-", " ").title()) for sub in nous_subtopics
        ]
    disabled = not nous_selected or not nous_subtopics
    return (
        _bar_label("Sub-topic", fr="nous_subtopic"),
        _filter_select("nous_subtopic", options, disabled=disabled),
    )


def _render_nous_subtopic_select(nous_subtopics: list[str]) -> Any | None:
    """NOUS sub-topic column (2nd taxonomy level), dependent on the NOUS topic.

    DERIVED from the graph (KuService.list_nous_subtopics / nous_subtopic_map),
    never hardcoded. ``nous_subtopics`` (the flat vocabulary) acts purely as the
    render GATE here: with no authored `nous_subtopic` data at all the column
    renders NOTHING (no orphan control) — the mechanism ships ahead of the vault
    content. The initial control itself is the DISABLED "Choose a Nous first"
    state, never the flat cross-topic list — sub-topics only mean something
    inside their parent NOUS topic.

    Dependent wiring: the stable container listens for changes on the NOUS
    select (``change from:[name='nous']``) and re-fetches ``/search/subtopics``,
    swapping its own innerHTML with the sub-topics scoped to the chosen topic.
    Pure HTMX — no Alpine window-global seeding (see the fragment-seed timing
    trap). ``hx-include`` carries only ``nous`` so the endpoint can scope.
    """
    if not nous_subtopics:
        return None
    return Div(
        *render_nous_subtopic_inner([], nous_selected=False),
        id=NOUS_SUBTOPIC_COLUMN_ID,
        cls="space-y-2 flex-1 min-w-[150px]",
        hx_get="/search/subtopics",
        hx_trigger="change from:[name='nous']",
        hx_target=f"#{NOUS_SUBTOPIC_COLUMN_ID}",
        hx_swap="innerHTML",
        hx_include="[name='nous']",
    )


def _render_sort_select() -> Any:
    """Sort order dropdown for the primary filter row.

    Options mirror SearchSortOrder exactly — every entry here is honored
    end-to-end by the faceted path. The formerly-listed domain-specific sorts
    (priority/due-date/progress/streak) were never implemented and were
    deleted with them in July 2026 (One Path Forward: no fake options).
    """
    sort_options = [
        (SearchSortOrder.RELEVANCE.value, "Relevance"),
        (SearchSortOrder.CREATED_DESC.value, "Newest First"),
        (SearchSortOrder.CREATED_ASC.value, "Oldest First"),
        (SearchSortOrder.UPDATED_DESC.value, "Recently Updated"),
        (SearchSortOrder.TITLE_ASC.value, "Title A–Z"),
    ]
    return _filter_select("sort_order", sort_options)


def _render_tags_filter(all_tags: list[str]) -> Div | None:
    """Tags facet select for the advanced (More filters) section.

    Vocabulary is DERIVED from the graph (SearchRouter.list_tags — distinct
    Ku + PathStep tags), never hardcoded. Applies across entity types, so it
    sits outside the per-type context filters. Fails soft: no tags in the
    corpus → no control.
    """
    if not all_tags:
        return None
    options = [("", "All Tags")] + [(tag, f"#{tag}") for tag in all_tags]
    return Div(
        Label("Tag", fr="tags", cls="block py-0.5"),
        _filter_select("tags", options),
        cls="space-y-2 min-w-[160px] mt-6 pt-4 border-t border-border",
    )


# ----------------------------------------------------------------------------
# Tier 2 context filters — shown per entity type (Alpine isFilterVisible())
# ----------------------------------------------------------------------------

_STATUS_OPTIONS = [
    ("", "All"),
    ("draft", "Draft"),
    ("scheduled", "Scheduled"),
    ("in_progress", "In Progress"),
    ("completed", "Completed"),
    ("cancelled", "Cancelled"),
]

_PRIORITY_OPTIONS = [
    ("", "All"),
    ("low", "Low"),
    ("medium", "Medium"),
    ("high", "High"),
    ("critical", "Critical"),
]

_FREQUENCY_OPTIONS = [
    ("", "All"),
    ("daily", "Daily"),
    ("2-3x_week", "2-3x/Week"),
    ("weekly", "Weekly"),
    ("bi_weekly", "Bi-weekly"),
    ("monthly", "Monthly"),
]

# Derived from the enum so the facet can never drift from the canonical
# vocabulary again (it used to offer ActivityType names no Event ever carried).
_EVENT_TYPE_OPTIONS = [
    ("", "All"),
    *((t.value, t.value.title()) for t in EventType),
]

_URGENCY_OPTIONS = [
    ("", "All"),
    ("low", "Low"),
    ("medium", "Medium"),
    ("high", "High"),
    ("critical", "Critical"),
]

_STRENGTH_OPTIONS = [
    ("", "All"),
    ("exploring", "Exploring"),
    ("developing", "Developing"),
    ("strong", "Strong"),
    ("core", "Core"),
]


def _sel_category_options() -> list[tuple[str, str]]:
    """SEL Category options with emoji icons (curriculum filter)."""
    return [("", "All")] + [
        (cat.value, f"{get_sel_icon(cat.value)} {cat.value.replace('_', ' ').title()}")
        for cat in SELCategory
    ]


def _learning_level_options() -> list[tuple[str, str]]:
    """Learning Level options (curriculum filter)."""
    return [("", "All")] + [(level.value, level.value.capitalize()) for level in LearningLevel]


def _content_type_options() -> list[tuple[str, str]]:
    """Content Type options with emoji icons (curriculum filter)."""
    return [("", "All")] + [
        (ctype.value, f"{get_content_icon(ctype.value)} {ctype.value.capitalize()}")
        for ctype in ContentType
    ]


def _educational_level_options() -> list[tuple[str, str]]:
    """Educational Level options with emoji icons (curriculum filter)."""
    return [("", "All")] + [
        (
            level.value,
            f"{get_educational_icon(level.value)} {level.value.replace('_', ' ').title()}",
        )
        for level in EducationalLevel
    ]


def _context_field(name: str, label_text: str, options: list[tuple[str, str]]) -> Div:
    """One Tier 2 context filter: label + select, visible per Alpine filter group.

    Disabled whenever it is hidden, and for the same reason the scope facets
    disable each other: ``hx-include`` names every filter on the page, so a
    control the user cannot see still rides every request. Hidden-but-live is
    how a `sel_category` chosen in knowledge mode ends up as a WHERE clause on a
    Task search — guaranteed zero rows, the defect class this surface refuses.
    htmx omits disabled elements, so hiding and withholding stay in step. The
    value is KEPT, not cleared: returning to that scope restores the filter
    visibly, rather than silently dropping what the user chose. (Codex, #1157.)
    """
    return Div(
        Label(label_text, fr=name, cls="block py-0.5"),
        _filter_select(name, options, attrs={"x-bind:disabled": f"!isFilterVisible('{name}')"}),
        cls="space-y-2 min-w-[140px]",
        x_show=f"isFilterVisible('{name}')",
        **{"x-transition": True},
    )


def _render_context_filters() -> Div:
    """
    Render Tier 2: Context filters, keyed to whichever scope facet is active.

    Alpine ``isFilterVisible`` reveals each column: the activity columns from a
    Type choice, the four knowledge columns from a NOUS topic (knowledge mode).
    The two are mutually exclusive (see the *Mutually exclusive scope facets*
    comment block), so at most one group is ever on screen, and the header names
    (``contextFilterLabel``).
    """
    fields = [
        # Common Filters (Activity domains)
        _context_field("status", "Status", _STATUS_OPTIONS),
        _context_field("priority", "Priority", _PRIORITY_OPTIONS),
        # Domain-Specific
        _context_field("frequency", "Frequency", _FREQUENCY_OPTIONS),
        _context_field("event_type", "Event Type", _EVENT_TYPE_OPTIONS),
        _context_field("urgency", "Urgency", _URGENCY_OPTIONS),
        _context_field("strength", "Strength", _STRENGTH_OPTIONS),
        # Knowledge Filters (Curriculum domains)
        _context_field("sel_category", "SEL Category", _sel_category_options()),
        _context_field("learning_level", "Learning Level", _learning_level_options()),
        _context_field("content_type", "Content Type", _content_type_options()),
        _context_field("educational_level", "Educational Level", _educational_level_options()),
    ]
    return Div(
        Div(
            Span("Filters", x_text="contextFilterLabel"),
            cls="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3",
        ),
        Div(*fields, cls="flex flex-wrap gap-4"),
        cls="context-filters mt-6 pt-4 border-t border-border",
        x_show="showContextFilters",
        **{
            "x-transition:enter": "transition ease-out duration-200",
            "x-transition:enter-start": "opacity-0 -translate-y-2",
            "x-transition:enter-end": "opacity-100 translate-y-0",
            "x-transition:leave": "transition ease-in duration-150",
            "x-transition:leave-start": "opacity-100 translate-y-0",
            "x-transition:leave-end": "opacity-0 -translate-y-2",
        },
    )


# ----------------------------------------------------------------------------
# Advanced checkbox facets
# ----------------------------------------------------------------------------


def _filter_checkbox(name: str, label_text: str, *, tight: bool = False) -> Any:
    """One boolean facet: checking it re-runs /search/results with all filters."""
    return Label(
        Checkbox(
            name=name,
            value="true",
            hx_get="/search/results",
            hx_trigger="change",
            hx_target="#search-results",
            hx_include=_get_hx_include(name),
        ),
        Span(label_text, cls="text-sm font-medium"),
        cls=f"flex cursor-pointer items-center gap-2 {'py-0.5' if tight else 'py-1'}",
    )


def _advanced_group(title: str, checkboxes: list[Any], badge: Any = None) -> Div:
    """Titled column of boolean facets in the advanced filter grid."""
    return Div(
        Div(
            title,
            badge,
            cls="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2",
        ),
        Div(*checkboxes, cls="flex flex-wrap gap-x-4 gap-y-1"),
    )


def _learning_progress_checkboxes() -> list[Any]:
    """Learning progress facets (pedagogical tracking)."""
    filters = [
        ("not_yet_viewed", "Not yet seen"),
        ("viewed_not_mastered", "In progress"),
        ("ready_to_review", "Ready to review"),
    ]
    return [_filter_checkbox(name, label) for name, label in filters]


def _relationship_checkboxes() -> list[Any]:
    """Graph relationship facets (traversal-backed filters)."""
    filters = [
        ("ready_to_learn", "Ready to learn"),
        ("builds_on_mastered", "Builds on known"),
        ("in_active_path", "In active path"),
        ("supports_goals", "Supports goals"),
        ("builds_on_habits", "Builds on habits"),
        ("applied_in_tasks", "Applied recently"),
        ("aligned_with_principles", "Aligned with values"),
        ("next_logical_step", "Next logical step"),
    ]
    return [_filter_checkbox(name, label, tight=True) for name, label in filters]


def _semantic_search_checkboxes() -> list[Any]:
    """Semantic enhancement facets (embedding-boosted, learning-aware search)."""
    filters = [
        ("enable_semantic_boost", "Semantic boost"),
        ("enable_learning_aware", "Learning-aware"),
        ("prefer_unmastered", "Prefer new content"),
    ]
    return [_filter_checkbox(name, label, tight=True) for name, label in filters]


def _render_active_filter_badges() -> Div:
    """
    Render active filter badges with clear buttons.

    Shows pill badges for non-default filter values (Alpine-driven).
    """
    return Div(
        Div(
            Span("Active filters:", cls="text-xs text-muted-foreground"),
            # Entity Type Badge
            Template(
                Badge(
                    Span(x_text="getFilterLabel('entity_type', entityType)"),
                    HtmlButton(
                        "×",
                        type="button",
                        cls="ml-1 leading-none opacity-70 hover:opacity-100 hover:text-destructive",
                        **{"x-on:click": "clearFilter('entity_type')"},
                    ),
                    variant=BadgeT.primary,
                    cls="gap-1",
                ),
                x_if="entityType",
            ),
            # Clear All Button
            Button(
                "Clear All",
                type="button",
                size="sm",
                cls=(ButtonT.ghost, "text-destructive"),
                x_show="hasActiveFilters",
                **{"x-on:click": "clearAllFilters()"},
            ),
            cls="flex flex-wrap items-center gap-2",
        ),
        cls="active-filters mb-4",
        x_show="hasActiveFilters",
        **{"x-transition": True},
    )


def _render_search_input(ask_enabled: bool = False) -> Div:
    """
    Render the main search input, with an optional "Ask" verb beside "Find".

    "Find" stays the live faceted search (the input searches on keyup). "Ask"
    (FULL tier only) hands the current query + nous facet to scoped Askesis via a
    full-page navigation to /askesis?question=&nous= — see ``searchFilters.askHref``.
    """
    ask_button = None
    if ask_enabled:
        ask_button = Button(
            Icon("sparkles", size=18, cls="inline-block"),
            Span("Ask"),
            type="button",
            cls=(ButtonT.primary, "gap-2 shrink-0"),
            title="Ask Askesis with your query and topic scope",
            **{"x-on:click": "window.location.href = askHref()"},
        )

    return Div(
        Div(
            Div(
                Span(
                    Icon("search", size=20, cls="inline-block"),
                    cls="absolute inset-y-0 left-3 flex items-center text-foreground/40 pointer-events-none",
                ),
                Input(
                    type="text",
                    name="query",
                    placeholder="Search across all your knowledge...",
                    cls="pl-10 pr-4",
                    hx_get="/search/results",
                    hx_trigger="keyup changed delay:500ms",
                    hx_target="#search-results",
                    hx_include=_get_hx_include("query"),
                ),
                cls="relative flex-1",
            ),
            ask_button,
            cls="flex items-center gap-2",
        ),
        cls="search-input-container panel-surface p-4",
    )


# ============================================================================
# SEARCH RESULTS COMPONENTS
# ============================================================================


def _render_capacity_banner(warnings: Mapping[str, Any]) -> Any | None:
    """Slim advisory strip above the results when the user is stretched.

    Fed by ``SearchResponse.capacity_warnings`` (warm-UserContext-cache only —
    see SearchRouter._peek_capacity_warnings). Empty warnings → no banner.
    """
    messages = [w["message"] for w in warnings.values() if isinstance(w, dict) and w.get("message")]
    if not messages:
        return None
    return Div(
        Span("⚠️", aria_hidden="true"),
        Span(" · ".join(messages)),
        cls=(
            "flex items-start gap-2 rounded-md border border-yellow-200 bg-yellow-50 "
            "text-yellow-800 text-sm px-3 py-2 mb-4"
        ),
    )


def _render_domain_breakdown(response: SearchResponse) -> Any | None:
    """Clickable per-type breakdown chips for a cross-domain result set.

    Fed by ``SearchResponse.facet_counts['entity_type']`` (counts within the
    returned window). Rendered only when the results span more than one type —
    clicking a chip narrows the Type filter (``searchFilters.setEntityType``
    sets the select and re-fires the search).
    """
    entity_counts = response.facet_counts.get("entity_type", [])
    if len(entity_counts) < 2:
        return None

    # Clickable only when the _domain value has a dropdown option — assigning
    # an unknown value to the <select> would CLEAR it (reset to "All Types")
    # instead of narrowing. Stamps and option values both speak canonical
    # EntityType values, so membership is a direct check.
    #
    # ⚠️ Accepted consequence of the facet redesign: **the "Ku" chip is no longer
    # clickable.** Ku is still a live result type but left the Type dropdown, so
    # it falls to the plain Badge below and reports its count without narrowing.
    # That is the honest rendering, not a regression to repair here — the chip
    # can only set the control the dropdown owns, and "narrow to Ku" is not the
    # same act as choosing a Nous topic, which is Ku's door now. Derived FROM
    # _ENTITY_TYPE_OPTIONS on purpose: hard-coding the tokens would make this a
    # fourth vocabulary site.
    dropdown_tokens = {value for value, _ in _ENTITY_TYPE_OPTIONS if value}

    def _chip(fc: FacetCount) -> Any:
        label = f"{fc.display_name or fc.facet_value} {fc.count}"
        if fc.facet_value not in dropdown_tokens:
            return Badge(label, variant=BadgeT.neutral)
        attrs: dict[str, Any] = {"x-on:click": f"setEntityType('{fc.facet_value}')"}
        return Badge(
            label,
            variant=BadgeT.neutral,
            cls="cursor-pointer hover:bg-accent",
            role="button",
            title=f"Show only {fc.display_name or fc.facet_value}",
            **attrs,
        )

    chips = [_chip(fc) for fc in entity_counts]
    return Div(*chips, cls="flex flex-wrap items-center gap-1.5 mt-2")


def render_search_results(response: SearchResponse) -> Any:
    """Render search results with calm design."""
    if not response.has_results():
        return Div(
            _render_capacity_banner(response.capacity_warnings),
            Div(
                P("🔍", cls="text-center text-5xl mb-4"),
                P(
                    f"No results found for '{response.query_text}'",
                    cls="text-center text-xl text-muted-foreground",
                ),
                P(
                    "Try adjusting your filters or search terms",
                    cls="text-center text-sm text-muted-foreground",
                ),
                cls="text-center py-16",
            ),
            id="search-results",
        )

    page_info = response.get_page_info()

    return Div(
        _render_capacity_banner(response.capacity_warnings),
        # Results header — count summary only. Sort lives in the persistent filter
        # bar (_render_sort_select): a second sort_order <select> here would sit
        # INSIDE #search-results — resetting to its default on every swap and
        # colliding with the bar's control on hx-include (duplicate sort_order
        # param, first-wins in Starlette). One control, outside the swap target.
        Div(
            H3(f"Found {response.total} results", cls="text-xl font-bold"),
            P(
                f"Showing {page_info['showing_from']}-{page_info['showing_to']} of {page_info['total_results']}",
                cls="text-muted-foreground text-sm",
            ),
            P(
                f"Search completed in {response.search_time_ms:.0f}ms",
                cls="text-muted-foreground text-xs",
            ),
            _render_domain_breakdown(response),
            cls="mb-6",
        ),
        # Results grid with generous spacing
        Div(
            *[_render_result_card(result) for result in response.results],
            cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
        ),
        # Pagination — shown whenever the result set spans more than one page, so
        # the LAST page still offers Previous (has_more_pages() is False there).
        _render_pagination(response) if page_info["total_pages"] > 1 else None,
        id="search-results",
        cls="mt-4",
    )


def _render_result_card(result: dict) -> Any:
    """
    Render a single search result card with calm design.

    Clean card with:
    - Subtle shadow
    - Generous padding
    - Clear typography
    - Minimal icons
    """
    # ``_domain`` is an EntityType value everywhere (single vocabulary stamped
    # by every SearchRouter producer path) — feed it straight to the badge and
    # to entity_detail_href, THE entity_type → detail-URL mapping.
    domain = result.get("_domain", "unknown")
    title = result.get("title", result.get("name", "Untitled"))
    uid = result.get("uid", "")

    # Get domain-specific fields
    description = result.get("description", result.get("content", ""))
    if description and len(description) > 200:
        description = description[:200] + "..."

    # Minimal domain badge (no emojis in calm design)
    domain_text = domain.replace("_", " ").title()

    # Get graph context if available
    graph_context = result.get("_graph_context")

    # Build card content
    card_body_items = [
        Badge(domain_text, variant=BadgeT.primary, cls="mb-2"),
        H4(title, cls="font-bold text-lg"),
    ]

    # Add description with generous spacing
    if description:
        card_body_items.append(
            P(description, cls="text-sm text-muted-foreground mt-2 leading-relaxed")
        )

    # Add graph context if available
    if graph_context:
        context_element = _render_graph_context(graph_context)
        if context_element:
            card_body_items.append(context_element)

    # Add footer with clean button — href resolved through THE canonical
    # entity_type → detail-URL mapping. The old f"/{domain}/{uid}" template
    # 404'd for every non-Activity domain (/ku/, /pathstep/, /exercise/ are
    # not routes). No detail page → no button, same as shared_view.
    href = entity_detail_href(domain, uid)
    if href:
        card_body_items.append(
            Div(
                ButtonLink("View Details", href=href, cls=ButtonT.ghost, size="sm"),
                cls="mt-4",
            )
        )

    return Div(
        Card(
            *card_body_items,
            cls="bg-background shadow-xs hover:shadow-md transition-shadow border border-border p-6",
        )
    )


def _render_graph_context(context: dict) -> Any | None:
    """
    Render graph relationship context.

    Clean, minimal badges showing:
    - Learning state (viewed, in-progress, mastered)
    - Prerequisites and what it enables
    - Goal alignment
    """
    prerequisites = context.get("prerequisites", [])
    enables = context.get("enables", [])
    supporting_goals = context.get("supporting_goals", [])
    prerequisites_met = context.get("prerequisites_met", False)

    # Learning state (pedagogical tracking)
    learning_state = context.get("learning_state", "not_started")

    items = []

    # Learning state badge (first, most prominent)
    if learning_state == "mastered":
        items.append(
            Badge(
                "✅ Mastered",
                variant=BadgeT.success,
                cls="mr-1",
                title="You have mastered this knowledge",
            )
        )
    elif learning_state == "in_progress":
        items.append(
            Badge(
                "📖 Learning",
                variant=BadgeT.info,
                cls="mr-1",
                title="You are actively learning this",
            )
        )
    elif learning_state == "viewed":
        view_count = context.get("view_count", 0)
        items.append(
            Badge(
                f"👁️ Viewed ({view_count}x)" if view_count > 1 else "👁️ Viewed",
                variant=BadgeT.ghost,
                cls="mr-1",
                title="You have seen this content",
            )
        )
    # Don't show badge for "not_started" - it's the default

    # Prerequisites status
    if prerequisites:
        prereq_icon = "✓" if prerequisites_met else "⚠"
        prereq_variant = BadgeT.success if prerequisites_met else BadgeT.warning
        prereq_text = (
            f"{len(prerequisites)} prerequisites {'met' if prerequisites_met else 'required'}"
        )

        items.append(
            Badge(
                f"{prereq_icon} {prereq_text}",
                variant=prereq_variant,
                cls="mr-1",
                title=", ".join(p.get("title", "Unknown") for p in prerequisites[:3]),
            )
        )

    # What it enables
    if enables:
        items.append(
            Badge(
                f"→ Unlocks {len(enables)} topics",
                variant=BadgeT.ghost,
                cls="mr-1",
                title=", ".join(e.get("title", "Unknown") for e in enables[:3]),
            )
        )

    # Goal alignment
    if supporting_goals:
        items.append(
            Badge(
                f"Supports {len(supporting_goals)} goals",
                variant=BadgeT.primary,
                cls="mr-1",
                title=", ".join(g.get("title", "Unknown") for g in supporting_goals),
            )
        )

    if not items:
        return None

    return Div(
        Div(
            Span("Graph Context: ", cls="font-semibold text-sm mr-2"),
            *items,
            cls="mt-3 p-3 bg-muted rounded-lg border-l-4 border-primary",
        ),
        cls="mt-4",
    )


def _render_pagination(response: SearchResponse) -> Any:
    """Render pagination controls with calm design.

    Each control re-runs ``/search/results`` for the target page's offset,
    passed via ``hx-vals`` (reliably included on GET) plus EVERY active filter
    via ``hx-include`` — so paging preserves the query and all facets.
    """
    page_info = response.get_page_info()
    current_page = page_info["current_page"]
    total_pages = page_info["total_pages"]
    include = _get_hx_include()  # all filters — pagination must carry every facet

    # Compose from the shared button vocabulary: ButtonT carries the style
    # variant; the sm geometry string mirrors ui.components.Button size="sm".
    btn_sm = (
        "inline-flex items-center justify-center font-medium transition-colors h-8 px-3 "
        "text-sm rounded-md focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring"
    )

    def page_link(
        label: str, offset: int, *, disabled: bool = False, current: bool = False
    ) -> "FT":
        """One pagination control. Current page and disabled ends are inert Spans;
        the rest are HTMX links that swap #search-results for the target offset."""
        if current:
            return Span(label, cls=f"{btn_sm} {ButtonT.primary}")
        if disabled:
            return Span(label, cls=f"{btn_sm} pointer-events-none opacity-50")
        return A(
            label,
            hx_get="/search/results",
            hx_vals=f'{{"offset": {offset}}}',
            hx_include=include,
            hx_target="#search-results",
            cls=f"{btn_sm} {ButtonT.default}",
        )

    return Div(
        Div(
            page_link(
                "« Previous",
                max(0, response.offset - response.limit),
                disabled=current_page <= 1,
            ),
            *[
                page_link(str(page), (page - 1) * response.limit, current=(page == current_page))
                for page in range(max(1, current_page - 2), min(total_pages + 1, current_page + 3))
            ],
            page_link(
                "Next »",
                response.offset + response.limit,
                disabled=not response.has_more_pages(),
            ),
            cls="flex justify-center gap-1",
        ),
        cls="mt-12",
    )


# ============================================================================
# UTILITY COMPONENTS
# ============================================================================


def render_empty_search_prompt() -> Div:
    """Render the empty state prompt for search."""
    return EmptyState(
        "Search or pick a filter to begin",
        description="Type a query, or use the filters above to browse — a filter alone is enough.",
        icon="🔍",
        id="search-results",
        cls="py-16",
    )


def render_search_error(message: str, error_type: str = "error") -> Div:
    """Render a search error message."""
    from ui.feedback import Alert, AlertT

    variant_map: dict[str, AlertT] = {
        "error": AlertT.error,
        "warning": AlertT.warning,
        "info": AlertT.info,
        "success": AlertT.success,
    }
    return Div(
        Alert(
            P(message),
            variant=variant_map.get(error_type, AlertT.error),
        ),
        id="search-results",
    )
