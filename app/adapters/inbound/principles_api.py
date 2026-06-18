"""Principles API routes.

Provides HTMX-compatible endpoints for principle status updates and hierarchy queries.

Hierarchy (ownership-verified):
    GET  /api/principles/children     — Direct subprinciples of a parent principle
    GET  /api/principles/parent       — Immediate parent of a subprinciple
    GET  /api/principles/hierarchy    — Full hierarchy context (ancestors, siblings, children)
    POST /api/principles/remove-child — Remove a subprinciple relationship

Cross-domain links:
    POST /api/principles/link-knowledge — Link principle to knowledge it is grounded in
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
from core.models.entity_requests import LinkPrincipleToKnowledgeRequest, RemoveHierarchyChildRequest
from core.models.principle.principle_update_intent import PrincipleUpdateIntent
from core.utils.result_simplified import Errors, Result
from ui.activities.principles_views import PrincipleCard

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.models.principle.principle import Principle
    from core.services.principles_service import PrinciplesService


def create_principles_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    principles_service: PrinciplesService,
    **_kwargs: Any,
) -> list[Any]:
    """Register Principles API routes."""

    async def update(uid: str, new_status: str) -> Result[Principle]:
        # Mirror tasks_api/choices_api: go through the facade contract with a typed intent
        # (ADR-066), not past it into .core with a raw dict. The facade funnels through the
        # core's PrincipleUpdated-firing update path.
        return await principles_service.update_principle(
            uid, PrincipleUpdateIntent(status=new_status)
        )

    status_routes = create_activity_status_api_routes(
        rt,
        ActivityStatusApiConfig(
            domain_name="principles",
            singular="principle",
            service=principles_service,
            update_status=update,
            card_fn=PrincipleCard,
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
    async def principle_parent(request: Request) -> Result[Principle | None]:
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

    return [
        *status_routes,
        principle_children,
        principle_parent,
        principle_hierarchy,
        principle_remove_child,
        principle_link_knowledge,
    ]
