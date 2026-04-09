"""Insights dashboard UI components — filter form, bulk actions, charts, card wrappers."""

from typing import Any

from fasthtml.common import H3, Div, NotStr, Span

from ui.buttons import Button, ButtonT
from ui.forms import Input, Label, LabelInput, LabelSelect
from ui.insights.filters import InsightsFilters
from ui.insights.insight_card import InsightCard
from ui.layout import Size


def render_filter_form(filters: InsightsFilters) -> Any:
    """Build advanced filter form with Alpine.js data binding."""
    return Div(
        # Row 1: Search + Domain
        Div(
            # Full-text search (debounced 300ms)
            LabelInput(
                "Search",
                lbl_cls="text-xs",
                type="text",
                placeholder="Search insights...",
                size=Size.sm,
                cls="space-y-2 flex-1",
                **{"x-model": "filters.search"},
                **{"@input.debounce.300ms": "applyFilters()"},
            ),
            # Domain filter
            LabelSelect(
                NotStr(
                    '<option value="">All Domains</option>'
                    '<option value="tasks">Tasks</option>'
                    '<option value="goals">Goals</option>'
                    '<option value="habits">Habits</option>'
                    '<option value="events">Events</option>'
                    '<option value="choices">Choices</option>'
                    '<option value="principles">Principles</option>'
                ),
                label="Domain",
                lbl_cls="text-xs",
                size=Size.sm,
                full_width=False,
                **{"x-model": "filters.domain"},
                **{"@change": "applyFilters()"},
            ),
            cls="flex gap-3",
        ),
        # Row 2: Impact + Type + Status
        Div(
            # Impact filter
            LabelSelect(
                NotStr(
                    '<option value="">All Impact</option>'
                    '<option value="critical">Critical</option>'
                    '<option value="high">High</option>'
                    '<option value="medium">Medium</option>'
                    '<option value="low">Low</option>'
                ),
                label="Impact",
                lbl_cls="text-xs",
                size=Size.sm,
                full_width=False,
                **{"x-model": "filters.impact"},
                **{"@change": "applyFilters()"},
            ),
            # Insight type filter
            LabelSelect(
                NotStr(
                    '<option value="">All Types</option>'
                    '<option value="difficulty_pattern">Difficulty Pattern</option>'
                    '<option value="completion_streak">Completion Streak</option>'
                    '<option value="habit_synergy">Habit Synergy</option>'
                    '<option value="goal_alignment">Goal Alignment</option>'
                    '<option value="principle_violation">Principle Violation</option>'
                    '<option value="learning_opportunity">Learning Opportunity</option>'
                ),
                label="Type",
                lbl_cls="text-xs",
                size=Size.sm,
                full_width=False,
                **{"x-model": "filters.type"},
                **{"@change": "applyFilters()"},
            ),
            # Action status filter
            LabelSelect(
                NotStr(
                    '<option value="all">All</option>'
                    '<option value="unactioned">Not Acted On</option>'
                    '<option value="actioned">Acted On</option>'
                ),
                label="Status",
                lbl_cls="text-xs",
                size=Size.sm,
                full_width=False,
                **{"x-model": "filters.status"},
                **{"@change": "applyFilters()"},
            ),
            cls="flex gap-3 mt-3",
        ),
        # Action buttons with loading indicator
        Div(
            Button(
                "Clear",
                type="button",
                variant=ButtonT.ghost,
                size=Size.sm,
                **{"@click": "clearFilters()"},
            ),
            # Loading indicator (shown during debounce/navigation)
            Span(
                "Filtering...",
                cls="text-xs text-muted-foreground animate-spin",
                **{"x-show": "loading"},
            ),
            cls="flex gap-2 mt-3 items-center",
        ),
        cls="mb-6 p-4 bg-muted rounded-lg",
        **{
            "x-data": f"insightFiltersDebounced({{search: '{filters.search}', domain: '{filters.domain or ''}', impact: '{filters.impact or ''}', type: '{filters.insight_type or ''}', status: '{filters.action_status or 'all'}'}})"
        },
    )


def render_bulk_action_bar() -> Any:
    """Render the bulk action bar (shown when insights are selected via Alpine)."""
    return Div(
        Div(
            # Selection count
            Div(
                Span(
                    NotStr("<span x-text='selectedCount'></span>"),
                    " insight",
                    NotStr("<span x-show='selectedCount !== 1'>s</span>"),
                    " selected",
                    cls="text-sm font-medium",
                ),
                cls="flex-1",
            ),
            # Action buttons
            Div(
                Button(
                    "Dismiss Selected",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                    **{"@click": "bulkDismiss()"},
                ),
                Button(
                    "Mark as Actioned",
                    variant=ButtonT.primary,
                    size=Size.sm,
                    **{"@click": "bulkMarkActioned()"},
                ),
                Button(
                    "Deselect All",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                    **{"@click": "deselectAll()"},
                ),
                cls="flex gap-2",
            ),
            cls="flex items-center justify-between",
        ),
        cls="mb-4 p-4 bg-primary/10 border border-primary/30 rounded-lg",
        **{"x-show": "showBulkActions"},
        **{"x-transition": ""},
    )


def render_select_all_header() -> Any:
    """Render the select-all checkbox header."""
    return Div(
        Label(
            Input(
                type="checkbox",
                cls="checkbox checkbox-primary",
                **{"x-model": "selectAllChecked"},
                **{"@change": "toggleSelectAll()"},
            ),
            Span("Select All", cls="ml-2 text-sm font-medium"),
            cls="cursor-pointer justify-start gap-2",
        ),
        cls="mb-4 p-3 bg-muted rounded-lg",
    )


def render_insight_card_with_checkbox(insight: Any) -> Any:
    """Wrap an insight card with a selection checkbox."""
    return Div(
        # Checkbox (left side)
        Label(
            Input(
                type="checkbox",
                name="insight-checkbox",
                value=insight.uid,
                cls="checkbox checkbox-primary",
                **{"@change": f"toggleSelection('{insight.uid}')"},
                **{":checked": f"isSelected('{insight.uid}')"},
            ),
            cls="mr-3 flex-shrink-0 mt-1",
        ),
        # Insight card (right side)
        Div(
            InsightCard(insight),
            cls="flex-1",
        ),
        cls="flex items-start gap-2",
    )


def render_charts_section(insight_count: int) -> Any | None:
    """Render the visual analytics charts section. Returns None if insufficient data."""
    if insight_count < 3:
        return None

    return Div(
        H3("Visual Analytics", cls="text-xl font-bold mb-4"),
        Div(
            # Impact distribution (doughnut)
            Div(
                **{
                    "x-data": "chartVis('/api/insights/charts/impact-distribution', 'doughnut')",
                    "class": "bg-background p-4 rounded-lg shadow",
                }
            ),
            # Domain distribution (bar)
            Div(
                **{
                    "x-data": "chartVis('/api/insights/charts/domain-distribution', 'bar')",
                    "class": "bg-background p-4 rounded-lg shadow",
                }
            ),
            # Type distribution (doughnut)
            Div(
                **{
                    "x-data": "chartVis('/api/insights/charts/type-distribution', 'doughnut')",
                    "class": "bg-background p-4 rounded-lg shadow",
                }
            ),
            # Action rate (gauge)
            Div(
                **{
                    "x-data": "chartVis('/api/insights/charts/action-rate', 'doughnut')",
                    "class": "bg-background p-4 rounded-lg shadow",
                }
            ),
            cls="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6",
        ),
        cls="mb-8",
    )
