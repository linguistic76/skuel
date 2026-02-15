"""
Calendar Service
================

Unified calendar service for displaying tasks, events, and habits in calendar views.
Simplified implementation focusing on essential calendar functionality.

Version: 1.0.0
- v1.0.0: Original unified calendar implementation

DESIGN DECISION (October 3, 2025):
-----------------------------------
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

Phase 1-4 Integration History:
Intelligent scheduling methods (conflict detection, recommendations, context loading)
were explored in October 2025 but removed to keep service simple and focused.
See git history (commit around Oct 3, 2025) for reference implementation if needed.

For intelligent scheduling features, create a dedicated orchestration service
that calls CalendarService for display data.
"""

from datetime import date, datetime, timedelta
from typing import Any

from core.models.enums import Priority
from core.models.enums.ku_enums import KuStatus, KuType
from core.models.event.calendar_models import (
    CalendarData,
    CalendarItem,
    CalendarItemType,
    CalendarOccurrence,
    CalendarView,
)
from core.models.ku.ku import Ku as EventPure
from core.models.ku.ku import Ku as HabitPure
from core.models.ku.ku import Ku as TaskPure
from core.models.ku.ku_dto import KuDTO as EventDTO
from core.models.ku.ku_dto import KuDTO as HabitDTO
from core.models.ku.ku_dto import KuDTO as TaskDTO
from core.services.protocols import get_enum_value

# Import protocol interfaces for dependency injection
from core.services.protocols.domain_protocols import (
    EventsOperations,
    HabitsOperations,
    TasksOperations,
)
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.neo4j_temporal import convert_neo4j_date, convert_neo4j_time
from core.utils.result_simplified import Errors, Result

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


    Source Tag: "calendar_service_explicit"
    - Format: "calendar_service_explicit" for user-created relationships
    - Format: "calendar_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from calendar metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging

    """

    def __init__(
        self,
        tasks_service: TasksOperations | None = None,
        events_service: EventsOperations | None = None,
        habits_service: HabitsOperations | None = None,
    ) -> None:
        """
        Initialize with domain services.

        PARTIAL INITIALIZATION SUPPORTED (Meta-Service Pattern):
        CalendarService is a meta-service that aggregates from multiple domains.
        Unlike domain services, it intentionally supports partial initialization -
        any or all services may be None. Methods gracefully return empty results
        for missing domains rather than failing.

        This design allows:
        - Flexible deployment where not all domains are available
        - Gradual feature rollout
        - Testing individual domain integrations

        Args:
            tasks_service: Service for task operations (optional)
            events_service: Service for event operations (optional)
            habits_service: Service for habit operations (optional)
        """
        self.tasks_service = tasks_service
        self.events_service = events_service
        self.habits_service = habits_service
        self.logger = logger
        logger.debug("CalendarService initialized (meta-service, partial initialization OK)")

    # ========================================================================
    # MAIN PUBLIC INTERFACE
    # ========================================================================

    @with_error_handling("get_calendar_view", error_type="system", uid_param="user_uid")
    async def get_calendar_view(
        self,
        user_uid: str,
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
            Phase 4 Refactoring (October 29, 2025):
            Uses unified query pattern with Cypher-level filtering.
            10-100x performance improvement over in-memory filtering.
        """
        items = []

        # Fetch tasks using unified API (Cypher-level filtering)
        if self.tasks_service:
            task_items = await self._fetch_tasks(user_uid, start_date, end_date, include_completed)
            items.extend(task_items)

        # Fetch events using unified API (Cypher-level filtering)
        if self.events_service:
            event_items = await self._fetch_events(
                user_uid, start_date, end_date, include_completed
            )
            items.extend(event_items)

        # Fetch habits using unified API (status filtering only)
        habit_occurrences = {}
        if self.habits_service:
            habits = await self._fetch_habits(user_uid, start_date, end_date, include_completed)
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
    async def get_item(self, item_uid: str) -> Result[CalendarItem | None]:
        """
        Get a specific calendar item by UID.

        Args:
            item_uid: UID of the calendar item

        Returns:
            Result with CalendarItem or None if not found
        """
        # Handle demo items specially - return them directly
        if item_uid.startswith("demo-"):
            demo_items = []
            if KuType.TASK.value in item_uid:
                demo_items = self._create_demo_tasks()
            elif KuType.EVENT.value in item_uid:
                demo_items = self._create_demo_events()

            # Find matching demo item
            for item in demo_items:
                if item.uid == item_uid:
                    return Result.ok(item)

            return Result.ok(None)

        # Parse item type from UID prefix
        if item_uid.startswith("task-"):
            source_uid = item_uid[5:]  # Remove "task-" prefix
            if self.tasks_service:
                result = await self.tasks_service.get(source_uid)
                if result.is_ok and result.value:
                    return Result.ok(self._task_to_calendar_item(result.value))

        elif item_uid.startswith("event-"):
            source_uid = item_uid[6:]  # Remove "event-" prefix
            if self.events_service:
                result = await self.events_service.get(source_uid)
                if result.is_ok and result.value:
                    return Result.ok(self._event_to_calendar_item(result.value))

        elif item_uid.startswith("habit-"):
            source_uid = item_uid[6:]  # Remove "habit-" prefix
            if self.habits_service:
                result = await self.habits_service.get(source_uid)
                if result.is_ok and result.value:
                    return Result.ok(self._habit_to_calendar_item(result.value))

        return Result.ok(None)

    @with_error_handling("quick_create", error_type="system")
    async def quick_create(
        self, item_type: str, title: str, start_time: datetime, **kwargs: Any
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

        if item_type == KuType.TASK.value and self.tasks_service:
            # Create task
            task_dto = TaskDTO(
                uid="",  # Will be generated
                user_uid=kwargs.get("user_uid", ""),
                title=title,
                description=kwargs.get("description", ""),
                scheduled_date=start_time.date(),
                due_date=start_time.date(),
                status=KuStatus.SCHEDULED,
                priority=Priority.MEDIUM,
            )
            result = await self.tasks_service.create(task_dto)
            if result.is_ok:
                return Result.ok(self._task_to_calendar_item(result.value))
            # Type boundary: Extract error from Result[Task] for Result[CalendarItem]
            return Result.fail(result.expect_error())

        elif item_type == KuType.EVENT.value and self.events_service:
            # Create event
            event_dto = EventDTO(
                uid="",  # Will be generated
                user_uid=kwargs.get("user_uid", ""),
                title=title,
                description=kwargs.get("description", ""),
                event_date=start_time.date(),
                start_time=start_time.time(),
                end_time=end_time.time(),
                status=KuStatus.SCHEDULED,
            )
            result = await self.events_service.create(event_dto)
            if result.is_ok:
                return Result.ok(self._event_to_calendar_item(result.value))
            # Type boundary: Extract error from Result[Ku] for Result[CalendarItem]
            return Result.fail(result.expect_error())

        elif item_type == KuType.HABIT.value and self.habits_service:
            # Create habit
            habit_dto = HabitDTO(
                uid="",  # Will be generated
                user_uid=kwargs.get("user_uid", ""),
                title=title,
                description=kwargs.get("description", ""),
                target_days_per_week=kwargs.get("frequency", 7),
                status=KuStatus.ACTIVE,  # Use KuStatus, not KuStatus
            )
            result = await self.habits_service.create(habit_dto)
            if result.is_ok:
                return Result.ok(self._habit_to_calendar_item(result.value))
            # Type boundary: Extract error from Result[Habit] for Result[CalendarItem]
            return Result.fail(result.expect_error())

        return Result.fail(Errors.validation(f"Unknown item type: {item_type}", field="item_type"))

    @with_error_handling("reschedule_item", error_type="system", uid_param="item_uid")
    async def reschedule_item(self, item_uid: str, new_start: datetime) -> Result[CalendarItem]:
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
            if self.tasks_service:
                # Get existing task
                get_result = await self.tasks_service.get(source_uid)
                if get_result.is_ok and get_result.value:
                    task = get_result.value
                    # Update scheduled time
                    updated_dto = TaskDTO(
                        uid=task.uid,
                        user_uid=task.user_uid,
                        title=task.title,
                        description=task.description,
                        scheduled_date=new_start.date(),
                        due_date=task.due_date,
                        status=task.status,
                        priority=task.priority,
                    )
                    result = await self.tasks_service.update(source_uid, updated_dto)
                    if result.is_ok:
                        return Result.ok(self._task_to_calendar_item(result.value))
                    # Type boundary: Extract error from Result[Task] for Result[CalendarItem]
                    return Result.fail(result.expect_error())

        elif item_uid.startswith("event-"):
            source_uid = item_uid[6:]
            if self.events_service:
                # Get existing event
                get_result = await self.events_service.get(source_uid)
                if get_result.is_ok and get_result.value:
                    event: EventPure = get_result.value  # Type hint for MyPy protocol inference
                    # Calculate new end time based on original duration
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
                    # Update event time
                    updated_dto = EventDTO(
                        uid=event.uid,
                        user_uid=event.user_uid,
                        title=event.title,
                        description=event.description,
                        event_date=new_start.date(),
                        start_time=new_start.time(),
                        end_time=new_end.time(),
                        status=event.status,
                    )
                    result = await self.events_service.update(source_uid, updated_dto)
                    if result.is_ok:
                        return Result.ok(self._event_to_calendar_item(result.value))
                    # Type boundary: Extract error from Result[Ku] for Result[CalendarItem]
                    return Result.fail(result.expect_error())

        return Result.fail(Errors.not_found(f"Item not found: {item_uid}"))

    # ========================================================================
    # DATA FETCHING
    # ========================================================================

    async def _fetch_tasks(
        self, user_uid: str, start_date: date, end_date: date, include_completed: bool
    ) -> list[CalendarItem]:
        """
        Fetch tasks and convert to calendar items.

        Phase 4 Refactoring (October 29, 2025):
        Uses unified query pattern with Cypher-level date filtering.
        BEFORE: Fetched 100 tasks, filtered in Python
        AFTER: Cypher filters by date range at database level
        """
        items: list[CalendarItem] = []

        # Null-safety check
        if not self.tasks_service:
            logger.warning("Calendar: tasks_service is None - cannot fetch tasks")
            return items

        try:
            logger.info(
                f"Calendar: Fetching tasks for user={user_uid}, range={start_date} to {end_date}"
            )
            # Use unified API for Cypher-level filtering
            result = await self.tasks_service.get_user_items_in_range(
                user_uid=user_uid,
                start_date=start_date,
                end_date=end_date,
                include_completed=include_completed,
            )

            logger.info(f"Calendar: Task query result is_ok={result.is_ok}")
            if result.is_ok:
                tasks = result.value  # List[Task] - already filtered by Cypher
                logger.info(f"Calendar: Found {len(tasks)} tasks in date range")
                # Convert all tasks to calendar items (no in-memory filtering needed)
                items = [self._task_to_calendar_item(task) for task in tasks]

                # Add demo data if database is empty
                if not tasks and date.today() >= start_date and date.today() <= end_date:
                    logger.info("Database empty - showing demo tasks")
                    items.extend(self._create_demo_tasks())

        except Exception as e:
            logger.warning(f"Failed to fetch tasks: {e}")

        return items

    async def _fetch_events(
        self, user_uid: str, start_date: date, end_date: date, include_completed: bool
    ) -> list[CalendarItem]:
        """
        Fetch events and convert to calendar items.

        Phase 4 Refactoring (October 29, 2025):
        Uses unified query pattern with Cypher-level date filtering.
        BEFORE: Fetched 100 events, filtered in Python
        AFTER: Cypher filters by event_date at database level
        """
        items: list[CalendarItem] = []

        # Null-safety check
        if not self.events_service:
            return items

        try:
            # Use unified API for Cypher-level filtering
            result = await self.events_service.get_user_items_in_range(
                user_uid=user_uid,
                start_date=start_date,
                end_date=end_date,
                include_completed=include_completed,
            )

            if result.is_ok:
                events = result.value  # List[Event] - already filtered by Cypher
                # Convert all events to calendar items (no in-memory filtering needed)
                items = [self._event_to_calendar_item(event) for event in events]

                # Add demo data if database is empty
                if not events and date.today() >= start_date and date.today() <= end_date:
                    logger.info("Database empty - showing demo events")
                    items.extend(self._create_demo_events())

        except Exception as e:
            logger.warning(f"Failed to fetch events: {e}")

        return items

    async def _fetch_habits(
        self, user_uid: str, start_date: date, end_date: date, include_completed: bool
    ) -> list[HabitPure]:
        """
        Fetch active habits.

        Phase 4 Refactoring (October 29, 2025):
        Uses unified query pattern with Cypher-level status filtering.
        BEFORE: Fetched 100 habits, filtered by is_active() in Python
        AFTER: Cypher filters by status (excludes ARCHIVED) at database level

        Note: Habits don't use date filtering (ongoing practices), but we maintain
        the unified interface signature for consistency.
        """
        habits: list[HabitPure] = []

        # Null-safety check
        if not self.habits_service:
            return habits

        try:
            # Use unified API for Cypher-level status filtering
            result = await self.habits_service.get_user_items_in_range(
                user_uid=user_uid,
                start_date=start_date,  # Ignored for habits
                end_date=end_date,  # Ignored for habits
                include_completed=include_completed,
            )

            if result.is_ok:
                habits = result.value  # List[Habit] - already filtered by Cypher

        except Exception as e:
            logger.warning(f"Failed to fetch habits: {e}")

        return habits

    # ========================================================================
    # ITEM CONVERSION
    # ========================================================================

    def _task_to_calendar_item(self, task: TaskPure) -> CalendarItem:
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

        # Get color dynamically from enum methods
        # Prefer status color over priority color for better visual feedback
        if task.status:
            color = task.status.get_color()
        elif task.priority:
            color = Priority(task.priority).get_color()
        else:
            color = "#3B82F6"  # Default blue

        return CalendarItem(
            uid=f"task-{task.uid}",
            source_uid=task.uid,
            title=task.title,
            description=task.description or "",
            item_type=CalendarItemType.TASK_WORK,
            start_time=start_time,
            end_time=end_time,
            all_day=task.scheduled_date is None and task.due_date is not None,
            color=color,
            icon=CalendarItemType.TASK_WORK.get_icon(),
            priority=Priority(task.priority).to_numeric() if task.priority else 1,
            tags=task.tags or [],
            metadata={
                "status": task.status.value if task.status else "pending",
                "priority": task.priority if task.priority else "medium",
            },
        )

    def _event_to_calendar_item(self, event: EventPure) -> CalendarItem:
        """Convert event to calendar item."""
        # Get color dynamically from status enum
        color = event.status.get_color() if event.status else "#3B82F6"

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
            tags=event.tags or [],
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

    def _habit_to_calendar_item(self, habit: HabitPure) -> CalendarItem:
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
            color="#8B5CF6",  # Purple for habits (could be status-based in future)
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
        self, habit: HabitPure, start_date: date, end_date: date
    ) -> list[CalendarOccurrence]:
        """Generate habit occurrences for date range based on recurrence pattern."""
        occurrences = []

        # Get the recurrence pattern from the habit
        pattern = getattr(habit, "recurrence_pattern", "daily")
        # Extract value if it's an enum, otherwise use as-is (handles both enum and string)
        pattern = get_enum_value(pattern)

        self.logger.debug(f"Generating occurrences for habit {habit.uid} with pattern: {pattern}")

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

    def _create_occurrence(self, habit: HabitPure, occurrence_date: date) -> CalendarOccurrence:
        """Create a calendar occurrence for a habit."""
        return CalendarOccurrence(
            calendar_item_uid=habit.uid,
            date=occurrence_date,
            status="pending",  # Will be updated from actual occurrence data
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

    def _format_recurrence_pattern(self, habit: HabitPure) -> str:
        """Format recurrence pattern for display."""
        pattern = getattr(habit, "recurrence_pattern", "daily")
        # Extract value if it's an enum, otherwise use as-is (handles both enum and string)
        pattern = get_enum_value(pattern)

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
    # DEMO DATA (for empty database)
    # ========================================================================

    def _create_demo_tasks(self) -> list[CalendarItem]:
        """Create demo tasks when database is empty."""
        today = date.today()
        datetime.now()

        return [
            CalendarItem(
                uid="demo-task-1",
                source_uid="demo-task-1",
                title="Review calendar implementation",
                description="Check calendar vs events consolidation",
                item_type=CalendarItemType.TASK_WORK,
                start_time=datetime.combine(today, datetime.min.time().replace(hour=10)),
                end_time=datetime.combine(today, datetime.min.time().replace(hour=11)),
                all_day=False,
                color="#3B82F6",
                icon="📋",
                priority=2,
                tags=["development", "calendar"],
                metadata={"status": "pending", "priority": "high", "demo": True},
            ),
            CalendarItem(
                uid="demo-task-2",
                source_uid="demo-task-2",
                title="Add multi-attendee support",
                description="Implement attendee management for events",
                item_type=CalendarItemType.TASK_WORK,
                start_time=datetime.combine(today, datetime.min.time().replace(hour=15)),
                end_time=datetime.combine(today, datetime.min.time().replace(hour=16)),
                all_day=False,
                color="#F59E0B",
                icon="📋",
                priority=1,
                tags=["feature", "events"],
                metadata={"status": "pending", "priority": "medium", "demo": True},
            ),
        ]

    def _create_demo_events(self) -> list[CalendarItem]:
        """Create demo events when database is empty."""
        today = date.today()
        datetime.now()

        return [
            CalendarItem(
                uid="demo-event-1",
                source_uid="demo-event-1",
                title="Team Standup",
                description="Daily team sync meeting",
                item_type=CalendarItemType.EVENT,
                start_time=datetime.combine(today, datetime.min.time().replace(hour=9)),
                end_time=datetime.combine(today, datetime.min.time().replace(hour=9, minute=30)),
                all_day=False,
                color="#10B981",
                icon="📅",
                priority=1,
                category="meeting",
                tags=["team", "recurring"],
                attendee_emails=("team@skuel.com",),
                location="Conference Room A",
                is_online=False,
                metadata={"status": "scheduled", "demo": True},
            ),
            CalendarItem(
                uid="demo-event-2",
                source_uid="demo-event-2",
                title="Project Review",
                description="Review clean architecture implementation",
                item_type=CalendarItemType.EVENT,
                start_time=datetime.combine(today, datetime.min.time().replace(hour=14)),
                end_time=datetime.combine(today, datetime.min.time().replace(hour=15)),
                all_day=False,
                color="#8B5CF6",
                icon="📅",
                priority=2,
                category="meeting",
                tags=["project", "review"],
                attendee_emails=("alice@skuel.com", "bob@skuel.com", "charlie@skuel.com"),
                max_attendees=5,
                location="",
                is_online=True,
                metadata={
                    "status": "scheduled",
                    "demo": True,
                    "attendee_count": 3,
                    "has_capacity": True,
                    "meeting_url": "https://meet.example.com/project-review",
                },
            ),
        ]
