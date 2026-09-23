"""The four goal-progress writers derive achievement from the WRITE (ADR-087 PR-4).

Each of ``GoalsProgressService``'s four completion-bearing writers used to answer one
question — "is this goal achieved now?" — from data it read *before* it wrote:
``complete_milestone`` from the goal's status, the other three from the stored
``progress_percentage``. Both are stale by the time the write lands, and the two
failures are opposite:

- **stale-open** — the writer read a goal that was not yet completed, another writer
  completed it first, and this one re-stamps ``achieved_date`` to today and re-publishes
  ``GoalAchieved``. A mutable completion stamp plus a duplicated PRINCIPLE_ALIGNMENT
  insight (``GoalEventHandlerService`` appends one per event under a per-second UID).
- **stale-completed** — the writer read a completed goal, another writer reopened it,
  and this one silently declines to record a genuine achievement.

Now the derivation splits. The *target* ("every milestone is done", "progress reached
100") stays in Python: it is a statement about the new state. The *"…and not already
achieved"* half is a ``patch_if_prior_not_in`` the write evaluates against the status the
node holds under its lock, and the ``GoalAchieved`` verdict comes back from the same
write via ``is_completion_transition(outcome.prior_status, patch)``. So the stamp and the
event cannot disagree, whatever the pre-read saw.

**Why every rig below drives the prior away from the read.** A fake that answers the
guard from whatever ``backend.get`` returned can only ever confirm the coupling this arc
removed — it would pass just as well against the old code. So each test of the two
pre-read writers (``complete_milestone``, ``update_goal_from_habit_progress``) seeds a
stored goal the write sees and a *different* goal the read returns, which is exactly
what a race produces. The two tally recomputes have no pre-read left to race: they plan
from the goal as read under the lock their write holds, so their rig (``_locked_rig``)
hands the planner the prior itself, and their tests pin the verdict of each locked state
— including the un-achieve (docs/roadmap/done/goal-progress-one-way.md).

The unraced behaviour of these writers (which fields, which events, which no-ops) is
pinned in ``test_goal_achievement_transition.py`` and
``test_task_completion_measurement.py``; ``tests/integration/test_goal_completion_cycle.py``
pins a milestone completion end to end against a real graph.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from core.events.base import BaseEvent
from core.events.goal_events import GoalAchieved
from core.models.enums import EntityStatus
from core.models.enums.goal_enums import MeasurementType
from core.models.goal.goal import Goal
from core.models.goal.milestone import Milestone
from core.services.goals.goals_progress_service import GoalsProgressService
from core.utils.result_simplified import Result
from tests.helpers.status_guarded_backend import (
    StatusGuardedWriteRecorder,
    guarded_backend,
    wire_locked_recompute,
)

_USER = "user_progress_guard"
_GOAL = "goal_progress_guard"
_HABIT = "habit_progress_guard"

#: An achievement recorded before today — the value a re-stamp would destroy.
_ORIGINAL_ACHIEVED = date(2026, 1, 15)


class _Bus:
    """Captures what a writer publishes — ``publish_event`` calls ``publish_async``."""

    def __init__(self) -> None:
        self.events: list[BaseEvent] = []

    async def publish_async(self, event: BaseEvent) -> None:
        self.events.append(event)

    def of[E: BaseEvent](self, event_type: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, event_type)]


class _Relationships:
    """Only ``get_related_uids`` — the shape ``fetch_relationships_parallel`` falls back
    to. A bare ``Mock`` would auto-create ``supporting_habits`` and hand
    ``asyncio.gather`` a non-awaitable."""

    def __init__(self, mapping: dict[str, list[str]]) -> None:
        self._mapping = mapping

    async def get_related_uids(self, key: str, uid: str) -> Result[list[str]]:
        return Result.ok(list(self._mapping.get(key, [])))


def _rig(
    *,
    read: Goal,
    stored: Goal,
    relationships: _Relationships | None = None,
    **tallies: Result[dict[str, Any]],  # boundary: the backend's own count-row shape
) -> tuple[GoalsProgressService, StatusGuardedWriteRecorder[Goal], _Bus]:
    """A progress service whose READ and whose WRITE-TIME PRIOR disagree.

    ``read`` answers ``get`` / ``get_goal`` (what the writer derives its target from);
    ``stored`` supplies the status the guard is resolved against, standing in for what a
    concurrent writer left on the node. ``tallies`` configures whichever counting method
    the writer under test calls.
    """
    backend, recorder = guarded_backend(stored, read)
    backend.get = AsyncMock(return_value=Result.ok(read))
    backend.get_goal = AsyncMock(return_value=Result.ok(read))
    for name, row in tallies.items():
        setattr(backend, name, AsyncMock(return_value=row))

    bus = _Bus()
    service = GoalsProgressService.__new__(GoalsProgressService)
    service.backend = backend
    service.logger = Mock()
    service.event_bus = bus
    service.relationships = relationships  # type: ignore[assignment]
    return service, recorder, bus


def _merged(
    recorder: StatusGuardedWriteRecorder[Goal],
) -> dict[str, Any]:  # boundary: pre-serialization patch
    """What the write actually merged for the prior it saw — the Cypher's CASE arms.

    The patch is genuinely heterogeneous (float, ``date``, ``list[Milestone]``); every
    assertion here is a membership or equality check, so nothing needs a narrower type.
    """
    assert len(recorder.calls) == 1, "expected exactly one write"
    return recorder.merged_patch()


def _assert_suppressed(recorder: StatusGuardedWriteRecorder[Goal], bus: _Bus) -> None:
    """The stale-open verdict: the recompute lands, the completion pair does not."""
    merged = _merged(recorder)
    assert "achieved_date" not in merged, "re-stamped a goal another writer completed"
    assert "status" not in merged, "re-wrote a status the goal already held"
    assert bus.of(GoalAchieved) == [], "a re-publish duplicates the alignment insight"
    assert merged, "the progress recompute itself must still have been written"


def _assert_achieved(recorder: StatusGuardedWriteRecorder[Goal], bus: _Bus) -> None:
    """The stale-completed verdict: a real achievement the pre-read would have missed."""
    merged = _merged(recorder)
    assert merged["achieved_date"] == date.today()
    assert merged["status"] == EntityStatus.COMPLETED.value
    assert len(bus.of(GoalAchieved)) == 1


def _goal(
    *,
    status: EntityStatus,
    measurement_type: MeasurementType,
    achieved_date: date | None = None,
    progress: float = 0.0,
    milestones: tuple[bool, ...] = (),
    **overrides: Any,  # boundary: Goal's own heterogeneous field set
) -> Goal:
    return Goal(
        uid=_GOAL,
        user_uid=_USER,
        title="Ship the thing",
        status=status,
        measurement_type=measurement_type,
        progress_percentage=progress,
        achieved_date=achieved_date,
        milestones=tuple(
            Milestone(
                uid=f"m{i}",
                title=f"Milestone {i}",
                is_completed=done,
                achieved_date=_ORIGINAL_ACHIEVED if done else None,
            )
            for i, done in enumerate(milestones)
        ),
        **overrides,
    )


@pytest.mark.asyncio
class TestCompleteMilestone:
    """``complete_milestone`` — the one writer whose stale input WAS a status."""

    async def test_a_goal_completed_by_another_writer_is_not_re_stamped(self) -> None:
        """Stale-open. The read says ACTIVE and every milestone is done after this call,
        so the target derivation says "achieved" — correctly. What it cannot know is that
        the goal is already COMPLETED, which is the guard's half."""
        read = _goal(
            status=EntityStatus.ACTIVE,
            measurement_type=MeasurementType.MILESTONE,
            milestones=(True, False),
        )
        stored = _goal(
            status=EntityStatus.COMPLETED,
            measurement_type=MeasurementType.MILESTONE,
            achieved_date=_ORIGINAL_ACHIEVED,
            milestones=(True, True),
        )
        service, recorder, bus = _rig(read=read, stored=stored)

        result = await service.complete_milestone(_GOAL, 1, Mock(user_uid=_USER))

        assert result.is_ok
        _assert_suppressed(recorder, bus)
        assert _merged(recorder)["progress_percentage"] == 100.0

    async def test_a_goal_reopened_by_another_writer_is_achieved_again(self) -> None:
        """Stale-completed. The read says COMPLETED, so the old ``was_already_achieved``
        local suppressed the achievement outright — but the goal was reopened before this
        write landed, and completing its last milestone genuinely re-achieves it."""
        read = _goal(
            status=EntityStatus.COMPLETED,
            measurement_type=MeasurementType.MILESTONE,
            achieved_date=_ORIGINAL_ACHIEVED,
            milestones=(True, False),
        )
        stored = _goal(
            status=EntityStatus.ACTIVE,
            measurement_type=MeasurementType.MILESTONE,
            milestones=(True, False),
        )
        service, recorder, bus = _rig(read=read, stored=stored)

        result = await service.complete_milestone(_GOAL, 1, Mock(user_uid=_USER))

        assert result.is_ok
        _assert_achieved(recorder, bus)

    async def test_an_unfinished_goal_carries_no_completion_patch_at_all(self) -> None:
        """The target half is still Python, and breaking it is the easy regression: 1 of
        3 milestones is not an achievement whatever the prior status is, so the guard
        must carry no conditional patch to resolve."""
        read = _goal(
            status=EntityStatus.ACTIVE,
            measurement_type=MeasurementType.MILESTONE,
            milestones=(False, False, False),
        )
        stored = _goal(
            status=EntityStatus.ACTIVE,
            measurement_type=MeasurementType.MILESTONE,
            milestones=(False, False, False),
        )
        service, recorder, bus = _rig(read=read, stored=stored)

        result = await service.complete_milestone(_GOAL, 0, Mock(user_uid=_USER))

        assert result.is_ok
        assert recorder.last_guard.has_patches() is False
        assert "achieved_date" not in _merged(recorder)
        assert bus.of(GoalAchieved) == []


@pytest.mark.asyncio
class TestUpdateGoalFromHabitProgress:
    """``update_goal_from_habit_progress`` — target from the streak, prior from the write."""

    @staticmethod
    def _rels() -> _Relationships:
        return _Relationships({"supporting_habits": [_HABIT]})

    async def test_a_goal_completed_by_another_writer_is_not_re_stamped(self) -> None:
        """Stale-open: the read's 0% makes 0 → 100 a genuine crossing, but the goal is
        already COMPLETED on the node."""
        read = _goal(
            status=EntityStatus.ACTIVE,
            measurement_type=MeasurementType.HABIT_BASED,
            progress=0.0,
            target_value=30.0,
        )
        stored = _goal(
            status=EntityStatus.COMPLETED,
            measurement_type=MeasurementType.HABIT_BASED,
            progress=100.0,
            achieved_date=_ORIGINAL_ACHIEVED,
            target_value=30.0,
        )
        service, recorder, bus = _rig(read=read, stored=stored, relationships=self._rels())

        result = await service.update_goal_from_habit_progress(_GOAL, _HABIT, new_streak=30)

        assert result.is_ok
        _assert_suppressed(recorder, bus)

    async def test_a_goal_reopened_by_another_writer_is_achieved_again(self) -> None:
        """Stale-completed: the crossing is real and the node is open, so it stamps —
        even though the goal the writer read carried a completion date."""
        read = _goal(
            status=EntityStatus.COMPLETED,
            measurement_type=MeasurementType.HABIT_BASED,
            progress=0.0,
            achieved_date=_ORIGINAL_ACHIEVED,
            target_value=30.0,
        )
        stored = _goal(
            status=EntityStatus.ACTIVE,
            measurement_type=MeasurementType.HABIT_BASED,
            progress=0.0,
            target_value=30.0,
        )
        service, recorder, bus = _rig(read=read, stored=stored, relationships=self._rels())

        result = await service.update_goal_from_habit_progress(_GOAL, _HABIT, new_streak=30)

        assert result.is_ok
        _assert_achieved(recorder, bus)

    async def test_a_short_streak_carries_no_completion_patch_at_all(self) -> None:
        """15 of 30 days is 50%: not achieved, whatever the node's prior says."""
        read = _goal(
            status=EntityStatus.ACTIVE,
            measurement_type=MeasurementType.HABIT_BASED,
            progress=0.0,
            target_value=30.0,
        )
        service, recorder, bus = _rig(read=read, stored=read, relationships=self._rels())

        result = await service.update_goal_from_habit_progress(_GOAL, _HABIT, new_streak=15)

        assert result.is_ok
        assert recorder.last_guard.has_patches() is False
        assert bus.of(GoalAchieved) == []


def _locked_rig(
    locked: Goal, *, method: str, tally: dict[str, Any]
) -> tuple[GoalsProgressService, StatusGuardedWriteRecorder[Goal], _Bus]:
    """A progress service whose tally recompute runs under the goal's lock.

    No read/stored split here, unlike ``_rig``: the two tally writers now read the goal
    and its tally INSIDE the locked transaction their write runs in
    (``GoalsBackend.recompute_progress_from_linked_*``), so the goal they plan from IS
    the prior the guard resolves against. The race a split rig models is closed by
    construction; what these tests pin is the verdict each locked state produces.
    """
    backend, recorder = guarded_backend(locked, locked)
    wire_locked_recompute(backend, recorder, locked, method=method, tally=tally)
    bus = _Bus()
    service = GoalsProgressService.__new__(GoalsProgressService)
    service.backend = backend
    service.logger = Mock()
    service.event_bus = bus
    service.relationships = None
    return service, recorder, bus


def _assert_unachieved(recorder: StatusGuardedWriteRecorder[Goal], bus: _Bus) -> None:
    """A completed goal recomputed below 100% is no longer achieved."""
    merged = _merged(recorder)
    assert merged["status"] == EntityStatus.ACTIVE.value
    assert merged["achieved_date"] is None, "a stamp must not outlive the completion"
    assert bus.of(GoalAchieved) == []


@pytest.mark.asyncio
class TestUpdateGoalFromTaskCompletion:
    """``_update_goal_from_task_completion`` — the task-tally recompute."""

    _METHOD = "recompute_progress_from_linked_tasks"

    def _tally(self, total: int, completed: int) -> dict[str, Any]:
        return {"total_tasks": total, "completed_tasks": completed}

    async def test_an_already_achieved_goal_at_its_tally_writes_nothing(self) -> None:
        """What a racing second completion now finds under the lock: the first one's
        write — 2/2, 100%, COMPLETED — so there is nothing left to write or announce."""
        locked = _goal(
            status=EntityStatus.COMPLETED,
            measurement_type=MeasurementType.TASK_BASED,
            progress=100.0,
            achieved_date=_ORIGINAL_ACHIEVED,
            current_value=2.0,
            target_value=2.0,
        )
        service, recorder, bus = _locked_rig(locked, method=self._METHOD, tally=self._tally(2, 2))

        await service._update_goal_from_task_completion(_GOAL, _USER)

        assert recorder.calls == []
        assert bus.of(GoalAchieved) == []

    async def test_a_completed_goal_reaching_100_again_is_not_re_stamped(self) -> None:
        """Completed by hand at 50%, then its tally reaches 2/2: the figure rises to 100,
        but the guard's prior is COMPLETED, so ``achieved_date`` keeps its day."""
        locked = _goal(
            status=EntityStatus.COMPLETED,
            measurement_type=MeasurementType.TASK_BASED,
            progress=50.0,
            achieved_date=_ORIGINAL_ACHIEVED,
            current_value=1.0,
            target_value=2.0,
        )
        service, recorder, bus = _locked_rig(locked, method=self._METHOD, tally=self._tally(2, 2))

        await service._update_goal_from_task_completion(_GOAL, _USER)

        _assert_suppressed(recorder, bus)

    async def test_an_open_goal_reaching_100_is_achieved(self) -> None:
        locked = _goal(
            status=EntityStatus.ACTIVE,
            measurement_type=MeasurementType.TASK_BASED,
            progress=50.0,
            current_value=1.0,
            target_value=2.0,
        )
        service, recorder, bus = _locked_rig(locked, method=self._METHOD, tally=self._tally(2, 2))

        await service._update_goal_from_task_completion(_GOAL, _USER)

        _assert_achieved(recorder, bus)

    async def test_a_partial_tally_carries_no_completion_patch_at_all(self) -> None:
        locked = _goal(
            status=EntityStatus.ACTIVE,
            measurement_type=MeasurementType.TASK_BASED,
            progress=0.0,
            current_value=0.0,
            target_value=4.0,
        )
        service, recorder, bus = _locked_rig(locked, method=self._METHOD, tally=self._tally(4, 1))

        await service._update_goal_from_task_completion(_GOAL, _USER)

        assert recorder.last_guard.has_patches() is False
        assert bus.of(GoalAchieved) == []

    async def test_a_completed_goal_whose_tally_drops_is_unachieved(self) -> None:
        """Its only task reopened: 1/1 → 0/1. Status back to ACTIVE, stamp removed."""
        locked = _goal(
            status=EntityStatus.COMPLETED,
            measurement_type=MeasurementType.TASK_BASED,
            progress=100.0,
            achieved_date=_ORIGINAL_ACHIEVED,
            current_value=1.0,
            target_value=1.0,
        )
        service, recorder, bus = _locked_rig(locked, method=self._METHOD, tally=self._tally(1, 0))

        await service._update_goal_from_task_completion(_GOAL, _USER)

        _assert_unachieved(recorder, bus)
        assert _merged(recorder)["progress_percentage"] == 0.0

    async def test_an_open_goal_whose_tally_drops_keeps_its_status(self) -> None:
        """A goal reopened by hand at 100% has no achievement to take back: the
        un-achieve patch is conditioned on a COMPLETED prior, and this one is ACTIVE."""
        locked = _goal(
            status=EntityStatus.ACTIVE,
            measurement_type=MeasurementType.TASK_BASED,
            progress=100.0,
            current_value=2.0,
            target_value=2.0,
        )
        service, recorder, _bus = _locked_rig(locked, method=self._METHOD, tally=self._tally(2, 1))

        await service._update_goal_from_task_completion(_GOAL, _USER)

        merged = _merged(recorder)
        assert "status" not in merged
        assert "achieved_date" not in merged
        assert merged["progress_percentage"] == pytest.approx(50.0)

    async def test_a_completed_goal_moving_below_100_is_not_a_drop(self) -> None:
        """Completed by hand at 40% (2/5); a third task completes → 60%. The figure
        never crossed 100 downward, so the completion the user recorded stands."""
        locked = _goal(
            status=EntityStatus.COMPLETED,
            measurement_type=MeasurementType.TASK_BASED,
            progress=40.0,
            achieved_date=_ORIGINAL_ACHIEVED,
            current_value=2.0,
            target_value=5.0,
        )
        service, recorder, _bus = _locked_rig(locked, method=self._METHOD, tally=self._tally(5, 3))

        await service._update_goal_from_task_completion(_GOAL, _USER)

        merged = _merged(recorder)
        assert "status" not in merged
        assert "achieved_date" not in merged


@pytest.mark.asyncio
class TestUpdateGoalFromHabitCompletion:
    """``_update_goal_from_habit_completion`` — the average-streak recompute."""

    _METHOD = "recompute_progress_from_linked_habits"

    def _tally(self, total: int, avg_streak: float) -> dict[str, Any]:
        return {"total_habits": total, "avg_streak": avg_streak}

    async def test_a_completed_goal_reaching_100_again_is_not_re_stamped(self) -> None:
        locked = _goal(
            status=EntityStatus.COMPLETED,
            measurement_type=MeasurementType.HABIT_BASED,
            progress=50.0,
            achieved_date=_ORIGINAL_ACHIEVED,
            current_value=15.0,
            target_value=30.0,
        )
        service, recorder, bus = _locked_rig(
            locked, method=self._METHOD, tally=self._tally(1, 30.0)
        )

        await service._update_goal_from_habit_completion(_GOAL, _USER, 30)

        _assert_suppressed(recorder, bus)

    async def test_an_open_goal_reaching_100_is_achieved(self) -> None:
        locked = _goal(
            status=EntityStatus.ACTIVE,
            measurement_type=MeasurementType.HABIT_BASED,
            progress=50.0,
            current_value=15.0,
            target_value=30.0,
        )
        service, recorder, bus = _locked_rig(
            locked, method=self._METHOD, tally=self._tally(1, 30.0)
        )

        await service._update_goal_from_habit_completion(_GOAL, _USER, 30)

        _assert_achieved(recorder, bus)

    async def test_a_short_streak_carries_no_completion_patch_at_all(self) -> None:
        locked = _goal(
            status=EntityStatus.ACTIVE,
            measurement_type=MeasurementType.HABIT_BASED,
            progress=0.0,
            current_value=0.0,
            target_value=30.0,
        )
        service, recorder, bus = _locked_rig(
            locked, method=self._METHOD, tally=self._tally(1, 15.0)
        )

        await service._update_goal_from_habit_completion(_GOAL, _USER, 15)

        assert recorder.last_guard.has_patches() is False
        assert bus.of(GoalAchieved) == []

    async def test_a_completed_goal_whose_streak_falls_is_unachieved(self) -> None:
        """A 30-day streak broke and restarted: the average falls to 1 of 30 days."""
        locked = _goal(
            status=EntityStatus.COMPLETED,
            measurement_type=MeasurementType.HABIT_BASED,
            progress=100.0,
            achieved_date=_ORIGINAL_ACHIEVED,
            current_value=30.0,
            target_value=30.0,
        )
        service, recorder, bus = _locked_rig(locked, method=self._METHOD, tally=self._tally(1, 1.0))

        await service._update_goal_from_habit_completion(_GOAL, _USER, 1)

        _assert_unachieved(recorder, bus)
