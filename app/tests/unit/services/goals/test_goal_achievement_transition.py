"""``GoalAchieved`` fires on the transition, never on the state.

Two writers in ``GoalsProgressService`` used to key achievement off the *state*
(``completed_count == len(milestones)`` / ``new_progress >= 100``) rather than
the *transition* into it. Both are reachable again after a goal is achieved — a
milestone can be re-completed, and a streak past its 30-day normalization window
keeps reporting 100% — so each later call set ``status=COMPLETED``, re-stamped
``achieved_date`` to today, and re-published ``GoalAchieved``.

Two defects in one: a **mutable completion stamp** (the class the
completion-stamping arc removed everywhere else) and a **duplicate append**,
since ``GoalEventHandlerService`` persists a PRINCIPLE_ALIGNMENT
``PersistedInsight`` per ``GoalAchieved`` under a UID carrying a per-second
timestamp.

**Since ADR-087 PR-4 the transition half is a condition of the WRITE.** The gates were
right about what to check and wrong about where to read it: "was it already achieved"
came from a status the writer read before it wrote, which a concurrent writer can move
in between. Now the progress recompute derives the achievement TARGET in Python and the
"…and not already" half rides ``patch_if_prior_not_in``, evaluated against the status the
node holds under its lock. So these tests come in two layers: the target derivation
(unchanged, and still this file's subject) and the prior the write hands back — which
``TestTheVerdictComesFromTheWrite`` drives to a value the pre-read does NOT agree with,
because a fake that answers from the read can only ever confirm the coupling the
primitive removed.
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

_USER = "user_achievement"
_GOAL = "goal_achievement"
_HABIT = "habit_meditation"

#: An achievement recorded before today — the value a re-stamp would destroy.
_ORIGINAL_ACHIEVED = date(2026, 1, 15)


class _RecordingBus:
    """Captures what the service publishes — ``publish_event`` calls ``publish_async``."""

    def __init__(self) -> None:
        self.events: list[BaseEvent] = []

    async def publish_async(self, event: BaseEvent) -> None:
        self.events.append(event)

    def of[E: BaseEvent](self, event_type: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, event_type)]


class _Relationships:
    """Only ``get_related_uids`` — the shape ``fetch_relationships_parallel`` falls back to.

    A bare ``Mock`` would auto-create a ``supporting_habits`` attribute and the
    fetcher would call *that* instead, handing ``asyncio.gather`` a non-awaitable.
    """

    def __init__(self, mapping: dict[str, list[str]]) -> None:
        self._mapping = mapping

    async def get_related_uids(self, key: str, uid: str) -> Result[list[str]]:
        return Result.ok(list(self._mapping.get(key, [])))


def _service(
    goal: Goal,
    *,
    relationships: _Relationships | None = None,
    prior: Goal | None = None,
) -> tuple[GoalsProgressService, StatusGuardedWriteRecorder[Goal], _RecordingBus]:
    """A progress service over one goal, writing through the status-guarded primitive.

    Two goals, deliberately separable (ADR-087): ``goal`` is what the pre-read returns
    and what the recompute is derived from; ``prior`` is the state the WRITE sees under
    the node's lock. They are the same object unless a test is about a writer that
    raced, which is the only way to drive a verdict the pre-read does not already agree
    with.

    ``get_goal`` mirrors ``GoalsBackend.get_goal`` (``Result[Goal]``, a domain model);
    the guarded write is the shared recorder, which evaluates the guard exactly as the
    Cypher's CASE arms do.
    """
    backend, recorder = guarded_backend(prior if prior is not None else goal, goal)
    backend.get_goal = AsyncMock(return_value=Result.ok(goal))

    bus = _RecordingBus()
    service = GoalsProgressService.__new__(GoalsProgressService)
    service.backend = backend
    service.logger = Mock()
    service.event_bus = bus
    service.relationships = relationships  # type: ignore[assignment]
    return service, recorder, bus


def _patch(recorder: StatusGuardedWriteRecorder[Goal]) -> dict[str, Any]:
    """What the write would actually have merged — base patch plus whichever conditional
    patch the prior selected.

    The resolved view is the right one for this file: the completion pair rides
    ``patch_if_prior_not_in`` now, so "did this write stamp?" is a question about the
    guard AND the prior together, which is exactly what the Cypher answers.

    ``Any`` (# boundary:) because the patch is genuinely heterogeneous — float, date,
    ``list[Milestone]`` — but every assertion below is an equality or membership check.
    """
    assert len(recorder.calls) == 1, "expected exactly one write"
    return recorder.merged_patch()


def _achieved(bus: _RecordingBus) -> list[GoalAchieved]:
    return bus.of(GoalAchieved)


def _milestone_goal(
    *,
    completed: tuple[bool, ...],
    achieved_date: date | None,
    status: EntityStatus = EntityStatus.ACTIVE,
) -> Goal:
    return Goal(
        uid=_GOAL,
        user_uid=_USER,
        title="Ship the thing",
        status=status,
        measurement_type=MeasurementType.MILESTONE,
        milestones=tuple(
            Milestone(
                uid=f"m{i}",
                title=f"Milestone {i}",
                is_completed=done,
                achieved_date=_ORIGINAL_ACHIEVED if done else None,
            )
            for i, done in enumerate(completed)
        ),
        achieved_date=achieved_date,
    )


class TestCompleteMilestone:
    async def test_the_last_milestone_stamps_and_publishes(self):
        """The genuine transition: one milestone left, and completing it achieves the goal."""
        goal = _milestone_goal(completed=(True, False), achieved_date=None)
        service, recorder, bus = _service(goal)

        result = await service.complete_milestone(_GOAL, 1, Mock(user_uid=_USER))

        assert result.is_ok
        updates = _patch(recorder)
        assert updates["achieved_date"] == date.today()
        assert updates["status"] is not None
        assert len(_achieved(bus)) == 1

    async def test_a_reopened_goal_can_be_achieved_again(self):
        """The case that rules out a milestone-flag proxy for "already achieved".

        Reopening clears ``achieved_date`` and resets ``progress_percentage``
        (``GoalsCoreService.update_goal``) but leaves the milestone flags set —
        so "every milestone done" stays true forever after the first
        achievement. Gating on it would make a reopened goal unachievable.
        """
        goal = _milestone_goal(
            completed=(True, True), achieved_date=None, status=EntityStatus.ACTIVE
        )
        service, recorder, bus = _service(goal)

        result = await service.complete_milestone(_GOAL, 1, Mock(user_uid=_USER))

        assert result.is_ok
        assert _patch(recorder)["achieved_date"] == date.today()
        assert len(_achieved(bus)) == 1

    async def test_an_already_achieved_goal_is_not_re_stamped(self):
        """Re-completing a milestone of a finished goal must not move its achievement date."""
        goal = _milestone_goal(
            completed=(True, True),
            achieved_date=_ORIGINAL_ACHIEVED,
            status=EntityStatus.COMPLETED,
        )
        service, recorder, bus = _service(goal)

        result = await service.complete_milestone(_GOAL, 1, Mock(user_uid=_USER))

        assert result.is_ok
        updates = _patch(recorder)
        assert "achieved_date" not in updates, "the recorded achievement must survive"
        assert "status" not in updates
        assert _achieved(bus) == [], "a re-publish would duplicate the alignment insight"
        # The progress recompute still runs — this is not a skipped write.
        assert updates["progress_percentage"] == 100.0

    async def test_a_partial_goal_neither_stamps_nor_publishes(self):
        """Baseline: completing 1 of 3 is not an achievement."""
        goal = _milestone_goal(completed=(False, False, False), achieved_date=None)
        service, recorder, bus = _service(goal)

        result = await service.complete_milestone(_GOAL, 0, Mock(user_uid=_USER))

        assert result.is_ok
        updates = _patch(recorder)
        assert "achieved_date" not in updates
        assert _achieved(bus) == []


class TestMilestoneOwnStamp:
    """The milestone's own ``achieved_date``, one level below the goal's.

    ``Milestone.achieved_date`` is documented as "when actually achieved", so it is
    the same kind of stamp as the goal-level one and follows the same rule: it
    records the FIRST completion and never moves. The goal-level gate above does
    not cover it — re-completing a milestone of a still-unachieved goal writes no
    goal stamp at all, yet used to move that milestone's own date to today.
    """

    @staticmethod
    def _milestones(recorder: StatusGuardedWriteRecorder[Goal]) -> list[Milestone]:
        milestones = _patch(recorder)["milestones"]
        assert isinstance(milestones, list)
        return milestones

    async def test_recompleting_a_milestone_keeps_its_original_date(self):
        """The defect: milestone 0 is already done, and completing it again moved its date."""
        goal = _milestone_goal(completed=(True, False, False), achieved_date=None)
        service, recorder, bus = _service(goal)

        result = await service.complete_milestone(_GOAL, 0, Mock(user_uid=_USER))

        assert result.is_ok
        milestone = self._milestones(recorder)[0]
        assert milestone.is_completed is True, "is_completed is idempotent, not gated"
        assert milestone.achieved_date == _ORIGINAL_ACHIEVED
        # Nothing fires at the goal level here — which is why the goal-level gate
        # cannot stand in for this one.
        assert _achieved(bus) == []

    async def test_a_first_completion_still_stamps_today(self):
        goal = _milestone_goal(completed=(True, False, False), achieved_date=None)
        service, recorder, _ = _service(goal)

        result = await service.complete_milestone(_GOAL, 1, Mock(user_uid=_USER))

        assert result.is_ok
        milestone = self._milestones(recorder)[1]
        assert milestone.is_completed is True
        assert milestone.achieved_date == date.today()

    async def test_a_completed_milestone_with_no_date_is_not_backfilled(self):
        """A repeat is not a transition, so there is no moment here to record.

        Matches the task stamp gate (#1125), which likewise leaves a null stamp
        null on a repeat rather than inventing a date.
        """
        goal = Goal(
            uid=_GOAL,
            user_uid=_USER,
            title="Ship the thing",
            measurement_type=MeasurementType.MILESTONE,
            milestones=(
                Milestone(uid="m0", title="Milestone 0", is_completed=True, achieved_date=None),
                Milestone(uid="m1", title="Milestone 1"),
            ),
        )
        service, recorder, _ = _service(goal)

        result = await service.complete_milestone(_GOAL, 0, Mock(user_uid=_USER))

        assert result.is_ok
        assert self._milestones(recorder)[0].achieved_date is None


def _habit_goal(*, progress: float, achieved_date: date | None) -> Goal:
    return Goal(
        uid=_GOAL,
        user_uid=_USER,
        title="Meditate daily",
        measurement_type=MeasurementType.HABIT_BASED,
        target_value=30.0,
        progress_percentage=progress,
        achieved_date=achieved_date,
    )


class TestUpdateGoalFromHabitProgress:
    async def test_reaching_the_streak_target_stamps_and_publishes(self):
        """0% → 100% is the transition: a 30-day streak fills the normalization window."""
        goal = _habit_goal(progress=0.0, achieved_date=None)
        service, recorder, bus = _service(
            goal, relationships=_Relationships({"supporting_habits": [_HABIT]})
        )

        result = await service.update_goal_from_habit_progress(_GOAL, _HABIT, new_streak=30)

        assert result.is_ok
        updates = _patch(recorder)
        assert updates["progress_percentage"] == 100.0
        assert updates["achieved_date"] == date.today()
        assert len(_achieved(bus)) == 1

    async def test_a_longer_streak_on_an_achieved_goal_is_not_re_stamped(self):
        """Day 31 of a 30-day target is still 100% — the old gate re-stamped on every report."""
        goal = _habit_goal(progress=100.0, achieved_date=_ORIGINAL_ACHIEVED)
        service, recorder, bus = _service(
            goal, relationships=_Relationships({"supporting_habits": [_HABIT]})
        )

        result = await service.update_goal_from_habit_progress(_GOAL, _HABIT, new_streak=45)

        assert result.is_ok
        updates = _patch(recorder)
        assert updates["progress_percentage"] == 100.0, "the recompute still runs"
        assert "achieved_date" not in updates, "the recorded achievement must survive"
        assert "status" not in updates
        assert _achieved(bus) == [], "a re-publish would duplicate the alignment insight"

    async def test_a_short_streak_neither_stamps_nor_publishes(self):
        """Baseline: 15 of 30 days is 50%."""
        goal = _habit_goal(progress=0.0, achieved_date=None)
        service, recorder, bus = _service(
            goal, relationships=_Relationships({"supporting_habits": [_HABIT]})
        )

        result = await service.update_goal_from_habit_progress(_GOAL, _HABIT, new_streak=15)

        assert result.is_ok
        updates = _patch(recorder)
        assert updates["progress_percentage"] == pytest.approx(50.0)
        assert "achieved_date" not in updates
        assert _achieved(bus) == []
