"""``GoalAchieved`` fires on the transition, never on the state.

A progress writer that keys achievement off the *state* (every milestone done,
``new_progress >= 100``) rather than the *transition* into it re-achieves on every
later call: a milestone can be re-completed, and a streak past its 30-day
normalization window keeps reporting 100%. Each such call would set
``status=COMPLETED``, re-stamp ``achieved_date`` to today, and re-publish
``GoalAchieved`` — a **mutable completion stamp** and a **duplicate append**, since
``GoalEventHandlerService`` persists a PRINCIPLE_ALIGNMENT ``PersistedInsight`` per
``GoalAchieved`` under a UID carrying a per-second timestamp.

The transition half is a condition of the WRITE (ADR-087): the recompute derives the
achievement TARGET in Python and the "…and not already" half rides
``patch_if_prior_not_in``, evaluated against the status the node holds under its lock.
These tests pin the target derivation and the verdict read from the prior the write
hands back.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import Mock

import pytest

from core.events.base import BaseEvent
from core.events.goal_events import GoalAchieved
from core.models.enums import EntityStatus
from core.models.enums.goal_enums import MeasurementType
from core.models.goal.goal import Goal
from core.models.goal.milestone import Milestone
from core.services.goals.goals_progress_service import GoalsProgressService
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone
from tests.helpers.status_guarded_backend import (
    StatusGuardedWriteRecorder,
    guarded_backend,
    wire_locked_recompute,
)

_USER = "user_achievement"
_GOAL = "goal_achievement"

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


def _service(
    goal: Goal,
    *,
    habit_tally: dict[str, Any] | None = None,  # boundary: LinkedHabitTally's row shape
) -> tuple[GoalsProgressService, StatusGuardedWriteRecorder[Goal], _RecordingBus]:
    """A progress service over one goal, as held under its lock, writing through the
    status-guarded primitive.

    The guarded write is the shared recorder, which evaluates the guard exactly as the
    Cypher's CASE arms do. ``habit_tally`` is what the habit recompute reads under the
    lock (``recompute_progress_from_linked_habits``).
    """
    backend, recorder = guarded_backend(goal, goal)
    if habit_tally is not None:
        wire_locked_recompute(
            backend,
            recorder,
            goal,
            method="recompute_progress_from_linked_habits",
            tally=habit_tally,
        )

    bus = _RecordingBus()
    service = GoalsProgressService.__new__(GoalsProgressService)
    service.backend = backend
    service.logger = Mock()
    service.event_bus = bus
    service.relationships = None  # type: ignore[assignment]
    return service, recorder, bus


def _patch(
    recorder: StatusGuardedWriteRecorder[Goal],
) -> dict[str, Any]:  # boundary: pre-serialization patch
    """What the write would actually have merged — base patch plus whichever conditional
    patch the prior selected.

    The resolved view is the right one for this file: the completion pair rides
    ``patch_if_prior_not_in`` now, so "did this write stamp?" is a question about the
    guard AND the prior together, which is exactly what the Cypher answers.

    The patch is genuinely heterogeneous — float, date, ``list[Milestone]`` — but every
    assertion below is an equality or membership check.
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

        result = await service.complete_milestone(_GOAL, "m1")

        assert result.is_ok
        updates = _patch(recorder)
        assert updates["achieved_date"] == today_in(current_zone())
        assert updates["status"] is not None
        assert len(_achieved(bus)) == 1

    async def test_a_reopened_goal_can_be_achieved_again(self):
        """The case that rules out a milestone-flag proxy for "already achieved".

        Reopening clears ``achieved_date`` (``GoalsCoreService.update_goal``) but
        leaves the milestone flags set — so "every milestone done" can hold on an
        open goal. Gating on it would make such a goal unachievable.
        """
        goal = _milestone_goal(
            completed=(True, True), achieved_date=None, status=EntityStatus.ACTIVE
        )
        service, recorder, bus = _service(goal)

        result = await service.complete_milestone(_GOAL, "m1")

        assert result.is_ok
        assert _patch(recorder)["achieved_date"] == today_in(current_zone())
        assert len(_achieved(bus)) == 1

    async def test_an_already_achieved_goal_is_not_re_stamped(self):
        """Re-completing a milestone of a finished goal must not move its achievement date."""
        goal = _milestone_goal(
            completed=(True, True),
            achieved_date=_ORIGINAL_ACHIEVED,
            status=EntityStatus.COMPLETED,
        )
        service, recorder, bus = _service(goal)

        result = await service.complete_milestone(_GOAL, "m1")

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

        result = await service.complete_milestone(_GOAL, "m0")

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

        result = await service.complete_milestone(_GOAL, "m0")

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

        result = await service.complete_milestone(_GOAL, "m1")

        assert result.is_ok
        milestone = self._milestones(recorder)[1]
        assert milestone.is_completed is True
        assert milestone.achieved_date == today_in(current_zone())

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

        result = await service.complete_milestone(_GOAL, "m0")

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


class TestRecomputeHabitFigure:
    """The habit recompute (``recompute_habit_figure``) against a 30-day streak target."""

    @staticmethod
    def _tally(avg_streak: float) -> dict[str, Any]:  # boundary: LinkedHabitTally row
        return {"total_habits": 1, "avg_streak": avg_streak}

    async def test_reaching_the_streak_target_stamps_and_publishes(self):
        """0% → 100% is the transition: the average streak reaches the target."""
        goal = _habit_goal(progress=0.0, achieved_date=None)
        service, recorder, bus = _service(goal, habit_tally=self._tally(30.0))

        result = await service.recompute_habit_figure(_GOAL)

        assert result.is_ok
        updates = _patch(recorder)
        assert updates["progress_percentage"] == 100.0
        assert updates["achieved_date"] == today_in(current_zone())
        assert len(_achieved(bus)) == 1

    async def test_a_longer_streak_on_an_achieved_goal_is_not_re_stamped(self):
        """45 days on a 30-day target is still 100%: the recorded achievement stays."""
        goal = _habit_goal(progress=100.0, achieved_date=_ORIGINAL_ACHIEVED)
        service, recorder, bus = _service(goal, habit_tally=self._tally(45.0))

        result = await service.recompute_habit_figure(_GOAL)

        assert result.is_ok
        updates = _patch(recorder)
        assert updates["current_value"] == 45.0, "the measurement still moves"
        assert "achieved_date" not in updates, "the recorded achievement must survive"
        assert "status" not in updates
        assert _achieved(bus) == [], "a re-publish would duplicate the alignment insight"

    async def test_a_short_streak_neither_stamps_nor_publishes(self):
        """Baseline: 15 of 30 days is 50%."""
        goal = _habit_goal(progress=0.0, achieved_date=None)
        service, recorder, bus = _service(goal, habit_tally=self._tally(15.0))

        result = await service.recompute_habit_figure(_GOAL)

        assert result.is_ok
        updates = _patch(recorder)
        assert updates["progress_percentage"] == pytest.approx(50.0)
        assert "achieved_date" not in updates
        assert _achieved(bus) == []
