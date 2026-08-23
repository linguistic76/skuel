"""The productivity reconciliation's DB-free contract.

``scripts/reconcile_productivity_analytics.py`` is a one-shot pass that
recomputes the derived ``ProductivityAnalytics.tasks_completed`` for every user
whose stored value disagrees with the graph. Four things about it can rot
without any Cypher running, and each is the whole point of the instrument:

1. **``--dry-run`` writes nothing.** It is the only way to look before leaping,
   so a report path that quietly called the writer would be worse than no flag.
2. **Only drifted users are written.** That is what makes the second run a
   no-op rather than a re-write of the same numbers.
3. **``occurred_at`` is always ``None``.** A reconciliation is not a completion
   moment; passing the wall clock would stamp ``last_completion_at`` and stretch
   the velocity denominator to make a bookkeeping run look tidy.
4. **A user with zero completed tasks is corrected, not skipped.** The stale
   node holding a legacy tally is exactly the row whose true count is often 0.

The Cypher — the scan set especially — is exercised against a real graph in
``tests/integration/test_reconcile_productivity_analytics.py``. These run on
every CI job; that one is path-filtered.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import reconcile_productivity_analytics as reconciler  # type: ignore[import-not-found]

from core.utils.result_simplified import Result


def _row(user_uid: str, stored: int | None, actual: int) -> dict[str, Any]:
    """One survey row, in the shape the backend query returns."""
    return {"user_uid": user_uid, "stored": stored, "actual": actual}


def _backend(rows: list[dict[str, Any]], *, after: list[dict[str, Any]] | None = None) -> Any:
    """A faithful fake of the two backend methods the pass uses.

    ``after`` is the survey the post-write verification sees; it defaults to a
    converged graph so the happy path does not have to spell that out.
    """
    backend = AsyncMock()
    surveys = [Result.ok(rows), Result.ok(after if after is not None else _converged(rows))]
    backend.survey_productivity_analytics_drift = AsyncMock(side_effect=surveys)
    backend.recompute_productivity_analytics = AsyncMock(return_value=Result.ok([]))
    return backend


def _converged(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The same users, with every stored value now equal to the graph's count."""
    return [_row(row["user_uid"], row["actual"], row["actual"]) for row in rows]


@pytest.mark.asyncio
async def test_dry_run_writes_nothing() -> None:
    """The whole value of the flag: a report, and no ``SET``."""
    backend = _backend([_row("user_mike", 9, 85), _row("user_ana", 3, 3)])

    assert await reconciler.reconcile(backend, dry_run=True) == 0

    backend.recompute_productivity_analytics.assert_not_awaited()


@pytest.mark.asyncio
async def test_dry_run_still_reports_the_drift(capsys: pytest.CaptureFixture[str]) -> None:
    backend = _backend([_row("user_mike", 9, 85), _row("user_ana", 3, 3)])

    await reconciler.reconcile(backend, dry_run=True)

    out = capsys.readouterr().out
    assert "DRY RUN (nothing written)" in out
    assert "user_mike" in out and "85" in out
    assert "user_ana" not in out, "a user already in agreement is not drift"


@pytest.mark.asyncio
async def test_only_drifted_users_are_written() -> None:
    backend = _backend([_row("user_mike", 9, 85), _row("user_ana", 3, 3)])

    assert await reconciler.reconcile(backend, dry_run=False) == 0

    written = [
        call.kwargs["user_uid"] for call in backend.recompute_productivity_analytics.await_args_list
    ]
    assert written == ["user_mike"]


@pytest.mark.asyncio
async def test_the_write_never_invents_a_completion_moment() -> None:
    """``occurred_at=None`` — the completion stamps are not the pass's business."""
    backend = _backend([_row("user_mike", 9, 85)])

    await reconciler.reconcile(backend, dry_run=False)

    backend.recompute_productivity_analytics.assert_awaited_once_with(
        user_uid="user_mike", occurred_at=None
    )


@pytest.mark.asyncio
async def test_a_converged_graph_issues_no_write_at_all() -> None:
    """The second run, expressed as a state rather than a sequence.

    Nothing drifts, so nothing is written — and the pass does not even reach the
    verification survey, which is why only one survey is consumed here.
    """
    backend = _backend([_row("user_mike", 85, 85)], after=[])

    assert await reconciler.reconcile(backend, dry_run=False) == 0

    backend.recompute_productivity_analytics.assert_not_awaited()
    assert backend.survey_productivity_analytics_drift.await_count == 1


@pytest.mark.asyncio
async def test_zero_completed_tasks_is_corrected_not_skipped() -> None:
    """A legacy tally whose true count has fallen to 0 is the headline case.

    Every completed task deleted, or reopened before the recompute existed —
    ``stored`` is 9 and ``actual`` is 0, and skipping it would leave the stale
    number being served under the new meaning forever.
    """
    backend = _backend([_row("user_mike", 9, 0)])

    assert await reconciler.reconcile(backend, dry_run=False) == 0

    backend.recompute_productivity_analytics.assert_awaited_once_with(
        user_uid="user_mike", occurred_at=None
    )


@pytest.mark.asyncio
async def test_a_missing_node_counts_as_drift() -> None:
    """The vault ``- [x]`` door's signature: completions, no analytics node.

    ``stored`` is ``None``, not 0 — coercing it would read as agreement with a
    user who has no completed tasks and write nothing.
    """
    surveyed = await reconciler.find_drift(_backend([_row("user_vault", None, 12)]))

    assert surveyed.is_ok
    _, drifted = surveyed.value
    assert drifted == [reconciler.Drift(user_uid="user_vault", stored=None, actual=12)]


@pytest.mark.asyncio
async def test_a_failed_survey_is_reported_not_swallowed() -> None:
    backend = AsyncMock()
    backend.survey_productivity_analytics_drift = AsyncMock(
        return_value=Result.fail("Neo4j is unreachable")
    )
    backend.recompute_productivity_analytics = AsyncMock()

    assert await reconciler.reconcile(backend, dry_run=False) == 1

    backend.recompute_productivity_analytics.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failed_write_exits_nonzero() -> None:
    backend = _backend([_row("user_mike", 9, 85)])
    backend.recompute_productivity_analytics = AsyncMock(return_value=Result.fail("write refused"))

    assert await reconciler.reconcile(backend, dry_run=False) == 1


@pytest.mark.asyncio
async def test_drift_surviving_the_write_exits_nonzero() -> None:
    """Convergence is proven, not asserted.

    A user still drifting after the pass was written by another door mid-run (or
    failed above). Re-running fixes it; reporting success would not.
    """
    rows = [_row("user_mike", 9, 85)]
    backend = _backend(rows, after=rows)

    assert await reconciler.reconcile(backend, dry_run=False) == 1
