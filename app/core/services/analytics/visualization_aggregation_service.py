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
from enum import Enum
from typing import Any

from core.models.enums import EntityStatus
from core.models.type_hints import UserUID
from core.ports.query_types import ChartJsConfig, GanttConfig
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class VisualizationAggregationService:
    """
    Fetch and aggregate domain data for visualization endpoints.

    Owns domain service dependencies for data retrieval. Delegates all
    chart/gantt formatting to VisualizationService.
    """

    def __init__(
        self,
        tasks_service: Any,
        habits_service: Any,
        goals_service: Any,
        visualization_service: Any,
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
        today = date.today()

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
            return result

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
            return result

        for task in result.value or []:
            priority = getattr(task, "priority", None)
            if priority:
                key = priority.value if isinstance(priority, Enum) else str(priority)
                distribution[key] = distribution.get(key, 0) + 1

        if not distribution:
            return Result.fail(Errors.not_found("No active tasks found for priority distribution"))

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
                "name": getattr(h, "title", "Habit"),
                "current": getattr(h, "current_streak", 0) or 0,
                "best": getattr(h, "best_streak", 0) or 0,
            }
            for h in (result.value or [])
        ]

        if not streaks:
            return Result.fail(Errors.not_found("No active habits found for streak chart"))

        return self.vis.format_streak_chart(streaks)

    async def get_status_distribution_chart_data(
        self,
        user_uid: UserUID,
        days_back: int = 30,
    ) -> Result[ChartJsConfig]:
        """Aggregate task counts by status over a date window, then format for Chart.js."""
        distribution: dict[str, int] = {}
        today = date.today()

        result = await self.tasks_service.get_user_items_in_range(
            user_uid=user_uid,
            start_date=today - timedelta(days=days_back),
            end_date=today,
            include_completed=True,
        )

        if result.is_error:
            return result

        for task in result.value or []:
            status = getattr(task, "status", None)
            if status:
                key = status.value if isinstance(status, Enum) else str(status)
                distribution[key] = distribution.get(key, 0) + 1

        if not distribution:
            return Result.fail(Errors.not_found("No tasks found for status distribution"))

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
        today = date.today()

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
            tasks = [t for t in tasks if getattr(t, "project", None) == project]

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
        # It reads the node column Task.fulfills_goal_uid, not the FULFILLS_GOAL edge —
        # the two agree by construction: every door lands both halves (the app doors
        # dual-write property + edge, the vault door stamps the property from
        # connections.fulfills_goal), so a vault-ingested task is found here too.
        # See TasksCoreService._write_link_edges for the invariant.
        # get_tasks_for_goal is NOT user-scoped (find_by on fulfills_goal_uid only), so
        # filter to the authenticated owner — a foreign task linked to this goal UID must
        # not leak its title/dates/status into the response (user-owned read invariant).
        tasks: list[Any] = []
        tasks_result = await self.tasks_service.get_tasks_for_goal(goal_uid)
        if tasks_result.is_ok:
            tasks = [t for t in (tasks_result.value or []) if t.user_uid == user_uid]

        return self.vis.format_goal_gantt(goal_result.value, tasks)

    # =========================================================================
    # Task Date Helpers
    # =========================================================================

    def _task_due_on(self, task: Any, d: date) -> bool:
        """Return True if the task's due_date or scheduled_date falls on d."""
        due = getattr(task, "due_date", None)
        scheduled = getattr(task, "scheduled_date", None)
        return (due == d) or (scheduled == d)

    def _task_in_range(self, task: Any, start: date, end: date) -> bool:
        """Return True if the task's due_date or scheduled_date falls within [start, end]."""
        due = getattr(task, "due_date", None)
        scheduled = getattr(task, "scheduled_date", None)
        if due and start <= due <= end:
            return True
        return bool(scheduled and start <= scheduled <= end)

    def _is_completed(self, task: Any) -> bool:
        """Return True if the task status is COMPLETED."""
        status = getattr(task, "status", None)
        if status is None:
            return False
        if isinstance(status, Enum):
            return status == EntityStatus.COMPLETED
        return str(status).lower() in ("done", "completed")
