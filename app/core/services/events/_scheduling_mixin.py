"""
Scheduling Mixin — EventsService
==================================

Conflict detection and recurring instance management.

Part of events_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.event.event import Event
    from core.models.event.event_request import (
        CheckConflictsRequest,
        GetRecurringEventsRequest,
        RecurringInstancesRequest,
    )
    from core.models.type_hints import EntityUID
    from core.ports.domain_protocols import EventsOperations
    from core.services.events.events_core_service import EventsCoreService


class _SchedulingMixin:
    """
    Conflict detection and recurring instance management for EventsService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by EventsService.__init__ / BaseService
    backend: "EventsOperations"
    core: EventsCoreService
    search: Any
    logger: Any
    get_event: Any  # delegation method on EventsService

    async def get_recurring_events(self, request: GetRecurringEventsRequest) -> Result[list[Event]]:
        """
        Get all recurring events for a user using typed request.

        Args:
            request: GetRecurringEventsRequest containing:
                - user_uid: User identifier
                - limit: Maximum results

        Returns:
            Result with list of recurring events
        """
        return await self.search.get_recurring(request.user_uid, request.limit)

    async def check_conflicts(self, request: CheckConflictsRequest) -> Result[list[EntityUID]]:
        """
        Check for scheduling conflicts with other events using typed request.

        Args:
            request: CheckConflictsRequest containing event_uid to check

        Returns:
            Result with list of conflicting event UIDs
        """
        event_result = await self.core.get(request.event_uid)
        if event_result.is_error:
            return Result.fail(event_result)

        event = event_result.value
        if not event:
            return Result.fail(Errors.not_found(resource="Event", identifier=request.event_uid))

        if not event.event_date or not event.start_time or not event.end_time:
            return Result.ok([])

        same_day_result = await self.backend.find_by(
            user_uid=event.user_uid,
            event_date=event.event_date.isoformat(),
        )
        if same_day_result.is_error:
            return Result.fail(same_day_result)

        conflicting_uids = [
            other.uid
            for other in (same_day_result.value or [])
            if other.uid != event.uid and event.overlaps_with(other)
        ]

        return Result.ok(conflicting_uids)

    async def create_recurring_instances(
        self,
        request: RecurringInstancesRequest,
    ) -> Result[list[Event]]:
        """
        Create instances of a recurring event using typed request.

        Args:
            request: RecurringInstancesRequest containing:
                - event_uid: UID of the recurring event template
                - count: Number of instances to create (1-100)

        Returns:
            Result with list of created event instances
        """
        from datetime import timedelta

        from core.models.event.event import Event as EventModel
        from core.models.event.event_dto import EventDTO

        event_result = await self.get_event(request.event_uid)
        if event_result.is_error:
            return Result.fail(event_result)

        event = event_result.value
        if not event:
            return Result.fail(Errors.not_found(resource="Event", identifier=request.event_uid))

        if not event.recurrence_pattern:
            return Result.fail(
                Errors.validation(
                    message="Event is not recurring",
                    field="recurrence_pattern",
                    value=None,
                )
            )

        pattern = event.recurrence_pattern

        interval_days = {
            "daily": 1,
            "weekly": 7,
            "biweekly": 14,
            "monthly": 30,
            "yearly": 365,
        }.get(pattern, 7)

        created_events: list[EventModel] = []
        base_date = event.event_date
        if base_date is None:
            return Result.fail(
                Errors.validation(
                    message="Event has no date set",
                    field="event_date",
                    value=None,
                )
            )

        for i in range(1, request.count + 1):
            new_date = base_date + timedelta(days=interval_days * i)

            dto = EventDTO.create_event(
                user_uid=event.user_uid,
                title=event.title,
                event_date=new_date,
                start_time=event.start_time,
                end_time=event.end_time,
                event_type=event.event_type,
                location=event.location,
                is_online=event.is_online,
                tags=event.tags,
            )
            dto.recurrence_parent_uid = request.event_uid  # Link to template

            create_result = await self.backend.create(EventModel.from_dto(dto))
            if create_result.is_ok:
                created_events.append(create_result.value)

        return Result.ok(created_events)
