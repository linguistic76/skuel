"""Every goal-progress write stamps ``last_progress_update``.

The report's ``goals_progressed`` counter reads that stamp (a goal counts when the
stamp falls inside the report period), so each writer that moves
``progress_percentage`` must carry it: the manual progress door, the milestone
door, and an intent that carries a progress figure through the core update.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums import EntityStatus
from core.models.enums.goal_enums import MeasurementType
from core.models.goal.goal import Goal
from core.models.goal.goal_update_intent import GoalUpdateIntent
from core.models.goal.milestone import Milestone
from core.services.goals.goals_core_service import GoalsCoreService
from core.services.goals.goals_progress_service import GoalsProgressService
from core.utils.result_simplified import Result
from tests.helpers.status_guarded_backend import guarded_backend

_USER = "user_stamp"
_GOAL = "goal_stamp"


class _Bus:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def publish_async(self, event: object) -> None:
        self.events.append(event)


def _goal(*, milestones_done: tuple[bool, ...] = (), progress: float = 0.0) -> Goal:
    return Goal(
        uid=_GOAL,
        user_uid=_USER,
        title="Stamp me",
        status=EntityStatus.ACTIVE,
        measurement_type=MeasurementType.MILESTONE
        if milestones_done
        else MeasurementType.PERCENTAGE,
        progress_percentage=progress,
        milestones=[
            Milestone(uid=f"m{i}", title=f"Milestone {i}", is_completed=done)
            for i, done in enumerate(milestones_done)
        ],
    )


def _progress_service(backend: Mock) -> GoalsProgressService:
    service = GoalsProgressService.__new__(GoalsProgressService)
    service.backend = backend
    service.logger = Mock()
    service.event_bus = _Bus()
    service.relationships = None  # type: ignore[assignment]
    return service


@pytest.mark.asyncio
async def test_manual_progress_update_stamps_last_progress_update() -> None:
    goal = _goal()
    backend = Mock()
    backend.get_goal = AsyncMock(return_value=Result.ok(goal.to_dto()))
    backend.update_goal = AsyncMock(return_value=Result.ok(goal))
    service = _progress_service(backend)

    result = await service.update_goal_progress(_GOAL, 40.0)

    assert result.is_ok
    updates = backend.update_goal.await_args.args[1]
    assert updates["progress_percentage"] == 40.0
    assert isinstance(updates["last_progress_update"], datetime)


@pytest.mark.asyncio
async def test_milestone_completion_stamps_last_progress_update() -> None:
    read = _goal(milestones_done=(False, False))
    backend, recorder = guarded_backend(read, read)
    backend.get = AsyncMock(return_value=Result.ok(read))
    backend.get_goal = AsyncMock(return_value=Result.ok(read))
    service = _progress_service(backend)

    result = await service.complete_milestone(_GOAL, 0, Mock(user_uid=_USER))

    assert result.is_ok
    updates = recorder.last_updates
    assert updates["progress_percentage"] == 50.0
    assert isinstance(updates["last_progress_update"], datetime)


@pytest.mark.asyncio
async def test_intent_carrying_progress_stamps_last_progress_update() -> None:
    goal = _goal(progress=55.0)
    backend, recorder = guarded_backend(goal, goal)
    core = GoalsCoreService(backend=backend, event_bus=None)

    result = await core.update_goal(_GOAL, GoalUpdateIntent(progress_percentage=55.0))

    assert result.is_ok
    changes = recorder.last_updates
    assert changes["progress_percentage"] == 55.0
    assert isinstance(changes["last_progress_update"], datetime)


@pytest.mark.asyncio
async def test_intent_without_progress_leaves_the_stamp_alone() -> None:
    goal = _goal()
    backend, recorder = guarded_backend(goal, goal)
    core = GoalsCoreService(backend=backend, event_bus=None)

    result = await core.update_goal(_GOAL, GoalUpdateIntent(title="Renamed"))

    assert result.is_ok
    assert "last_progress_update" not in recorder.last_updates


@pytest.mark.asyncio
async def test_reopening_a_completed_goal_stamps_the_conditional_reset() -> None:
    """A status-only reopen resets progress through the guard's prior-conditional
    patch, not through ``changes`` — the stamp must ride that patch."""
    completed = _goal(progress=100.0)
    completed = Goal(**{**completed.__dict__, "status": EntityStatus.COMPLETED})
    backend, recorder = guarded_backend(completed, completed)
    core = GoalsCoreService(backend=backend, event_bus=None)

    result = await core.update_goal(_GOAL, GoalUpdateIntent(status=EntityStatus.ACTIVE.value))

    assert result.is_ok
    assert "last_progress_update" not in recorder.last_updates
    conditional = recorder.last_guard.patch_if_prior_in
    assert conditional is not None
    _statuses, reset = conditional
    assert reset["progress_percentage"] == 0.0
    assert isinstance(reset["last_progress_update"], datetime)


# ---------------------------------------------------------------------------
# complete_goal — the 100% figure and its stamp are part of the TRANSITION
# ---------------------------------------------------------------------------


def _completed(goal: Goal) -> Goal:
    return Goal(**{**goal.__dict__, "status": EntityStatus.COMPLETED})


@pytest.mark.asyncio
async def test_completing_a_goal_carries_progress_on_the_transition_patch() -> None:
    """The 100% and its stamp ride the guard's prior-NOT-in patch beside the
    achievement stamp — never the base patch — so only a real completion
    writes them."""
    active = _goal(progress=40.0)
    backend, recorder = guarded_backend(active, _completed(active))
    core = GoalsCoreService(backend=backend, event_bus=None)

    result = await core.complete_goal(_GOAL)

    assert result.is_ok
    assert "progress_percentage" not in recorder.last_updates
    assert "last_progress_update" not in recorder.last_updates
    conditional = recorder.last_guard.patch_if_prior_not_in
    assert conditional is not None
    statuses, transition = conditional
    assert statuses == frozenset({EntityStatus.COMPLETED.value})
    assert transition["progress_percentage"] == 100.0
    assert isinstance(transition["last_progress_update"], datetime)
    assert "achieved_date" in transition
    merged = recorder.merged_patch()
    assert merged["progress_percentage"] == 100.0
    assert isinstance(merged["last_progress_update"], datetime)


@pytest.mark.asyncio
async def test_reposted_completion_writes_neither_progress_nor_stamp() -> None:
    """A re-posted completion of an already-completed goal is not a progress
    event: the report must not count it in a later period."""
    done = _completed(_goal(progress=100.0))
    backend, recorder = guarded_backend(done, done)
    core = GoalsCoreService(backend=backend, event_bus=None)

    result = await core.complete_goal(_GOAL)

    assert result.is_ok
    merged = recorder.merged_patch()
    assert "progress_percentage" not in merged
    assert "last_progress_update" not in merged


@pytest.mark.asyncio
async def test_explicit_achieved_date_still_gates_progress_on_the_transition() -> None:
    """An intent that supplies its own achieved_date arrives with a guard carrying
    no patches; the transition patch is constructed, not merely extended."""
    active = _goal(progress=40.0)
    backend, recorder = guarded_backend(active, _completed(active))
    core = GoalsCoreService(backend=backend, event_bus=None)

    result = await core.complete_goal(_GOAL, achieved_date="2026-09-01")

    assert result.is_ok
    assert "progress_percentage" not in recorder.last_updates
    conditional = recorder.last_guard.patch_if_prior_not_in
    assert conditional is not None
    _statuses, transition = conditional
    assert transition["progress_percentage"] == 100.0
    assert isinstance(transition["last_progress_update"], datetime)
    assert "achieved_date" not in transition  # the explicit date rides the base patch
    assert recorder.merged_patch()["progress_percentage"] == 100.0
