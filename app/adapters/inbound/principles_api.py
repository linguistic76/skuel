"""Principles API routes.

Provides HTMX-compatible endpoints for principle status/priority updates and hierarchy queries.

Hierarchy (ownership-verified, via create_activity_hierarchy_api_routes):
    GET  /api/principles/children       — Direct subprinciples of a parent principle (JSON)
    GET  /api/principles/{uid}/children — Subprinciples as a TreeNodeList fragment (HTMX)
    GET  /api/principles/parent         — Immediate parent of a subprinciple
    GET  /api/principles/hierarchy      — Full hierarchy context (ancestors, siblings, children)
    POST /api/principles/remove-child   — Remove a subprinciple relationship
    POST /api/principles/add-child      — Add a subprinciple relationship

Cross-domain links (via create_activity_link_api_routes):
    POST /api/principles/link-knowledge — Link principle to knowledge it is grounded in

Knowledge intelligence:
    GET  /api/principles/knowledge-patterns — Detected learning patterns across user principles
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
    create_activity_field_api_routes,
    create_activity_hierarchy_api_routes,
    create_activity_link_api_routes,
    create_knowledge_patterns_api_route,
    verify_entity_ownership,
)
from core.models.entity_requests import (
    AddHierarchyChildRequest,
    LinkPrincipleToKnowledgeRequest,
)
from core.models.enums.neo_labels import NeoLabel
from core.models.enums.principle_enums import PrincipleLinkType
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
    from core.ports import ConnectionFetchOperations
    from core.services.principles_service import PrinciplesService


def create_principles_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    principles_service: PrinciplesService,
    connection_fetch_backend: ConnectionFetchOperations,
    **_kwargs: Any,
) -> None:
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

    create_activity_field_api_routes(
        rt,
        ActivityFieldApiConfig(
            domain_name="principles",
            singular="principle",
            service=principles_service,
            card_fn=PrincipleCard,
            links=connection_fetch_backend,
            link_label=NeoLabel.PRINCIPLE,
            fields=(
                FieldUpdateSpec(field="status", apply=update_status),
                FieldUpdateSpec(
                    field="priority", apply=update_priority, allowed_values=PRIORITY_VALUES
                ),
            ),
        ),
    )

    # ================================================================
    # HIERARCHY — shared Activity Domain hierarchy route block
    # ================================================================

    async def add_subprinciple_relationship(req: AddHierarchyChildRequest) -> Result[bool]:
        # Principles carry no progress_weight — the request field is ignored.
        return await principles_service.create_subprinciple_relationship(
            req.parent_uid, req.child_uid
        )

    create_activity_hierarchy_api_routes(
        rt,
        ActivityHierarchyApiConfig(
            domain_name="principles",
            singular="principle",
            service=principles_service,
            get_children=principles_service.get_subprinciples,
            get_parent=principles_service.get_parent_principle,
            get_hierarchy=principles_service.get_principle_hierarchy,
            add_child_relationship=add_subprinciple_relationship,
            remove_child_relationship=principles_service.remove_subprinciple_relationship,
        ),
    )

    # ================================================================
    # CROSS-DOMAIN LINKS
    # ================================================================

    async def apply_link_knowledge(req: LinkPrincipleToKnowledgeRequest) -> Result[bool]:
        return await principles_service.link_principle_to_knowledge(
            req.principle_uid, req.knowledge_uid, req.relevance
        )

    create_activity_link_api_routes(
        rt,
        domain_name="principles",
        singular="principle",
        service=principles_service,
        specs=(
            CrossDomainLinkSpec(
                action="link-knowledge",
                request_model=LinkPrincipleToKnowledgeRequest,
                owner_uid_field="principle_uid",
                apply=apply_link_knowledge,
                doc="Link principle to a Ku it is grounded in (GROUNDED_IN_KNOWLEDGE). "
                "The service admits the far end: a Ku, shared content.",
            ),
        ),
    )

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
        """Link the caller's principle (query ``uid``) to a goal, habit, Ku, choice or principle."""
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
        # The target is admitted by the service, per link_type: it exists, is of that
        # kind, and is the caller's own or shared content — anything else is not found.
        return await principles_service.create_principle_link(uid, req.target_uid, req.link_type)

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
        link_type: PrincipleLinkType | None = None
        requested = request.query_params.get("link_type")
        if requested:
            try:
                link_type = PrincipleLinkType(requested)
            except ValueError:
                return Result.fail(
                    Errors.validation(
                        message=f"link_type must be one of: {', '.join(PrincipleLinkType)}",
                        field="link_type",
                        value=requested,
                    )
                )
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

    create_knowledge_patterns_api_route(
        rt, "principles", principles_service.analyze_learning_patterns
    )
