"""Goals API routes.

Provides HTMX-compatible endpoints for goal status/priority updates and hierarchy queries.

The transition dispatch (activate / complete / archive / cancel with their
per-state side effects) lives in ``GoalsService.set_status``; this route is
a transport shim.

Hierarchy (ownership-verified):
    GET  /api/goals/children     — Direct subgoals of a parent goal
    GET  /api/goals/parent       — Immediate parent of a subgoal
    GET  /api/goals/hierarchy    — Full hierarchy context (ancestors, siblings, children)
    POST /api/goals/remove-child — Remove a subgoal relationship
    POST /api/goals/add-child   — Add a subgoal relationship

Planning (user-scoped reads, full UserContext required):
    GET  /api/goals/stalled      — Goals with minimal progress needing attention
    GET  /api/goals/achievable   — Goals near completion, prioritised for finishing

Scheduling-aware creation:
    POST /api/goals/create-with-scheduling          — Create goal with capacity check
    POST /api/goals/create-with-learning-scheduling — Create goal aligned to learning path

Cross-domain links:
    POST /api/goals/link-knowledge — Link goal to required knowledge/skill
    POST /api/goals/link-principle — Link goal to a guiding principle

Knowledge intelligence:
    GET  /api/goals/knowledge-patterns — Detected learning patterns across user goals
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
    parse_bool_query_param,
    parse_float_query_param,
    parse_int_query_param,
    verify_entity_ownership,
)
from core.models.context_types import ContextualGoal
from core.models.entity_requests import (
    AddHierarchyChildRequest,
    LinkGoalToKnowledgeRequest,
    LinkGoalToPrincipleRequest,
    RemoveHierarchyChildRequest,
)
from core.models.goal.goal import Goal
from core.models.goal.goal_request import GoalCreateRequest
from core.models.goal.goal_update_intent import GoalUpdateIntent
from core.utils.result_simplified import Errors, Result
from ui.activities.goals_views import GoalCard

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.goals_service import GoalsService
    from core.services.principles_service import PrinciplesService
    from core.services.user_service import UserService


def create_goals_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    goals_service: GoalsService,
    principles_service: PrinciplesService,
    user_service: UserService | None = None,
    **_kwargs: Any,
) -> list[Any]:
    """Register Goals API routes."""

    async def update_priority(uid: str, new_priority: str) -> Result[Goal]:
        return await goals_service.update_goal(uid, GoalUpdateIntent(priority=new_priority))

    field_routes = create_activity_field_api_routes(
        rt,
        ActivityFieldApiConfig(
            domain_name="goals",
            singular="goal",
            service=goals_service,
            card_fn=GoalCard,
            fields=(
                FieldUpdateSpec(field="status", apply=goals_service.set_status),
                FieldUpdateSpec(
                    field="priority", apply=update_priority, allowed_values=PRIORITY_VALUES
                ),
            ),
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
        result = await goals_service.get_subgoals(uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok([g for g in result.value if g.user_uid == user_uid])

    @rt("/api/goals/parent", methods=["GET"])
    @boundary_handler()
    async def goal_parent(request: Request) -> Result[Optional[Goal]]:  # noqa: UP045
        """Immediate parent of a subgoal (None if root-level)."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(goals_service, uid, user_uid, "goal")
        if ownership_error:
            return ownership_error
        result = await goals_service.get_parent_goal(uid)
        if result.is_error:
            return Result.fail(result)
        if result.value is not None and result.value.user_uid != user_uid:
            return Result.ok(None)
        return result

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
        result = await goals_service.get_goal_hierarchy(uid)
        if result.is_error:
            return Result.fail(result)
        h = result.value
        ancestors = [g for g in h["ancestors"] if g.user_uid == user_uid]
        return Result.ok(
            {
                "ancestors": ancestors,
                "current": h["current"],
                "siblings": [g for g in h["siblings"] if g.user_uid == user_uid],
                "children": [g for g in h["children"] if g.user_uid == user_uid],
                "depth": len(ancestors),
            }
        )

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
        child_ownership_error = await verify_entity_ownership(
            goals_service, req.child_uid, user_uid, "goal"
        )
        if child_ownership_error:
            return child_ownership_error
        result = await goals_service.remove_subgoal_relationship(req.parent_uid, req.child_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"removed": result.value})

    @rt("/api/goals/add-child", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def goal_add_child(request: Request) -> Result[dict[str, Any]]:
        """Add a subgoal relationship between two goals."""
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
            goals_service, req.parent_uid, user_uid, "goal"
        )
        if ownership_error:
            return ownership_error
        child_ownership_error = await verify_entity_ownership(
            goals_service, req.child_uid, user_uid, "goal"
        )
        if child_ownership_error:
            return child_ownership_error
        existing_parent = await goals_service.get_parent_goal(req.child_uid)
        if existing_parent.is_error:
            return Result.fail(existing_parent)
        if existing_parent.value is not None:
            return Result.fail(
                Errors.validation("goal already has a parent — remove it first", field="child_uid")
            )
        result = await goals_service.create_subgoal_relationship(
            req.parent_uid, req.child_uid, req.progress_weight
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"added": result.value})

    # ================================================================
    # PLANNING — stalled and achievable goal reads
    # ================================================================

    @rt("/api/goals/stalled", methods=["GET"])
    @boundary_handler()
    async def goals_stalled(request: Request) -> Result[list[ContextualGoal]]:
        """Goals with minimal progress that need attention.

        Query params:
            max_progress: Upper progress threshold (default 0.1 = 10%)
            limit: Max results (default 10)
        """
        user_uid = require_authenticated_user(request)
        if not user_service:
            return Result.fail(
                Errors.system(message="user_service not available", operation="goals_stalled")
            )
        max_progress = parse_float_query_param(request.query_params, "max_progress", 0.1)
        limit = parse_int_query_param(request.query_params, "limit", 10)
        ctx_result = await user_service.get_user_context(user_uid)
        if ctx_result.is_error:
            return Result.fail(ctx_result)
        return await goals_service.get_stalled_goals_for_user(ctx_result.value, max_progress, limit)

    @rt("/api/goals/achievable", methods=["GET"])
    @boundary_handler()
    async def goals_achievable(request: Request) -> Result[list[ContextualGoal]]:
        """Goals near completion, prioritised for finishing.

        Query params:
            min_progress: Lower progress threshold (default 0.7 = 70%)
            limit: Max results (default 5)
        """
        user_uid = require_authenticated_user(request)
        if not user_service:
            return Result.fail(
                Errors.system(message="user_service not available", operation="goals_achievable")
            )
        min_progress = parse_float_query_param(request.query_params, "min_progress", 0.7)
        limit = parse_int_query_param(request.query_params, "limit", 5)
        ctx_result = await user_service.get_user_context(user_uid)
        if ctx_result.is_error:
            return Result.fail(ctx_result)
        return await goals_service.get_achievable_goals_for_user(
            ctx_result.value, min_progress, limit
        )

    @rt("/api/goals/advancing", methods=["GET"])
    @boundary_handler()
    async def goals_advancing(request: Request) -> Result[list[ContextualGoal]]:
        """Goals with active momentum, for the daily plan P6 slot.

        Query params:
            limit: Max results (default 2)
        """
        user_uid = require_authenticated_user(request)
        if not user_service:
            return Result.fail(
                Errors.system(message="user_service not available", operation="goals_advancing")
            )
        limit = parse_int_query_param(request.query_params, "limit", 2)
        ctx_result = await user_service.get_rich_unified_context(user_uid)
        if ctx_result.is_error:
            return Result.fail(ctx_result)
        return await goals_service.get_advancing_goals_for_user(ctx_result.value, limit)

    # ================================================================
    # SCHEDULING-AWARE CREATION
    # ================================================================

    @rt("/api/goals/create-with-scheduling", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def goal_create_with_scheduling(request: Request) -> Result[Goal]:
        """Create a goal with capacity check and timeline validation.

        Body: GoalCreateRequest JSON
        Query params:
            check_capacity: Whether to enforce capacity limits (default true)
        """
        user_uid = require_authenticated_user(request)
        if not user_service:
            return Result.fail(
                Errors.system(
                    message="user_service not available", operation="goal_create_with_scheduling"
                )
            )
        check_capacity = parse_bool_query_param(
            request.query_params, "check_capacity", default=True
        )
        parsed = await parse_json_body(request, GoalCreateRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        ctx_result = await user_service.get_user_context(user_uid)
        if ctx_result.is_error:
            return Result.fail(ctx_result)
        return await goals_service.create_goal_with_scheduling_context(
            parsed.value, ctx_result.value, check_capacity
        )

    @rt("/api/goals/create-with-learning-scheduling", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def goal_create_with_learning_scheduling(request: Request) -> Result[Goal]:
        """Create a goal aligned with the user's active learning paths.

        Body: GoalCreateRequest JSON
        """
        user_uid = require_authenticated_user(request)
        if not user_service:
            return Result.fail(
                Errors.system(
                    message="user_service not available",
                    operation="goal_create_with_learning_scheduling",
                )
            )
        parsed = await parse_json_body(request, GoalCreateRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        ctx_result = await user_service.get_user_context(user_uid)
        if ctx_result.is_error:
            return Result.fail(ctx_result)
        return await goals_service.create_goal_with_learning_scheduling(
            parsed.value, None, ctx_result.value
        )

    # ================================================================
    # CROSS-DOMAIN LINKS
    # ================================================================

    @rt("/api/goals/link-knowledge", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def goal_link_knowledge(request: Request) -> Result[dict[str, Any]]:
        """Link goal to required knowledge/skill (REQUIRES_KNOWLEDGE). Ku is shared content."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, LinkGoalToKnowledgeRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        ownership_error = await verify_entity_ownership(
            goals_service, req.goal_uid, user_uid, "goal"
        )
        if ownership_error:
            return ownership_error
        result = await goals_service.link_goal_to_knowledge(
            req.goal_uid, req.knowledge_uid, req.proficiency_required, req.priority
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"linked": result.value})

    @rt("/api/goals/link-principle", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def goal_link_principle(request: Request) -> Result[dict[str, Any]]:
        """Link goal to a guiding principle/value (GUIDED_BY_PRINCIPLE)."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, LinkGoalToPrincipleRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        ownership_error = await verify_entity_ownership(
            goals_service, req.goal_uid, user_uid, "goal"
        )
        if ownership_error:
            return ownership_error
        principle_ownership_error = await verify_entity_ownership(
            principles_service, req.principle_uid, user_uid, "principle"
        )
        if principle_ownership_error:
            return principle_ownership_error
        result = await goals_service.link_goal_to_principle(
            req.goal_uid, req.principle_uid, req.alignment_strength
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"linked": result.value})

    # ================================================================
    # KNOWLEDGE INTELLIGENCE — learning patterns
    # ================================================================

    @rt("/api/goals/knowledge-patterns", methods=["GET"])
    @boundary_handler()
    async def goal_knowledge_patterns(request: Request) -> Result[dict[str, Any]]:
        """Detect knowledge-learning patterns across the authenticated user's goals."""
        user_uid = require_authenticated_user(request)
        timeframe_days = parse_int_query_param(
            request.query_params, "timeframe_days", default=30, minimum=1, maximum=365
        )
        result = await goals_service.analyze_learning_patterns(user_uid, timeframe_days)
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

    return [
        *field_routes,
        goal_children,
        goal_parent,
        goal_hierarchy,
        goal_remove_child,
        goal_add_child,
        goals_stalled,
        goals_achievable,
        goal_create_with_scheduling,
        goal_create_with_learning_scheduling,
        goal_link_knowledge,
        goal_link_principle,
        goal_knowledge_patterns,
    ]
