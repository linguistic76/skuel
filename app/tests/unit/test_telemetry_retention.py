"""Unit tests for telemetry retention + startup connect-retry (ADR-080 Horizon 0).

Two mechanisms, both mockable without a live graph:

- ``TelemetryRetentionBackend`` — the age-based prune Cypher. These tests lock the
  query SHAPE (the temporal-storage-bug-class: native-datetime vs stored-ISO-string
  predicates), the dry-run/real split, and the batched delete loop's termination.
  The persisted-deletion behaviour is proven against a real container in
  ``tests/integration/test_telemetry_retention_roundtrip.py``.
- ``connect_with_retry`` — bounded exponential-backoff around the startup
  connectivity probe. Tests cover first-try success, recover-after-failure, and a
  clean actionable ``RuntimeError`` (never a raw ``ServiceUnavailable``) after the
  bound, with ``asyncio.sleep`` patched out.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from neo4j.exceptions import ServiceUnavailable

from adapters.persistence.neo4j import neo4j_connection
from adapters.persistence.neo4j.neo4j_connection import connect_with_retry
from adapters.persistence.neo4j.telemetry_retention_backend import TelemetryRetentionBackend
from core.utils.result_simplified import Errors, Result


class _FakeExecutor:
    """Records (query, params) and returns a scripted queue of Results."""

    def __init__(self, results: list[Result]) -> None:
        self._results = list(results)
        self.calls: list[tuple[str, dict]] = []

    async def execute_query(self, query: str, params: dict | None = None) -> Result:
        self.calls.append((query, params or {}))
        return self._results.pop(0)


def _rows(cnt: int) -> Result:
    return Result.ok([{"cnt": cnt}])


# ============================================================================
# Dry-run: COUNT only, deletes nothing
# ============================================================================


@pytest.mark.anyio
async def test_dry_run_counts_and_never_deletes() -> None:
    """Dry-run issues exactly one COUNT query and returns its count."""
    executor = _FakeExecutor([_rows(42)])
    backend = TelemetryRetentionBackend(executor)  # type: ignore[arg-type]

    result = await backend.prune_auth_events(days=90, batch_size=500, dry_run=True)

    assert result.is_ok
    assert result.value == 42
    assert len(executor.calls) == 1
    query, params = executor.calls[0]
    assert "count(e)" in query
    assert "DELETE" not in query.upper()
    assert params == {"days": 90}


@pytest.mark.anyio
async def test_auth_event_predicate_is_native_datetime() -> None:
    """AuthEvent.timestamp is a native ZONED DATETIME → compared directly."""
    executor = _FakeExecutor([_rows(0)])
    backend = TelemetryRetentionBackend(executor)  # type: ignore[arg-type]

    await backend.prune_auth_events(days=90, batch_size=500, dry_run=True)

    query, _ = executor.calls[0]
    assert "e.timestamp < datetime() - duration({days: $days})" in query
    # No datetime(...) PARSE wrap around the field — it is already a datetime.
    assert "datetime(e.timestamp)" not in query


@pytest.mark.anyio
async def test_interaction_predicate_parses_stored_string() -> None:
    """Interaction.created_at is a STRING (universal-backend writer) → datetime()-parsed.

    This is the temporal-storage-bug-class guard: getting this wrong silently
    matches zero rows (string vs datetime comparison) and prunes nothing.
    """
    executor = _FakeExecutor([_rows(0)])
    backend = TelemetryRetentionBackend(executor)  # type: ignore[arg-type]

    await backend.prune_interactions(days=365, batch_size=500, dry_run=True)

    query, _ = executor.calls[0]
    assert "datetime(e.created_at) < datetime() - duration({days: $days})" in query


@pytest.mark.anyio
async def test_viewed_dry_run_targets_edge() -> None:
    """VIEWED prune counts the edge (native last_viewed_at), not its endpoints."""
    executor = _FakeExecutor([_rows(3)])
    backend = TelemetryRetentionBackend(executor)  # type: ignore[arg-type]

    result = await backend.prune_viewed_edges(days=365, batch_size=500, dry_run=True)

    assert result.value == 3
    query, _ = executor.calls[0]
    assert "[r:VIEWED]" in query
    assert "r.last_viewed_at < datetime() - duration({days: $days})" in query


# ============================================================================
# Real run: batched delete loop
# ============================================================================


@pytest.mark.anyio
async def test_batch_loop_drains_across_multiple_batches() -> None:
    """A full batch keeps looping; a short batch stops the loop. 500 + 31 = 531."""
    executor = _FakeExecutor([_rows(500), _rows(31)])
    backend = TelemetryRetentionBackend(executor)  # type: ignore[arg-type]

    result = await backend.prune_auth_events(days=90, batch_size=500, dry_run=False)

    assert result.is_ok
    assert result.value == 531
    assert len(executor.calls) == 2  # looped once more because batch 1 was full
    for query, params in executor.calls:
        assert "DETACH DELETE e" in query
        assert params == {"days": 90, "batch": 500}


@pytest.mark.anyio
async def test_single_short_batch_stops_immediately() -> None:
    """A first batch below batch_size ends the loop after one delete."""
    executor = _FakeExecutor([_rows(7)])
    backend = TelemetryRetentionBackend(executor)  # type: ignore[arg-type]

    result = await backend.prune_search_events(days=90, batch_size=500, dry_run=False)

    assert result.value == 7
    assert len(executor.calls) == 1


@pytest.mark.anyio
async def test_empty_delete_returns_zero() -> None:
    """Nothing to prune: one delete returns 0, loop stops, total 0."""
    executor = _FakeExecutor([_rows(0)])
    backend = TelemetryRetentionBackend(executor)  # type: ignore[arg-type]

    result = await backend.prune_interactions(days=365, batch_size=500, dry_run=False)

    assert result.value == 0
    assert len(executor.calls) == 1


def test_prune_surface_excludes_conversations() -> None:
    """The prune surface is exactly the four SYSTEM-telemetry types.

    Regression guard: saved discussions (:ConversationSession) are user content
    (ADR-078 "Save this chat") — retention must never delete something a user
    chose to keep. If someone re-adds a conversation prune (or drops an expected
    one), this fails loudly.
    """
    prune_methods = {m for m in dir(TelemetryRetentionBackend) if m.startswith("prune_")}
    assert prune_methods == {
        "prune_auth_events",
        "prune_search_events",
        "prune_interactions",
        "prune_viewed_edges",
    }


@pytest.mark.anyio
async def test_error_result_propagates() -> None:
    """A backend query failure surfaces as an error Result, not a raise."""
    executor = _FakeExecutor([Result.fail(Errors.database(operation="q", message="down"))])
    backend = TelemetryRetentionBackend(executor)  # type: ignore[arg-type]

    result = await backend.prune_auth_events(days=90, batch_size=500, dry_run=True)

    assert result.is_error


# ============================================================================
# connect_with_retry — bounded exponential backoff
# ============================================================================


@pytest.mark.anyio
async def test_connect_succeeds_first_try_without_sleeping() -> None:
    """A reachable instance returns on attempt 1 and never backs off."""
    conn = AsyncMock()
    conn.probe_connectivity = AsyncMock(return_value=None)

    with patch.object(neo4j_connection.asyncio, "sleep", AsyncMock()) as sleep:
        await connect_with_retry(
            conn, max_attempts=3, base_delay_seconds=0.1, max_delay_seconds=1.0
        )

    conn.probe_connectivity.assert_awaited_once()
    sleep.assert_not_awaited()


@pytest.mark.anyio
async def test_connect_recovers_after_transient_failure() -> None:
    """A waking instance (fail once, then succeed) is tolerated with one backoff."""
    conn = AsyncMock()
    conn.probe_connectivity = AsyncMock(side_effect=[ServiceUnavailable("waking"), None])

    with patch.object(neo4j_connection.asyncio, "sleep", AsyncMock()) as sleep:
        await connect_with_retry(
            conn, max_attempts=3, base_delay_seconds=0.1, max_delay_seconds=1.0
        )

    assert conn.probe_connectivity.await_count == 2
    sleep.assert_awaited_once()


@pytest.mark.anyio
async def test_connect_raises_clean_error_after_exhausting_attempts() -> None:
    """All attempts fail → a clean actionable RuntimeError, not a raw ServiceUnavailable."""
    conn = AsyncMock()
    conn.probe_connectivity = AsyncMock(side_effect=ServiceUnavailable("down"))

    with patch.object(neo4j_connection.asyncio, "sleep", AsyncMock()) as sleep:
        with pytest.raises(RuntimeError, match="Neo4j unreachable after 3 attempts"):
            await connect_with_retry(
                conn, max_attempts=3, base_delay_seconds=0.1, max_delay_seconds=1.0
            )

    assert conn.probe_connectivity.await_count == 3
    assert sleep.await_count == 2  # backs off between attempts, not after the last


@pytest.mark.anyio
async def test_backoff_is_bounded_by_max_delay() -> None:
    """Delays grow exponentially but never exceed max_delay_seconds."""
    conn = AsyncMock()
    conn.probe_connectivity = AsyncMock(side_effect=ServiceUnavailable("down"))
    delays: list[float] = []

    async def _record(seconds: float) -> None:
        delays.append(seconds)

    with patch.object(neo4j_connection.asyncio, "sleep", _record):
        with pytest.raises(RuntimeError):
            await connect_with_retry(
                conn, max_attempts=5, base_delay_seconds=1.0, max_delay_seconds=4.0
            )

    # 1, 2, 4, then capped at 4 (not 8)
    assert delays == [1.0, 2.0, 4.0, 4.0]
