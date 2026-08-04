"""
Visualization Service
=====================

Pure adapters for transforming SKUEL data to visualization library formats.

Supports two visualization libraries:
- Chart.js: Progress metrics, completion rates, trends
- Frappe Gantt: Project planning with dependencies

Architecture:
- Pure formatting: all methods are synchronous transformations of pre-fetched data
- No domain service dependencies — callers supply the data
- Data fetching and aggregation live in VisualizationAggregationService

See: core/services/analytics/visualization_aggregation_service.py

Usage:
    service = VisualizationService()

    # Chart.js — pass pre-computed counts
    chart = service.format_completion_chart(completed=[3, 5], total=[5, 7], labels=["Mon", "Tue"])

    # Frappe Gantt — pass Task domain models
    gantt = service.format_for_gantt(tasks, dependencies)
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from core.models.enums import EntityStatus, Priority
from core.models.goal.goal import Goal
from core.ports.query_types import ChartJsConfig, GanttConfig
from core.utils.logging import get_logger
from core.utils.palette import SemanticColor
from core.utils.result_simplified import Errors, Result
from core.utils.type_converters import finite_float

logger = get_logger(__name__)


# =============================================================================
# Chart.js Adapters
# =============================================================================


@dataclass
class ChartDataset:
    """Chart.js dataset structure."""

    label: str
    data: list[float | int]
    backgroundColor: str | list[str] = "#3B82F6"  # noqa: N815 (Chart.js API)
    borderColor: str | list[str] = "#2563EB"  # noqa: N815 (Chart.js API)
    borderWidth: int = 2  # noqa: N815 (Chart.js API)
    fill: bool = False
    tension: float = 0.1  # Line smoothing


@dataclass
class ChartData:
    """Chart.js data structure."""

    labels: list[str]
    datasets: list[ChartDataset]


@dataclass
class ChartConfig:
    """Complete Chart.js configuration."""

    type: str  # line, bar, pie, doughnut, radar
    data: ChartData
    options: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Frappe Gantt Adapters
# =============================================================================


@dataclass
class GanttTask:
    """Frappe Gantt task structure."""

    id: str
    name: str
    start: str  # YYYY-MM-DD
    end: str  # YYYY-MM-DD
    progress: int = 0  # 0-100
    dependencies: str = ""  # Comma-separated task IDs
    custom_class: str = ""  # CSS class for styling


@dataclass
class GanttData:
    """Frappe Gantt data structure."""

    tasks: list[GanttTask]
    options: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Visualization Service (pure formatter — no domain service dependencies)
# =============================================================================


class VisualizationService:
    """
    Transform pre-fetched SKUEL data to visualization library formats.

    All methods are synchronous pure transformations. No domain service
    dependencies — data fetching and aggregation are handled by
    VisualizationAggregationService.
    """

    # =========================================================================
    # Chart.js Formatting
    # =========================================================================

    def format_completion_chart(
        self,
        completed: list[int],
        total: list[int],
        labels: list[str],
        chart_type: Literal["line", "bar"] = "line",
    ) -> Result[ChartJsConfig]:
        """
        Format completion rate data for Chart.js.

        Args:
            completed: List of completed counts per period
            total: List of total counts per period
            labels: Period labels (dates, weeks, etc.)
            chart_type: Chart type (line or bar)

        Returns:
            Chart.js configuration dict
        """
        if len(completed) != len(total) or len(completed) != len(labels):
            return Result.fail(Errors.validation("Data arrays must have same length"))

        rates = [
            round((c / t * 100) if t > 0 else 0, 1) for c, t in zip(completed, total, strict=False)
        ]

        config = ChartConfig(
            type=chart_type,
            data=ChartData(
                labels=labels,
                datasets=[
                    ChartDataset(
                        label="Completion Rate (%)",
                        data=rates,
                        backgroundColor=SemanticColor.SUCCESS
                        if chart_type == "bar"
                        else "transparent",
                        borderColor=SemanticColor.SUCCESS,
                        fill=chart_type == "line",
                    ),
                ],
            ),
            options={
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {
                    "y": {
                        "beginAtZero": True,
                        "max": 100,
                        "title": {"display": True, "text": "Completion %"},
                    }
                },
                "plugins": {
                    "legend": {"display": True, "position": "top"},
                    "title": {"display": True, "text": "Task Completion Rate"},
                },
            },
        )

        return Result.ok(self._chart_config_to_dict(config))

    def format_distribution_chart(
        self,
        data: dict[str, int],
        title: str = "Distribution",
        chart_type: Literal["pie", "doughnut", "bar"] = "doughnut",
    ) -> Result[ChartJsConfig]:
        """
        Format distribution data for Chart.js (pie, doughnut, or bar).

        Args:
            data: Dictionary of label -> count
            title: Chart title
            chart_type: Chart type

        Returns:
            Chart.js configuration dict
        """
        if not data:
            return Result.fail(Errors.validation("Data cannot be empty"))

        labels = list(data.keys())
        values: list[float | int] = [float(v) for v in data.values()]

        color_cycle = SemanticColor.ALL
        colors = [color_cycle[i % len(color_cycle)] for i in range(len(labels))]

        config = ChartConfig(
            type=chart_type,
            data=ChartData(
                labels=labels,
                datasets=[
                    ChartDataset(
                        label=title,
                        data=values,
                        backgroundColor=colors,
                        borderColor=colors if chart_type == "bar" else "#ffffff",
                        borderWidth=1 if chart_type in ("pie", "doughnut") else 2,
                    ),
                ],
            ),
            options={
                "responsive": True,
                "maintainAspectRatio": False,
                "plugins": {
                    "legend": {
                        "display": True,
                        "position": "right" if chart_type in ("pie", "doughnut") else "top",
                    },
                    "title": {"display": True, "text": title},
                },
            },
        )

        return Result.ok(self._chart_config_to_dict(config))

    def format_streak_chart(
        self,
        streaks: list[dict[str, Any]],
    ) -> Result[ChartJsConfig]:
        """
        Format habit streak data for Chart.js horizontal bar chart.

        Args:
            streaks: List of {"name": str, "current": int, "best": int}

        Returns:
            Chart.js configuration dict
        """
        if not streaks:
            return Result.fail(Errors.validation("Streaks cannot be empty"))

        config = ChartConfig(
            type="bar",
            data=ChartData(
                labels=[s["name"] for s in streaks],
                datasets=[
                    ChartDataset(
                        label="Current Streak",
                        data=[s["current"] for s in streaks],
                        backgroundColor=SemanticColor.SUCCESS,
                        borderColor=SemanticColor.SUCCESS,
                    ),
                    ChartDataset(
                        label="Best Streak",
                        data=[s["best"] for s in streaks],
                        backgroundColor=SemanticColor.INFO,
                        borderColor=SemanticColor.INFO,
                    ),
                ],
            ),
            options={
                "responsive": True,
                "maintainAspectRatio": False,
                "indexAxis": "y",  # Horizontal bars
                "plugins": {
                    "legend": {"display": True, "position": "top"},
                    "title": {"display": True, "text": "Habit Streaks"},
                },
            },
        )

        return Result.ok(self._chart_config_to_dict(config))

    # =========================================================================
    # Frappe Gantt Formatting
    # =========================================================================

    def format_for_gantt(
        self,
        tasks: list[Any],  # List of Task domain models
        dependencies: dict[str, list[str]] | None = None,
    ) -> Result[GanttConfig]:
        """
        Format tasks for Frappe Gantt.

        Args:
            tasks: List of Task domain models
            dependencies: Dict of task_uid -> list of dependency UIDs

        Returns:
            Frappe Gantt configuration dict
        """
        if not tasks:
            return Result.fail(Errors.validation("Tasks cannot be empty"))

        from datetime import date, timedelta

        dependencies = dependencies or {}
        gantt_tasks: list[GanttTask] = []

        for task in tasks:
            start_date = task.scheduled_date or task.due_date or date.today()
            if task.due_date and task.due_date > start_date:
                end_date = task.due_date
            else:
                duration_days = max(1, (task.duration_minutes or 30) // (8 * 60))
                end_date = start_date + timedelta(days=duration_days)

            task_deps = dependencies.get(task.uid, [])

            gantt_tasks.append(
                GanttTask(
                    id=task.uid,
                    name=task.title,
                    start=start_date.isoformat(),
                    end=end_date.isoformat(),
                    progress=self._calculate_task_progress(task),
                    dependencies=", ".join(task_deps) if task_deps else "",
                    custom_class=self._get_gantt_class(task),
                )
            )

        data = GanttData(
            tasks=gantt_tasks,
            options={
                "view_mode": "Week",
                "date_format": "YYYY-MM-DD",
                "popup_trigger": "click",
                "custom_popup_html": None,
                "language": "en",
            },
        )

        return Result.ok(self._gantt_data_to_dict(data))

    def format_goal_gantt(
        self,
        goal: Goal,
        tasks: list[Any],  # Related tasks
        milestones: list[dict[str, Any]] | None = None,
    ) -> Result[GanttConfig]:
        """
        Format a goal with its tasks as a Gantt chart.

        Args:
            goal: Goal domain model
            tasks: Related tasks for the goal
            milestones: Optional milestone markers

        Returns:
            Frappe Gantt configuration dict
        """
        from datetime import date, timedelta

        gantt_tasks: list[GanttTask] = []

        goal_start = goal.start_date or date.today()
        goal_end = goal.target_date or goal_start + timedelta(days=90)
        # progress_percentage is the number every goal writer maintains: all five
        # current_value writers in goals_progress_service set it in the same update dict,
        # and goals_core_service.complete_goal sets only it. It is already 0-100, the
        # scale Frappe Gantt wants. That is why the old `if goal_progress <= 1`
        # normalisation is deleted rather than repaired — against a 0-100 reader it would
        # render a goal 0.5% along as a 50% bar.
        #
        # Goal.calculate_progress() looks like the natural reader here and is not. The
        # unit defect it used to carry — a current_value / target_value branch dividing a
        # percent by domain units — is fixed, so that is no longer the reason; two others
        # outlive it. It returns 0.0-1.0, so switching to it would bring back the very
        # `* 100` deleted above. And it computes on the stored value, so a non-numeric
        # progress_percentage raises inside the model before the narrowing below can turn
        # it into a Result — reading raw is what keeps that guard reachable.
        #
        # Nothing validates the stored value, in range OR in type: vault ingestion copies
        # goal frontmatter into node properties unchecked
        # (core/services/ingestion/preparer.py) and nothing coerces on the way back out, so
        # `progress_percentage: 150`, `-40`, a quoted `"40"` and YAML's `.nan` / `.inf` all
        # reach this line as-is. Hence the narrowing below, then the clamp. round() rather
        # than int() — 2 of 3 milestones stores 66.666…, which truncates to 66.
        #
        # finite_float is the shared total predicate (core/utils/type_converters.py):
        # float() either raises or yields a float, and a float is finite, ±inf or nan, so
        # "converts and is finite" admits exactly the values round() cannot fail on.
        # Goal.calculate_progress() narrows through the same predicate and answers None
        # with 0.0; here there is a Result channel, so None is reported instead. None from
        # an absent property does not arrive by this route (_CrudMixin.get returns a node
        # property map, which omits unset keys, so the DTO default 0.0 wins) — it is
        # handled because to_domain_model passes a present-but-None through unchanged.
        raw_progress = goal.progress_percentage
        percent = 0.0 if raw_progress is None else finite_float(raw_progress)
        if percent is None:
            return Result.fail(
                Errors.validation(
                    message=(
                        f"Goal {goal.uid} has a progress_percentage that is not a finite "
                        f"number ({raw_progress!r}); cannot render its Gantt bar"
                    ),
                    field="progress_percentage",
                    value=raw_progress,
                    user_message="This goal's progress value is invalid and needs correcting.",
                )
            )
        goal_progress = min(100, max(0, round(percent)))

        gantt_tasks.append(
            GanttTask(
                id=goal.uid,
                name=f"Goal: {goal.title}",
                start=goal_start.isoformat(),
                end=goal_end.isoformat(),
                progress=goal_progress,
                custom_class="goal-bar",
            )
        )

        for task in tasks:
            start_date = task.scheduled_date or task.due_date or goal_start
            end_date = task.due_date or start_date + timedelta(days=1)

            gantt_tasks.append(
                GanttTask(
                    id=task.uid,
                    name=task.title,
                    start=start_date.isoformat(),
                    end=end_date.isoformat(),
                    progress=self._calculate_task_progress(task),
                    dependencies=goal.uid,
                    custom_class=self._get_gantt_class(task),
                )
            )

        if milestones:
            for ms in milestones:
                ms_date = ms.get("date", goal_end)
                gantt_tasks.append(
                    GanttTask(
                        id=ms.get("id", f"ms_{ms.get('name', 'milestone')}"),
                        name=ms.get("name", "Milestone"),
                        start=ms_date.isoformat() if isinstance(ms_date, date) else ms_date,
                        end=ms_date.isoformat() if isinstance(ms_date, date) else ms_date,
                        progress=100 if ms.get("completed", False) else 0,
                        custom_class="milestone-bar",
                    )
                )

        data = GanttData(tasks=gantt_tasks, options={"view_mode": "Month"})

        return Result.ok(self._gantt_data_to_dict(data))

    # =========================================================================
    # Gantt Progress Helper (presentation logic: status → progress bar %)
    # =========================================================================

    def _calculate_task_progress(self, task: Any) -> int:
        """Map task status and time-tracking fields to a 0-100 Gantt progress value."""
        status = getattr(task, "status", EntityStatus.DRAFT)

        if status == EntityStatus.COMPLETED:
            return 100
        if status == EntityStatus.ACTIVE:
            actual = getattr(task, "actual_minutes", 0) or 0
            duration = getattr(task, "duration_minutes", 30) or 30
            if actual > 0:
                return min(95, int(actual / duration * 100))
            return 50  # Default for in-progress
        if status == EntityStatus.BLOCKED:
            return 25
        return 0

    # =========================================================================
    # Serialization Helpers
    # =========================================================================

    # Each helper returns the TypedDict literal directly. A `cast()` here would
    # be unchecked by construction: a renamed Chart.js/Gantt key is a
    # breaking wire change (skuel.js hands the payload to `new Chart(ctx, config)`
    # unmodified) that no Python test observes, and under a cast MyPy reported
    # nothing. Returning the literal makes ChartJsData/ChartJsDataset the checker.

    def _chart_config_to_dict(self, config: ChartConfig) -> ChartJsConfig:
        """Convert ChartConfig to a ChartJsConfig TypedDict for JSON serialization."""
        return {
            "type": config.type,
            "data": {
                "labels": config.data.labels,
                "datasets": [
                    {
                        "label": ds.label,
                        "data": ds.data,
                        "backgroundColor": ds.backgroundColor,
                        "borderColor": ds.borderColor,
                        "borderWidth": ds.borderWidth,
                        "fill": ds.fill,
                        "tension": ds.tension,
                    }
                    for ds in config.data.datasets
                ],
            },
            "options": config.options,
        }

    def _gantt_data_to_dict(self, data: GanttData) -> GanttConfig:
        """Convert GanttData to a GanttConfig TypedDict for JSON serialization."""
        return {
            "tasks": [asdict(task) for task in data.tasks],
            "options": data.options,
        }

    # =========================================================================
    # CSS Class Helpers
    # =========================================================================

    def _get_priority_class(self, priority: Priority | str) -> str:
        """Get CSS class for priority.

        Accepts a Priority enum or its raw string value: entities loaded from Neo4j
        carry ``priority`` as a plain string (not the enum), so ``priority.value``
        would raise AttributeError on the persisted-task path.
        """
        value = priority.value if isinstance(priority, Priority) else str(priority)
        return f"priority-{value}"

    def _get_gantt_class(self, task: Any) -> str:
        """Get CSS class for Gantt task based on status and priority."""
        classes = []
        status = getattr(task, "status", EntityStatus.DRAFT)
        if status == EntityStatus.COMPLETED:
            classes.append("completed")
        elif status == EntityStatus.ACTIVE:
            classes.append("in-progress")
        elif status == EntityStatus.BLOCKED:
            classes.append("blocked")

        priority = getattr(task, "priority", Priority.MEDIUM)
        classes.append(self._get_priority_class(priority))

        return " ".join(classes)
