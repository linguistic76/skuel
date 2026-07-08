"""
Search UI Components
====================

UI components for the search page with horizontal filter layout.
Extracted from search_routes.py for separation of concerns.

Design Philosophy:
    "Users can handle complexity, but they need visual calm to process it."

Uses semantic HTML with TailwindCSS.

Usage:
    from ui.search.components import (
        render_search_page_with_navbar,
        render_search_results,
    )

Version: 3.0.0 - Horizontal filters layout
"""

__version__ = "3.0"

from html import escape
from typing import Any

from fasthtml.common import H3, H4, A, Div, NotStr, P, Span

from core.models.enums import (
    ContentType,
    EducationalLevel,
    LearningLevel,
    SELCategory,
)
from core.models.search_request import SearchResponse
from ui.components import ButtonT, Card, Icon
from ui.enum_helpers import (
    get_content_icon,
    get_educational_icon,
    get_sel_icon,
)
from ui.feedback import Badge, BadgeT
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.empty_state import EmptyState
from ui.patterns.entity_links import entity_detail_href
from ui.primitives import ButtonLink
from ui.tokens import Container

# ============================================================================
# PAGE LAYOUT COMPONENTS
# ============================================================================


async def render_search_page_with_navbar(
    request: Any = None,
    nous_topics: list[str] | None = None,
    nous_subtopics: list[str] | None = None,
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
            graph (route fetches via KuService.list_nous_subtopics). Empty until
            the vault carries `nous_subtopic:` data — the control fails soft to
            nothing on an empty list.
        ask_enabled: FULL-tier gate for the "Ask" button (hands the query +
            nous facet to scoped Askesis). Hidden in CORE tier.

    Returns:
        Complete HTML page using unified BasePage layout
    """
    content = _render_search_layout(nous_topics or [], nous_subtopics or [], ask_enabled)

    return await BasePage(
        content=content,
        title="Search",
        page_type=PageType.STANDARD,
        request=request,
        active_page="search",
        extra_css=["/static/css/search.css"],
    )


def _render_search_layout(
    nous_topics: list[str], nous_subtopics: list[str], ask_enabled: bool = False
) -> Div:
    """
    Two-column search layout: a left rail of faucets beside the results.

    The query box (+ Ask verb) and active-filter badges span the top; below them a
    responsive grid places the filter faucets (Tier 1 filter bar + Tier 2 context
    filters) in a sticky left rail and the results in the main column. Collapses to
    a single stacked column on narrow viewports (see search.css `.search-layout`).
    Faucet markup and every hx-get/hx-include are unchanged — this is layout only.
    Alpine.js still drives filter visibility and expand/collapse.
    """
    return Div(
        Div(
            # Search Input (+ Ask verb when FULL tier) — spans the top
            NotStr(_render_search_input(ask_enabled)),
            # Active Filter Badges — below the query, above the rail/results
            NotStr(_render_active_filter_badges()),
            # Two-column grid: left rail (faucets) + results
            Div(
                # Left rail — Tier 1 filter bar + Tier 2 context filters
                Div(
                    NotStr(_render_filter_bar(nous_topics, nous_subtopics)),
                    NotStr(_render_context_filters()),
                    cls="search-rail",
                ),
                # Results column
                Div(
                    Div(
                        P("🔍", cls="text-5xl mb-4"),
                        P("Enter a search query to begin", cls="text-xl"),
                        P(
                            "Use the filters on the left to refine your results",
                            cls="text-sm mt-2 text-muted-foreground",
                        ),
                        cls="text-center text-muted-foreground py-16",
                    ),
                    id="search-results",
                    cls="search-results-col min-w-0",
                ),
                cls="search-layout",
            ),
            cls=f"search-main {Container.WIDE} px-4 py-8",
        ),
        cls="search-container",
        **{"x-data": "searchFilters()"},
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
]


def _get_hx_include(*exclude: str) -> str:
    """Build hx-include string for HTMX, excluding the named filter(s)."""
    excluded = set(exclude)
    names = [n for n in ALL_FILTER_NAMES if n not in excluded]
    return ", ".join(f"[name='{n}']" for n in names)


def _render_filter_bar(nous_topics: list[str], nous_subtopics: list[str]) -> str:
    """
    Render Tier 1: Primary filters always visible.

    Contains: Type, Nous, Sort dropdowns + Learning Progress and Graph Relationships checkboxes.
    """
    return f"""
    <div class="filter-bar panel-surface p-4 mb-4">
        <!-- Dropdowns Row -->
        <div class="flex flex-wrap gap-4 items-end mb-4">
            <!-- Entity Type -->
            <div class="space-y-2 flex-1 min-w-[150px]">
                <label class="label py-1">
                    <span class="text-xs font-semibold uppercase tracking-wide">Type</span>
                </label>
                {_render_entity_type_select()}
            </div>

            <!-- Nous -->
            <div class="space-y-2 flex-1 min-w-[150px]">
                <label class="label py-1">
                    <span class="text-xs font-semibold uppercase tracking-wide">Nous</span>
                </label>
                {_render_nous_select(nous_topics)}
            </div>

            {_render_nous_subtopic_select(nous_subtopics)}

            <!-- Sort Order -->
            <div class="space-y-2 flex-1 min-w-[150px]">
                <label class="label py-1">
                    <span class="text-xs font-semibold uppercase tracking-wide">Sort</span>
                </label>
                {_render_sort_select()}
            </div>
        </div>

        <!-- Checkbox Groups Row -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 pt-3 border-t border-border">
            <!-- Learning Progress -->
            <div>
                <div class="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Learning Progress</div>
                <div class="flex flex-wrap gap-x-4 gap-y-1">
                    {_render_learning_progress_checkboxes()}
                </div>
            </div>

            <!-- Graph Relationships -->
            <div>
                <div class="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Graph Relationships</div>
                <div class="flex flex-wrap gap-x-4 gap-y-1">
                    {_render_relationship_checkboxes()}
                </div>
            </div>

            <!-- Semantic Search -->
            <div>
                <div class="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Semantic Search
                    <span class="inline-flex items-center rounded-full border font-medium text-[10px] px-1.5 py-0 bg-primary/10 text-primary border-primary/20 ml-1">NEW</span>
                </div>
                <div class="flex flex-wrap gap-x-4 gap-y-1">
                    {_render_semantic_search_checkboxes()}
                </div>
            </div>
        </div>
    </div>
    """


def _render_entity_type_select() -> str:
    """Entity Type dropdown for horizontal bar."""
    entity_types = [
        ("", "All Types"),
        ("ku", "Knowledge Units"),
        ("ps", "Path Steps"),
        ("lp", "Learning Paths"),
        ("task", "Tasks"),
        ("goal", "Goals"),
        ("habit", "Habits"),
        ("event", "Events"),
        ("choice", "Choices"),
        ("principle", "Principles"),
        ("user_entry", "My Entries"),
    ]

    options = "\n".join(
        f'<option value="{escape(value, quote=True)}">{escape(label)}</option>'
        for value, label in entity_types
    )

    return f"""
    <select name="entity_type" class="select select-bordered select-sm w-full"
            hx-get="/search/results"
            hx-trigger="change"
            hx-target="#search-results"
            hx-include="{_get_hx_include("entity_type")}"
            x-model="entityType">
        {options}
    </select>
    """


def _render_nous_select(nous_topics: list[str]) -> str:
    """NOUS topic dropdown for Tier 1 filter bar.

    Options are DERIVED from the graph (KuService.list_nous_topics), never
    hardcoded — the facet cannot drift from the vault vocabulary.

    Changing NOUS fires TWO concurrent HTMX requests: this select re-runs
    ``/search/results`` (below) AND the dependent sub-topic column re-fetches
    ``/search/subtopics`` (via ``change from:[name='nous']``). This request
    EXCLUDES ``nous_subtopic`` from its include set on purpose — a new NOUS
    topic invalidates the old sub-topic, so results must re-scope by NOUS alone
    rather than carry a now-orphaned sub-topic value while the column resets.
    """
    sections = [("", "All Nous")] + [(topic, topic.title()) for topic in nous_topics]
    options = "\n".join(
        f'<option value="{escape(value, quote=True)}">{escape(label)}</option>'
        for value, label in sections
    )
    return f"""
    <select name="nous" class="select select-bordered select-sm w-full"
            hx-get="/search/results"
            hx-trigger="change"
            hx-target="#search-results"
            hx-include="{_get_hx_include("nous", "nous_subtopic")}">
        {options}
    </select>
    """


NOUS_SUBTOPIC_COLUMN_ID = "nous-subtopic-column"


def render_nous_subtopic_inner(nous_subtopics: list[str]) -> str:
    """Inner label + select for the sub-topic column (the HTMX-swapped fragment).

    Options are DERIVED from the graph, never hardcoded (content boundary). The
    ``/search/subtopics`` endpoint re-renders THIS fragment scoped to the chosen
    NOUS topic; the initial page render passes the full flat vocabulary.

    Fail-soft: an empty ``nous_subtopics`` (a NOUS topic with no authored
    sub-topics, or none authored at all) yields just the "All Sub-topics" option
    — the column stays present and stable so the dependent HTMX target never
    vanishes mid-interaction, it simply has nothing to narrow by.
    """
    sections = [("", "All Sub-topics")] + [
        (sub, sub.replace("-", " ").title()) for sub in nous_subtopics
    ]
    options = "\n".join(
        f'<option value="{escape(value, quote=True)}">{escape(label)}</option>'
        for value, label in sections
    )
    return f"""
        <label class="label py-1">
            <span class="text-xs font-semibold uppercase tracking-wide">Sub-topic</span>
        </label>
        <select name="nous_subtopic" class="select select-bordered select-sm w-full"
                hx-get="/search/results"
                hx-trigger="change"
                hx-target="#search-results"
                hx-include="{_get_hx_include("nous_subtopic")}">
            {options}
        </select>
    """


def _render_nous_subtopic_select(nous_subtopics: list[str]) -> str:
    """NOUS sub-topic column (2nd taxonomy level), dependent on the NOUS topic.

    DERIVED from the graph (KuService.list_nous_subtopics / nous_subtopic_map),
    never hardcoded. Fails soft: with no authored `nous_subtopic` data at all the
    column renders NOTHING (no orphan control) — the mechanism ships ahead of
    the vault content.

    Dependent wiring: the stable container listens for changes on the NOUS
    select (``change from:[name='nous']``) and re-fetches ``/search/subtopics``,
    swapping its own innerHTML with the sub-topics scoped to the chosen topic.
    Pure HTMX — no Alpine window-global seeding (see the fragment-seed timing
    trap). ``hx-include`` carries only ``nous`` so the endpoint can scope.
    """
    if not nous_subtopics:
        return ""
    return f"""
    <!-- Nous Sub-topic (dependent on Nous topic) -->
    <div id="{NOUS_SUBTOPIC_COLUMN_ID}" class="space-y-2 flex-1 min-w-[150px]"
         hx-get="/search/subtopics"
         hx-trigger="change from:[name='nous']"
         hx-target="#{NOUS_SUBTOPIC_COLUMN_ID}"
         hx-swap="innerHTML"
         hx-include="[name='nous']">
        {render_nous_subtopic_inner(nous_subtopics)}
    </div>
    """


def _render_sort_select() -> str:
    """Sort order dropdown for horizontal bar."""
    sort_options = [
        ("relevance", "Relevance"),
        ("created_desc", "Newest First"),
        ("created_asc", "Oldest First"),
        ("updated_desc", "Recently Updated"),
        ("priority_desc", "Highest Priority"),
        ("due_date_asc", "Due Date (Soonest)"),
        ("progress_desc", "Most Progress"),
        ("streak_desc", "Longest Streak"),
    ]

    options = "\n".join(
        f'<option value="{escape(value, quote=True)}">{escape(label)}</option>'
        for value, label in sort_options
    )

    return f"""
    <select name="sort_order" class="select select-bordered select-sm w-full"
            hx-get="/search/results"
            hx-trigger="change"
            hx-target="#search-results"
            hx-include="{_get_hx_include("sort_order")}">
        {options}
    </select>
    """


def _render_context_filters() -> str:
    """
    Render Tier 2: Context filters based on entity type selection.

    Shows different filters depending on whether Activity or Curriculum domain.
    """
    return f"""
    <!-- Context Filters (shown based on entity type) -->
    <div class="context-filters panel-surface p-4 mb-4"
         x-show="showContextFilters"
         x-transition:enter="transition ease-out duration-200"
         x-transition:enter-start="opacity-0 -translate-y-2"
         x-transition:enter-end="opacity-100 translate-y-0"
         x-transition:leave="transition ease-in duration-150"
         x-transition:leave-start="opacity-100 translate-y-0"
         x-transition:leave-end="opacity-0 -translate-y-2">

        <div class="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3">
            <span x-text="contextFilterLabel">Filters</span>
        </div>

        <div class="flex flex-wrap gap-4">
            <!-- Common Filters (Activity domains) -->
            <div class="space-y-2 min-w-[140px]" x-show="isFilterVisible('status')" x-transition>
                <label class="label py-0.5">
                    <span class="text-sm font-medium">Status</span>
                </label>
                {_render_status_select()}
            </div>

            <div class="space-y-2 min-w-[140px]" x-show="isFilterVisible('priority')" x-transition>
                <label class="label py-0.5">
                    <span class="text-sm font-medium">Priority</span>
                </label>
                {_render_priority_select()}
            </div>

            <!-- Domain-Specific -->
            <div class="space-y-2 min-w-[140px]" x-show="isFilterVisible('frequency')" x-transition>
                <label class="label py-0.5">
                    <span class="text-sm font-medium">Frequency</span>
                </label>
                {_render_frequency_select()}
            </div>

            <div class="space-y-2 min-w-[140px]" x-show="isFilterVisible('event_type')" x-transition>
                <label class="label py-0.5">
                    <span class="text-sm font-medium">Event Type</span>
                </label>
                {_render_event_type_select()}
            </div>

            <div class="space-y-2 min-w-[140px]" x-show="isFilterVisible('urgency')" x-transition>
                <label class="label py-0.5">
                    <span class="text-sm font-medium">Urgency</span>
                </label>
                {_render_urgency_select()}
            </div>

            <div class="space-y-2 min-w-[140px]" x-show="isFilterVisible('strength')" x-transition>
                <label class="label py-0.5">
                    <span class="text-sm font-medium">Strength</span>
                </label>
                {_render_strength_select()}
            </div>

            <!-- Knowledge Filters (Curriculum domains) -->
            <div class="space-y-2 min-w-[140px]" x-show="isFilterVisible('sel_category')" x-transition>
                <label class="label py-0.5">
                    <span class="text-sm font-medium">SEL Category</span>
                </label>
                {_render_sel_select()}
            </div>

            <div class="space-y-2 min-w-[140px]" x-show="isFilterVisible('learning_level')" x-transition>
                <label class="label py-0.5">
                    <span class="text-sm font-medium">Learning Level</span>
                </label>
                {_render_learning_level_select()}
            </div>

            <div class="space-y-2 min-w-[140px]" x-show="isFilterVisible('content_type')" x-transition>
                <label class="label py-0.5">
                    <span class="text-sm font-medium">Content Type</span>
                </label>
                {_render_content_type_select()}
            </div>

            <div class="space-y-2 min-w-[140px]" x-show="isFilterVisible('educational_level')" x-transition>
                <label class="label py-0.5">
                    <span class="text-sm font-medium">Educational Level</span>
                </label>
                {_render_educational_level_select()}
            </div>
        </div>
    </div>
    """


def _render_status_select() -> str:
    """Status dropdown for context filters."""
    statuses = [
        ("", "All"),
        ("draft", "Draft"),
        ("scheduled", "Scheduled"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]
    options = "\n".join(
        f'<option value="{escape(value, quote=True)}">{escape(label)}</option>'
        for value, label in statuses
    )
    return f"""
    <select name="status" class="select select-bordered select-sm w-full"
            hx-get="/search/results" hx-trigger="change" hx-target="#search-results"
            hx-include="{_get_hx_include("status")}">
        {options}
    </select>
    """


def _render_priority_select() -> str:
    """Priority dropdown for context filters."""
    priorities = [
        ("", "All"),
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("critical", "Critical"),
    ]
    options = "\n".join(
        f'<option value="{escape(value, quote=True)}">{escape(label)}</option>'
        for value, label in priorities
    )
    return f"""
    <select name="priority" class="select select-bordered select-sm w-full"
            hx-get="/search/results" hx-trigger="change" hx-target="#search-results"
            hx-include="{_get_hx_include("priority")}">
        {options}
    </select>
    """


def _render_frequency_select() -> str:
    """Frequency dropdown for Habits."""
    frequencies = [
        ("", "All"),
        ("daily", "Daily"),
        ("2-3x_week", "2-3x/Week"),
        ("weekly", "Weekly"),
        ("bi_weekly", "Bi-weekly"),
        ("monthly", "Monthly"),
    ]
    options = "\n".join(
        f'<option value="{escape(value, quote=True)}">{escape(label)}</option>'
        for value, label in frequencies
    )
    return f"""
    <select name="frequency" class="select select-bordered select-sm w-full"
            hx-get="/search/results" hx-trigger="change" hx-target="#search-results"
            hx-include="{_get_hx_include("frequency")}">
        {options}
    </select>
    """


def _render_event_type_select() -> str:
    """Event Type dropdown for Events."""
    event_types = [
        ("", "All"),
        ("meeting", "Meeting"),
        ("deadline", "Deadline"),
        ("milestone", "Milestone"),
        ("practice", "Practice"),
        ("review", "Review"),
    ]
    options = "\n".join(
        f'<option value="{escape(value, quote=True)}">{escape(label)}</option>'
        for value, label in event_types
    )
    return f"""
    <select name="event_type" class="select select-bordered select-sm w-full"
            hx-get="/search/results" hx-trigger="change" hx-target="#search-results"
            hx-include="{_get_hx_include("event_type")}">
        {options}
    </select>
    """


def _render_urgency_select() -> str:
    """Urgency dropdown for Choices."""
    urgencies = [
        ("", "All"),
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("critical", "Critical"),
    ]
    options = "\n".join(
        f'<option value="{escape(value, quote=True)}">{escape(label)}</option>'
        for value, label in urgencies
    )
    return f"""
    <select name="urgency" class="select select-bordered select-sm w-full"
            hx-get="/search/results" hx-trigger="change" hx-target="#search-results"
            hx-include="{_get_hx_include("urgency")}">
        {options}
    </select>
    """


def _render_strength_select() -> str:
    """Strength dropdown for Principles."""
    strengths = [
        ("", "All"),
        ("exploring", "Exploring"),
        ("developing", "Developing"),
        ("strong", "Strong"),
        ("core", "Core"),
    ]
    options = "\n".join(
        f'<option value="{escape(value, quote=True)}">{escape(label)}</option>'
        for value, label in strengths
    )
    return f"""
    <select name="strength" class="select select-bordered select-sm w-full"
            hx-get="/search/results" hx-trigger="change" hx-target="#search-results"
            hx-include="{_get_hx_include("strength")}">
        {options}
    </select>
    """


def _render_sel_select() -> str:
    """SEL Category dropdown for curriculum."""
    options = '<option value="">All</option>\n'
    for cat in SELCategory:
        icon = get_sel_icon(cat.value)
        options += (
            f'<option value="{cat.value}">{icon} {cat.value.replace("_", " ").title()}</option>\n'
        )
    return f"""
    <select name="sel_category" class="select select-bordered select-sm w-full"
            hx-get="/search/results" hx-trigger="change" hx-target="#search-results"
            hx-include="{_get_hx_include("sel_category")}">
        {options}
    </select>
    """


def _render_learning_level_select() -> str:
    """Learning Level dropdown for curriculum."""
    options = '<option value="">All</option>\n'
    for level in LearningLevel:
        options += f'<option value="{level.value}">{level.value.capitalize()}</option>\n'
    return f"""
    <select name="learning_level" class="select select-bordered select-sm w-full"
            hx-get="/search/results" hx-trigger="change" hx-target="#search-results"
            hx-include="{_get_hx_include("learning_level")}">
        {options}
    </select>
    """


def _render_content_type_select() -> str:
    """Content Type dropdown for curriculum."""
    options = '<option value="">All</option>\n'
    for ctype in ContentType:
        icon = get_content_icon(ctype.value)
        options += f'<option value="{ctype.value}">{icon} {ctype.value.capitalize()}</option>\n'
    return f"""
    <select name="content_type" class="select select-bordered select-sm w-full"
            hx-get="/search/results" hx-trigger="change" hx-target="#search-results"
            hx-include="{_get_hx_include("content_type")}">
        {options}
    </select>
    """


def _render_educational_level_select() -> str:
    """Educational Level dropdown for curriculum."""
    options = '<option value="">All</option>\n'
    for level in EducationalLevel:
        icon = get_educational_icon(level.value)
        options += f'<option value="{level.value}">{icon} {level.value.replace("_", " ").title()}</option>\n'
    return f"""
    <select name="educational_level" class="select select-bordered select-sm w-full"
            hx-get="/search/results" hx-trigger="change" hx-target="#search-results"
            hx-include="{_get_hx_include("educational_level")}">
        {options}
    </select>
    """


def _render_learning_progress_checkboxes() -> str:
    """Learning progress checkboxes."""
    filters = [
        ("not_yet_viewed", "Not yet seen"),
        ("viewed_not_mastered", "In progress"),
        ("ready_to_review", "Ready to review"),
    ]

    result = ""
    for name, label in filters:
        result += f"""
        <label class="label cursor-pointer justify-start gap-2 py-1">
            <input type="checkbox" name="{name}" value="true" class="checkbox checkbox-primary checkbox-sm"
                   hx-get="/search/results" hx-trigger="change" hx-target="#search-results"
                   hx-include="{_get_hx_include(name)}">
            <span class="text-sm font-medium">{label}</span>
        </label>
        """
    return result


def _render_relationship_checkboxes() -> str:
    """Graph relationship checkboxes."""
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

    result = ""
    for name, label in filters:
        result += f"""
        <label class="label cursor-pointer justify-start gap-2 py-0.5">
            <input type="checkbox" name="{name}" value="true" class="checkbox checkbox-primary checkbox-sm"
                   hx-get="/search/results" hx-trigger="change" hx-target="#search-results"
                   hx-include="{_get_hx_include(name)}">
            <span class="text-sm font-medium">{label}</span>
        </label>
        """
    return result


def _render_semantic_search_checkboxes() -> str:
    """
    Semantic search checkboxes.

    Enables semantic relationship boosting and learning-aware search.
    """
    filters = [
        ("enable_semantic_boost", "Semantic boost"),
        ("enable_learning_aware", "Learning-aware"),
        ("prefer_unmastered", "Prefer new content"),
    ]

    result = ""
    for name, label in filters:
        result += f"""
        <label class="label cursor-pointer justify-start gap-2 py-0.5">
            <input type="checkbox" name="{name}" value="true" class="checkbox checkbox-primary checkbox-sm"
                   hx-get="/search/results" hx-trigger="change" hx-target="#search-results"
                   hx-include="{_get_hx_include(name)}">
            <span class="text-sm font-medium">{label}</span>
        </label>
        """
    return result


def _render_active_filter_badges() -> str:
    """
    Render active filter badges with clear buttons.

    Shows pill badges for all non-default filter values.
    """
    return """
    <!-- Active Filter Badges -->
    <div class="active-filters mb-4" x-show="hasActiveFilters" x-transition>
        <div class="flex flex-wrap items-center gap-2">
            <span class="text-xs text-muted-foreground">Active filters:</span>

            <!-- Entity Type Badge -->
            <template x-if="entityType">
                <span class="inline-flex items-center rounded-full border font-medium text-xs px-2 py-0.5 bg-primary/10 text-primary border-primary/20 gap-1">
                    <span x-text="getFilterLabel('entity_type', entityType)"></span>
                    <button type="button" class="hover:text-error" x-on:click="clearFilter('entity_type')">×</button>
                </span>
            </template>

            <!-- Dynamic filter badges would be added here via JavaScript -->

            <!-- Clear All Button -->
            <button type="button"
                    class="inline-flex items-center justify-center font-medium transition-colors h-8 px-3 text-sm rounded-md hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring text-error"
                    x-on:click="clearAllFilters()"
                    x-show="hasActiveFilters">
                Clear All
            </button>
        </div>
    </div>
    """


def _render_search_input(ask_enabled: bool = False) -> str:
    """
    Render the main search input, with an optional "Ask" verb beside "Find".

    "Find" stays the live faceted search (the input searches on keyup). "Ask"
    (FULL tier only) hands the current query + nous facet to scoped Askesis via a
    full-page navigation to /askesis?question=&nous= — see ``searchFilters.askHref``.
    """
    hx_include = _get_hx_include("query")

    ask_button = ""
    if ask_enabled:
        ask_button = f"""
            <button type="button"
                    class="btn btn-primary gap-2 shrink-0"
                    x-on:click="window.location.href = askHref()"
                    title="Ask Askesis with your query and topic scope">
                {Icon("sparkles", size=18, cls="inline-block")}
                <span>Ask</span>
            </button>
        """

    return f"""
    <!-- Search Input -->
    <div class="search-input-container panel-surface p-4">
        <div class="flex items-center gap-2">
            <div class="relative flex-1">
                <span class="absolute inset-y-0 left-3 flex items-center text-foreground/40">
                    {Icon("search", size=20, cls="inline-block")}
                </span>
                <input type="text"
                       name="query"
                       placeholder="Search across all your knowledge..."
                       class="input input-bordered w-full pl-10 pr-4"
                       hx-get="/search/results"
                       hx-trigger="keyup changed delay:500ms"
                       hx-target="#search-results"
                       hx-include="{hx_include}">
            </div>
            {ask_button}
        </div>
    </div>
    """


# ============================================================================
# SEARCH RESULTS COMPONENTS
# ============================================================================


def render_search_results(response: SearchResponse) -> Any:
    """Render search results with calm design."""
    if not response.has_results():
        return Div(
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
        # Results header — count summary only. Sort lives in the persistent left
        # rail (_render_sort_select): a second sort_order <select> here would sit
        # INSIDE #search-results — resetting to its default on every swap and
        # colliding with the rail's control on hx-include (duplicate sort_order
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
            cls="mb-6",
        ),
        # Results grid with generous spacing
        Div(
            *[_render_result_card(result) for result in response.results],
            cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
        ),
        # Pagination — shown whenever the result set spans more than one page, so
        # the LAST page still offers Previous (has_more_pages() is False there).
        _render_pagination(response) if response.get_page_info()["total_pages"] > 1 else None,
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
            cls="bg-background shadow-sm hover:shadow-md transition-shadow border border-border p-6",
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

    The previous version was inert: it put the offset in an ``href`` that
    ``hx-get`` ignores (so the page never advanced), named a non-existent
    ``domain`` field in ``hx-include`` while dropping most real filters, and the
    numbered page links carried no ``hx-get`` at all.
    """
    page_info = response.get_page_info()
    current_page = page_info["current_page"]
    total_pages = page_info["total_pages"]
    include = _get_hx_include()  # all filters — pagination must carry every facet

    # SKUEL button class strings (mirror ui.components.Button + ButtonT, size="sm").
    btn_sm = (
        "inline-flex items-center justify-center font-medium transition-colors h-8 px-3 "
        "text-sm rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    )
    btn_outline = "border border-input bg-background hover:bg-accent hover:text-accent-foreground"
    btn_primary = "bg-primary text-primary-foreground hover:bg-primary/90"
    btn_disabled = "pointer-events-none opacity-50"

    def page_link(label: str, offset: int, *, disabled: bool = False, current: bool = False) -> Any:
        """One pagination control. Current page and disabled ends are inert Spans;
        the rest are HTMX links that swap #search-results for the target offset."""
        if current:
            return Span(label, cls=f"{btn_sm} {btn_primary}")
        if disabled:
            return Span(label, cls=f"{btn_sm} {btn_disabled}")
        return A(
            label,
            hx_get="/search/results",
            hx_vals=f'{{"offset": {offset}}}',
            hx_include=include,
            hx_target="#search-results",
            cls=f"{btn_sm} {btn_outline}",
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
        description="Type a query, or use the filters on the left to browse — a filter alone is enough.",
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
