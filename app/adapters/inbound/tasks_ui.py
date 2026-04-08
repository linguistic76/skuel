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
from ui.patterns.loading import content_loading_placeholder
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
        """Main tasks page — shell renders immediately, content loads via HTMX."""
        require_authenticated_user(request)
        content = Div(
            PageHeader("Tasks"),
            personal_header_placeholder(),
            content_loading_placeholder("/tasks/content", "tasks-content"),
        )
        return await render_activity_sidebar_page(content, active="tasks", request=request)

    @rt("/tasks/content")
    async def tasks_content_fragment(request: Request) -> Any:
        """HTMX fragment: task list with stats and filters."""
        user_uid = require_authenticated_user(request)

        result = await tasks_service.get_user_tasks(user_uid)
        if result.is_error:
            error = result.expect_error()
            return Div(render_error_banner(error.user_message or error.message), id="tasks-content")

        all_tasks = result.value

        status_filter = request.query_params.get("status", "active")
        priority_filter = request.query_params.get("priority", "all")
        sort_by = request.query_params.get("sort_by", "priority")

        filtered = filter_tasks(all_tasks, status_filter, priority_filter, sort_by)

        task_uids = [t.uid for t in filtered]
        connections_map = await fetch_entity_connections(
            tasks_service.core.backend, TASK_CONNECTION_CONFIG, task_uids
        )

        return Div(
            TaskStatsBar(all_tasks),
            ActivityFilterBar(
                TASK_FILTER_CONFIG,
                {"status": status_filter, "priority": priority_filter, "sort_by": sort_by},
            ),
            TaskList(filtered, connections_map),
            id="tasks-content",
        )

    @rt("/tasks/list-fragment")
    async def tasks_list_fragment(request: Request) -> Any:
        """HTMX fragment: filtered task list for filter updates."""
        user_uid = require_authenticated_user(request)

        result = await tasks_service.get_user_tasks(user_uid)
        if result.is_error:
            error = result.expect_error()
            return Div(render_error_banner(error.user_message or error.message), id="task-list")

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
        """Detail page for a single task — shell renders immediately, content loads via HTMX."""
        require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return await render_activity_sidebar_page(
                Div(render_error_banner("Missing task UID")),
                active="tasks",
                request=request,
            )
        content = Div(
            content_loading_placeholder(f"/tasks/detail/content?uid={uid}", "task-detail-content"),
        )
        return await render_activity_sidebar_page(content, active="tasks", request=request)

    @rt("/tasks/detail/content")
    async def task_detail_content_fragment(request: Request) -> Any:
        """HTMX fragment: task detail with connections and relationships."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Div(render_error_banner("Missing task UID"), id="task-detail-content")

        task_result = await tasks_service.get_task(uid)
        if task_result.is_error:
            return Div(render_error_banner("Task not found"), id="task-detail-content")

        task = task_result.value
        if task.user_uid != user_uid:
            return Div(render_error_banner("Task not found"), id="task-detail-content")

        connections_map = await fetch_entity_connections(
            tasks_service.core.backend, TASK_CONNECTION_CONFIG, [task.uid]
        )
        connections = connections_map.get(task.uid, [])

        return TaskDetailView(task, connections)

    routes.extend([tasks_page, tasks_content_fragment, tasks_list_fragment, task_detail_page, task_detail_content_fragment])
    return routes
