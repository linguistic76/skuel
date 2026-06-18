"""Events API routes.

Provides HTMX-compatible endpoints for event status updates and hierarchy queries.

Hierarchy (ownership-verified):
    GET  /api/events/children     — Direct subevents of a parent event
    GET  /api/events/parent       — Immediate parent of a subevent
    GET  /api/events/hierarchy    — Full hierarchy context (ancestors, siblings, children)
    POST /api/events/remove-child — Remove a subevent relationship
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
from core.models.event.event_update_intent import EventUpdateIntent
from core.utils.result_simplified import Errors, Result
from ui.activities.events_views import EventCard

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.models.event.event import Event
    from core.services.events_service import EventsService


def create_events_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    events_service: EventsService,
    **_kwargs: Any,
) -> list[Any]:
    """Register Events API routes."""

    async def update(uid: str, new_status: str) -> Result[Event]:
        return await events_service.update_event(uid, EventUpdateIntent(status=new_status))

    status_routes = create_activity_status_api_routes(
        rt,
        ActivityStatusApiConfig(
            domain_name="events",
            singular="event",
            service=events_service,
            update_status=update,
            card_fn=EventCard,
        ),
    )

    # ================================================================
    # HIERARCHY — read-paths and relationship removal
    # ================================================================

    @rt("/api/events/children", methods=["GET"])
    @boundary_handler()
    async def event_children(request: Request) -> Result[list[Event]]:
        """Direct subevents of a parent event."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(events_service, uid, user_uid, "event")
        if ownership_error:
            return ownership_error
        return await events_service.get_subevents(uid)

    @rt("/api/events/parent", methods=["GET"])
    @boundary_handler()
    async def event_parent(request: Request) -> Result[Event | None]:
        """Immediate parent of a subevent (None if root-level)."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(events_service, uid, user_uid, "event")
        if ownership_error:
            return ownership_error
        return await events_service.get_parent_event(uid)

    @rt("/api/events/hierarchy", methods=["GET"])
    @boundary_handler()
    async def event_hierarchy(request: Request) -> Result[dict[str, Any]]:
        """Full hierarchy context: ancestors, current, siblings, children, depth."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(events_service, uid, user_uid, "event")
        if ownership_error:
            return ownership_error
        return await events_service.get_event_hierarchy(uid)

    @rt("/api/events/remove-child", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def event_remove_child(request: Request) -> Result[dict[str, Any]]:
        """Remove a subevent relationship (does not delete the event nodes)."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, RemoveHierarchyChildRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        ownership_error = await verify_entity_ownership(
            events_service, req.parent_uid, user_uid, "event"
        )
        if ownership_error:
            return ownership_error
        result = await events_service.remove_subevent_relationship(req.parent_uid, req.child_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"removed": result.value})

    return [
        *status_routes,
        event_children,
        event_parent,
        event_hierarchy,
        event_remove_child,
    ]
