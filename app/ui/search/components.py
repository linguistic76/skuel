"""
Search UI Components
====================

UI components for the search page with horizontal filter layout.
Extracted from search_routes.py for separation of concerns.

Design Philosophy:
    "Users can handle complexity, but they need visual calm to process it."

Uses semantic HTML with TailwindCSS + MonsterUI styling.

Usage:
    from ui.search.components import (
        render_search_page_with_navbar,
        render_search_results,
    )

Version: 3.0.0 - Horizontal filters layout
"""

__version__ = "3.0"

from typing import Any

from fasthtml.common import H3, H4, A, Div, NotStr, P, Span

from core.models.enums import (
    ContentType,
    EducationalLevel,
    LearningLevel,
    SELCategory,
)
from core.models.search_request import SearchResponse
from ui.enum_helpers import (
    get_content_icon,
    get_educational_icon,
    get_sel_icon,
)
from ui.feedback import Badge, BadgeT
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType

# ============================================================================
# PAGE LAYOUT COMPONENTS
# ============================================================================


async def render_search_page_with_navbar(request: Any = None) -> Any:
    """
    Main search page with horizontal filters above the search bar.

    Design inspired by:
    - Askesis: Clean filter organization
    - Register: Centered content, generous whitespace
    - Login: Clean typography, minimal colors

    Args:
        request: Starlette request for auto-detection of auth/admin

    Returns:
        Complete HTML page using unified BasePage layout
    """
    content = _render_horizontal_layout()

    return await BasePage(
        content=content,
        title="Search",
        page_type=PageType.STANDARD,
        request=request,
        active_page="search",
        extra_css=["/static/css/search.css"],
    )


def _render_horizontal_layout() -> Div:
    """
    Horizontal filter layout for search.

    Returns the container structure with filters above search bar.
    Uses Alpine.js for filter visibility and expand/collapse.
    """
    return Div(
        Div(
            # Filter Bar (Tier 1 - All filters always visible)
            NotStr(_render_filter_bar()),
            # Context Filters (Tier 2 - Expandable based on entity type)
            NotStr(_render_context_filters()),
            # Active Filter Badges
            NotStr(_render_active_filter_badges()),
            # Search Input
            NotStr(_render_search_input()),
            # Results Container
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
                cls="mt-6",
            ),
            cls="search-main max-w-6xl mx-auto px-4 py-8",
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
    # Nous
    "nous_section",
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


def _get_hx_include(exclude: str = "") -> str:
    """Build hx-include string for HTMX, excluding specified filter."""
    names = [n for n in ALL_FILTER_NAMES if n != exclude]
    return ", ".join(f"[name='{n}']" for n in names)


def _render_filter_bar() -> str:
    """
    Render Tier 1: Primary filters always visible.

    Contains: Type, Nous, Sort dropdowns + Learning Progress and Graph Relationships checkboxes.
    """
    return f"""
    <div class="filter-bar bg-background rounded-lg shadow-sm p-4 mb-4">
        <!-- Dropdowns Row -->
        <div class="flex flex-wrap gap-4 items-end mb-4">
            <!-- Entity Type -->
            <div class="form-control flex-1 min-w-[150px]">
                <label class="label py-1">
                    <span class="label-text text-xs font-semibold uppercase tracking-wide">Type</span>
                </label>
                {_render_entity_type_select()}
            </div>

            <!-- Nous -->
            <div class="form-control flex-1 min-w-[150px]">
                <label class="label py-1">
                    <span class="label-text text-xs font-semibold uppercase tracking-wide">Nous</span>
                </label>
                {_render_nous_select()}
            </div>

            <!-- Sort Order -->
            <div class="form-control flex-1 min-w-[150px]">
                <label class="label py-1">
                    <span class="label-text text-xs font-semibold uppercase tracking-wide">Sort</span>
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
        ("ls", "Learning Steps"),
        ("lp", "Learning Paths"),
        ("moc", "Maps of Content"),
        ("task", "Tasks"),
        ("goal", "Goals"),
        ("habit", "Habits"),
        ("event", "Events"),
        ("choice", "Choices"),
        ("principle", "Principles"),
    ]

    options = "\n".join(
        f'<option value="{value}">{label}</option>' for value, label in entity_types
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


def _render_nous_select() -> str:
    """Nous section dropdown for Tier 1 filter bar."""
    sections = [
        ("", "All Nous"),
        ("stories", "Stories"),
        ("environment", "Environment"),
        ("intelligence", "Intelligence"),
        ("investment", "Investment"),
        ("words", "Words"),
        ("relationships", "Relationships"),
        ("social", "Social"),
        ("body", "Body"),
        ("exercises", "Exercises"),
        ("self_management", "Self-Management"),
        ("self_awareness", "Self-Awareness"),
    ]
    options = "\n".join(f'<option value="{value}">{label}</option>' for value, label in sections)
    return f"""
    <select name="nous_section" class="select select-bordered select-sm w-full"
            hx-get="/search/results"
            hx-trigger="change"
            hx-target="#search-results"
            hx-include="{_get_hx_include("nous_section")}">
        {options}
    </select>
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
        f'<option value="{value}">{label}</option>' for value, label in sort_options
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
    <div class="context-filters bg-background rounded-lg shadow-sm p-4 mb-4"
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
            <div class="form-control min-w-[140px]" x-show="isFilterVisible('status')" x-transition>
                <label class="label py-0.5">
                    <span class="label-text text-xs">Status</span>
                </label>
                {_render_status_select()}
            </div>

            <div class="form-control min-w-[140px]" x-show="isFilterVisible('priority')" x-transition>
                <label class="label py-0.5">
                    <span class="label-text text-xs">Priority</span>
                </label>
                {_render_priority_select()}
            </div>

            <!-- Domain-Specific -->
            <div class="form-control min-w-[140px]" x-show="isFilterVisible('frequency')" x-transition>
                <label class="label py-0.5">
                    <span class="label-text text-xs">Frequency</span>
                </label>
                {_render_frequency_select()}
            </div>

            <div class="form-control min-w-[140px]" x-show="isFilterVisible('event_type')" x-transition>
                <label class="label py-0.5">
                    <span class="label-text text-xs">Event Type</span>
                </label>
                {_render_event_type_select()}
            </div>

            <div class="form-control min-w-[140px]" x-show="isFilterVisible('urgency')" x-transition>
                <label class="label py-0.5">
                    <span class="label-text text-xs">Urgency</span>
                </label>
                {_render_urgency_select()}
            </div>

            <div class="form-control min-w-[140px]" x-show="isFilterVisible('strength')" x-transition>
                <label class="label py-0.5">
                    <span class="label-text text-xs">Strength</span>
                </label>
                {_render_strength_select()}
            </div>

            <!-- Knowledge Filters (Curriculum domains) -->
            <div class="form-control min-w-[140px]" x-show="isFilterVisible('sel_category')" x-transition>
                <label class="label py-0.5">
                    <span class="label-text text-xs">SEL Category</span>
                </label>
                {_render_sel_select()}
            </div>

            <div class="form-control min-w-[140px]" x-show="isFilterVisible('learning_level')" x-transition>
                <label class="label py-0.5">
                    <span class="label-text text-xs">Learning Level</span>
                </label>
                {_render_learning_level_select()}
            </div>

            <div class="form-control min-w-[140px]" x-show="isFilterVisible('content_type')" x-transition>
                <label class="label py-0.5">
                    <span class="label-text text-xs">Content Type</span>
                </label>
                {_render_content_type_select()}
            </div>

            <div class="form-control min-w-[140px]" x-show="isFilterVisible('educational_level')" x-transition>
                <label class="label py-0.5">
                    <span class="label-text text-xs">Educational Level</span>
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
    options = "\n".join(f'<option value="{value}">{label}</option>' for value, label in statuses)
    return f"""
    <select name="status" class="select select-bordered select-xs w-full"
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
    options = "\n".join(f'<option value="{value}">{label}</option>' for value, label in priorities)
    return f"""
    <select name="priority" class="select select-bordered select-xs w-full"
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
    options = "\n".join(f'<option value="{value}">{label}</option>' for value, label in frequencies)
    return f"""
    <select name="frequency" class="select select-bordered select-xs w-full"
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
    options = "\n".join(f'<option value="{value}">{label}</option>' for value, label in event_types)
    return f"""
    <select name="event_type" class="select select-bordered select-xs w-full"
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
    options = "\n".join(f'<option value="{value}">{label}</option>' for value, label in urgencies)
    return f"""
    <select name="urgency" class="select select-bordered select-xs w-full"
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
    options = "\n".join(f'<option value="{value}">{label}</option>' for value, label in strengths)
    return f"""
    <select name="strength" class="select select-bordered select-xs w-full"
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
    <select name="sel_category" class="select select-bordered select-xs w-full"
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
    <select name="learning_level" class="select select-bordered select-xs w-full"
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
    <select name="content_type" class="select select-bordered select-xs w-full"
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
    <select name="educational_level" class="select select-bordered select-xs w-full"
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
            <input type="checkbox" name="{name}" value="true" class="checkbox checkbox-xs checkbox-primary"
                   hx-get="/search/results" hx-trigger="change" hx-target="#search-results"
                   hx-include="{_get_hx_include(name)}">
            <span class="label-text text-xs">{label}</span>
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
            <input type="checkbox" name="{name}" value="true" class="checkbox checkbox-xs checkbox-primary"
                   hx-get="/search/results" hx-trigger="change" hx-target="#search-results"
                   hx-include="{_get_hx_include(name)}">
            <span class="label-text text-xs">{label}</span>
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
            <input type="checkbox" name="{name}" value="true" class="checkbox checkbox-xs checkbox-primary"
                   hx-get="/search/results" hx-trigger="change" hx-target="#search-results"
                   hx-include="{_get_hx_include(name)}">
            <span class="label-text text-xs">{label}</span>
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
                    class="btn btn-ghost btn-xs text-error"
                    x-on:click="clearAllFilters()"
                    x-show="hasActiveFilters">
                Clear All
            </button>
        </div>
    </div>
    """


def _render_search_input() -> str:
    """
    Render the main search input.
    """
    hx_include = _get_hx_include("query")

    return f"""
    <!-- Search Input -->
    <div class="search-input-container bg-background rounded-lg shadow-sm p-4">
        <div class="relative">
            <span class="absolute inset-y-0 left-3 flex items-center text-foreground/40">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
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
    </div>
    """


# ============================================================================
# SEARCH RESULTS COMPONENTS
# ============================================================================


def _render_results_sort_dropdown() -> Any:
    """Render sort dropdown for the results header area."""
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

    return Div(
        Span("Sort:", cls="text-sm text-muted-foreground mr-2"),
        NotStr(f"""
        <select name="sort_order" id="sort-order-results" class="select select-bordered select-xs"
                hx-get="/search/results"
                hx-trigger="change"
                hx-target="#search-results"
                hx-include="{_get_hx_include("sort_order")}">
            {"".join(f'<option value="{v}">{label}</option>' for v, label in sort_options)}
        </select>
        """),
        cls="flex items-center",
    )


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
        # Results header with sort dropdown
        Div(
            # Left side: Results count
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
            ),
            # Right side: Sort dropdown
            _render_results_sort_dropdown(),
            cls="flex justify-between items-start mb-6",
        ),
        # Results grid with generous spacing
        Div(
            *[_render_result_card(result) for result in response.results],
            cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4",
        ),
        # Pagination
        _render_pagination(response) if response.has_more_pages() else None,
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
    domain = result.get("_domain", "unknown")
    title = result.get("title", result.get("name", "Untitled"))
    uid = result.get("uid", "")

    # Get domain-specific fields
    description = result.get("description", result.get("content", ""))
    if description and len(description) > 150:
        description = description[:150] + "..."

    # Minimal domain badge (no emojis in calm design)
    domain_text = domain.title()

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

    # Add footer with clean button
    card_body_items.append(
        Div(
            A("View Details", href=f"/{domain}/{uid}", cls="link link-primary text-sm"),
            cls="mt-4",
        )
    )

    return Div(
        Div(
            *card_body_items,
            cls="card bg-background shadow-sm hover:shadow-md transition-shadow border border-border p-6",
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
    """Render pagination controls with calm design."""
    page_info = response.get_page_info()
    current_page = page_info["current_page"]
    total_pages = page_info["total_pages"]

    return Div(
        Div(
            # Previous button
            A(
                "« Previous",
                href=f"?offset={max(0, response.offset - response.limit)}",
                hx_get="/search/results",
                hx_target="#search-results",
                hx_include="[name='query'], [name='domain'], [name='sel_category'], [name='learning_level'], [name='content_type'], [name='educational_level']",
                cls=f"btn btn-sm {'btn-disabled' if current_page <= 1 else 'btn-outline'}",
            ),
            # Page numbers (show current and surrounding pages)
            *[
                A(
                    str(page),
                    cls=f"btn btn-sm {'btn-primary' if page == current_page else 'btn-ghost'}",
                )
                for page in range(max(1, current_page - 2), min(total_pages + 1, current_page + 3))
            ],
            # Next button
            A(
                "Next »",
                href=f"?offset={response.offset + response.limit}",
                hx_get="/search/results",
                hx_target="#search-results",
                hx_include="[name='query'], [name='domain'], [name='sel_category'], [name='learning_level'], [name='content_type'], [name='educational_level']",
                cls=f"btn btn-sm {'btn-disabled' if not response.has_more_pages() else 'btn-outline'}",
            ),
            cls="join flex justify-center gap-1",
        ),
        cls="mt-12",
    )


# ============================================================================
# UTILITY COMPONENTS
# ============================================================================


def render_empty_search_prompt() -> Div:
    """Render the empty state prompt for search."""
    return Div(
        Div(
            P("🔍", cls="text-center text-5xl mb-4"),
            P("Enter a search query to begin", cls="text-center text-xl text-muted-foreground"),
            P(
                "Use the filters above to refine your results",
                cls="text-center text-sm text-muted-foreground",
            ),
            cls="text-center py-16",
        ),
        id="search-results",
    )


def render_search_error(message: str, error_type: str = "error") -> Div:
    """Render a search error message."""
    alert_class = f"alert alert-{error_type}"
    return Div(
        Div(
            P(message),
            cls=alert_class,
        ),
        id="search-results",
    )
