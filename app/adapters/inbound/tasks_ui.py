"""Tasks UI routes.

Provides the read-focused task list view at /tasks and detail view at /tasks/detail.
Tasks enter via YAML upload; this UI shows them with status controls,
priority, cross-domain connections, and EntityRelationshipsSection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.fasthtml_types import Request
from core.utils.connection_fetcher import TASK_CONNECTION_CONFIG, fetch_entity_connections
from core.utils.entity_filters import filter_tasks
from core.utils.logging import get_logger
from ui.activities.filter_bar import ActivityFilterBar
from ui.activities.nav import render_activity_sidebar_page
from ui.activities.tasks_views import (
    TASK_FILTER_CONFIG,
    TaskDetailView,
    TaskList,
    TaskStatsBar,
)
from ui.patterns import PageHeader
from ui.patterns.error_banner import render_error_banner
from ui.patterns.personal_header import personal_header_placeholder

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.tasks_service import TasksService

logger = get_logger("skuel.routes.tasks_ui")


def create_tasks_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    tasks_service: TasksService,
    user_service: Any = None,  # kept for DomainRouteConfig signature compat
) -> list[Any]:
    """Register Tasks UI routes."""
    routes: list[Any] = []

    @rt("/tasks")
    async def tasks_page(request: Request) -> Any:
        """Main tasks page — lists all user tasks with filters."""
        user_uid = require_authenticated_user(request)

        result = await tasks_service.get_user_tasks(user_uid)
        if result.is_error:
            error = result.expect_error()
            content = Div(
                PageHeader("Tasks"),
                render_error_banner(error.user_message or error.message),
            )
            return await render_activity_sidebar_page(content, active="tasks", request=request)

        all_tasks = result.value

        # Parse filter params from query string
        status_filter = request.query_params.get("status", "active")
        priority_filter = request.query_params.get("priority", "all")
        sort_by = request.query_params.get("sort_by", "priority")

        filtered = filter_tasks(all_tasks, status_filter, priority_filter, sort_by)

        # Batch-fetch cross-domain connections for visible tasks
        task_uids = [t.uid for t in filtered]
        connections_map = await fetch_entity_connections(
            tasks_service.core.backend, TASK_CONNECTION_CONFIG, task_uids
        )

        task_count = len(all_tasks)
        subtitle = f"{task_count} task{'s' if task_count != 1 else ''}"

        content = Div(
            PageHeader("Tasks", subtitle=subtitle),
            personal_header_placeholder(),
            TaskStatsBar(all_tasks),
            ActivityFilterBar(
                TASK_FILTER_CONFIG,
                {"status": status_filter, "priority": priority_filter, "sort_by": sort_by},
            ),
            TaskList(filtered, connections_map),
        )

        return await render_activity_sidebar_page(content, active="tasks", request=request)

    @rt("/tasks/list-fragment")
    async def tasks_list_fragment(request: Request) -> Any:
        """HTMX fragment: filtered task list for filter updates."""
        user_uid = require_authenticated_user(request)

        result = await tasks_service.get_user_tasks(user_uid)
        if result.is_error:
            error = result.expect_error()
            return render_error_banner(error.user_message or error.message)

        all_tasks = result.value

        status_filter = request.query_params.get("status", "active")
        priority_filter = request.query_params.get("priority", "all")
        sort_by = request.query_params.get("sort_by", "priority")

        filtered = filter_tasks(all_tasks, status_filter, priority_filter, sort_by)

        task_uids = [t.uid for t in filtered]
        connections_map = await fetch_entity_connections(
            tasks_service.core.backend, TASK_CONNECTION_CONFIG, task_uids
        )

        return TaskList(filtered, connections_map)

    @rt("/tasks/detail")
    async def task_detail_page(request: Request) -> Any:
        """Detail page for a single task with connections and relationships."""
        user_uid = require_authenticated_user(request)

        uid = request.query_params.get("uid", "")
        if not uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Missing task UID")),
                active="tasks",
                request=request,
            )

        task_result = await tasks_service.get_task(uid)
        if task_result.is_error:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Task not found")),
                active="tasks",
                request=request,
            )

        task = task_result.value
        if task.user_uid != user_uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Task not found")),
                active="tasks",
                request=request,
            )

        # Fetch connections for this task
        connections_map = await fetch_entity_connections(
            tasks_service.core.backend, TASK_CONNECTION_CONFIG, [task.uid]
        )
        connections = connections_map.get(task.uid, [])

        content = TaskDetailView(task, connections)

        return await render_activity_sidebar_page(content, active="tasks", request=request)

    routes.extend([tasks_page, tasks_list_fragment, task_detail_page])
    return routes
