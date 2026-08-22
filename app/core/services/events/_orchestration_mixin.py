"""
Orchestration Mixin — EventsService
=====================================

Multi-service coordination methods: attendee management, cross-domain
linking, and context-aware event creation.

Part of events_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.calendar_event_events import EventAttendeeAdded, EventAttendeeRemoved
from core.models.enums import AttendanceStatus, EventType, RecurrencePattern
from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.models.relationship_names import RelationshipName
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.event.event_request import (
        AddAttendeeRequest,
        EventCreateRequest,
        RemoveAttendeeRequest,
    )
    from core.models.type_hints import UserUID
    from core.ports.domain_protocols import EventsOperations
    from core.services.events.events_core_service import EventsCoreService
    from core.services.user import UserContext


class _OrchestrationMixin:
    """
    Multi-service coordination methods for EventsService.

    Covers attendee management, cross-domain relationship linking, and the
    context-aware creation flow. Status transitions are NOT here — the one
    status path is ``update_event(uid, EventUpdateIntent(status=...))`` via
    the generic status API route (events_api.py).

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by EventsService.__init__ / BaseService
    backend: "EventsOperations"
    core: EventsCoreService
    relationships: Any
    event_bus: Any
    logger: Any
    get_event: Any  # delegation method on EventsService

    # ========================================================================
    # GRAPH RELATIONSHIPS — Cross-domain linking
    # ========================================================================

    async def link_event_to_goal(
        self, event_uid: str, goal_uid: str, contribution_weight: float = 1.0
    ) -> Result[bool]:
        """Link event to goal it contributes to (``CONTRIBUTES_TO_GOAL``)."""
        return await self.relationships.create_relationship(
            "goals", event_uid, goal_uid, {"contribution_weight": contribution_weight}
        )

    async def link_event_to_habit(self, event_uid: str, habit_uid: str) -> Result[bool]:
        """Link event to habit it reinforces."""
        return await self.relationships.create_relationship("habits", event_uid, habit_uid)

    async def link_event_to_knowledge(
        self, event_uid: str, knowledge_uids: list[str]
    ) -> Result[bool]:
        """Link event to knowledge units it reinforces."""
        result = await self.relationships.create_relationships_batch(
            event_uid, {"knowledge": knowledge_uids}
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value > 0)

    # ========================================================================
    # ATTENDEE MANAGEMENT — (User)-[:ATTENDS]->(Event), ADR-086 (staged)
    # ========================================================================
    # STAGED: no route reaches this triple yet (PLANNED_METHODS). The actor is
    # always resolved by the caller from the auth layer (current_user) — never
    # from the request body. Wiring-PR obligations recorded in ADR-086: the
    # self-add eligibility gate ("open to the actor" events), max_attendees
    # enforcement, a role enum, and the soft-delete ghost-attendee filter.

    async def get_event_attendees(self, event_uid: str) -> Result[list[str]]:
        """Get attendee user UIDs for an event.

        Attendees hold a ``(User)-[:ATTENDS]->(Event)`` edge — read as an
        *incoming* ``ATTENDS`` traversal on the backend. Returns attendees in
        every consent status; status-aware reads and the live-user ghost filter
        are wiring obligations (ADR-086).
        """
        return await self.backend.get_related_uids(
            event_uid, RelationshipName.ATTENDS, direction="incoming"
        )

    async def add_attendee(self, request: AddAttendeeRequest, actor_uid: UserUID) -> Result[bool]:
        """
        Add an attendee to an event — the consent-aware attendance write.

        The ADR-086 state machine decides what the write may say:
        - actor == target (self-add): writes ``accepted`` — self-add IS the
          attendee's consent, and it also accepts the actor's own pending
          invite (the target is the only actor who transitions status).
        - actor == event owner (organizer): creates ``invited`` — an organizer
          can never write acceptance for someone else; re-inviting an existing
          attendance changes nothing.
        - anyone else: refused (Forbidden).

        Args:
            request: target ``user_uid`` + ``event_uid`` + ``role`` +
                ``send_notification`` (the target, never the actor).
            actor_uid: The acting user, from the auth layer.

        Returns:
            Result[bool] — success of the attendance write.
        """
        event_result = await self.core.get(request.event_uid)
        if event_result.is_error:
            return Result.fail(event_result)
        event = event_result.value
        if event is None:
            return Result.fail(Errors.not_found("event", request.event_uid))

        if actor_uid == request.user_uid:
            # Self-add is the attendee's own consent. Eligibility gate (whether
            # this event is open to the actor) is a wiring obligation — see the
            # section comment.
            status = AttendanceStatus.ACCEPTED
            set_status_on_match = True
        elif event.user_uid == actor_uid:
            status = AttendanceStatus.INVITED
            set_status_on_match = False
        else:
            return Result.fail(
                Errors.forbidden(
                    f"add attendee to event {request.event_uid}",
                    reason="only the event owner may invite, and only the target user may self-add",
                )
            )

        result = await self.backend.add_attendee(
            event_uid=request.event_uid,
            attendee_uid=request.user_uid,
            actor_uid=actor_uid,
            role=request.role,
            status=status.value,
            set_status_on_match=set_status_on_match,
        )
        if result.is_error:
            return Result.fail(result)

        if request.send_notification:
            notification_event = EventAttendeeAdded(
                event_uid=request.event_uid,
                event_title=event.title,
                attendee_uid=request.user_uid,
                added_by_uid=actor_uid,
                role=request.role,
            )
            await publish_event(self.event_bus, notification_event, self.logger)

        return Result.ok(True)

    async def remove_attendee(
        self, request: RemoveAttendeeRequest, actor_uid: UserUID
    ) -> Result[bool]:
        """
        Remove an attendee from an event — consent-aware (ADR-086).

        - actor == target: may always remove their own attendance, whatever its
          status.
        - actor == event owner (organizer): may only revoke a still-``invited``
          attendance — an accepted attendance is the attendee's to keep.
        - anyone else: refused (Forbidden).

        Args:
            request: target ``user_uid`` + ``event_uid`` + ``send_notification``.
            actor_uid: The acting user, from the auth layer.

        Returns:
            Result[bool] — True when an attendance was removed; False when
            nothing matched (absent, or the organizer's revoke met a
            non-invited attendance).
        """
        event_result = await self.core.get(request.event_uid)
        if event_result.is_error:
            return Result.fail(event_result)
        event = event_result.value
        if event is None:
            return Result.fail(Errors.not_found("event", request.event_uid))

        if actor_uid == request.user_uid:
            only_if_status: str | None = None
        elif event.user_uid == actor_uid:
            only_if_status = AttendanceStatus.INVITED.value
        else:
            return Result.fail(
                Errors.forbidden(
                    f"remove attendee from event {request.event_uid}",
                    reason=(
                        "only the target user may leave, and the event owner "
                        "may only revoke a pending invite"
                    ),
                )
            )

        result = await self.backend.remove_attendee(
            event_uid=request.event_uid,
            attendee_uid=request.user_uid,
            only_if_status=only_if_status,
        )
        if result.is_error:
            return Result.fail(result)

        if result.value and request.send_notification:
            notification_event = EventAttendeeRemoved(
                event_uid=request.event_uid,
                event_title=event.title,
                attendee_uid=request.user_uid,
                removed_by_uid=actor_uid,
            )
            await publish_event(self.event_bus, notification_event, self.logger)

        return Result.ok(result.value)

    # ========================================================================
    # CONTEXT-AWARE CREATION
    # ========================================================================

    async def create_event_with_context(
        self, event_data: EventCreateRequest, user_context: UserContext
    ) -> Result[Event]:
        """
        Create an event with full context awareness (orchestration method).

        This method orchestrates multiple checks:
        1. Sets up habit reinforcement relationships
        2. Links to learning paths if applicable
        3. Updates context after creation
        """
        dto = EventDTO.create_event(
            user_uid=user_context.user_uid,
            title=event_data.title,
            event_date=event_data.event_date,
            start_time=event_data.start_time,
            end_time=event_data.end_time,
            event_type=event_data.event_type,
            location=event_data.location,
            is_online=event_data.is_online,
            tags=event_data.tags,
        )

        # Habit reinforcement is a graph edge ((Event)-[:REINFORCES_HABIT]->(Habit)),
        # not a DTO property — capture it here and write the edge after create.
        habit_uid = event_data.reinforces_habit_uid

        if habit_uid and habit_uid in user_context.active_habit_uids:
            dto.recurrence_pattern = RecurrencePattern.DAILY  # Default

        create_result = await self.backend.create(Event.from_dto(dto))
        if create_result.is_error:
            return Result.fail(create_result)

        event = create_result.value

        if habit_uid:
            await self.link_event_to_habit(event.uid, habit_uid)

        from core.events import CalendarEventCreated, publish_event

        event_obj = CalendarEventCreated(
            event_uid=event.uid,
            user_uid=user_context.user_uid,
            title=event.title,
            # Event.event_date and .event_type are both optional on the model but
            # required by the event; fall back the same way the sibling publish
            # sites in events_core_service / events_habit_integration_service do.
            event_date=event.event_date or date.today(),
            calendar_event_type=event.event_type or EventType.MEETING,
        )
        await publish_event(self.event_bus, event_obj, self.logger)

        if event_data.practices_knowledge_uids:
            from core.events.knowledge_substance_events import KnowledgePracticedInEvent

            for knowledge_uid in event_data.practices_knowledge_uids:
                knowledge_event = KnowledgePracticedInEvent(
                    knowledge_uid=knowledge_uid,
                    event_uid=event.uid,
                    user_uid=user_context.user_uid,
                    event_title=event.title,
                    duration_minutes=event.duration_minutes,
                )
                await publish_event(self.event_bus, knowledge_event, self.logger)

            self.logger.debug(
                f"Published {len(event_data.practices_knowledge_uids)} KnowledgePracticedInEvent events for event {event.uid}"
            )

        self.logger.info(
            "Created event %s with habit=%s, knowledge=%d",
            event.uid,
            habit_uid,
            len(event_data.practices_knowledge_uids or []),
        )

        return Result.ok(event)
