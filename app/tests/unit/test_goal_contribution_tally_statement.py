"""A goal's contribution tally has one statement and one percentage.

The locked recompute writes a TASK_BASED goal's progress from the tally; the
progress dashboard reports from it. Both must count by one membership rule and
scale by one function, or a goal's stored figure and its reported one drift
apart. These pin the two backend callers to the shared statement
(``build_contribution_tally_query``) and the two service callers to the shared
percentage (``contribution_progress``).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from adapters.persistence.neo4j.backends.activity_backends import GoalsBackend
from adapters.persistence.neo4j.query.cypher.goal_tally_queries import (
    build_contribution_tally_query,
    contribution_tally_params,
)
from core.models.enums.goal_enums import MeasurementType
from core.models.goal.goal import Goal
from core.models.goal.goal_contribution import DONE_STATUSES, OUT_STATUSES
from core.models.type_hints import UserUID
from core.ports.query_types import ContributionTally
from core.services.goals.goals_progress_service import (
    _plan_contribution_progress,
    contribution_progress,
)
from core.utils.result_simplified import Result

_GOAL = "goal_tally_pin"
_USER = UserUID("user_tally_pin")


def _backend() -> GoalsBackend:
    """A GoalsBackend with no driver — every statement it sends is captured, none runs."""
    return GoalsBackend.__new__(GoalsBackend)


def _decline(_goal: Goal, _tally: ContributionTally) -> None:
    """A planner that writes nothing."""
    return


@pytest.mark.asyncio
async def test_the_recompute_and_the_read_send_the_same_statement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _backend()
    recompute = AsyncMock(return_value=Result.ok(None))
    read = AsyncMock(
        return_value=Result.ok([{"total_contributions": 10, "completed_contributions": 8}])
    )
    monkeypatch.setattr(backend, "_recompute_with_status_guard", recompute)
    monkeypatch.setattr(backend, "execute_query", read)

    await backend.recompute_progress_from_contributions(_GOAL, _decline)
    tally = await backend.get_contribution_tally(_GOAL)

    statement = build_contribution_tally_query()
    assert recompute.await_args is not None
    assert read.await_args is not None
    _uid, written_statement, written_params, _plan = recompute.await_args.args
    read_statement, read_params = read.await_args.args

    assert written_statement == statement
    assert read_statement == statement
    # The recompute primitive binds ``$uid`` itself; the read binds it here.
    assert written_params == contribution_tally_params()
    assert read_params == {**contribution_tally_params(), "uid": _GOAL}
    assert tally.value == {"total_contributions": 10, "completed_contributions": 8}


def test_the_statement_reads_the_owner_off_the_goal() -> None:
    """No caller binds whose contributions count — the goal's own owner is the scope."""
    statement = build_contribution_tally_query()
    params = contribution_tally_params()

    assert "c.user_uid = goal.user_uid" in statement
    assert "user_uid" not in params
    assert "count(DISTINCT c)" in statement
    assert set(params["done"]) == {s.value for s in DONE_STATUSES}
    assert set(params["out"]) == {s.value for s in OUT_STATUSES}


@pytest.mark.asyncio
async def test_the_planner_and_the_read_narrow_the_row_alike(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both callers hand on the same ``ContributionTally`` for the same row."""
    backend = _backend()
    row = {"total_contributions": 4, "completed_contributions": 3}
    planned: list[ContributionTally] = []

    async def run_plan(_uid: str, _query: str, _params: Any, plan: Any) -> Result[None]:
        plan(None, row)
        return Result.ok(None)

    def capture(_goal: Goal, tally: ContributionTally) -> None:
        planned.append(tally)

    monkeypatch.setattr(backend, "_recompute_with_status_guard", run_plan)
    monkeypatch.setattr(backend, "execute_query", AsyncMock(return_value=Result.ok([row])))

    await backend.recompute_progress_from_contributions(_GOAL, capture)
    read = await backend.get_contribution_tally(_GOAL)

    assert planned == [read.value] == [{"total_contributions": 4, "completed_contributions": 3}]


@pytest.mark.asyncio
async def test_a_read_that_returns_no_row_is_a_zero_tally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _backend()
    monkeypatch.setattr(backend, "execute_query", AsyncMock(return_value=Result.ok([])))

    tally = await backend.get_contribution_tally(_GOAL)

    assert tally.value == {"total_contributions": 0, "completed_contributions": 0}


@pytest.mark.parametrize(
    ("total", "completed", "expected"),
    [(10, 8, 80.0), (3, 3, 100.0), (4, 0, 0.0), (0, 0, 0.0)],
)
def test_contribution_progress_is_completed_over_total(
    total: int, completed: int, expected: float
) -> None:
    tally = ContributionTally(total_contributions=total, completed_contributions=completed)
    assert contribution_progress(tally) == expected


def test_the_figure_a_recompute_writes_is_contribution_progress() -> None:
    """The planner's ``progress_percentage`` is the function the dashboard reports with."""
    goal = Goal(
        uid=_GOAL,
        title="Tally pin",
        user_uid=_USER,
        measurement_type=MeasurementType.TASK_BASED,
        progress_percentage=0.0,
    )
    tally = ContributionTally(total_contributions=3, completed_contributions=2)

    write = _plan_contribution_progress(goal, tally)

    assert write is not None
    assert write.updates["progress_percentage"] == contribution_progress(tally)
