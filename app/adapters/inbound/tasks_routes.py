"""
Tasks Routes - Configuration-Driven Registration
==================================================

Factory that wires tasks API and UI routes using DomainRouteConfig.

Architecture:
    - Config-driven: CRUD, Query, Intelligence factories via create_activity_domain_route_config()
    - API Routes: tasks_api.py (domain-specific: status updates)
    - UI Routes:  tasks_ui.py  (list, detail, cross-domain views)
"""

from typing import TYPE_CHECKING, Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories import (
    create_activity_domain_route_config,
    register_domain_routes,
)
from adapters.inbound.tasks_api import create_tasks_api_routes
from adapters.inbound.tasks_ui import create_tasks_ui_routes
from core.models.task.task_request import TaskCreateRequest, TaskUpdateRequest

if TYPE_CHECKING:
    from services_bootstrap import Services


TASKS_CONFIG = create_activity_domain_route_config(
    domain_name="tasks",
    primary_service_attr="tasks",
    api_factory=create_tasks_api_routes,
    ui_factory=create_tasks_ui_routes,
    create_schema=TaskCreateRequest,
    update_schema=TaskUpdateRequest,
    uid_prefix="task",
    request_create_method="create_task",
    supports_goal_filter=True,
    supports_habit_filter=True,
    api_related_services={
        "goals_service": "goals",
        "habits_service": "habits",
    },
    ui_related_services={
        "connection_fetch_backend": "connection_fetch_backend",
        "user_service": "user",
        "goals_service": "goals",
        "habits_service": "habits",
    },
    prometheus_metrics_attr="prometheus_metrics",
)


def create_tasks_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: "Services | None", _sync_service: Any = None
) -> None:
    """Wire tasks API and UI routes using configuration-driven registration."""
    register_domain_routes(app, rt, services, TASKS_CONFIG)


__all__ = ["create_tasks_routes"]
