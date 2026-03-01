"""
Goals Routes - Config-Driven Registration
==========================================

Activity Domain: CRUD, Query, and Intelligence factories declared in config.
Status factory remains in goals_api.py.
"""

from adapters.inbound.goals_api import create_goals_api_routes
from adapters.inbound.goals_ui import create_goals_ui_routes
from adapters.inbound.route_factories import (
    create_activity_domain_route_config,
    register_domain_routes,
)
from core.models.goal.goal_request import GoalCreateRequest, GoalUpdateRequest

GOALS_CONFIG = create_activity_domain_route_config(
    domain_name="goals",
    primary_service_attr="goals",
    api_factory=create_goals_api_routes,
    ui_factory=create_goals_ui_routes,
    create_schema=GoalCreateRequest,
    update_schema=GoalUpdateRequest,
    uid_prefix="goal",
    supports_goal_filter=False,
    supports_habit_filter=True,
    api_related_services={
        "user_service": "user_service",
        "habits_service": "habits",
    },
    prometheus_metrics_attr="prometheus_metrics",
)


def create_goals_routes(app, rt, services, _sync_service=None):
    """Wire goals API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, GOALS_CONFIG)


__all__ = ["create_goals_routes"]
