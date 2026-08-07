"""
Goals Routes - Configuration-Driven Registration
==================================================

Factory that wires goals API and UI routes using DomainRouteConfig.

Architecture:
    - Config-driven: CRUD, Query, Intelligence factories via create_activity_domain_route_config()
    - API Routes: goals_api.py (domain-specific: status updates)
    - UI Routes:  goals_ui.py  (list, detail, cross-domain views)
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.goals_api import create_goals_api_routes
from adapters.inbound.goals_ui import create_goals_ui_routes
from adapters.inbound.route_factories import (
    create_activity_domain_route_config,
    register_domain_routes,
)
from core.models.goal.goal_request import GoalCreateRequest, GoalUpdateRequest

if TYPE_CHECKING:
    from services_bootstrap import Services


GOALS_CONFIG = create_activity_domain_route_config(
    domain_name="goals",
    primary_service_attr="goals",
    api_factory=create_goals_api_routes,
    ui_factory=create_goals_ui_routes,
    create_schema=GoalCreateRequest,
    update_schema=GoalUpdateRequest,
    uid_prefix="goal",
    request_create_method="create_goal",
    supports_goal_filter=False,
    supports_habit_filter=False,
    api_related_services={"user_service": "user", "principles_service": "principles"},
    ui_related_services={"connection_fetch_backend": "connection_fetch_backend"},
    prometheus_metrics_attr="prometheus_metrics",
)


def create_goals_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> None:
    """Wire goals API and UI routes using configuration-driven registration."""
    register_domain_routes(app, rt, services, GOALS_CONFIG)


__all__ = ["create_goals_routes"]
