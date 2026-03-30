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
from core.utils.logging import get_logger
from ui.activities.goals_views import (
    GoalDetailView,
    GoalFilterBar,
    GoalList,
    GoalStatsBar,
    filter_goals,
)
from ui.layouts.base_page import BasePage
from ui.patterns import PageHeader
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
    from core.services.goals_service import GoalsService

logger = get_logger("skuel.routes.goals_ui")


async def _fetch_goal_connections(
    goals_service: GoalsService,
    goal_uids: list[str],
) -> dict[str, list[dict[str, str]]]:
    """Batch-fetch incoming cross-domain connections for a list of goals.

    Goals are the gravity well: entities point AT goals.
    Returns a map of goal_uid -> list of connection dicts with keys:
    rel_type, source_uid, title, source_type.
    """
    if not goal_uids:
        return {}

    query = """
    MATCH (g:Entity:Goal)
    WHERE g.uid IN $goal_uids
    OPTIONAL MATCH (source:Entity)-[r]->(g)
    WHERE type(r) IN [
        'FULFILLS_GOAL', 'SUPPORTS_GOAL', 'CONTRIBUTES_TO_GOAL',
        'REINFORCES_GOAL', 'APPLIES_KNOWLEDGE', 'INFORMED_BY_GOAL',
        'RELATED_TO'
    ]
    RETURN g.uid AS goal_uid,
           type(r) AS rel_type,
           source.uid AS source_uid,
           source.title AS title,
           source.entity_type AS source_type
    """
    try:
        result = await goals_service.core.backend.execute_query(query, {"goal_uids": goal_uids})
    except Exception:  # safety-net: Neo4j query failure shouldn't break the page
        logger.warning("Failed to fetch goal connections", exc_info=True)
        return {}

    if result.is_error:
        return {}

    connections_map: dict[str, list[dict[str, str]]] = {}
    for record in result.value:
        goal_uid = record["goal_uid"]
        if record.get("rel_type") is None:
            continue
        if goal_uid not in connections_map:
            connections_map[goal_uid] = []
        connections_map[goal_uid].append(
            {
                "rel_type": record["rel_type"],
                "source_uid": record.get("source_uid", ""),
                "title": record.get("title", ""),
                "source_type": record.get("source_type", ""),
            }
        )
    return connections_map


def create_goals_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    goals_service: GoalsService,
) -> RouteList:
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
                cls="uk-container uk-container-small",
            )
            return await BasePage(
                content,
                title="Goals",
                request=request,
                active_page="goals",
            )

        all_goals = result.value

        # Parse filter params
        status_filter = request.query_params.get("status", "active")
        sort_by = request.query_params.get("sort_by", "target_date")

        filtered = filter_goals(all_goals, status_filter, sort_by)

        # Batch-fetch incoming connections for visible goals
        goal_uids = [g.uid for g in filtered]
        connections_map = await _fetch_goal_connections(goals_service, goal_uids)

        goal_count = len(all_goals)
        subtitle = f"{goal_count} goal{'s' if goal_count != 1 else ''}"

        content = Div(
            PageHeader("Goals", subtitle=subtitle),
            GoalStatsBar(all_goals),
            GoalFilterBar(status_filter, sort_by),
            GoalList(filtered, connections_map),
            cls="uk-container uk-container-small",
        )

        return await BasePage(
            content,
            title="Goals",
            request=request,
            active_page="goals",
        )

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
        connections_map = await _fetch_goal_connections(goals_service, goal_uids)

        return GoalList(filtered, connections_map)

    @rt("/goals/detail")
    async def goal_detail_page(request: Request) -> Any:
        """Detail page for a single goal with connections and relationships."""
        user_uid = require_authenticated_user(request)

        uid = request.query_params.get("uid", "")
        if not uid:
            return await BasePage(
                Div(render_error_banner("Missing goal UID"), cls="uk-container uk-container-small"),
                title="Goal Not Found",
                request=request,
                active_page="goals",
            )

        goal_result = await goals_service.get_goal(uid)
        if goal_result.is_error:
            return await BasePage(
                Div(render_error_banner("Goal not found"), cls="uk-container uk-container-small"),
                title="Goal Not Found",
                request=request,
                active_page="goals",
            )

        goal = goal_result.value
        if goal.user_uid != user_uid:
            return await BasePage(
                Div(render_error_banner("Goal not found"), cls="uk-container uk-container-small"),
                title="Goal Not Found",
                request=request,
                active_page="goals",
            )

        # Fetch incoming connections for this goal (gravity well)
        connections_map = await _fetch_goal_connections(goals_service, [goal.uid])
        connections = connections_map.get(goal.uid, [])

        content = GoalDetailView(goal, connections)

        return await BasePage(
            content,
            title=goal.title or "Goal",
            request=request,
            active_page="goals",
        )

    routes.extend([goals_page, goals_list_fragment, goal_detail_page])
    return routes
