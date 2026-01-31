"""Insights UI Routes - Event-Driven Insights Dashboard
========================================================

UI routes for displaying and managing event-driven insights.

Phase 1 (January 2026): Insight dashboard with dismiss/action functionality.
"""

from typing import Any

from fasthtml.common import Div, Form, H1, H2, NotStr, P, Select

from components.insight_card import DismissedInsightMessage, InsightCard
from core.auth import require_authenticated_user
from core.models.insight.persisted_insight import InsightImpact, InsightType
from core.utils.logging import get_logger
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader
from ui.primitives.button import Button

logger = get_logger("skuel.routes.insights.ui")


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

        # Get query params for filtering
        params = request.query_params
        domain_filter = params.get("domain")
        impact_filter = params.get("impact")

        # Get active insights from store
        result = await insight_store.get_active_insights(
            user_uid=user_uid,
            domain=domain_filter,
            limit=50,
        )

        if result.is_error:
            logger.error(f"Failed to retrieve insights: {result.error}")
            insights = []
        else:
            insights = result.value

            # Apply impact filter (client-side for now)
            if impact_filter:
                insights = [i for i in insights if i.impact.value == impact_filter]

        # Build filter form
        filter_form = Div(
            Form(
                Div(
                    Select(
                        NotStr(
                            '<option value="">All Domains</option>'
                            '<option value="habits">Habits</option>'
                            '<option value="choices">Choices</option>'
                            '<option value="principles">Principles</option>'
                            '<option value="tasks">Tasks</option>'
                            '<option value="goals">Goals</option>'
                            '<option value="events">Events</option>'
                        ),
                        name="domain",
                        cls="select select-bordered select-sm",
                        value=domain_filter or "",
                    ),
                    Select(
                        NotStr(
                            '<option value="">All Impact Levels</option>'
                            '<option value="critical">Critical</option>'
                            '<option value="high">High</option>'
                            '<option value="medium">Medium</option>'
                            '<option value="low">Low</option>'
                        ),
                        name="impact",
                        cls="select select-bordered select-sm",
                        value=impact_filter or "",
                    ),
                    Button(
                        "Filter",
                        type="submit",
                        cls="btn btn-sm btn-primary",
                    ),
                    cls="flex gap-3",
                ),
                method="GET",
                action="/insights",
            ),
            cls="mb-6 p-4 bg-base-200 rounded-lg",
        )

        # Build insight cards
        if insights:
            insight_cards = Div(
                *[InsightCard(insight) for insight in insights],
                cls="space-y-4",
            )
        else:
            # Empty state
            insight_cards = EmptyState(
                title="No Active Insights",
                message="Your intelligence services haven't detected any patterns yet. "
                "Keep using SKUEL and insights will appear automatically!",
                icon="💡",
            )

        # Build page content
        content = Div(
            PageHeader(
                title="💡 Insights",
                subtitle=f"{len(insights)} active insight{'s' if len(insights) != 1 else ''} from your behavior patterns",
            ),
            filter_form,
            insight_cards,
            cls="space-y-6",
        )

        return BasePage(
            content,
            title="Insights | SKUEL",
            page_type=PageType.STANDARD,
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
                    P("Total Insights", cls="text-sm text-base-content/70"),
                    P(str(stats.get("total_insights", 0)), cls="text-3xl font-bold"),
                    cls="stat",
                ),
                Div(
                    P("Active Insights", cls="text-sm text-base-content/70"),
                    P(str(stats.get("active_insights", 0)), cls="text-3xl font-bold"),
                    cls="stat",
                ),
                Div(
                    P("Actioned", cls="text-sm text-base-content/70"),
                    P(str(stats.get("actioned_insights", 0)), cls="text-3xl font-bold"),
                    cls="stat",
                ),
                Div(
                    P("Action Rate", cls="text-sm text-base-content/70"),
                    P(
                        f"{stats.get('action_rate', 0):.0%}",
                        cls="text-3xl font-bold",
                    ),
                    cls="stat",
                ),
                cls="stats stats-vertical lg:stats-horizontal shadow",
            ),
            Div(
                H2("Domains", cls="text-xl font-bold mb-4 mt-8"),
                P(
                    ", ".join(stats.get("domains", [])) or "None",
                    cls="text-base-content/70",
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

        return BasePage(
            content,
            title="Insight Statistics | SKUEL",
            page_type=PageType.STANDARD,
        )

    return [insights_dashboard, insights_stats]
