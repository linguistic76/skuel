"""
Habits Routes - Config-Driven Registration
============================================

Activity Domain: CRUD, Query, and Intelligence factories declared in config.
Status and Analytics factories remain in habits_api.py.
"""

from adapters.inbound.habits_api import create_habits_api_routes
from adapters.inbound.habits_ui import create_habits_ui_routes
from core.infrastructure.routes import create_activity_domain_route_config, register_domain_routes
from core.models.habit.habit_request import HabitCreateRequest, HabitUpdateRequest

HABITS_CONFIG = create_activity_domain_route_config(
    domain_name="habits",
    primary_service_attr="habits",
    api_factory=create_habits_api_routes,
    ui_factory=create_habits_ui_routes,
    create_schema=HabitCreateRequest,
    update_schema=HabitUpdateRequest,
    uid_prefix="habit",
    supports_goal_filter=True,
    supports_habit_filter=False,
    api_related_services={
        "user_service": "user_service",
        "goals_service": "goals",
    },
    ui_related_services={
        "goals_service": "goals",
    },
)


def create_habits_routes(app, rt, services, _sync_service=None):
    """Wire habits API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, HABITS_CONFIG)


__all__ = ["create_habits_routes"]
