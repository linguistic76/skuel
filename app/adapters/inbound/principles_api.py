"""Principles API routes.

Provides HTMX-compatible endpoints for principle status/priority updates and hierarchy queries.

Hierarchy (ownership-verified):
    GET  /api/principles/children     — Direct subprinciples of a parent principle
    GET  /api/principles/parent       — Immediate parent of a subprinciple
    GET  /api/principles/hierarchy    — Full hierarchy context (ancestors, siblings, children)
    POST /api/principles/remove-child — Remove a subprinciple relationship
    POST /api/principles/add-child   — Add a subprinciple relationship

Cross-domain links:
    POST /api/principles/link-knowledge — Link principle to knowledge it is grounded in

Knowledge intelligence:
    GET  /api/principles/knowledge-patterns — Detected learning patterns across user principles
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
from core.models.entity_requests import (
    AddHierarchyChildRequest,
    LinkPrincipleToKnowledgeRequest,
    RemoveHierarchyChildRequest,
)
from core.models.enums.entity_enums import EntityType
from core.models.principle.principle import Principle
from core.models.principle.principle_request import (
    PrincipleBatchImpactRequest,
    PrincipleExpressionRequest,
    PrincipleLinkRequest,
    PrincipleReflectionRequest,
)
from core.models.principle.principle_update_intent import PrincipleUpdateIntent
from core.utils.result_simplified import Errors, Result
from ui.activities.principles_views import PrincipleCard

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.principles_service import PrinciplesService


def create_principles_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    principles_service: PrinciplesService,
    goals_service: Any = None,
    habits_service: Any = None,
    **_kwargs: Any,
) -> list[Any]:
    """Register Principles API routes."""

    async def update_status(uid: str, new_status: str) -> Result[Principle]:
        # Mirror tasks_api/choices_api: go through the facade contract with a typed intent
        # (ADR-066), not past it into .core with a raw dict. The facade funnels through the
        # core's PrincipleUpdated-firing update path.
        return await principles_service.update_principle(
            uid, PrincipleUpdateIntent(status=new_status)
        )

    async def update_priority(uid: str, new_priority: str) -> Result[Principle]:
        return await principles_service.update_principle(
            uid, PrincipleUpdateIntent(priority=new_priority)
        )

    field_routes = create_activity_field_api_routes(
        rt,
        ActivityFieldApiConfig(
            domain_name="principles",
            singular="principle",
            service=principles_service,
            card_fn=PrincipleCard,
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

    @rt("/api/principles/children", methods=["GET"])
    @boundary_handler()
    async def principle_children(request: Request) -> Result[list[Principle]]:
        """Direct subprinciples of a parent principle."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(
            principles_service, uid, user_uid, "principle"
        )
        if ownership_error:
            return ownership_error
        result = await principles_service.get_subprinciples(uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok([p for p in result.value if p.user_uid == user_uid])

    @rt("/api/principles/parent", methods=["GET"])
    @boundary_handler()
    async def principle_parent(request: Request) -> Result[Optional[Principle]]:  # noqa: UP045
        """Immediate parent of a subprinciple (None if root-level)."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(
            principles_service, uid, user_uid, "principle"
        )
        if ownership_error:
            return ownership_error
        result = await principles_service.get_parent_principle(uid)
        if result.is_error:
            return Result.fail(result)
        if result.value is not None and result.value.user_uid != user_uid:
            return Result.ok(None)
        return result

    @rt("/api/principles/hierarchy", methods=["GET"])
    @boundary_handler()
    async def principle_hierarchy(request: Request) -> Result[dict[str, Any]]:
        """Full hierarchy context: ancestors, current, siblings, children, depth."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(
            principles_service, uid, user_uid, "principle"
        )
        if ownership_error:
            return ownership_error
        result = await principles_service.get_principle_hierarchy(uid)
        if result.is_error:
            return Result.fail(result)
        h = result.value
        ancestors = [pr for pr in h["ancestors"] if pr.user_uid == user_uid]
        return Result.ok(
            {
                "ancestors": ancestors,
                "current": h["current"],
                "siblings": [pr for pr in h["siblings"] if pr.user_uid == user_uid],
                "children": [pr for pr in h["children"] if pr.user_uid == user_uid],
                "depth": len(ancestors),
            }
        )

    @rt("/api/principles/remove-child", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def principle_remove_child(request: Request) -> Result[dict[str, Any]]:
        """Remove a subprinciple relationship (does not delete the principle nodes)."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, RemoveHierarchyChildRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        ownership_error = await verify_entity_ownership(
            principles_service, req.parent_uid, user_uid, "principle"
        )
        if ownership_error:
            return ownership_error
        child_ownership_error = await verify_entity_ownership(
            principles_service, req.child_uid, user_uid, "principle"
        )
        if child_ownership_error:
            return child_ownership_error
        result = await principles_service.remove_subprinciple_relationship(
            req.parent_uid, req.child_uid
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"removed": result.value})

    @rt("/api/principles/add-child", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def principle_add_child(request: Request) -> Result[dict[str, Any]]:
        """Add a subprinciple relationship between two principles."""
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
            principles_service, req.parent_uid, user_uid, "principle"
        )
        if ownership_error:
            return ownership_error
        child_ownership_error = await verify_entity_ownership(
            principles_service, req.child_uid, user_uid, "principle"
        )
        if child_ownership_error:
            return child_ownership_error
        existing_parent = await principles_service.get_parent_principle(req.child_uid)
        if existing_parent.is_error:
            return Result.fail(existing_parent)
        if existing_parent.value is not None:
            return Result.fail(
                Errors.validation(
                    "principle already has a parent — remove it first", field="child_uid"
                )
            )
        result = await principles_service.create_subprinciple_relationship(
            req.parent_uid, req.child_uid
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"added": result.value})

    # ================================================================
    # CROSS-DOMAIN LINKS
    # ================================================================

    @rt("/api/principles/link-knowledge", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def principle_link_knowledge(request: Request) -> Result[dict[str, Any]]:
        """Link principle to knowledge it is grounded in (GROUNDED_IN_KNOWLEDGE). Ku is shared."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, LinkPrincipleToKnowledgeRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        ownership_error = await verify_entity_ownership(
            principles_service, req.principle_uid, user_uid, "principle"
        )
        if ownership_error:
            return ownership_error
        result = await principles_service.link_principle_to_knowledge(
            req.principle_uid, req.knowledge_uid, req.relevance
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"linked": result.value})

    # ================================================================
    # EMBODIMENT — expressions, portfolio, integrity
    # ================================================================

    @rt("/api/principles/expression", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def principle_create_expression(request: Request) -> Result[dict[str, Any]]:
        """Append a lived expression (context + behavior) to a principle."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, PrincipleExpressionRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(
                Errors.validation(message="uid query param is required", field="uid")
            )
        ownership_error = await verify_entity_ownership(
            principles_service, uid, user_uid, "principle"
        )
        if ownership_error:
            return ownership_error
        return await principles_service.create_principle_expression(
            {
                "principle_uid": uid,
                "context": req.context,
                "behavior": req.behavior,
                "example": req.example,
            }
        )

    @rt("/api/principles/portfolio", methods=["GET"])
    @boundary_handler()
    async def principle_portfolio(request: Request) -> Result[dict[str, Any]]:
        """Return the authenticated user's complete principle portfolio."""
        user_uid = require_authenticated_user(request)
        return await principles_service.get_user_principle_portfolio(user_uid)

    @rt("/api/principles/integrity", methods=["GET"])
    @boundary_handler()
    async def principle_integrity(request: Request) -> Result[dict[str, Any]]:
        """Calculate how well user's actions align with a stated principle."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(
            principles_service, uid, user_uid, "principle"
        )
        if ownership_error:
            return ownership_error
        return await principles_service.calculate_principle_integrity(user_uid, uid)

    # ================================================================
    # GRAVITY — cross-domain links
    # ================================================================

    @rt("/api/principles/link", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def principle_create_link(request: Request) -> Result[dict[str, Any]]:
        """Link a principle to a goal, habit, knowledge unit, or another principle."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(
            principles_service, uid, user_uid, "principle"
        )
        if ownership_error:
            return ownership_error
        parsed = await parse_json_body(request, PrincipleLinkRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        # Knowledge (Ku) is SHARED — no ownership check required.
        # User-owned targets (goal, habit, principle) must 404 for wrong owner.
        if req.link_type == EntityType.GOAL.value and goals_service is not None:
            target_err = await verify_entity_ownership(goals_service, req.uid, user_uid, "goal")
            if target_err:
                return target_err
        elif req.link_type == EntityType.HABIT.value and habits_service is not None:
            target_err = await verify_entity_ownership(habits_service, req.uid, user_uid, "habit")
            if target_err:
                return target_err
        elif req.link_type == EntityType.PRINCIPLE.value:
            target_err = await verify_entity_ownership(
                principles_service, req.uid, user_uid, "principle"
            )
            if target_err:
                return target_err
        return await principles_service.create_principle_link(
            {"principle_uid": uid, "target_uid": req.uid, "link_type": req.link_type}
        )

    @rt("/api/principles/links", methods=["GET"])
    @boundary_handler()
    async def principle_get_links(request: Request) -> Result[list[dict[str, Any]]]:
        """Return all cross-domain links for a principle, optionally filtered by link_type."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(
            principles_service, uid, user_uid, "principle"
        )
        if ownership_error:
            return ownership_error
        link_type = request.query_params.get("link_type") or None
        return await principles_service.get_principle_links(uid, link_type)

    # ================================================================
    # ANALYTICS — impact, batch adoption, choice effectiveness
    # ================================================================

    @rt("/api/principles/impact", methods=["GET"])
    @boundary_handler()
    async def principle_quick_impact(request: Request) -> Result[dict[str, Any]]:
        """Return quick impact metrics for a principle (relationship counts, adoption level)."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(
            principles_service, uid, user_uid, "principle"
        )
        if ownership_error:
            return ownership_error
        return await principles_service.get_quick_principle_impact(uid)

    @rt("/api/principles/batch-impact", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def principle_batch_impact(request: Request) -> Result[dict[str, dict[str, Any]]]:
        """Batch-analyze adoption metrics for multiple principles."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, PrincipleBatchImpactRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        for uid in parsed.value.principle_uids:
            ownership_error = await verify_entity_ownership(
                principles_service, uid, user_uid, "principle"
            )
            if ownership_error:
                return ownership_error
        return await principles_service.batch_analyze_principle_adoption(
            parsed.value.principle_uids
        )

    @rt("/api/principles/choice-effectiveness", methods=["GET"])
    @boundary_handler()
    async def principle_choice_effectiveness(request: Request) -> Result[dict[str, Any]]:
        """Analyze how effectively a principle guides user choices."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(
            principles_service, uid, user_uid, "principle"
        )
        if ownership_error:
            return ownership_error
        period_str = request.query_params.get("period_days", "90")
        try:
            period_days = int(period_str)
        except ValueError:
            period_days = 90
        return await principles_service.get_choice_guidance_effectiveness(
            uid, user_uid, period_days
        )

    # ================================================================
    # REFLECTION — publishes PrincipleReflectionRecorded + optionally
    #               PrincipleConflictRevealed
    # ================================================================

    @rt("/api/principles/reflection", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def principle_record_reflection(request: Request) -> Result[dict[str, Any]]:
        """
        Record a principle reflection (how well you lived it today).

        Publishes PrincipleReflectionRecorded. Supply conflicting_principle_uid
        to also fire PrincipleConflictRevealed.
        """
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, PrincipleReflectionRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        ownership_error = await verify_entity_ownership(
            principles_service, req.principle_uid, user_uid, "principle"
        )
        if ownership_error:
            return ownership_error
        if req.conflicting_principle_uid:
            conflict_ownership_error = await verify_entity_ownership(
                principles_service, req.conflicting_principle_uid, user_uid, "principle"
            )
            if conflict_ownership_error:
                return conflict_ownership_error
        return await principles_service.record_principle_reflection(
            principle_uid=req.principle_uid,
            user_uid=user_uid,
            alignment_level=req.alignment_level.value,
            evidence=req.evidence,
            trigger_type=req.trigger_type,
            trigger_uid=req.trigger_uid,
            conflicting_principle_uid=req.conflicting_principle_uid,
            reflection_quality_score=req.reflection_quality_score,
        )

    # ================================================================
    # KNOWLEDGE INTELLIGENCE — learning patterns
    # ================================================================

    @rt("/api/principles/knowledge-patterns", methods=["GET"])
    @boundary_handler()
    async def principle_knowledge_patterns(request: Request) -> Result[dict[str, Any]]:
        """Detect knowledge-learning patterns across the authenticated user's principles."""
        user_uid = require_authenticated_user(request)
        timeframe_days = parse_int_query_param(
            request.query_params, "timeframe_days", default=30, minimum=1, maximum=365
        )
        result = await principles_service.analyze_learning_patterns(user_uid, timeframe_days)
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
        principle_children,
        principle_parent,
        principle_hierarchy,
        principle_remove_child,
        principle_add_child,
        principle_link_knowledge,
        principle_create_expression,
        principle_portfolio,
        principle_integrity,
        principle_create_link,
        principle_get_links,
        principle_quick_impact,
        principle_batch_impact,
        principle_choice_effectiveness,
        principle_record_reflection,
        principle_knowledge_patterns,
    ]
