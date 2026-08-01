"""Calendar Optimization Orchestrator
======================================

Application orchestrator for the Calendar Optimization API. Consolidates
CalendarOptimizationService with TasksService and EventsService into a single
facade, eliminating the multi-service kwargs threading in
create_calendar_optimization_routes.

All dependencies are required — bootstrap raises if any are missing
(Fail-Fast Dependency Philosophy).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from core.models.enums.entity_enums import EntityStatus
from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.calendar_optimization import CalendarOptimization, SchedulingStrategy
    from core.services.calendar_optimization_service import CalendarOptimizationService
    from core.services.events_service import EventsService
    from core.services.tasks_service import TasksService

logger = get_logger("skuel.orchestrator.calendar_optimization")


class CalendarOptimizationOrchestrator:
    """Facade for the Calendar Optimization API layer.

    Wraps CalendarOptimizationService with TasksService and EventsService,
    eliminating the multi-service kwargs threading in
    create_calendar_optimization_routes. Route handlers call the orchestrator
    directly — no service references leak into the route layer.

    All dependencies are required — bootstrap raises if any are missing
    (Fail-Fast Dependency Philosophy).
    """

    def __init__(
        self,
        calendar_service: CalendarOptimizationService,
        tasks_service: TasksService,
        events_service: EventsService,
    ) -> None:
        self._calendar = calendar_service
        self._tasks = tasks_service
        self._events = events_service

    async def optimize_schedule(
        self,
        user_uid: UserUID,
        target_date: date,
        strategy: SchedulingStrategy,
    ) -> Result[CalendarOptimization]:
        """Fetch tasks and events for the date, then run scheduling optimisation.

        Partial failures (tasks or events unavailable) degrade gracefully — the
        optimiser runs with whatever data it receives, logging a warning for each
        failed fetch.
        """
        task_list: list[Any] = []
        event_list: list[Any] = []
        next_day = target_date + timedelta(days=1)

        tasks_result = await self._tasks.get_user_items_in_range(
            user_uid=user_uid,
            start_date=target_date,
            end_date=next_day,
            include_completed=False,
        )
        if tasks_result.is_ok:
            task_list = tasks_result.value or []
        else:
            logger.warning(
                "Failed to get tasks for scheduling",
                extra={"date": str(target_date), "error": str(tasks_result.error)},
            )

        events_result = await self._events.get_events_in_range(
            start_date=target_date,
            end_date=next_day,
            user_uid=user_uid,
        )
        if events_result.is_ok:
            event_list = events_result.value or []
        else:
            logger.warning(
                "Failed to get events for scheduling",
                extra={"date": str(target_date), "error": str(events_result.error)},
            )

        return self._calendar.optimize_knowledge_scheduling(
            user_uid=user_uid,
            target_date=target_date,
            tasks=task_list,
            events=event_list,
            knowledge_units=[],
            strategy=strategy,
        )

    async def get_cognitive_load_analyses(
        self,
        user_uid: UserUID,
        target_date: date,
    ) -> tuple[list[Any], list[dict[str, Any]]]:
        """Fetch tasks for the date and compute per-task cognitive load analyses.

        Returns:
            (task_list, analyses) — task_list for count reporting,
            analyses for the response payload.
        """
        task_list: list[Any] = []
        next_day = target_date + timedelta(days=1)

        tasks_result = await self._tasks.get_user_items_in_range(
            user_uid=user_uid,
            start_date=target_date,
            end_date=next_day,
            include_completed=False,
        )
        if tasks_result.is_ok:
            task_list = tasks_result.value or []
        else:
            logger.warning(
                "Failed to get tasks for cognitive load",
                extra={"date": str(target_date), "error": str(tasks_result.error)},
            )

        analyses: list[dict[str, Any]] = []
        for task in task_list:
            analysis = self._calendar._analyze_task_cognitive_load(task, [])
            analyses.append(
                {
                    "task_uid": task.uid,
                    "task_title": task.title,
                    "cognitive_load": analysis.to_dict(),
                }
            )

        return task_list, analyses

    # ========================================================================
    # CROSS-DOMAIN SCHEDULING INTELLIGENCE
    # ========================================================================
    # These methods were previously in EventsSchedulingService, which could only
    # see Events data. They live here because real calendar intelligence requires
    # Tasks + Events together.

    async def get_busy_times(
        self,
        user_uid: UserUID,
        start_date: date,
        end_date: date,
    ) -> Result[dict[str, list[dict[str, str]]]]:
        """Get busy time blocks for a date range, aggregating Events and Tasks.

        Events contribute time-specific blocks (start_time/end_time).
        Tasks contribute date-level blocks (all-day items on scheduled_date or due_date).
        Partial failures degrade gracefully — the other domain's data is still returned.
        """
        busy_times: dict[str, list[dict[str, str]]] = {}

        events_result = await self._events.get_events_in_range(
            start_date=start_date,
            end_date=end_date,
            user_uid=user_uid,
        )
        if events_result.is_ok:
            for event in events_result.value or []:
                if not event.event_date or event.status == EntityStatus.CANCELLED.value:
                    continue
                date_key = event.event_date.isoformat()
                busy_times.setdefault(date_key, []).append(
                    {
                        "source_uid": event.uid,
                        "source_type": "event",
                        "title": event.title,
                        "start_time": event.start_time.isoformat() if event.start_time else "",
                        "end_time": event.end_time.isoformat() if event.end_time else "",
                    }
                )
        else:
            logger.warning(
                "Failed to fetch events for busy times",
                extra={"error": str(events_result.error)},
            )

        tasks_result = await self._tasks.get_user_items_in_range(
            user_uid=user_uid,
            start_date=start_date,
            end_date=end_date,
            include_completed=False,
        )
        if tasks_result.is_ok:
            for task in tasks_result.value or []:
                scheduled = task.scheduled_date or task.due_date
                if not scheduled:
                    continue
                date_key = scheduled.isoformat()
                busy_times.setdefault(date_key, []).append(
                    {
                        "source_uid": task.uid,
                        "source_type": "task",
                        "title": task.title,
                        "start_time": "",
                        "end_time": "",
                    }
                )
        else:
            logger.warning(
                "Failed to fetch tasks for busy times",
                extra={"error": str(tasks_result.error)},
            )

        return Result.ok(busy_times)

    async def get_calendar_density(
        self,
        user_uid: UserUID,
        days_ahead: int = 14,
    ) -> Result[dict[str, Any]]:
        """Calculate calendar density across Tasks and Events.

        Partial failures degrade gracefully — the available domain's count is used.
        """
        start_date = date.today()
        end_date = start_date + timedelta(days=days_ahead)

        events_result = await self._events.get_events_in_range(
            start_date=start_date,
            end_date=end_date,
            user_uid=user_uid,
        )
        events = (
            [e for e in (events_result.value or []) if e.status != EntityStatus.CANCELLED.value]
            if events_result.is_ok
            else []
        )
        if not events_result.is_ok:
            logger.warning(
                "Failed to fetch events for density", extra={"error": str(events_result.error)}
            )

        tasks_result = await self._tasks.get_user_items_in_range(
            user_uid=user_uid,
            start_date=start_date,
            end_date=end_date,
            include_completed=False,
        )
        tasks = tasks_result.value or [] if tasks_result.is_ok else []
        if not tasks_result.is_ok:
            logger.warning(
                "Failed to fetch tasks for density", extra={"error": str(tasks_result.error)}
            )

        total_items = len(events) + len(tasks)
        items_per_day = total_items / days_ahead if days_ahead > 0 else 0

        days_with_events = len({e.event_date for e in events if e.event_date})
        days_with_tasks = len(
            {t.scheduled_date or t.due_date for t in tasks if t.scheduled_date or t.due_date}
        )
        days_with_items = len(
            {e.event_date for e in events if e.event_date}
            | {t.scheduled_date or t.due_date for t in tasks if t.scheduled_date or t.due_date}
        )
        total_scheduled_minutes = sum(e.duration_minutes or 0 for e in events)

        return Result.ok(
            {
                "user_uid": user_uid,
                "days_analyzed": days_ahead,
                "total_events": len(events),
                "total_tasks": len(tasks),
                "total_items": total_items,
                "items_per_day": round(items_per_day, 2),
                "days_with_events": days_with_events,
                "days_with_tasks": days_with_tasks,
                "days_with_items": days_with_items,
                "free_days": days_ahead - days_with_items,
                "total_scheduled_minutes": total_scheduled_minutes,
                "average_minutes_per_day": round(total_scheduled_minutes / days_ahead, 1)
                if days_ahead > 0
                else 0,
                "density_rating": "high"
                if items_per_day > 3
                else ("medium" if items_per_day > 1 else "low"),
            }
        )

    async def suggest_time_slots(
        self,
        user_uid: UserUID,
        target_date: date,
        duration_minutes: int = 60,
        preferred_hours: tuple[int, int] = (9, 18),
    ) -> Result[list[dict[str, Any]]]:
        """Suggest available time slots on a given date.

        Uses Events (which have start_time/end_time) to identify blocked time.
        Tasks are all-day items and do not block specific time slots.
        """
        events_result = await self._events.get_events_in_range(
            start_date=target_date,
            end_date=target_date,
            user_uid=user_uid,
        )
        existing_events = events_result.value or [] if events_result.is_ok else []
        if not events_result.is_ok:
            logger.warning(
                "Failed to fetch events for slot suggestions",
                extra={"error": str(events_result.error)},
            )

        blocked: list[tuple[time, time]] = [
            (e.start_time, e.end_time)
            for e in existing_events
            if e.start_time and e.end_time and e.status != EntityStatus.CANCELLED.value
        ]

        def by_start_time(t: tuple[time, time]) -> time:
            return t[0]

        blocked.sort(key=by_start_time)

        slots: list[dict[str, Any]] = []
        current = time(preferred_hours[0], 0)
        end_of_day = time(preferred_hours[1], 0)

        for block_start, block_end in blocked:
            if current < block_start:
                gap_minutes = (
                    datetime.combine(target_date, block_start)
                    - datetime.combine(target_date, current)
                ).total_seconds() / 60
                if gap_minutes >= duration_minutes:
                    slots.append(
                        {
                            "start_time": current.isoformat(),
                            "end_time": block_start.isoformat(),
                            "available_minutes": int(gap_minutes),
                            "fits_duration": True,
                        }
                    )
            if block_end > current:
                current = block_end

        if current < end_of_day:
            gap_minutes = (
                datetime.combine(target_date, end_of_day) - datetime.combine(target_date, current)
            ).total_seconds() / 60
            if gap_minutes >= duration_minutes:
                slots.append(
                    {
                        "start_time": current.isoformat(),
                        "end_time": end_of_day.isoformat(),
                        "available_minutes": int(gap_minutes),
                        "fits_duration": True,
                    }
                )

        return Result.ok(slots)

    async def find_next_available_slot(
        self,
        user_uid: UserUID,
        duration_minutes: int = 60,
        preferred_hours: tuple[int, int] = (9, 18),
        days_to_search: int = 7,
    ) -> Result[dict[str, Any] | None]:
        """Find the next available time slot across multiple days."""
        current_date = date.today()
        for _ in range(days_to_search):
            slots_result = await self.suggest_time_slots(
                user_uid=user_uid,
                target_date=current_date,
                duration_minutes=duration_minutes,
                preferred_hours=preferred_hours,
            )
            if slots_result.is_ok and slots_result.value:
                slot = slots_result.value[0]
                slot["date"] = current_date.isoformat()
                return Result.ok(slot)
            current_date += timedelta(days=1)
        return Result.ok(None)

    async def check_conflicts(
        self,
        user_uid: UserUID,
        event_date: date,
        start_time: time | None = None,
        end_time: time | None = None,
        exclude_uid: str | None = None,
    ) -> Result[list[Any]]:
        """Check for conflicting Events on the same date/time.

        Returns Events that overlap with the proposed time window.
        Tasks are all-day items and are not included in time-slot conflict detection.
        """
        events_result = await self._events.get_events_in_range(
            start_date=event_date,
            end_date=event_date,
            user_uid=user_uid,
        )
        if events_result.is_error or not events_result.value:
            return Result.ok([])

        conflicts = []
        for event in events_result.value:
            if exclude_uid and event.uid == exclude_uid:
                continue
            if event.status == EntityStatus.CANCELLED.value:
                continue
            if not start_time or not end_time:
                conflicts.append(event)
                continue
            if (
                event.start_time
                and event.end_time
                and start_time < event.end_time
                and end_time > event.start_time
            ):
                conflicts.append(event)

        return Result.ok(conflicts)
