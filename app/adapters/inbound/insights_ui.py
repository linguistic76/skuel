"""Insights UI Routes - Event-Driven Insights Dashboard
========================================================

UI routes for displaying and managing event-driven insights.

(January 2026): Insight dashboard with dismiss/action functionality.
"""

from dataclasses import dataclass
from typing import Any

from fasthtml.common import H2, H3, Div, NotStr, P, Span
from starlette.requests import Request

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.route_factories import parse_int_query_param
from core.utils.logging import get_logger
from ui.buttons import Button, ButtonLink, ButtonT
from ui.forms import Input, Label, LabelInput, LabelSelect
from ui.insights.insight_card import InsightCard
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader

logger = get_logger("skuel.routes.insights.ui")


# ============================================================================
# TYPED QUERY PARAMETERS
# ============================================================================


@dataclass
class InsightsFilters:
    """Typed filters for insights list queries."""

    domain: str | None
    impact: str | None
    search: str
    insight_type: str | None
    action_status: str | None
    offset: int


def parse_insights_filters(request: Request) -> InsightsFilters:
    """
    Extract insights filter parameters from request query params.

    Args:
        request: Starlette request object

    Returns:
        Typed InsightsFilters with defaults applied
    """
    offset = parse_int_query_param(request.query_params, "offset", 0, minimum=0)

    return InsightsFilters(
        domain=request.query_params.get("domain"),
        impact=request.query_params.get("impact"),
        search=request.query_params.get("search", ""),
        insight_type=request.query_params.get("type"),
        action_status=request.query_params.get("status"),
        offset=offset,
    )


def create_insights_ui_routes(
    app: Any,
    rt: Any,
    insight_store: Any,
) -> list[Any]:
    """Create insights UI routes.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        insight_store: InsightStore service for retrieving insights

    Returns:
        List of route handler functions
    """

    @rt("/insights")
    async def insights_dashboard(request):
        """Display active insights dashboard with filtering."""
        user_uid = require_authenticated_user(request)

        # Parse typed filter parameters
        filters = parse_insights_filters(request)

        # , Task 8: Progressive loading - load 10 initially for fast page load
        page_size = 10
        result = await insight_store.get_active_insights(
            user_uid=user_uid,
            domain=filters.domain,
            limit=page_size,  # Initial load: 10 insights only
        )

        if result.is_error:
            logger.error(f"Failed to retrieve insights: {result.error}")
            insights = []
        else:
            insights = result.value

            # Apply filters (client-side for now - would be server-side in production)
            if filters.impact:
                insights = [i for i in insights if i.impact.value == filters.impact]

            if filters.insight_type:
                insights = [i for i in insights if i.insight_type.value == filters.insight_type]

            if filters.action_status == "unactioned":
                insights = [i for i in insights if not i.actioned]
            elif filters.action_status == "actioned":
                insights = [i for i in insights if i.actioned]

            if filters.search:
                search_lower = filters.search.lower()
                insights = [
                    i
                    for i in insights
                    if search_lower in i.title.lower()
                    or search_lower in (i.description or "").lower()
                ]

        # Build advanced filter form
        filter_form = Div(
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
                    cls="text-xs text-muted-foreground uk-spinner uk-spinner-small",
                    **{"x-show": "loading"},
                ),
                cls="flex gap-2 mt-3 items-center",
            ),
            cls="mb-6 p-4 bg-muted rounded-lg",
            **{
                "x-data": f"insightFiltersDebounced({{search: '{filters.search}', domain: '{filters.domain or ''}', impact: '{filters.impact or ''}', type: '{filters.insight_type or ''}', status: '{filters.action_status or 'all'}'}})"
            },
        )

        # , Task 9: Bulk actions bar (only shown when insights selected)
        bulk_action_bar = Div(
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

        # , Task 9: Select-all header (only shown when insights present)
        select_all_header = None
        if insights:
            select_all_header = Div(
                Label(
                    Input(
                        type="checkbox",
                        cls="uk-checkbox",
                        **{"x-model": "selectAllChecked"},
                        **{"@change": "toggleSelectAll()"},
                    ),
                    Span("Select All", cls="ml-2 text-sm font-medium"),
                    cls="cursor-pointer justify-start gap-2",
                ),
                cls="mb-4 p-3 bg-muted rounded-lg",
            )

        # , Task 8: Progressive loading with HTMX infinite scroll
        # Build insight cards with load-more trigger
        if insights:
            # Encode filters for load-more URL
            filter_params = []
            if filters.domain:
                filter_params.append(f"domain={filters.domain}")
            if filters.impact:
                filter_params.append(f"impact={filters.impact}")
            if filters.search:
                filter_params.append(f"search={filters.search}")
            if filters.insight_type:
                filter_params.append(f"type={filters.insight_type}")
            if filters.action_status:
                filter_params.append(f"status={filters.action_status}")

            filter_query = "&".join(filter_params)
            load_more_url = (
                f"/insights/load-more?offset={page_size}&{filter_query}"
                if filter_query
                else f"/insights/load-more?offset={page_size}"
            )

            # , Task 9: Wrap each insight card with checkbox
            insight_card_items = []
            for insight in insights:
                card_with_checkbox = Div(
                    # Checkbox (left side)
                    Label(
                        Input(
                            type="checkbox",
                            name="insight-checkbox",
                            value=insight.uid,
                            cls="uk-checkbox",
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
                insight_card_items.append(card_with_checkbox)

            # Container for insights with HTMX infinite scroll
            insight_cards = Div(
                # Initial batch of insights
                Div(
                    *insight_card_items,
                    id="insights-list",
                    cls="space-y-4",
                ),
                # Load more trigger (revealed when scrolled into view)
                Div(
                    id="load-more-trigger",
                    hx_get=load_more_url,
                    hx_trigger="revealed",
                    hx_swap="outerHTML",
                    hx_indicator="#loading-indicator",
                ),
                # Loading indicator
                Div(
                    Div(
                        Span("Loading more insights...", cls="uk-spinner uk-spinner-small"),
                        cls="flex justify-center items-center py-8",
                    ),
                    id="loading-indicator",
                    cls="htmx-indicator",
                ),
            )
        else:
            # Empty state
            insight_cards = EmptyState(
                title="No Active Insights",
                message="Your intelligence services haven't detected any patterns yet. "
                "Keep using SKUEL and insights will appear automatically!",
                icon="💡",
            )

        # Charts visualization section (only show if there are insights)
        charts_section = None
        if len(insights) >= 3:  # Only show charts if meaningful data (3+ insights)
            charts_section = Div(
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

        # Build page content
        content = Div(
            PageHeader(
                title="💡 Insights",
                subtitle=f"{len(insights)} active insight{'s' if len(insights) != 1 else ''} from your behavior patterns",
            ),
            # , Task 17: Link to history page
            Div(
                ButtonLink(
                    "📜 View History",
                    href="/insights/history",
                    variant=ButtonT.ghost,
                    size=Size.sm,
                ),
                cls="mb-4",
            ),
            filter_form,
            charts_section if charts_section else Div(),  # Add charts section if available
            bulk_action_bar,  # bulk action bar (shown when insights selected)
            select_all_header if select_all_header else Div(),  # select-all checkbox
            insight_cards,
            cls="space-y-6",
            **{"x-data": "bulkInsightManager()"},  # Alpine component for bulk selection
        )

        return await BasePage(
            content,
            title="Insights | SKUEL",
            page_type=PageType.STANDARD,
            request=request,  # Pass request for auto-detected auth state
            active_page="insights",
        )

    @rt("/insights/stats")
    async def insights_stats(request):
        """Display insight statistics page."""
        user_uid = require_authenticated_user(request)

        # Get insight stats
        result = await insight_store.get_insight_stats(user_uid)

        if result.is_error:
            logger.error(f"Failed to retrieve insight stats: {result.error}")
            stats = {}
        else:
            stats = result.value

        # Build stats display
        stats_content = Div(
            H2("Insight Statistics", cls="text-2xl font-bold mb-6"),
            Div(
                Div(
                    P("Total Insights", cls="text-sm text-muted-foreground"),
                    P(str(stats.get("total_insights", 0)), cls="text-3xl font-bold"),
                    cls="p-4 text-center",
                ),
                Div(
                    P("Active Insights", cls="text-sm text-muted-foreground"),
                    P(str(stats.get("active_insights", 0)), cls="text-3xl font-bold"),
                    cls="p-4 text-center",
                ),
                Div(
                    P("Actioned", cls="text-sm text-muted-foreground"),
                    P(str(stats.get("actioned_insights", 0)), cls="text-3xl font-bold"),
                    cls="p-4 text-center",
                ),
                Div(
                    P("Action Rate", cls="text-sm text-muted-foreground"),
                    P(
                        f"{stats.get('action_rate', 0):.0%}",
                        cls="text-3xl font-bold",
                    ),
                    cls="p-4 text-center",
                ),
                cls="grid grid-cols-2 lg:grid-cols-4 gap-4 shadow rounded-lg",
            ),
            Div(
                H2("Domains", cls="text-xl font-bold mb-4 mt-8"),
                P(
                    ", ".join(stats.get("domains", [])) or "None",
                    cls="text-muted-foreground",
                ),
                cls="mt-6",
            ),
            cls="space-y-6",
        )

        content = Div(
            PageHeader(
                title="📊 Insight Statistics",
                subtitle="Track how you're using insights to improve",
            ),
            stats_content,
            cls="space-y-6",
        )

        return await BasePage(
            content,
            title="Insight Statistics | SKUEL",
            page_type=PageType.STANDARD,
            request=request,  # Pass request for auto-detected auth state
            active_page="insights",
        )

    @rt("/insights/load-more")
    async def load_more_insights(request):
        """HTMX endpoint for progressive loading.

        Loads next batch of insights for infinite scroll.
        Returns insight cards + new load-more trigger (or end marker).
        """
        user_uid = require_authenticated_user(request)

        # Parse typed filter parameters
        filters = parse_insights_filters(request)
        page_size = 10

        # Get next batch of insights
        result = await insight_store.get_active_insights(
            user_uid=user_uid,
            domain=filters.domain,
            limit=page_size + filters.offset,  # Get all up to this point
        )

        if result.is_error:
            logger.error(f"Failed to retrieve insights: {result.error}")
            return Div(P("Failed to load more insights", cls="text-error"))

        all_insights = result.value

        # Apply same filters as main dashboard
        if filters.impact:
            all_insights = [i for i in all_insights if i.impact.value == filters.impact]
        if filters.insight_type:
            all_insights = [i for i in all_insights if i.insight_type.value == filters.insight_type]
        if filters.action_status == "unactioned":
            all_insights = [i for i in all_insights if not i.actioned]
        elif filters.action_status == "actioned":
            all_insights = [i for i in all_insights if i.actioned]
        if filters.search:
            search_lower = filters.search.lower()
            all_insights = [
                i
                for i in all_insights
                if search_lower in i.title.lower() or search_lower in (i.description or "").lower()
            ]

        # Get only the new batch (slice from offset)
        new_insights = all_insights[filters.offset : filters.offset + page_size]

        if not new_insights:
            # No more insights - return end marker
            return Div(
                P("No more insights to load", cls="text-center text-muted-foreground py-4"),
                id="load-more-trigger",
            )

        # Encode filters for next load-more URL
        filter_params = []
        if filters.domain:
            filter_params.append(f"domain={filters.domain}")
        if filters.impact:
            filter_params.append(f"impact={filters.impact}")
        if filters.search:
            filter_params.append(f"search={filters.search}")
        if filters.insight_type:
            filter_params.append(f"type={filters.insight_type}")
        if filters.action_status:
            filter_params.append(f"status={filters.action_status}")

        filter_query = "&".join(filter_params)
        next_offset = filters.offset + page_size
        next_url = (
            f"/insights/load-more?offset={next_offset}&{filter_query}"
            if filter_query
            else f"/insights/load-more?offset={next_offset}"
        )

        # , Task 9: Wrap each loaded insight with checkbox
        loaded_card_items = []
        for insight in new_insights:
            card_with_checkbox = Div(
                # Checkbox (left side)
                Label(
                    Input(
                        type="checkbox",
                        name="insight-checkbox",
                        value=insight.uid,
                        cls="uk-checkbox",
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
            loaded_card_items.append(card_with_checkbox)

        # Return new insight cards + new load-more trigger
        return Div(
            # New batch of insights (append to existing list)
            *loaded_card_items,
            # New load-more trigger for next batch
            Div(
                id="load-more-trigger",
                hx_get=next_url,
                hx_trigger="revealed",
                hx_swap="outerHTML",
                hx_indicator="#loading-indicator",
            ),
        )

    return [insights_dashboard, insights_stats, load_more_insights]
