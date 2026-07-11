"""Events API routes.

Provides HTMX-compatible endpoints for event status/priority updates and hierarchy queries.

Hierarchy (ownership-verified):
    GET  /api/events/children     — Direct subevents of a parent event
    GET  /api/events/parent       — Immediate parent of a subevent
    GET  /api/events/hierarchy    — Full hierarchy context (ancestors, siblings, children)
    POST /api/events/remove-child — Remove a subevent relationship
    POST /api/events/add-child   — Add a subevent relationship

Cross-domain links:
    POST /api/events/link-goal    — Link event to a goal it contributes to

Knowledge intelligence:
    GET  /api/events/knowledge-patterns — Detected learning patterns across user events
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
    LinkEventToGoalRequest,
    RemoveHierarchyChildRequest,
)
from core.models.event.event import Event
from core.models.event.event_update_intent import EventUpdateIntent
from core.utils.result_simplified import Errors, Result
from ui.activities.events_views import EventCard

if TYPE_CHECKING:
    from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
    from core.services.events_service import EventsService
    from core.services.goals_service import GoalsService


def create_events_api_routes(
    app: FastHTMLApp,
    rt: RouteDecorator,
    events_service: EventsService,
    goals_service: GoalsService,
    **_kwargs: Any,
) -> list[Any]:
    """Register Events API routes."""

    async def update_status(uid: str, new_status: str) -> Result[Event]:
        return await events_service.update_event(uid, EventUpdateIntent(status=new_status))

    async def update_priority(uid: str, new_priority: str) -> Result[Event]:
        return await events_service.update_event(uid, EventUpdateIntent(priority=new_priority))

    field_routes = create_activity_field_api_routes(
        rt,
        ActivityFieldApiConfig(
            domain_name="events",
            singular="event",
            service=events_service,
            card_fn=EventCard,
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
        result = await events_service.get_subevents(uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok([e for e in result.value if e.user_uid == user_uid])

    @rt("/api/events/parent", methods=["GET"])
    @boundary_handler()
    async def event_parent(request: Request) -> Result[Optional[Event]]:  # noqa: UP045
        """Immediate parent of a subevent (None if root-level)."""
        user_uid = require_authenticated_user(request)
        uid = request.query_params.get("uid", "")
        if not uid:
            return Result.fail(Errors.validation(message="uid is required", field="uid"))
        ownership_error = await verify_entity_ownership(events_service, uid, user_uid, "event")
        if ownership_error:
            return ownership_error
        result = await events_service.get_parent_event(uid)
        if result.is_error:
            return Result.fail(result)
        if result.value is not None and result.value.user_uid != user_uid:
            return Result.ok(None)
        return result

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
        result = await events_service.get_event_hierarchy(uid)
        if result.is_error:
            return Result.fail(result)
        h = result.value
        ancestors = [ev for ev in h["ancestors"] if ev.user_uid == user_uid]
        return Result.ok(
            {
                "ancestors": ancestors,
                "current": h["current"],
                "siblings": [ev for ev in h["siblings"] if ev.user_uid == user_uid],
                "children": [ev for ev in h["children"] if ev.user_uid == user_uid],
                "depth": len(ancestors),
            }
        )

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
        child_ownership_error = await verify_entity_ownership(
            events_service, req.child_uid, user_uid, "event"
        )
        if child_ownership_error:
            return child_ownership_error
        result = await events_service.remove_subevent_relationship(req.parent_uid, req.child_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"removed": result.value})

    @rt("/api/events/add-child", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def event_add_child(request: Request) -> Result[dict[str, Any]]:
        """Add a subevent relationship between two events."""
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
            events_service, req.parent_uid, user_uid, "event"
        )
        if ownership_error:
            return ownership_error
        child_ownership_error = await verify_entity_ownership(
            events_service, req.child_uid, user_uid, "event"
        )
        if child_ownership_error:
            return child_ownership_error
        existing_parent = await events_service.get_parent_event(req.child_uid)
        if existing_parent.is_error:
            return Result.fail(existing_parent)
        if existing_parent.value is not None:
            return Result.fail(
                Errors.validation("event already has a parent — remove it first", field="child_uid")
            )
        result = await events_service.create_subevent_relationship(req.parent_uid, req.child_uid)
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"added": result.value})

    # ================================================================
    # CROSS-DOMAIN LINKS
    # ================================================================

    @rt("/api/events/link-goal", methods=["POST"])
    @csrf_protected
    @boundary_handler()
    async def event_link_goal(request: Request) -> Result[dict[str, Any]]:
        """Link event to a goal it contributes to (CONTRIBUTES_TO_GOAL)."""
        user_uid = require_authenticated_user(request)
        parsed = await parse_json_body(request, LinkEventToGoalRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value
        ownership_error = await verify_entity_ownership(
            events_service, req.event_uid, user_uid, "event"
        )
        if ownership_error:
            return ownership_error
        goal_ownership_error = await verify_entity_ownership(
            goals_service, req.goal_uid, user_uid, "goal"
        )
        if goal_ownership_error:
            return goal_ownership_error
        result = await events_service.link_event_to_goal(
            req.event_uid, req.goal_uid, req.contribution_weight
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok({"linked": result.value})

    # ================================================================
    # KNOWLEDGE INTELLIGENCE — learning patterns
    # ================================================================

    @rt("/api/events/knowledge-patterns", methods=["GET"])
    @boundary_handler()
    async def event_knowledge_patterns(request: Request) -> Result[dict[str, Any]]:
        """Detect knowledge-learning patterns across the authenticated user's events."""
        user_uid = require_authenticated_user(request)
        timeframe_days = parse_int_query_param(
            request.query_params, "timeframe_days", default=30, minimum=1, maximum=365
        )
        result = await events_service.analyze_learning_patterns(user_uid, timeframe_days)
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
        event_children,
        event_parent,
        event_hierarchy,
        event_remove_child,
        event_add_child,
        event_link_goal,
        event_knowledge_patterns,
    ]
