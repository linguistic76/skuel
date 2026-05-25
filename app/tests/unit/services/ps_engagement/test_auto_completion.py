"""Unit tests for ``PsEngagementService.check_auto_complete``.

The method is a wrapper around one ``PsEngagementBackend`` read + Python
classification + delegate to ``complete_pathstep``. These tests replace the
backend with an in-memory stub so we can rehearse the branches without Neo4j:

  - Instance is not part of an engagement → returns None, never calls complete.
  - Some siblings still pending → returns None, never calls complete.
  - All siblings terminal → calls ``complete_pathstep`` with empty review.
  - Principle siblings never block (always engagement-terminal).
  - Habit ACTIVE sibling blocks (PAUSED also blocks — see rule).
  - Malformed sibling record is treated as "skip auto-complete" — student declares.

Live Cypher behavior is covered by the integration test suite.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from core.services.ps_engagement.engagement import Engagement
from core.services.ps_engagement.ps_engagement_service import PsEngagementService
from core.utils.result_simplified import Errors, Result


@dataclass
class _StubBackend:
    """Captures the call args; returns a canned result."""

    canned: Any
    called_with: list[dict[str, Any]] | None = None

    async def fetch_auto_complete_siblings(
        self, student_uid: str, instance_uid: str
    ) -> Result[list[dict[str, Any]]]:
        if self.called_with is None:
            self.called_with = []
        self.called_with.append({"student_uid": student_uid, "instance_uid": instance_uid})
        return self.canned


def _service_with_stubs(
    backend: _StubBackend,
    complete_mock: AsyncMock | None = None,
) -> PsEngagementService:
    """Build a PsEngagementService with only the backend + complete patched.

    ``check_auto_complete`` only touches ``self._backend`` and (on success)
    ``self.complete_pathstep`` — skipping the full constructor keeps the test
    focused on the classification + delegation surface.
    """
    svc = PsEngagementService.__new__(PsEngagementService)
    svc._backend = backend  # type: ignore[assignment]
    svc.logger = AsyncMock()  # silences the info/warning logs
    if complete_mock is not None:
        svc.complete_pathstep = complete_mock  # type: ignore[method-assign]
    return svc


def _completed_engagement(ps_uid: str = "ps_x") -> Engagement:
    return Engagement(
        student_uid="user_alice",
        ps_uid=ps_uid,
        state="completed",
        since=datetime(2026, 5, 11, 9, 0, tzinfo=UTC),
        completed_at=datetime(2026, 5, 11, 10, 0, tzinfo=UTC),
    )


@pytest.mark.anyio
async def test_returns_none_when_instance_not_in_active_engagement() -> None:
    """Empty query result → no engagement → no-op."""
    backend = _StubBackend(canned=Result.ok([]))
    complete = AsyncMock()
    svc = _service_with_stubs(backend, complete)

    res = await svc.check_auto_complete("user_alice", "task_loose")

    assert res.is_ok
    assert res.value is None
    complete.assert_not_called()


@pytest.mark.anyio
async def test_returns_none_when_query_fails() -> None:
    """Backend failure is propagated as an error Result, complete is not called."""
    backend = _StubBackend(
        canned=Result.fail(Errors.database(operation="check_auto_complete", message="boom"))
    )
    complete = AsyncMock()
    svc = _service_with_stubs(backend, complete)

    res = await svc.check_auto_complete("user_alice", "task_x")

    assert res.is_error
    complete.assert_not_called()


@pytest.mark.anyio
async def test_pending_sibling_blocks_auto_complete() -> None:
    """A Task still ACTIVE keeps the engagement open."""
    backend = _StubBackend(
        canned=Result.ok(
            [
                {
                    "ps_uid": "ps_x",
                    "siblings": [
                        {"entity_type": "task", "status": "completed"},
                        {"entity_type": "task", "status": "active"},  # still pending
                    ],
                }
            ]
        )
    )
    complete = AsyncMock()
    svc = _service_with_stubs(backend, complete)

    res = await svc.check_auto_complete("user_alice", "task_done")

    assert res.is_ok
    assert res.value is None
    complete.assert_not_called()


@pytest.mark.anyio
async def test_all_terminal_fires_complete_with_empty_review() -> None:
    """When every sibling is engagement-terminal, complete is called with review={}."""
    backend = _StubBackend(
        canned=Result.ok(
            [
                {
                    "ps_uid": "ps_x",
                    "siblings": [
                        {"entity_type": "task", "status": "completed"},
                        {"entity_type": "goal", "status": "completed"},
                        {"entity_type": "event", "status": "completed"},
                        {"entity_type": "choice", "status": "completed"},
                    ],
                }
            ]
        )
    )
    expected = _completed_engagement("ps_x")
    complete = AsyncMock(return_value=Result.ok(expected))
    svc = _service_with_stubs(backend, complete)

    res = await svc.check_auto_complete("user_alice", "task_done")

    assert res.is_ok
    assert res.value is expected
    complete.assert_awaited_once_with("user_alice", "ps_x", review={})


@pytest.mark.anyio
async def test_principle_active_does_not_block() -> None:
    """Principle ACTIVE is engagement-terminal — it never blocks completion."""
    backend = _StubBackend(
        canned=Result.ok(
            [
                {
                    "ps_uid": "ps_x",
                    "siblings": [
                        {"entity_type": "task", "status": "completed"},
                        {"entity_type": "principle", "status": "active"},  # passes
                    ],
                }
            ]
        )
    )
    expected = _completed_engagement("ps_x")
    complete = AsyncMock(return_value=Result.ok(expected))
    svc = _service_with_stubs(backend, complete)

    res = await svc.check_auto_complete("user_alice", "task_done")

    assert res.is_ok
    assert res.value is expected
    complete.assert_awaited_once()


@pytest.mark.anyio
async def test_habit_active_blocks() -> None:
    """Habit ACTIVE is NOT engagement-terminal — engagement waits."""
    backend = _StubBackend(
        canned=Result.ok(
            [
                {
                    "ps_uid": "ps_x",
                    "siblings": [
                        {"entity_type": "task", "status": "completed"},
                        {"entity_type": "habit", "status": "active"},  # blocks
                    ],
                }
            ]
        )
    )
    complete = AsyncMock()
    svc = _service_with_stubs(backend, complete)

    res = await svc.check_auto_complete("user_alice", "task_done")

    assert res.is_ok
    assert res.value is None
    complete.assert_not_called()


@pytest.mark.anyio
async def test_malformed_sibling_does_not_auto_complete() -> None:
    """Bad entity_type / status string → defensive return None, log warning."""
    backend = _StubBackend(
        canned=Result.ok(
            [
                {
                    "ps_uid": "ps_x",
                    "siblings": [
                        {"entity_type": "task", "status": "completed"},
                        {"entity_type": "not_a_real_type", "status": "completed"},
                    ],
                }
            ]
        )
    )
    complete = AsyncMock()
    svc = _service_with_stubs(backend, complete)

    res = await svc.check_auto_complete("user_alice", "task_done")

    assert res.is_ok
    assert res.value is None
    complete.assert_not_called()


@pytest.mark.anyio
async def test_call_carries_expected_args() -> None:
    """Sanity check that the backend read is called with the call arguments."""
    backend = _StubBackend(canned=Result.ok([]))
    svc = _service_with_stubs(backend, AsyncMock())

    await svc.check_auto_complete("user_alice", "task_xyz")

    assert backend.called_with is not None
    [call] = backend.called_with
    assert call == {"student_uid": "user_alice", "instance_uid": "task_xyz"}
