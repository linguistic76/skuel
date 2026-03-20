"""
Events Event Handler Service
==============================

Handles event-driven reactive logic for calendar event domain events.

Fire-and-forget handlers that analyze attendance patterns, detect
rescheduling trends, and monitor scheduling density.

Part of the EventsService decomposition — centralizes all domain-specific
event handling for calendar events.

Responsibilities:
- Attendance time-of-day pattern tracking on event completion
- Goal alignment cross-domain insights on completion
- Chronic rescheduling pattern detection
- Scheduling density monitoring and overcommitment warnings
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from core.events.calendar_event_events import (
    CalendarEventCompleted,
    CalendarEventCreated,
    CalendarEventRescheduled,
)
from core.models.relationship_names import RelationshipName
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS, NEO4J_EXCEPTIONS
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.ports.domain_protocols import EventsOperations
    from core.services.relationships import UnifiedRelationshipService


# ========================================================================
# MODULE-LEVEL HELPERS
# ========================================================================


def _classify_rescheduling_pattern(reschedule_count: int) -> str:
    """Classify rescheduling frequency as a behavioral pattern.

    Args:
        reschedule_count: Number of reschedules in recent history for a user

    Returns:
        Classification: "rare", "occasional", or "chronic"
    """
    if reschedule_count <= 1:
        return "rare"
    elif reschedule_count <= 3:
        return "occasional"
    else:
        return "chronic"


def _assess_scheduling_density(events_in_week: int) -> str:
    """Assess how packed a user's week is based on event count.

    Args:
        events_in_week: Number of events in a 7-day window

    Returns:
        Density level: "light", "moderate", "heavy", or "overcommitted"
    """
    if events_in_week <= 3:
        return "light"
    elif events_in_week <= 7:
        return "moderate"
    elif events_in_week <= 12:
        return "heavy"
    else:
        return "overcommitted"


class EventsEventHandlerService:
    """Event-driven handlers for calendar event domain events.

    Fire-and-forget handlers that analyze attendance patterns, detect
    rescheduling trends, and monitor scheduling density.

    Handles:
    - CalendarEventCompleted: Attendance time-of-day tracking, goal alignment
    - CalendarEventRescheduled: Rescheduling pattern detection
    - CalendarEventCreated: Scheduling density monitoring
    """

    def __init__(
        self,
        backend: EventsOperations,
        relationship_service: UnifiedRelationshipService | None = None,
    ) -> None:
        """Initialize events event handler service.

        Args:
            backend: Backend for event operations
            relationship_service: For querying related entities (optional)
        """
        self.backend = backend
        self.relationships = relationship_service
        self.logger = get_logger("skuel.services.events.event_handler")

    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================

    async def handle_event_completed(self, event: CalendarEventCompleted) -> None:
        """Handle event completion with attendance tracking and goal alignment.

        The handler:
        1. Tracks time-of-day attendance pattern from completion_date
        2. Checks goal alignment via relationship service

        Args:
            event: CalendarEventCompleted event with completion context

        Note:
            Fire-and-forget — errors are logged, never propagated.
        """
        try:
            # 1. Attendance time-of-day pattern
            hour = event.occurred_at.hour
            if hour < 6:
                time_slot = "early_morning"
            elif hour < 12:
                time_slot = "morning"
            elif hour < 17:
                time_slot = "afternoon"
            elif hour < 21:
                time_slot = "evening"
            else:
                time_slot = "night"

            self.logger.info(
                f"Event completed ({time_slot})",
                extra={
                    "event_uid": event.event_uid,
                    "user_uid": event.user_uid,
                    "completion_date": event.completion_date.isoformat(),
                    "time_slot": time_slot,
                    "quality_score": event.quality_score,
                    "event_type": "calendar_event.completed.tracked",
                },
            )

            # 2. Goal alignment check
            if self.relationships:
                await self._check_goal_alignment(event)

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                f"Error handling event_completed: {e}",
                extra={
                    "event_uid": event.event_uid,
                    "user_uid": event.user_uid,
                    "error": str(e),
                },
            )

    async def handle_event_rescheduled(self, event: CalendarEventRescheduled) -> None:
        """Handle event rescheduling with pattern detection.

        Queries recent reschedule count for the user and classifies
        the rescheduling frequency as rare, occasional, or chronic.

        Args:
            event: CalendarEventRescheduled event with old/new dates

        Note:
            Fire-and-forget — errors are logged, never propagated.
        """
        try:
            # Query recent reschedules for this user (last 30 days)
            reschedule_count = await self._count_recent_reschedules(event.user_uid)

            pattern = _classify_rescheduling_pattern(reschedule_count)

            self.logger.info(
                f"Event rescheduled ({pattern}): {event.old_date} -> {event.new_date}",
                extra={
                    "event_uid": event.event_uid,
                    "user_uid": event.user_uid,
                    "old_date": event.old_date.isoformat(),
                    "new_date": event.new_date.isoformat(),
                    "reschedule_count": reschedule_count,
                    "pattern": pattern,
                    "event_type": "calendar_event.rescheduled.pattern",
                },
            )

            if pattern == "chronic":
                self.logger.warning(
                    f"Chronic rescheduling detected: {reschedule_count} reschedules in recent history",
                    extra={
                        "user_uid": event.user_uid,
                        "reschedule_count": reschedule_count,
                        "event_type": "calendar_event.rescheduling.chronic",
                    },
                )

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                f"Error handling event_rescheduled: {e}",
                extra={
                    "event_uid": event.event_uid,
                    "user_uid": event.user_uid,
                    "error": str(e),
                },
            )

    async def handle_event_created(self, event: CalendarEventCreated) -> None:
        """Handle event creation with scheduling density monitoring.

        Checks how many events the user has in the week around the
        new event's date and logs overcommitment warnings.

        Args:
            event: CalendarEventCreated event with event details

        Note:
            Fire-and-forget — errors are logged, never propagated.
        """
        try:
            # Check scheduling density for the week around the event date
            events_in_week = await self._count_events_in_week(
                event.user_uid, event.event_date
            )

            density = _assess_scheduling_density(events_in_week)

            self.logger.info(
                f"Event created, week density: {density} ({events_in_week} events)",
                extra={
                    "event_uid": event.event_uid,
                    "user_uid": event.user_uid,
                    "event_date": event.event_date.isoformat(),
                    "calendar_event_type": event.calendar_event_type,
                    "events_in_week": events_in_week,
                    "density": density,
                    "event_type": "calendar_event.created.density",
                },
            )

            if density == "overcommitted":
                self.logger.warning(
                    f"Overcommitment warning: {events_in_week} events in week of {event.event_date}",
                    extra={
                        "user_uid": event.user_uid,
                        "event_date": event.event_date.isoformat(),
                        "events_in_week": events_in_week,
                        "event_type": "calendar_event.scheduling.overcommitted",
                    },
                )

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                f"Error handling event_created: {e}",
                extra={
                    "event_uid": event.event_uid,
                    "user_uid": event.user_uid,
                    "error": str(e),
                },
            )

    # ========================================================================
    # INTERNAL HELPERS
    # ========================================================================

    async def _check_goal_alignment(self, event: CalendarEventCompleted) -> None:
        """Check if completed event is aligned with any goals.

        Generates cross-domain insight when event completion contributes
        to goal progress.
        """
        if not self.relationships:
            return

        aligned_result = await self.relationships.get_related_uids(
            RelationshipName.SUPPORTS_GOAL.value, event.event_uid
        )
        if aligned_result.is_ok and aligned_result.value:
            goal_uids = aligned_result.value
            self.logger.info(
                f"Completed event supports {len(goal_uids)} goal(s)",
                extra={
                    "event_uid": event.event_uid,
                    "user_uid": event.user_uid,
                    "goal_uids": goal_uids[:5],
                    "event_type": "calendar_event.completion.goal_alignment",
                },
            )

    async def _count_recent_reschedules(self, user_uid: str) -> int:
        """Count events rescheduled by this user in the last 30 days.

        Uses a lightweight query on event metadata to detect rescheduling frequency.
        """
        query = """
        MATCH (e:Entity {user_uid: $user_uid, entity_type: 'event'})
        WHERE e.rescheduled_at IS NOT NULL
          AND date(e.rescheduled_at) >= date() - duration('P30D')
        RETURN count(e) as reschedule_count
        """
        result = await self.backend.execute_query(query, {"user_uid": user_uid})
        if result.is_error or not result.value:
            return 0

        row = result.value[0]
        return row.get("reschedule_count", 0) if isinstance(row, dict) else 0

    async def _count_events_in_week(self, user_uid: str, event_date: date) -> int:
        """Count events for a user in the 7-day window around a date.

        Args:
            user_uid: User to check
            event_date: Center date for the week window
        """
        start = event_date - timedelta(days=3)
        end = event_date + timedelta(days=3)

        query = """
        MATCH (e:Entity {user_uid: $user_uid, entity_type: 'event'})
        WHERE e.event_date >= $start_date AND e.event_date <= $end_date
        RETURN count(e) as event_count
        """
        result = await self.backend.execute_query(
            query,
            {
                "user_uid": user_uid,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            },
        )
        if result.is_error or not result.value:
            return 0

        row = result.value[0]
        return row.get("event_count", 0) if isinstance(row, dict) else 0
