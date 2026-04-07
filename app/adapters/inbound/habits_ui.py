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
from core.utils.connection_fetcher import HABIT_CONNECTION_CONFIG, fetch_entity_connections
from core.utils.logging import get_logger
from ui.activities.filter_bar import ActivityFilterBar
from core.utils.entity_filters import filter_habits
from ui.activities.habits_views import (
    HABIT_FILTER_CONFIG,
    HabitDetailView,
    HabitList,
    HabitStatsBar,
)
from ui.activities.nav import render_activity_sidebar_page
from ui.patterns import PageHeader
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.habits_service import HabitsService

logger = get_logger("skuel.routes.habits_ui")


def create_habits_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    habits_service: HabitsService,
) -> list[Any]:
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
            )
            return await render_activity_sidebar_page(content, active="habits", request=request)

        all_habits = result.value

        # Parse filter params
        status_filter = request.query_params.get("status", "active")
        category_filter = request.query_params.get("category", "all")
        sort_by = request.query_params.get("sort_by", "streak")

        filtered = filter_habits(all_habits, status_filter, category_filter, sort_by)

        # Batch-fetch connections
        habit_uids = [h.uid for h in filtered]
        connections_map = await fetch_entity_connections(
            habits_service.core.backend, HABIT_CONNECTION_CONFIG, habit_uids
        )

        habit_count = len(all_habits)
        subtitle = f"{habit_count} habit{'s' if habit_count != 1 else ''}"

        content = Div(
            PageHeader("Habits", subtitle=subtitle),
            HabitStatsBar(all_habits),
            ActivityFilterBar(
                HABIT_FILTER_CONFIG,
                {"status": status_filter, "category": category_filter, "sort_by": sort_by},
            ),
            HabitList(filtered, connections_map),
        )

        return await render_activity_sidebar_page(content, active="habits", request=request)

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
        connections_map = await fetch_entity_connections(
            habits_service.core.backend, HABIT_CONNECTION_CONFIG, habit_uids
        )

        return HabitList(filtered, connections_map)

    @rt("/habits/detail")
    async def habit_detail_page(request: Request) -> Any:
        """Detail page for a single habit with connections and relationships."""
        user_uid = require_authenticated_user(request)

        uid = request.query_params.get("uid", "")
        if not uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Missing habit UID")),
                active="habits",
                request=request,
            )

        habit_result = await habits_service.get_habit(uid)
        if habit_result.is_error:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Habit not found")),
                active="habits",
                request=request,
            )

        habit = habit_result.value
        if habit.user_uid != user_uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Habit not found")),
                active="habits",
                request=request,
            )

        # Fetch connections
        connections_map = await fetch_entity_connections(
            habits_service.core.backend, HABIT_CONNECTION_CONFIG, [habit.uid]
        )
        connections = connections_map.get(habit.uid, [])

        content = HabitDetailView(habit, connections)

        return await render_activity_sidebar_page(content, active="habits", request=request)

    routes.extend([habits_page, habits_list_fragment, habit_detail_page])
    return routes
