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

The two already-correct writers in the same file
(``_update_goal_from_task_completion``, ``_update_goal_from_habit_completion``)
carry the pattern these now copy; their gates are pinned elsewhere.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, Mock

import pytest

from core.events.goal_events import GoalAchieved
from core.models.enums import EntityStatus
from core.models.enums.goal_enums import MeasurementType
from core.models.goal.goal import Goal
from core.models.goal.milestone import Milestone
from core.services.goals.goals_progress_service import GoalsProgressService
from core.utils.result_simplified import Result

_USER = "user_achievement"
_GOAL = "goal_achievement"
_HABIT = "habit_meditation"

#: An achievement recorded before today — the value a re-stamp would destroy.
_ORIGINAL_ACHIEVED = date(2026, 1, 15)


class _RecordingBus:
    """Captures what the service publishes — ``publish_event`` calls ``publish_async``."""

    def __init__(self) -> None:
        self.events: list[object] = []

    async def publish_async(self, event: object) -> None:
        self.events.append(event)


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
    goal: Goal, *, relationships: _Relationships | None = None
) -> tuple[GoalsProgressService, Mock, _RecordingBus]:
    """A progress service over one goal.

    ``get_goal``/``update_goal`` mirror the real backend: ``GoalsBackend`` has no
    explicit ``update_goal``, so ``UniversalNeo4jBackend.__getattr__`` aliases it
    to ``update``, which returns ``Result[Goal]`` — a domain model, not a dict.
    """
    backend = Mock()
    backend.get_goal = AsyncMock(return_value=Result.ok(goal))
    backend.update_goal = AsyncMock(return_value=Result.ok(goal))

    bus = _RecordingBus()
    service = GoalsProgressService.__new__(GoalsProgressService)
    service.backend = backend
    service.logger = Mock()
    service.event_bus = bus
    service.relationships = relationships  # type: ignore[assignment]
    return service, backend, bus


def _patch(backend: Mock) -> dict[str, object]:
    """The single update patch handed to the backend.

    ``object`` rather than ``Any``: the patch is genuinely heterogeneous
    (float, date, EntityStatus, list[Milestone]) but every assertion below is
    an equality or membership check, so nothing needs the escape hatch.
    """
    assert backend.update_goal.await_count == 1, "expected exactly one write"
    return dict(backend.update_goal.await_args.args[1])


def _achieved(bus: _RecordingBus) -> list[object]:
    return [e for e in bus.events if isinstance(e, GoalAchieved)]


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
        service, backend, bus = _service(goal)

        result = await service.complete_milestone(_GOAL, 1, Mock(user_uid=_USER))

        assert result.is_ok
        updates = _patch(backend)
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
        service, backend, bus = _service(goal)

        result = await service.complete_milestone(_GOAL, 1, Mock(user_uid=_USER))

        assert result.is_ok
        assert _patch(backend)["achieved_date"] == date.today()
        assert len(_achieved(bus)) == 1

    async def test_an_already_achieved_goal_is_not_re_stamped(self):
        """Re-completing a milestone of a finished goal must not move its achievement date."""
        goal = _milestone_goal(
            completed=(True, True),
            achieved_date=_ORIGINAL_ACHIEVED,
            status=EntityStatus.COMPLETED,
        )
        service, backend, bus = _service(goal)

        result = await service.complete_milestone(_GOAL, 1, Mock(user_uid=_USER))

        assert result.is_ok
        updates = _patch(backend)
        assert "achieved_date" not in updates, "the recorded achievement must survive"
        assert "status" not in updates
        assert _achieved(bus) == [], "a re-publish would duplicate the alignment insight"
        # The progress recompute still runs — this is not a skipped write.
        assert updates["progress_percentage"] == 100.0

    async def test_a_partial_goal_neither_stamps_nor_publishes(self):
        """Baseline: completing 1 of 3 is not an achievement."""
        goal = _milestone_goal(completed=(False, False, False), achieved_date=None)
        service, backend, bus = _service(goal)

        result = await service.complete_milestone(_GOAL, 0, Mock(user_uid=_USER))

        assert result.is_ok
        updates = _patch(backend)
        assert "achieved_date" not in updates
        assert _achieved(bus) == []


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
        service, backend, bus = _service(
            goal, relationships=_Relationships({"supporting_habits": [_HABIT]})
        )

        result = await service.update_goal_from_habit_progress(_GOAL, _HABIT, new_streak=30)

        assert result.is_ok
        updates = _patch(backend)
        assert updates["progress_percentage"] == 100.0
        assert updates["achieved_date"] == date.today()
        assert len(_achieved(bus)) == 1

    async def test_a_longer_streak_on_an_achieved_goal_is_not_re_stamped(self):
        """Day 31 of a 30-day target is still 100% — the old gate re-stamped on every report."""
        goal = _habit_goal(progress=100.0, achieved_date=_ORIGINAL_ACHIEVED)
        service, backend, bus = _service(
            goal, relationships=_Relationships({"supporting_habits": [_HABIT]})
        )

        result = await service.update_goal_from_habit_progress(_GOAL, _HABIT, new_streak=45)

        assert result.is_ok
        updates = _patch(backend)
        assert updates["progress_percentage"] == 100.0, "the recompute still runs"
        assert "achieved_date" not in updates, "the recorded achievement must survive"
        assert "status" not in updates
        assert _achieved(bus) == [], "a re-publish would duplicate the alignment insight"

    async def test_a_short_streak_neither_stamps_nor_publishes(self):
        """Baseline: 15 of 30 days is 50%."""
        goal = _habit_goal(progress=0.0, achieved_date=None)
        service, backend, bus = _service(
            goal, relationships=_Relationships({"supporting_habits": [_HABIT]})
        )

        result = await service.update_goal_from_habit_progress(_GOAL, _HABIT, new_streak=15)

        assert result.is_ok
        updates = _patch(backend)
        assert updates["progress_percentage"] == pytest.approx(50.0)
        assert "achieved_date" not in updates
        assert _achieved(bus) == []
