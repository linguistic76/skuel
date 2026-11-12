"""A reopened goal keeps the figure its measure gives; a milestone can be reopened.

Ruled 2026-11-12 (``docs/domains/goals.md`` § "A reopened goal keeps the figure its
measure gives"). On a goal whose percentage follows a measure held elsewhere (the
contribution tally, the habits' streaks, the milestones, ``current_value``), the
reopen's subscriber rewrites the figure from that measure through the planner the
type's own writer uses, with the status half taken off: a reopen restores the
figure, it neither achieves nor un-achieves. ``complete_goal`` writes 100% on every
type, which is what makes this a rewrite and not a leave-alone: a goal completed by
hand at 2 of 5 tasks would otherwise reopen at 100%.

``reopen_milestone`` is ``complete_milestone``'s mirror: the figure falls on a
milestone-measured goal (a fall from 100 un-achieves it), and the milestone keeps the
day it was first reached, which a later completion does not move.

The real graph and the page's controls: ``tests/integration/routes/
test_goal_progress_milestone_doors.py``.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import date
from typing import Any
from unittest.mock import Mock

import pytest

from core.events.base import BaseEvent
from core.events.goal_events import (
    GoalAchieved,
    GoalProgressUpdated,
    GoalReopened,
    GoalUpdated,
)
from core.models.enums import EntityStatus
from core.models.enums.goal_enums import MeasurementType
from core.models.goal.goal import Goal
from core.models.goal.milestone import Milestone
from core.services.goals.goals_progress_service import GoalsProgressService
from core.utils.result_simplified import ErrorCategory, Errors, Result
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone
from tests.helpers.status_guarded_backend import (
    StatusGuardedWriteRecorder,
    guarded_backend,
    wire_locked_recompute,
)

_USER = "user_reopen"
_GOAL = "goal_reopen"
_FIRST = date(2026, 1, 15)


class _Bus:
    def __init__(self) -> None:
        self.events: list[BaseEvent] = []

    async def publish_async(self, event: BaseEvent) -> None:
        self.events.append(event)

    def of[E: BaseEvent](self, event_type: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, event_type)]


def _goal(
    measurement: MeasurementType | None,
    *,
    done: tuple[bool, ...] = (),
    progress: float = 100.0,
    status: EntityStatus = EntityStatus.ACTIVE,
    **fields: Any,  # boundary: Goal's own heterogeneous field set
) -> Goal:
    return Goal(
        uid=_GOAL,
        user_uid=_USER,
        title="Reopened",
        status=status,
        measurement_type=measurement,
        progress_percentage=progress,
        achieved_date=_FIRST if status is EntityStatus.COMPLETED else None,
        milestones=tuple(
            Milestone(
                uid=f"m{i}",
                title=f"Milestone {i}",
                is_completed=flag,
                achieved_date=_FIRST if flag else None,
            )
            for i, flag in enumerate(done)
        ),
        **fields,
    )


@dataclass(frozen=True)
class _Rig:
    service: GoalsProgressService
    backend: Mock
    logger: Mock
    recorder: StatusGuardedWriteRecorder[Goal]
    bus: _Bus


def _rig(goal: Goal) -> _Rig:
    backend, recorder = guarded_backend(goal, goal)
    bus = _Bus()
    logger = Mock()
    service = GoalsProgressService.__new__(GoalsProgressService)
    service.backend = backend
    service.logger = logger
    service.event_bus = bus
    service.relationships = None  # type: ignore[assignment]
    return _Rig(service, backend, logger, recorder, bus)


def _service(goal: Goal) -> tuple[GoalsProgressService, StatusGuardedWriteRecorder[Goal], _Bus]:
    rig = _rig(goal)
    return rig.service, rig.recorder, rig.bus


def _assert_no_status_written(recorder: StatusGuardedWriteRecorder[Goal], bus: _Bus) -> None:
    guard = recorder.last_guard
    assert not guard.has_patches(), "a reopen's recompute never achieves or un-achieves"
    assert "status" not in recorder.merged_patch()
    assert bus.of(GoalAchieved) == []


def test_the_percentage_is_the_measure_on_exactly_the_four_entered_percentage_types() -> None:
    assert {m for m in MeasurementType if m.percentage_is_the_measure()} == {
        MeasurementType.PERCENTAGE,
        MeasurementType.BINARY,
        MeasurementType.KNOWLEDGE_BASED,
        MeasurementType.MIXED,
    }


@pytest.mark.asyncio
class TestRestoreFigureFromMeasure:
    async def test_a_milestone_goal_takes_its_milestones_figure(self) -> None:
        """Completed by hand at 1 of 3: the reopen leaves 100%; the measure says 33%."""
        service, recorder, bus = _service(
            _goal(MeasurementType.MILESTONE, done=(True, False, False))
        )

        result = await service.restore_figure_from_measure(_GOAL, _USER)

        assert result.is_ok and result.value is True
        merged = recorder.merged_patch()
        assert merged["progress_percentage"] == pytest.approx(100 / 3)
        assert (merged["current_value"], merged["target_value"]) == (1.0, 3.0)
        _assert_no_status_written(recorder, bus)
        (moved,) = bus.of(GoalProgressUpdated)
        assert moved.old_progress == 100.0
        assert moved.new_progress == pytest.approx(100 / 3)

    async def test_a_measure_still_at_100_is_not_re_achieved(self) -> None:
        """Every milestone still ticked: 100% on a working goal, and nothing announced
        as an achievement, even from a stored figure below 100."""
        service, recorder, bus = _service(
            _goal(MeasurementType.MILESTONE, done=(True, True), progress=0.0)
        )

        await service.restore_figure_from_measure(_GOAL, _USER)

        assert recorder.merged_patch()["progress_percentage"] == 100.0
        _assert_no_status_written(recorder, bus)

    async def test_a_numeric_goal_takes_its_units_figure_and_keeps_current_value(self) -> None:
        service, recorder, bus = _service(
            _goal(MeasurementType.NUMERIC, current_value=12.5, target_value=50.0)
        )

        await service.restore_figure_from_measure(_GOAL, _USER)

        merged = recorder.merged_patch()
        assert merged["progress_percentage"] == 25.0
        assert merged["current_value"] == 12.5
        _assert_no_status_written(recorder, bus)

    async def test_a_numeric_goal_with_no_target_has_no_figure_to_give(self) -> None:
        service, recorder, _bus = _service(_goal(MeasurementType.NUMERIC, current_value=3.0))

        result = await service.restore_figure_from_measure(_GOAL, _USER)

        assert result.is_ok and result.value is False
        assert recorder.calls == []

    @pytest.mark.parametrize(
        "measurement",
        [
            None,
            MeasurementType.PERCENTAGE,
            MeasurementType.BINARY,
            MeasurementType.KNOWLEDGE_BASED,
            MeasurementType.MIXED,
        ],
    )
    async def test_a_percentage_that_is_the_measure_has_no_other_source(
        self, measurement: MeasurementType | None
    ) -> None:
        service, recorder, _bus = _service(_goal(measurement))

        result = await service.restore_figure_from_measure(_GOAL, _USER)

        assert result.is_ok and result.value is False
        assert recorder.calls == []

    async def test_a_task_based_goal_takes_its_tally_figure(self) -> None:
        goal = _goal(MeasurementType.TASK_BASED)
        rig = _rig(goal)
        service, recorder, bus = rig.service, rig.recorder, rig.bus
        wire_locked_recompute(
            rig.backend,
            recorder,
            goal,
            method="recompute_progress_from_contributions",
            tally={"total_contributions": 5, "completed_contributions": 2},
        )

        await service.restore_figure_from_measure(_GOAL, _USER)

        merged = recorder.merged_patch()
        assert merged["progress_percentage"] == pytest.approx(40.0)
        assert (merged["current_value"], merged["target_value"]) == (2.0, 5.0)
        _assert_no_status_written(recorder, bus)
        (moved,) = bus.of(GoalProgressUpdated)
        assert moved.triggered_by_contribution_change

    async def test_a_habit_based_goal_takes_its_streaks_figure(self) -> None:
        goal = _goal(MeasurementType.HABIT_BASED, target_value=30.0)
        rig = _rig(goal)
        service, recorder, bus = rig.service, rig.recorder, rig.bus
        wire_locked_recompute(
            rig.backend,
            recorder,
            goal,
            method="recompute_progress_from_linked_habits",
            tally={"total_habits": 2, "avg_streak": 15.0},
        )

        await service.restore_figure_from_measure(_GOAL, _USER)

        assert recorder.merged_patch()["progress_percentage"] == pytest.approx(50.0)
        _assert_no_status_written(recorder, bus)

    async def test_the_subscriber_restores_the_named_goal(self) -> None:
        service, recorder, _bus = _service(_goal(MeasurementType.MILESTONE, done=(True, False)))

        await service.handle_goal_reopened(GoalReopened(goal_uid=_GOAL, user_uid=_USER))

        assert recorder.merged_patch()["progress_percentage"] == 50.0

    async def test_the_subscriber_logs_a_failure_and_never_raises(self) -> None:
        rig = _rig(_goal(MeasurementType.MILESTONE, done=(True,)))
        rig.backend.get.return_value = Result.fail(Errors.database("read", "down"))

        await rig.service.handle_goal_reopened(GoalReopened(goal_uid=_GOAL, user_uid=_USER))

        assert rig.recorder.calls == []
        assert rig.logger.error.call_count == 1


@pytest.mark.asyncio
class TestReopenMilestone:
    async def test_reopening_a_milestone_lowers_the_figure_and_un_achieves(self) -> None:
        service, recorder, bus = _service(
            _goal(MeasurementType.MILESTONE, done=(True, True), status=EntityStatus.COMPLETED)
        )

        result = await service.reopen_milestone(_GOAL, "m1")

        assert result.is_ok
        merged = recorder.merged_patch()
        assert merged["progress_percentage"] == 50.0
        assert merged["status"] == EntityStatus.ACTIVE.value
        assert merged["achieved_date"] is None
        (reopened,) = [m for m in merged["milestones"] if m.uid == "m1"]
        assert reopened.is_completed is False
        assert reopened.achieved_date == _FIRST, "the day it was first reached is kept"
        assert len(bus.of(GoalUpdated)) == 1

    async def test_on_a_goal_it_does_not_measure_it_is_a_checklist_entry(self) -> None:
        service, recorder, bus = _service(
            _goal(MeasurementType.PERCENTAGE, done=(True,), progress=70.0)
        )

        await service.reopen_milestone(_GOAL, "m0")

        merged = recorder.merged_patch()
        assert "progress_percentage" not in merged
        assert merged["milestones"][0].is_completed is False
        assert len(bus.of(GoalUpdated)) == 1, "the list changed, so a cached context goes"

    async def test_reopening_an_open_milestone_changes_nothing_and_announces_nothing(
        self,
    ) -> None:
        service, recorder, bus = _service(
            _goal(MeasurementType.MILESTONE, done=(True, False), progress=50.0)
        )

        result = await service.reopen_milestone(_GOAL, "m1")

        assert result.is_ok
        assert recorder.merged_patch()["progress_percentage"] == 50.0
        assert bus.of(GoalUpdated) == []
        assert bus.of(GoalProgressUpdated) == []

    async def test_a_milestone_the_goal_does_not_hold_is_not_found(self) -> None:
        service, recorder, _bus = _service(_goal(MeasurementType.MILESTONE, done=(True,)))

        result = await service.reopen_milestone(_GOAL, "m9")

        assert result.is_error
        assert result.expect_error().category is ErrorCategory.NOT_FOUND
        assert recorder.calls == []

    async def test_completing_a_reopened_milestone_keeps_the_day_it_was_first_reached(
        self,
    ) -> None:
        """A reopened milestone holds its first date with ``is_completed`` false; the
        completion that follows must not move it to today."""
        goal = _goal(MeasurementType.MILESTONE, done=(True, False), progress=50.0)
        reopened = Milestone(uid="m1", title="Milestone 1", achieved_date=_FIRST)
        goal = dataclasses.replace(goal, milestones=(goal.milestones[0], reopened))
        service, recorder, _bus = _service(goal)

        await service.complete_milestone(_GOAL, "m1")

        (written,) = [m for m in recorder.merged_patch()["milestones"] if m.uid == "m1"]
        assert written.is_completed is True
        assert written.achieved_date == _FIRST
        assert today_in(current_zone()) != _FIRST
