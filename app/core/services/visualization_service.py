"""
Visualization Service
=====================

Adapters for transforming SKUEL data to visualization library formats.

Supports three visualization libraries:
- Chart.js: Progress metrics, completion rates, trends
- Vis.js Timeline: Interactive timeline with grouping
- Frappe Gantt: Project planning with dependencies

Architecture:
- Adapts domain models to library-specific JSON formats
- No external dependencies (pure Python transformation)
- Returns Result[T] for error handling
- Works with CalendarData, Task, and ReportMetrics

Usage:
    service = VisualizationService()

    # Chart.js
    chart_data = service.format_for_chartjs(metrics, "line")

    # Vis.js Timeline
    timeline_data = service.format_for_visjs(calendar_data)

    # Frappe Gantt
    gantt_data = service.format_for_gantt(tasks, dependencies)
"""

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, ClassVar, Literal

from core.models.enums import KuStatus, Priority
from core.models.event.calendar_models import CalendarData, CalendarItem, CalendarItemType
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

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
# Vis.js Timeline Adapters
# =============================================================================


@dataclass
class VisTimelineItem:
    """Vis.js Timeline item structure."""

    id: str
    content: str
    start: str  # ISO datetime string
    end: str | None = None  # ISO datetime string
    group: str | None = None
    type: str = "range"  # range, box, point, background
    className: str = ""  # noqa: N815 (Vis.js API)
    style: str = ""
    title: str = ""  # Tooltip


@dataclass
class VisTimelineGroup:
    """Vis.js Timeline group structure."""

    id: str
    content: str
    className: str = ""  # noqa: N815 (Vis.js API)
    style: str = ""


@dataclass
class VisTimelineData:
    """Vis.js Timeline data structure."""

    items: list[VisTimelineItem]
    groups: list[VisTimelineGroup]
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
# Visualization Service
# =============================================================================


class VisualizationService:
    """
    Transform SKUEL data models to visualization library formats.

    This service provides pure transformation functions - no I/O operations.
    All methods are synchronous since they only transform data.
    """

    # Color schemes for consistent styling
    COLORS: ClassVar[dict[str, str]] = {
        "primary": "#3B82F6",  # Blue
        "success": "#10B981",  # Green
        "warning": "#F59E0B",  # Amber
        "danger": "#EF4444",  # Red
        "info": "#6366F1",  # Indigo
        "neutral": "#6B7280",  # Gray
    }

    PRIORITY_COLORS: ClassVar[dict[Priority, str]] = {
        Priority.CRITICAL: "#EF4444",
        Priority.HIGH: "#F59E0B",
        Priority.MEDIUM: "#3B82F6",
        Priority.LOW: "#10B981",
    }

    STATUS_COLORS: ClassVar[dict[KuStatus, str]] = {
        KuStatus.COMPLETED: "#10B981",
        KuStatus.ACTIVE: "#3B82F6",
        KuStatus.BLOCKED: "#EF4444",
        KuStatus.DRAFT: "#6B7280",
        KuStatus.CANCELLED: "#9CA3AF",
    }

    ITEM_TYPE_GROUPS: ClassVar[dict[CalendarItemType, str]] = {
        CalendarItemType.TASK_WORK: "tasks",
        CalendarItemType.TASK_DEADLINE: "deadlines",
        CalendarItemType.EVENT: "events",
        CalendarItemType.HABIT: "habits",
        CalendarItemType.MILESTONE: "milestones",
    }

    # =========================================================================
    # Chart.js Formatting
    # =========================================================================

    def format_completion_chart(
        self,
        completed: list[int],
        total: list[int],
        labels: list[str],
        chart_type: Literal["line", "bar"] = "line",
    ) -> Result[dict[str, Any]]:
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

        # Calculate completion rates
        rates = []
        for c, t in zip(completed, total, strict=False):
            rate = round((c / t * 100) if t > 0 else 0, 1)
            rates.append(rate)

        config = ChartConfig(
            type=chart_type,
            data=ChartData(
                labels=labels,
                datasets=[
                    ChartDataset(
                        label="Completion Rate (%)",
                        data=rates,
                        backgroundColor=self.COLORS["success"]
                        if chart_type == "bar"
                        else "transparent",
                        borderColor=self.COLORS["success"],
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
    ) -> Result[dict[str, Any]]:
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
        values = list(data.values())

        # Generate colors for each segment
        color_cycle = [
            self.COLORS["primary"],
            self.COLORS["success"],
            self.COLORS["warning"],
            self.COLORS["danger"],
            self.COLORS["info"],
            self.COLORS["neutral"],
        ]
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

    def format_trend_chart(
        self,
        series: list[dict[str, Any]],
        labels: list[str],
        title: str = "Trends",
    ) -> Result[dict[str, Any]]:
        """
        Format multi-series trend data for Chart.js line chart.

        Args:
            series: List of {"name": str, "data": list[float], "color": str (optional)}
            labels: X-axis labels (dates, periods)
            title: Chart title

        Returns:
            Chart.js configuration dict
        """
        if not series:
            return Result.fail(Errors.validation("Series cannot be empty"))

        datasets = []
        color_cycle = list(self.COLORS.values())

        for i, s in enumerate(series):
            color = s.get("color", color_cycle[i % len(color_cycle)])
            datasets.append(
                ChartDataset(
                    label=s["name"],
                    data=s["data"],
                    borderColor=color,
                    backgroundColor="transparent",
                    tension=0.3,
                )
            )

        config = ChartConfig(
            type="line",
            data=ChartData(labels=labels, datasets=datasets),
            options={
                "responsive": True,
                "maintainAspectRatio": False,
                "interaction": {"intersect": False, "mode": "index"},
                "plugins": {
                    "legend": {"display": True, "position": "top"},
                    "title": {"display": True, "text": title},
                },
            },
        )

        return Result.ok(self._chart_config_to_dict(config))

    def format_streak_chart(
        self,
        streaks: list[dict[str, Any]],
    ) -> Result[dict[str, Any]]:
        """
        Format habit streak data for Chart.js horizontal bar chart.

        Args:
            streaks: List of {"name": str, "current": int, "best": int}

        Returns:
            Chart.js configuration dict
        """
        if not streaks:
            return Result.fail(Errors.validation("Streaks cannot be empty"))

        labels = [s["name"] for s in streaks]
        current_data = [s["current"] for s in streaks]
        best_data = [s["best"] for s in streaks]

        config = ChartConfig(
            type="bar",
            data=ChartData(
                labels=labels,
                datasets=[
                    ChartDataset(
                        label="Current Streak",
                        data=current_data,
                        backgroundColor=self.COLORS["success"],
                        borderColor=self.COLORS["success"],
                    ),
                    ChartDataset(
                        label="Best Streak",
                        data=best_data,
                        backgroundColor=self.COLORS["info"],
                        borderColor=self.COLORS["info"],
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
    # Vis.js Timeline Formatting
    # =========================================================================

    def format_for_visjs(
        self,
        calendar_data: CalendarData,
        group_by: Literal["type", "project", "none"] = "type",
    ) -> Result[dict[str, Any]]:
        """
        Format CalendarData for Vis.js Timeline.

        Args:
            calendar_data: CalendarData from CalendarService
            group_by: Grouping strategy (type, project, or none)

        Returns:
            Vis.js Timeline configuration dict
        """
        items: list[VisTimelineItem] = []
        groups: list[VisTimelineGroup] = []
        group_ids: set[str] = set()

        for item in calendar_data.items:
            vis_item = self._calendar_item_to_visjs(item, group_by)
            items.append(vis_item)

            # Track groups
            if vis_item.group and vis_item.group not in group_ids:
                group_ids.add(vis_item.group)

        # Build groups
        if group_by == "type":
            groups = self._build_type_groups(group_ids)
        elif group_by == "project":
            groups = self._build_project_groups(group_ids)

        data = VisTimelineData(
            items=items,
            groups=groups,
            options={
                "stack": True,
                "showCurrentTime": True,
                "zoomable": True,
                "moveable": True,
                "orientation": {"axis": "top", "item": "bottom"},
                "margin": {"item": {"horizontal": 5, "vertical": 5}},
            },
        )

        return Result.ok(self._visjs_data_to_dict(data))

    def format_tasks_for_visjs(
        self,
        tasks: list[Any],  # List of Task domain models
        show_deadlines: bool = True,
    ) -> Result[dict[str, Any]]:
        """
        Format Task list for Vis.js Timeline.

        Args:
            tasks: List of Task domain models
            show_deadlines: Whether to show deadline markers

        Returns:
            Vis.js Timeline configuration dict
        """
        items: list[VisTimelineItem] = []

        for task in tasks:
            # Work block (scheduled date + duration)
            if task.scheduled_date:
                start_dt = datetime.combine(
                    task.scheduled_date, datetime.min.time().replace(hour=9)
                )
                end_dt = start_dt + timedelta(minutes=task.duration_minutes or 30)

                items.append(
                    VisTimelineItem(
                        id=f"{task.uid}_work",
                        content=task.title,
                        start=start_dt.isoformat(),
                        end=end_dt.isoformat(),
                        group="tasks",
                        type="range",
                        className=self._get_priority_class(task.priority),
                        title=f"{task.title} ({task.duration_minutes}min)",
                    )
                )

            # Deadline marker
            if show_deadlines and task.due_date:
                deadline_dt = datetime.combine(
                    task.due_date, datetime.min.time().replace(hour=23, minute=59)
                )
                items.append(
                    VisTimelineItem(
                        id=f"{task.uid}_deadline",
                        content=f"Due: {task.title}",
                        start=deadline_dt.isoformat(),
                        group="deadlines",
                        type="point",
                        className="deadline-marker",
                        title=f"Deadline: {task.title}",
                    )
                )

        groups = [
            VisTimelineGroup(id="tasks", content="Tasks", className="task-group"),
            VisTimelineGroup(id="deadlines", content="Deadlines", className="deadline-group"),
        ]

        data = VisTimelineData(
            items=items,
            groups=groups,
            options={
                "stack": True,
                "showCurrentTime": True,
                "zoomable": True,
            },
        )

        return Result.ok(self._visjs_data_to_dict(data))

    # =========================================================================
    # Frappe Gantt Formatting
    # =========================================================================

    def format_for_gantt(
        self,
        tasks: list[Any],  # List of Task domain models
        dependencies: dict[str, list[str]] | None = None,
    ) -> Result[dict[str, Any]]:
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

        dependencies = dependencies or {}
        gantt_tasks: list[GanttTask] = []

        for task in tasks:
            # Determine start and end dates
            start_date = task.scheduled_date or task.due_date or date.today()
            if task.due_date and task.due_date > start_date:
                end_date = task.due_date
            else:
                # Default: start + duration (convert minutes to days, minimum 1 day)
                duration_days = max(1, (task.duration_minutes or 30) // (8 * 60))
                end_date = start_date + timedelta(days=duration_days)

            # Calculate progress
            progress = self._calculate_task_progress(task)

            # Get dependencies for this task
            task_deps = dependencies.get(task.uid, [])
            deps_str = ", ".join(task_deps) if task_deps else ""

            gantt_tasks.append(
                GanttTask(
                    id=task.uid,
                    name=task.title,
                    start=start_date.isoformat(),
                    end=end_date.isoformat(),
                    progress=progress,
                    dependencies=deps_str,
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
        goal: Any,  # Goal domain model
        tasks: list[Any],  # Related tasks
        milestones: list[dict[str, Any]] | None = None,
    ) -> Result[dict[str, Any]]:
        """
        Format a goal with its tasks as a Gantt chart.

        Args:
            goal: Goal domain model
            tasks: Related tasks for the goal
            milestones: Optional milestone markers

        Returns:
            Frappe Gantt configuration dict
        """
        gantt_tasks: list[GanttTask] = []

        # Add goal as parent task
        goal_start = getattr(goal, "start_date", None) or date.today()
        goal_end = getattr(goal, "target_date", None) or goal_start + timedelta(days=90)
        goal_progress = getattr(goal, "progress", 0) or 0

        gantt_tasks.append(
            GanttTask(
                id=goal.uid,
                name=f"Goal: {goal.title}",
                start=goal_start.isoformat(),
                end=goal_end.isoformat(),
                progress=int(goal_progress * 100) if goal_progress <= 1 else int(goal_progress),
                custom_class="goal-bar",
            )
        )

        # Add tasks
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
                    dependencies=goal.uid,  # All tasks depend on goal
                    custom_class=self._get_gantt_class(task),
                )
            )

        # Add milestones
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
    # Data Aggregation Methods
    # =========================================================================

    async def get_completion_data(
        self,
        user_uid: str,
        period: str,
        tasks_service: Any,
    ) -> Result[dict[str, Any]]:
        """
        Get task completion data aggregated by period.

        Args:
            user_uid: User identifier
            period: Time period (week, month, quarter)
            tasks_service: Tasks service for data retrieval

        Returns:
            Result containing completed/total arrays and labels
        """
        from datetime import date, timedelta

        today = date.today()

        # Calculate date range and labels based on period
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

        # Get task data from service
        result = await tasks_service.get_user_items_in_range(
            user_uid=user_uid,
            start_date=start_date,
            end_date=today,
            include_completed=True,
        )

        if result.is_error:
            return result

        tasks = result.value or []

        # Calculate completed/total per period
        completed = []
        total = []

        if period == "week":
            for i in range(7):
                d = start_date + timedelta(days=i)
                day_tasks = [t for t in tasks if self._task_due_on(t, d)]
                day_completed = [t for t in day_tasks if self._is_completed(t)]
                total.append(len(day_tasks))
                completed.append(len(day_completed))
        elif period == "month":
            for i in range(0, 30, 3):
                d_start = start_date + timedelta(days=i)
                d_end = d_start + timedelta(days=2)
                period_tasks = [t for t in tasks if self._task_in_range(t, d_start, d_end)]
                period_completed = [t for t in period_tasks if self._is_completed(t)]
                total.append(len(period_tasks))
                completed.append(len(period_completed))
        else:  # quarter
            for i in range(0, 90, 7):
                d_start = start_date + timedelta(days=i)
                d_end = d_start + timedelta(days=6)
                period_tasks = [t for t in tasks if self._task_in_range(t, d_start, d_end)]
                period_completed = [t for t in period_tasks if self._is_completed(t)]
                total.append(len(period_tasks))
                completed.append(len(period_completed))

        return Result.ok({"completed": completed, "total": total, "labels": labels})

    async def get_priority_distribution_data(
        self,
        user_uid: str,
        tasks_service: Any,
    ) -> Result[dict[str, int]]:
        """
        Get task priority distribution.

        Args:
            user_uid: User identifier
            tasks_service: Tasks service for data retrieval

        Returns:
            Result containing priority distribution dict
        """
        from enum import Enum

        distribution: dict[str, int] = {}

        # Get active tasks
        result = await tasks_service.search.get_by_status(
            user_uid=user_uid,
            status="active",
        )

        if result.is_error:
            return result

        tasks = result.value or []
        for task in tasks:
            priority = getattr(task, "priority", None)
            if priority:
                key = priority.value if isinstance(priority, Enum) else str(priority)
                distribution[key] = distribution.get(key, 0) + 1

        return Result.ok(distribution)

    async def get_streak_data(
        self,
        user_uid: str,
        habits_service: Any,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get habit streak data.

        Args:
            user_uid: User identifier
            habits_service: Habits service for data retrieval

        Returns:
            Result containing streak data list
        """
        streaks: list[dict[str, Any]] = []

        result = await habits_service.search.get_by_status(
            user_uid=user_uid,
            status="active",
        )

        if result.is_error:
            return result

        habits = result.value or []
        for habit in habits:
            streak = {
                "name": getattr(habit, "title", "Habit"),
                "current": getattr(habit, "current_streak", 0) or 0,
                "best": getattr(habit, "best_streak", 0) or 0,
            }
            streaks.append(streak)

        return Result.ok(streaks)

    async def get_status_distribution_data(
        self,
        user_uid: str,
        tasks_service: Any,
        days_back: int = 30,
    ) -> Result[dict[str, int]]:
        """
        Get task status distribution.

        Args:
            user_uid: User identifier
            tasks_service: Tasks service for data retrieval
            days_back: Number of days to look back

        Returns:
            Result containing status distribution dict
        """
        from datetime import date, timedelta
        from enum import Enum

        distribution: dict[str, int] = {}

        today = date.today()
        result = await tasks_service.get_user_items_in_range(
            user_uid=user_uid,
            start_date=today - timedelta(days=days_back),
            end_date=today,
            include_completed=True,
        )

        if result.is_error:
            return result

        tasks = result.value or []
        for task in tasks:
            status = getattr(task, "status", None)
            if status:
                key = status.value if isinstance(status, Enum) else str(status)
                distribution[key] = distribution.get(key, 0) + 1

        return Result.ok(distribution)

    # =========================================================================
    # Helper Methods (Task Filtering)
    # =========================================================================

    def _task_due_on(self, task: Any, d: date) -> bool:
        """Check if task is due on specific date."""
        due = getattr(task, "due_date", None)
        scheduled = getattr(task, "scheduled_date", None)
        return (due == d) or (scheduled == d)

    def _task_in_range(self, task: Any, start: date, end: date) -> bool:
        """Check if task falls within date range."""
        due = getattr(task, "due_date", None)
        scheduled = getattr(task, "scheduled_date", None)

        if due and start <= due <= end:
            return True
        return bool(scheduled and start <= scheduled <= end)

    def _is_completed(self, task: Any) -> bool:
        """Check if task is completed."""
        from enum import Enum

        status = getattr(task, "status", None)
        if status is None:
            return False
        if isinstance(status, Enum):
            return status == KuStatus.COMPLETED
        return str(status).lower() in ("done", "completed")

    # =========================================================================
    # Helper Methods (Serialization)
    # =========================================================================

    def _chart_config_to_dict(self, config: ChartConfig) -> dict[str, Any]:
        """Convert ChartConfig to dict for JSON serialization."""
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

    def _visjs_data_to_dict(self, data: VisTimelineData) -> dict[str, Any]:
        """Convert VisTimelineData to dict for JSON serialization."""
        return {
            "items": [asdict(item) for item in data.items],
            "groups": [asdict(group) for group in data.groups],
            "options": data.options,
        }

    def _gantt_data_to_dict(self, data: GanttData) -> dict[str, Any]:
        """Convert GanttData to dict for JSON serialization."""
        return {
            "tasks": [asdict(task) for task in data.tasks],
            "options": data.options,
        }

    def _calendar_item_to_visjs(self, item: CalendarItem, group_by: str) -> VisTimelineItem:
        """Convert CalendarItem to VisTimelineItem."""
        # Determine group
        if group_by == "type":
            group = self.ITEM_TYPE_GROUPS.get(item.item_type, "other")
        elif group_by == "project":
            group = item.project_uid or "no-project"
        else:
            group = None

        # Determine type (range vs point)
        vis_type = "range" if item.end_time != item.start_time else "point"

        return VisTimelineItem(
            id=item.uid,
            content=item.title,
            start=item.start_time.isoformat(),
            end=item.end_time.isoformat() if vis_type == "range" else None,
            group=group,
            type=vis_type,
            className=f"item-{item.item_type.value}",
            style=f"background-color: {item.color};" if item.color else "",
            title=item.description or item.title,
        )

    def _build_type_groups(self, group_ids: set[str]) -> list[VisTimelineGroup]:
        """Build Vis.js groups for type-based grouping."""
        group_labels = {
            "tasks": "Tasks",
            "deadlines": "Deadlines",
            "events": "Events",
            "habits": "Habits",
            "milestones": "Milestones",
            "other": "Other",
        }

        groups = []
        for gid in sorted(group_ids):
            groups.append(
                VisTimelineGroup(
                    id=gid,
                    content=group_labels.get(gid, gid.title()),
                    className=f"group-{gid}",
                )
            )
        return groups

    def _build_project_groups(self, group_ids: set[str]) -> list[VisTimelineGroup]:
        """Build Vis.js groups for project-based grouping."""
        groups = []
        for gid in sorted(group_ids):
            label = "No Project" if gid == "no-project" else gid
            groups.append(VisTimelineGroup(id=gid, content=label, className="group-project"))
        return groups

    def _get_priority_class(self, priority: Priority) -> str:
        """Get CSS class for priority."""
        return f"priority-{priority.value}"

    def _get_gantt_class(self, task: Any) -> str:
        """Get CSS class for Gantt task based on status and priority."""
        classes = []

        # Status-based class
        status = getattr(task, "status", KuStatus.DRAFT)
        if status == KuStatus.COMPLETED:
            classes.append("completed")
        elif status == KuStatus.ACTIVE:
            classes.append("in-progress")
        elif status == KuStatus.BLOCKED:
            classes.append("blocked")

        # Priority-based class
        priority = getattr(task, "priority", Priority.MEDIUM)
        classes.append(f"priority-{priority.value}")

        return " ".join(classes)

    def _calculate_task_progress(self, task: Any) -> int:
        """Calculate task progress percentage."""
        status = getattr(task, "status", KuStatus.DRAFT)

        if status == KuStatus.COMPLETED:
            return 100
        elif status == KuStatus.ACTIVE:
            # If task has actual_minutes and duration_minutes, calculate
            actual = getattr(task, "actual_minutes", 0) or 0
            duration = getattr(task, "duration_minutes", 30) or 30
            if actual > 0:
                return min(95, int(actual / duration * 100))
            return 50  # Default for in-progress
        elif status == KuStatus.BLOCKED:
            return 25
        else:
            return 0
