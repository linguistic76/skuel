"""Habits UI routes.

Provides the read-focused habit list view at /habits and detail view at /habits/detail.
Habits enter via YAML upload; this UI shows them with status controls,
streaks, atomic habits, cross-domain connections, and EntityRelationshipsSection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.inbound.activity_ui_factory import ActivityUIConfig, create_activity_ui_routes
from core.utils.connection_fetcher import HABIT_CONNECTION_CONFIG
from core.utils.entity_filters import filter_habits
from ui.activities.habits_views import (
    HABIT_FILTER_CONFIG,
    HabitDetailView,
    HabitList,
    HabitStatsBar,
)

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.habits_service import HabitsService


def create_habits_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    habits_service: HabitsService,
) -> list[Any]:
    """Register Habits UI routes."""
    config = ActivityUIConfig(
        domain_name="habits",
        domain_singular="habit",
        page_title="Habits",
        filter_params=(("status", "active"), ("category", "all"), ("sort_by", "streak")),
        get_all=habits_service.get_user_habits,
        get_one=habits_service.get_habit,
        backend=habits_service.core.backend,
        filter_fn=filter_habits,
        connection_config=HABIT_CONNECTION_CONFIG,
        filter_config=HABIT_FILTER_CONFIG,
        list_component=HabitList,
        stats_component=HabitStatsBar,
        detail_component=HabitDetailView,
    )
    return create_activity_ui_routes(app, rt, config)
