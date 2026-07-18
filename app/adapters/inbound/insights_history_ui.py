"""Insights History UI Routes - Action Tracking & Audit Trail
================================================================

UI routes for viewing dismissed and actioned insights with notes.
"""

from dataclasses import dataclass
from typing import Any

from fasthtml.common import Div, NotStr, Span

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from core.utils.logging import get_logger
from ui.feedback import Badge, BadgeT
from ui.forms import Select
from ui.insights.insight_card import InsightCard
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader
from ui.patterns.personal_header import personal_header_placeholder
from ui.patterns.stats_grid import StatItem, StatsGrid

logger = get_logger("skuel.routes.insights.history")


# ============================================================================
# TYPED QUERY PARAMETERS
# ============================================================================


@dataclass
class InsightsHistoryParams:
    """Typed parameters for insights history queries."""

    history_type: str


def parse_insights_history_params(request: Request) -> InsightsHistoryParams:
    """
    Extract insights history parameters from request query params.

    Args:
        request: Starlette request object

    Returns:
        Typed InsightsHistoryParams with defaults applied
    """
    return InsightsHistoryParams(
        history_type=request.query_params.get("type", "all"),
    )


def create_insights_history_routes(
    app: Any,
    rt: Any,
    insight_store: Any,
) -> list[Any]:
    """Create insights history UI routes.

    Args:
        app: FastHTML app instance
        rt: Route decorator
        insight_store: InsightStore service

    Returns:
        List of route handler functions
    """

    @rt("/insights/history")
    async def insights_history_page(request):
        """Display insight action history (dismissed and actioned insights)."""
        user_uid = require_authenticated_user(request)

        # Parse typed parameters for filtering
        params = parse_insights_history_params(request)

        # Get historical insights
        result = await insight_store.get_insight_history(
            user_uid=user_uid,
            history_type=params.history_type,  # all, dismissed, actioned
            limit=100,
        )

        if result.is_error:
            logger.error(f"Failed to retrieve insight history: {result.error}")
            insights = []
        else:
            insights = result.value

        # Build filter controls
        filter_controls = Div(
            Div(
                Span("Filter: ", cls="text-sm font-medium mr-2"),
                Select(
                    NotStr(
                        f'<option value="all" {"selected" if params.history_type == "all" else ""}>All Actions</option>'
                        f'<option value="dismissed" {"selected" if params.history_type == "dismissed" else ""}>Dismissed Only</option>'
                        f'<option value="actioned" {"selected" if params.history_type == "actioned" else ""}>Actioned Only</option>'
                    ),
                    size=Size.sm,
                    full_width=False,
                    onchange="window.location.href='/insights/history?type=' + this.value",
                ),
                cls="flex items-center",
            ),
            cls="mb-6 p-4 bg-muted rounded-lg flex justify-between items-center",
        )

        # Build insight cards with action metadata
        if insights:
            insight_items = []
            for insight in insights:
                # Add action metadata header
                action_type = "Dismissed" if insight.dismissed else "Actioned"
                action_date = insight.dismissed_at if insight.dismissed else insight.actioned_at
                action_notes = (
                    insight.dismissed_notes if insight.dismissed else insight.actioned_notes
                )

                metadata_header = Div(
                    Div(
                        Badge(
                            action_type,
                            variant=BadgeT.ghost if insight.dismissed else BadgeT.success,
                        ),
                        Span(
                            f" on {action_date.strftime('%b %d, %Y at %I:%M %p')}"
                            if action_date
                            else "",
                            cls="text-xs text-muted-foreground ml-2",
                        ),
                        cls="flex items-center mb-2",
                    ),
                    Div(
                        Span("Your notes: ", cls="text-xs font-semibold text-muted-foreground"),
                        Span(
                            action_notes if action_notes else "(No notes provided)",
                            cls="text-xs text-muted-foreground italic",
                        ),
                        cls="mb-3",
                    )
                    if action_notes or insight.dismissed or insight.actioned
                    else Div(),
                    cls="mb-2 p-3 bg-background rounded-md border-l-2 "
                    + ("border-l-border" if insight.dismissed else "border-l-success"),
                )

                # Wrap card with metadata
                item = Div(
                    metadata_header,
                    InsightCard(insight),
                    cls="mb-4",
                )
                insight_items.append(item)

            history_cards = Div(*insight_items)
        else:
            # Empty state
            empty_message = {
                "all": "You haven't dismissed or acted on any insights yet.",
                "dismissed": "You haven't dismissed any insights yet.",
                "actioned": "You haven't acted on any insights yet. When you take action on insights, they'll appear here.",
            }
            history_cards = EmptyState(
                title="No Action History",
                description=empty_message.get(params.history_type, "No insights found."),
                icon="📜",
            )

        # Build summary stats
        dismissed_count = sum(1 for i in insights if i.dismissed)
        actioned_count = sum(1 for i in insights if i.actioned)

        stats_summary = StatsGrid(
            [
                StatItem(label="Total Actions", value=str(len(insights))),
                StatItem(label="Dismissed", value=str(dismissed_count)),
                StatItem(label="Actioned", value=str(actioned_count), color="success"),
            ],
            cols=3,
            cls="mb-6",
        )

        # Build page content
        content = Div(
            personal_header_placeholder(),
            PageHeader(
                title="📜 Insight History",
                subtitle=f"{len(insights)} historical insight{'s' if len(insights) != 1 else ''} - audit trail of your actions",
            ),
            stats_summary if insights else Div(),
            filter_controls,
            history_cards,
            cls="space-y-6",
        )

        return BasePage(
            content,
            title="Insight History | SKUEL",
            page_type=PageType.STANDARD,
            request=request,
            active_page="insights",
        )

    return [insights_history_page]
