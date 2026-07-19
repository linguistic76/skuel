"""Events API routes.

Provides HTMX-compatible endpoints for event status/priority updates and hierarchy queries.

Hierarchy (ownership-verified, via create_activity_hierarchy_api_routes):
    GET  /api/events/children       — Direct subevents of a parent event (JSON)
    GET  /api/events/{uid}/children — Subevents as a TreeNodeList fragment (HTMX)
    GET  /api/events/parent         — Immediate parent of a subevent
    GET  /api/events/hierarchy      — Full hierarchy context (ancestors, siblings, children)
    POST /api/events/remove-child   — Remove a subevent relationship
    POST /api/events/add-child      — Add a subevent relationship

Cross-domain links (via create_activity_link_api_routes):
    POST /api/events/link-goal    — Link event to a goal it contributes to

Knowledge intelligence:
    GET  /api/events/knowledge-patterns — Detected learning patterns across user events
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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
)
from core.models.entity_requests import AddHierarchyChildRequest, LinkEventToGoalRequest
from core.models.event.event import Event
from core.models.event.event_update_intent import EventUpdateIntent
from core.utils.result_simplified import Result
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

    async def add_subevent_relationship(req: AddHierarchyChildRequest) -> Result[bool]:
        # Events carry no progress_weight — the request field is ignored.
        return await events_service.create_subevent_relationship(req.parent_uid, req.child_uid)

    hierarchy_routes = create_activity_hierarchy_api_routes(
        rt,
        ActivityHierarchyApiConfig(
            domain_name="events",
            singular="event",
            service=events_service,
            get_children=events_service.get_subevents,
            get_parent=events_service.get_parent_event,
            get_hierarchy=events_service.get_event_hierarchy,
            add_child_relationship=add_subevent_relationship,
            remove_child_relationship=events_service.remove_subevent_relationship,
        ),
    )

    async def apply_link_goal(req: LinkEventToGoalRequest) -> Result[bool]:
        return await events_service.link_event_to_goal(
            req.event_uid, req.goal_uid, req.contribution_weight
        )

    link_routes = create_activity_link_api_routes(
        rt,
        domain_name="events",
        singular="event",
        service=events_service,
        specs=(
            CrossDomainLinkSpec(
                action="link-goal",
                request_model=LinkEventToGoalRequest,
                owner_uid_field="event_uid",
                apply=apply_link_goal,
                doc="Link event to a goal it contributes to (CONTRIBUTES_TO_GOAL).",
                target=LinkTargetSpec(service=goals_service, uid_field="goal_uid", singular="goal"),
            ),
        ),
    )

    knowledge_patterns_route = create_knowledge_patterns_api_route(
        rt, "events", events_service.analyze_learning_patterns
    )

    return [
        *field_routes,
        *hierarchy_routes,
        *link_routes,
        knowledge_patterns_route,
    ]
