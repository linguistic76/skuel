"""Every goal-progress writer appends a ``progress_history`` entry beside its stamp.

The report's ``goals_progressed`` counts from this persisted history — a
single stamp is overwritten by every later write — so each writer that moves
``progress_percentage`` appends ``{date, progress_percentage}`` from the goal
it pre-read: the manual door, the milestone door, the habit-progress recompute,
and an intent carrying a figure through the core update, where a completion's
entry rides the transition patch and a repeat appends nothing.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from core.models.enums import EntityStatus
from core.models.enums.goal_enums import MeasurementType
from core.models.goal.goal import Goal
from core.models.goal.goal_update_intent import GoalUpdateIntent
from core.models.goal.milestone import Milestone
from core.services.goals.goal_relationships import GoalRelationships
from core.services.goals.goals_core_service import GoalsCoreService
from core.services.goals.goals_progress_service import GoalsProgressService
from core.services.goals.progress_history import progress_entry, with_progress_entry
from core.utils.result_simplified import Result
from tests.helpers.status_guarded_backend import guarded_backend

_USER = "user_history"
_GOAL = "goal_history"
_EARLIER = {"date": "2026-08-20T09:00:00", "progress_percentage": 20.0}


class _Bus:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def publish_async(self, event: object) -> None:
        self.events.append(event)


def _goal(
    *,
    progress: float = 20.0,
    status: EntityStatus = EntityStatus.ACTIVE,
    milestones_done: tuple[bool, ...] = (),
    history: tuple[dict, ...] = (_EARLIER,),
) -> Goal:
    return Goal(
        uid=_GOAL,
        user_uid=_USER,
        title="Keep the record",
        status=status,
        measurement_type=MeasurementType.MILESTONE
        if milestones_done
        else MeasurementType.PERCENTAGE,
        progress_percentage=progress,
        progress_history=history,
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


def _entries(updates: dict) -> list[dict]:  # type: ignore[type-arg]
    return list(updates["progress_history"])


# ---------------------------------------------------------------------------
# The helper
# ---------------------------------------------------------------------------


def test_with_progress_entry_appends_after_the_stored_history() -> None:
    at = datetime(2026, 9, 12, 10, 0)
    history = with_progress_entry(_goal(), 55.0, at)
    assert history == [_EARLIER, progress_entry(55.0, at)]
    assert history[-1] == {"date": "2026-09-12T10:00:00", "progress_percentage": 55.0}
    # Copied out of the goal's read-only views: plain dicts the write can serialize.
    assert all(type(entry) is dict for entry in history)


def test_with_progress_entry_starts_the_history_without_a_goal() -> None:
    at = datetime(2026, 9, 12, 10, 0)
    assert with_progress_entry(None, 10.0, at) == [progress_entry(10.0, at)]


# ---------------------------------------------------------------------------
# The writers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manual_progress_update_appends_an_entry() -> None:
    goal = _goal()
    backend = Mock()
    backend.get_goal = AsyncMock(return_value=Result.ok(goal.to_dto()))
    backend.update_goal = AsyncMock(return_value=Result.ok(goal))
    service = _progress_service(backend)

    result = await service.update_goal_progress(_GOAL, 40.0)

    assert result.is_ok
    updates = backend.update_goal.await_args.args[1]
    entries = _entries(updates)
    assert entries[0] == _EARLIER
    assert entries[-1]["progress_percentage"] == 40.0
    assert entries[-1]["date"] == updates["last_progress_update"].isoformat()


@pytest.mark.asyncio
async def test_re_posting_the_stored_figure_appends_nothing() -> None:
    goal = _goal(progress=40.0)
    backend = Mock()
    backend.get_goal = AsyncMock(return_value=Result.ok(goal.to_dto()))
    backend.update_goal = AsyncMock(return_value=Result.ok(goal))
    service = _progress_service(backend)

    await service.update_goal_progress(_GOAL, 40.0)

    assert "progress_history" not in backend.update_goal.await_args.args[1]


@pytest.mark.asyncio
async def test_milestone_completion_appends_an_entry() -> None:
    read = _goal(milestones_done=(False, False), progress=0.0)
    backend, recorder = guarded_backend(read, read)
    backend.get = AsyncMock(return_value=Result.ok(read))
    backend.get_goal = AsyncMock(return_value=Result.ok(read))
    service = _progress_service(backend)

    result = await service.complete_milestone(_GOAL, 0, Mock(user_uid=_USER))

    assert result.is_ok
    entries = _entries(recorder.last_updates)
    assert entries[-1]["progress_percentage"] == 50.0


@pytest.mark.asyncio
async def test_habit_progress_recompute_appends_an_entry_only_when_the_figure_moves() -> None:
    goal = _goal(progress=100.0)
    goal = Goal(**{**goal.__dict__, "measurement_type": MeasurementType.HABIT_BASED})
    backend, recorder = guarded_backend(goal, goal)
    backend.get_goal = AsyncMock(return_value=Result.ok(goal.to_dto()))
    service = _progress_service(backend)
    service.relationships = Mock()  # type: ignore[assignment]
    linked = GoalRelationships(supporting_habit_uids=["habit_1"])
    with patch.object(GoalRelationships, "fetch", AsyncMock(return_value=linked)):
        result = await service.update_goal_from_habit_progress(_GOAL, "habit_1", 31)

    assert result.is_ok
    assert "progress_history" not in recorder.last_updates


@pytest.mark.asyncio
async def test_intent_carrying_a_moving_figure_appends_an_entry() -> None:
    goal = _goal(progress=20.0)
    backend, recorder = guarded_backend(goal, goal)
    core = GoalsCoreService(backend=backend, event_bus=None)

    result = await core.update_goal(_GOAL, GoalUpdateIntent(progress_percentage=55.0))

    assert result.is_ok
    entries = _entries(recorder.last_updates)
    assert entries == [_EARLIER, {"date": entries[-1]["date"], "progress_percentage": 55.0}]


@pytest.mark.asyncio
async def test_completion_appends_its_entry_on_the_transition_only() -> None:
    """The 100% entry rides the prior-NOT-in patch beside the figure and stamp:
    applied for an ACTIVE prior, written by a repeat not at all."""
    active = _goal(progress=20.0)
    backend, recorder = guarded_backend(active, active)
    core = GoalsCoreService(backend=backend, event_bus=None)
    result = await core.complete_goal(_GOAL)
    assert result.is_ok
    # Not in the base patch — on the transition patch the ACTIVE prior selects.
    assert "progress_history" not in recorder.last_updates
    entries = _entries(recorder.merged_patch())
    assert entries[-1]["progress_percentage"] == 100.0

    done = _goal(progress=100.0, status=EntityStatus.COMPLETED)
    backend, recorder = guarded_backend(done, done)
    core = GoalsCoreService(backend=backend, event_bus=None)
    result = await core.complete_goal(_GOAL)
    assert result.is_ok
    assert "progress_history" not in recorder.merged_patch()
    assert "last_progress_update" not in recorder.merged_patch()


# ---------------------------------------------------------------------------
# The reopen reset and the supplied progress date
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reopening_a_completed_goal_appends_the_reset_entry_on_the_transition() -> None:
    """A status-only reopen resets 100% -> 0% under the prior-COMPLETED condition;
    the history entry rides that same patch, so the report counts the reopen."""
    done = _goal(progress=100.0, status=EntityStatus.COMPLETED)
    backend, recorder = guarded_backend(done, done)
    core = GoalsCoreService(backend=backend, event_bus=None)

    result = await core.update_goal(_GOAL, GoalUpdateIntent(status="active"))

    assert result.is_ok
    merged = recorder.merged_patch()
    assert merged["progress_percentage"] == 0.0
    entries = _entries(merged)
    assert entries[:-1] == [_EARLIER]
    assert entries[-1]["progress_percentage"] == 0.0
    assert entries[-1]["date"] == merged["last_progress_update"].isoformat()


@pytest.mark.asyncio
async def test_a_status_change_that_reopens_nothing_appends_nothing() -> None:
    """Pausing an ACTIVE goal names a non-terminal status too, but the prior is
    not COMPLETED, so the reset patch — entry included — is not applied."""
    active = _goal(progress=40.0)
    backend, recorder = guarded_backend(active, active)
    core = GoalsCoreService(backend=backend, event_bus=None)

    result = await core.update_goal(_GOAL, GoalUpdateIntent(status="paused"))

    assert result.is_ok
    assert "progress_history" not in recorder.merged_patch()
    assert "progress_percentage" not in recorder.merged_patch()


@pytest.mark.asyncio
async def test_manual_update_dates_its_entry_and_stamp_at_the_supplied_date() -> None:
    """A September correction entered in October is a September event."""
    goal = _goal()
    backend = Mock()
    backend.get_goal = AsyncMock(return_value=Result.ok(goal.to_dto()))
    backend.update_goal = AsyncMock(return_value=Result.ok(goal))
    service = _progress_service(backend)

    result = await service.update_goal_progress(
        _GOAL, 45.0, notes="late entry", update_date="2026-09-05"
    )

    assert result.is_ok
    updates = backend.update_goal.await_args.args[1]
    assert updates["last_progress_update"] == datetime(2026, 9, 5)
    assert _entries(updates)[-1] == {"date": "2026-09-05T00:00:00", "progress_percentage": 45.0}
    assert updates["metadata"]["progress_notes"][-1]["date"] == "2026-09-05T00:00:00"
    assert result.value["update_date"] == "2026-09-05T00:00:00"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["not-a-date", "2099-01-01"])
async def test_an_unparseable_or_future_update_date_is_refused_before_any_write(
    bad: str,
) -> None:
    goal = _goal()
    backend = Mock()
    backend.get_goal = AsyncMock(return_value=Result.ok(goal.to_dto()))
    backend.update_goal = AsyncMock(return_value=Result.ok(goal))
    service = _progress_service(backend)

    result = await service.update_goal_progress(_GOAL, 45.0, update_date=bad)

    assert result.is_error
    assert result.expect_error().category.value == "validation"
    backend.update_goal.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_status", [None, "reopened", ""])
async def test_a_null_or_unknown_status_is_a_validation_failure_not_a_crash(
    bad_status: str | None,
) -> None:
    """The reopen predicate runs before the guard's legality check; a target
    that is not a status is not a reopen, and the guard refuses it as the
    validation failure it is — never a ValueError the database decorator turns
    into a 503."""
    done = _goal(progress=100.0, status=EntityStatus.COMPLETED)
    backend, recorder = guarded_backend(done, done)
    core = GoalsCoreService(backend=backend, event_bus=None)

    result = await core.update_goal(_GOAL, GoalUpdateIntent(status=bad_status))

    assert result.is_error
    assert result.expect_error().category.value == "validation"
    assert recorder.calls == []  # refused before the write
