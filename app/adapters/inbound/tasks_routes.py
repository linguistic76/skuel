"""
Tasks Routes - Config-Driven Registration
==========================================

Activity Domain pilot: CRUD, Query, and Intelligence factories are declared
in the config.  Status and Analytics factories (runtime closures) remain in
tasks_api.py.
"""

from adapters.inbound.tasks_api import create_tasks_api_routes
from adapters.inbound.tasks_ui import create_tasks_ui_routes
from core.infrastructure.routes import create_activity_domain_route_config, register_domain_routes
from core.models.ku.ku_request import KuTaskCreateRequest as TaskCreateRequest, KuUpdateRequest as TaskUpdateRequest

TASKS_CONFIG = create_activity_domain_route_config(
    domain_name="tasks",
    primary_service_attr="tasks",
    api_factory=create_tasks_api_routes,
    ui_factory=create_tasks_ui_routes,
    create_schema=TaskCreateRequest,
    update_schema=TaskUpdateRequest,
    uid_prefix="task",
    supports_goal_filter=True,
    supports_habit_filter=True,
    api_related_services={
        "user_service": "user_service",
        "goals_service": "goals",
        "habits_service": "habits",
    },
    prometheus_metrics_attr="prometheus_metrics",
)


def create_tasks_routes(app, rt, services, _sync_service=None):
    """Wire tasks API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, TASKS_CONFIG)


__all__ = ["create_tasks_routes"]
