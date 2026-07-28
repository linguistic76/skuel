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
"""

from __future__ import annotations

from datetime import date
from operator import attrgetter
from typing import TYPE_CHECKING, Any

from core.events import publish_event
from core.events.base import BaseEvent
from core.events.calendar_event_events import (
    CalendarEventCompleted,
    CalendarEventCreated,
    CalendarEventDeleted,
    CalendarEventRescheduled,
    CalendarEventUpdated,
)
from core.events.embedding_publisher import publish_embedding_requested
from core.models.enums import EntityStatus
from core.models.enums.entity_enums import EntityType
from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.models.event.event_request import EventType
from core.models.event.event_update_intent import EventUpdateIntent
from core.models.type_hints import UserUID
from core.ports.query_types import EventStats
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.mixins.hierarchy_read_mixin import HierarchyReadMixin
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports.domain_protocols import EventsOperations


class EventsCoreService(
    HierarchyReadMixin["EventsOperations", Event],
    BaseService["EventsOperations", Event, EventUpdateIntent],
):
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
    # EMBEDDING HELPERS (Async Background Generation - January 2026)
    # ========================================================================

    # ========================================================================
    # DOMAIN-SPECIFIC CONFIGURATION (DomainConfig - January 2026)
    # ========================================================================

    _config = create_activity_domain_config(
        dto_class=EventDTO,
        model_class=Event,
        entity_label="Entity",
        domain_name="events",
        date_field="event_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
        status_filters={
            "scheduled": {"status": "scheduled"},
            "completed": {"status": "completed"},
            "cancelled": {"status": "cancelled"},
        },
    )
    # ========================================================================
    # DOMAIN-SPECIFIC VALIDATION HOOKS
    # ========================================================================

    def _validate_create(self, event: Event) -> Result[None]:
        """
        Validate event creation with business rules.

        Business Rules:
        1. Event duration sanity check: 5 minutes to 12 hours (720 minutes)

        Args:
            event: Ku domain model being created

        Returns:
            None if valid, Result.fail() with validation error if invalid
        """

        # Business Rule: Event duration sanity check
        # Catches data entry errors and suggests better patterns
        duration = event.duration_minutes
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

        return Result.ok(None)  # All validations passed

    def _validate_update(self, current: Event, updates: EventUpdateIntent) -> Result[None]:
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

        changes = updates.to_changes()
        # Business Rule 1: Past event immutability (with notes exception)
        # Past events are historical records, but allow adding notes retrospectively
        if current.event_date and current.event_date < date.today():
            allowed_fields = {"notes", "tags", "quality_score"}  # Can update these
            disallowed_updates = set(changes.keys()) - allowed_fields

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
        if "duration_minutes" in changes:
            duration = changes["duration_minutes"]
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

        return Result.ok(None)  # All validations passed

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

    async def get_user_events(self, user_uid: UserUID) -> Result[list[Event]]:
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
            return Result.fail(result)

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
            return Result.fail(result)

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
        count_result = await self.backend.count(**(filters or {}))
        if count_result.is_error:
            return Result.fail(count_result)
        return Result.ok(count_result.value)

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
                event_date=event.event_date or date.today(),
                # Canonical member, not the former lowercase "meeting" literal:
                # EventAdapter compares against EventType's UPPERCASE members.
                # (get_enum_value was a no-op here — event_type is a str field.)
                calendar_event_type=event.event_type or EventType.MEETING,
            )
            await publish_event(self.event_bus, domain_event, self.logger)

            # Post-persist embedding refresh (ADR-074) — the background worker embeds async
            await publish_embedding_requested(self.event_bus, EntityType.EVENT, event, self.logger)

        return result

    @with_error_handling("update_event", error_type="database", uid_param="uid")
    async def update_event(self, uid: str, intent: EventUpdateIntent) -> Result[Event]:
        """Update a calendar event's node properties (ADR-066 typed update contract).

        Materializes the intent to a partial patch once, validated and written through the
        inherited CRUD ``update`` (BaseService → ``_validate_update`` → ``backend.update``),
        then publishes the appropriate calendar event. This is Shape B: ``super().update``
        is kept (not a direct ``backend.update``) so ``_validate_update`` (past-event
        immutability, duration bounds) still runs.

        The facade (``EventsService.update_event``) splits the two edge fields off the
        intent before calling this, so ``intent.to_changes()`` here carries only node
        properties.

        Args:
            uid: Event UID
            intent: Typed ``EventUpdateIntent`` (property sub-intent) — only set fields written

        Returns:
            Result containing updated Event

        Events Published:
            - CalendarEventCompleted: if status transitions into COMPLETED
            - CalendarEventRescheduled: if event_date changed
            - CalendarEventUpdated: otherwise (cache invalidation contract)
        """
        changes = intent.to_changes()
        # Capture the intended fields now: the backend stamps updated_at in place, so
        # reading changes.keys() after the write would leak that bump into the event.
        updated_fields: dict[str, Any] = dict(changes)

        # Fetch the prior event only when a status / date transition needs old-vs-new.
        old_event_date = None
        old_status = None
        if "status" in changes or "event_date" in changes:
            current_result = await self.get(uid)
            if current_result.is_ok and current_result.value:
                old_event_date = current_result.value.event_date
                old_status = current_result.value.status

        result = await super().update(uid, intent)
        if result.is_error:
            return result

        event = result.value

        domain_event: BaseEvent
        # Priority 1: Status changed to COMPLETED (state transition only).
        if (
            "status" in changes
            and changes["status"] == EntityStatus.COMPLETED.value
            and old_status != EntityStatus.COMPLETED
        ):
            domain_event = CalendarEventCompleted(
                event_uid=event.uid,
                user_uid=event.user_uid,
                completion_date=event.event_date or date.today(),
                # quality_score never flows through the generic update path — it is owned
                # by the progress / habit-completion services, which fire their own
                # CalendarEventCompleted with the score (honest None, not a dead key read).
                quality_score=None,
            )
        # Priority 2: Event date changed (rescheduled).
        elif "event_date" in changes and old_event_date and changes["event_date"] != old_event_date:
            domain_event = CalendarEventRescheduled(
                event_uid=event.uid,
                user_uid=event.user_uid,
                old_date=old_event_date,
                new_date=changes["event_date"],
            )
        # Default: Generic update (cache invalidation contract).
        else:
            domain_event = CalendarEventUpdated(
                event_uid=event.uid,
                user_uid=event.user_uid,
                updated_fields=updated_fields,
            )
        await publish_event(self.event_bus, domain_event, self.logger)

        # Post-persist embedding refresh (ADR-074) — only when a text field changed
        await publish_embedding_requested(
            self.event_bus, EntityType.EVENT, event, self.logger, changed_fields=updated_fields
        )

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
            return Result.fail(event_result)

        event = event_result.value

        # Call parent delete
        result = await super().delete(uid, cascade=cascade)

        # Publish CalendarEventDeleted event
        if result.is_ok:
            domain_event = CalendarEventDeleted(
                event_uid=uid,
                user_uid=event.user_uid,
                title=event.title,
            )
            await publish_event(self.event_bus, domain_event, self.logger)

        return result

    # ========================================================================
    # HIERARCHICAL RELATIONSHIPS (2026-01-30 - Flat UID, Rich Structure)
    # Delegated to EventsBackend via _HierarchyMixin (2026-03-24)
    # ========================================================================

    async def create_subevent_relationship(
        self,
        parent_uid: str,
        subevent_uid: str,
        order: int = 0,
        time_offset_minutes: int | None = None,
    ) -> Result[bool]:
        """Create bidirectional HAS_SUBEVENT/SUBEVENT_OF relationship with cycle detection."""
        forward_props: dict[str, Any] = {"order": order}
        if time_offset_minutes is not None:
            forward_props["time_offset_minutes"] = time_offset_minutes
        return await self.backend.create_hierarchy_relationship(
            parent_uid, subevent_uid, forward_props
        )

    async def remove_subevent_relationship(
        self, parent_uid: str, subevent_uid: str
    ) -> Result[bool]:
        """Remove bidirectional HAS_SUBEVENT/SUBEVENT_OF relationship."""
        return await self.backend.remove_hierarchy_relationship(parent_uid, subevent_uid)

    # ========================================================================
    # QUERY LAYER — Cypher-level filtering for get_filtered_context
    # ========================================================================

    async def get_stats_for_user(self, user_uid: UserUID) -> Result[EventStats]:
        """Count event stats via Cypher COUNT — no entity deserialization."""
        return await self.backend.get_stats_for_user(user_uid)

    # get_for_user_filtered: inherited from SearchOperationsMixin, driven by
    # the status_filters map in _config above.
