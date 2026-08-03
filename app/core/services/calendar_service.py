"""
Calendar Service
================

Unified calendar service for displaying tasks, events, habits, and goal
milestones in calendar views. Simplified implementation focusing on essential
calendar functionality.

DESIGN DECISION (October 3, 2025):
----------------------------------
This service intentionally keeps a SIMPLE, BASIC, FUNDAMENTAL design.

Core Responsibilities:
1. Display calendar items (tasks, events, habits, goal milestones)
2. Provide day/week/month views
3. Reschedule tasks/events and record habit completions from the calendar
4. Habit recurrence projection

Creation is NOT a calendar concern: the day lens (/today/{date}) is the acting
surface for adding tasks (act-from arc C6) — it creates through TasksService, so
the calendar's former multi-type ``quick_create`` was deleted as superseded.

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

from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from core.models.type_hints import EntityUID, UserUID

if TYPE_CHECKING:
    from core.services.habits_service import HabitsService

from core.models.enums import Priority
from core.models.enums.entity_enums import EntityType
from core.models.enums.habit_enums import CompletionStatus
from core.models.event.calendar_models import (
    CalendarData,
    CalendarItem,
    CalendarItemType,
    CalendarOccurrence,
    CalendarView,
    parse_calendar_item_uid,
)
from core.models.event.event import Event
from core.models.event.event_update_intent import EventUpdateIntent
from core.models.goal.goal import Goal
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
    GoalsOperations,
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

logger = get_logger("skuel.services.calendar")


def _planning_item_start(item: CalendarItem) -> datetime:
    """Chronological sort key for planning-item lists (named — SKUEL012)."""
    return item.start_time


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
    - Task, event, habit, and goal-milestone integration
    - Habit recurrence projection
    - Color and icon styling

    This is a meta-service: it delegates all graph queries to the injected domain
    services (TasksOperations, EventsOperations, HabitsService, GoalsOperations).
    It does not write Cypher directly.
    """

    def __init__(
        self,
        tasks_service: TasksOperations,
        events_service: EventsOperations,
        habits_service: HabitsService,
        goals_service: GoalsOperations,
    ) -> None:
        """
        Initialize with required domain services.

        All four domain services are required — fail-fast if any is missing.

        Args:
            tasks_service: Service for task operations
            events_service: Service for event operations
            habits_service: Service for habit operations
            goals_service: Service for goal operations (Milestone chips)
        """
        self.tasks_service = tasks_service
        self.events_service = events_service
        self.habits_service = habits_service
        self.goals_service = goals_service
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

        # Fetch goals as all-day Milestone markers on their target_date
        goal_items = await self._fetch_goals(user_uid, start_date, end_date, include_completed)
        items.extend(goal_items)

        # Fetch habits (ongoing practices — status-filtered, never date-filtered)
        habit_occurrences = {}
        habits = await self._fetch_habits(user_uid, include_completed)
        for habit in habits:
            # Add habit as calendar item
            items.append(self._habit_to_calendar_item(habit))
            # Generate occurrences for the date range, with real per-day
            # completion state (N small queries over few live habits is fine;
            # bulk plumbing only if habit count grows — act-from arc C3).
            completed_dates = await self._fetch_completed_dates(habit.uid, start_date, end_date)
            occurrences = self._generate_habit_occurrences(
                habit, start_date, end_date, completed_dates
            )
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

    @with_error_handling("get_planning_items", error_type="system", uid_param="user_uid")
    async def get_planning_items(
        self,
        user_uid: UserUID,
        start_date: date,
        end_date: date,
    ) -> Result[list[CalendarItem]]:
        """The range's plannable items — tasks + events + goal Milestones, no habits.

        Producer for the weekly-note read panel (periodic-notes arc S3): the
        vault plans, the app shows. Composes the SAME internal fetches as the
        calendar grid, so the due-OR-scheduled task semantics (act-from arc C2)
        can never drift between the two surfaces. Habits are deliberately
        excluded — daily recurrence is calendar texture, not weekly planning
        matter (v1 ruling) — and each fetch degrades to empty on failure,
        matching the grid's best-effort display contract.
        """
        task_items = await self._fetch_tasks(user_uid, start_date, end_date, False)
        event_items = await self._fetch_events(user_uid, start_date, end_date, False)
        goal_items = await self._fetch_goals(user_uid, start_date, end_date, False)
        items = [*task_items, *event_items, *goal_items]
        items.sort(key=_planning_item_start)
        return Result.ok(items)

    @with_error_handling("get_item", error_type="system", uid_param="item_uid")
    async def get_item(
        self, user_uid: UserUID, item_uid: str, on_date: date | None = None
    ) -> Result[CalendarItem | None]:
        """
        Get a specific calendar item by UID.

        Args:
            item_uid: UID of the calendar item
            on_date: For habit items, the occurrence day the caller clicked —
                the returned item is stamped with that day and its completion
                state (``occurrence_data``) so the modal shows THAT day, never
                a reconstruction from "today". Ignored for non-habit items,
                which carry their own real dates.

        Returns:
            Result with CalendarItem or None if not found
        """
        # One wire-format parse (parse_calendar_item_uid), typed dispatch after.
        parsed = parse_calendar_item_uid(item_uid)
        if parsed is None:
            return Result.ok(None)
        kind, source_uid = parsed

        if kind is EntityType.TASK:
            task_result = await self.tasks_service.get(source_uid)
            if task_result.is_error:
                # A failed read is not a missing item — propagate it.
                return Result.fail(task_result)
            if task_result.value:
                if task_result.value.user_uid != user_uid:
                    return Result.ok(None)  # not the requester's — treat as not found
                return Result.ok(self._task_to_calendar_item(task_result.value))

        elif kind is EntityType.EVENT:
            event_result = await self.events_service.get(source_uid)
            if event_result.is_error:
                # A failed read is not a missing item — propagate it.
                return Result.fail(event_result)
            if event_result.value:
                if event_result.value.user_uid != user_uid:
                    return Result.ok(None)  # not the requester's — treat as not found
                return Result.ok(self._event_to_calendar_item(event_result.value))

        elif kind is EntityType.GOAL:
            goal_result = await self.goals_service.get(source_uid)
            if goal_result.is_error:
                # A failed read is not a missing item — propagate it.
                return Result.fail(goal_result)
            if goal_result.value:
                if goal_result.value.user_uid != user_uid:
                    return Result.ok(None)  # not the requester's — treat as not found
                return Result.ok(self._goal_to_calendar_item(goal_result.value))

        elif kind is EntityType.HABIT:
            habit_result = await self.habits_service.get(source_uid)
            if habit_result.is_error:
                # A failed read is not a missing item — propagate it.
                return Result.fail(habit_result)
            if habit_result.value:
                if habit_result.value.user_uid != user_uid:
                    return Result.ok(None)  # not the requester's — treat as not found
                item = self._habit_to_calendar_item(habit_result.value)
                # Stamp only genuine occurrence days: an off-schedule ?date=
                # (hand-crafted URL) yields the unstamped, display-only modal —
                # no Mark Complete for a day the habit never occurs on.
                if on_date is not None and self._is_occurrence_day(habit_result.value, on_date):
                    stamped = await self._stamp_habit_occurrence(item, source_uid, on_date)
                    if stamped.is_error:
                        return Result.fail(stamped)
                    item = stamped.value
                return Result.ok(item)

        return Result.ok(None)

    def _is_occurrence_day(self, habit: Habit, day: date) -> bool:
        """Whether the habit's recurrence projects an occurrence on ``day``.

        The same generator that renders chips decides — one projection truth
        for inception clamp, recurrence end, and cadence.
        """
        return any(occ.date == day for occ in self._generate_habit_occurrences(habit, day, day))

    async def _stamp_habit_occurrence(
        self, item: CalendarItem, habit_uid: str, on_date: date
    ) -> Result[CalendarItem]:
        """Scope a habit calendar item to one occurrence day.

        Replaces the now()-stamped stub times with the occurrence day (all-day)
        and records the day + its completion state in ``occurrence_data`` — the
        contract habit chips and the item-details modal share.

        Unlike the grid's best-effort ``_fetch_completed_dates``, a failed
        completions read here PROPAGATES: this stamp drives an actionable
        modal, and rendering an already-done day as PENDING would offer a
        second "Mark Complete" for it.
        """
        completions = await self._read_completions(habit_uid, on_date, on_date)
        if completions.is_error:
            return Result.fail(completions)
        done = any(self._completion_day(c) == on_date for c in completions.value)
        status = CompletionStatus.DONE if done else CompletionStatus.PENDING
        day_start = datetime.combine(on_date, datetime.min.time())
        return Result.ok(
            replace(
                item,
                all_day=True,
                start_time=day_start,
                end_time=day_start,
                occurrence_data={"date": on_date.isoformat(), "status": status.value},
            )
        )

    @with_error_handling("reschedule_item", error_type="system", uid_param="item_uid")
    async def reschedule_item(
        self, user_uid: UserUID, item_uid: str, new_start: datetime
    ) -> Result[CalendarItem]:
        """
        Reschedule a calendar item to a new start.

        Moves the date that PLACES the item on the calendar: a scheduled task
        moves ``scheduled_date`` (refused past the task's own due_date —
        creation forbids that ordering); a due-only deadline task moves
        ``due_date`` and stays a deadline; an event moves its date + start
        time and keeps its duration (refused when the preserved duration
        would cross midnight — the Event model is single-day). Owner-scoped:
        any other user's item — and any non task/event id (habits recur and
        goal target dates move on the goals surface — neither reschedules
        here) — is not-found.

        Args:
            item_uid: UID of the item to reschedule,
            new_start: New start time

        Returns:
            Result with updated CalendarItem
        """
        # One wire-format parse (parse_calendar_item_uid), typed dispatch after.
        parsed = parse_calendar_item_uid(item_uid)
        if parsed is None:
            return Result.fail(Errors.not_found(f"Item not found: {item_uid}"))
        kind, source_uid = parsed

        if kind is EntityType.TASK:
            task_get = await self.tasks_service.get(source_uid)
            if task_get.is_error:
                # A failed read is not a missing item — propagate so the
                # caller retries instead of seeing a false 'not found'.
                return Result.fail(task_get)
            if task_get.value:
                task = task_get.value
                if task.user_uid != user_uid:
                    # Not the requester's task — 'not found', no UID oracle.
                    return Result.fail(Errors.not_found(f"Item not found: {item_uid}"))
                # Move the date that PLACES the task on the calendar (ADR-066
                # typed update contract: a TaskUpdateIntent, not a rebuilt DTO
                # or field dict). A due-only task renders as a deadline chip —
                # moving it must move due_date itself; writing scheduled_date
                # would silently convert the deadline into a work chip while
                # the real due date stayed behind. A scheduled task moves
                # scheduled_date (an existing due_date is a separate fact).
                if task.scheduled_date is None and task.due_date is not None:
                    task_recurrence_end = convert_neo4j_date(task.recurrence_end_date)
                    if task_recurrence_end is not None and new_start.date() >= task_recurrence_end:
                        # Creation forbids due_date on/after recurrence_end_date
                        # (validate_recurrence_end_after_start) and the update
                        # path doesn't recheck — refuse rather than persist a
                        # recurrence window that ends before it starts.
                        return Result.fail(
                            Errors.validation(
                                message=(
                                    "New date is not before the recurrence end "
                                    f"({task_recurrence_end.isoformat()}) — edit the task "
                                    "to change its recurrence"
                                ),
                                field="new_start",
                                value=new_start.isoformat(),
                            )
                        )
                    intent = TaskUpdateIntent(due_date=new_start.date())
                else:
                    if task.due_date is not None and new_start.date() > task.due_date:
                        # Creation forbids due_date < scheduled_date
                        # (TaskCreateRequest.validate_due_after_scheduled) and
                        # the update path doesn't recheck — refuse rather than
                        # persist work scheduled after its own deadline.
                        return Result.fail(
                            Errors.validation(
                                message=(
                                    "Work date would pass the task's deadline "
                                    f"({task.due_date.isoformat()}) — edit the task "
                                    "to move the deadline"
                                ),
                                field="new_start",
                                value=new_start.isoformat(),
                            )
                        )
                    intent = TaskUpdateIntent(scheduled_date=new_start.date())
                task_update = await self.tasks_service.update_task(EntityUID(source_uid), intent)
                if task_update.is_ok:
                    return Result.ok(self._task_to_calendar_item(task_update.value))
                return Result.fail(task_update)

        elif kind is EntityType.EVENT:
            event_get = await self.events_service.get(source_uid)
            if event_get.is_error:
                # A failed read is not a missing item — propagate so the
                # caller retries instead of seeing a false 'not found'.
                return Result.fail(event_get)
            if event_get.value:
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
                if new_end.date() != new_start.date():
                    # The Event model is single-day (one event_date + two
                    # times) — an end past midnight would persist end_time
                    # BEFORE start_time and corrupt duration everywhere.
                    return Result.fail(
                        Errors.validation(
                            message=(
                                "Event duration crosses midnight — choose an earlier start time"
                            ),
                            field="new_start",
                            value=new_start.isoformat(),
                        )
                    )
                recurrence_end = convert_neo4j_date(event.recurrence_end_date)
                if recurrence_end is not None and new_start.date() >= recurrence_end:
                    # Creation forbids event_date on/after recurrence_end_date
                    # (validate_recurrence_end_after_start) and the update
                    # path doesn't recheck — refuse rather than persist a
                    # recurrence window that ends before it starts.
                    return Result.fail(
                        Errors.validation(
                            message=(
                                "New date is not before the recurrence end "
                                f"({recurrence_end.isoformat()}) — edit the event "
                                "to change its recurrence"
                            ),
                            field="new_start",
                            value=new_start.isoformat(),
                        )
                    )
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

        Fetches by due_date OR scheduled_date (calendar-only override of Tasks'
        configured due_date field): ``_task_to_calendar_item`` renders scheduled
        tasks as work chips, so a scheduled-only task must be fetched too — with
        due_date alone it could never render (act-from arc C2). Other range
        consumers keep the DomainConfig default.
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
                date_field=["due_date", "scheduled_date"],
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

    async def _fetch_goals(
        self, user_uid: UserUID, start_date: date, end_date: date, include_completed: bool
    ) -> list[CalendarItem]:
        """
        Fetch goals with a target date in range and convert to Milestone items.

        Goals place on the calendar by ``target_date`` (the Goals DomainConfig
        date field, so the plain range fetch works unmodified); a goal without
        a target date has no calendar placement and is never fetched. Every
        legend entry now has a producer (act-from arc C5).
        """
        items: list[CalendarItem] = []

        try:
            result = await self.goals_service.get_user_items_in_range(
                user_uid=user_uid,
                start_date=start_date,
                end_date=end_date,
                include_completed=include_completed,
            )

            if result.is_ok:
                items = [self._goal_to_calendar_item(goal) for goal in result.value]

        except NEO4J_EXCEPTIONS as e:
            logger.warning(f"Failed to fetch goals: {e}")

        return items

    async def _fetch_habits(
        self, user_uid: UserUID, include_completed: bool = False
    ) -> list[Habit]:
        """
        Fetch the user's habits — status-filtered, NEVER date-filtered.

        Habits are ongoing practices with no scheduled date; the calendar projects
        each one across the view range via ``_generate_habit_occurrences``. So we
        need them by status, independent of when they were created — not via a dated
        range query. By default only "alive" habits (active or paused) are returned
        (``get_active``); ``include_completed`` widens to every status (archived /
        completed / cancelled too, via ``get_user_habits``), honouring the same flag
        the task/event fetches already respect for audit/timeline callers.

        History: this previously called ``get_user_items_in_range``, which silently
        filters by ``created_at``. That made habits vanish from any view window that
        didn't span their creation date — e.g. a habit created July 1 showed on every
        day of the July month view but on *no* day of a late-July week view. Fetching
        by status keeps month and week consistent.
        """
        habits: list[Habit] = []

        try:
            result = (
                await self.habits_service.get_user_habits(user_uid)
                if include_completed
                else await self.habits_service.get_active(user_uid)
            )
            if result.is_ok:
                habits = result.value

        except NEO4J_EXCEPTIONS as e:
            logger.warning(f"Failed to fetch habits: {e}")

        return habits

    async def _read_completions(
        self, habit_uid: str, start_date: date, end_date: date
    ) -> Result[list[HabitCompletion]]:
        """The habit's stored completions in [start_date, end_date] (errors propagate)."""
        try:
            return await self.habits_service.completions.get_completions_for_habit(
                habit_uid, start_date=start_date, end_date=end_date
            )
        except NEO4J_EXCEPTIONS as e:
            return Result.fail(
                Errors.database("calendar.read_completions", f"habit {habit_uid}: {e}")
            )

    @staticmethod
    def _completion_day(completion: HabitCompletion) -> date | None:
        """The calendar day a completion landed on.

        Tolerates the native/string temporal split (storage type is decided by
        the writer): native Neo4j DateTime / datetime via the converter, ISO
        strings via fromisoformat.
        """
        completed_at = convert_neo4j_datetime(completion.completed_at)
        if completed_at is None and isinstance(completion.completed_at, str):
            try:
                completed_at = datetime.fromisoformat(completion.completed_at)
            except ValueError:
                return None
        return completed_at.date() if completed_at is not None else None

    async def _fetch_completed_dates(
        self, habit_uid: str, start_date: date, end_date: date
    ) -> set[date]:
        """Days in [start_date, end_date] with a recorded completion for the habit.

        Best-effort like the other calendar GRID fetches: a failed completions
        read logs and returns an empty set (occurrences render PENDING) rather
        than failing the whole view. Display-only degradation is safe because
        the actionable paths do their own strict reads — the modal stamp
        propagates read failures and the completion write is day-idempotent.
        """
        result = await self._read_completions(habit_uid, start_date, end_date)
        if result.is_error:
            logger.warning(f"Failed to fetch completions for habit {habit_uid}: {result.error}")
            return set()
        completed: set[date] = set()
        for completion in result.value:
            day = self._completion_day(completion)
            if day is not None:
                completed.add(day)
        return completed

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

        # Every task is ONE kind — Task (periodic-notes arc E1). A due-date-only
        # task carries the due STATE: an all-day chip with the ⏰/red urgency cue,
        # never a separate legend kind.
        is_due = task.scheduled_date is None and task.due_date is not None
        item_type = CalendarItemType.TASK
        color = item_type.get_color()

        return CalendarItem(
            uid=f"task-{task.uid}",
            source_uid=task.uid,
            title=task.title,
            description=task.description or "",
            item_type=item_type,
            start_time=start_time,
            end_time=end_time,
            all_day=is_due,
            is_due=is_due,
            color=color,
            icon="⏰" if is_due else item_type.get_icon(),
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

    def _goal_to_calendar_item(self, goal: Goal) -> CalendarItem:
        """Convert a goal to an all-day Milestone marker on its target date.

        The one MILESTONE producer in the calendar pipeline — color/icon come
        from the enum so the legend stays truthful. Tolerates a missing/
        unparseable target_date (a hand-crafted ``get_item`` request for a
        dateless goal) by falling back to now, like the task converter.
        """
        target_date = convert_neo4j_date(goal.target_date)
        if target_date is not None:
            start_time = datetime.combine(target_date, datetime.min.time())
            end_time = datetime.combine(target_date, datetime.max.time())
        else:
            start_time = datetime.now()
            end_time = start_time + timedelta(hours=1)

        item_type = CalendarItemType.MILESTONE
        return CalendarItem(
            uid=f"goal-{goal.uid}",
            source_uid=goal.uid,
            title=goal.title,
            description=goal.description or "",
            item_type=item_type,
            start_time=start_time,
            end_time=end_time,
            all_day=True,
            color=item_type.get_color(),
            icon=item_type.get_icon(),
            priority=Priority(goal.priority).to_numeric() if goal.priority else 1,
            tags=list(goal.tags),
            metadata={
                "status": goal.status.value if goal.status else "active",
                "progress": goal.progress_percentage,
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
        self,
        habit: Habit,
        start_date: date,
        end_date: date,
        completed_dates: set[date] | frozenset[date] = frozenset(),
    ) -> list[CalendarOccurrence]:
        """Generate habit occurrences for date range based on recurrence pattern.

        ``completed_dates`` — days carrying a recorded completion (fetched by
        the async caller): those occurrences get DONE status, the rest PENDING,
        so completed days render distinctly from missed ones.
        """
        occurrences = []

        # Get the recurrence pattern from the habit
        pattern = getattr(habit, "recurrence_pattern", "daily")
        # Extract value if it's an enum, otherwise use as-is (handles both enum and string)
        pattern = get_enum_value(pattern)

        self.logger.debug(f"Generating occurrences for habit {habit.uid} with pattern: {pattern}")

        # Anchor recurrence to the habit's inception (started_at, else created_at),
        # NEVER the view window. Habit has no `start_date` field, so the old
        # getattr(habit, "start_date", start_date) silently anchored every pattern
        # to the view's start_date: a weekly habit begun on a Wednesday rendered on
        # the view's first weekday, and biweekly parity reset per view. The habit
        # scheduler (habit_event_scheduler) already anchors to started_at — match it.
        inception = self._habit_inception_date(habit)
        anchor = inception or start_date

        # Never project a habit before it existed. Now that habits are fetched by
        # status (not by a created_at range), the "don't show before creation" bound
        # the old range-fetch implied has to be enforced here — otherwise an active
        # habit would backfill days/weeks/months preceding its inception. Clamp the
        # window's lower bound to the inception; a habit whose inception is after the
        # whole range yields nothing (start > end → the loops below never run).
        if inception and inception > start_date:
            start_date = inception

        # Nor after it stops. A finite habit (recurrence_end_date set, e.g. a
        # PS-spawned habit) that is still ACTIVE now reaches this generator via the
        # status-only fetch, so clamp the upper bound too — else pending occurrences
        # keep rendering past the habit's end. A habit that ended before the window
        # yields nothing (end < start → the loops below never run).
        recurrence_end = self._habit_recurrence_end(habit)
        if recurrence_end is not None and recurrence_end < end_date:
            end_date = recurrence_end

        current_date = start_date

        if pattern == "none":
            # One-time practice — a single occurrence on its inception day.
            if start_date <= anchor <= end_date:
                occurrences.append(self._create_occurrence(habit, anchor))

        elif pattern == "daily":
            while current_date <= end_date:
                occurrences.append(self._create_occurrence(habit, current_date))
                current_date += timedelta(days=1)

        elif pattern == "weekdays":
            while current_date <= end_date:
                if current_date.weekday() < 5:  # Monday=0 … Friday=4
                    occurrences.append(self._create_occurrence(habit, current_date))
                current_date += timedelta(days=1)

        elif pattern == "weekends":
            while current_date <= end_date:
                if current_date.weekday() >= 5:  # Saturday=5, Sunday=6
                    occurrences.append(self._create_occurrence(habit, current_date))
                current_date += timedelta(days=1)

        elif pattern == "weekly":
            # Same weekday as the anchor, every week.
            current_date = self._advance_to_weekday(current_date, anchor.weekday(), end_date)
            while current_date <= end_date:
                occurrences.append(self._create_occurrence(habit, current_date))
                current_date += timedelta(weeks=1)

        elif pattern == "biweekly":
            # Same weekday as the anchor, on the anchor's fixed 14-day parity.
            current_date = self._advance_to_weekday(current_date, anchor.weekday(), end_date)
            if current_date <= end_date and ((current_date - anchor).days // 7) % 2:
                current_date += timedelta(weeks=1)  # shift onto the anchor's cycle
            while current_date <= end_date:
                occurrences.append(self._create_occurrence(habit, current_date))
                current_date += timedelta(weeks=2)

        elif pattern == "monthly":
            # Anchor day-of-month, every month (clamped to each month's length).
            occurrences.extend(
                self._monthly_occurrences(habit, anchor.day, start_date, end_date, step_months=1)
            )

        elif pattern == "quarterly":
            # Anchor day-of-month, every third month on the anchor's phase.
            occurrences.extend(
                self._monthly_occurrences(
                    habit, anchor.day, start_date, end_date, step_months=3, phase_month=anchor
                )
            )

        elif pattern == "yearly":
            # Anchor month + day, once a year.
            for year in range(start_date.year, end_date.year + 1):
                try:
                    occurrence_date = date(year, anchor.month, anchor.day)
                except ValueError:
                    continue  # Feb 29 in a non-leap year — no occurrence that year
                if start_date <= occurrence_date <= end_date:
                    occurrences.append(self._create_occurrence(habit, occurrence_date))

        # Overlay real completion state: an occurrence on a day with a recorded
        # completion is DONE. (The old code hardcoded PENDING in
        # _create_occurrence, so completed days rendered like missed ones.)
        if completed_dates:
            occurrences = [
                replace(occ, status=CompletionStatus.DONE) if occ.date in completed_dates else occ
                for occ in occurrences
            ]

        self.logger.debug(f"Generated {len(occurrences)} occurrences for habit {habit.uid}")
        return occurrences

    def _advance_to_weekday(self, start: date, weekday: int, limit: date) -> date:
        """First date on ``weekday`` (0=Mon) at or after ``start``.

        Returns a date past ``limit`` if the weekday never occurs in range, so the
        caller's ``while d <= limit`` loop simply produces no occurrences.
        """
        d = start
        while d <= limit and d.weekday() != weekday:
            d += timedelta(days=1)
        return d

    def _monthly_occurrences(
        self,
        habit: Habit,
        target_day: int,
        start_date: date,
        end_date: date,
        *,
        step_months: int,
        phase_month: date | None = None,
    ) -> list[CalendarOccurrence]:
        """Occurrences on ``target_day`` of each qualifying month in the range.

        ``step_months`` is the cadence (1 = monthly, 3 = quarterly). ``phase_month``
        anchors that cadence so quarterly stays on the habit's own quarter regardless
        of the view window; None (monthly) accepts every month. ``target_day`` is
        clamped to each month's length (e.g. day 31 → 30 in April, 28/29 in February).
        """
        result: list[CalendarOccurrence] = []
        anchor_index = (
            phase_month.year * 12 + (phase_month.month - 1) if phase_month is not None else 0
        )
        month = start_date.replace(day=1)
        while month.year * 12 + month.month <= end_date.year * 12 + end_date.month:
            month_index = month.year * 12 + (month.month - 1)
            if step_months == 1 or (month_index - anchor_index) % step_months == 0:
                occurrence_date = month.replace(day=min(target_day, self._days_in_month(month)))
                if start_date <= occurrence_date <= end_date:
                    result.append(self._create_occurrence(habit, occurrence_date))
            month = (
                month.replace(year=month.year + 1, month=1)
                if month.month == 12
                else month.replace(month=month.month + 1)
            )
        return result

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

    def _habit_recurrence_end(self, habit: Habit) -> date | None:
        """The last day a finite habit recurs (``recurrence_end_date``), or None.

        Occurrences are not projected past this day. None means the habit recurs
        indefinitely (the common case). Tolerates the date native/string temporal
        split — an ISO date, or an ISO datetime whose date half is taken.
        """
        end = habit.recurrence_end_date
        converted = convert_neo4j_date(end)
        if converted is not None:
            return converted
        if isinstance(end, str):
            try:
                return date.fromisoformat(end[:10])
            except ValueError:
                return None
        return None

    def _create_occurrence(self, habit: Habit, occurrence_date: date) -> CalendarOccurrence:
        """Create a PENDING calendar occurrence for a habit.

        Real per-day status is overlaid afterwards in
        ``_generate_habit_occurrences`` from the fetched completion dates.
        """
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
        notes: str | None = None,
    ) -> Result[HabitCompletion]:
        """
        Record a habit completion for a specific day from the calendar view.

        ``on_date`` is the occurrence day (ISO date string) the user acted on —
        the modal's day, never a server-side "today". Verifies the requester
        owns the habit (returns not-found otherwise, no UID oracle), then
        delegates to habits_service.track_habit.

        Day-idempotent: if that day already carries a completion, the existing
        record is returned and nothing is written — a stale/degraded modal (or
        a double click) must not double-count streaks and totals. The
        idempotency read's failure propagates (never degrades to a write).

        Only genuine occurrence days are completable: a day the habit never
        occurs on (before inception, past its recurrence end, off-cadence) is
        rejected — an invisible completion would still inflate the stats.
        """
        habit_get = await self.habits_service.get(habit_uid)
        if habit_get.is_error:
            # Propagate genuine backend failures — don't mask them as not-found.
            return Result.fail(habit_get)
        if not habit_get.value or habit_get.value.user_uid != user_uid:
            return Result.fail(Errors.not_found(f"Habit not found: {habit_uid}"))
        try:
            day = date.fromisoformat(on_date[:10])
        except ValueError:
            return Result.fail(
                Errors.validation("on_date must be an ISO date", field="on_date", value=on_date)
            )
        if not self._is_occurrence_day(habit_get.value, day):
            return Result.fail(
                Errors.validation("No habit occurrence on this day", field="on_date", value=on_date)
            )
        existing = await self._read_completions(habit_uid, day, day)
        if existing.is_error:
            return Result.fail(existing)
        for completion in existing.value:
            if self._completion_day(completion) == day:
                return Result.ok(completion)  # already complete that day — idempotent
        request = TrackHabitRequest(
            habit_uid=habit_uid,
            completion_date=on_date,
            notes=notes,
        )
        return await self.habits_service.track_habit(request)
