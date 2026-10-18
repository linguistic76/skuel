"""VisualizationAggregationService's Chart.js reads, over fake domain facades.

Pins what each chart counts from the tasks and habits it is handed, and that a
failed domain read comes back as the chart's failure, unchanged.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.enums import EntityStatus
from core.models.habit.habit import Habit
from core.models.task.task import Task
from core.ports.query_types import ChartJsConfig, ChartJsDataset
from core.services.analytics.visualization_aggregation_service import (
    VisualizationAggregationService,
)
from core.services.visualization_service import VisualizationService
from core.utils.result_simplified import Errors, Result
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone

TODAY = today_in(current_zone())


def _task(uid: str, **fields: object) -> Task:
    return Task(uid=uid, title=f"Task {uid}", user_uid="user_x", **fields)  # type: ignore[arg-type]


def _service(
    tasks_in_range: Result[list[Task]] | None = None,
    tasks_by_status: Result[list[Task]] | None = None,
    habits_by_status: Result[list[Habit]] | None = None,
) -> VisualizationAggregationService:
    tasks, habits = MagicMock(), MagicMock()
    tasks.get_user_items_in_range = AsyncMock(return_value=tasks_in_range or Result.ok([]))
    tasks.search.get_by_status = AsyncMock(return_value=tasks_by_status or Result.ok([]))
    habits.search.get_by_status = AsyncMock(return_value=habits_by_status or Result.ok([]))
    return VisualizationAggregationService(
        tasks_service=tasks,
        habits_service=habits,
        goals_service=MagicMock(),
        visualization_service=VisualizationService(),
    )


def _dataset(config: ChartJsConfig) -> ChartJsDataset:
    return config["data"]["datasets"][0]


async def test_week_completion_counts_tasks_due_or_scheduled_each_day() -> None:
    week_start = TODAY - timedelta(days=6)
    tasks = [
        _task("t1", due_date=week_start, status=EntityStatus.COMPLETED),
        _task("t2", scheduled_date=week_start, status=EntityStatus.ACTIVE),
        _task("t3", due_date=TODAY, status=EntityStatus.COMPLETED),
    ]
    config = (
        await _service(tasks_in_range=Result.ok(tasks)).get_completion_chart_data("user_x", "week")
    ).value

    assert config["type"] == "line"
    assert config["data"]["labels"] == [
        (week_start + timedelta(days=i)).strftime("%a") for i in range(7)
    ]
    assert _dataset(config)["data"] == [50.0, 0, 0, 0, 0, 0, 100.0]


async def test_month_completion_buckets_three_days() -> None:
    start = TODAY - timedelta(days=29)
    tasks = [
        _task("t1", due_date=start + timedelta(days=2), status=EntityStatus.COMPLETED),
        _task("t2", scheduled_date=start + timedelta(days=4), status=EntityStatus.ACTIVE),
    ]
    config = (
        await _service(tasks_in_range=Result.ok(tasks)).get_completion_chart_data("user_x", "month")
    ).value

    assert _dataset(config)["data"][:2] == [100.0, 0.0]


async def test_priority_distribution_counts_active_tasks_that_have_a_priority() -> None:
    tasks = [_task("t1", priority="high"), _task("t2", priority="high"), _task("t3")]
    config = (
        await _service(tasks_by_status=Result.ok(tasks)).get_priority_distribution_chart_data(
            "user_x"
        )
    ).value

    assert config["type"] == "doughnut"
    assert dict(zip(config["data"]["labels"], _dataset(config)["data"], strict=True)) == {"high": 2}


async def test_status_distribution_counts_tasks_by_status() -> None:
    tasks = [
        _task("t1", status=EntityStatus.COMPLETED),
        _task("t2", status=EntityStatus.ACTIVE),
        _task("t3", status=EntityStatus.ACTIVE),
    ]
    config = (
        await _service(tasks_in_range=Result.ok(tasks)).get_status_distribution_chart_data("user_x")
    ).value

    assert config["type"] == "pie"
    assert dict(zip(config["data"]["labels"], _dataset(config)["data"], strict=True)) == {
        "completed": 1,
        "active": 2,
    }


async def test_streak_chart_reads_each_habits_streaks() -> None:
    habits = [Habit(uid="h1", title="Read", user_uid="user_x", current_streak=3, best_streak=9)]
    config = (
        await _service(habits_by_status=Result.ok(habits)).get_streak_chart_data("user_x")
    ).value

    assert config["data"]["labels"] == ["Read"]
    assert [ds["data"] for ds in config["data"]["datasets"]] == [[3], [9]]


@pytest.mark.parametrize(
    ("chart", "failing"),
    [
        ("get_completion_chart_data", "tasks_in_range"),
        ("get_priority_distribution_chart_data", "tasks_by_status"),
        ("get_status_distribution_chart_data", "tasks_in_range"),
        ("get_streak_chart_data", "habits_by_status"),
    ],
)
async def test_a_failed_domain_read_is_the_charts_failure(chart: str, failing: str) -> None:
    failure: Result[list[Task]] = Result.fail(Errors.database("find_by", "graph unavailable"))
    service = _service(**{failing: failure})
    args = ("user_x", "week") if chart == "get_completion_chart_data" else ("user_x",)

    result = await getattr(service, chart)(*args)

    assert result.is_error
    assert result.expect_error() is failure.expect_error()


async def test_no_active_tasks_is_not_found() -> None:
    result = await _service().get_priority_distribution_chart_data("user_x")
    assert result.is_error
