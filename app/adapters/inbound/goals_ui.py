"""Goals UI routes.

Provides the read-focused goal list view at /goals and detail view at /goals/detail.
Goals are the gravity well — they show incoming relationships from tasks, habits,
events, choices, and principles.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from core.utils.connection_fetcher import GOAL_CONNECTION_CONFIG, fetch_entity_connections
from core.utils.entity_filters import filter_goals
from core.utils.logging import get_logger
from ui.activities.filter_bar import ActivityFilterBar
from ui.activities.goals_views import (
    GOAL_FILTER_CONFIG,
    GoalDetailView,
    GoalList,
    GoalStatsBar,
)
from ui.activities.nav import render_activity_sidebar_page
from ui.patterns import PageHeader
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.goals_service import GoalsService

logger = get_logger("skuel.routes.goals_ui")


def create_goals_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    goals_service: GoalsService,
) -> list[Any]:
    """Register Goals UI routes."""
    routes: list[Any] = []

    @rt("/goals")
    async def goals_page(request: Request) -> Any:
        """Main goals page — lists all user goals with filters."""
        user_uid = require_authenticated_user(request)

        result = await goals_service.get_user_goals(user_uid)
        if result.is_error:
            error = result.expect_error()
            content = Div(
                PageHeader("Goals"),
                render_error_banner(error.user_message or error.message),
            )
            return await render_activity_sidebar_page(content, active="goals", request=request)

        all_goals = result.value

        # Parse filter params
        status_filter = request.query_params.get("status", "active")
        sort_by = request.query_params.get("sort_by", "target_date")

        filtered = filter_goals(all_goals, status_filter, sort_by)

        # Batch-fetch incoming connections for visible goals
        goal_uids = [g.uid for g in filtered]
        connections_map = await fetch_entity_connections(
            goals_service.core.backend, GOAL_CONNECTION_CONFIG, goal_uids
        )

        goal_count = len(all_goals)
        subtitle = f"{goal_count} goal{'s' if goal_count != 1 else ''}"

        content = Div(
            PageHeader("Goals", subtitle=subtitle),
            GoalStatsBar(all_goals),
            ActivityFilterBar(GOAL_FILTER_CONFIG, {"status": status_filter, "sort_by": sort_by}),
            GoalList(filtered, connections_map),
        )

        return await render_activity_sidebar_page(content, active="goals", request=request)

    @rt("/goals/list-fragment")
    async def goals_list_fragment(request: Request) -> Any:
        """HTMX fragment: filtered goal list for filter updates."""
        user_uid = require_authenticated_user(request)

        result = await goals_service.get_user_goals(user_uid)
        if result.is_error:
            error = result.expect_error()
            return render_error_banner(error.user_message or error.message)

        all_goals = result.value

        status_filter = request.query_params.get("status", "active")
        sort_by = request.query_params.get("sort_by", "target_date")

        filtered = filter_goals(all_goals, status_filter, sort_by)

        goal_uids = [g.uid for g in filtered]
        connections_map = await fetch_entity_connections(
            goals_service.core.backend, GOAL_CONNECTION_CONFIG, goal_uids
        )

        return GoalList(filtered, connections_map)

    @rt("/goals/detail")
    async def goal_detail_page(request: Request) -> Any:
        """Detail page for a single goal with connections and relationships."""
        user_uid = require_authenticated_user(request)

        uid = request.query_params.get("uid", "")
        if not uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Missing goal UID")),
                active="goals",
                request=request,
            )

        goal_result = await goals_service.get_goal(uid)
        if goal_result.is_error:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Goal not found")),
                active="goals",
                request=request,
            )

        goal = goal_result.value
        if goal.user_uid != user_uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Goal not found")),
                active="goals",
                request=request,
            )

        # Fetch incoming connections for this goal (gravity well)
        connections_map = await fetch_entity_connections(
            goals_service.core.backend, GOAL_CONNECTION_CONFIG, [goal.uid]
        )
        connections = connections_map.get(goal.uid, [])

        content = GoalDetailView(goal, connections)

        return await render_activity_sidebar_page(content, active="goals", request=request)

    routes.extend([goals_page, goals_list_fragment, goal_detail_page])
    return routes
