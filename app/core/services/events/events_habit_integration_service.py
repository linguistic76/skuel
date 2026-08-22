"""
Events Habit Integration Service
=================================

Handles cross-domain habits integration FROM the Events perspective.

Responsibilities:
- Get events that reinforce specific habits
- Complete events with habit quality tracking
- Create recurring events for habit reinforcement
- Handle habit-event cascade effects

Complementary to HabitsIntelligenceService (which provides event scheduling
intelligence FROM the Habits perspective). This service manages actual Event
entities and their habit-related lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, cast

from core.events import publish_event
from core.models.enums import EventType, RecurrencePattern
from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.models.relationship_names import RelationshipName
from core.models.type_hints import FilterParams, Neo4jProperties
from core.services.events._habit_links import enrich_events_with_habit_links
from core.services.user import UserContext
from core.services.user.rich_context import rich_entity_to_model
from core.utils.dto_converters import to_domain_model
from core.utils.logging import get_logger
from core.utils.result_simplified import Result
from core.utils.timestamp_helpers import parse_date_value

if TYPE_CHECKING:
    from core.ports.domain_protocols import EventsOperations
    from core.ports.query_types import RichEntityItem


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
    - Marking habit events as missed
    - Creating recurring events for habits
    - Managing habit-event relationships
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
    # Philosophy: "Check UserContext.entities_rich["events"] BEFORE querying Neo4j"
    #
    # UserContext is THE source of truth for user state.
    # MEGA-QUERY already fetched events with graph context - reuse that data!
    #
    # Benefits:
    # - Zero queries when data is in rich context
    # - Single source of truth (UserContext)
    # - Consistent with Tasks, Habits, Goals progress services
    # ========================================================================

    def _get_events_from_rich_context(self, user_context: UserContext) -> list[RichEntityItem]:
        """
        Get all events from UserContext rich data.

        Returns list of raw event dicts from MEGA-QUERY.
        Each dict contains: {entity: {...}, graph_context: {...}}

        Returns:
            List of event data dicts (may be empty if no rich context)
        """
        return user_context.entities_rich.get("events", [])

    @staticmethod
    def _reinforced_habit_uid(event_data: RichEntityItem) -> str | None:
        """Extract the reinforced habit uid from a rich event's graph context.

        Graph-native: reads ``graph_context.reinforced_habits`` (loaded from the
        (Event)-[:REINFORCES_HABIT]->(Habit) edge by the MEGA-QUERY) rather than a
        property. An event reinforces at most one habit, so returns the first.
        """
        graph_ctx = event_data.get("graph_context", {}) or {}
        reinforced = graph_ctx.get("reinforced_habits") or []
        if reinforced and isinstance(reinforced[0], dict):
            return reinforced[0].get("uid")
        return None

    def _dict_to_event(self, event_dict: dict[str, Any]) -> Event | None:
        """Convert a raw rich-context event dict to an Event domain model."""
        return rich_entity_to_model(event_dict, EventDTO, Event)

    async def _enrich_with_habit_links(self, events: list[Event]) -> list[Event]:
        """Populate the derived ``reinforces_habit_uid`` from REINFORCES_HABIT edges.

        Used on fallback (non-rich-context) paths where events come from a plain
        backend query that doesn't load the edge.
        """
        return await enrich_events_with_habit_links(self.backend, events)

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
            event_dict = event_data.get("entity", {})

            # Filter by habit_uid (graph-native: from REINFORCES_HABIT edge context)
            event_habit_uid = self._reinforced_habit_uid(event_data)
            if criteria.habit_uid and event_habit_uid != criteria.habit_uid:
                continue
            if criteria.require_habit and not event_habit_uid:
                continue

            # Filter by date range
            event_date = parse_date_value(event_dict.get("event_date"))
            if criteria.start_date and (not event_date or event_date < criteria.start_date):
                continue
            if criteria.end_date and (not event_date or event_date > criteria.end_date):
                continue

            # Filter by status
            if criteria.status_filter and event_dict.get("status") != criteria.status_filter:
                continue

            built = self._dict_to_event(event_dict)
            if not built:
                continue
            # Populate the derived field from the graph-context habit link.
            event = replace(built, reinforces_habit_uid=event_habit_uid)

            # Handle different output modes
            if criteria.find_earliest_per_habit and event_habit_uid:
                existing_date = earliest_by_habit.get(event_habit_uid)
                if existing_date is None or (
                    event.event_date is not None
                    and (
                        existing_date.event_date is None
                        or event.event_date < existing_date.event_date
                    )
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

        CONTEXT-FIRST: Checks UserContext.entities_rich["events"] before Neo4j query.

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

        # Fallback: graph traversal of (Event)-[:REINFORCES_HABIT]->(Habit)
        self.logger.debug(f"No rich context, querying Neo4j for habit {habit_uid} events")
        result = await self.backend.get_events_reinforcing_habit(habit_uid, user_context.user_uid)
        if result.is_error:
            return Result.fail(result)

        events_list: list[Event] = []
        for event_dict in result.value:
            event = self._dict_to_event(event_dict)
            if not event or not event.event_date:
                continue
            if start_date <= event.event_date <= end_date:
                events_list.append(replace(event, reinforces_habit_uid=habit_uid))
        return Result.ok(events_list)

    async def get_habit_reinforcement_events(
        self, user_context: UserContext, days_ahead: int = 7
    ) -> Result[dict[str, list[Event]]]:
        """
        Get all upcoming events grouped by habit they reinforce.

        CONTEXT-FIRST: Checks UserContext.entities_rich["events"] before Neo4j query.

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
            # criteria.group_by_habit=True -> dict[str, list[Event]] variant
            return Result.ok(cast("dict[str, list[Event]]", events_by_habit))

        # Fallback: Query Neo4j
        self.logger.debug("No rich context, querying Neo4j for habit reinforcement events")
        filters: FilterParams = {
            "user_uid": user_context.user_uid,
            "event_date__gte": start_date.isoformat(),
            "event_date__lte": end_date.isoformat(),
        }

        result = await self.backend.list(filters=filters)
        if result.is_error:
            return Result.fail(result)

        # Unpack tuple: backend.list() returns (events, total_count)
        events, _ = result.value
        # Enrich with habit links from the REINFORCES_HABIT edge (derived field).
        events = await self._enrich_with_habit_links(events)

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

        CONTEXT-FIRST: Checks UserContext.entities_rich["events"] before Neo4j query.

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
        filters: FilterParams = {
            "user_uid": user_context.user_uid,
            "event_date__gte": start_date.isoformat(),
            "event_date__lte": end_date.isoformat(),
            "status": "scheduled",
        }

        result = await self.backend.list(filters=filters)
        if result.is_error:
            return Result.fail(result)

        # Unpack tuple: backend.list() returns (events, total_count)
        events_list, _ = result.value
        # Enrich with habit links from the REINFORCES_HABIT edge (derived field).
        events_list = await self._enrich_with_habit_links(events_list)

        # Filter events that reinforce habits
        habit_events = [event for event in events_list if event.reinforces_habit_uid]

        return Result.ok(habit_events)

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
        updates: Neo4jProperties = {
            "status": "cancelled",
            "notes": f"Missed: {reason}" if reason else "Missed",
        }

        # raw-write: miss-habit-event writes directly to the backend, bypassing the
        # validated/event-firing contract (EventUpdateIntent → update_event) on purpose —
        # this path publishes its OWN CalendarEventUpdated below with the miss provenance
        # (status=cancelled + notes). Routing through the contract would double-fire
        # CalendarEventUpdated, and `notes` is not an Event column the intent carries.
        result = await self.backend.update(event_uid, updates)
        if result.is_error:
            return Result.fail(result)

        # Publish CalendarEventUpdated event (event-driven architecture)
        from core.events import CalendarEventUpdated

        event_obj = CalendarEventUpdated(
            event_uid=event_uid,
            user_uid=user_context.user_uid,
            updated_fields={"status": "cancelled", "notes": updates["notes"]},
        )
        await publish_event(self.event_bus, event_obj, self.logger)

        self.logger.warning(f"Habit event {event_uid} marked as missed")

        # Fetch and return updated event
        updated_result = await self.backend.get(event_uid)
        if updated_result.is_error:
            return Result.fail(updated_result)

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
                "status": "scheduled",
                "recurrence_pattern": pattern.value,
            }

            result = await self.backend.create(Event.from_dto(EventDTO.from_dict(event_data)))
            if result.is_error:
                self.logger.error(f"Failed to create recurring event: {result.error}")
                continue

            event = to_domain_model(result.value, EventDTO, Event)
            events.append(event)
            # Habit reinforcement is a graph edge, not a property.
            await self.backend.create_relationship(
                event.uid, habit_uid, RelationshipName.REINFORCES_HABIT
            )

            # Publish CalendarEventCreated event (event-driven architecture)
            from core.events import CalendarEventCreated

            event_obj = CalendarEventCreated(
                event_uid=event.uid,
                user_uid=user_context.user_uid,
                title=event.title,
                event_date=event.event_date or date.today(),
                # event_data above sets no event_type, so Event.event_type is
                # None here — publish a canonical EventType member rather than
                # None (the field is declared str) or a raw literal. PERSONAL
                # because a habit practice session is the user's own event and
                # EventType has no RECURRING member.
                calendar_event_type=event.event_type or EventType.PERSONAL,
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

        CONTEXT-FIRST: Checks UserContext.entities_rich["events"] before Neo4j query.

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
            # criteria.find_earliest_per_habit=True -> dict[str, Event] variant;
            # widen to Event | None for the public contract.
            return Result.ok(cast("dict[str, Event | None]", next_events))

        # Fallback: Query Neo4j
        self.logger.debug("No rich context, querying Neo4j for next habit events")
        filters: FilterParams = {
            "user_uid": user_context.user_uid,
            "event_date__gte": today.isoformat(),
            "status": "scheduled",
        }

        result = await self.backend.list(filters=filters)
        if result.is_error:
            return Result.fail(result)

        # Unpack tuple: backend.list() returns (events, total_count)
        events, _ = result.value
        # Enrich with habit links from the REINFORCES_HABIT edge (derived field).
        events = await self._enrich_with_habit_links(events)

        # Find next event for each habit
        next_events_fallback: dict[str, Event] = {}
        for event in events:
            if not event.reinforces_habit_uid:
                continue

            habit_uid = event.reinforces_habit_uid

            # Track earliest event for each habit
            existing_event = next_events_fallback.get(habit_uid)
            if existing_event is None or (
                event.event_date is not None
                and (
                    existing_event.event_date is None
                    or event.event_date < existing_event.event_date
                )
            ):
                next_events_fallback[habit_uid] = event

        # Widen to match the Result[dict[str, Event | None]] public contract
        # (our local dict only ever contains Event values, never None).
        return Result.ok(cast("dict[str, Event | None]", next_events_fallback))
