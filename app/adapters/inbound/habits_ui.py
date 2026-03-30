"""Habits UI routes.

Provides the read-focused habit list view at /habits and detail view at /habits/detail.
Habits enter via YAML upload; this UI shows them with status controls,
streaks, atomic habits, cross-domain connections, and EntityRelationshipsSection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from core.utils.logging import get_logger
from ui.activities.habits_views import (
    HabitDetailView,
    HabitFilterBar,
    HabitList,
    HabitStatsBar,
    filter_habits,
)
from ui.layouts.base_page import BasePage
from ui.patterns import PageHeader
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
    from core.services.habits_service import HabitsService

logger = get_logger("skuel.routes.habits_ui")


async def _fetch_habit_connections(
    habits_service: HabitsService,
    habit_uids: list[str],
) -> dict[str, list[dict[str, str]]]:
    """Batch-fetch outbound cross-domain connections for a list of habits.

    Returns a map of habit_uid -> list of connection dicts with keys:
    rel_type, target_uid, title, target_type.
    """
    if not habit_uids:
        return {}

    query = """
    MATCH (h:Entity:Habit)
    WHERE h.uid IN $habit_uids
    OPTIONAL MATCH (h)-[r]->(target:Entity)
    WHERE type(r) IN [
        'REINFORCES_GOAL', 'APPLIES_KNOWLEDGE', 'REINFORCED_BY_PRINCIPLE',
        'PART_OF_LEARNING_STEP', 'PART_OF_LEARNING_PATH',
        'RELATED_TO'
    ]
    RETURN h.uid AS habit_uid,
           type(r) AS rel_type,
           target.uid AS target_uid,
           target.title AS title,
           target.entity_type AS target_type
    """
    try:
        result = await habits_service.core.backend.execute_query(query, {"habit_uids": habit_uids})
    except Exception:  # safety-net: Neo4j query failure shouldn't break the page
        logger.warning("Failed to fetch habit connections", exc_info=True)
        return {}

    if result.is_error:
        return {}

    connections_map: dict[str, list[dict[str, str]]] = {}
    for record in result.value:
        habit_uid = record["habit_uid"]
        if record.get("rel_type") is None:
            continue
        if habit_uid not in connections_map:
            connections_map[habit_uid] = []
        connections_map[habit_uid].append(
            {
                "rel_type": record["rel_type"],
                "target_uid": record.get("target_uid", ""),
                "title": record.get("title", ""),
                "target_type": record.get("target_type", ""),
            }
        )
    return connections_map


def create_habits_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    habits_service: HabitsService,
) -> RouteList:
    """Register Habits UI routes."""
    routes: list[Any] = []

    @rt("/habits")
    async def habits_page(request: Request) -> Any:
        """Main habits page — lists all user habits with filters."""
        user_uid = require_authenticated_user(request)

        result = await habits_service.get_user_habits(user_uid)
        if result.is_error:
            error = result.expect_error()
            content = Div(
                PageHeader("Habits"),
                render_error_banner(error.user_message or error.message),
                cls="uk-container uk-container-small",
            )
            return await BasePage(
                content,
                title="Habits",
                request=request,
                active_page="habits",
            )

        all_habits = result.value

        # Parse filter params
        status_filter = request.query_params.get("status", "active")
        category_filter = request.query_params.get("category", "all")
        sort_by = request.query_params.get("sort_by", "streak")

        filtered = filter_habits(all_habits, status_filter, category_filter, sort_by)

        # Batch-fetch connections
        habit_uids = [h.uid for h in filtered]
        connections_map = await _fetch_habit_connections(habits_service, habit_uids)

        habit_count = len(all_habits)
        subtitle = f"{habit_count} habit{'s' if habit_count != 1 else ''}"

        content = Div(
            PageHeader("Habits", subtitle=subtitle),
            HabitStatsBar(all_habits),
            HabitFilterBar(status_filter, category_filter, sort_by),
            HabitList(filtered, connections_map),
            cls="uk-container uk-container-small",
        )

        return await BasePage(
            content,
            title="Habits",
            request=request,
            active_page="habits",
        )

    @rt("/habits/list-fragment")
    async def habits_list_fragment(request: Request) -> Any:
        """HTMX fragment: filtered habit list for filter updates."""
        user_uid = require_authenticated_user(request)

        result = await habits_service.get_user_habits(user_uid)
        if result.is_error:
            error = result.expect_error()
            return render_error_banner(error.user_message or error.message)

        all_habits = result.value

        status_filter = request.query_params.get("status", "active")
        category_filter = request.query_params.get("category", "all")
        sort_by = request.query_params.get("sort_by", "streak")

        filtered = filter_habits(all_habits, status_filter, category_filter, sort_by)

        habit_uids = [h.uid for h in filtered]
        connections_map = await _fetch_habit_connections(habits_service, habit_uids)

        return HabitList(filtered, connections_map)

    @rt("/habits/detail")
    async def habit_detail_page(request: Request) -> Any:
        """Detail page for a single habit with connections and relationships."""
        user_uid = require_authenticated_user(request)

        uid = request.query_params.get("uid", "")
        if not uid:
            return await BasePage(
                Div(
                    render_error_banner("Missing habit UID"), cls="uk-container uk-container-small"
                ),
                title="Habit Not Found",
                request=request,
                active_page="habits",
            )

        habit_result = await habits_service.get_habit(uid)
        if habit_result.is_error:
            return await BasePage(
                Div(render_error_banner("Habit not found"), cls="uk-container uk-container-small"),
                title="Habit Not Found",
                request=request,
                active_page="habits",
            )

        habit = habit_result.value
        if habit.user_uid != user_uid:
            return await BasePage(
                Div(render_error_banner("Habit not found"), cls="uk-container uk-container-small"),
                title="Habit Not Found",
                request=request,
                active_page="habits",
            )

        # Fetch connections
        connections_map = await _fetch_habit_connections(habits_service, [habit.uid])
        connections = connections_map.get(habit.uid, [])

        content = HabitDetailView(habit, connections)

        return await BasePage(
            content,
            title=habit.title or "Habit",
            request=request,
            active_page="habits",
        )

    routes.extend([habits_page, habits_list_fragment, habit_detail_page])
    return routes
