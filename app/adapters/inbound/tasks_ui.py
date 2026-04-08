"""Tasks UI routes.

Provides the read-focused task list view at /tasks and detail view at /tasks/detail.
Tasks enter via YAML upload; this UI shows them with status controls,
priority, cross-domain connections, and EntityRelationshipsSection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.inbound.activity_ui_factory import ActivityUIConfig, create_activity_ui_routes
from core.utils.connection_fetcher import TASK_CONNECTION_CONFIG
from core.utils.entity_filters import filter_tasks
from ui.activities.tasks_views import (
    TASK_FILTER_CONFIG,
    TaskDetailView,
    TaskList,
    TaskStatsBar,
)

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.tasks_service import TasksService


def create_tasks_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    tasks_service: TasksService,
    user_service: Any = None,  # kept for DomainRouteConfig signature compat
) -> list[Any]:
    """Register Tasks UI routes."""
    config = ActivityUIConfig(
        domain_name="tasks",
        domain_singular="task",
        page_title="Tasks",
        filter_params=(("status", "active"), ("priority", "all"), ("sort_by", "priority")),
        get_all=tasks_service.get_user_tasks,
        get_one=tasks_service.get_task,
        backend=tasks_service.core.backend,
        filter_fn=filter_tasks,
        connection_config=TASK_CONNECTION_CONFIG,
        filter_config=TASK_FILTER_CONFIG,
        list_component=TaskList,
        stats_component=TaskStatsBar,
        detail_component=TaskDetailView,
    )
    return create_activity_ui_routes(app, rt, config)
