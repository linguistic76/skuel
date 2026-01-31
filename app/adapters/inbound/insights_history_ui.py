"""Insights History UI Routes - Action Tracking & Audit Trail
================================================================

UI routes for viewing dismissed and actioned insights with notes.

Phase 4, Task 17: Action tracking and history page.
"""

from typing import Any

from fasthtml.common import Div, H3, Li, NotStr, P, Select, Span, Ul

from components.insight_card import InsightCard
from core.auth import require_authenticated_user
from core.utils.logging import get_logger
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader
from ui.primitives.badge import Badge

logger = get_logger("skuel.routes.insights.history")


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
        """Display insight action history (dismissed and actioned insights).

        Phase 4, Task 17: Audit trail for user actions.
        """
        user_uid = require_authenticated_user(request)

        # Get query params for filtering
        params = request.query_params
        history_type = params.get("type", "all")  # all, dismissed, actioned

        # Get historical insights
        result = await insight_store.get_insight_history(
            user_uid=user_uid,
            history_type=history_type,
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
                        f'<option value="all" {"selected" if history_type == "all" else ""}>All Actions</option>'
                        f'<option value="dismissed" {"selected" if history_type == "dismissed" else ""}>Dismissed Only</option>'
                        f'<option value="actioned" {"selected" if history_type == "actioned" else ""}>Actioned Only</option>'
                    ),
                    cls="select select-bordered select-sm",
                    onchange="window.location.href='/insights/history?type=' + this.value",
                ),
                cls="flex items-center",
            ),
            cls="mb-6 p-4 bg-base-200 rounded-lg flex justify-between items-center",
        )

        # Build insight cards with action metadata
        if insights:
            insight_items = []
            for insight in insights:
                # Add action metadata header
                action_type = "Dismissed" if insight.dismissed else "Actioned"
                action_date = insight.dismissed_at if insight.dismissed else insight.actioned_at
                action_notes = insight.dismissed_notes if insight.dismissed else insight.actioned_notes

                metadata_header = Div(
                    Div(
                        Badge(
                            action_type,
                            variant="ghost" if insight.dismissed else "success",
                        ),
                        Span(
                            f" on {action_date.strftime('%b %d, %Y at %I:%M %p')}" if action_date else "",
                            cls="text-xs text-base-content/60 ml-2",
                        ),
                        cls="flex items-center mb-2",
                    ),
                    Div(
                        Span("Your notes: ", cls="text-xs font-semibold text-base-content/70"),
                        Span(
                            action_notes if action_notes else "(No notes provided)",
                            cls="text-xs text-base-content/60 italic",
                        ),
                        cls="mb-3",
                    ) if action_notes or insight.dismissed or insight.actioned else Div(),
                    cls="mb-2 p-3 bg-base-100 rounded-md border-l-2 "
                    + ("border-l-base-300" if insight.dismissed else "border-l-success"),
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
                message=empty_message.get(history_type, "No insights found."),
                icon="📜",
            )

        # Build summary stats
        dismissed_count = sum(1 for i in insights if i.dismissed)
        actioned_count = sum(1 for i in insights if i.actioned)

        stats_summary = Div(
            Div(
                Div(
                    P("Total Actions", cls="text-sm text-base-content/70"),
                    P(str(len(insights)), cls="text-3xl font-bold"),
                    cls="stat",
                ),
                Div(
                    P("Dismissed", cls="text-sm text-base-content/70"),
                    P(str(dismissed_count), cls="text-3xl font-bold"),
                    cls="stat",
                ),
                Div(
                    P("Actioned", cls="text-sm text-base-content/70"),
                    P(str(actioned_count), cls="text-3xl font-bold text-success"),
                    cls="stat",
                ),
                cls="stats stats-horizontal shadow mb-6",
            ),
        )

        # Build page content
        content = Div(
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
