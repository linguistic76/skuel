"""Goals API routes.

Provides HTMX-compatible endpoints for goal status/priority updates and hierarchy queries.

The transition dispatch (activate / complete / archive / cancel with their
per-state side effects) lives in ``GoalsService.set_status``; this route is
a transport shim.

Hierarchy (ownership-verified, via create_activity_hierarchy_api_routes):
    GET  /api/goals/children       — Direct subgoals of a parent goal (JSON)
    GET  /api/goals/{uid}/children — Subgoals as a TreeNodeList fragment (HTMX)
    GET  /api/goals/parent         — Immediate parent of a subgoal
    GET  /api/goals/hierarchy      — Full hierarchy context (ancestors, siblings, children)
    POST /api/goals/remove-child   — Remove a subgoal relationship
    POST /api/goals/add-child      — Add a subgoal relationship

Planning (user-scoped reads, full UserContext required):
    GET  /api/goals/stalled      — Goals with minimal progress needing attention
    GET  /api/goals/achievable   — Goals near completion, prioritised for finishing

Scheduling-aware creation:
    POST /api/goals/create-with-scheduling          — Create goal with capacity check
    POST /api/goals/create-with-learning-scheduling — Create goal aligned to learning path

Cross-domain links (via create_activity_link_api_routes):
    POST /api/goals/link-knowledge — Link goal to required knowledge/skill
    POST /api/goals/link-principle — Link goal to a guiding principle

Knowledge intelligence:
    GET  /api/goals/knowledge-patterns — Detected learning patterns across user goals
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.inbound.auth import require_authenticated_user
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import parse_json_body
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
    parse_bool_query_param,
    parse_float_query_param,
    parse_int_query_param,
)
from core.models.context_types import ContextualGoal
from core.models.entity_requests import (
    AddHierarchyChildRequest,
    LinkGoalToKnowledgeRequest,
    LinkGoalToPrincipleRequest,
)
from core.models.goal.goal import Goal
from core.models.goal.goal_request import GoalCreateRequest
from core.models.goal.goal_update_intent import GoalUpdateIntent
from core.utils.result_simplified import Result
from ui.activities.goals_views import GoalCard

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.models.type_hints import UserUID
    from core.services.goals_service import GoalsService
    from core.services.principles_service import PrinciplesService
    from core.services.user.unified_user_context import UserContext
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

    # Fail-fast: UserService is always wired at compose (api_related_services
    # maps it from services.user) — a missing one is a wiring defect, not a
    # runtime condition to guard per handler.
    assert user_service is not None, "UserService must be wired before goals API routes"

    async def fetch_context(user_uid: UserUID) -> Result[UserContext]:
        """The standard UserContext read shared by planning + scheduling handlers."""
        return await user_service.get_user_context(user_uid)

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
    # HIERARCHY — shared Activity Domain hierarchy route block
    # ================================================================

    async def add_subgoal_relationship(req: AddHierarchyChildRequest) -> Result[bool]:
        return await goals_service.create_subgoal_relationship(
            req.parent_uid, req.child_uid, req.progress_weight
        )

    hierarchy_routes = create_activity_hierarchy_api_routes(
        rt,
        ActivityHierarchyApiConfig(
            domain_name="goals",
            singular="goal",
            service=goals_service,
            get_children=goals_service.get_subgoals,
            get_parent=goals_service.get_parent_goal,
            get_hierarchy=goals_service.get_goal_hierarchy,
            add_child_relationship=add_subgoal_relationship,
            remove_child_relationship=goals_service.remove_subgoal_relationship,
        ),
    )

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
        max_progress = parse_float_query_param(request.query_params, "max_progress", 0.1)
        limit = parse_int_query_param(request.query_params, "limit", 10)
        ctx_result = await fetch_context(user_uid)
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
        min_progress = parse_float_query_param(request.query_params, "min_progress", 0.7)
        limit = parse_int_query_param(request.query_params, "limit", 5)
        ctx_result = await fetch_context(user_uid)
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
        check_capacity = parse_bool_query_param(
            request.query_params, "check_capacity", default=True
        )
        parsed = await parse_json_body(request, GoalCreateRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        ctx_result = await fetch_context(user_uid)
        if ctx_result.is_error:
            return Result.fail(ctx_result)
        return await goals_service.create_goal_with_scheduling_context(
            parsed.value, ctx_result.value, check_capacity
        )

    # ================================================================
    # CROSS-DOMAIN LINKS + KNOWLEDGE INTELLIGENCE
    # ================================================================

    async def apply_link_knowledge(req: LinkGoalToKnowledgeRequest) -> Result[bool]:
        return await goals_service.link_goal_to_knowledge(
            req.goal_uid, req.knowledge_uid, req.proficiency_required, req.priority
        )

    async def apply_link_principle(req: LinkGoalToPrincipleRequest) -> Result[bool]:
        return await goals_service.link_goal_to_principle(
            req.goal_uid, req.principle_uid, req.alignment_strength
        )

    link_routes = create_activity_link_api_routes(
        rt,
        domain_name="goals",
        singular="goal",
        service=goals_service,
        specs=(
            CrossDomainLinkSpec(
                action="link-knowledge",
                request_model=LinkGoalToKnowledgeRequest,
                owner_uid_field="goal_uid",
                apply=apply_link_knowledge,
                doc="Link goal to required knowledge/skill (REQUIRES_KNOWLEDGE). "
                "Ku is shared content.",
            ),
            CrossDomainLinkSpec(
                action="link-principle",
                request_model=LinkGoalToPrincipleRequest,
                owner_uid_field="goal_uid",
                apply=apply_link_principle,
                doc="Link goal to a guiding principle/value (GUIDED_BY_PRINCIPLE).",
                target=LinkTargetSpec(
                    service=principles_service, uid_field="principle_uid", singular="principle"
                ),
            ),
        ),
    )

    knowledge_patterns_route = create_knowledge_patterns_api_route(
        rt, "goals", goals_service.analyze_learning_patterns
    )

    return [
        *field_routes,
        *hierarchy_routes,
        goals_stalled,
        goals_achievable,
        goals_advancing,
        goal_create_with_scheduling,
        *link_routes,
        knowledge_patterns_route,
    ]
