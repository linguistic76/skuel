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
removed — it would pass just as well against the old code. So each test seeds a stored
goal the write sees and a *different* goal the read returns, which is exactly what a race
produces.

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


@pytest.mark.asyncio
class TestUpdateGoalFromTaskCompletion:
    """``_update_goal_from_task_completion`` — the ``TaskCompleted`` propagation."""

    @staticmethod
    # boundary: ``count_linked_tasks``'s own row shape — a mixed int/float count map the
    # backend returns untyped; this mirrors it rather than narrowing past the real contract.
    def _tally(total: int, completed: int) -> Result[dict[str, Any]]:
        return Result.ok({"total_tasks": total, "completed_tasks": completed})

    async def test_a_goal_completed_by_another_writer_is_not_re_stamped(self) -> None:
        read = _goal(
            status=EntityStatus.ACTIVE,
            measurement_type=MeasurementType.TASK_BASED,
            progress=50.0,
            current_value=1.0,
            target_value=2.0,
        )
        stored = _goal(
            status=EntityStatus.COMPLETED,
            measurement_type=MeasurementType.TASK_BASED,
            progress=100.0,
            achieved_date=_ORIGINAL_ACHIEVED,
            current_value=2.0,
            target_value=2.0,
        )
        service, recorder, bus = _rig(
            read=read, stored=stored, count_linked_tasks=self._tally(2, 2)
        )

        await service._update_goal_from_task_completion(_GOAL, _USER)

        _assert_suppressed(recorder, bus)

    async def test_a_goal_reopened_by_another_writer_is_achieved_again(self) -> None:
        read = _goal(
            status=EntityStatus.COMPLETED,
            measurement_type=MeasurementType.TASK_BASED,
            progress=50.0,
            achieved_date=_ORIGINAL_ACHIEVED,
            current_value=1.0,
            target_value=2.0,
        )
        stored = _goal(
            status=EntityStatus.ACTIVE,
            measurement_type=MeasurementType.TASK_BASED,
            progress=50.0,
            current_value=1.0,
            target_value=2.0,
        )
        service, recorder, bus = _rig(
            read=read, stored=stored, count_linked_tasks=self._tally(2, 2)
        )

        await service._update_goal_from_task_completion(_GOAL, _USER)

        _assert_achieved(recorder, bus)

    async def test_a_partial_tally_carries_no_completion_patch_at_all(self) -> None:
        read = _goal(
            status=EntityStatus.ACTIVE,
            measurement_type=MeasurementType.TASK_BASED,
            progress=0.0,
            current_value=0.0,
            target_value=4.0,
        )
        service, recorder, bus = _rig(read=read, stored=read, count_linked_tasks=self._tally(4, 1))

        await service._update_goal_from_task_completion(_GOAL, _USER)

        assert recorder.last_guard.has_patches() is False
        assert bus.of(GoalAchieved) == []


@pytest.mark.asyncio
class TestUpdateGoalFromHabitCompletion:
    """``_update_goal_from_habit_completion`` — the ``HabitCompleted`` propagation."""

    @staticmethod
    # boundary: ``count_linked_habits_avg_streak``'s own row shape — see the sibling above.
    def _tally(total: int, avg_streak: float) -> Result[dict[str, Any]]:
        return Result.ok({"total_habits": total, "avg_streak": avg_streak})

    async def test_a_goal_completed_by_another_writer_is_not_re_stamped(self) -> None:
        read = _goal(
            status=EntityStatus.ACTIVE,
            measurement_type=MeasurementType.HABIT_BASED,
            progress=50.0,
            current_value=15.0,
            target_value=30.0,
        )
        stored = _goal(
            status=EntityStatus.COMPLETED,
            measurement_type=MeasurementType.HABIT_BASED,
            progress=100.0,
            achieved_date=_ORIGINAL_ACHIEVED,
            current_value=30.0,
            target_value=30.0,
        )
        service, recorder, bus = _rig(
            read=read, stored=stored, count_linked_habits_avg_streak=self._tally(1, 30.0)
        )

        await service._update_goal_from_habit_completion(_GOAL, _USER, 30)

        _assert_suppressed(recorder, bus)

    async def test_a_goal_reopened_by_another_writer_is_achieved_again(self) -> None:
        read = _goal(
            status=EntityStatus.COMPLETED,
            measurement_type=MeasurementType.HABIT_BASED,
            progress=50.0,
            achieved_date=_ORIGINAL_ACHIEVED,
            current_value=15.0,
            target_value=30.0,
        )
        stored = _goal(
            status=EntityStatus.ACTIVE,
            measurement_type=MeasurementType.HABIT_BASED,
            progress=50.0,
            current_value=15.0,
            target_value=30.0,
        )
        service, recorder, bus = _rig(
            read=read, stored=stored, count_linked_habits_avg_streak=self._tally(1, 30.0)
        )

        await service._update_goal_from_habit_completion(_GOAL, _USER, 30)

        _assert_achieved(recorder, bus)

    async def test_a_short_streak_carries_no_completion_patch_at_all(self) -> None:
        read = _goal(
            status=EntityStatus.ACTIVE,
            measurement_type=MeasurementType.HABIT_BASED,
            progress=0.0,
            current_value=0.0,
            target_value=30.0,
        )
        service, recorder, bus = _rig(
            read=read, stored=read, count_linked_habits_avg_streak=self._tally(1, 15.0)
        )

        await service._update_goal_from_habit_completion(_GOAL, _USER, 15)

        assert recorder.last_guard.has_patches() is False
        assert bus.of(GoalAchieved) == []
