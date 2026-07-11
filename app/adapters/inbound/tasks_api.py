"""Tasks API routes.

Provides HTMX-compatible endpoints for task status/priority updates, hierarchy queries,
cross-domain links, and knowledge intelligence.

Hierarchy (ownership-verified):
    GET  /api/tasks/children     — Direct subtasks of a parent task
    GET  /api/tasks/parent       — Immediate parent of a subtask
    GET  /api/tasks/hierarchy    — Full hierarchy context (ancestors, siblings, children)
    POST /api/tasks/remove-child — Remove a subtask relationship
    POST /api/tasks/add-child   — Add a subtask relationship

Cross-domain links:
    POST /api/tasks/link-goal    — Link task to a goal it contributes to

Knowledge intelligence:
    GET  /api/tasks/knowledge-patterns   — Detected learning patterns across user tasks
    GET  /api/tasks/knowledge-priorities — Knowledge-aware priority scores for user tasks
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import parse_json_body
from adapters.inbound.route_factories import (
    PRIORITY_VALUES,
    ActivityFieldApiConfig,
    FieldUpdateSpec,
    create_activity_field_api_routes,
    parse_csv_query_param,
    parse_int_query_param,
    verify_entity_ownership,
)
from core.models.entity_requests import (
    AddHierarchyChildRequest,
    LinkTaskToGoalRequest,
    RemoveHierarchyChildRequest,
)
from core.models.task.task import Task
from core.models.task.task_update_intent import TaskUpdateIntent
from core.utils.result_simplified import Errors, Result
from ui.activities.tasks_views import TaskCard

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.goals_service import GoalsService
    from core.services.tasks_service import TasksService


def create_tasks_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    tasks_service: TasksService,
    goals_service: GoalsService,
    **_kwargs: Any,
) -> list[Any]:
    """Register Tasks API routes."""

    async def update_status(uid: str, new_status: str) -> Result[Task]:
        return await tasks_service.update_task(uid, TaskUpdateIntent(status=new_status))

    async def update_priority(uid: str, new_priority: str) -> Result[Task]:
        return await tasks_service.update_task(uid, TaskUpdateIntent(priority=new_priority))

    field_routes = create_activity_field_api_routes(
        rt,
        ActivityFieldApiConfig(
            domain_name="tasks",
            singular="task",
            service=tasks_service,
            card_fn=TaskCard,
            fields=(
                FieldUpdateSpec(field="status", apply=update_status),
                FieldUpdateSpec(
                    field="priority", apply=update_priority, allowed_values=PRIORITY_VALUES
                ),
            ),
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
    async def task_parent(request: Request) -> Result[Optional[Task]]:  # noqa: UP045
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

    @rt("/api/tasks/add-child", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def task_add_child(request: Request) -> Result[dict[str, Any]]:
        """Add a subtask relationship between two tasks."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, AddHierarchyChildRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        if req.parent_uid == req.child_uid:
            return Result.fail(
                Errors.validation("parent_uid and child_uid must differ", field="child_uid")
            )
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
        existing_parent = await tasks_service.get_parent_task(req.child_uid)
        if existing_parent.is_error:
            return Result.fail(existing_parent)
        if existing_parent.value is not None:
            return Result.fail(
                Errors.validation("task already has a parent — remove it first", field="child_uid")
            )
        result = await tasks_service.create_subtask_relationship(
            req.parent_uid, req.child_uid, req.progress_weight
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"added": result.value})

    # ================================================================
    # CROSS-DOMAIN LINKS
    # ================================================================

    @rt("/api/tasks/link-goal", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def task_link_goal(request: Request) -> Result[dict[str, Any]]:
        """Link task to a goal it contributes to (CONTRIBUTES_TO_GOAL)."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, LinkTaskToGoalRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        ownership_error = await verify_entity_ownership(
            tasks_service, req.task_uid, user_uid, "task"
        )
        if ownership_error:
            return ownership_error
        goal_ownership_error = await verify_entity_ownership(
            goals_service, req.goal_uid, user_uid, "goal"
        )
        if goal_ownership_error:
            return goal_ownership_error
        result = await tasks_service.link_task_to_goal(
            req.task_uid, req.goal_uid, req.contribution_percentage, req.milestone_uid
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"linked": result.value})

    # ================================================================
    # KNOWLEDGE INTELLIGENCE — learning patterns and priority scoring
    # ================================================================

    @rt("/api/tasks/knowledge-patterns", methods=["GET"])
    @boundary_handler()
    async def task_knowledge_patterns(request: Request) -> Result[dict[str, Any]]:
        """Detect knowledge-learning patterns across the authenticated user's tasks."""
        user_uid = require_authenticated_user(request)
        timeframe_days = parse_int_query_param(
            request.query_params, "timeframe_days", default=30, minimum=1, maximum=365
        )
        result = await tasks_service.analyze_learning_patterns(user_uid, timeframe_days)
        if result.is_error:
            return Result.fail(result)
        patterns = [
            {
                "pattern_type": p.pattern_type.value,
                "knowledge_uids": p.knowledge_uids,
                "entity_uids": p.entity_uids,
                "confidence": p.confidence,
                "timeframe_days": p.timeframe_days,
                "frequency": p.frequency,
                "growth_indicator": p.growth_indicator,
                "metadata": p.metadata,
            }
            for p in result.value
        ]
        return Result.ok(
            {"patterns": patterns, "count": len(patterns), "timeframe_days": timeframe_days}
        )

    @rt("/api/tasks/knowledge-priorities", methods=["GET"])
    @boundary_handler()
    async def task_knowledge_priorities(request: Request) -> Result[dict[str, Any]]:
        """Calculate knowledge-aware priority scores for the authenticated user's tasks."""
        user_uid = require_authenticated_user(request)
        task_uids = parse_csv_query_param(request.query_params, "task_uids") or None
        if task_uids:
            for uid in task_uids:
                ownership_error = await verify_entity_ownership(
                    tasks_service, uid, user_uid, "task"
                )
                if ownership_error:
                    return ownership_error
        result = await tasks_service.calculate_knowledge_aware_priorities(user_uid, task_uids)
        if result.is_error:
            return Result.fail(result)
        priorities = [
            {
                "task_uid": p.task_uid,
                "base_priority_score": p.base_priority_score,
                "knowledge_enhancement_score": p.knowledge_enhancement_score,
                "learning_opportunity_score": p.learning_opportunity_score,
                "mastery_progression_score": p.mastery_progression_score,
                "cross_domain_impact_score": p.cross_domain_impact_score,
                "final_priority_score": p.final_priority_score,
                "scoring_rationale": p.scoring_rationale,
            }
            for p in result.value
        ]
        return Result.ok({"priorities": priorities, "count": len(priorities)})

    return [
        *field_routes,
        task_children,
        task_parent,
        task_hierarchy,
        task_remove_child,
        task_add_child,
        task_link_goal,
        task_knowledge_patterns,
        task_knowledge_priorities,
    ]
