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
from core.utils.logging import get_logger
from ui.activities.tasks_views import (
    TaskDetailView,
    TaskFilterBar,
    TaskList,
    TaskStatsBar,
    filter_tasks,
)
from ui.layouts.base_page import BasePage
from ui.patterns import PageHeader
from ui.patterns.error_banner import render_error_banner

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator, RouteList
    from core.services.tasks_service import TasksService

logger = get_logger("skuel.routes.tasks_ui")


async def _fetch_task_connections(
    tasks_service: TasksService,
    task_uids: list[str],
) -> dict[str, list[dict[str, str]]]:
    """Batch-fetch cross-domain connections for a list of tasks.

    Returns a map of task_uid -> list of connection dicts with keys:
    rel_type, target_uid, title, target_type.
    """
    if not task_uids:
        return {}

    query = """
    MATCH (t:Entity:Task)
    WHERE t.uid IN $task_uids
    OPTIONAL MATCH (t)-[r]->(target:Entity)
    WHERE type(r) IN [
        'FULFILLS_GOAL', 'REINFORCES_HABIT', 'APPLIES_KNOWLEDGE',
        'PART_OF_LEARNING_STEP', 'PART_OF_LEARNING_PATH',
        'INFORMED_BY_PRINCIPLE', 'RELATED_TO'
    ]
    RETURN t.uid AS task_uid,
           type(r) AS rel_type,
           target.uid AS target_uid,
           target.title AS title,
           target.entity_type AS target_type
    """
    try:
        result = await tasks_service.core.backend.execute_query(query, {"task_uids": task_uids})
    except Exception:  # safety-net: Neo4j query failure shouldn't break the page
        logger.warning("Failed to fetch task connections", exc_info=True)
        return {}

    if result.is_error:
        return {}

    connections_map: dict[str, list[dict[str, str]]] = {}
    for record in result.value:
        task_uid = record["task_uid"]
        if record.get("rel_type") is None:
            continue
        if task_uid not in connections_map:
            connections_map[task_uid] = []
        connections_map[task_uid].append(
            {
                "rel_type": record["rel_type"],
                "target_uid": record.get("target_uid", ""),
                "title": record.get("title", ""),
                "target_type": record.get("target_type", ""),
            }
        )
    return connections_map


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

        # Batch-fetch cross-domain connections for visible tasks
        task_uids = [t.uid for t in filtered]
        connections_map = await _fetch_task_connections(tasks_service, task_uids)

        task_count = len(all_tasks)
        subtitle = f"{task_count} task{'s' if task_count != 1 else ''}"

        content = Div(
            PageHeader("Tasks", subtitle=subtitle),
            TaskStatsBar(all_tasks),
            TaskFilterBar(status_filter, priority_filter, sort_by),
            TaskList(filtered, connections_map),
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

        task_uids = [t.uid for t in filtered]
        connections_map = await _fetch_task_connections(tasks_service, task_uids)

        return TaskList(filtered, connections_map)

    @rt("/tasks/detail")
    async def task_detail_page(request: Request) -> Any:
        """Detail page for a single task with connections and relationships."""
        user_uid = require_authenticated_user(request)

        uid = request.query_params.get("uid", "")
        if not uid:
            return await BasePage(
                Div(render_error_banner("Missing task UID"), cls="uk-container uk-container-small"),
                title="Task Not Found",
                request=request,
                active_page="tasks",
            )

        task_result = await tasks_service.get_task(uid)
        if task_result.is_error:
            return await BasePage(
                Div(render_error_banner("Task not found"), cls="uk-container uk-container-small"),
                title="Task Not Found",
                request=request,
                active_page="tasks",
            )

        task = task_result.value
        if task.user_uid != user_uid:
            return await BasePage(
                Div(render_error_banner("Task not found"), cls="uk-container uk-container-small"),
                title="Task Not Found",
                request=request,
                active_page="tasks",
            )

        # Fetch connections for this task
        connections_map = await _fetch_task_connections(tasks_service, [task.uid])
        connections = connections_map.get(task.uid, [])

        content = TaskDetailView(task, connections)

        return await BasePage(
            content,
            title=task.title or "Task",
            request=request,
            active_page="tasks",
        )

    routes.extend([tasks_page, tasks_list_fragment, task_detail_page])
    return routes
