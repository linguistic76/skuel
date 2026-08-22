"""
Event Search Service - Search and Discovery Operations
=======================================================

Handles search and discovery operations for calendar events.
Implements DomainSearchOperations[Event] protocol plus event-specific methods.

**Responsibilities:**
- Text search on title/description
- Filter by status, domain, event type
- Date range queries (in range, upcoming, past)
- Context-aware prioritization
- Graph-based relationship queries
- Recurring event discovery
- Conflict detection

**Pattern:**
This service follows the SearchService pattern documented in:
/docs/patterns/search_service_pattern.md
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from core.models.type_hints import UserUID

if TYPE_CHECKING:
    from core.ports.domain_protocols import EventsOperations

from core.models.enums import EntityStatus
from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.models.relationship_names import RelationshipName
from core.models.search.scoring import score_event
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.events._goal_links import enrich_events_with_goal_links
from core.services.events._habit_links import enrich_events_with_habit_links
from core.services.user import UserContext
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Result
from core.utils.sort_functions import get_result_score


class EventsSearchService(BaseService["EventsOperations", Event]):
    """
    Event search and discovery operations.

    Implements DomainSearchOperations[Event] protocol for consistent
    search interface across all activity domains.

    Universal Methods (DomainSearchOperations protocol):
    - search() - Text search on title/description (inherited from BaseService)
    - get_by_status() - Filter by EntityStatus
    - get_prioritized() - Context-aware prioritization
    - get_by_relationship() - Graph relationship queries
    - get_upcoming() - Events within N days
    - get_overdue() - Past events not completed

    Event-Specific Methods:
    - get_in_range() - Events within date range
    - get_recurring() - Recurring events only
    - get_for_goal() - Events supporting a goal
    - get_conflicting() - Events with time conflicts
    - get_by_type() - Filter by event type
    - get_upcoming() - Future events
    - get_history() - Past completed events

    Semantic Types Used:
    - SUPPORTS_GOAL: Event supports goal achievement
    - REINFORCES_HABIT: Event reinforces habit practice
    - APPLIES_KNOWLEDGE: Event applies knowledge unit practically
    - SCHEDULED_FOR: Event scheduled for user
    """

    # DomainConfig consolidation (January 2026)
    # All configuration in one place, using centralized relationship registry
    # See: /docs/decisions/ADR-025-service-consolidation-patterns.md
    _config = create_activity_domain_config(
        dto_class=EventDTO,
        model_class=Event,
        entity_label="Entity",
        domain_name="events",
        date_field="event_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
        search_order_by="event_date",  # Events ordered by event date, not created_at
        temporal_secondary_sort="start_time",
    )

    def __init__(self, backend: EventsOperations) -> None:
        """Initialize service with required backend."""
        super().__init__(backend=backend, service_name="events.search")

    # Inherited from BaseService (December 2025):
    # - search(), get_by_status(), get_by_category(),
    # - list_categories(), get_by_relationship()

    # ========================================================================
    # DOMAIN SEARCH OPERATIONS PROTOCOL IMPLEMENTATION
    # ========================================================================
    # Inherited from BaseService: search(), get_by_status(),
    # get_by_category(), list_categories(), get_by_relationship()

    @with_error_handling("get_prioritized", error_type="database")
    async def get_prioritized(
        self, user_context: UserContext, limit: int = 10
    ) -> Result[list[Event]]:
        """
        Get events prioritized for the user's current context.

        Uses UserContext to determine relevance:
        - Upcoming events (sooner = higher priority)
        - Goal alignment
        - Habit reinforcement
        - Learning path support

        Args:
            user_context: User's current context (~240 fields)
            limit: Maximum results to return

        Returns:
            Result containing events sorted by priority/relevance
        """
        today = date.today()
        end_date = today + timedelta(days=14)  # Next 2 weeks

        # Get user's upcoming events
        result = await self.backend.find_by(
            user_uid=user_context.user_uid,
            event_date__gte=today.isoformat(),
            event_date__lte=end_date.isoformat(),
        )
        if result.is_error:
            return result

        all_events = self._to_domain_models(result.value, EventDTO, Event)

        active_events = [
            e
            for e in all_events
            if not e.status
            or e.status.value
            not in {
                EntityStatus.COMPLETED.value,
                EntityStatus.CANCELLED.value,
            }
        ]

        # Populate the derived reinforces_habit_uid from the REINFORCES_HABIT edge
        # so the streak-protection scorer can read it (graph is source of truth).
        active_events = await enrich_events_with_habit_links(self.backend, active_events)
        # Populate the derived contributes_to_goal_uid from the CONTRIBUTES_TO_GOAL edge
        # so the goal-alignment scorer can read it (graph is source of truth).
        # Pass active_goal_uids so multi-goal events prefer the active goal.
        active_events = await enrich_events_with_goal_links(
            self.backend, active_events, user_context.active_goal_uids
        )

        scored_events = [(event, score_event(event, user_context).total) for event in active_events]
        scored_events.sort(key=get_result_score, reverse=True)

        prioritized = [event for event, _ in scored_events[:limit]]

        self.logger.info(f"Prioritized {len(prioritized)} events for user {user_context.user_uid}")
        return Result.ok(prioritized)

    # get_by_relationship() - inherited from BaseService using _dto_class, _model_class
    # get_upcoming(), get_overdue(), get_active() - inherited from TimeQueryMixin via DomainConfig

    # ========================================================================
    # EVENT-SPECIFIC SEARCH METHODS
    # ========================================================================

    @with_error_handling("get_in_range", error_type="database")
    async def get_in_range(
        self,
        start_date: date,
        end_date: date,
        user_uid: UserUID | None = None,
        limit: int = 100,
    ) -> Result[list[Event]]:
        """
        Get events within a date range.

        Args:
            start_date: Start of date range
            end_date: End of date range
            user_uid: Optional user filter
            limit: Maximum results

        Returns:
            Result containing events in range
        """
        result = await self.backend.get_events_in_range(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            user_uid=user_uid,
            limit=limit,
        )
        if result.is_error:
            return Result.fail(result)

        events = self._to_domain_models(result.value, EventDTO, Event)

        self.logger.debug(f"Found {len(events)} events between {start_date} and {end_date}")
        return Result.ok(events)

    @with_error_handling("get_recurring", error_type="database")
    async def get_recurring(
        self, user_uid: UserUID | None = None, limit: int = 100
    ) -> Result[list[Event]]:
        """
        Get recurring events.

        Args:
            user_uid: Optional user filter
            limit: Maximum results

        Returns:
            Result containing recurring events
        """
        result = await self.backend.get_recurring_events(user_uid=user_uid, limit=limit)
        if result.is_error:
            return Result.fail(result)

        events = self._to_domain_models(result.value, EventDTO, Event)

        self.logger.debug(f"Found {len(events)} recurring events")
        return Result.ok(events)

    @with_error_handling("get_for_goal", error_type="database", uid_param="goal_uid")
    async def get_for_goal(
        self, goal_uid: str, user_uid: UserUID | None = None
    ) -> Result[list[Event]]:
        """
        Get events that support a specific goal.

        Query: (Event)-[:SUPPORTS_GOAL]->(Goal)

        Args:
            goal_uid: Goal UID
            user_uid: Optional user filter

        Returns:
            Result containing events supporting the goal
        """
        # Ownership scoping rides in the traversal query itself (ADR-085 G3) —
        # the former Python post-filter is gone with it.
        events_result = await self.get_by_relationship(
            related_uid=goal_uid,
            relationship_type=RelationshipName.SUPPORTS_GOAL,
            direction="incoming",
            user_uid=user_uid,
        )
        if events_result.is_error:
            return events_result

        events = events_result.value

        self.logger.debug(f"Found {len(events)} events supporting goal {goal_uid}")
        return Result.ok(events)

    @with_error_handling("get_conflicting", error_type="database", uid_param="event_uid")
    async def get_conflicting(self, event_uid: str) -> Result[list[Event]]:
        """
        Get events that conflict with a given event.

        Two events conflict if they overlap in time on the same date.

        Args:
            event_uid: Event UID to check conflicts for

        Returns:
            Result containing conflicting events
        """
        # First get the target event
        event_result = await self.backend.get(event_uid)
        if event_result.is_error:
            return Result.fail(event_result)

        event = self._to_domain_model(event_result.value, EventDTO, Event)

        if not event.event_date:
            return Result.ok([])  # No date = no conflicts

        result = await self.backend.get_events_on_date(
            event_date=event.event_date.isoformat(),
            user_uid=event.user_uid,
            exclude_uid=event_uid,
        )
        if result.is_error:
            return Result.fail(result)

        # Convert and check for time overlap
        conflicts = []
        for event_node in result.value:
            dto = EventDTO.from_dict(dict(event_node))
            other_event = Event.from_dto(dto)

            # Check time overlap if both have times
            if (
                event.start_time
                and event.end_time
                and other_event.start_time
                and other_event.end_time
            ):
                # Events overlap if one starts before the other ends
                if (
                    event.start_time < other_event.end_time
                    and event.end_time > other_event.start_time
                ):
                    conflicts.append(other_event)
            else:
                # No times = consider potential conflict
                conflicts.append(other_event)

        self.logger.debug(f"Found {len(conflicts)} conflicting events for {event_uid}")
        return Result.ok(conflicts)

    # get_upcoming() inherited from TimeQueryMixin — uses event_date field via DomainConfig.
    # Default signature: get_upcoming(days_ahead=7, user_uid=None, limit=100).

    @with_error_handling("get_for_habit", error_type="database", uid_param="habit_uid")
    async def get_for_habit(
        self, habit_uid: str, user_uid: UserUID | None = None
    ) -> Result[list[Event]]:
        """
        Get events that reinforce a specific habit.

        Query: (Event)-[:REINFORCES_HABIT]->(Habit)

        Args:
            habit_uid: Habit UID
            user_uid: Optional user filter

        Returns:
            Result containing events reinforcing the habit
        """
        # Ownership scoping rides in the traversal query itself (ADR-085 G3) —
        # the former Python post-filter is gone with it.
        events_result = await self.get_by_relationship(
            related_uid=habit_uid,
            relationship_type=RelationshipName.REINFORCES_HABIT,
            direction="incoming",
            user_uid=user_uid,
        )
        if events_result.is_error:
            return events_result

        events = events_result.value

        self.logger.debug(f"Found {len(events)} events reinforcing habit {habit_uid}")
        return Result.ok(events)

    @with_error_handling("get_calendar_events", error_type="database", uid_param="user_uid")
    async def get_calendar_events(
        self,
        user_uid: UserUID,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
    ) -> Result[list[Event]]:
        """
        Get events for calendar display.

        Args:
            user_uid: User identifier
            start_date: Optional start date filter
            end_date: Optional end date filter
            limit: Maximum results

        Returns:
            Result with list of events
        """
        # Default to current month if no dates specified
        if not start_date:
            today = date.today()
            start_date = today.replace(day=1)
        if not end_date:
            # Last day of month
            if start_date.month == 12:
                end_date = start_date.replace(year=start_date.year + 1, month=1, day=1) - timedelta(
                    days=1
                )
            else:
                end_date = start_date.replace(month=start_date.month + 1, day=1) - timedelta(days=1)

        return await self.get_in_range(
            start_date=start_date,
            end_date=end_date,
            user_uid=user_uid,
            limit=limit,
        )

    # ========================================================================
    # GRAPH-AWARE FACETED SEARCH
    # ========================================================================
    # graph_aware_faceted_search() is inherited from BaseService (January 2026)
    # Configured via _graph_enrichment_patterns class attribute above
    # See: BaseService.graph_aware_faceted_search() for implementation

    # ========================================================================
    # INTELLIGENT SEARCH
    # ========================================================================
