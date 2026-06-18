"""Choices API routes.

Provides HTMX-compatible endpoints for choice status updates and hierarchy queries.

Hierarchy (ownership-verified):
    GET  /api/choices/children     — Direct subchoices of a parent choice
    GET  /api/choices/parent       — Immediate parent of a subchoice
    GET  /api/choices/hierarchy    — Full hierarchy context (ancestors, siblings, children)
    POST /api/choices/remove-child — Remove a subchoice relationship
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
from core.models.choice.choice_update_intent import ChoiceUpdateIntent
from core.models.entity_requests import RemoveHierarchyChildRequest
from core.utils.result_simplified import Errors, Result
from ui.activities.choices_views import ChoiceCard

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.models.choice.choice import Choice
    from core.services.choices_service import ChoicesService


def create_choices_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    choices_service: ChoicesService,
    **_kwargs: Any,
) -> list[Any]:
    """Register Choices API routes."""

    async def update(uid: str, new_status: str) -> Result[Choice]:
        # Mirror tasks_api: go through the facade contract with a typed intent (ADR-066),
        # not past it into .core with a raw dict. The facade funnels through the core's
        # validated, ChoiceUpdated-firing update path.
        return await choices_service.update_choice(uid, ChoiceUpdateIntent(status=new_status))

    status_routes = create_activity_status_api_routes(
        rt,
        ActivityStatusApiConfig(
            domain_name="choices",
            singular="choice",
            service=choices_service,
            update_status=update,
            card_fn=ChoiceCard,
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
        return await choices_service.get_subchoices(uid)

    @rt("/api/choices/parent", methods=["GET"])
    @boundary_handler()
    async def choice_parent(request: Request) -> Result[Choice | None]:
        """Immediate parent of a subchoice (None if root-level)."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(choices_service, uid, user_uid, "choice")
        if ownership_error:
            return ownership_error
        return await choices_service.get_parent_choice(uid)

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
        return await choices_service.get_choice_hierarchy(uid)

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
        result = await choices_service.remove_subchoice_relationship(req.parent_uid, req.child_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"removed": result.value})

    return [
        *status_routes,
        choice_children,
        choice_parent,
        choice_hierarchy,
        choice_remove_child,
    ]
