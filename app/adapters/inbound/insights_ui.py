"""Insights UI Routes - Event-Driven Insights Dashboard
========================================================

UI routes for displaying and managing event-driven insights.

(January 2026): Insight dashboard with dismiss/action functionality.
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div, P, Span

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.route_factories import parse_int_query_param
from core.utils.logging import get_logger
from ui.components import ButtonT
from ui.insights.components import (
    InsightsFilters,
    render_bulk_action_bar,
    render_charts_section,
    render_filter_form,
    render_insight_card_with_checkbox,
    render_select_all_header,
)
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_error_banner
from ui.patterns.page_header import PageHeader
from ui.patterns.personal_header import personal_header_placeholder
from ui.patterns.section_header import SectionHeader
from ui.patterns.stats_grid import StatItem, StatsGrid
from ui.primitives import ButtonLink

if TYPE_CHECKING:
    from core.models.insight.persisted_insight import PersistedInsight
    from core.services.insight import InsightStore

logger = get_logger("skuel.routes.insights.ui")


def _parse_insights_filters(request: Request) -> InsightsFilters:
    """Extract insights filter parameters from request query params."""
    offset = parse_int_query_param(request.query_params, "offset", 0, minimum=0)

    return InsightsFilters(
        domain=request.query_params.get("domain"),
        impact=request.query_params.get("impact"),
        search=request.query_params.get("search", ""),
        insight_type=request.query_params.get("type"),
        action_status=request.query_params.get("status"),
        offset=offset,
    )


def _apply_insight_filters(
    insight_store: "InsightStore", insights: "list[PersistedInsight]", filters: InsightsFilters
) -> "list[PersistedInsight]":
    """Apply in-memory filters via InsightStore.filter_insights (staticmethod on the injected store)."""
    return insight_store.filter_insights(
        insights,
        impact=filters.impact,
        insight_type=filters.insight_type,
        action_status=filters.action_status,
        search=filters.search or None,
    )


def _build_filter_query_string(filters: InsightsFilters) -> str:
    """Build URL query string from insight filters."""
    params = []
    if filters.domain:
        params.append(f"domain={filters.domain}")
    if filters.impact:
        params.append(f"impact={filters.impact}")
    if filters.search:
        params.append(f"search={filters.search}")
    if filters.insight_type:
        params.append(f"type={filters.insight_type}")
    if filters.action_status:
        params.append(f"status={filters.action_status}")
    return "&".join(params)


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
        filters = _parse_insights_filters(request)

        # Progressive loading - load 10 initially for fast page load
        page_size = 10
        result = await insight_store.get_active_insights(
            user_uid=user_uid,
            domain=filters.domain,
            limit=page_size,
        )

        insights_load_error = False
        if result.is_error:
            logger.error(f"Failed to retrieve insights: {result.error}")
            insights = []
            insights_load_error = True
        else:
            insights = _apply_insight_filters(insight_store, result.value, filters)

        # Build filter form
        filter_form = render_filter_form(filters)

        # Bulk actions bar (shown when insights selected)
        bulk_action_bar = render_bulk_action_bar()

        # Select-all header (only shown when insights present)
        select_all_header = render_select_all_header() if insights else None

        # Build insight cards with load-more trigger
        if insights:
            filter_query = _build_filter_query_string(filters)
            load_more_url = (
                f"/insights/load-more?offset={page_size}&{filter_query}"
                if filter_query
                else f"/insights/load-more?offset={page_size}"
            )

            insight_card_items = [
                render_insight_card_with_checkbox(insight) for insight in insights
            ]

            # Container for insights with HTMX infinite scroll
            insight_cards = Div(
                Div(
                    *insight_card_items,
                    id="insights-list",
                    cls="space-y-4",
                ),
                Div(
                    id="load-more-trigger",
                    hx_get=load_more_url,
                    hx_trigger="revealed",
                    hx_swap="outerHTML",
                    hx_indicator="#loading-indicator",
                ),
                Div(
                    Div(
                        Span("Loading more insights...", cls="text-muted-foreground text-sm"),
                        cls="flex justify-center items-center py-8",
                    ),
                    id="loading-indicator",
                    cls="htmx-indicator",
                ),
            )
        elif insights_load_error:
            insight_cards = render_error_banner(
                "Unable to load insights. Please try again later.",
                str(result.error),
            )
        else:
            insight_cards = EmptyState(
                title="No Active Insights",
                description="Your intelligence services haven't detected any patterns yet. "
                "Keep using SKUEL and insights will appear automatically!",
                icon="💡",
            )

        # Charts visualization section
        charts_section = render_charts_section(len(insights))

        # Build page content
        content = Div(
            personal_header_placeholder(),
            PageHeader(
                title="💡 Insights",
                subtitle=f"{len(insights)} active insight{'s' if len(insights) != 1 else ''} from your behavior patterns",
            ),
            Div(
                ButtonLink(
                    "📜 View History",
                    href="/insights/history",
                    cls=ButtonT.ghost,
                    size="sm",
                ),
                cls="mb-4",
            ),
            filter_form,
            charts_section if charts_section else Div(),
            bulk_action_bar,
            select_all_header if select_all_header else Div(),
            insight_cards,
            cls="space-y-6",
            **{"x-data": "bulkInsightManager()"},
        )

        return await BasePage(
            content,
            title="Insights | SKUEL",
            page_type=PageType.STANDARD,
            request=request,
            active_page="insights",
            # BasePage builds its own <head>, so fast_app-level chartjs_headers
            # never reach this page — the charts section needs Chart.js here.
            extra_scripts=["/static/vendor/chart.js/chart.umd.js"],
        )

    @rt("/insights/stats")
    async def insights_stats(request):
        """Display insight statistics page."""
        user_uid = require_authenticated_user(request)

        result = await insight_store.get_insight_stats(user_uid)

        stats_load_error = False
        if result.is_error:
            logger.error(f"Failed to retrieve insight stats: {result.error}")
            stats = {}
            stats_load_error = True
        else:
            stats = result.value

        stats_content = Div(
            SectionHeader("Insight Statistics"),
            StatsGrid(
                [
                    StatItem(label="Total Insights", value=str(stats.get("total_insights", 0))),
                    StatItem(label="Active Insights", value=str(stats.get("active_insights", 0))),
                    StatItem(label="Actioned", value=str(stats.get("actioned_insights", 0))),
                    StatItem(label="Action Rate", value=f"{stats.get('action_rate', 0):.0%}"),
                ]
            ),
            Div(
                SectionHeader("Domains", cls="mt-8"),
                P(
                    ", ".join(stats.get("domains", [])) or "None",
                    cls="text-muted-foreground",
                ),
                cls="mt-6",
            ),
            cls="space-y-6",
        )

        content = Div(
            personal_header_placeholder(),
            PageHeader(
                title="📊 Insight Statistics",
                subtitle="Track how you're using insights to improve",
            ),
            render_error_banner("Unable to load insight statistics", str(result.error))
            if stats_load_error
            else None,
            stats_content,
            cls="space-y-6",
        )

        return await BasePage(
            content,
            title="Insight Statistics | SKUEL",
            page_type=PageType.STANDARD,
            request=request,
            active_page="insights",
        )

    @rt("/insights/load-more")
    async def load_more_insights(request):
        """HTMX endpoint for progressive loading.

        Loads next batch of insights for infinite scroll.
        Returns insight cards + new load-more trigger (or end marker).
        """
        user_uid = require_authenticated_user(request)

        filters = _parse_insights_filters(request)
        page_size = 10

        result = await insight_store.get_active_insights(
            user_uid=user_uid,
            domain=filters.domain,
            limit=page_size + filters.offset,
        )

        if result.is_error:
            logger.error(f"Failed to retrieve insights: {result.error}")
            return render_error_banner("Failed to load more insights", str(result.error))

        all_insights = _apply_insight_filters(insight_store, result.value, filters)
        new_insights = all_insights[filters.offset : filters.offset + page_size]

        if not new_insights:
            return EmptyState("No more insights to load", id="load-more-trigger", cls="py-4")

        filter_query = _build_filter_query_string(filters)
        next_offset = filters.offset + page_size
        next_url = (
            f"/insights/load-more?offset={next_offset}&{filter_query}"
            if filter_query
            else f"/insights/load-more?offset={next_offset}"
        )

        loaded_card_items = [render_insight_card_with_checkbox(insight) for insight in new_insights]

        return Div(
            *loaded_card_items,
            Div(
                id="load-more-trigger",
                hx_get=next_url,
                hx_trigger="revealed",
                hx_swap="outerHTML",
                hx_indicator="#loading-indicator",
            ),
        )

    return [insights_dashboard, insights_stats, load_more_insights]
