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
from urllib.parse import urlencode

from fasthtml.common import Div, P, Span
from starlette.responses import Response

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.insights_api import (
    parse_active_insight_filter,
    parse_active_insight_offset,
)
from adapters.inbound.route_factories import refuse_malformed
from core.models.enums import EntityType, HubQuestion
from core.models.insight.persisted_insight import ActiveInsightFilter
from core.services.user.rich_context import rich_entity_titles
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
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

    from core.services.ku_service import KuService
    from core.services.user.intelligence import (
        UserContextIntelligence,
        UserContextIntelligenceFactory,
    )
    from core.services.user.unified_user_context import RichUserContext
    from core.services.user_service import UserService

logger = get_logger("skuel.routes.insights.ui")


def _names_a_ku(domain: str) -> bool:
    """Whether a record's domain word is the Ku kind — the one kind the rich context
    may hold no title for (a Ku the user has not engaged), read in one batch.

    The records speak ``"knowledge"``; ``EntityType.from_string`` resolves that alias
    and the canonical ``"ku"`` alike, so a record emitting either is a Ku here.
    """
    return EntityType.from_string(domain) is EntityType.KU


def _parse_insights_filters(request: Request) -> Result[InsightsFilters]:
    """The page's filters and offset from its query params — a validation error
    when ``offset`` does not read or is outside 0..``QueryLimit.MAXIMUM``, or a
    domain / impact / type is outside its vocabulary."""
    match = parse_active_insight_filter(request.query_params)
    if match.is_error:
        return Result.fail(match)
    offset = parse_active_insight_offset(request.query_params)
    if offset.is_error:
        return Result.fail(offset)
    return Result.ok(InsightsFilters(match=match.value, offset=offset.value))


def _load_more_query(filters: InsightsFilters, offset: int) -> str:
    """The load-more query for the page starting at ``offset``, carrying the filters."""
    match = filters.match
    chosen = {
        "domain": match.domain or "",
        "impact": match.impact or "",
        "type": match.insight_type or "",
        "search": match.search,
    }
    params = {"offset": str(offset)} | {name: value for name, value in chosen.items() if value}
    return urlencode(params)


def _subtitle(matching: int, active_total: int, *, filtered: bool) -> str:
    """The page's count line: every match, never the length of the first page."""
    noun = "insight" if active_total == 1 else "insights"
    if filtered:
        return f"{matching} of {active_total} active {noun} match your filters"
    return f"{active_total} active {noun} from your behavior patterns"


# ============================================================================
# The hub cards — one answer per HubQuestion
# ============================================================================


async def _resolve_titles(
    context: RichUserContext, ku_uids: Iterable[str], ku_service: KuService
) -> dict[str, str]:
    """Titles for the uids a card names: the rich context's, plus one Ku batch for the rest.

    An activity the hub names is in the context (the hub read it there); a Ku may
    not be, so the ones the context lacks are read through ``KuService.get_kus_batch``.
    A failed batch leaves those uids to the card's fallback text — never an error.
    """
    titles = rich_entity_titles(context)
    missing = sorted({uid for uid in ku_uids if uid and uid not in titles})
    if not missing:
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


def _error_card(question: HubQuestion, failed: Result[Any]) -> FT:
    """The question's error card: the client-safe message is shown, the developer
    message (which may carry raw exception text) goes to the server log only."""
    error = failed.expect_error()
    logger.error("Insights hub %s: %s", question.value, error.message)
    return render_hub_card_error(question, error.display_message)


async def _answer_learn_next(
    hub: UserContextIntelligence, _context: RichUserContext, _ku_service: KuService
) -> FT:
    result = await hub.get_optimal_next_path_steps()
    if result.is_error:
        return _error_card(HubQuestion.LEARN_NEXT, result)
    # Every step carries its title (the hub reads the published ones in one batch —
    # a withheld draft keeps its placeholder), so no Ku read and no context title here.
    return render_learn_next_card(result.value)


async def _answer_unblock_first(
    hub: UserContextIntelligence, context: RichUserContext, ku_service: KuService
) -> FT:
    result = await hub.get_unblocking_priority_order()
    if result.is_error:
        return _error_card(HubQuestion.UNBLOCK_FIRST, result)
    blockers = result.value
    titles = await _resolve_titles(context, (uid for uid, _ in blockers), ku_service)
    return render_unblock_first_card(blockers, titles)


async def _answer_synergies(
    hub: UserContextIntelligence, context: RichUserContext, ku_service: KuService
) -> FT:
    result = await hub.get_cross_domain_synergies()
    if result.is_error:
        return _error_card(HubQuestion.SYNERGIES, result)
    synergies = result.value
    ku_uids: list[str] = []
    for synergy in synergies:
        if _names_a_ku(synergy.source_domain):
            ku_uids.append(synergy.source_uid)
        if _names_a_ku(synergy.target_domain):
            ku_uids.extend(synergy.target_uids)
    titles = await _resolve_titles(context, ku_uids, ku_service)
    return render_synergies_card(synergies, titles)


async def _answer_alignment(
    hub: UserContextIntelligence, context: RichUserContext, ku_service: KuService
) -> FT:
    result = await hub.calculate_life_path_alignment()
    if result.is_error:
        return _error_card(HubQuestion.ALIGNMENT, result)
    alignment = result.value
    titles = await _resolve_titles(context, alignment.knowledge_gaps, ku_service)
    return render_alignment_card(alignment, titles)


async def _answer_right_now(
    hub: UserContextIntelligence, context: RichUserContext, ku_service: KuService
) -> FT:
    result = await hub.get_schedule_aware_recommendations()
    if result.is_error:
        return _error_card(HubQuestion.RIGHT_NOW, result)
    recommendations = result.value
    titles = await _resolve_titles(
        context,
        (rec.uid for rec in recommendations if _names_a_ku(rec.entity_type)),
        ku_service,
    )
    return render_right_now_card(recommendations, titles)


async def _answer_perception(
    hub: UserContextIntelligence, _context: RichUserContext, _ku_service: KuService
) -> FT:
    result = await hub.get_cross_domain_perception_analysis()
    if result.is_error:
        return _error_card(HubQuestion.PERCEPTION, result)
    return render_perception_card(result.value)


# Every HubQuestion answers through exactly one of these; the dispatch is a dict so
# a question without an answer is a KeyError at import time in the test, not a 500.
_ANSWERS: dict[
    HubQuestion,
    Callable[[UserContextIntelligence, RichUserContext, KuService], Awaitable[FT]],
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
    user_service: UserService,
    context_intelligence: UserContextIntelligenceFactory,
    ku_service: KuService,
) -> None:
    """Create insights UI routes.

    The three hub services are REQUIRED — the hub is wired in both tiers, and a
    page that silently dropped its cards would be a second, degraded path.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        insight_store: InsightStore service for retrieving insights
        user_service: UserService — ``get_rich_unified_context`` builds the context the
            hub answers from (cached, 5-minute TTL)
        context_intelligence: ``UserContextIntelligenceFactory`` — creates the hub for a
            context; its answers are the "Your intelligence" section's cards
        ku_service: KuService — one batched read for the Ku titles the context lacks

    Raises:
        ValueError: when a hub service is missing — at registration, not at click time
    """
    missing = [
        name
        for name, service in (
            ("user_service", user_service),
            ("context_intelligence", context_intelligence),
            ("ku_service", ku_service),
        )
        if service is None
    ]
    if missing:
        raise ValueError(f"Insights UI routes require the hub services; missing: {missing}")

    @rt("/insights")
    async def insights_dashboard(request):
        """Display active insights dashboard with filtering."""
        user_uid = require_authenticated_user(request)

        # Parse typed filter parameters
        parsed = _parse_insights_filters(request)
        if parsed.is_error:
            return refuse_malformed(parsed.expect_error())
        filters = parsed.value

        # Progressive loading - load 10 initially for fast page load
        page_size = 10
        result = await insight_store.get_active_insights(
            user_uid, filters.match, limit=page_size, offset=0
        )
        # The subtitle counts every match; the charts show the whole active set,
        # so they are gated on its size, not on the filtered matches.
        matching = await insight_store.count_active_insights(user_uid, filters.match)
        filtered = filters.match != ActiveInsightFilter()
        active_total = await insight_store.count_active_insights(user_uid) if filtered else matching

        load_error = next((r for r in (result, matching, active_total) if r.is_error), None)
        if load_error is not None:
            logger.error(f"Failed to retrieve insights: {load_error.error}")
            insights = []
        else:
            insights = result.value

        # Build filter form
        filter_form = render_filter_form(filters)

        # Bulk actions bar (shown when insights selected)
        bulk_action_bar = render_bulk_action_bar()

        # Select-all header (only shown when insights present)
        select_all_header = render_select_all_header() if insights else None

        # Build insight cards with load-more trigger
        if insights:
            load_more_query = _load_more_query(filters, page_size)

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
                    hx_get=f"/insights/load-more?{load_more_query}",
                    hx_trigger="revealed",
                    hx_swap="outerHTML",
                    hx_indicator="#loading-indicator",
                ),
                Div(
                    Div(
                        Span("Loading more insights...", cls="text-muted-foreground text-sm"),
                        cls="flex justify-center items-center pt-8",
                    ),
                    id="loading-indicator",
                    cls="htmx-indicator",
                ),
            )
        elif load_error is not None:
            insight_cards = render_error_banner(
                "Unable to load insights. Please try again later.",
                str(load_error.error),
            )
        elif filtered and active_total.value:
            insight_cards = EmptyState(
                title="No Matching Insights",
                description="None of your active insights match these filters.",
                icon="🔍",
            )
        else:
            insight_cards = EmptyState(
                title="No Active Insights",
                description="Your intelligence services haven't detected any patterns yet. "
                "Keep using SKUEL and insights will appear automatically!",
                icon="💡",
            )

        # Charts visualization section
        charts_section = render_charts_section(0 if load_error else active_total.value)
        subtitle = (
            "Insights could not be counted"
            if load_error
            else _subtitle(matching.value, active_total.value, filtered=filtered)
        )

        # Build page content
        content = Div(
            personal_header_placeholder(),
            PageHeader(
                title="💡 Insights",
                subtitle=subtitle,
            ),
            # The Insights section's pages: its history and the two analytics pages
            # (which pass active_page="insights", so this section stays lit there).
            Div(
                ButtonLink(
                    "📜 View History",
                    href="/insights/history",
                    cls=ButtonT.ghost,
                    size="sm",
                ),
                ButtonLink("📊 Analytics", href="/ui/analytics", cls=ButtonT.ghost, size="sm"),
                ButtonLink(
                    "🗓️ Weekly summary",
                    href="/ui/analytics/weekly-life-summary",
                    cls=ButtonT.ghost,
                    size="sm",
                ),
                cls="flex flex-wrap gap-2 mb-4",
            ),
            render_hub_section(),
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
                SectionHeader("Domains you've had insights in", cls="mt-8"),
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

        context_result = await user_service.get_rich_unified_context(user_uid)
        if context_result.is_error:
            return _error_card(asked, context_result)
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

        parsed = _parse_insights_filters(request)
        if parsed.is_error:
            return refuse_malformed(parsed.expect_error())
        filters = parsed.value
        page_size = 10

        result = await insight_store.get_active_insights(
            user_uid, filters.match, limit=page_size, offset=filters.offset
        )

        if result.is_error:
            logger.error(f"Failed to retrieve insights: {result.error}")
            return render_error_banner("Failed to load more insights", str(result.error))

        new_insights = result.value
        if not new_insights:
            return EmptyState("No more insights to load", id="load-more-trigger", cls="pt-4")

        next_query = _load_more_query(filters, filters.offset + page_size)

        loaded_card_items = [render_insight_card_with_checkbox(insight) for insight in new_insights]

        return Div(
            *loaded_card_items,
            Div(
                id="load-more-trigger",
                hx_get=f"/insights/load-more?{next_query}",
                hx_trigger="revealed",
                hx_swap="outerHTML",
                hx_indicator="#loading-indicator",
            ),
        )
