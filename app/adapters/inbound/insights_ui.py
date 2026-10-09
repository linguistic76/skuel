"""Insights UI Routes - Event-Driven Insights Dashboard
========================================================

UI routes for displaying and managing event-driven insights, and the Insights
cards — the hub methods' first door: ``GET /insights/hub/{question}`` builds
``UserContextIntelligence`` from the caller's rich context and answers one
``HubQuestion`` as an HTMX fragment (the card the ``/insights`` section mounts).

See: /docs/roadmap/askesis-intelligence-doors.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div, P, Span
from starlette.responses import Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.route_factories import parse_int_query_param
from core.models.enums import HubQuestion
from core.services.user.rich_context import rich_entity_titles
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
from ui.insights.hub_cards import (
    render_alignment_card,
    render_hub_card_error,
    render_hub_section,
    render_learn_next_card,
    render_perception_card,
    render_right_now_card,
    render_synergies_card,
    render_unblock_first_card,
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
    from collections.abc import Awaitable, Callable, Iterable

    from fasthtml.common import FT

    from core.models.insight.persisted_insight import PersistedInsight
    from core.services.insight import InsightStore
    from core.services.user.intelligence import UserContextIntelligence
    from core.services.user.unified_user_context import RichUserContext

logger = get_logger("skuel.routes.insights.ui")

# The record domains whose uids are Kus — the one kind the rich context may hold
# no title for (a Ku the user has not engaged), so the card reads them in one batch.
_KNOWLEDGE_DOMAIN = "knowledge"


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
    insight_store: InsightStore, insights: list[PersistedInsight], filters: InsightsFilters
) -> list[PersistedInsight]:
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


# ============================================================================
# The hub cards — one answer per HubQuestion
# ============================================================================


async def _resolve_titles(
    context: RichUserContext, ku_uids: Iterable[str], ku_service: Any
) -> dict[str, str]:
    """Titles for the uids a card names: the rich context's, plus one Ku batch for the rest.

    An activity the hub names is in the context (the hub read it there); a Ku may
    not be, so the ones the context lacks are read through ``KuService.get_kus_batch``.
    A failed batch leaves those uids to the card's fallback text — never an error.
    """
    titles = rich_entity_titles(context)
    missing = sorted({uid for uid in ku_uids if uid and uid not in titles})
    if not missing or ku_service is None:
        return titles
    batch = await ku_service.get_kus_batch(missing)
    if batch.is_error:
        logger.warning(
            "Insights hub: Ku titles unavailable for %d uids: %s",
            len(missing),
            batch.expect_error().message,
        )
        return titles
    for ku in batch.value:
        if ku is not None and ku.title:
            titles[ku.uid] = ku.title
    return titles


async def _answer_learn_next(
    hub: UserContextIntelligence, context: RichUserContext, ku_service: Any
) -> FT:
    result = await hub.get_optimal_next_path_steps()
    if result.is_error:
        return render_hub_card_error(HubQuestion.LEARN_NEXT, result.expect_error().message)
    steps = result.value
    titles = await _resolve_titles(context, (step.ku_uid for step in steps), ku_service)
    return render_learn_next_card(steps, titles)


async def _answer_unblock_first(
    hub: UserContextIntelligence, context: RichUserContext, ku_service: Any
) -> FT:
    result = await hub.get_unblocking_priority_order()
    if result.is_error:
        return render_hub_card_error(HubQuestion.UNBLOCK_FIRST, result.expect_error().message)
    blockers = result.value
    titles = await _resolve_titles(context, (uid for uid, _ in blockers), ku_service)
    return render_unblock_first_card(blockers, titles)


async def _answer_synergies(
    hub: UserContextIntelligence, context: RichUserContext, ku_service: Any
) -> FT:
    result = await hub.get_cross_domain_synergies()
    if result.is_error:
        return render_hub_card_error(HubQuestion.SYNERGIES, result.expect_error().message)
    synergies = result.value
    ku_uids: list[str] = []
    for synergy in synergies:
        if synergy.source_domain == _KNOWLEDGE_DOMAIN:
            ku_uids.append(synergy.source_uid)
        if synergy.target_domain == _KNOWLEDGE_DOMAIN:
            ku_uids.extend(synergy.target_uids)
    titles = await _resolve_titles(context, ku_uids, ku_service)
    return render_synergies_card(synergies, titles)


async def _answer_alignment(
    hub: UserContextIntelligence, context: RichUserContext, ku_service: Any
) -> FT:
    result = await hub.calculate_life_path_alignment()
    if result.is_error:
        return render_hub_card_error(HubQuestion.ALIGNMENT, result.expect_error().message)
    alignment = result.value
    titles = await _resolve_titles(context, alignment.knowledge_gaps, ku_service)
    return render_alignment_card(alignment, titles)


async def _answer_right_now(
    hub: UserContextIntelligence, context: RichUserContext, ku_service: Any
) -> FT:
    result = await hub.get_schedule_aware_recommendations()
    if result.is_error:
        return render_hub_card_error(HubQuestion.RIGHT_NOW, result.expect_error().message)
    recommendations = result.value
    titles = await _resolve_titles(
        context,
        (rec.uid for rec in recommendations if rec.entity_type == _KNOWLEDGE_DOMAIN),
        ku_service,
    )
    return render_right_now_card(recommendations, titles)


async def _answer_perception(
    hub: UserContextIntelligence, _context: RichUserContext, _ku_service: Any
) -> FT:
    result = await hub.get_cross_domain_perception_analysis()
    if result.is_error:
        return render_hub_card_error(HubQuestion.PERCEPTION, result.expect_error().message)
    return render_perception_card(result.value)


# Every HubQuestion answers through exactly one of these; the dispatch is a dict so
# a question without an answer is a KeyError at import time in the test, not a 500.
_ANSWERS: dict[
    HubQuestion,
    Callable[[UserContextIntelligence, RichUserContext, Any], Awaitable[FT]],
] = {
    HubQuestion.LEARN_NEXT: _answer_learn_next,
    HubQuestion.UNBLOCK_FIRST: _answer_unblock_first,
    HubQuestion.SYNERGIES: _answer_synergies,
    HubQuestion.ALIGNMENT: _answer_alignment,
    HubQuestion.RIGHT_NOW: _answer_right_now,
    HubQuestion.PERCEPTION: _answer_perception,
}


def create_insights_ui_routes(
    app: Any,
    rt: Any,
    insight_store: Any,
    user_service: Any = None,
    context_intelligence: Any = None,
    ku_service: Any = None,
) -> None:
    """Create insights UI routes.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        insight_store: InsightStore service for retrieving insights
        user_service: UserService — ``get_rich_unified_context`` builds the context the
            hub answers from (cached, 5-minute TTL)
        context_intelligence: ``UserContextIntelligenceFactory`` — creates the hub for a
            context. With ``user_service`` it enables the "Your intelligence" section and
            the ``/insights/hub/{question}`` fragments; absent, the section is not mounted.
        ku_service: KuService — one batched read for the Ku titles the context lacks
    """
    hub_wired = user_service is not None and context_intelligence is not None
    if not hub_wired:
        logger.warning(
            "Insights hub cards not mounted: user_service or context_intelligence absent"
        )

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
            render_hub_section() if hub_wired else Div(),
            filter_form,
            charts_section if charts_section else Div(),
            bulk_action_bar,
            select_all_header if select_all_header else Div(),
            insight_cards,
            cls="space-y-6",
            **{"x-data": "bulkInsightManager()"},
        )

        return BasePage(
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

        return BasePage(
            content,
            title="Insight Statistics | SKUEL",
            page_type=PageType.STANDARD,
            request=request,
            active_page="insights",
        )

    @rt("/insights/hub/{question}")
    async def insights_hub_card(request: Request, question: str):
        """HTMX fragment: one Insights card — a hub method's answer for the caller.

        Builds the hub from the caller's rich context (``get_rich_unified_context``,
        cached) and asks the ``HubQuestion`` the segment names. A failed context
        read or hub answer renders the question's error card (200, never a 500);
        a segment that names no question is a 404.
        """
        user_uid = require_authenticated_user(request)
        try:
            asked = HubQuestion(question)
        except ValueError:
            return Response("Unknown question", status_code=404, media_type="text/plain")
        if not hub_wired:
            return render_hub_card_error(asked, "The intelligence hub is not wired.")

        context_result = await user_service.get_rich_unified_context(user_uid)
        if context_result.is_error:
            logger.error(
                "Insights hub %s: rich context failed: %s",
                asked.value,
                context_result.expect_error().message,
            )
            return render_hub_card_error(asked, context_result.expect_error().message)
        context = context_result.value
        hub = context_intelligence.create(context)
        return await _ANSWERS[asked](hub, context, ku_service)

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
