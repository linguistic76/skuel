"""
Habit Event Scheduler Service
==============================

Automatically schedules events from habits based on frequency, streaks,
and learning reinforcement needs. Uses UserContext for intelligent scheduling.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta
from enum import Enum
from typing import TYPE_CHECKING

from core.models.enums import Priority, RecurrencePattern
from core.models.enums.ku_enums import HabitCategory
from core.models.ku.event_dto import EventDTO
from core.models.ku.habit import Habit as Habit
from core.models.ku.habit_dto import HabitDTO

# Import protocol interfaces
from core.utils.dto_helpers import to_domain_model
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports import EventsOperations, HabitsOperations
    from core.services.user import UserContext


class SchedulingStrategy(Enum):
    """Event scheduling strategies."""

    FIXED_TIME = "fixed_time"  # Same time every day
    OPTIMAL_TIME = "optimal_time"  # Based on user's best performance times
    FLEXIBLE = "flexible"  # Any time during the day
    MORNING = "morning"  # Morning routine
    EVENING = "evening"  # Evening routine


@dataclass
class EventSchedulingConfig:
    """Configuration for event scheduling."""

    default_strategy: SchedulingStrategy = SchedulingStrategy.OPTIMAL_TIME
    default_duration_minutes: int = 30
    morning_start_hour: int = 6
    morning_end_hour: int = 9
    evening_start_hour: int = 19
    evening_end_hour: int = 22
    max_events_per_day: int = 10
    schedule_ahead_days: int = 7
    buffer_minutes_between_events: int = 15
    skip_weekends: bool = False


class HabitEventScheduler:
    """
    Service that automatically schedules events from habits.

    This service analyzes habits and creates:
    1. Recurring events based on habit frequency
    2. Streak maintenance events
    3. Knowledge reinforcement sessions
    4. Keystone habit priority events
    """

    def __init__(
        self,
        habits_backend: HabitsOperations,
        events_backend: EventsOperations,
        config: EventSchedulingConfig | None = None,
        relationship_service=None,
    ) -> None:
        """
        Initialize event scheduler.

        Args:
            habits_backend: Backend for habit operations,
            events_backend: Backend for event operations,
            config: Scheduling configuration,
            relationship_service: Service for fetching habit relationships

        Note:
            Context invalidation now happens via event-driven architecture.
            Created events trigger domain events which invalidate context.
        """
        if not habits_backend:
            raise ValueError("Habits backend is required")
        if not events_backend:
            raise ValueError("Events backend is required")

        self.habits_backend = habits_backend
        self.events_backend = events_backend
        self.config = config or EventSchedulingConfig()
        self.relationships = relationship_service
        self.logger = get_logger("skuel.services.habit_event_scheduler")

    def _calculate_end_time(
        self, start_time: time, duration_minutes: int, event_date: date | None = None
    ) -> time:
        """
        Calculate end time by adding duration to start time.

        Args:
            start_time: Event start time
            duration_minutes: Duration in minutes
            event_date: Event date (default: today) - needed for midnight boundary cases

        Returns:
            End time

        Note:
            Handles midnight boundary by combining with date, adding duration, then extracting time.
        """
        from datetime import datetime

        # Use provided date or today
        base_date = event_date if event_date else date.today()

        # Combine date + time, add duration, extract time
        start_dt = datetime.combine(base_date, start_time)
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        return end_dt.time()

    # ========================================================================
    # AUTOMATIC EVENT SCHEDULING
    # ========================================================================

    async def schedule_events_for_habit(
        self,
        habit_uid: str,
        user_context: UserContext,
        auto_create: bool = False,
        days_ahead: int | None = None,
    ) -> Result[list[EventDTO]]:
        """
        Schedule events for a specific habit.

        Args:
            habit_uid: Habit to schedule events for,
            user_context: User's current context,
            auto_create: If True, automatically create events; if False, return templates,
            days_ahead: Number of days to schedule ahead (defaults to config)

        Returns:
            List of created or template events
        """
        days_ahead = days_ahead or self.config.schedule_ahead_days

        # Get the habit
        habit_result = await self.habits_backend.get_habit(habit_uid)
        if habit_result.is_error:
            return Result.fail(habit_result.expect_error())

        habit = to_domain_model(habit_result.value, HabitDTO, Habit)

        # Check if habit is active (is_active is a bool field on Ku)
        if not habit.is_active:
            return Result.ok([])

        # Generate events based on frequency
        scheduled_events = await self._generate_events_for_frequency(
            habit, user_context, days_ahead
        )

        # Apply scheduling strategy
        scheduled_events = self._apply_scheduling_strategy(scheduled_events, habit, user_context)

        # Avoid conflicts with existing events
        scheduled_events = await self._avoid_conflicts(scheduled_events, user_context)

        # Create events if requested
        created_events = []
        if auto_create:
            for event_template in scheduled_events:
                create_result = await self.events_backend.create_event(event_template.to_dict())
                if create_result.is_ok:
                    created_dto = to_domain_model(create_result.value, EventDTO, EventDTO)
                    created_events.append(created_dto)
                else:
                    self.logger.warning(f"Failed to create event: {create_result.error}")

            # Context invalidation happens via domain events (event-driven architecture)
            # Event handlers in bootstrap will call user_service.invalidate_context()

            self.logger.info(
                "Scheduled and created %d events for habit %s", len(created_events), habit_uid
            )

            return Result.ok(created_events)

        self.logger.info(
            "Generated %d event templates for habit %s", len(scheduled_events), habit_uid
        )

        return Result.ok(scheduled_events)

    # ========================================================================
    # BULK SCHEDULING
    # ========================================================================

    async def schedule_events_for_all_habits(
        self, user_context: UserContext, auto_create: bool = False
    ) -> Result[dict[str, list[EventDTO]]]:
        """
        Schedule events for all active habits.

        Args:
            user_context: User's current context,
            auto_create: If True, automatically create events

        Returns:
            Dictionary mapping habit_uid to scheduled events
        """
        all_scheduled = {}

        # Prioritize keystone habits
        habit_order = []
        habit_order.extend(user_context.keystone_habits)  # Keystone first
        habit_order.extend(
            [h for h in user_context.active_habit_uids if h not in user_context.keystone_habits]
        )

        for habit_uid in habit_order:
            # Check if habit already has enough events scheduled
            existing_events = user_context.events_by_habit.get(habit_uid, [])
            upcoming_events = [e for e in existing_events if e in user_context.upcoming_event_uids]

            if len(upcoming_events) >= self.config.schedule_ahead_days:
                continue

            result = await self.schedule_events_for_habit(habit_uid, user_context, auto_create)
            if result.is_ok:
                all_scheduled[habit_uid] = result.value

        self.logger.info("Scheduled events for %d habits", len(all_scheduled))

        return Result.ok(all_scheduled)

    # ========================================================================
    # SMART SCHEDULING
    # ========================================================================

    async def schedule_streak_maintenance(
        self, user_context: UserContext, auto_create: bool = False
    ) -> Result[list[EventDTO]]:
        """
        Schedule events to maintain at-risk habit streaks.

        Prioritizes habits with:
        1. Long streaks at risk
        2. Keystone habits
        3. Habits supporting critical goals
        """
        maintenance_events = []

        for habit_uid in user_context.at_risk_habits:
            # Get habit details
            habit_result = await self.habits_backend.get_habit(habit_uid)
            if habit_result.is_error:
                continue

            habit = to_domain_model(habit_result.value, HabitDTO, Habit)

            # Create urgent maintenance event
            start_time = self._get_optimal_time(user_context)
            duration = habit.duration_minutes or self.config.default_duration_minutes
            end_time = self._calculate_end_time(start_time, duration, date.today())

            from core.models.enums.ku_enums import EntityType
            from core.utils.uid_generator import UIDGenerator

            event = EventDTO(
                uid=UIDGenerator.generate_random_uid("event"),
                ku_type=EntityType.EVENT,
                user_uid=user_context.user_uid,
                title=f"MAINTAIN STREAK: {habit.title}",
                event_date=date.today(),
                start_time=start_time,
                end_time=end_time,
            )

            # Add habit integration
            event.reinforces_habit_uid = habit_uid
            event.recurrence_maintains_habit = True
            event.skip_breaks_habit_streak = True
            event.metadata["is_urgent"] = True
            event.priority = Priority.CRITICAL if habit.is_keystone else Priority.HIGH

            maintenance_events.append(event)

        # Create events if requested
        if auto_create and maintenance_events:
            created = []
            for event in maintenance_events:
                create_result = await self.events_backend.create_event(event.to_dict())
                if create_result.is_ok:
                    created.append(to_domain_model(create_result.value, EventDTO, EventDTO))

            # Context invalidation happens via domain events (event-driven architecture)

            return Result.ok(created)

        return Result.ok(maintenance_events)

    async def create_habit_routine(
        self,
        user_context: UserContext,
        routine_type: str = "morning",
        habit_uids: list[str] | None = None,
    ) -> Result[list[EventDTO]]:
        """
        Create a routine by scheduling multiple habits together.

        Args:
            user_context: User's current context,
            routine_type: "morning", "evening", or "custom",
            habit_uids: Specific habits to include (None = auto-select)

        Returns:
            List of scheduled routine events
        """
        routine_events = []

        # Auto-select habits if not specified
        if not habit_uids:
            habit_uids = await self._select_routine_habits(user_context, routine_type)

        # Determine routine time window
        if routine_type == "morning":
            start_hour = self.config.morning_start_hour
            current_time = time(start_hour, 0)
        elif routine_type == "evening":
            start_hour = self.config.evening_start_hour
            current_time = time(start_hour, 0)
        else:
            current_time = self._get_optimal_time(user_context)

        # Schedule habits in sequence
        for habit_uid in habit_uids:
            habit_result = await self.habits_backend.get_habit(habit_uid)
            if habit_result.is_error:
                continue

            habit = to_domain_model(habit_result.value, HabitDTO, Habit)

            # Create event for this habit
            duration = habit.duration_minutes or self.config.default_duration_minutes
            event_date_val = date.today() + timedelta(days=1)  # Start tomorrow
            end_time = self._calculate_end_time(current_time, duration, event_date_val)

            from core.models.enums.ku_enums import EntityType
            from core.utils.uid_generator import UIDGenerator

            event = EventDTO(
                uid=UIDGenerator.generate_random_uid("event"),
                ku_type=EntityType.EVENT,
                user_uid=user_context.user_uid,
                title=f"{routine_type.title()} Routine: {habit.title}",
                event_date=event_date_val,
                start_time=current_time,
                end_time=end_time,
            )

            event.reinforces_habit_uid = habit_uid
            event.metadata["part_of_routine"] = routine_type
            event.metadata["routine_order"] = len(routine_events) + 1

            routine_events.append(event)

            # Calculate next time slot (calculate duration from start/end time)
            minutes = current_time.hour * 60 + current_time.minute
            if end_time:
                duration_minutes = (end_time.hour * 60 + end_time.minute) - (
                    current_time.hour * 60 + current_time.minute
                )
            else:
                duration_minutes = 30  # Default duration
            minutes += duration_minutes + self.config.buffer_minutes_between_events
            current_time = time(minutes // 60, minutes % 60)

        self.logger.info("Created %s routine with %d habits", routine_type, len(routine_events))

        return Result.ok(routine_events)

    # ========================================================================
    # PRIVATE SCHEDULING METHODS
    # ========================================================================

    async def _generate_events_for_frequency(
        self, habit: Habit, user_context: UserContext, days_ahead: int
    ) -> list[EventDTO]:
        """Generate events based on habit frequency."""
        # Fetch habit relationships from graph
        from core.services.habits.habit_relationships import HabitRelationships

        rels = (
            await HabitRelationships.fetch(habit.uid, self.relationships)
            if self.relationships
            else HabitRelationships()
        )

        events = []
        start_date = date.today()

        for day_offset in range(days_ahead):
            event_date = start_date + timedelta(days=day_offset)

            # Skip weekends if configured
            if self.config.skip_weekends and event_date.weekday() >= 5:
                continue

            # Check if habit occurs on this date
            if self._should_schedule_on_date(habit, event_date):
                start_time = self._get_optimal_time(user_context)
                duration = habit.duration_minutes or self.config.default_duration_minutes
                end_time = self._calculate_end_time(start_time, duration, event_date)

                from core.models.enums.ku_enums import EntityType
                from core.utils.uid_generator import UIDGenerator

                event = EventDTO(
                    uid=UIDGenerator.generate_random_uid("event"),
                    ku_type=EntityType.EVENT,
                    user_uid=user_context.user_uid,
                    title=habit.title,
                    description=habit.description or f"Practice {habit.title}",
                    event_date=event_date,
                    start_time=start_time,
                    end_time=end_time,
                )

                # Add habit integration
                event.reinforces_habit_uid = habit.uid
                event.recurrence_maintains_habit = True
                event.skip_breaks_habit_streak = True

                # Add knowledge reinforcement if applicable
                # Store in metadata - service layer creates PRACTICES_KNOWLEDGE graph relationships
                if rels.knowledge_reinforcement_uids:
                    event.metadata["practices_knowledge_uids"] = list(
                        rels.knowledge_reinforcement_uids
                    )
                    event.metadata["contributes_to_mastery"] = True

                # Add goal support if applicable
                if rels.linked_goal_uids:
                    # Use fulfills_goal_uid for the first goal (singular field exists)
                    event.fulfills_goal_uid = next(iter(rels.linked_goal_uids))  # type: ignore[attr-defined]
                    # Store all goals in metadata
                    event.metadata["supports_goals"] = list(rels.linked_goal_uids)

                # Set priority based on habit importance
                if habit.is_keystone or habit.uid in user_context.at_risk_habits:
                    event.priority = Priority.HIGH
                else:
                    event.priority = habit.priority or Priority.MEDIUM

                events.append(event)

        return events

    def _should_schedule_on_date(self, habit: Habit, check_date: date) -> bool:
        """Determine if habit should be scheduled on a specific date."""
        if habit.recurrence_pattern == RecurrencePattern.DAILY:
            return True

        elif habit.recurrence_pattern == RecurrencePattern.WEEKDAYS:
            # Monday-Friday (weekday() returns 0-6, where 0=Monday, 5=Saturday)
            return check_date.weekday() < 5

        elif habit.recurrence_pattern == RecurrencePattern.WEEKENDS:
            # Saturday-Sunday
            return check_date.weekday() >= 5

        elif habit.recurrence_pattern == RecurrencePattern.WEEKLY:
            # Once a week - schedule on same weekday as habit was started
            if habit.started_at:
                return check_date.weekday() == habit.started_at.weekday()
            # Default to current weekday if no start date
            return True

        elif habit.recurrence_pattern == RecurrencePattern.BIWEEKLY:
            # Every two weeks
            if habit.started_at:
                days_since_start = (check_date - habit.started_at.date()).days
                # Schedule if it's been a multiple of 14 days and same weekday
                return (
                    days_since_start % 14 == 0
                    and check_date.weekday() == habit.started_at.weekday()
                )
            return False

        elif habit.recurrence_pattern == RecurrencePattern.MONTHLY:
            # Once a month - same day of month as start date
            if habit.started_at:
                return check_date.day == habit.started_at.day
            return False

        # For CUSTOM, QUARTERLY, YEARLY, NONE - don't auto-schedule
        return False

    def _apply_scheduling_strategy(
        self, events: list[EventDTO], habit: Habit, user_context: UserContext
    ) -> list[EventDTO]:
        """Apply scheduling strategy to determine event times."""
        strategy = self._determine_strategy(habit, user_context)

        for event in events:
            if strategy == SchedulingStrategy.MORNING:
                event.start_time = time(self.config.morning_start_hour, 0)
            elif strategy == SchedulingStrategy.EVENING:
                event.start_time = time(self.config.evening_start_hour, 0)
            elif strategy == SchedulingStrategy.OPTIMAL_TIME:
                event.start_time = self._get_optimal_time(user_context)
            elif strategy == SchedulingStrategy.FIXED_TIME and habit.preferred_time:
                event.start_time = habit.preferred_time
            else:  # FLEXIBLE
                event.start_time = None  # Any time

        return events

    def _determine_strategy(self, habit: Habit, _user_context: UserContext) -> SchedulingStrategy:
        """Determine best scheduling strategy for a habit."""
        # Keystone habits get optimal time
        if habit.is_keystone:
            return SchedulingStrategy.OPTIMAL_TIME

        # Learning habits in the morning
        if habit.habit_category == HabitCategory.LEARNING:
            return SchedulingStrategy.MORNING

        # Check habit tags/category for hints
        if habit.tags:
            if "morning" in habit.tags:
                return SchedulingStrategy.MORNING
            elif "evening" in habit.tags:
                return SchedulingStrategy.EVENING

        return self.config.default_strategy

    def _get_optimal_time(self, _user_context: UserContext) -> time:
        """Get optimal time for user based on context."""
        # This would analyze user's performance patterns
        # For now, return mid-morning as default optimal time
        return time(10, 0)

    async def _avoid_conflicts(
        self, events: list[EventDTO], _user_context: UserContext
    ) -> list[EventDTO]:
        """Adjust event times to avoid conflicts with existing events."""
        # This would check against existing calendar
        # For now, return events as-is
        return events

    async def _select_routine_habits(
        self, user_context: UserContext, routine_type: str
    ) -> list[str]:
        """Auto-select habits for a routine."""
        selected = []

        # Always include keystone habits
        selected.extend(user_context.keystone_habits)

        # Add habits based on routine type
        if routine_type == "morning":
            # Add learning habits
            for habit_uid in user_context.active_habit_uids:
                if habit_uid not in selected:
                    habit_result = await self.habits_backend.get_habit(habit_uid)
                    if habit_result.is_ok and habit_result.value:
                        habit = habit_result.value  # Already a Habit domain model
                        if habit.habit_category == HabitCategory.LEARNING:
                            selected.append(habit_uid)

        elif routine_type == "evening":
            # Add reflection/planning habits
            for habit_uid in user_context.active_habit_uids:
                if habit_uid not in selected:
                    habit_result = await self.habits_backend.get_habit(habit_uid)
                    if habit_result.is_ok and habit_result.value:
                        habit = habit_result.value  # Already a Habit domain model
                        if habit.tags and "reflection" in habit.tags:
                            selected.append(habit_uid)

        # Limit to reasonable number
        return selected[:5]

    # ========================================================================
    # EVENT TEMPLATE LIBRARY
    # ========================================================================

    def get_event_templates(self) -> dict[str, EventDTO]:
        """
        Get library of reusable event templates.

        Note: These are template events with placeholder values.
        Real usage should copy and customize with actual user_uid and dates.
        """
        placeholder_user = "template_user"
        today = date.today()

        from core.models.enums.ku_enums import EntityType
        from core.utils.uid_generator import UIDGenerator

        return {
            "daily_habit": EventDTO(
                uid=UIDGenerator.generate_random_uid("event"),
                ku_type=EntityType.EVENT,
                user_uid=placeholder_user,
                title="Daily habit practice",
                event_date=today,
                start_time=time(9, 0),
                end_time=time(9, 30),
                tags=["habit", "daily"],
            ),
            "morning_routine": EventDTO(
                uid=UIDGenerator.generate_random_uid("event"),
                ku_type=EntityType.EVENT,
                user_uid=placeholder_user,
                title="Morning routine",
                event_date=today,
                start_time=time(6, 0),
                end_time=time(7, 0),
                tags=["routine", "morning"],
            ),
            "learning_session": EventDTO(
                uid=UIDGenerator.generate_random_uid("event"),
                ku_type=EntityType.EVENT,
                user_uid=placeholder_user,
                title="Learning session",
                event_date=today,
                start_time=time(14, 0),
                end_time=time(15, 30),
                tags=["learning", "study"],
            ),
            "streak_maintenance": EventDTO(
                uid=UIDGenerator.generate_random_uid("event"),
                ku_type=EntityType.EVENT,
                user_uid=placeholder_user,
                title="Maintain streak",
                event_date=today,
                start_time=time(20, 0),
                end_time=time(20, 30),
                priority=Priority.HIGH,
                tags=["streak", "urgent"],
            ),
        }
