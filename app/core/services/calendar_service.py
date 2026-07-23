"""
Calendar Service
================

Unified calendar service for displaying tasks, events, and habits in calendar views.
Simplified implementation focusing on essential calendar functionality.

DESIGN DECISION (October 3, 2025):
----------------------------------
This service intentionally keeps a SIMPLE, BASIC, FUNDAMENTAL design.

Core Responsibilities:
1. Display calendar items (tasks, events, habits)
2. Provide day/week/month views
3. Basic CRUD operations (create, reschedule, quick-create)
4. Habit recurrence projection

This service does NOT provide:
- Intelligent scheduling recommendations
- Conflict detection
- Knowledge-aware scheduling
- Dependency analysis
- Cross-domain intelligence

Integration History:
Intelligent scheduling methods (conflict detection, recommendations, context loading)
were explored in October 2025 but removed to keep service simple and focused.
See git history (commit around Oct 3, 2025) for reference implementation if needed.

For intelligent scheduling features, create a dedicated orchestration service
that calls CalendarService for display data.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.models.type_hints import EntityUID, UserUID

if TYPE_CHECKING:
    from core.services.habits_service import HabitsService

from core.models.enums import Priority
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.habit_enums import CompletionStatus
from core.models.event.calendar_models import (
    CalendarData,
    CalendarItem,
    CalendarItemType,
    CalendarOccurrence,
    CalendarView,
)
from core.models.event.event import Event
from core.models.event.event_update_intent import EventUpdateIntent
from core.models.habit.completion import HabitCompletion
from core.models.habit.habit import Habit

# Facade import for habit occurrence recording (needs track_habit method)
from core.models.habit.habit_request import TrackHabitRequest
from core.models.task.task import Task
from core.models.task.task_update_intent import TaskUpdateIntent
from core.ports import get_enum_value

# Import protocol interfaces for dependency injection
from core.ports.domain_protocols import (
    EventsOperations,
    TasksOperations,
)
from core.utils.decorators import with_error_handling
from core.utils.exception_types import NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.neo4j_temporal import (
    convert_neo4j_date,
    convert_neo4j_datetime,
    convert_neo4j_time,
)
from core.utils.result_simplified import Errors, Result
from core.utils.uid_generator import UIDGenerator

logger = get_logger("skuel.services.calendar")


# ============================================================================
# CALENDAR SERVICE
# ============================================================================
# Note: Presentation constants (colors, icons) are now dynamic.
# All styling is derived from enum methods in shared_enums.py and calendar_models.py.
# This allows the entire codebase to update when enum definitions change.


class CalendarService:
    """
    Unified calendar service for managing calendar views.

    Provides:
    - Calendar view generation (day/week/month)
    - Task, event, and habit integration
    - Habit recurrence projection
    - Color and icon styling

    This is a meta-service: it delegates all graph queries to the injected domain
    services (TasksOperations, EventsOperations, HabitsService). It does not
    write Cypher directly.
    """

    def __init__(
        self,
        tasks_service: TasksOperations,
        events_service: EventsOperations,
        habits_service: HabitsService,
    ) -> None:
        """
        Initialize with required domain services.

        All three domain services are required — fail-fast if any is missing.

        Args:
            tasks_service: Service for task operations
            events_service: Service for event operations
            habits_service: Service for habit operations
        """
        self.tasks_service = tasks_service
        self.events_service = events_service
        self.habits_service = habits_service
        self.logger = logger
        logger.debug("CalendarService initialized")

    # ========================================================================
    # MAIN PUBLIC INTERFACE
    # ========================================================================

    @with_error_handling("get_calendar_view", error_type="system", uid_param="user_uid")
    async def get_calendar_view(
        self,
        user_uid: UserUID,
        start_date: date,
        end_date: date,
        view_type: CalendarView = CalendarView.MONTH,
        include_completed: bool = False,
    ) -> Result[CalendarData]:
        """
        Get calendar data for the specified date range.

        Args:
            user_uid: User UID (REQUIRED for unified query pattern),
            start_date: Start of date range,
            end_date: End of date range,
            view_type: Type of calendar view,
            include_completed: Whether to include completed items

        Returns:
            Result with CalendarData or error

        Note:
            Refactoring:
            Uses unified query pattern with Cypher-level filtering.
            10-100x performance improvement over in-memory filtering.
        """
        items = []

        # Fetch tasks using unified API (Cypher-level filtering)
        task_items = await self._fetch_tasks(user_uid, start_date, end_date, include_completed)
        items.extend(task_items)

        # Fetch events using unified API (Cypher-level filtering)
        event_items = await self._fetch_events(user_uid, start_date, end_date, include_completed)
        items.extend(event_items)

        # Fetch habits (ongoing practices — status-filtered, never date-filtered)
        habit_occurrences = {}
        habits = await self._fetch_habits(user_uid)
        for habit in habits:
            # Add habit as calendar item
            items.append(self._habit_to_calendar_item(habit))
            # Generate occurrences for the date range
            occurrences = self._generate_habit_occurrences(habit, start_date, end_date)
            if occurrences:
                habit_occurrences[habit.uid] = occurrences

        # Build calendar data
        calendar_data = CalendarData(
            items=items,
            occurrences=habit_occurrences,
            view=view_type,
            start_date=start_date,
            end_date=end_date,
            metadata={"total_items": len(items), "total_habits": len(habit_occurrences)},
        )

        return Result.ok(calendar_data)

    @with_error_handling("get_item", error_type="system", uid_param="item_uid")
    async def get_item(self, user_uid: UserUID, item_uid: str) -> Result[CalendarItem | None]:
        """
        Get a specific calendar item by UID.

        Args:
            item_uid: UID of the calendar item

        Returns:
            Result with CalendarItem or None if not found
        """
        # Parse item type from UID prefix
        if item_uid.startswith("task-"):
            source_uid = item_uid[5:]  # Remove "task-" prefix
            task_result = await self.tasks_service.get(source_uid)
            if task_result.is_ok and task_result.value:
                if task_result.value.user_uid != user_uid:
                    return Result.ok(None)  # not the requester's — treat as not found
                return Result.ok(self._task_to_calendar_item(task_result.value))

        elif item_uid.startswith("event-"):
            source_uid = item_uid[6:]  # Remove "event-" prefix
            event_result = await self.events_service.get(source_uid)
            if event_result.is_ok and event_result.value:
                if event_result.value.user_uid != user_uid:
                    return Result.ok(None)  # not the requester's — treat as not found
                return Result.ok(self._event_to_calendar_item(event_result.value))

        elif item_uid.startswith("habit-"):
            source_uid = item_uid[6:]  # Remove "habit-" prefix
            habit_result = await self.habits_service.get(source_uid)
            if habit_result.is_ok and habit_result.value:
                if habit_result.value.user_uid != user_uid:
                    return Result.ok(None)  # not the requester's — treat as not found
                return Result.ok(self._habit_to_calendar_item(habit_result.value))

        return Result.ok(None)

    @with_error_handling("quick_create", error_type="system")
    async def quick_create(
        self, user_uid: UserUID, item_type: str, title: str, start_time: datetime, **kwargs: Any
    ) -> Result[CalendarItem]:
        """
        Quick create a calendar item.

        Args:
            item_type: Type of item (task, event, habit),
            title: Title of the item,
            start_time: Start time
            **kwargs: Additional fields

        Returns:
            Result with created CalendarItem
        """
        duration = kwargs.get("duration", 60)  # Default 60 minutes
        end_time = start_time + timedelta(minutes=duration)

        if item_type == EntityType.TASK.value:
            # Create task — frozen domain model end-to-end (ADR-035/ADR-065).
            task = Task(
                uid=EntityUID(UIDGenerator.generate_random_uid("task")),
                entity_type=EntityType.TASK,
                user_uid=user_uid,
                title=title,
                description=kwargs.get("description", ""),
                scheduled_date=start_time.date(),
                due_date=start_time.date(),
                status=EntityStatus.SCHEDULED,
                priority=Priority.MEDIUM,
            )
            task_result = await self.tasks_service.create(task)
            if task_result.is_ok:
                return Result.ok(self._task_to_calendar_item(task_result.value))
            # Type boundary: Extract error from Result[Task] for Result[CalendarItem]
            return Result.fail(task_result)

        elif item_type == EntityType.EVENT.value:
            # Create event — frozen domain model end-to-end (ADR-035/ADR-065).
            event = Event(
                uid=EntityUID(UIDGenerator.generate_random_uid("event")),
                entity_type=EntityType.EVENT,
                user_uid=user_uid,
                title=title,
                description=kwargs.get("description", ""),
                event_date=start_time.date(),
                start_time=start_time.time(),
                end_time=end_time.time(),
                status=EntityStatus.SCHEDULED,
            )
            event_result = await self.events_service.create(event)
            if event_result.is_ok:
                return Result.ok(self._event_to_calendar_item(event_result.value))
            # Type boundary: Extract error from Result[Event] for Result[CalendarItem]
            return Result.fail(event_result)

        elif item_type == EntityType.HABIT.value:
            # Create habit — frozen domain model end-to-end (ADR-035/ADR-065).
            habit = Habit(
                uid=EntityUID(UIDGenerator.generate_random_uid("habit")),
                entity_type=EntityType.HABIT,
                user_uid=user_uid,
                title=title,
                description=kwargs.get("description", ""),
                target_days_per_week=kwargs.get("frequency", 7),
                status=EntityStatus.ACTIVE,
            )
            habit_result = await self.habits_service.create(habit)
            if habit_result.is_ok:
                return Result.ok(self._habit_to_calendar_item(habit_result.value))
            # Type boundary: Extract error from Result[Habit] for Result[CalendarItem]
            return Result.fail(habit_result)

        return Result.fail(Errors.validation(f"Unknown item type: {item_type}", field="item_type"))

    @with_error_handling("reschedule_item", error_type="system", uid_param="item_uid")
    async def reschedule_item(
        self, user_uid: UserUID, item_uid: str, new_start: datetime
    ) -> Result[CalendarItem]:
        """
        Reschedule a calendar item.

        Args:
            item_uid: UID of the item to reschedule,
            new_start: New start time

        Returns:
            Result with updated CalendarItem
        """
        # Parse item type and update accordingly
        if item_uid.startswith("task-"):
            source_uid = item_uid[5:]
            task_get = await self.tasks_service.get(source_uid)
            if task_get.is_ok and task_get.value:
                task = task_get.value
                if task.user_uid != user_uid:
                    # Not the requester's task — 'not found', no UID oracle.
                    return Result.fail(Errors.not_found(f"Item not found: {item_uid}"))
                # Reschedule mutates only the scheduled date (ADR-066 typed update
                # contract: a TaskUpdateIntent, not a rebuilt DTO or field dict).
                task_update = await self.tasks_service.update_task(
                    EntityUID(source_uid), TaskUpdateIntent(scheduled_date=new_start.date())
                )
                if task_update.is_ok:
                    return Result.ok(self._task_to_calendar_item(task_update.value))
                return Result.fail(task_update)

        elif item_uid.startswith("event-"):
            source_uid = item_uid[6:]
            event_get = await self.events_service.get(source_uid)
            if event_get.is_ok and event_get.value:
                event: Event = event_get.value  # Type hint for MyPy protocol inference
                if event.user_uid != user_uid:
                    # Not the requester's event — 'not found', no UID oracle.
                    return Result.fail(Errors.not_found(f"Item not found: {item_uid}"))
                start_dt = event.start_datetime()
                end_dt = event.end_datetime()
                if start_dt is None or end_dt is None:
                    return Result.fail(
                        Errors.validation(
                            message="Event is missing start or end datetime",
                            field="datetime",
                            value=source_uid,
                        )
                    )
                duration = end_dt - start_dt
                new_end = new_start + duration
                # Reschedule mutates only the date/time window (ADR-066 typed update
                # contract: an EventUpdateIntent, not a rebuilt DTO or field dict).
                event_update = await self.events_service.update_event(
                    EntityUID(source_uid),
                    EventUpdateIntent(
                        event_date=new_start.date(),
                        start_time=new_start.time(),
                        end_time=new_end.time(),
                    ),
                )
                if event_update.is_ok:
                    return Result.ok(self._event_to_calendar_item(event_update.value))
                return Result.fail(event_update)

        return Result.fail(Errors.not_found(f"Item not found: {item_uid}"))

    # ========================================================================
    # DATA FETCHING
    # ========================================================================

    async def _fetch_tasks(
        self, user_uid: UserUID, start_date: date, end_date: date, include_completed: bool
    ) -> list[CalendarItem]:
        """
        Fetch tasks and convert to calendar items.

        Refactoring:
        Uses unified query pattern with Cypher-level date filtering.
        BEFORE: Fetched 100 tasks, filtered in Python
        AFTER: Cypher filters by date range at database level
        """
        items: list[CalendarItem] = []

        try:
            logger.info(
                f"Calendar: Fetching tasks for user={user_uid}, range={start_date} to {end_date}"
            )
            result = await self.tasks_service.get_user_items_in_range(
                user_uid=user_uid,
                start_date=start_date,
                end_date=end_date,
                include_completed=include_completed,
            )

            if result.is_ok:
                tasks = result.value
                logger.info(f"Calendar: Found {len(tasks)} tasks in date range")
                items = [self._task_to_calendar_item(task) for task in tasks]

        except NEO4J_EXCEPTIONS as e:
            logger.warning(f"Failed to fetch tasks: {e}")

        return items

    async def _fetch_events(
        self, user_uid: UserUID, start_date: date, end_date: date, include_completed: bool
    ) -> list[CalendarItem]:
        """
        Fetch events and convert to calendar items.

        Refactoring:
        Uses unified query pattern with Cypher-level date filtering.
        BEFORE: Fetched 100 events, filtered in Python
        AFTER: Cypher filters by event_date at database level
        """
        items: list[CalendarItem] = []

        try:
            result = await self.events_service.get_user_items_in_range(
                user_uid=user_uid,
                start_date=start_date,
                end_date=end_date,
                include_completed=include_completed,
            )

            if result.is_ok:
                events = result.value
                items = [self._event_to_calendar_item(event) for event in events]

        except NEO4J_EXCEPTIONS as e:
            logger.warning(f"Failed to fetch events: {e}")

        return items

    async def _fetch_habits(self, user_uid: UserUID) -> list[Habit]:
        """
        Fetch the user's active habits — status-filtered, NEVER date-filtered.

        Habits are ongoing practices with no scheduled date; the calendar projects
        each one across the view range via ``_generate_habit_occurrences``. So we
        need every "alive" habit (active or paused), independent of when it was
        created — hence ``get_active`` (status-only) rather than a dated range query.

        History: this previously called ``get_user_items_in_range``, which silently
        filters by ``created_at``. That made habits vanish from any view window that
        didn't span their creation date — e.g. a habit created July 1 showed on every
        day of the July month view but on *no* day of a late-July week view. Fetching
        by status keeps month and week consistent.
        """
        habits: list[Habit] = []

        try:
            result = await self.habits_service.get_active(user_uid)
            if result.is_ok:
                habits = result.value

        except NEO4J_EXCEPTIONS as e:
            logger.warning(f"Failed to fetch habits: {e}")

        return habits

    # ========================================================================
    # ITEM CONVERSION
    # ========================================================================

    def _task_to_calendar_item(self, task: Task) -> CalendarItem:
        """Convert task to calendar item."""
        # Determine start and end time
        if task.scheduled_date:
            # Scheduled date is a date - combine with default time
            start_time = datetime.combine(task.scheduled_date, datetime.min.time().replace(hour=9))
            end_time = start_time + timedelta(hours=1)  # Default 1 hour
        elif task.due_date:
            start_time = datetime.combine(task.due_date, datetime.min.time())
            end_time = datetime.combine(task.due_date, datetime.max.time())
        else:
            start_time = datetime.now()
            end_time = start_time + timedelta(hours=1)

        # A due-date-only task is a deadline marker; a scheduled task is work.
        # Color communicates the type (per-type palette) so the legend is truthful.
        is_deadline = task.scheduled_date is None and task.due_date is not None
        item_type = CalendarItemType.TASK_DEADLINE if is_deadline else CalendarItemType.TASK_WORK
        color = item_type.get_color()

        return CalendarItem(
            uid=f"task-{task.uid}",
            source_uid=task.uid,
            title=task.title,
            description=task.description or "",
            item_type=item_type,
            start_time=start_time,
            end_time=end_time,
            all_day=is_deadline,
            color=color,
            icon=item_type.get_icon(),
            priority=Priority(task.priority).to_numeric() if task.priority else 1,
            tags=list(task.tags),
            metadata={
                "status": task.status.value if task.status else "pending",
                "priority": task.priority if task.priority else "medium",
            },
        )

    def _event_to_calendar_item(self, event: Event) -> CalendarItem:
        """Convert event to calendar item."""
        # Color by type so the calendar legend stays truthful.
        color = CalendarItemType.EVENT.get_color()

        # Convert Neo4j temporal types to Python types
        start_time_val = convert_neo4j_time(event.start_time)
        end_time_val = convert_neo4j_time(event.end_time)
        event_date_val = convert_neo4j_date(event.event_date)

        # Combine event_date with start_time and end_time
        start_time = (
            datetime.combine(event_date_val, start_time_val)
            if event_date_val and start_time_val
            else datetime.now()
        )
        end_time = (
            datetime.combine(event_date_val, end_time_val)
            if event_date_val and end_time_val
            else (start_time + timedelta(hours=1))
        )

        # Calculate if event has capacity
        has_capacity = True
        if event.max_attendees:
            attendee_count = len(event.attendee_emails) if event.attendee_emails else 0
            has_capacity = attendee_count < event.max_attendees

        return CalendarItem(
            uid=f"event-{event.uid}",
            source_uid=event.uid,
            title=event.title,
            description=event.description or "",
            item_type=CalendarItemType.EVENT,
            start_time=start_time,
            end_time=end_time,
            all_day=False,
            color=color,
            icon=CalendarItemType.EVENT.get_icon(),
            priority=1,
            category=event.event_type if event.event_type else "PERSONAL",
            tags=list(event.tags),
            # Multi-attendee event support
            attendee_emails=event.attendee_emails,
            max_attendees=event.max_attendees,
            location=event.location or "",
            is_online=event.is_online,
            metadata={
                "status": event.status.value if event.status else "scheduled",
                "attendee_count": len(event.attendee_emails) if event.attendee_emails else 0,
                "has_capacity": has_capacity,
            },
        )

    def _habit_to_calendar_item(self, habit: Habit) -> CalendarItem:
        """Convert habit to calendar item."""
        # Habits show up as recurring items
        now = datetime.now()

        return CalendarItem(
            uid=f"habit-{habit.uid}",
            source_uid=habit.uid,
            title=habit.title,
            description=habit.description or "",
            item_type=CalendarItemType.HABIT,
            start_time=now,
            end_time=now + timedelta(minutes=30),  # Default 30 min for habits
            all_day=False,
            color=CalendarItemType.HABIT.get_color(),
            icon=CalendarItemType.HABIT.get_icon(),
            priority=1,
            is_recurring=getattr(habit, "recurrence_pattern", "daily") != "none",
            recurrence_pattern=self._format_recurrence_pattern(habit),
            streak_count=habit.current_streak,
            metadata={
                "status": habit.status.value if habit.status else "active",
                "frequency": habit.target_days_per_week,
            },
        )

    def _generate_habit_occurrences(
        self, habit: Habit, start_date: date, end_date: date
    ) -> list[CalendarOccurrence]:
        """Generate habit occurrences for date range based on recurrence pattern."""
        occurrences = []

        # Get the recurrence pattern from the habit
        pattern = getattr(habit, "recurrence_pattern", "daily")
        # Extract value if it's an enum, otherwise use as-is (handles both enum and string)
        pattern = get_enum_value(pattern)

        self.logger.debug(f"Generating occurrences for habit {habit.uid} with pattern: {pattern}")

        # Never project a habit before it existed. Now that habits are fetched by
        # status (not by created_at range), the "don't show before creation" bound
        # that the old range-fetch implied has to be enforced here — otherwise an
        # active habit would backfill days/weeks/months preceding its inception
        # (e.g. a habit created mid-month appearing on the month's earlier days, or
        # a habit created next month bleeding into current views). Clamp the lower
        # bound to the habit's inception; a habit created after the whole range
        # yields nothing (start > end → the pattern loops below never run).
        inception = self._habit_inception_date(habit)
        if inception and inception > start_date:
            start_date = inception

        # Calculate occurrences based on pattern
        current_date = start_date

        if pattern == "none":
            # One-time only - check if it falls in our range
            habit_start = getattr(habit, "start_date", start_date)
            if isinstance(habit_start, str):
                habit_start = date.fromisoformat(habit_start)
            if start_date <= habit_start <= end_date:
                occurrences.append(self._create_occurrence(habit, habit_start))

        elif pattern == "daily":
            # Every day
            while current_date <= end_date:
                occurrences.append(self._create_occurrence(habit, current_date))
                current_date += timedelta(days=1)

        elif pattern == "weekdays":
            # Monday-Friday (0-4)
            while current_date <= end_date:
                if current_date.weekday() < 5:  # Monday=0, Friday=4
                    occurrences.append(self._create_occurrence(habit, current_date))
                current_date += timedelta(days=1)

        elif pattern == "weekends":
            # Saturday-Sunday (5-6)
            while current_date <= end_date:
                if current_date.weekday() >= 5:  # Saturday=5, Sunday=6
                    occurrences.append(self._create_occurrence(habit, current_date))
                current_date += timedelta(days=1)

        elif pattern == "weekly":
            # Once a week - use the start date's weekday
            habit_start = getattr(habit, "start_date", start_date)
            if isinstance(habit_start, str):
                habit_start = date.fromisoformat(habit_start)

            target_weekday = habit_start.weekday()

            # Find first occurrence in range
            while current_date <= end_date:
                if current_date.weekday() == target_weekday:
                    break
                current_date += timedelta(days=1)

            # Generate weekly occurrences
            while current_date <= end_date:
                occurrences.append(self._create_occurrence(habit, current_date))
                current_date += timedelta(weeks=1)

        elif pattern == "biweekly":
            # Every two weeks
            habit_start = getattr(habit, "start_date", start_date)
            if isinstance(habit_start, str):
                habit_start = date.fromisoformat(habit_start)

            target_weekday = habit_start.weekday()

            # Find first occurrence in range
            while current_date <= end_date:
                if current_date.weekday() == target_weekday:
                    break
                current_date += timedelta(days=1)

            # Generate biweekly occurrences
            while current_date <= end_date:
                occurrences.append(self._create_occurrence(habit, current_date))
                current_date += timedelta(weeks=2)

        elif pattern == "monthly":
            # Once a month - use the start date's day
            habit_start = getattr(habit, "start_date", start_date)
            if isinstance(habit_start, str):
                habit_start = date.fromisoformat(habit_start)

            target_day = habit_start.day

            # Generate monthly occurrences
            current_month = current_date.replace(day=1)
            while (
                current_month.year * 12 + current_month.month <= end_date.year * 12 + end_date.month
            ):
                try:
                    occurrence_date = current_month.replace(
                        day=min(target_day, self._days_in_month(current_month))
                    )
                    if start_date <= occurrence_date <= end_date:
                        occurrences.append(self._create_occurrence(habit, occurrence_date))
                except ValueError:
                    # Handle edge cases (e.g., February 30th)
                    pass

                # Move to next month
                if current_month.month == 12:
                    current_month = current_month.replace(year=current_month.year + 1, month=1)
                else:
                    current_month = current_month.replace(month=current_month.month + 1)

        elif pattern == "quarterly":
            # Every three months
            habit_start = getattr(habit, "start_date", start_date)
            if isinstance(habit_start, str):
                habit_start = date.fromisoformat(habit_start)

            target_day = habit_start.day

            # Start from the quarter containing start_date
            current_month = current_date.replace(day=1)
            while (
                current_month.year * 12 + current_month.month <= end_date.year * 12 + end_date.month
            ):
                try:
                    occurrence_date = current_month.replace(
                        day=min(target_day, self._days_in_month(current_month))
                    )
                    if start_date <= occurrence_date <= end_date:
                        occurrences.append(self._create_occurrence(habit, occurrence_date))
                except ValueError:
                    pass

                # Move to next quarter (3 months)
                new_month = current_month.month + 3
                new_year = current_month.year
                if new_month > 12:
                    new_year += 1
                    new_month -= 12
                current_month = date(new_year, new_month, 1)

        elif pattern == "yearly":
            # Once a year
            habit_start = getattr(habit, "start_date", start_date)
            if isinstance(habit_start, str):
                habit_start = date.fromisoformat(habit_start)

            target_month = habit_start.month
            target_day = habit_start.day

            # Generate yearly occurrences
            for year in range(start_date.year, end_date.year + 1):
                try:
                    occurrence_date = date(year, target_month, target_day)
                    if start_date <= occurrence_date <= end_date:
                        occurrences.append(self._create_occurrence(habit, occurrence_date))
                except ValueError:
                    # Handle leap year edge cases
                    pass

        self.logger.debug(f"Generated {len(occurrences)} occurrences for habit {habit.uid}")
        return occurrences

    def _habit_inception_date(self, habit: Habit) -> date | None:
        """The calendar day a habit began — its ``started_at``, else its ``created_at``.

        Occurrences are projected forward from here so an active, ongoing habit is
        never rendered on days before it existed. Tolerates the created_at native/
        string temporal split (some writers persist an ISO string, others a native
        Neo4j DateTime); returns None only if neither anchor is parseable.
        """
        anchor = habit.started_at or habit.created_at
        converted = convert_neo4j_datetime(anchor)
        if converted is not None:
            return converted.date()
        if isinstance(anchor, str):
            try:
                return datetime.fromisoformat(anchor).date()
            except ValueError:
                return None
        return None

    def _create_occurrence(self, habit: Habit, occurrence_date: date) -> CalendarOccurrence:
        """Create a calendar occurrence for a habit."""
        return CalendarOccurrence(
            calendar_item_uid=habit.uid,
            date=occurrence_date,
            status=CompletionStatus.PENDING,
            notes="",
        )

    def _days_in_month(self, date_obj: date) -> int:
        """Get number of days in a month."""
        if date_obj.month == 12:
            next_month = date_obj.replace(year=date_obj.year + 1, month=1)
        else:
            next_month = date_obj.replace(month=date_obj.month + 1)

        last_day_of_month = next_month - timedelta(days=1)
        return last_day_of_month.day

    def _format_recurrence_pattern(self, habit: Habit) -> str:
        """Format recurrence pattern for display."""
        raw_pattern = getattr(habit, "recurrence_pattern", "daily")
        # Extract value if it's an enum, otherwise use as-is (handles both enum and string)
        pattern = str(get_enum_value(raw_pattern))

        pattern_labels = {
            "none": "One-time",
            "daily": "Daily",
            "weekdays": "Weekdays only",
            "weekends": "Weekends only",
            "weekly": "Weekly",
            "biweekly": "Every 2 weeks",
            "monthly": "Monthly",
            "quarterly": "Quarterly",
            "yearly": "Yearly",
        }

        return pattern_labels.get(pattern, pattern.title())

    # ========================================================================
    # HABIT OCCURRENCE RECORDING
    # ========================================================================

    async def record_habit_occurrence(
        self,
        user_uid: UserUID,
        habit_uid: str,
        on_date: str,
        status: str,
        notes: str | None = None,
    ) -> Result[HabitCompletion]:
        """
        Record a habit occurrence from the calendar view.

        Verifies the requester owns the habit (returns not-found otherwise, no
        UID oracle), then delegates to habits_service.track_habit.
        """
        habit_get = await self.habits_service.get(habit_uid)
        if habit_get.is_error:
            # Propagate genuine backend failures — don't mask them as not-found.
            return Result.fail(habit_get)
        if not habit_get.value or habit_get.value.user_uid != user_uid:
            return Result.fail(Errors.not_found(f"Habit not found: {habit_uid}"))
        request = TrackHabitRequest(
            habit_uid=habit_uid,
            completion_date=on_date,
            notes=notes,
        )
        return await self.habits_service.track_habit(request)
