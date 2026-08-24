"""What the task- and habit-completion writers put in the measurement fields.

For a TASK_BASED goal the measurement *is* the linked-task tally, so this writer owns
both ends of it. That is unusual — every other progress writer leaves ``target_value``
alone — and it is bounded by a fact the tests below pin: ``target_value`` has no
computational consumer for TASK_BASED (``calculate_combined_progress`` returns
``task_contribution * 100`` and discards ``milestone_completion``), whereas for MIXED it
is the denominator ``_update_goal_from_habit_completion`` divides ``avg_streak`` by.
Overwrite it for MIXED and the habit half of a mixed goal is corrupted.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums.goal_enums import MeasurementType
from core.models.goal.goal import Goal
from core.services.goals.goals_progress_service import GoalsProgressService
from core.utils.result_simplified import Result
from tests.helpers.status_guarded_backend import (
    StatusGuardedWriteRecorder,
    guarded_backend,
)

_USER = "user_task_measurement"


class _RecordingBus:
    """Captures what the handler publishes — ``publish_event`` calls ``publish_async``."""

    def __init__(self, sink: list[object]) -> None:
        self._sink = sink

    async def publish_async(self, event: object) -> None:
        self._sink.append(event)


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
) -> tuple[GoalsProgressService, StatusGuardedWriteRecorder[Goal]]:
    """A progress service whose backend reports a fixed linked-task tally.

    The write goes through the status-guarded primitive (ADR-087), so the assertions
    below read the RESOLVED patch — base fields plus whichever conditional patch the
    goal's own status selects. For every case in this file the two are the same thing:
    the achievement pair is the only conditional part, and these are measurement tests.
    """
    backend, recorder = guarded_backend(goal, goal)
    backend.count_linked_tasks = AsyncMock(
        return_value=Result.ok({"total_tasks": total_tasks, "completed_tasks": completed_tasks})
    )

    service = GoalsProgressService.__new__(GoalsProgressService)
    service.backend = backend
    service.logger = Mock()
    service.event_bus = None
    service.relationships = None
    return service, recorder


async def _written(
    goal: Goal, *, total_tasks: int, completed_tasks: int
) -> dict[str, Any]:  # boundary: pre-serialization patch
    service, recorder = _service(goal, total_tasks=total_tasks, completed_tasks=completed_tasks)
    await service._update_goal_from_task_completion(goal.uid, _USER)
    assert len(recorder.calls) == 1, "expected exactly one write"
    return recorder.merged_patch()


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

    async def test_a_changed_tally_at_the_same_percent_still_writes(self):
        """1-of-5 and 2-of-10 are both 20%, so the unchanged-progress guard would
        return before the tally write and leave the page rendering "1/5 tasks" after
        five more tasks were linked and one completed. The tally is part of "changed".
        """
        goal = _goal(
            MeasurementType.TASK_BASED,
            current_value=1.0,
            target_value=5.0,
            progress_percentage=20.0,
        )
        updates = await _written(goal, total_tasks=10, completed_tasks=2)

        assert updates["current_value"] == 2.0
        assert updates["target_value"] == 10.0
        assert updates["progress_percentage"] == pytest.approx(20.0)

    async def test_an_unchanged_tally_at_the_same_percent_does_not_write(self):
        """The guard still does its job — a no-op event must stay a no-op."""
        goal = _goal(
            MeasurementType.TASK_BASED,
            current_value=1.0,
            target_value=5.0,
            progress_percentage=20.0,
        )
        service, recorder = _service(goal, total_tasks=5, completed_tasks=1)

        await service._update_goal_from_task_completion(goal.uid, _USER)

        assert recorder.calls == []

    async def test_a_tally_only_write_publishes_no_progress_event(self):
        """``handle_goal_progress_updated`` reads a near-zero delta on a positive goal
        as a stall and persists an IMBALANCE_DETECTED insight, so announcing a
        tally-only repair would tell a user who just completed a task that their goal
        has stalled.
        """
        goal = _goal(
            MeasurementType.TASK_BASED,
            current_value=1.0,
            target_value=5.0,
            progress_percentage=20.0,
        )
        service, recorder = _service(goal, total_tasks=10, completed_tasks=2)
        published: list[object] = []
        service.event_bus = _RecordingBus(published)

        await service._update_goal_from_task_completion(goal.uid, _USER)

        assert len(recorder.calls) == 1, "the tally repair itself must still happen"
        assert published == []

    async def test_a_real_progress_change_still_publishes(self):
        """The mirror — suppressing the event must not silence genuine movement."""
        goal = _goal(
            MeasurementType.TASK_BASED,
            current_value=1.0,
            target_value=5.0,
            progress_percentage=20.0,
        )
        service, _ = _service(goal, total_tasks=5, completed_tasks=2)
        published: list[object] = []
        service.event_bus = _RecordingBus(published)

        await service._update_goal_from_task_completion(goal.uid, _USER)

        assert [type(e).__name__ for e in published] == ["GoalProgressUpdated"]

    async def test_a_tally_only_write_does_not_restamp_achieved_date(self):
        """5/5 -> 10/10 is 100% either way. ``>= 100`` alone would move the recorded
        achievement to today; the gate is the transition, as GoalAchieved's already was.
        """
        goal = _goal(
            MeasurementType.TASK_BASED,
            current_value=5.0,
            target_value=5.0,
            progress_percentage=100.0,
        )
        updates = await _written(goal, total_tasks=10, completed_tasks=10)

        assert updates["current_value"] == 10.0
        assert "achieved_date" not in updates
        assert "status" not in updates

    async def test_the_three_fields_agree(self):
        """current/target is the percent, by construction rather than by luck."""
        updates = await _written(
            _goal(MeasurementType.TASK_BASED), total_tasks=8, completed_tasks=3
        )

        ratio = updates["current_value"] / updates["target_value"]
        assert ratio * 100 == pytest.approx(updates["progress_percentage"])


def _habit_service(
    goal: Goal, *, total_habits: int, avg_streak: float
) -> tuple[GoalsProgressService, StatusGuardedWriteRecorder[Goal]]:
    """The habit sibling of ``_service`` — same writer shape, different tally source."""
    backend, recorder = guarded_backend(goal, goal)
    backend.count_linked_habits_avg_streak = AsyncMock(
        return_value=Result.ok({"total_habits": total_habits, "avg_streak": avg_streak})
    )

    service = GoalsProgressService.__new__(GoalsProgressService)
    service.backend = backend
    service.logger = Mock()
    service.event_bus = None
    service.relationships = None
    return service, recorder


class TestHabitGoalMeasurementKeepsUpdatingPastTarget:
    """``new_progress`` is capped at 100, so the percentage stops moving before the
    streak does. Without measurement staleness in the guard the field tracks a *falling*
    streak (which moves the percentage) but freezes on a rising one.
    """

    async def test_a_streak_past_its_target_still_updates_the_measurement(self):
        """30-day target, streak now 31: "30/30 days" must not be the final answer."""
        goal = _goal(
            MeasurementType.HABIT_BASED,
            target_value=30.0,
            current_value=30.0,
            progress_percentage=100.0,
        )
        service, recorder = _habit_service(goal, total_habits=1, avg_streak=31.0)

        await service._update_goal_from_habit_completion(goal.uid, _USER, 31)

        assert len(recorder.calls) == 1
        assert recorder.merged_patch()["current_value"] == 31.0

    async def test_it_does_not_restamp_achieved_date(self):
        goal = _goal(
            MeasurementType.HABIT_BASED,
            target_value=30.0,
            current_value=30.0,
            progress_percentage=100.0,
        )
        service, recorder = _habit_service(goal, total_habits=1, avg_streak=31.0)

        await service._update_goal_from_habit_completion(goal.uid, _USER, 31)

        updates = recorder.merged_patch()
        assert "achieved_date" not in updates
        assert "status" not in updates

    async def test_it_publishes_no_stall_shaped_progress_event(self):
        goal = _goal(
            MeasurementType.HABIT_BASED,
            target_value=30.0,
            current_value=30.0,
            progress_percentage=100.0,
        )
        service, _recorder = _habit_service(goal, total_habits=1, avg_streak=31.0)
        published: list[object] = []
        service.event_bus = _RecordingBus(published)

        await service._update_goal_from_habit_completion(goal.uid, _USER, 31)

        assert published == []

    async def test_an_unchanged_streak_still_writes_nothing(self):
        goal = _goal(
            MeasurementType.HABIT_BASED,
            target_value=30.0,
            current_value=30.0,
            progress_percentage=100.0,
        )
        service, recorder = _habit_service(goal, total_habits=1, avg_streak=30.0)

        await service._update_goal_from_habit_completion(goal.uid, _USER, 30)

        assert recorder.calls == []


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
