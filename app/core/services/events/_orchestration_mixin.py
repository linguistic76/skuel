"""
Orchestration Mixin — EventsService
=====================================

Multi-service coordination methods: event lifecycle (status, attendees),
cross-domain linking, and context-aware event creation.

Part of events_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.calendar_event_events import EventAttendeeAdded, EventAttendeeRemoved
from core.models.enums import EntityStatus, RecurrencePattern
from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.ports import get_enum_value
from core.ports.query_types import EventUpdatePayload
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.event.event_request import (
        AddAttendeeRequest,
        EventCreateRequest,
        EventStatusUpdateRequest,
        RemoveAttendeeRequest,
    )
    from core.models.type_hints import UserUID
    from core.services.user import UserContext


class _OrchestrationMixin:
    """
    Multi-service coordination methods for EventsService.

    Covers event lifecycle (status transitions, attendee management),
    cross-domain relationship linking, and the context-aware creation flow.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by EventsService.__init__ / BaseService
    backend: Any
    core: Any
    relationships: Any
    event_bus: Any
    logger: Any
    get_event: Any  # delegation method on EventsService

    # ========================================================================
    # STATUS MANAGEMENT
    # ========================================================================

    async def update_event_status(self, request: EventStatusUpdateRequest) -> Result[Event]:
        """
        Update an event's status using typed request object.

        Args:
            request: EventStatusUpdateRequest containing:
                - event_uid: UID of the event (added via route)
                - status: New status value
                - notes: Optional status change notes
                - cancellation_reason: Optional cancellation reason

        Returns:
            Result with the updated event
        """
        updates: dict[str, Any] = {"status": get_enum_value(request.status)}

        metadata_updates = {}
        if request.notes:
            metadata_updates["status_change_notes"] = request.notes
        if request.cancellation_reason:
            metadata_updates["cancellation_reason"] = request.cancellation_reason

        if metadata_updates:
            event_result = await self.core.get(request.event_uid)
            if event_result.is_error:
                return Result.fail(event_result)
            if event_result.value is None:
                return Result.fail(Errors.not_found(resource="Event", identifier=request.event_uid))
            current_metadata = event_result.value.metadata or {}
            updates["metadata"] = {**current_metadata, **metadata_updates}

        return await self.core.update(request.event_uid, updates)

    async def start_event(self, event_uid: str) -> Result[Event]:
        """Mark an event as started/in progress."""
        updates: EventUpdatePayload = {"status": EntityStatus.ACTIVE.value}
        return await self.core.update(event_uid, updates)

    async def complete_event(self, event_uid: str) -> Result[Event]:
        """Mark an event as completed."""
        updates: EventUpdatePayload = {"status": EntityStatus.COMPLETED.value}
        return await self.core.update(event_uid, updates)

    async def cancel_event(self, event_uid: str, reason: str = "") -> Result[Event]:
        """Cancel an event."""
        updates: EventUpdatePayload = {"status": EntityStatus.CANCELLED.value}
        if reason:
            updates["notes"] = reason
        return await self.core.update(event_uid, updates)

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
        """Link event to goal it supports."""
        return await self.relationships.link_to_goal(
            event_uid, goal_uid, contribution_weight=contribution_weight
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
        """Get attendees for an event."""
        return await self.relationships.get_related_uids("attendees", event_uid)

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

        dto.reinforces_habit_uid = event_data.reinforces_habit_uid
        # PHASE 3B: practices_knowledge_uids is a graph relationship, not a DTO field
        dto.fulfills_goal_uid = getattr(event_data, "supports_goal_uid", None)  # type: ignore[attr-defined]
        dto.learning_path_uid = getattr(event_data, "learning_path_uid", None)  # type: ignore[attr-defined]

        if dto.reinforces_habit_uid and dto.reinforces_habit_uid in user_context.active_habit_uids:
            dto.recurrence_pattern = RecurrencePattern.DAILY  # Default

        create_result = await self.backend.create(dto.to_dict())
        if create_result.is_error:
            return Result.fail(create_result)

        event = self._to_domain_model(create_result.value, EventDTO, Event)  # type: ignore[attr-defined]

        from core.events import CalendarEventCreated, publish_event

        event_obj = CalendarEventCreated(
            event_uid=event.uid,
            user_uid=user_context.user_uid,
            title=event.title,
            event_date=event.event_date,
            calendar_event_type=get_enum_value(event.event_type),
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
            event.reinforces_habit_uid,
            len(event_data.practices_knowledge_uids or []),
        )

        return Result.ok(event)
