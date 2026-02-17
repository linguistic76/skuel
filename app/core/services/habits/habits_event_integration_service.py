"""
Habits Event Integration Service
==================================

Handles cross-domain event scheduling integration for habits.

This service manages the Habits→Events integration FROM THE HABITS PERSPECTIVE.
It does NOT create actual Event entities - that's the responsibility of EventsService.
Instead, it provides habit-specific intelligence for event scheduling.

Responsibilities:
- Get events linked to specific habits (from user context)
- Generate event SUGGESTIONS based on habit frequency
- Determine when habits should occur (recurrence logic)
- Return event templates for EventsService to create
"""

from datetime import date, timedelta
from typing import Any

from core.models.enums import RecurrencePattern as HabitFrequency
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO
from core.services.protocols.domain_protocols import HabitsOperations
from core.services.user import UserContext
from core.utils.dto_helpers import to_domain_model
from core.utils.logging import get_logger
from core.utils.result_simplified import Result


class HabitsEventIntegrationService:
    """
    Cross-domain event integration service for habits.

    This service provides habit-specific intelligence for event scheduling,
    but does NOT create actual Event entities. It generates event templates
    and suggestions that EventsService can use to create actual events.

    Handles:
    - Retrieving event UIDs linked to habits (from user context)
    - Generating event SUGGESTIONS for habit maintenance
    - Habit recurrence logic (when should habit occur)
    - Event template generation with habit-specific data


    Source Tag: "habits_event_integration_service_explicit"
    - Format: "habits_event_integration_service_explicit" for user-created relationships
    - Format: "habits_event_integration_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from habits_event_integration metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(self, backend: HabitsOperations) -> None:
        """
        Initialize habits event service.

        Args:
            backend: Protocol-based backend for habit operations

        Note:
            Context invalidation now happens via event-driven architecture.
            Habit events trigger user_service.invalidate_context() in bootstrap.
        """
        self.backend = backend
        self.logger = get_logger("skuel.services.habits.event_integration")

    # ========================================================================
    # EVENT INTEGRATION METHODS
    # ========================================================================

    async def get_events_for_habit(
        self, habit_uid: str, user_context: UserContext, _days_ahead: int = 7
    ) -> Result[list[str]]:
        """
        Get upcoming events that reinforce this habit.

        Args:
            habit_uid: UID of the habit,
            user_context: User's context with event mappings,
            days_ahead: Number of days to look ahead

        Returns:
            Result containing list of event UIDs
        """
        if habit_uid not in user_context.events_by_habit:
            return Result.ok([])

        event_uids = user_context.events_by_habit[habit_uid]

        # Filter to upcoming events
        upcoming = [
            event_uid for event_uid in event_uids if event_uid in user_context.upcoming_event_uids
        ]

        return Result.ok(upcoming)

    async def schedule_events_for_habit(
        self, habit_uid: str, _user_context: UserContext, days_to_schedule: int = 7
    ) -> Result[list[dict[str, Any]]]:
        """
        Generate event suggestions for maintaining a habit.

        Returns list of event templates that can be created.

        DESIGN DECISION - Knowledge UIDs Intentionally Omitted (Graph-Native):
        ===================================================================
        Event suggestions do NOT include `practices_knowledge_uids` even though
        habits may have knowledge reinforcement relationships in the graph.

        Rationale:
        1. **Templates vs. Entities**: These are SUGGESTIONS, not actual events
        2. **Creation Responsibility**: EventsService is responsible for creating
           actual Event entities and establishing graph relationships
        3. **Relationship Timing**: Knowledge links should be created when
           EventsService persists the Event, not in the suggestion phase
        4. **Clean Separation**: Habit intelligence provides scheduling data,
           EventsService handles entity creation and relationship wiring

        If knowledge UIDs are needed:
        - EventsService can fetch HabitRelationships.fetch(habit_uid) when
          creating the Event from the suggestion template
        - EventsRelationshipService can link Event→Knowledge after creation

        This maintains graph-native pattern: relationships created in graph after
        both entities exist, not passed as template fields.

        Args:
            habit_uid: UID of the habit,
            user_context: User's context,
            days_to_schedule: Number of days to generate events for

        Returns:
            Result containing list of event suggestion dictionaries
        """
        habit_result = await self.backend.get_habit(habit_uid)
        if habit_result.is_error:
            return Result.fail(habit_result.expect_error())

        habit = to_domain_model(habit_result.value, KuDTO, Ku)

        event_suggestions = []
        start_date = date.today()

        for day_offset in range(days_to_schedule):
            event_date = start_date + timedelta(days=day_offset)

            # Check if habit should occur on this day
            if self._should_occur_on_date(habit, event_date):
                event = {
                    "title": habit.title,
                    "description": f"Maintain {habit.title} habit",
                    "reinforces_habit_uid": habit_uid,
                    "event_date": event_date.isoformat(),
                    "duration_minutes": habit.duration_minutes,
                    "recurrence_maintains_habit": True,
                    "skip_breaks_habit_streak": True,
                    "habit_completion_quality": None,  # To be filled on completion
                    "tags": ["habit", *list(habit.tags if habit.tags else [])],
                }

                # DESIGN DECISION (Graph-Native): Knowledge UIDs intentionally omitted
                # See docstring for rationale - EventsService handles relationship
                # creation when converting suggestion → actual Event entity

                event_suggestions.append(event)

        self.logger.info(
            "Generated %d event suggestions for habit %s", len(event_suggestions), habit_uid
        )

        return Result.ok(event_suggestions)

    # ========================================================================
    # PRIVATE HELPER METHODS
    # ========================================================================

    def _should_occur_on_date(self, habit: Ku, check_date: date) -> bool:
        """
        Check if habit should occur on a specific date based on recurrence pattern.

        Graph-Native Note:
        - Removed habit.weekly_days (not part of model)
        - Removed habit.custom_frequency_days (not part of model)
        - Simplified to use RecurrencePattern enum values
        - For complex patterns, use RRULE or event scheduling service

        Args:
            habit: Habit domain model
            check_date: Date to check

        Returns:
            bool: True if habit should occur on this date
        """
        if habit.recurrence_pattern == HabitFrequency.DAILY:
            return True
        elif habit.recurrence_pattern == HabitFrequency.WEEKDAYS:
            # Monday-Friday (0-4)
            return check_date.weekday() < 5
        elif habit.recurrence_pattern == HabitFrequency.WEEKENDS:
            # Saturday-Sunday (5-6)
            return check_date.weekday() >= 5
        elif habit.recurrence_pattern == HabitFrequency.WEEKLY:
            # GRAPH-NATIVE: Simplified - occurs once per week
            # For specific day-of-week control, use target_days_per_week
            # Return True on first check (will create one event per week)
            if habit.started_at:
                days_since_start = (check_date - habit.started_at.date()).days
                # Occur every 7 days starting from start date
                return days_since_start % 7 == 0
            return check_date.weekday() == 0  # Default to Monday
        elif habit.recurrence_pattern == HabitFrequency.CUSTOM:
            # GRAPH-NATIVE: Custom patterns not supported in simplified check
            # Use RRULE or advanced event scheduling for custom patterns
            return False
        return False
