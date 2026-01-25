"""
Events Core Service
===================

Handles basic CRUD operations for events.

Responsibilities:
- Get event by UID
- Get user's events
- List events with filters
- Count events
- Basic event retrieval operations
- Publishes domain events (CalendarEventCreated, CalendarEventUpdated, etc.)

Version: 2.0.0
Date: 2025-11-05
"""

from datetime import date, datetime
from operator import attrgetter
from typing import Any, ClassVar

from core.events import publish_event
from core.events.calendar_event_events import (
    CalendarEventCompleted,
    CalendarEventCreated,
    CalendarEventDeleted,
    CalendarEventRescheduled,
    CalendarEventUpdated,
)
from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.models.shared_enums import ActivityStatus
from core.services.base_service import BaseService
from core.services.protocols import get_enum_value
from core.services.protocols.domain_protocols import EventsOperations
from core.utils.result_simplified import Result


class EventsCoreService(BaseService[EventsOperations, Event]):
    """
    Core CRUD service for events.

    Handles:
    - Basic retrieval operations
    - User event queries
    - Event listing and filtering
    - Event counting
    - Publishes domain events for all state changes

    Event-Driven Architecture:
    - Publishes CalendarEventCreated on creation
    - Publishes CalendarEventUpdated on update
    - Publishes CalendarEventCompleted on completion
    - Publishes CalendarEventDeleted on deletion
    - Publishes CalendarEventRescheduled on date change


    Source Tag: "events_core_service_explicit"
    - Format: "events_core_service_explicit" for user-created relationships
    - Format: "events_core_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from events_core metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(self, backend: EventsOperations, event_bus=None) -> None:
        """
        Initialize events core service.

        Args:
            backend: Protocol-based backend for event operations
            event_bus: Event bus for publishing domain events (optional)

        Note:
            Context invalidation now happens via event-driven architecture.
            Calendar event operations trigger domain events which invalidate context.
        """
        super().__init__(backend, "events.core")
        self.event_bus = event_bus

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Event entities."""
        return "Event"

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (Class Attributes)
    # ========================================================================
    # CONSOLIDATED (November 27, 2025): These class attributes configure
    # the unified get_user_items_in_range() method in BaseService.

    _date_field: str = "event_date"  # Events filter by event date
    _completed_statuses: ClassVar[list[str]] = [
        ActivityStatus.COMPLETED.value,
        ActivityStatus.CANCELLED.value,
    ]
    _dto_class = EventDTO
    _model_class = Event

    # ========================================================================
    # DOMAIN-SPECIFIC VALIDATION HOOKS
    # ========================================================================

    def _validate_create(self, event: Event) -> Result[None] | None:
        """
        Validate event creation with business rules.

        Business Rules:
        1. Event duration sanity check: 5 minutes to 12 hours (720 minutes)

        Args:
            event: Event domain model being created

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """
        from core.utils.result_simplified import Errors

        # Business Rule: Event duration sanity check
        # Catches data entry errors and suggests better patterns
        duration = event.duration_minutes()  # duration_minutes is a METHOD, not an attribute
        if duration:
            if duration < 5:
                return Result.fail(
                    Errors.validation(
                        message="Event duration must be at least 5 minutes",
                        field="duration_minutes",
                        value=duration,
                    )
                )

            if duration > 720:  # 12 hours
                return Result.fail(
                    Errors.validation(
                        message="Event duration exceeds 12 hours. Use multi-day event or split into sessions.",
                        field="duration_minutes",
                        value=duration,
                    )
                )

        return None  # All validations passed

    def _validate_update(self, current: Event, updates: dict[str, Any]) -> Result[None] | None:
        """
        Validate event updates with business rules.

        Business Rules:
        1. Past event immutability: Can't modify past events (except notes/tags)
        2. Duration sanity check: If updating duration, must be 5-720 minutes

        Args:
            current: Current event state
            updates: Dictionary of proposed changes

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """
        from core.utils.result_simplified import Errors

        # Business Rule 1: Past event immutability (with notes exception)
        # Past events are historical records, but allow adding notes retrospectively
        if current.event_date and current.event_date < date.today():
            allowed_fields = {"notes", "tags", "quality_score"}  # Can update these
            disallowed_updates = set(updates.keys()) - allowed_fields

            if disallowed_updates:
                return Result.fail(
                    Errors.validation(
                        message=f"Cannot modify past events (except notes/tags/quality_score). "
                        f"Attempted to change: {', '.join(disallowed_updates)}",
                        field="event_date",
                        value=current.event_date.isoformat(),
                    )
                )

        # Business Rule 2: Duration sanity check on update
        if "duration_minutes" in updates:
            duration = updates["duration_minutes"]
            if duration < 5:
                return Result.fail(
                    Errors.validation(
                        message="Event duration must be at least 5 minutes",
                        field="duration_minutes",
                        value=duration,
                    )
                )

            if duration > 720:  # 12 hours
                return Result.fail(
                    Errors.validation(
                        message="Event duration exceeds 12 hours. Use multi-day event or split into sessions.",
                        field="duration_minutes",
                        value=duration,
                    )
                )

        return None  # All validations passed

    # ========================================================================
    # BASIC CRUD OPERATIONS
    # ========================================================================

    async def get_event(self, event_uid: str) -> Result[Event]:
        """
        Get a specific event by UID.

        Uses BaseService.get() which delegates to BackendOperations.get().
        Not found is returned as Result.fail(Errors.not_found(...)).

        Args:
            event_uid: Event UID

        Returns:
            Result[Event] - success contains Event, not found is an error
        """
        return await self.get(event_uid)

    async def get_user_events(self, user_uid: str) -> Result[list[Event]]:
        """
        Get all events for a user, including learning relationships.

        Args:
            user_uid: UID of the user

        Returns:
            Result containing list of Event objects
        """
        # Use find_by with user_uid filter (UniversalNeo4jBackend pattern)
        result = await self.backend.find_by(user_uid=user_uid)
        if result.is_error:
            return Result.fail(result.expect_error())

        # find_by returns domain models directly (no DTO conversion needed)
        return result

    async def find_events(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        offset: int = 0,
        order_by: str | None = None,
        order_desc: bool = False,
    ) -> Result[list[Event]]:
        """
        Find events with filters and pagination.

        Args:
            filters: Optional filters to apply,
            limit: Maximum number of results,
            offset: Pagination offset,
            order_by: Field to order by,
            order_desc: Whether to order descending

        Returns:
            Result containing list of events
        """
        # Use backend's list_events method
        result = await self.backend.list(filters=filters or {}, limit=limit, offset=offset)

        if result.is_error:
            return Result.fail(result.expect_error())

        # Unpack tuple: backend.list() returns (events, total_count)
        events_data, _ = result.value

        # Use BaseService helper for batch DTO conversion
        events = self._to_domain_models(events_data, EventDTO, Event)

        # Sort if requested
        if order_by and events:
            reverse = order_desc
            if order_by == "event_date":
                events.sort(key=attrgetter("event_date"), reverse=reverse)
            elif order_by == "title":
                events.sort(key=attrgetter("title"), reverse=reverse)
            elif order_by == "created_at":
                events.sort(key=attrgetter("created_at"), reverse=reverse)

        return Result.ok(events)

    async def count_events(self, filters: dict[str, Any] | None = None) -> Result[int]:
        """
        Count events matching filters efficiently.

        Args:
            filters: Optional filters to apply

        Returns:
            Result containing count
        """
        try:
            # Try using backend's count method if available
            count = await self.backend.count_events(filters=filters)
            return Result.ok(count)
        except AttributeError:
            # Fallback: count via list_events
            self.logger.warning(
                "Backend doesn't support efficient count, falling back to list_events"
            )
            result = await self.backend.list(filters=filters or {})

            if result.is_error:
                return Result.fail(result.expect_error())

            # Unpack tuple: backend.list() returns (events, total_count)
            _, total_count = result.value
            return Result.ok(total_count)
        except Exception as e:
            self.logger.error(f"Error counting events: {e}")
            # Fallback to list method
            result = await self.backend.list(filters=filters or {})

            if result.is_error:
                return Result.fail(result.expect_error())

            # Unpack tuple: backend.list() returns (events, total_count)
            _, total_count = result.value
            return Result.ok(total_count)

    # get_user_items_in_range() is now inherited from BaseService
    # Configured via class attributes: _date_field, _completed_statuses, _dto_class, _model_class
    # CONSOLIDATED (November 27, 2025) - Removed 45 lines of duplicate code

    # ========================================================================
    # EVENT-DRIVEN CRUD OPERATIONS
    # ========================================================================

    async def create(self, entity: Event) -> Result[Event]:
        """
        Create a calendar event and publish CalendarEventCreated event.

        Args:
            entity: Event to create

        Returns:
            Result containing created Event

        Events Published:
            - CalendarEventCreated: When event is successfully created
        """
        # Call parent create
        result = await super().create(entity)

        # Publish CalendarEventCreated event
        if result.is_ok:
            event = result.value
            domain_event = CalendarEventCreated(
                event_uid=event.uid,
                user_uid=event.user_uid,
                title=event.title,
                event_date=event.event_date,
                calendar_event_type=get_enum_value(event.event_type)
                if event.event_type
                else "meeting",
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, domain_event, self.logger)

        return result

    async def update(self, uid: str, updates: dict[str, Any]) -> Result[Event]:
        """
        Update a calendar event and publish appropriate events.

        Publishes CalendarEventUpdated, CalendarEventCompleted, or
        CalendarEventRescheduled depending on what changed.

        Args:
            uid: Event UID
            updates: Dictionary of field updates

        Returns:
            Result containing updated Event

        Events Published:
            - CalendarEventCompleted: If status changed to COMPLETED
            - CalendarEventRescheduled: If event_date changed
            - CalendarEventUpdated: For other updates
        """
        # Get current event to track specific changes (always fetch for update events)
        old_event_date = None
        old_status = None
        current_result = await self.get(uid)
        if current_result.is_ok and current_result.value:
            old_event_date = current_result.value.event_date
            old_status = current_result.value.status

        # Call parent update
        result = await super().update(uid, updates)

        # Publish appropriate event based on what changed
        if result.is_ok:
            event = result.value

            # Priority 1: Status changed to COMPLETED (state transition only)
            if (
                "status" in updates
                and updates["status"] == ActivityStatus.COMPLETED.value
                and old_status != ActivityStatus.COMPLETED
            ):
                domain_event = CalendarEventCompleted(
                    event_uid=event.uid,
                    user_uid=event.user_uid,
                    completion_date=event.event_date,
                    quality_score=updates.get("quality_score"),
                    occurred_at=datetime.now(),
                )
                await publish_event(self.event_bus, domain_event, self.logger)

            # Priority 2: Event date changed (rescheduled)
            elif (
                "event_date" in updates
                and old_event_date
                and updates["event_date"] != old_event_date
            ):
                domain_event = CalendarEventRescheduled(
                    event_uid=event.uid,
                    user_uid=event.user_uid,
                    old_date=old_event_date,
                    new_date=updates["event_date"],
                    occurred_at=datetime.now(),
                )
                await publish_event(self.event_bus, domain_event, self.logger)

            # Default: Generic update
            else:
                domain_event = CalendarEventUpdated(
                    event_uid=event.uid,
                    user_uid=event.user_uid,
                    updated_fields=updates,
                    occurred_at=datetime.now(),
                )
                await publish_event(self.event_bus, domain_event, self.logger)

        return result

    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """
        DETACH DELETE a calendar event and publish CalendarEventDeleted event.

        Args:
            uid: Event UID
            cascade: Whether to cascade DETACH DELETE (default False)

        Returns:
            Result indicating success

        Events Published:
            - CalendarEventDeleted: When event is successfully deleted
        """
        # Get event details before deletion for event publishing
        event_result = await self.get(uid)
        if event_result.is_error:
            return Result.fail(event_result.expect_error())

        event = event_result.value

        # Call parent delete
        result = await super().delete(uid, cascade=cascade)

        # Publish CalendarEventDeleted event
        if result.is_ok:
            domain_event = CalendarEventDeleted(
                event_uid=uid,
                user_uid=event.user_uid,
                title=event.title,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, domain_event, self.logger)

        return result
