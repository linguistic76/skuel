"""Goals UI routes.

Provides the read-focused goal list view at /goals and detail view at /goals/detail.
Goals are the gravity well — they show incoming relationships from tasks, habits,
events, choices, and principles.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.inbound.activity_ui_factory import ActivityUIConfig, create_activity_ui_routes
from core.utils.connection_fetcher import GOAL_CONNECTION_CONFIG
from core.utils.entity_filters import filter_goals
from ui.activities.goals_views import (
    GOAL_FILTER_CONFIG,
    GoalDetailView,
    GoalList,
    GoalStatsBar,
)

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.goals_service import GoalsService


def create_goals_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    goals_service: GoalsService,
) -> list[Any]:
    """Register Goals UI routes."""
    config = ActivityUIConfig(
        domain_name="goals",
        domain_singular="goal",
        page_title="Goals",
        filter_params=(("status", "active"), ("sort_by", "target_date")),
        get_all=goals_service.get_user_goals,
        get_one=goals_service.get_goal,
        backend=goals_service.core.backend,
        filter_fn=filter_goals,
        connection_config=GOAL_CONNECTION_CONFIG,
        filter_config=GOAL_FILTER_CONFIG,
        list_component=GoalList,
        stats_component=GoalStatsBar,
        detail_component=GoalDetailView,
    )
    return create_activity_ui_routes(app, rt, config)
