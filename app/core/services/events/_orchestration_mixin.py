"""
Orchestration Mixin — EventsService
=====================================

Multi-service coordination methods: attendee management, cross-domain
linking, and context-aware event creation.

Part of events_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.calendar_event_events import EventAttendeeAdded, EventAttendeeRemoved
from core.models.enums import EventType, RecurrencePattern
from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.models.relationship_names import RelationshipName
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.event.event_request import (
        AddAttendeeRequest,
        EventCreateRequest,
        RemoveAttendeeRequest,
    )
    from core.models.type_hints import UserUID
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
    backend: Any
    core: EventsCoreService
    relationships: Any
    event_bus: Any
    logger: Any
    get_event: Any  # delegation method on EventsService

    # ========================================================================
    # GRAPH RELATIONSHIPS — Cross-domain linking
    # ========================================================================

    async def create_user_event_relationship(
        self, user_uid: UserUID, event_uid: str, participation_type: str = "scheduled"
    ) -> Result[bool]:
        """Create User→Event relationship in graph."""
        properties = (
            {"participation_type": participation_type}
            if participation_type != "scheduled"
            else None
        )
        return await self.relationships.create_user_relationship(user_uid, event_uid, properties)

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
    # ATTENDEE MANAGEMENT
    # ========================================================================

    async def get_event_attendees(self, event_uid: str) -> Result[list[str]]:
        """Get attendee user UIDs for an event.

        Attendees are users joined via ``(User)-[:HAS_EVENT]->(Event)`` — the same edge
        ``add_attendee``/``remove_attendee`` create and delete. Read it as an *incoming*
        ``HAS_EVENT`` traversal on the backend. (The previous ``get_related_uids("attendees",
        event_uid)`` used a config method_key that does not exist, so it always failed
        validation and returned nothing — the write path and read path had diverged.)
        """
        return await self.backend.get_related_uids(
            event_uid, RelationshipName.HAS_EVENT, direction="incoming"
        )

    async def add_attendee(self, request: AddAttendeeRequest) -> Result[bool]:
        """
        Add an attendee to an event using typed request.

        Args:
            request: AddAttendeeRequest containing:
                - event_uid: UID of the event
                - user_uid: UID of the user to add as attendee
                - role: Attendee role (attendee, organizer, speaker)
                - send_notification: Whether to notify the attendee

        Returns:
            Result with success status
        """
        properties = {"participation_type": request.role} if request.role != "scheduled" else None
        result = await self.relationships.create_user_relationship(
            user_uid=request.user_uid,
            entity_uid=request.event_uid,
            properties=properties,
        )

        if request.send_notification and result.is_ok:
            event_result = await self.core.get(request.event_uid)
            event_title = (
                event_result.value.title if event_result.is_ok and event_result.value else "Event"
            )

            notification_event = EventAttendeeAdded(
                event_uid=request.event_uid,
                event_title=event_title,
                attendee_uid=request.user_uid,
                added_by_uid=request.user_uid,
                role=request.role,
            )
            await publish_event(self.event_bus, notification_event, self.logger)

        return result

    async def remove_attendee(self, request: RemoveAttendeeRequest) -> Result[bool]:
        """
        Remove an attendee from an event using typed request.

        Args:
            request: RemoveAttendeeRequest containing:
                - event_uid: UID of the event
                - user_uid: UID of the user to remove
                - send_notification: Whether to notify the attendee

        Returns:
            Result with success status
        """
        event_title = "Event"
        if request.send_notification:
            event_result = await self.core.get(request.event_uid)
            if event_result.is_ok and event_result.value:
                event_title = event_result.value.title

        result = await self.relationships.delete_user_relationship(
            user_uid=request.user_uid,
            entity_uid=request.event_uid,
        )

        if request.send_notification and result.is_ok:
            notification_event = EventAttendeeRemoved(
                event_uid=request.event_uid,
                event_title=event_title,
                attendee_uid=request.user_uid,
                removed_by_uid=request.user_uid,
            )
            await publish_event(self.event_bus, notification_event, self.logger)

        return result

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

        create_result = await self.backend.create(dto.to_dict())
        if create_result.is_error:
            return Result.fail(create_result)

        event = self._to_domain_model(create_result.value, EventDTO, Event)  # type: ignore[attr-defined]

        if habit_uid:
            await self.link_event_to_habit(event.uid, habit_uid)

        from core.events import CalendarEventCreated, publish_event

        event_obj = CalendarEventCreated(
            event_uid=event.uid,
            user_uid=user_context.user_uid,
            title=event.title,
            event_date=event.event_date,
            # Event.event_type is str | None. Not a mypy error here only
            # because the ignore above leaves `event` as Any — same defect as
            # the three sibling publish sites, fixed the same way.
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
