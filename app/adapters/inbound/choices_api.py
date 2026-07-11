"""Choices API routes.

Provides HTMX-compatible endpoints for choice status/priority updates and hierarchy queries.

Hierarchy (ownership-verified):
    GET  /api/choices/children     — Direct subchoices of a parent choice
    GET  /api/choices/parent       — Immediate parent of a subchoice
    GET  /api/choices/hierarchy    — Full hierarchy context (ancestors, siblings, children)
    POST /api/choices/remove-child — Remove a subchoice relationship
    POST /api/choices/add-child   — Add a subchoice relationship

Cross-domain links:
    POST /api/choices/link-goal              — Link choice to a goal it affects/advances
    POST /api/choices/link-principle         — Link choice to the principle that informs it
    GET  /api/choices/aligned-with-principle — Choices semantically aligned with a principle

Knowledge intelligence:
    GET  /api/choices/knowledge-patterns — Detected learning patterns across user choices
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
    parse_int_query_param,
    verify_entity_ownership,
)
from core.models.choice.choice import Choice
from core.models.choice.choice_update_intent import ChoiceUpdateIntent
from core.models.entity_requests import (
    AddHierarchyChildRequest,
    LinkChoiceToGoalRequest,
    LinkChoiceToPrincipleRequest,
    RemoveHierarchyChildRequest,
)
from core.utils.result_simplified import Errors, Result
from ui.activities.choices_views import ChoiceCard

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.choices_service import ChoicesService
    from core.services.goals_service import GoalsService
    from core.services.principles_service import PrinciplesService


def create_choices_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    choices_service: ChoicesService,
    goals_service: GoalsService,
    principles_service: PrinciplesService,
    **_kwargs: Any,
) -> list[Any]:
    """Register Choices API routes."""

    async def update_status(uid: str, new_status: str) -> Result[Choice]:
        # Mirror tasks_api: go through the facade contract with a typed intent (ADR-066),
        # not past it into .core with a raw dict. The facade funnels through the core's
        # validated, ChoiceUpdated-firing update path.
        return await choices_service.update_choice(uid, ChoiceUpdateIntent(status=new_status))

    async def update_priority(uid: str, new_priority: str) -> Result[Choice]:
        return await choices_service.update_choice(uid, ChoiceUpdateIntent(priority=new_priority))

    field_routes = create_activity_field_api_routes(
        rt,
        ActivityFieldApiConfig(
            domain_name="choices",
            singular="choice",
            service=choices_service,
            card_fn=ChoiceCard,
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

    @rt("/api/choices/children", methods=["GET"])
    @boundary_handler()
    async def choice_children(request: Request) -> Result[list[Choice]]:
        """Direct subchoices of a parent choice."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(choices_service, uid, user_uid, "choice")
        if ownership_error:
            return ownership_error
        result = await choices_service.get_subchoices(uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok([c for c in result.value if c.user_uid == user_uid])

    @rt("/api/choices/parent", methods=["GET"])
    @boundary_handler()
    async def choice_parent(request: Request) -> Result[Optional[Choice]]:  # noqa: UP045
        """Immediate parent of a subchoice (None if root-level)."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(choices_service, uid, user_uid, "choice")
        if ownership_error:
            return ownership_error
        result = await choices_service.get_parent_choice(uid)
        if result.is_error:
            return Result.fail(result)
        if result.value is not None and result.value.user_uid != user_uid:
            return Result.ok(None)
        return result

    @rt("/api/choices/hierarchy", methods=["GET"])
    @boundary_handler()
    async def choice_hierarchy(request: Request) -> Result[dict[str, Any]]:
        """Full hierarchy context: ancestors, current, siblings, children, depth."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(choices_service, uid, user_uid, "choice")
        if ownership_error:
            return ownership_error
        result = await choices_service.get_choice_hierarchy(uid)
        if result.is_error:
            return Result.fail(result)
        h = result.value
        ancestors = [ch for ch in h["ancestors"] if ch.user_uid == user_uid]
        return Result.ok(
            {
                "ancestors": ancestors,
                "current": h["current"],
                "siblings": [ch for ch in h["siblings"] if ch.user_uid == user_uid],
                "children": [ch for ch in h["children"] if ch.user_uid == user_uid],
                "depth": len(ancestors),
            }
        )

    @rt("/api/choices/remove-child", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def choice_remove_child(request: Request) -> Result[dict[str, Any]]:
        """Remove a subchoice relationship (does not delete the choice nodes)."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, RemoveHierarchyChildRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        ownership_error = await verify_entity_ownership(
            choices_service, req.parent_uid, user_uid, "choice"
        )
        if ownership_error:
            return ownership_error
        child_ownership_error = await verify_entity_ownership(
            choices_service, req.child_uid, user_uid, "choice"
        )
        if child_ownership_error:
            return child_ownership_error
        result = await choices_service.remove_subchoice_relationship(req.parent_uid, req.child_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"removed": result.value})

    @rt("/api/choices/add-child", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def choice_add_child(request: Request) -> Result[dict[str, Any]]:
        """Add a subchoice relationship between two choices."""
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
            choices_service, req.parent_uid, user_uid, "choice"
        )
        if ownership_error:
            return ownership_error
        child_ownership_error = await verify_entity_ownership(
            choices_service, req.child_uid, user_uid, "choice"
        )
        if child_ownership_error:
            return child_ownership_error
        existing_parent = await choices_service.get_parent_choice(req.child_uid)
        if existing_parent.is_error:
            return Result.fail(existing_parent)
        if existing_parent.value is not None:
            return Result.fail(
                Errors.validation(
                    "choice already has a parent — remove it first", field="child_uid"
                )
            )
        result = await choices_service.create_subchoice_relationship(req.parent_uid, req.child_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"added": result.value})

    # ================================================================
    # CROSS-DOMAIN LINKS
    # ================================================================

    @rt("/api/choices/link-goal", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def choice_link_goal(request: Request) -> Result[dict[str, Any]]:
        """Link choice to a goal it affects/advances (AFFECTS_GOAL)."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, LinkChoiceToGoalRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        ownership_error = await verify_entity_ownership(
            choices_service, req.choice_uid, user_uid, "choice"
        )
        if ownership_error:
            return ownership_error
        goal_ownership_error = await verify_entity_ownership(
            goals_service, req.goal_uid, user_uid, "goal"
        )
        if goal_ownership_error:
            return goal_ownership_error
        result = await choices_service.link_choice_to_goal(
            req.choice_uid, req.goal_uid, req.contribution_score
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"linked": result.value})

    @rt("/api/choices/link-principle", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def choice_link_principle(request: Request) -> Result[dict[str, Any]]:
        """Link choice to the principle that informs it (INFORMED_BY_PRINCIPLE)."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, LinkChoiceToPrincipleRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        ownership_error = await verify_entity_ownership(
            choices_service, req.choice_uid, user_uid, "choice"
        )
        if ownership_error:
            return ownership_error
        principle_ownership_error = await verify_entity_ownership(
            principles_service, req.principle_uid, user_uid, "principle"
        )
        if principle_ownership_error:
            return principle_ownership_error
        result = await choices_service.link_choice_to_principle(
            req.choice_uid, req.principle_uid, req.alignment_score
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"linked": result.value})

    @rt("/api/choices/aligned-with-principle", methods=["GET"])
    @boundary_handler()
    async def choices_aligned_with_principle(request: Request) -> Result[list[Choice]]:
        """Choices semantically aligned with a given principle (min_confidence threshold)."""
        user_uid = require_authenticated_user(request)
        principle_uid = request.query_params.get("principle_uid", "").strip()
        if not principle_uid:
            return Result.fail(
                Errors.validation(message="principle_uid is required", field="principle_uid")
            )
        principle_ownership_error = await verify_entity_ownership(
            principles_service, principle_uid, user_uid, "principle"
        )
        if principle_ownership_error:
            return principle_ownership_error
        raw_confidence = request.query_params.get("min_confidence", "0.8")
        try:
            min_confidence = float(raw_confidence)
        except ValueError:
            return Result.fail(
                Errors.validation(message="min_confidence must be a number", field="min_confidence")
            )
        result = await choices_service.find_choices_aligned_with_principle(
            principle_uid, min_confidence
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([c for c in result.value if c.user_uid == user_uid])

    # ================================================================
    # KNOWLEDGE INTELLIGENCE — learning patterns
    # ================================================================

    @rt("/api/choices/knowledge-patterns", methods=["GET"])
    @boundary_handler()
    async def choice_knowledge_patterns(request: Request) -> Result[dict[str, Any]]:
        """Detect knowledge-learning patterns across the authenticated user's choices."""
        user_uid = require_authenticated_user(request)
        timeframe_days = parse_int_query_param(
            request.query_params, "timeframe_days", default=30, minimum=1, maximum=365
        )
        result = await choices_service.analyze_learning_patterns(user_uid, timeframe_days)
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
        choice_children,
        choice_parent,
        choice_hierarchy,
        choice_remove_child,
        choice_add_child,
        choice_link_goal,
        choice_link_principle,
        choices_aligned_with_principle,
        choice_knowledge_patterns,
    ]
