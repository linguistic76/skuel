"""Calendar Optimization Orchestrator
======================================

Application orchestrator for the Calendar Optimization API. Consolidates
CalendarOptimizationService with TasksService and EventsService into a single
facade, eliminating the multi-service kwargs threading in
create_calendar_optimization_routes.

All dependencies are required — bootstrap raises if any are missing
(Fail-Fast Dependency Philosophy).
"""

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from core.models.type_hints import UserUID
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.services.calendar_optimization_service import (
        CalendarOptimizationService,
        SchedulingStrategy,
    )
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
        calendar_service: "CalendarOptimizationService",
        tasks_service: "TasksService",
        events_service: "EventsService",
    ) -> None:
        self._calendar = calendar_service
        self._tasks = tasks_service
        self._events = events_service

    async def optimize_schedule(
        self,
        user_uid: UserUID,
        target_date: date,
        strategy: "SchedulingStrategy",
    ) -> "Result[Any]":
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

        return await self._calendar.optimize_knowledge_scheduling(
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
            analysis = await self._calendar._analyze_task_cognitive_load(task, [])
            analyses.append(
                {
                    "task_uid": task.uid,
                    "task_title": task.title,
                    "cognitive_load": analysis.to_dict(),
                }
            )

        return task_list, analyses
