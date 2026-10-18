"""
Visualization Aggregation Service
===================================

Data fetching and aggregation for visualization endpoints.

Fetches data from domain services (tasks, habits, goals),
computes aggregates (completion rates, distributions, streaks),
then delegates to VisualizationService for formatting.

Separation of concerns:
- This service: data fetching + aggregation (graph queries + business logic)
- VisualizationService: pure formatting (Chart.js/Gantt adapters)
"""

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from core.models.enums import EntityStatus
from core.models.type_hints import UserUID
from core.ports.query_types import ChartJsConfig, GanttConfig
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone

if TYPE_CHECKING:
    from core.models.task.task import Task
    from core.services.goals_service import GoalsService
    from core.services.habits_service import HabitsService
    from core.services.tasks_service import TasksService
    from core.services.visualization_service import VisualizationService

logger = get_logger(__name__)


class VisualizationAggregationService:
    """
    Fetch and aggregate domain data for visualization endpoints.

    Owns domain service dependencies for data retrieval. Delegates all
    chart/gantt formatting to VisualizationService.
    """

    def __init__(
        self,
        tasks_service: TasksService,
        habits_service: HabitsService,
        goals_service: GoalsService,
        visualization_service: VisualizationService,
    ) -> None:
        self.tasks_service = tasks_service
        self.habits_service = habits_service
        self.goals_service = goals_service
        self.vis = visualization_service

    # =========================================================================
    # Chart.js Aggregation
    # =========================================================================

    async def get_completion_chart_data(
        self,
        user_uid: UserUID,
        period: str,
    ) -> Result[ChartJsConfig]:
        """Aggregate task completion counts per period, then format for Chart.js."""
        today = today_in(current_zone())

        if period == "week":
            start_date = today - timedelta(days=6)
            labels = [(start_date + timedelta(days=i)).strftime("%a") for i in range(7)]
        elif period == "month":
            start_date = today - timedelta(days=29)
            labels = [(start_date + timedelta(days=i)).strftime("%m/%d") for i in range(0, 30, 3)]
        elif period == "quarter":
            start_date = today - timedelta(days=89)
            labels = [(start_date + timedelta(days=i)).strftime("%m/%d") for i in range(0, 90, 7)]
        else:
            return Result.fail(
                Errors.validation(
                    message="Invalid period. Must be: week, month, or quarter",
                    field="period",
                    value=period,
                )
            )

        result = await self.tasks_service.get_user_items_in_range(
            user_uid=user_uid,
            start_date=start_date,
            end_date=today,
            include_completed=True,
        )

        if result.is_error:
            return Result.fail(result)

        tasks = result.value or []
        completed: list[int] = []
        total: list[int] = []

        if period == "week":
            for i in range(7):
                d = start_date + timedelta(days=i)
                day_tasks = [t for t in tasks if self._task_due_on(t, d)]
                total.append(len(day_tasks))
                completed.append(sum(1 for t in day_tasks if self._is_completed(t)))
        elif period == "month":
            for i in range(0, 30, 3):
                d_start = start_date + timedelta(days=i)
                d_end = d_start + timedelta(days=2)
                period_tasks = [t for t in tasks if self._task_in_range(t, d_start, d_end)]
                total.append(len(period_tasks))
                completed.append(sum(1 for t in period_tasks if self._is_completed(t)))
        else:  # quarter
            for i in range(0, 90, 7):
                d_start = start_date + timedelta(days=i)
                d_end = d_start + timedelta(days=6)
                period_tasks = [t for t in tasks if self._task_in_range(t, d_start, d_end)]
                total.append(len(period_tasks))
                completed.append(sum(1 for t in period_tasks if self._is_completed(t)))

        return self.vis.format_completion_chart(completed, total, labels)

    async def get_priority_distribution_chart_data(
        self,
        user_uid: UserUID,
    ) -> Result[ChartJsConfig]:
        """Aggregate active task counts by priority, then format for Chart.js."""
        distribution: dict[str, int] = {}

        result = await self.tasks_service.search.get_by_status(
            user_uid=user_uid,
            status="active",
        )

        if result.is_error:
            return Result.fail(result)

        for task in result.value or []:
            if task.priority:
                key = str(task.priority)
                distribution[key] = distribution.get(key, 0) + 1

        if not distribution:
            return Result.fail(
                Errors.not_found("Chart data", "task-priority", reason="no active tasks")
            )

        return self.vis.format_distribution_chart(
            distribution, "Task Priority Distribution", "doughnut"
        )

    async def get_streak_chart_data(
        self,
        user_uid: UserUID,
    ) -> Result[ChartJsConfig]:
        """Aggregate active habit streak data, then format for Chart.js."""
        result = await self.habits_service.search.get_by_status(
            user_uid=user_uid,
            status="active",
        )

        if result.is_error:
            return Result.fail(result)

        streaks: list[dict[str, Any]] = [
            {
                "name": h.title,
                "current": h.current_streak or 0,
                "best": h.best_streak or 0,
            }
            for h in (result.value or [])
        ]

        if not streaks:
            return Result.fail(
                Errors.not_found("Chart data", "habit-streaks", reason="no active habits")
            )

        return self.vis.format_streak_chart(streaks)

    async def get_status_distribution_chart_data(
        self,
        user_uid: UserUID,
        days_back: int = 30,
    ) -> Result[ChartJsConfig]:
        """Aggregate task counts by status over a date window, then format for Chart.js."""
        distribution: dict[str, int] = {}
        today = today_in(current_zone())

        result = await self.tasks_service.get_user_items_in_range(
            user_uid=user_uid,
            start_date=today - timedelta(days=days_back),
            end_date=today,
            include_completed=True,
        )

        if result.is_error:
            return Result.fail(result)

        for task in result.value or []:
            key = str(task.status)
            distribution[key] = distribution.get(key, 0) + 1

        if not distribution:
            return Result.fail(Errors.not_found("Chart data", "task-status", reason="no tasks"))

        return self.vis.format_distribution_chart(distribution, "Task Status Distribution", "pie")

    # =========================================================================
    # Frappe Gantt Aggregation
    # =========================================================================

    async def get_tasks_gantt_data(
        self,
        user_uid: UserUID,
        project: str | None = None,
    ) -> Result[GanttConfig]:
        """Fetch tasks + prerequisites (optionally filtered by project), then format for Gantt."""
        today = today_in(current_zone())

        result = await self.tasks_service.get_user_items_in_range(
            user_uid=user_uid,
            start_date=today - timedelta(days=7),
            end_date=today + timedelta(days=60),
            include_completed=True,
        )

        if result.is_error:
            return Result.fail(result)

        tasks = result.value or []
        if project:
            tasks = [t for t in tasks if t.project == project]

        # Only emit dependencies that point at a task actually in the chart — a
        # prerequisite outside the date window (or filtered out by `project`) would
        # otherwise be a dangling id; Frappe Gantt dereferences a missing dependency
        # bar (undefined) when the dependent bar is dragged.
        rendered_ids = {task.uid for task in tasks}
        dependencies: dict[str, list[str]] = {}
        for task in tasks:
            # Prerequisite tasks live on the (Task)-[:DEPENDS_ON]->(prereq) edge;
            # the generic service reader keys it as "prerequisite_tasks" and
            # returns the prerequisite UIDs directly. A per-task failure is
            # skipped so one bad lookup never drops the whole Gantt.
            deps_result = await self.tasks_service.relationships.get_related_uids(
                "prerequisite_tasks", task.uid
            )
            if deps_result.is_ok and deps_result.value:
                in_view = [uid for uid in deps_result.value if uid in rendered_ids]
                if in_view:
                    dependencies[task.uid] = in_view

        return self.vis.format_for_gantt(tasks, dependencies)

    async def get_goal_gantt_data(
        self,
        user_uid: UserUID,
        goal_uid: str,
    ) -> Result[GanttConfig]:
        """Fetch goal + related tasks, then format for Gantt."""
        goal_result = await self.goals_service.get_for_user(goal_uid, user_uid)

        if goal_result.is_error:
            return Result.fail(goal_result)

        # get_tasks_for_goal returns full Task models, which format_goal_gantt needs.
        # It traverses the CONTRIBUTES_TO_GOAL edge, so a task linked at any door —
        # vault-ingested ones included — is on the chart.
        tasks: list[Task] = []
        tasks_result = await self.tasks_service.get_tasks_for_goal(goal_uid, user_uid)
        if tasks_result.is_ok:
            tasks = list(tasks_result.value or [])

        return self.vis.format_goal_gantt(goal_result.value, tasks)

    # =========================================================================
    # Task Date Helpers
    # =========================================================================

    def _task_due_on(self, task: Task, d: date) -> bool:
        """Return True if the task's due_date or scheduled_date falls on d."""
        return d in (task.due_date, task.scheduled_date)

    def _task_in_range(self, task: Task, start: date, end: date) -> bool:
        """Return True if the task's due_date or scheduled_date falls within [start, end]."""
        return any(
            day is not None and start <= day <= end for day in (task.due_date, task.scheduled_date)
        )

    def _is_completed(self, task: Task) -> bool:
        """Return True if the task status is COMPLETED."""
        return task.status == EntityStatus.COMPLETED
