"""Tasks API routes.

Provides HTMX-compatible endpoints for task status/priority updates, hierarchy queries,
cross-domain links, and knowledge intelligence.

Hierarchy (ownership-verified, via create_activity_hierarchy_api_routes):
    GET  /api/tasks/children       — Direct subtasks of a parent task (JSON)
    GET  /api/tasks/{uid}/children — Subtasks as a TreeNodeList fragment (HTMX)
    GET  /api/tasks/parent         — Immediate parent of a subtask
    GET  /api/tasks/hierarchy      — Full hierarchy context (ancestors, siblings, children)
    POST /api/tasks/remove-child   — Remove a subtask relationship
    POST /api/tasks/add-child      — Add a subtask relationship

Cross-domain links (via create_activity_link_api_routes):
    POST /api/tasks/link-goal    — Link task to a goal it contributes to

Knowledge intelligence:
    GET  /api/tasks/knowledge-patterns   — Detected learning patterns across user tasks
    GET  /api/tasks/knowledge-priorities — Knowledge-aware priority scores for user tasks
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.route_factories import (
    PRIORITY_VALUES,
    ActivityFieldApiConfig,
    ActivityHierarchyApiConfig,
    CrossDomainLinkSpec,
    FieldUpdateSpec,
    LinkTargetSpec,
    create_activity_field_api_routes,
    create_activity_hierarchy_api_routes,
    create_activity_link_api_routes,
    create_knowledge_patterns_api_route,
    parse_csv_query_param,
    verify_entity_ownership,
)
from core.models.entity_requests import AddHierarchyChildRequest, LinkTaskToGoalRequest
from core.models.task.task import Task
from core.models.task.task_update_intent import TaskUpdateIntent
from core.utils.result_simplified import Result
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

    async def add_subtask_relationship(req: AddHierarchyChildRequest) -> Result[bool]:
        return await tasks_service.create_subtask_relationship(
            req.parent_uid, req.child_uid, req.progress_weight
        )

    hierarchy_routes = create_activity_hierarchy_api_routes(
        rt,
        ActivityHierarchyApiConfig(
            domain_name="tasks",
            singular="task",
            service=tasks_service,
            get_children=tasks_service.get_subtasks,
            get_parent=tasks_service.get_parent_task,
            get_hierarchy=tasks_service.get_task_hierarchy,
            add_child_relationship=add_subtask_relationship,
            remove_child_relationship=tasks_service.remove_subtask_relationship,
        ),
    )

    async def apply_link_goal(req: LinkTaskToGoalRequest) -> Result[bool]:
        return await tasks_service.link_task_to_goal(
            req.task_uid, req.goal_uid, req.contribution_percentage, req.milestone_uid
        )

    link_routes = create_activity_link_api_routes(
        rt,
        domain_name="tasks",
        singular="task",
        service=tasks_service,
        specs=(
            CrossDomainLinkSpec(
                action="link-goal",
                request_model=LinkTaskToGoalRequest,
                owner_uid_field="task_uid",
                apply=apply_link_goal,
                doc="Link task to a goal it contributes to (CONTRIBUTES_TO_GOAL).",
                target=LinkTargetSpec(service=goals_service, uid_field="goal_uid", singular="goal"),
            ),
        ),
    )

    knowledge_patterns_route = create_knowledge_patterns_api_route(
        rt, "tasks", tasks_service.analyze_learning_patterns
    )

    # ================================================================
    # KNOWLEDGE INTELLIGENCE — priority scoring (Tasks-only)
    # ================================================================

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
        *hierarchy_routes,
        *link_routes,
        knowledge_patterns_route,
        task_knowledge_priorities,
    ]
