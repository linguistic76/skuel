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
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.personal_header import personal_header_placeholder

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
        """Main goals page — shell renders immediately, content loads via HTMX."""
        require_authenticated_user(request)
        content = Div(
            PageHeader("Goals"),
            content_loading_placeholder("/goals/content", "goals-content"),
            personal_header_placeholder(),
        )
        return await render_activity_sidebar_page(content, active="goals", request=request)

    @rt("/goals/content")
    async def goals_content_fragment(request: Request) -> Any:
        """HTMX fragment: goal list with stats and filters."""
        user_uid = require_authenticated_user(request)

        result = await goals_service.get_user_goals(user_uid)
        if result.is_error:
            error = result.expect_error()
            return Div(render_error_banner(error.user_message or error.message), id="goals-content")

        all_goals = result.value

        status_filter = request.query_params.get("status", "active")
        sort_by = request.query_params.get("sort_by", "target_date")

        filtered = filter_goals(all_goals, status_filter, sort_by)

        goal_uids = [g.uid for g in filtered]
        connections_map = await fetch_entity_connections(
            goals_service.core.backend, GOAL_CONNECTION_CONFIG, goal_uids
        )

        return Div(
            ActivityFilterBar(GOAL_FILTER_CONFIG, {"status": status_filter, "sort_by": sort_by}),
            GoalList(filtered, connections_map),
            GoalStatsBar(all_goals),
            id="goals-content",
        )

    @rt("/goals/list-fragment")
    async def goals_list_fragment(request: Request) -> Any:
        """HTMX fragment: filtered goal list for filter updates."""
        user_uid = require_authenticated_user(request)

        result = await goals_service.get_user_goals(user_uid)
        if result.is_error:
            error = result.expect_error()
            return Div(render_error_banner(error.user_message or error.message), id="goal-list")

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
        """Detail page for a single goal — shell renders immediately, content loads via HTMX."""
        require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Missing goal UID")),
                active="goals",
                request=request,
            )
        content = Div(
            content_loading_placeholder(f"/goals/detail/content?uid={uid}", "goal-detail-content"),
        )
        return await render_activity_sidebar_page(content, active="goals", request=request)

    @rt("/goals/detail/content")
    async def goal_detail_content_fragment(request: Request) -> Any:
        """HTMX fragment: goal detail with connections and relationships."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Div(render_error_banner("Missing goal UID"), id="goal-detail-content")

        goal_result = await goals_service.get_goal(uid)
        if goal_result.is_error:
            return Div(render_error_banner("Goal not found"), id="goal-detail-content")

        goal = goal_result.value
        if goal.user_uid != user_uid:
            return Div(render_error_banner("Goal not found"), id="goal-detail-content")

        connections_map = await fetch_entity_connections(
            goals_service.core.backend, GOAL_CONNECTION_CONFIG, [goal.uid]
        )
        connections = connections_map.get(goal.uid, [])

        return GoalDetailView(goal, connections)

    routes.extend([goals_page, goals_content_fragment, goals_list_fragment, goal_detail_page, goal_detail_content_fragment])
    return routes
