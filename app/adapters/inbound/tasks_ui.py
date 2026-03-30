"""Tasks UI routes.

Provides the read-focused task list view at /tasks.
Tasks enter via YAML upload; this UI shows them with status controls,
priority, and knowledge connections.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fasthtml.common import Div

from adapters.inbound.auth import require_authenticated_user
from core.utils.logging import get_logger
from ui.activities.tasks_views import (
    TaskFilterBar,
    TaskList,
    TaskStatsBar,
    filter_tasks,
)
from ui.layouts.base_page import BasePage
from ui.patterns import PageHeader
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from starlette.requests import Request

    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
    from core.services.tasks_service import TasksService

logger = get_logger("skuel.routes.tasks_ui")


def create_tasks_ui_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    tasks_service: TasksService,
) -> RouteList:
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
                cls="uk-container uk-container-small",
            )
            return await BasePage(
                content,
                title="Tasks",
                request=request,
                active_page="tasks",
            )

        all_tasks = result.value

        # Parse filter params from query string
        status_filter = request.query_params.get("status", "active")
        priority_filter = request.query_params.get("priority", "all")
        sort_by = request.query_params.get("sort_by", "priority")

        filtered = filter_tasks(all_tasks, status_filter, priority_filter, sort_by)

        task_count = len(all_tasks)
        subtitle = f"{task_count} task{'s' if task_count != 1 else ''}"

        content = Div(
            PageHeader("Tasks", subtitle=subtitle),
            TaskStatsBar(all_tasks),
            TaskFilterBar(status_filter, priority_filter, sort_by),
            TaskList(filtered),
            cls="uk-container uk-container-small",
        )

        return await BasePage(
            content,
            title="Tasks",
            request=request,
            active_page="tasks",
        )

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
        return TaskList(filtered)

    routes.extend([tasks_page, tasks_list_fragment])
    return routes
