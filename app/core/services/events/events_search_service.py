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

Version: 1.0.0
Date: 2025-11-28

Changelog:
- v1.0.0 (2025-11-28): Initial implementation
  Implements DomainSearchOperations[Event] protocol
"""

from datetime import date, timedelta

from core.models.event.event import Event
from core.models.event.event_dto import EventDTO
from core.models.relationship_names import RelationshipName
from core.models.search.query_parser import ParsedSearchQuery, SearchQueryParser
from core.models.enums import ActivityStatus
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.services.protocols.domain_protocols import EventsOperations
from core.services.user import UserContext
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Result
from core.utils.sort_functions import get_result_score


class EventsSearchService(BaseService[EventsOperations, Event]):
    """
    Event search and discovery operations.

    Implements DomainSearchOperations[Event] protocol for consistent
    search interface across all activity domains.

    Universal Methods (DomainSearchOperations protocol):
    - search() - Text search on title/description (inherited from BaseService)
    - get_by_status() - Filter by ActivityStatus
    - get_by_domain() - Filter by Domain enum
    - get_prioritized() - Context-aware prioritization
    - get_by_relationship() - Graph relationship queries
    - get_due_soon() - Events within N days
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

    Source Tag: "events_search_explicit"
    - Format: "events_search_explicit" for user-defined relationships
    - Format: "events_search_inferred" for system-discovered relationships

    Confidence Scoring:
    - 0.9+: User explicitly linked event to goal/habit
    - 0.7-0.9: Inferred from domain/type alignment
    - <0.7: Suggested based on scheduling patterns

    SKUEL Architecture:
    - Uses CypherGenerator for graph queries
    - Returns Result[T] for error handling
    - Logs operations with structured logging
    """

    # DomainConfig consolidation (January 2026 Phase 3)
    # All configuration in one place, using centralized relationship registry
    # See: /docs/decisions/ADR-025-service-consolidation-patterns.md
    _config = create_activity_domain_config(
        dto_class=EventDTO,
        model_class=Event,
        domain_name="events",
        date_field="event_date",
        completed_statuses=(ActivityStatus.COMPLETED.value,),
        search_order_by="event_date",  # Events ordered by event date, not created_at
    )

    # Inherited from BaseService (December 2025):
    # - search(), get_by_status(), get_by_domain(), get_by_category(),
    # - list_categories(), get_by_relationship()

    # ========================================================================
    # DOMAIN SEARCH OPERATIONS PROTOCOL IMPLEMENTATION
    # ========================================================================
    # Inherited from BaseService: search(), get_by_status(), get_by_domain(),
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

        # Filter out completed/cancelled
        active_events = [
            e
            for e in all_events
            if not e.status
            or e.status.value
            not in {
                ActivityStatus.COMPLETED.value,
                ActivityStatus.CANCELLED.value,
            }
        ]

        # Score and sort by priority factors
        scored_events = []
        for event in active_events:
            score = self._calculate_priority_score(event, user_context)
            scored_events.append((event, score))

        # Sort by score descending
        scored_events.sort(key=get_result_score, reverse=True)

        # Return top N
        prioritized = [event for event, _ in scored_events[:limit]]

        self.logger.info(f"Prioritized {len(prioritized)} events for user {user_context.user_uid}")
        return Result.ok(prioritized)

    def _calculate_priority_score(self, event: Event, user_context: UserContext) -> float:
        """
        Calculate priority score for an event based on user context.

        Factors:
        - Time proximity (sooner = higher)
        - Goal support (supporting active goals)
        - Habit reinforcement (maintaining streaks)
        - Learning alignment
        """
        score = 0.0
        today = date.today()

        # Time proximity (0-40 points)
        if event.event_date:
            days_until = (event.event_date - today).days
            if days_until <= 0:
                score += 40  # Today or overdue
            elif days_until == 1:
                score += 35  # Tomorrow
            elif days_until <= 3:
                score += 30
            elif days_until <= 7:
                score += 20
            else:
                score += 10

        # Goal support (0-25 points) - use milestone_celebration_for_goal field
        # Note: supports_goal_uid is graph-native (SUPPORTS_GOAL relationship)
        if event.milestone_celebration_for_goal and user_context.active_goal_uids:
            if event.milestone_celebration_for_goal in user_context.active_goal_uids:
                score += 25

        # Habit reinforcement (0-25 points)
        if event.reinforces_habit_uid:
            habit_streaks = user_context.habit_streaks or {}
            streak = habit_streaks.get(event.reinforces_habit_uid, 0)
            if streak > 0:
                score += 25  # Protecting an active streak
            elif event.reinforces_habit_uid in user_context.active_habit_uids:
                score += 15  # Supporting active habit

        # Event type priority (0-10 points)
        if event.event_type:
            from core.services.protocols import get_enum_value

            event_type = get_enum_value(event.event_type)
            # Learning events get slight priority
            if event_type in {"study", "learning", "practice"}:
                score += 10

        return score

    # get_by_relationship() - inherited from BaseService using _dto_class, _model_class

    @with_error_handling("get_due_soon", error_type="database")
    async def get_due_soon(
        self,
        days_ahead: int = 7,
        user_uid: str | None = None,
        limit: int = 100,
    ) -> Result[list[Event]]:
        """
        Get events within specified number of days.

        Args:
            days_ahead: Number of days to look ahead (default 7)
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing upcoming events, sorted by date
        """
        today = date.today()
        end_date = today + timedelta(days=days_ahead)

        # Build query with optional user filter
        user_clause = "AND e.user_uid = $user_uid" if user_uid else ""
        cypher_query = f"""
        MATCH (e:Event)
        WHERE e.event_date >= date($today)
          AND e.event_date <= date($end_date)
          AND e.status NOT IN ['completed', 'cancelled']
          {user_clause}
        RETURN e
        ORDER BY e.event_date ASC, e.start_time ASC
        LIMIT $limit
        """

        params: dict[str, str | int] = {
            "today": today.isoformat(),
            "end_date": end_date.isoformat(),
            "limit": limit,
        }
        if user_uid:
            params["user_uid"] = user_uid

        result = await self.backend.execute_query(cypher_query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to Events using inherited helper
        events = self._to_domain_models([record["e"] for record in result.value], EventDTO, Event)

        self.logger.debug(f"Found {len(events)} events within {days_ahead} days")
        return Result.ok(events)

    @with_error_handling("get_overdue", error_type="database")
    async def get_overdue(
        self,
        user_uid: str | None = None,
        limit: int = 100,
    ) -> Result[list[Event]]:
        """
        Get events that are past their date and not completed.

        Args:
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing overdue events
        """
        today = date.today()

        # Build query with optional user filter
        user_clause = "AND e.user_uid = $user_uid" if user_uid else ""
        cypher_query = f"""
        MATCH (e:Event)
        WHERE e.event_date < date($today)
          AND e.status NOT IN ['completed', 'cancelled']
          {user_clause}
        RETURN e
        ORDER BY e.event_date DESC
        LIMIT $limit
        """

        params: dict[str, str | int] = {"today": today.isoformat(), "limit": limit}
        if user_uid:
            params["user_uid"] = user_uid

        result = await self.backend.execute_query(cypher_query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to Events using inherited helper
        events = self._to_domain_models([record["e"] for record in result.value], EventDTO, Event)

        self.logger.debug(f"Found {len(events)} overdue events")
        return Result.ok(events)

    # ========================================================================
    # EVENT-SPECIFIC SEARCH METHODS
    # ========================================================================

    @with_error_handling("get_in_range", error_type="database")
    async def get_in_range(
        self,
        start_date: date,
        end_date: date,
        user_uid: str | None = None,
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
        # Build query with optional user filter
        if user_uid:
            cypher_query = """
            MATCH (e:Event)
            WHERE e.event_date >= date($start_date)
              AND e.event_date <= date($end_date)
              AND e.user_uid = $user_uid
            RETURN e
            ORDER BY e.event_date ASC, e.start_time ASC
            LIMIT $limit
            """
            params = {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "user_uid": user_uid,
                "limit": limit,
            }
        else:
            cypher_query = """
            MATCH (e:Event)
            WHERE e.event_date >= date($start_date)
              AND e.event_date <= date($end_date)
            RETURN e
            ORDER BY e.event_date ASC, e.start_time ASC
            LIMIT $limit
            """
            params = {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "limit": limit,
            }

        result = await self.backend.execute_query(cypher_query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to Events using inherited helper
        events = self._to_domain_models([record["e"] for record in result.value], EventDTO, Event)

        self.logger.debug(f"Found {len(events)} events between {start_date} and {end_date}")
        return Result.ok(events)

    @with_error_handling("get_recurring", error_type="database")
    async def get_recurring(
        self, user_uid: str | None = None, limit: int = 100
    ) -> Result[list[Event]]:
        """
        Get recurring events.

        Args:
            user_uid: Optional user filter
            limit: Maximum results

        Returns:
            Result containing recurring events
        """
        # Build query with optional user filter
        if user_uid:
            cypher_query = """
            MATCH (e:Event)
            WHERE e.recurrence_pattern IS NOT NULL
              AND e.user_uid = $user_uid
            RETURN e
            ORDER BY e.event_date ASC
            LIMIT $limit
            """
            params = {"user_uid": user_uid, "limit": limit}
        else:
            cypher_query = """
            MATCH (e:Event)
            WHERE e.recurrence_pattern IS NOT NULL
            RETURN e
            ORDER BY e.event_date ASC
            LIMIT $limit
            """
            params = {"limit": limit}

        result = await self.backend.execute_query(cypher_query, params)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to Events using inherited helper
        events = self._to_domain_models([record["e"] for record in result.value], EventDTO, Event)

        self.logger.debug(f"Found {len(events)} recurring events")
        return Result.ok(events)

    @with_error_handling("get_for_goal", error_type="database", uid_param="goal_uid")
    async def get_for_goal(self, goal_uid: str, user_uid: str | None = None) -> Result[list[Event]]:
        """
        Get events that support a specific goal.

        Query: (Event)-[:SUPPORTS_GOAL]->(Goal)

        Args:
            goal_uid: Goal UID
            user_uid: Optional user filter

        Returns:
            Result containing events supporting the goal
        """
        events_result = await self.get_by_relationship(
            related_uid=goal_uid,
            relationship_type=RelationshipName.SUPPORTS_GOAL,
            direction="incoming",
        )
        if events_result.is_error:
            return events_result

        events = events_result.value

        # Filter by user if specified
        if user_uid:
            events = [e for e in events if e.user_uid == user_uid]

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
        event_result = await self.backend.get_event(event_uid)
        if event_result.is_error:
            return Result.fail(event_result.expect_error())

        event = self._to_domain_model(event_result.value, EventDTO, Event)

        if not event.event_date:
            return Result.ok([])  # No date = no conflicts

        # Query for events on same date for same user
        cypher_query = """
        MATCH (e:Event)
        WHERE e.event_date = date($event_date)
          AND e.user_uid = $user_uid
          AND e.uid <> $event_uid
          AND e.status NOT IN ['cancelled']
        RETURN e
        """

        result = await self.backend.execute_query(
            cypher_query,
            {
                "event_date": event.event_date.isoformat(),
                "user_uid": event.user_uid,
                "event_uid": event_uid,
            },
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert and check for time overlap
        conflicts = []
        for record in result.value:
            event_node = record["e"]
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

    @with_error_handling("get_by_type", error_type="database")
    async def get_by_type(
        self, event_type: str, user_uid: str | None = None, limit: int = 100
    ) -> Result[list[Event]]:
        """
        Get events by event type.

        Args:
            event_type: Event type string (e.g., "meeting", "study", "exercise")
            user_uid: Optional user filter
            limit: Maximum results

        Returns:
            Result containing events of the specified type
        """
        if user_uid:
            result = await self.backend.find_by(
                event_type=event_type, user_uid=user_uid, limit=limit
            )
        else:
            result = await self.backend.find_by(event_type=event_type, limit=limit)

        if result.is_error:
            return result

        events = self._to_domain_models(result.value, EventDTO, Event)

        self.logger.debug(f"Found {len(events)} events of type '{event_type}'")
        return Result.ok(events)

    @with_error_handling("get_upcoming", error_type="database", uid_param="user_uid")
    async def get_upcoming(
        self, user_uid: str, days_ahead: int = 30, limit: int = 100
    ) -> Result[list[Event]]:
        """
        Get upcoming events for a user.

        Args:
            user_uid: User identifier
            days_ahead: Number of days to look ahead
            limit: Maximum results

        Returns:
            Result containing upcoming events sorted by date
        """
        today = date.today()
        end_date = today + timedelta(days=days_ahead)

        return await self.get_in_range(
            start_date=today,
            end_date=end_date,
            user_uid=user_uid,
            limit=limit,
        )

    @with_error_handling("get_history", error_type="database", uid_param="user_uid")
    async def get_history(
        self, user_uid: str, days_back: int = 90, limit: int = 100
    ) -> Result[list[Event]]:
        """
        Get completed/past events for a user.

        Args:
            user_uid: User identifier
            days_back: Number of days of history to retrieve
            limit: Maximum results

        Returns:
            Result containing past events (most recent first)
        """
        today = date.today()
        start_date = today - timedelta(days=days_back)

        # Query for completed events in date range
        cypher_query = """
        MATCH (e:Event)
        WHERE e.user_uid = $user_uid
          AND e.event_date >= date($start_date)
          AND e.event_date <= date($today)
          AND e.status = 'completed'
        RETURN e
        ORDER BY e.event_date DESC
        LIMIT $limit
        """

        result = await self.backend.execute_query(
            cypher_query,
            {
                "user_uid": user_uid,
                "start_date": start_date.isoformat(),
                "today": today.isoformat(),
                "limit": limit,
            },
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        # Convert to Events
        events = []
        for record in result.value:
            event_node = record["e"]
            dto = EventDTO.from_dict(dict(event_node))
            events.append(Event.from_dto(dto))

        self.logger.debug(f"Found {len(events)} events in history for user {user_uid}")
        return Result.ok(events)

    @with_error_handling("get_for_habit", error_type="database", uid_param="habit_uid")
    async def get_for_habit(
        self, habit_uid: str, user_uid: str | None = None
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
        events_result = await self.get_by_relationship(
            related_uid=habit_uid,
            relationship_type=RelationshipName.REINFORCES_HABIT,
            direction="incoming",
        )
        if events_result.is_error:
            return events_result

        events = events_result.value

        # Filter by user if specified
        if user_uid:
            events = [e for e in events if e.user_uid == user_uid]

        self.logger.debug(f"Found {len(events)} events reinforcing habit {habit_uid}")
        return Result.ok(events)

    @with_error_handling("get_calendar_events", error_type="database", uid_param="user_uid")
    async def get_calendar_events(
        self,
        user_uid: str,
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

    @with_error_handling("intelligent_search", error_type="database")
    async def intelligent_search(
        self, query: str, user_uid: str | None = None, limit: int = 50
    ) -> Result[tuple[list[Event], ParsedSearchQuery]]:
        """
        Natural language search with semantic filter extraction.

        Parses queries like "upcoming tech events this week" to extract:
        - Date keywords (today, this week, upcoming, past)
        - Status filters (completed, cancelled, active)
        - Domain filters (health, tech, etc.)
        - Recurrence filters (recurring, one-time)

        Args:
            query: Natural language search query
            user_uid: Optional user UID to filter by ownership
            limit: Maximum results to return

        Returns:
            Result containing (events, parsed_query) tuple

        Example:
            >>> result = await search.intelligent_search("upcoming health events")
            >>> events, parsed = result.value
            >>> print(f"Filters: {parsed.to_filter_summary()}")
        """
        # Parse query for semantic filters
        parser = SearchQueryParser()
        parsed = parser.parse(query)
        query_lower = query.lower()

        # Determine date range based on keywords
        today = date.today()
        start_date: date | None = None
        end_date: date | None = None
        is_past = False

        # Event-specific: Date keyword extraction
        if "today" in query_lower:
            start_date = today
            end_date = today
        elif "tomorrow" in query_lower:
            start_date = today + timedelta(days=1)
            end_date = start_date
        elif "this week" in query_lower:
            # This week = today through end of week (Sunday)
            days_until_sunday = 6 - today.weekday()
            start_date = today
            end_date = today + timedelta(days=days_until_sunday)
        elif "next week" in query_lower:
            # Next week
            days_until_monday = 7 - today.weekday()
            start_date = today + timedelta(days=days_until_monday)
            end_date = start_date + timedelta(days=6)
        elif "this month" in query_lower:
            start_date = today.replace(day=1)
            if today.month == 12:
                end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end_date = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        elif "upcoming" in query_lower or "future" in query_lower:
            start_date = today
            end_date = today + timedelta(days=90)  # Next 3 months
        elif "past" in query_lower or "history" in query_lower:
            is_past = True
            start_date = today - timedelta(days=90)
            end_date = today - timedelta(days=1)

        # Use date range query if date keywords found
        if start_date and end_date:
            if is_past:
                # For past events, fetch all and filter to completed
                result = await self.get_in_range(start_date, end_date, user_uid, limit)
                if result.is_error:
                    return Result.fail(result.expect_error())
                events = [e for e in result.value if e.status == ActivityStatus.COMPLETED]
            else:
                result = await self.get_in_range(start_date, end_date, user_uid, limit)
                if result.is_error:
                    return Result.fail(result.expect_error())
                events = result.value
        else:
            # No date range - use filters or text search
            filters: dict[str, object] = {}

            # Apply status filter from parsed query (use first status if multiple)
            if parsed.statuses:
                filters["status"] = parsed.statuses[0].value

            # Apply domain filter from parsed query (use first domain if multiple)
            if parsed.domains:
                filters["domain"] = parsed.domains[0].value

            # Execute search
            if filters:
                result = await self.backend.find_by(limit=limit, **filters)
                if result.is_error:
                    return Result.fail(result.expect_error())
                events = self._to_domain_models(result.value, EventDTO, Event)
            else:
                result = await self.search(parsed.text_query, limit=limit)
                if result.is_error:
                    return Result.fail(result.expect_error())
                events = result.value

            # Filter by user ownership if provided
            if user_uid and events:
                events = [e for e in events if getattr(e, "user_uid", None) == user_uid]

        # Event-specific: Recurrence filtering (post-filter)
        if "recurring" in query_lower or "repeat" in query_lower:
            events = [e for e in events if e.recurrence_pattern is not None]
        elif "one-time" in query_lower or "single" in query_lower:
            events = [e for e in events if e.recurrence_pattern is None]

        self.logger.info(
            "Intelligent search: query=%r filters=%s results=%d",
            query,
            parsed.to_filter_summary(),
            len(events),
        )

        return Result.ok((events, parsed))
