"""Wire-shape pins for the Chart.js / Vis.js / Frappe Gantt payloads (SoC arc #11).

``static/js/skuel.js``'s ``chartVis`` component does ``new Chart(ctx, config)`` on the
deserialized response body, and the Vis.js timeline / Frappe Gantt views consume their
payloads the same way. Every key name below is therefore a **public wire contract** with
a JavaScript consumer, and until this file existed nothing on the Python side observed a
rename. ``tests/unit/adapters/test_visualization_api_routes.py`` drives the routes with a
``MagicMock`` service and asserts auth/IDOR only — it passes for any payload whatsoever.

Division of labour with MyPy, measured rather than assumed:

* The **outer** Chart.js keys (``type`` / ``data`` / ``labels`` / ``datasets`` and every
  dataset key) are now checked statically, because ``_chart_config_to_dict`` returns the
  ``ChartJsConfig`` literal instead of ``cast()``-ing a dict into it. Injecting
  ``"bgColor"`` for ``"backgroundColor"`` is ``typeddict-unknown-key`` on the branch and
  was silent before.
* The **item-level** Vis.js and Gantt keys are *not*, and cannot be: ``VisTimelineConfig``
  declares ``items``/``groups`` as ``list[dict[str, Any]]`` and the helpers fill them with
  ``asdict()``. Renaming ``GanttTask.custom_class`` to ``css_class`` consistently changes
  the emitted Frappe Gantt key and MyPy reports ``Success: no issues found``. That is the
  gap these assertions exist to cover.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from core.models.enums.goal_enums import MeasurementType
from core.models.event.calendar_models import (
    CalendarData,
    CalendarItem,
    CalendarItemType,
    CalendarView,
)
from core.models.goal.goal import Goal
from core.services.visualization_service import VisualizationService

# Chart.js reads these off each entry of config.data.datasets.
_CHARTJS_DATASET_KEYS = {
    "label",
    "data",
    "backgroundColor",
    "borderColor",
    "borderWidth",
    "fill",
    "tension",
}

# Vis.js Timeline reads these off each DataSet row.
_VISJS_ITEM_KEYS = {"id", "content", "start", "end", "group", "type", "className", "style", "title"}
_VISJS_GROUP_KEYS = {"id", "content", "className", "style"}

# Frappe Gantt reads these off each task; `custom_class` is its documented spelling.
_GANTT_TASK_KEYS = {"id", "name", "start", "end", "progress", "dependencies", "custom_class"}


@pytest.fixture
def service() -> VisualizationService:
    return VisualizationService()


class _Task:
    """Minimal stand-in for the Task fields the formatters actually read."""

    def __init__(self, uid: str) -> None:
        self.uid = uid
        self.title = f"Task {uid}"
        self.scheduled_date = datetime(2026, 3, 2).date()
        self.due_date = datetime(2026, 3, 5).date()
        self.duration_minutes = 45
        self.actual_minutes = 0
        self.priority = None
        self.status = None
        self.start_date = datetime(2026, 3, 2).date()


class TestChartJsWireShape:
    def test_completion_chart_top_level_and_dataset_keys(
        self, service: VisualizationService
    ) -> None:
        result = service.format_completion_chart([1, 2], [2, 4], ["Mon", "Tue"])

        assert result.is_ok
        config = result.value
        assert set(config.keys()) == {"type", "data", "options"}
        assert set(config["data"].keys()) == {"labels", "datasets"}
        assert set(config["data"]["datasets"][0].keys()) == _CHARTJS_DATASET_KEYS

    def test_distribution_chart_dataset_keys(self, service: VisualizationService) -> None:
        result = service.format_distribution_chart({"high": 2, "low": 1})

        assert result.is_ok
        assert set(result.value["data"]["datasets"][0].keys()) == _CHARTJS_DATASET_KEYS

    def test_streak_chart_dataset_keys(self, service: VisualizationService) -> None:
        result = service.format_streak_chart([{"name": "Read", "current": 3, "best": 9}])

        assert result.is_ok
        for dataset in result.value["data"]["datasets"]:
            assert set(dataset.keys()) == _CHARTJS_DATASET_KEYS


class TestVisTimelineWireShape:
    def test_calendar_items_and_groups_keys(self, service: VisualizationService) -> None:
        calendar = CalendarData(
            items=[
                CalendarItem(
                    uid="task_1",
                    title="Write tests",
                    item_type=CalendarItemType.TASK_WORK,
                    start_time=datetime(2026, 3, 2, 9, 0),
                    end_time=datetime(2026, 3, 2, 10, 0),
                    source_uid="task_1",
                )
            ],
            occurrences={},
            view=CalendarView.WEEK,
            start_date=datetime(2026, 3, 2).date(),
            end_date=datetime(2026, 3, 3).date(),
            metadata={},
        )

        result = service.format_for_visjs(calendar, group_by="type")

        assert result.is_ok
        config = result.value
        assert set(config.keys()) == {"items", "groups", "options"}
        assert set(config["items"][0].keys()) == _VISJS_ITEM_KEYS
        assert set(config["groups"][0].keys()) == _VISJS_GROUP_KEYS

    def test_tasks_timeline_item_keys(self, service: VisualizationService) -> None:
        result = service.format_tasks_for_visjs([_Task("task_1")])

        assert result.is_ok
        for item in result.value["items"]:
            assert set(item.keys()) == _VISJS_ITEM_KEYS


class TestGanttWireShape:
    def test_tasks_gantt_task_keys(self, service: VisualizationService) -> None:
        result = service.format_for_gantt([_Task("task_1")], {})

        assert result.is_ok
        config = result.value
        assert set(config.keys()) == {"tasks", "options"}
        assert set(config["tasks"][0].keys()) == _GANTT_TASK_KEYS

    def test_goal_gantt_task_keys(self, service: VisualizationService) -> None:
        """``format_goal_gantt`` is the second producer of Frappe Gantt tasks — the goal
        bar, its fulfilling tasks and its milestones all go out under these key names.
        The values behind them are pinned in ``test_goal_gantt_progress.py``."""
        goal = Goal(
            uid="goal_1",
            user_uid="user_1",
            title="Ship the feature",
            measurement_type=MeasurementType.PERCENTAGE,
            progress_percentage=40.0,
            start_date=datetime(2026, 3, 1).date(),
            target_date=datetime(2026, 6, 1).date(),
        )

        result = service.format_goal_gantt(
            goal, [_Task("task_1")], milestones=[{"id": "ms_1", "name": "Alpha"}]
        )

        assert result.is_ok
        config = result.value
        assert set(config.keys()) == {"tasks", "options"}
        assert len(config["tasks"]) == 3  # goal bar + task + milestone
        for task in config["tasks"]:
            assert set(task.keys()) == _GANTT_TASK_KEYS
