"""Goals API routes.

Provides HTMX-compatible endpoints for goal status updates and hierarchy queries.

The transition dispatch (activate / complete / archive / cancel with their
per-state side effects) lives in ``GoalsService.set_status``; this route is
a transport shim.

Hierarchy (ownership-verified):
    GET  /api/goals/children     — Direct subgoals of a parent goal
    GET  /api/goals/parent       — Immediate parent of a subgoal
    GET  /api/goals/hierarchy    — Full hierarchy context (ancestors, siblings, children)
    POST /api/goals/remove-child — Remove a subgoal relationship
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
from core.utils.result_simplified import Errors, Result
from ui.activities.goals_views import GoalCard

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.models.goal.goal import Goal
    from core.services.goals_service import GoalsService


def create_goals_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    goals_service: GoalsService,
    **_kwargs: Any,
) -> list[Any]:
    """Register Goals API routes."""

    status_routes = create_activity_status_api_routes(
        rt,
        ActivityStatusApiConfig(
            domain_name="goals",
            singular="goal",
            service=goals_service,
            update_status=goals_service.set_status,
            card_fn=GoalCard,
        ),
    )

    # ================================================================
    # HIERARCHY — read-paths and relationship removal
    # ================================================================

    @rt("/api/goals/children", methods=["GET"])
    @boundary_handler()
    async def goal_children(request: Request) -> Result[list[Goal]]:
        """Direct subgoals of a parent goal."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(goals_service, uid, user_uid, "goal")
        if ownership_error:
            return ownership_error
        return await goals_service.get_subgoals(uid)

    @rt("/api/goals/parent", methods=["GET"])
    @boundary_handler()
    async def goal_parent(request: Request) -> Result[Goal | None]:
        """Immediate parent of a subgoal (None if root-level)."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(goals_service, uid, user_uid, "goal")
        if ownership_error:
            return ownership_error
        return await goals_service.get_parent_goal(uid)

    @rt("/api/goals/hierarchy", methods=["GET"])
    @boundary_handler()
    async def goal_hierarchy(request: Request) -> Result[dict[str, Any]]:
        """Full hierarchy context: ancestors, current, siblings, children, depth."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(goals_service, uid, user_uid, "goal")
        if ownership_error:
            return ownership_error
        return await goals_service.get_goal_hierarchy(uid)

    @rt("/api/goals/remove-child", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def goal_remove_child(request: Request) -> Result[dict[str, Any]]:
        """Remove a subgoal relationship (does not delete the goal nodes)."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, RemoveHierarchyChildRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        ownership_error = await verify_entity_ownership(
            goals_service, req.parent_uid, user_uid, "goal"
        )
        if ownership_error:
            return ownership_error
        result = await goals_service.remove_subgoal_relationship(req.parent_uid, req.child_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"removed": result.value})

    return [
        *status_routes,
        goal_children,
        goal_parent,
        goal_hierarchy,
        goal_remove_child,
    ]
