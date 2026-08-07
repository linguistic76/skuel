"""
Habits Routes - Configuration-Driven Registration
===================================================

Factory that wires habits API and UI routes using DomainRouteConfig.

Architecture:
    - Config-driven: CRUD, Query, Intelligence factories via create_activity_domain_route_config()
    - API Routes: habits_api.py (domain-specific: status updates)
    - UI Routes:  habits_ui.py  (list, detail, cross-domain views)
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.habits_api import create_habits_api_routes
from adapters.inbound.habits_ui import create_habits_ui_routes
from adapters.inbound.route_factories import (
    create_activity_domain_route_config,
    register_domain_routes,
)
from core.models.habit.habit_request import HabitCreateRequest, HabitUpdateRequest

if TYPE_CHECKING:
    from services_bootstrap import Services


HABITS_CONFIG = create_activity_domain_route_config(
    domain_name="habits",
    primary_service_attr="habits",
    api_factory=create_habits_api_routes,
    ui_factory=create_habits_ui_routes,
    create_schema=HabitCreateRequest,
    update_schema=HabitUpdateRequest,
    uid_prefix="habit",
    request_create_method="create_habit",
    supports_goal_filter=False,
    supports_habit_filter=False,
    api_related_services={"principles_service": "principles"},
    ui_related_services={
        "connection_fetch_backend": "connection_fetch_backend",
        # Owner-scopes the Habit ↔ Choice fragment: INFORMS_CHOICE / IMPACTS_HABIT
        # edges can cross users, so related choices are filtered through the
        # choices facade's verify_ownership (USER_OWNED 404-not-403 invariant).
        "choices_ownership": "choices",
    },
    prometheus_metrics_attr="prometheus_metrics",
)


def create_habits_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> None:
    """Wire habits API and UI routes using configuration-driven registration."""
    register_domain_routes(app, rt, services, HABITS_CONFIG)


__all__ = ["create_habits_routes"]
