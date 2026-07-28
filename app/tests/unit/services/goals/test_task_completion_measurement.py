"""What ``_update_goal_from_task_completion`` writes into the measurement fields.

For a TASK_BASED goal the measurement *is* the linked-task tally, so this writer owns
both ends of it. That is unusual — every other progress writer leaves ``target_value``
alone — and it is bounded by a fact the tests below pin: ``target_value`` has no
computational consumer for TASK_BASED (``calculate_combined_progress`` returns
``task_contribution * 100`` and discards ``milestone_completion``), whereas for MIXED it
is the denominator ``_update_goal_from_habit_completion`` divides ``avg_streak`` by.
Overwrite it for MIXED and the habit half of a mixed goal is corrupted.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums.goal_enums import MeasurementType
from core.models.goal.goal import Goal
from core.services.goals.goals_progress_service import GoalsProgressService
from core.utils.result_simplified import Result

_USER = "user_task_measurement"


def _goal(measurement_type: MeasurementType, **overrides: object) -> Goal:
    fields: dict[str, object] = {
        "uid": "goal_task_measurement",
        "user_uid": _USER,
        "title": "Ship the thing",
        "measurement_type": measurement_type,
        "target_value": 5.0,
        "current_value": 0.0,
        "progress_percentage": 0.0,
    }
    fields.update(overrides)
    return Goal(**fields)  # type: ignore[arg-type]


def _service(
    goal: Goal, *, total_tasks: int, completed_tasks: int
) -> tuple[GoalsProgressService, Mock]:
    """A progress service whose backend reports a fixed linked-task tally."""
    backend = Mock()
    backend.get = AsyncMock(return_value=Result.ok(goal))
    backend.update = AsyncMock(return_value=Result.ok({}))
    backend.count_linked_tasks = AsyncMock(
        return_value=Result.ok({"total_tasks": total_tasks, "completed_tasks": completed_tasks})
    )

    service = GoalsProgressService.__new__(GoalsProgressService)
    service.backend = backend
    service.logger = Mock()
    service.event_bus = None
    service.relationships = None
    return service, backend


async def _written(goal: Goal, *, total_tasks: int, completed_tasks: int) -> dict:
    service, backend = _service(goal, total_tasks=total_tasks, completed_tasks=completed_tasks)
    await service._update_goal_from_task_completion(goal.uid, _USER)
    assert backend.update.await_count == 1, "expected exactly one write"
    return backend.update.await_args.args[1]


class TestTaskBasedGoalOwnsItsMeasurement:
    async def test_both_ends_are_written_from_the_linked_task_tally(self):
        """1 of 5 tasks: the detail page must render "1/5", not "0/5"."""
        updates = await _written(
            _goal(MeasurementType.TASK_BASED), total_tasks=5, completed_tasks=1
        )

        assert updates["current_value"] == 1.0
        assert updates["target_value"] == 5.0
        assert updates["progress_percentage"] == pytest.approx(20.0)

    async def test_a_user_typed_target_is_replaced_by_the_real_denominator(self):
        """The case that rules out writing current_value alone.

        ``target_value=5`` was typed by hand; 20 tasks are actually linked, and the
        percent is computed from those 20. Persisting ``completed_tasks`` against the
        typed 5 would render "4/5 tasks" beside a 20% bar.
        """
        updates = await _written(
            _goal(MeasurementType.TASK_BASED), total_tasks=20, completed_tasks=4
        )

        assert updates["current_value"] == 4.0
        assert updates["target_value"] == 20.0
        assert updates["progress_percentage"] == pytest.approx(20.0)

    async def test_the_three_fields_agree(self):
        """current/target is the percent, by construction rather than by luck."""
        updates = await _written(
            _goal(MeasurementType.TASK_BASED), total_tasks=8, completed_tasks=3
        )

        ratio = updates["current_value"] / updates["target_value"]
        assert ratio * 100 == pytest.approx(updates["progress_percentage"])


class TestMixedGoalMeasurementIsNotTouched:
    """MIXED shares this writer but not the ownership — its target_value is a streak."""

    async def test_neither_measurement_field_is_written(self):
        updates = await _written(
            _goal(MeasurementType.MIXED, target_value=30.0),
            total_tasks=5,
            completed_tasks=1,
        )

        assert "current_value" not in updates
        assert "target_value" not in updates, (
            "MIXED divides avg_streak by target_value — overwriting it corrupts the habit half"
        )
        assert "progress_percentage" in updates
