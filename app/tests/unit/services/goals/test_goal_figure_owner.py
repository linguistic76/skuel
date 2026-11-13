"""A goal's measurement type names the one writer of its figure.

``progress_percentage`` has four writers: the contribution tally (task-based), the
habit streaks (habit-based), the milestones (milestone) and the learner (every other
type). Each writes only the goals whose type is its own:

- a milestone added or completed moves the figure on a milestone-measured goal, and
  is a checklist entry on any other;
- an entered figure lands on the entered types and is refused on the three derived
  ones, in the goal's own unit on a numeric goal and as the percentage otherwise;
- status follows a figure by one rule for all four: rising to 100 achieves the goal
  unless its owner settled it, falling from 100 un-achieves it.

The writes are planned from the goal a locked rewrite hands the planner; the fake
here plans from the held goal the same way (``StatusGuardedWriteRecorder.rewrite``).
What the lock itself buys is pinned against a real graph in
``tests/integration/routes/test_goal_progress_milestone_doors.py``.
"""

from __future__ import annotations

import re
from datetime import date
from types import MappingProxyType
from typing import Any
from unittest.mock import Mock

import pytest

from core.events.base import BaseEvent
from core.events.goal_events import (
    GoalAchieved,
    GoalMilestoneReached,
    GoalProgressUpdated,
    GoalUpdated,
)
from core.models.enums import EntityStatus
from core.models.enums.goal_enums import MeasurementType
from core.models.goal.goal import Goal
from core.models.goal.milestone import Milestone
from core.services.goals.goals_progress_service import GoalsProgressService
from core.utils.result_simplified import ErrorCategory
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone
from tests.helpers.status_guarded_backend import StatusGuardedWriteRecorder, guarded_backend

_USER = "user_figure"
_GOAL = "goal_figure"
_ACHIEVED = date(2026, 1, 15)


class _Bus:
    def __init__(self) -> None:
        self.events: list[BaseEvent] = []

    async def publish_async(self, event: BaseEvent) -> None:
        self.events.append(event)

    def of[E: BaseEvent](self, event_type: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, event_type)]


def _goal(
    measurement: MeasurementType,
    *,
    done: tuple[bool, ...] = (),
    progress: float = 0.0,
    status: EntityStatus = EntityStatus.ACTIVE,
    **fields: Any,  # boundary: Goal's own heterogeneous field set
) -> Goal:
    return Goal(
        uid=_GOAL,
        user_uid=_USER,
        title="Whose figure",
        status=status,
        measurement_type=measurement,
        progress_percentage=progress,
        achieved_date=_ACHIEVED if status is EntityStatus.COMPLETED else None,
        milestones=tuple(
            Milestone(
                uid=f"m{i}",
                title=f"Milestone {i}",
                is_completed=flag,
                achieved_date=_ACHIEVED if flag else None,
            )
            for i, flag in enumerate(done)
        ),
        **fields,
    )


def _service(goal: Goal) -> tuple[GoalsProgressService, StatusGuardedWriteRecorder[Goal], _Bus]:
    backend, recorder = guarded_backend(goal, goal)
    bus = _Bus()
    service = GoalsProgressService.__new__(GoalsProgressService)
    service.backend = backend
    service.logger = Mock()
    service.event_bus = bus
    service.relationships = None  # type: ignore[assignment]
    return service, recorder, bus


_ENTERED = (
    MeasurementType.PERCENTAGE,
    MeasurementType.NUMERIC,
    MeasurementType.BINARY,
    MeasurementType.KNOWLEDGE_BASED,
    MeasurementType.MIXED,
)
_DERIVED = (MeasurementType.TASK_BASED, MeasurementType.HABIT_BASED, MeasurementType.MILESTONE)


def test_every_measurement_type_has_exactly_one_figure_writer() -> None:
    assert set(_ENTERED) | set(_DERIVED) == set(MeasurementType)
    assert {m for m in MeasurementType if m.takes_entered_figure()} == set(_ENTERED)
    assert [m for m in MeasurementType if m.follows_milestones()] == [MeasurementType.MILESTONE]
    assert [m for m in MeasurementType if m.entered_in_units()] == [MeasurementType.NUMERIC]


class TestMilestonesOnAGoalTheyDoNotMeasure:
    @pytest.mark.parametrize(
        "measurement", [m for m in MeasurementType if not m.follows_milestones()]
    )
    async def test_completing_the_last_one_writes_the_list_alone(
        self, measurement: MeasurementType
    ) -> None:
        goal = _goal(measurement, done=(True, False), progress=40.0, target_value=50.0)
        service, recorder, bus = _service(goal)

        result = await service.complete_milestone(_GOAL, "m1")

        assert result.is_ok
        assert set(recorder.merged_patch()) == {"milestones"}
        assert [m.is_completed for m in recorder.last_updates["milestones"]] == [True, True]
        assert len(bus.of(GoalMilestoneReached)) == 1
        assert bus.of(GoalProgressUpdated) == []
        assert bus.of(GoalAchieved) == []

    async def test_adding_one_writes_the_list_alone(self) -> None:
        goal = _goal(MeasurementType.PERCENTAGE, done=(True,), progress=100.0)
        service, recorder, bus = _service(goal)

        result = await service.create_goal_milestone(_GOAL, "One more")

        assert result.is_ok
        assert set(recorder.merged_patch()) == {"milestones"}
        assert [type(e) for e in bus.events] == [GoalUpdated]


class TestMilestonesOnAMilestoneGoal:
    async def test_a_completion_writes_the_figure_and_both_counts(self) -> None:
        goal = _goal(MeasurementType.MILESTONE, done=(False, False, False, False))
        service, recorder, bus = _service(goal)

        assert (await service.complete_milestone(_GOAL, "m2")).is_ok

        patch = recorder.merged_patch()
        assert patch["progress_percentage"] == 25.0
        assert (patch["current_value"], patch["target_value"]) == (1.0, 4.0)
        assert "status" not in patch
        reached = bus.of(GoalMilestoneReached)
        assert [e.milestone_percentage for e in reached] == [0.25]
        progressed = bus.of(GoalProgressUpdated)
        assert [(e.old_progress, e.new_progress) for e in progressed] == [(0.0, 25.0)]
        assert not progressed[0].triggered_by_manual_update

    async def test_a_repeat_moves_no_stamp_and_announces_nothing(self) -> None:
        goal = _goal(MeasurementType.MILESTONE, done=(True, False), progress=50.0)
        service, recorder, bus = _service(goal)

        assert (await service.complete_milestone(_GOAL, "m0")).is_ok

        patch = recorder.merged_patch()
        assert patch["milestones"][0].achieved_date == _ACHIEVED
        assert "last_progress_update" not in patch
        assert "progress_history" not in patch
        assert bus.events == []

    async def test_a_first_completion_is_dated_today(self) -> None:
        goal = _goal(MeasurementType.MILESTONE, done=(True, False), progress=50.0)
        service, recorder, _bus = _service(goal)

        assert (await service.complete_milestone(_GOAL, "m1")).is_ok

        assert recorder.last_updates["milestones"][1].achieved_date == today_in(current_zone())

    async def test_adding_one_to_an_achieved_goal_un_achieves_it(self) -> None:
        goal = _goal(
            MeasurementType.MILESTONE,
            done=(True, True),
            progress=100.0,
            status=EntityStatus.COMPLETED,
        )
        service, recorder, bus = _service(goal)

        assert (await service.create_goal_milestone(_GOAL, "A third")).is_ok

        patch = recorder.merged_patch()
        assert patch["progress_percentage"] == pytest.approx(200 / 3)
        assert patch["status"] == EntityStatus.ACTIVE.value
        assert patch["achieved_date"] is None
        assert bus.of(GoalAchieved) == []

    @pytest.mark.parametrize(
        "settled", [EntityStatus.CANCELLED, EntityStatus.ARCHIVED, EntityStatus.FAILED]
    )
    async def test_the_last_one_does_not_achieve_a_goal_its_owner_settled(
        self, settled: EntityStatus
    ) -> None:
        goal = _goal(MeasurementType.MILESTONE, done=(True, False), progress=50.0, status=settled)
        service, recorder, bus = _service(goal)

        assert (await service.complete_milestone(_GOAL, "m1")).is_ok

        patch = recorder.merged_patch()
        assert patch["progress_percentage"] == 100.0
        assert "status" not in patch
        assert bus.of(GoalAchieved) == []

    async def test_an_added_milestone_takes_a_generated_uid_and_the_fields_given(self) -> None:
        goal = _goal(MeasurementType.MILESTONE, done=(True,), progress=100.0)
        service, recorder, _bus = _service(goal)
        target = date(2027, 3, 1)

        assert (await service.create_goal_milestone(_GOAL, "Draft", target, "All chapters")).is_ok

        kept, added = recorder.last_updates["milestones"]
        assert kept.uid == "m0"
        assert re.fullmatch(r"milestone_[0-9a-f]{16}", added.uid)
        assert (added.title, added.target_date, added.description) == (
            "Draft",
            target,
            "All chapters",
        )
        assert (added.is_completed, added.achieved_date) == (False, None)


async def test_a_milestone_the_goal_does_not_hold_is_not_found_and_writes_nothing() -> None:
    goal = _goal(MeasurementType.MILESTONE, done=(True, False))
    service, recorder, bus = _service(goal)

    result = await service.complete_milestone(_GOAL, "m9")

    assert result.is_error
    assert result.expect_error().category is ErrorCategory.NOT_FOUND
    assert recorder.calls == []
    assert bus.events == []


class TestAnEnteredFigure:
    @pytest.mark.parametrize("measurement", _DERIVED)
    async def test_a_derived_goal_refuses_it_and_keeps_its_figure(
        self, measurement: MeasurementType
    ) -> None:
        goal = _goal(measurement, progress=20.0, target_value=30.0)
        service, recorder, bus = _service(goal)

        result = await service.update_goal_progress(_GOAL, 80.0)

        assert result.is_error
        assert result.expect_error().category is ErrorCategory.BUSINESS
        assert recorder.calls == []
        assert bus.events == []

    @pytest.mark.parametrize("measurement", [m for m in _ENTERED if not m.entered_in_units()])
    async def test_a_percentage_is_the_figure(self, measurement: MeasurementType) -> None:
        goal = _goal(measurement, progress=20.0, target_value=30.0)
        service, recorder, bus = _service(goal)

        assert (await service.update_goal_progress(_GOAL, 80.0)).is_ok

        patch = recorder.merged_patch()
        assert patch["progress_percentage"] == 80.0
        assert "current_value" not in patch
        assert [e.triggered_by_manual_update for e in bus.of(GoalProgressUpdated)] == [True]

    @pytest.mark.parametrize("figure", [100.01, 250.0])
    async def test_a_percentage_above_100_is_refused(self, figure: float) -> None:
        service, recorder, _bus = _service(_goal(MeasurementType.PERCENTAGE))

        result = await service.update_goal_progress(_GOAL, figure)

        assert result.expect_error().category is ErrorCategory.VALIDATION
        assert recorder.calls == []

    async def test_a_negative_figure_is_refused(self) -> None:
        service, recorder, _bus = _service(_goal(MeasurementType.PERCENTAGE))

        result = await service.update_goal_progress(_GOAL, -1.0)

        assert result.expect_error().category is ErrorCategory.VALIDATION
        assert recorder.calls == []

    async def test_a_numeric_goal_takes_its_unit_and_derives_the_percentage(self) -> None:
        goal = _goal(MeasurementType.NUMERIC, target_value=50.0, unit_of_measurement="pages")
        service, recorder, _bus = _service(goal)

        assert (await service.update_goal_progress(_GOAL, 30.0)).is_ok

        patch = recorder.merged_patch()
        assert patch["current_value"] == 30.0
        assert patch["progress_percentage"] == 60.0
        assert "target_value" not in patch

    async def test_a_numeric_figure_past_the_target_is_kept_and_the_percentage_capped(self) -> None:
        goal = _goal(MeasurementType.NUMERIC, target_value=50.0)
        service, recorder, bus = _service(goal)

        assert (await service.update_goal_progress(_GOAL, 65.0)).is_ok

        patch = recorder.merged_patch()
        assert (patch["current_value"], patch["progress_percentage"]) == (65.0, 100.0)
        assert patch["status"] == EntityStatus.COMPLETED.value
        assert len(bus.of(GoalAchieved)) == 1

    @pytest.mark.parametrize("target", [None, 0.0])
    async def test_a_numeric_goal_with_no_target_is_refused(self, target: float | None) -> None:
        service, recorder, _bus = _service(_goal(MeasurementType.NUMERIC, target_value=target))

        result = await service.update_goal_progress(_GOAL, 30.0)

        assert result.expect_error().category is ErrorCategory.VALIDATION
        assert recorder.calls == []

    async def test_reaching_100_achieves_the_goal_once(self) -> None:
        service, recorder, bus = _service(_goal(MeasurementType.PERCENTAGE, progress=90.0))

        assert (await service.update_goal_progress(_GOAL, 100.0)).is_ok

        patch = recorder.merged_patch()
        assert patch["status"] == EntityStatus.COMPLETED.value
        assert patch["achieved_date"] == today_in(current_zone())
        assert len(bus.of(GoalAchieved)) == 1

    async def test_re_entering_100_on_an_achieved_goal_moves_no_stamp(self) -> None:
        goal = _goal(MeasurementType.PERCENTAGE, progress=100.0, status=EntityStatus.COMPLETED)
        service, recorder, bus = _service(goal)

        assert (await service.update_goal_progress(_GOAL, 100.0)).is_ok

        assert set(recorder.merged_patch()) == {"progress_percentage"}
        assert bus.events == []

    async def test_falling_from_100_un_achieves_the_goal(self) -> None:
        goal = _goal(MeasurementType.PERCENTAGE, progress=100.0, status=EntityStatus.COMPLETED)
        service, recorder, bus = _service(goal)

        assert (await service.update_goal_progress(_GOAL, 80.0)).is_ok

        patch = recorder.merged_patch()
        assert patch["status"] == EntityStatus.ACTIVE.value
        assert patch["achieved_date"] is None
        assert bus.of(GoalAchieved) == []

    async def test_a_goal_completed_by_hand_below_100_stays_completed(self) -> None:
        goal = _goal(MeasurementType.PERCENTAGE, progress=40.0, status=EntityStatus.COMPLETED)
        service, recorder, _bus = _service(goal)

        assert (await service.update_goal_progress(_GOAL, 60.0)).is_ok

        assert "status" not in recorder.merged_patch()

    async def test_100_does_not_achieve_a_goal_its_owner_settled(self) -> None:
        goal = _goal(MeasurementType.PERCENTAGE, progress=10.0, status=EntityStatus.CANCELLED)
        service, recorder, bus = _service(goal)

        assert (await service.update_goal_progress(_GOAL, 100.0)).is_ok

        assert "status" not in recorder.merged_patch()
        assert bus.of(GoalAchieved) == []

    async def test_a_note_rides_the_entry_the_figure_appends_after_a_frozen_history(
        self,
    ) -> None:
        held = (MappingProxyType({"date": "2026-01-01T09:00:00", "progress_percentage": 5.0}),)
        goal = _goal(MeasurementType.PERCENTAGE, progress=5.0, progress_history=held)
        service, recorder, bus = _service(goal)

        assert (await service.update_goal_progress(_GOAL, 10.0, note="second")).is_ok

        history = recorder.last_updates["progress_history"]
        assert [entry.get("note") for entry in history] == [None, "second"]
        assert "note_only" not in history[-1]
        assert "metadata" not in recorder.last_updates
        assert len(bus.of(GoalProgressUpdated)) == 1

    async def test_a_note_with_the_figure_unmoved_is_a_note_only_entry_and_no_event(
        self,
    ) -> None:
        goal = _goal(MeasurementType.PERCENTAGE, progress=40.0)
        service, recorder, bus = _service(goal)

        assert (await service.update_goal_progress(_GOAL, 40.0, note="Stuck this week")).is_ok

        updates = recorder.last_updates
        (entry,) = updates["progress_history"]
        assert entry["note"] == "Stuck this week"
        assert entry["note_only"] is True
        assert entry["progress_percentage"] == 40.0
        assert "last_progress_update" not in updates, "a note alone is not a progress event"
        assert bus.of(GoalProgressUpdated) == []

    async def test_an_unmoved_figure_without_a_note_appends_nothing(self) -> None:
        goal = _goal(MeasurementType.PERCENTAGE, progress=40.0)
        service, recorder, _bus = _service(goal)

        assert (await service.update_goal_progress(_GOAL, 40.0)).is_ok

        assert "progress_history" not in recorder.merged_patch()
