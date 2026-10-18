"""Insights dashboard UI components — filter form, bulk actions, charts, card wrappers."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from fasthtml.common import FT, H3, Canvas, Div, NotStr, Option, Span

from core.models.insight.persisted_insight import (
    ActiveInsightFilter,
    InsightDomain,
    InsightImpact,
    InsightType,
)
from ui.alpine import alpine_call
from ui.components import Button, ButtonT
from ui.forms import Input, Label, LabelInput, LabelSelect
from ui.insights.insight_card import InsightCard

# The impact select lists the most severe first, as the page orders them.
_IMPACT_ORDER = (
    InsightImpact.CRITICAL,
    InsightImpact.HIGH,
    InsightImpact.MEDIUM,
    InsightImpact.LOW,
)


@dataclass(frozen=True)
class InsightsFilters:
    """Filter-state contract between the insights routes and UI components.

    Routes parse query params into this (see ``insights_ui.py``); the filter
    form renders from it.
    """

    match: ActiveInsightFilter
    offset: int


def _options(all_label: str, members: tuple[StrEnum, ...]) -> tuple[FT, ...]:
    """A select's options: "all" (blank — no filter), then one per vocabulary member."""
    return (
        Option(all_label, value=""),
        *(Option(member.value.replace("_", " ").title(), value=member.value) for member in members),
    )


def render_filter_form(filters: InsightsFilters) -> Any:
    """Build advanced filter form with Alpine.js data binding."""
    match = filters.match
    return Div(
        # Row 1: Search + Domain
        Div(
            # Full-text search (debounced 300ms)
            LabelInput(
                "Search",
                lbl_cls="text-xs",
                type="text",
                placeholder="Search insights...",
                id="insight-filter-search",
                cls="space-y-2 flex-1",
                **{"x-model": "filters.search"},
                **{"@input.debounce.300ms": "applyFilters()"},
            ),
            # Domain filter
            LabelSelect(
                *_options("All Domains", tuple(InsightDomain)),
                label="Domain",
                lbl_cls="text-xs",
                id="insight-filter-domain",
                full_width=False,
                **{"x-model": "filters.domain"},
                **{"@change": "applyFilters()"},
            ),
            cls="flex flex-wrap gap-3",
        ),
        # Row 2: Impact + Type
        Div(
            # Impact filter
            LabelSelect(
                *_options("All Impact", _IMPACT_ORDER),
                label="Impact",
                lbl_cls="text-xs",
                id="insight-filter-impact",
                full_width=False,
                **{"x-model": "filters.impact"},
                **{"@change": "applyFilters()"},
            ),
            # Insight type filter
            LabelSelect(
                *_options("All Types", tuple(InsightType)),
                label="Type",
                lbl_cls="text-xs",
                id="insight-filter-type",
                full_width=False,
                **{"x-model": "filters.type"},
                **{"@change": "applyFilters()"},
            ),
            cls="flex flex-wrap gap-3 mt-3",
        ),
        # Action buttons with loading indicator
        Div(
            Button(
                "Clear",
                type="button",
                cls=ButtonT.ghost,
                size="sm",
                **{"@click": "clearFilters()"},  # fasthtml dynamic-attr splat
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
        x_data=alpine_call(
            "insightFiltersDebounced",
            {
                "search": match.search,
                "domain": match.domain or "",
                "impact": match.impact or "",
                "type": match.insight_type or "",
            },
        ),
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
                    cls=ButtonT.ghost,
                    size="sm",
                    **{"@click": "bulkDismiss()"},  # fasthtml dynamic-attr splat
                ),
                Button(
                    "Mark as Actioned",
                    cls=ButtonT.primary,
                    size="sm",
                    **{"@click": "bulkMarkActioned()"},  # fasthtml dynamic-attr splat
                ),
                Button(
                    "Deselect All",
                    cls=ButtonT.ghost,
                    size="sm",
                    **{"@click": "deselectAll()"},  # fasthtml dynamic-attr splat
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
                x_model="selectAllChecked",
                **{"@change": "toggleSelectAll()"},  # type: ignore[arg-type]  # fasthtml dynamic-attr splat
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
                **{"@change": alpine_call("toggleSelection", insight.uid)},  # type: ignore[arg-type]  # fasthtml dynamic-attr splat
                **{":checked": alpine_call("isSelected", insight.uid)},  # type: ignore[arg-type]  # fasthtml dynamic-attr splat
            ),
            cls="mr-3 shrink-0 mt-1",
        ),
        # Insight card (right side)
        Div(
            InsightCard(insight),
            cls="flex-1",
        ),
        cls="flex items-start gap-2",
    )


def render_charts_section(insight_count: int) -> FT | None:
    """Render the visual analytics charts section. Returns None if insufficient data."""
    if insight_count < 3:
        return None

    return Div(
        H3("Visual Analytics", cls="text-xl font-bold mb-4"),
        Div(
            _chart_card("/api/insights/charts/impact-distribution"),
            _chart_card("/api/insights/charts/domain-distribution"),
            _chart_card("/api/insights/charts/type-distribution"),
            _chart_card("/api/insights/charts/action-rate"),
            cls="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6",
        ),
        cls="mb-8",
    )


def _chart_card(data_url: str) -> FT:
    """Chart card — canvas + loading/error states for the chartVis component.

    ``data_url`` answers the whole Chart.js config, its chart type included.
    """
    return Div(
        Canvas(**{"x-ref": "canvas", "width": "400", "height": "300", "class": "max-w-full"}),
        Div(
            "Loading chart...",
            cls="text-center text-muted-foreground py-8",
            **{"x-show": "loading"},
        ),
        Div(
            Span("Error: ", cls="font-bold"),
            Span(**{"x-text": "error"}),
            cls="text-error text-center py-8",
            **{"x-show": "error"},
        ),
        **{
            "x-data": alpine_call("chartVis", data_url),
            "class": "bg-background p-4 rounded-lg shadow-sm",
        },
    )
