"""Tasks API routes.

Provides HTMX-compatible endpoints for task status updates and hierarchy queries.

Hierarchy (ownership-verified):
    GET  /api/tasks/children     — Direct subtasks of a parent task
    GET  /api/tasks/parent       — Immediate parent of a subtask
    GET  /api/tasks/hierarchy    — Full hierarchy context (ancestors, siblings, children)
    POST /api/tasks/remove-child — Remove a subtask relationship
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import parse_json_body
from adapters.inbound.route_factories import (
    ActivityStatusApiConfig,
    create_activity_status_api_routes,
    verify_entity_ownership,
)
from core.models.entity_requests import RemoveHierarchyChildRequest
from core.models.task.task_update_intent import TaskUpdateIntent
from core.utils.result_simplified import Errors, Result
from ui.activities.tasks_views import TaskCard

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.models.task.task import Task
    from core.services.tasks_service import TasksService


def create_tasks_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    tasks_service: TasksService,
    **_kwargs: Any,
) -> list[Any]:
    """Register Tasks API routes."""

    async def update(uid: str, new_status: str) -> Result[Task]:
        return await tasks_service.update_task(uid, TaskUpdateIntent(status=new_status))

    status_routes = create_activity_status_api_routes(
        rt,
        ActivityStatusApiConfig(
            domain_name="tasks",
            singular="task",
            service=tasks_service,
            update_status=update,
            card_fn=TaskCard,
        ),
    )

    # ================================================================
    # HIERARCHY — read-paths and relationship removal
    # ================================================================

    @rt("/api/tasks/children", methods=["GET"])
    @boundary_handler()
    async def task_children(request: Request) -> Result[list[Task]]:
        """Direct subtasks of a parent task."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(tasks_service, uid, user_uid, "task")
        if ownership_error:
            return ownership_error
        result = await tasks_service.get_subtasks(uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok([t for t in result.value if t.user_uid == user_uid])

    @rt("/api/tasks/parent", methods=["GET"])
    @boundary_handler()
    async def task_parent(request: Request) -> Result[Task | None]:
        """Immediate parent of a subtask (None if root-level)."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(tasks_service, uid, user_uid, "task")
        if ownership_error:
            return ownership_error
        result = await tasks_service.get_parent_task(uid)
        if result.is_error:
            return Result.fail(result)
        if result.value is not None and result.value.user_uid != user_uid:
            return Result.ok(None)
        return result

    @rt("/api/tasks/hierarchy", methods=["GET"])
    @boundary_handler()
    async def task_hierarchy(request: Request) -> Result[dict[str, Any]]:
        """Full hierarchy context: ancestors, current, siblings, children, depth."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(tasks_service, uid, user_uid, "task")
        if ownership_error:
            return ownership_error
        result = await tasks_service.get_task_hierarchy(uid)
        if result.is_error:
            return Result.fail(result)
        h = result.value
        ancestors = [t for t in h["ancestors"] if t.user_uid == user_uid]
        return Result.ok(
            {
                "ancestors": ancestors,
                "current": h["current"],
                "siblings": [t for t in h["siblings"] if t.user_uid == user_uid],
                "children": [t for t in h["children"] if t.user_uid == user_uid],
                "depth": len(ancestors),
            }
        )

    @rt("/api/tasks/remove-child", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def task_remove_child(request: Request) -> Result[dict[str, Any]]:
        """Remove a subtask relationship (does not delete the task nodes)."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, RemoveHierarchyChildRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        ownership_error = await verify_entity_ownership(
            tasks_service, req.parent_uid, user_uid, "task"
        )
        if ownership_error:
            return ownership_error
        child_ownership_error = await verify_entity_ownership(
            tasks_service, req.child_uid, user_uid, "task"
        )
        if child_ownership_error:
            return child_ownership_error
        result = await tasks_service.remove_subtask_relationship(req.parent_uid, req.child_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"removed": result.value})

    return [
        *status_routes,
        task_children,
        task_parent,
        task_hierarchy,
        task_remove_child,
    ]
