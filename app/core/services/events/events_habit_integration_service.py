"""
Events Habit Integration Service
=================================

Handles cross-domain habits integration FROM the Events perspective.

Responsibilities:
- Get events that reinforce specific habits
- Complete events with habit quality tracking
- Create recurring events for habit reinforcement
- Handle habit-event cascade effects

Complementary to HabitsEventIntegrationService (which handles Events integration
FROM the Habits perspective). This service manages actual Event entities and their
habit-related lifecycle.

Version: 1.0.0
Date: 2025-10-13
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from core.events import publish_event
from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.models.enums import ActivityStatus, RecurrencePattern
from core.services.context_first_mixin import (
    parse_date_field,
    parse_datetime_field,
    parse_enum_field,
)
from core.services.protocols.domain_protocols import EventsOperations
from core.services.user import UserContext
from core.utils.dto_helpers import to_domain_model
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


@dataclass(frozen=True)
class EventFilterCriteria:
    """Criteria for filtering events from rich context.

    Used by _filter_events_by_criteria() to reduce code duplication
    across get_events_for_habit, get_habit_reinforcement_events,
    get_at_risk_habit_events, and get_next_habit_events.
    """

    habit_uid: str | None = None
    require_habit: bool = False  # Only events with reinforces_habit_uid
    start_date: date | None = None
    end_date: date | None = None
    status_filter: str | None = None
    group_by_habit: bool = False
    find_earliest_per_habit: bool = False


class EventsHabitIntegrationService:
    """
    Cross-domain habit integration service for events.

    Handles event operations related to habit reinforcement:
    - Getting events for specific habits
    - Completing events with habit quality tracking
    - Creating recurring events for habits
    - Managing habit-event relationships


    Source Tag: "events_habit_integration_service_explicit"
    - Format: "events_habit_integration_service_explicit" for user-created relationships
    - Format: "events_habit_integration_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from events_habit_integration metadata
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
        Initialize events habit integration service.

        Args:
            backend: Protocol-based backend for event operations,
            event_bus: Event bus for publishing domain events (optional)

        Note:
            Context invalidation now happens via event-driven architecture.
            Calendar event operations trigger domain events which invalidate context.
        """
        self.backend = backend
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.events.habit_integration")

    # ========================================================================
    # CONTEXT-FIRST PATTERN: Rich Context Helpers (November 26, 2025)
    # ========================================================================
    # Philosophy: "Check UserContext.active_events_rich BEFORE querying Neo4j"
    #
    # UserContext is THE source of truth for user state.
    # MEGA-QUERY already fetched events with graph context - reuse that data!
    #
    # Benefits:
    # - Zero queries when data is in rich context
    # - Single source of truth (UserContext)
    # - Consistent with Tasks, Habits, Goals progress services
    # ========================================================================

    def _get_events_from_rich_context(self, user_context: UserContext) -> list[dict[str, Any]]:
        """
        Get all events from UserContext rich data.

        Returns list of raw event dicts from MEGA-QUERY.
        Each dict contains: {event: {...}, graph_context: {...}}

        Returns:
            List of event data dicts (may be empty if no rich context)
        """
        return user_context.active_events_rich or []

    def _filter_events_by_habit(
        self, events_rich: list[dict[str, Any]], habit_uid: str
    ) -> list[Event]:
        """
        Filter rich event data by reinforces_habit_uid.

        Args:
            events_rich: List of rich event dicts from context
            habit_uid: UID of habit to filter by

        Returns:
            List of Event domain models that reinforce the habit
        """
        result = []
        for event_data in events_rich:
            event_dict = event_data.get("event", {})
            if event_dict.get("reinforces_habit_uid") == habit_uid:
                event = self._dict_to_event(event_dict)
                if event:
                    result.append(event)
        return result

    def _filter_events_by_date_range(
        self,
        events_rich: list[dict[str, Any]],
        start_date: date,
        end_date: date,
        status_filter: str | None = None,
    ) -> list[Event]:
        """
        Filter rich event data by date range and optional status.

        Args:
            events_rich: List of rich event dicts from context
            start_date: Inclusive start date
            end_date: Inclusive end date
            status_filter: Optional status to filter by

        Returns:
            List of Event domain models in date range
        """
        result = []
        for event_data in events_rich:
            event_dict = event_data.get("event", {})
            event_date = parse_date_field(event_dict.get("event_date"))

            if event_date and start_date <= event_date <= end_date:
                if status_filter and event_dict.get("status") != status_filter:
                    continue
                event = self._dict_to_event(event_dict)
                if event:
                    result.append(event)
        return result

    def _dict_to_event(self, event_dict: dict[str, Any]) -> Event | None:
        """
        Convert raw Neo4j event dict to Event domain model.

        Args:
            event_dict: Dict with event properties from MEGA-QUERY

        Returns:
            Event domain model or None if conversion fails
        """
        if not event_dict or not event_dict.get("uid"):
            return None

        return Event(
            uid=event_dict.get("uid", ""),
            user_uid=event_dict.get("user_uid", ""),
            title=event_dict.get("title", ""),
            description=event_dict.get("description"),
            event_date=parse_date_field(event_dict.get("event_date")) or date.today(),
            start_time=self._parse_time_field(event_dict.get("start_time")),
            end_time=self._parse_time_field(event_dict.get("end_time")),
            # NOTE: duration_minutes is a computed property in Event, not a field
            event_type=event_dict.get("event_type", "PERSONAL"),  # String field
            status=parse_enum_field(
                event_dict.get("status"), ActivityStatus, ActivityStatus.SCHEDULED
            ),
            recurrence_pattern=parse_enum_field(
                event_dict.get("recurrence_pattern"), RecurrencePattern
            ),
            recurrence_end_date=parse_date_field(event_dict.get("recurrence_end_date")),
            reinforces_habit_uid=event_dict.get("reinforces_habit_uid"),
            # NOTE: Event uses 'milestone_celebration_for_goal' not 'fulfills_goal_uid'
            milestone_celebration_for_goal=event_dict.get(
                "milestone_celebration_for_goal", event_dict.get("fulfills_goal_uid")
            ),
            # NOTE: Event uses 'habit_completion_quality' not 'quality_score'
            habit_completion_quality=event_dict.get(
                "habit_completion_quality", event_dict.get("quality_score")
            ),
            # NOTE: energy_level, notes, completed_at not in Event model - store in metadata
            created_at=parse_datetime_field(event_dict.get("created_at")) or datetime.now(),
            updated_at=parse_datetime_field(event_dict.get("updated_at")) or datetime.now(),
            metadata=event_dict.get("metadata", {}),
        )

    def _parse_time_field(self, value: Any) -> time | None:
        """Parse a time value from Neo4j."""
        if value is None:
            return None
        if isinstance(value, time):
            return value
        if isinstance(value, str):
            return time.fromisoformat(value)
        return None

    def _filter_events_by_criteria(
        self,
        user_context: UserContext,
        criteria: EventFilterCriteria,
    ) -> list[Event] | dict[str, list[Event]] | dict[str, Event]:
        """
        Generic event filtering from rich context.

        Consolidates filtering logic from:
        - get_events_for_habit
        - get_habit_reinforcement_events
        - get_at_risk_habit_events
        - get_next_habit_events

        Args:
            user_context: User context with rich event data
            criteria: Filtering criteria

        Returns:
            - list[Event] when filtering without grouping
            - dict[str, list[Event]] when group_by_habit=True
            - dict[str, Event] when find_earliest_per_habit=True
        """
        events_rich = self._get_events_from_rich_context(user_context)
        if not events_rich:
            if criteria.group_by_habit or criteria.find_earliest_per_habit:
                return {}
            return []

        result_list: list[Event] = []
        by_habit: dict[str, list[Event]] = {}
        earliest_by_habit: dict[str, Event] = {}

        for event_data in events_rich:
            event_dict = event_data.get("event", {})

            # Filter by habit_uid
            event_habit_uid = event_dict.get("reinforces_habit_uid")
            if criteria.habit_uid and event_habit_uid != criteria.habit_uid:
                continue
            if criteria.require_habit and not event_habit_uid:
                continue

            # Filter by date range
            event_date = parse_date_field(event_dict.get("event_date"))
            if criteria.start_date and (not event_date or event_date < criteria.start_date):
                continue
            if criteria.end_date and (not event_date or event_date > criteria.end_date):
                continue

            # Filter by status
            if criteria.status_filter and event_dict.get("status") != criteria.status_filter:
                continue

            event = self._dict_to_event(event_dict)
            if not event:
                continue

            # Handle different output modes
            if criteria.find_earliest_per_habit and event_habit_uid:
                if (
                    event_habit_uid not in earliest_by_habit
                    or event.event_date < earliest_by_habit[event_habit_uid].event_date
                ):
                    earliest_by_habit[event_habit_uid] = event
            elif criteria.group_by_habit and event_habit_uid:
                by_habit.setdefault(event_habit_uid, []).append(event)
            else:
                result_list.append(event)

        if criteria.find_earliest_per_habit:
            return earliest_by_habit
        if criteria.group_by_habit:
            return by_habit
        return result_list

    # ========================================================================
    # HABIT-RELATED EVENT QUERIES
    # ========================================================================

    async def get_events_for_habit(
        self, habit_uid: str, user_context: UserContext, days_ahead: int = 7
    ) -> Result[list[Event]]:
        """
        Get all upcoming events that reinforce a specific habit.

        CONTEXT-FIRST: Checks UserContext.active_events_rich before Neo4j query.

        Args:
            habit_uid: UID of the habit,
            user_context: User context for filtering,
            days_ahead: Number of days to look ahead

        Returns:
            Result containing list of events
        """
        start_date = date.today()
        end_date = start_date + timedelta(days=days_ahead)

        # CONTEXT-FIRST: Try rich context before Neo4j
        criteria = EventFilterCriteria(
            habit_uid=habit_uid,
            start_date=start_date,
            end_date=end_date,
        )
        events = self._filter_events_by_criteria(user_context, criteria)
        if isinstance(events, list) and events:
            self.logger.debug(
                f"Context-first: Found {len(events)} events for habit {habit_uid} "
                f"from rich context (no Neo4j query)"
            )
            return Result.ok(events)

        # Fallback: Query Neo4j
        self.logger.debug(f"No rich context, querying Neo4j for habit {habit_uid} events")
        filters = {
            "reinforces_habit_uid": habit_uid,
            "user_uid": user_context.user_uid,
            "event_date__gte": start_date,
            "event_date__lte": end_date,
        }

        result = await self.backend.list(filters=filters)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Unpack tuple: backend.list() returns (events, total_count)
        events_list, _ = result.value
        return Result.ok(events_list)

    async def get_habit_reinforcement_events(
        self, user_context: UserContext, days_ahead: int = 7
    ) -> Result[dict[str, list[Event]]]:
        """
        Get all upcoming events grouped by habit they reinforce.

        CONTEXT-FIRST: Checks UserContext.active_events_rich before Neo4j query.

        Args:
            user_context: User context for filtering,
            days_ahead: Number of days to look ahead

        Returns:
            Result containing dict mapping habit_uid to list of events
        """
        start_date = date.today()
        end_date = start_date + timedelta(days=days_ahead)

        # CONTEXT-FIRST: Try rich context before Neo4j
        criteria = EventFilterCriteria(
            require_habit=True,
            start_date=start_date,
            end_date=end_date,
            group_by_habit=True,
        )
        events_by_habit = self._filter_events_by_criteria(user_context, criteria)
        if isinstance(events_by_habit, dict) and events_by_habit:
            self.logger.debug(
                f"Context-first: Found events for {len(events_by_habit)} habits "
                f"from rich context (no Neo4j query)"
            )
            return Result.ok(events_by_habit)

        # Fallback: Query Neo4j
        self.logger.debug("No rich context, querying Neo4j for habit reinforcement events")
        filters = {
            "user_uid": user_context.user_uid,
            "event_date__gte": start_date,
            "event_date__lte": end_date,
        }

        result = await self.backend.list(filters=filters)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Unpack tuple: backend.list() returns (events, total_count)
        events, _ = result.value

        # Group by habit
        events_by_habit_fallback: dict[str, list[Event]] = {}
        for event in events:
            if event.reinforces_habit_uid:
                events_by_habit_fallback.setdefault(event.reinforces_habit_uid, []).append(event)

        return Result.ok(events_by_habit_fallback)

    async def get_at_risk_habit_events(
        self, user_context: UserContext, risk_threshold_days: int = 3
    ) -> Result[list[Event]]:
        """
        Get events for habits that are at risk of breaking their streaks.

        CONTEXT-FIRST: Checks UserContext.active_events_rich before Neo4j query.

        Args:
            user_context: User context,
            risk_threshold_days: Days until habit is at risk

        Returns:
            Result containing list of events for at-risk habits
        """
        start_date = date.today()
        end_date = start_date + timedelta(days=risk_threshold_days)

        # CONTEXT-FIRST: Try rich context before Neo4j
        criteria = EventFilterCriteria(
            require_habit=True,
            start_date=start_date,
            end_date=end_date,
            status_filter="scheduled",
        )
        events = self._filter_events_by_criteria(user_context, criteria)
        if isinstance(events, list) and events:
            self.logger.debug(
                f"Context-first: Found {len(events)} at-risk habit events "
                f"from rich context (no Neo4j query)"
            )
            return Result.ok(events)

        # Fallback: Query Neo4j
        self.logger.debug("No rich context, querying Neo4j for at-risk habit events")
        filters = {
            "user_uid": user_context.user_uid,
            "event_date__gte": start_date,
            "event_date__lte": end_date,
            "status": "scheduled",
        }

        result = await self.backend.list(filters=filters)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Unpack tuple: backend.list() returns (events, total_count)
        events_list, _ = result.value

        # Filter events that reinforce habits
        habit_events = [event for event in events_list if event.reinforces_habit_uid]

        return Result.ok(habit_events)

    # ========================================================================
    # HABIT-AWARE EVENT COMPLETION
    # ========================================================================

    async def complete_event_with_quality(
        self,
        event_uid: str,
        user_context: UserContext,
        quality_score: int = 4,
        completion_date: date | None = None,
    ) -> Result[Event]:
        """
        Complete an event and track habit quality if it reinforces a habit.

        Args:
            event_uid: UID of the event,
            user_context: User context,
            quality_score: Quality rating (1-5),
            completion_date: Date completed (defaults to today)

        Returns:
            Result containing updated event
        """
        # Get the event
        result = await self.backend.get_event(event_uid)
        if result.is_error:
            return Result.fail(result.expect_error())

        if not result.value:
            return Result.fail(Errors.not_found(resource="Event", identifier=event_uid))

        event = to_domain_model(result.value, EventDTO, Event)

        # Update event
        updates = {
            "status": "completed",
            "completed_at": completion_date or date.today(),
            "quality_score": quality_score,
        }

        update_result = await self.backend.update_event(event_uid, updates)
        if update_result.is_error:
            return Result.fail(update_result.expect_error())

        # Publish CalendarEventCompleted event (event-driven architecture)
        from core.events import CalendarEventCompleted

        event_obj = CalendarEventCompleted(
            event_uid=event_uid,
            user_uid=user_context.user_uid,
            completion_date=completion_date or date.today(),
            quality_score=quality_score,
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event_obj, self.logger)

        # If event reinforces habit, cascade effects happen via events
        if event.reinforces_habit_uid:
            self.logger.info(
                f"Event {event_uid} reinforces habit {event.reinforces_habit_uid}, "
                f"quality={quality_score}"
            )
            # Cascade effects handled by CalendarEventCompleted event → habit service

        # Fetch and return updated event
        updated_result = await self.backend.get_event(event_uid)
        if updated_result.is_error:
            return Result.fail(updated_result.expect_error())

        updated_event = to_domain_model(updated_result.value, EventDTO, Event)
        return Result.ok(updated_event)

    async def miss_habit_event(
        self, event_uid: str, user_context: UserContext, reason: str | None = None
    ) -> Result[Event]:
        """
        Mark a habit-reinforcing event as missed.

        Args:
            event_uid: UID of the event,
            user_context: User context,
            reason: Optional reason for missing

        Returns:
            Result containing updated event
        """
        updates = {"status": "cancelled", "notes": f"Missed: {reason}" if reason else "Missed"}

        result = await self.backend.update_event(event_uid, updates)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Publish CalendarEventUpdated event (event-driven architecture)
        from core.events import CalendarEventUpdated

        event_obj = CalendarEventUpdated(
            event_uid=event_uid,
            user_uid=user_context.user_uid,
            updated_fields={"status": "cancelled", "notes": updates["notes"]},
            occurred_at=datetime.now(),
        )
        await publish_event(self.event_bus, event_obj, self.logger)

        self.logger.warning(f"Habit event {event_uid} marked as missed")

        # Fetch and return updated event
        updated_result = await self.backend.get_event(event_uid)
        if updated_result.is_error:
            return Result.fail(updated_result.expect_error())

        updated_event = to_domain_model(updated_result.value, EventDTO, Event)
        return Result.ok(updated_event)

    # ========================================================================
    # RECURRING EVENT CREATION
    # ========================================================================

    async def create_recurring_events_for_habit(
        self,
        habit_uid: str,
        user_context: UserContext,
        pattern: RecurrencePattern,
        duration_minutes: int = 30,
        days_to_create: int = 30,
        title: str | None = None,
    ) -> Result[list[Event]]:
        """
        Create recurring events to reinforce a habit.

        Args:
            habit_uid: UID of the habit,
            user_context: User context,
            pattern: Recurrence pattern (DAILY, WEEKLY, etc.),
            duration_minutes: Duration of each event,
            days_to_create: Number of days to create events for,
            title: Optional custom title

        Returns:
            Result containing list of created events
        """
        events = []
        current_date = date.today()
        end_date = current_date + timedelta(days=days_to_create)

        # Calculate interval based on pattern
        interval_days = {
            RecurrencePattern.DAILY: 1,
            RecurrencePattern.WEEKLY: 7,
            RecurrencePattern.BIWEEKLY: 14,
            RecurrencePattern.MONTHLY: 30,
        }.get(pattern, 1)

        # Create events
        while current_date <= end_date:
            event_data = {
                "user_uid": user_context.user_uid,
                "title": title or f"Practice: {habit_uid}",
                "event_date": current_date,
                "duration_minutes": duration_minutes,
                "reinforces_habit_uid": habit_uid,
                "status": "scheduled",
                "recurrence_pattern": pattern.value,
            }

            result = await self.backend.create_event(event_data)
            if result.is_error:
                self.logger.error(f"Failed to create recurring event: {result.error}")
                continue

            event = to_domain_model(result.value, EventDTO, Event)
            events.append(event)

            # Publish CalendarEventCreated event (event-driven architecture)
            from core.events import CalendarEventCreated
            from core.services.protocols import get_enum_value

            event_obj = CalendarEventCreated(
                event_uid=event.uid,
                user_uid=user_context.user_uid,
                title=event.title,
                event_date=event.event_date,
                calendar_event_type=get_enum_value(event.event_type),
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, event_obj, self.logger)

            current_date += timedelta(days=interval_days)

        self.logger.info(f"Created {len(events)} recurring events for habit {habit_uid}")
        return Result.ok(events)

    async def get_next_habit_events(
        self, user_context: UserContext
    ) -> Result[dict[str, Event | None]]:
        """
        Get the next scheduled event for each active habit.

        CONTEXT-FIRST: Checks UserContext.active_events_rich before Neo4j query.

        Args:
            user_context: User context

        Returns:
            Result containing dict mapping habit_uid to next event (or None)
        """
        today = date.today()

        # CONTEXT-FIRST: Try rich context before Neo4j
        criteria = EventFilterCriteria(
            require_habit=True,
            start_date=today,
            status_filter="scheduled",
            find_earliest_per_habit=True,
        )
        next_events = self._filter_events_by_criteria(user_context, criteria)
        if isinstance(next_events, dict) and next_events:
            self.logger.debug(
                f"Context-first: Found next events for {len(next_events)} habits "
                f"from rich context (no Neo4j query)"
            )
            return Result.ok(next_events)

        # Fallback: Query Neo4j
        self.logger.debug("No rich context, querying Neo4j for next habit events")
        filters = {
            "user_uid": user_context.user_uid,
            "event_date__gte": today,
            "status": "scheduled",
        }

        result = await self.backend.list(filters=filters)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Unpack tuple: backend.list() returns (events, total_count)
        events, _ = result.value

        # Find next event for each habit
        next_events_fallback: dict[str, Event] = {}
        for event in events:
            if not event.reinforces_habit_uid:
                continue

            habit_uid = event.reinforces_habit_uid

            # Track earliest event for each habit
            if (
                habit_uid not in next_events_fallback
                or event.event_date < next_events_fallback[habit_uid].event_date
            ):
                next_events_fallback[habit_uid] = event

        return Result.ok(next_events_fallback)
