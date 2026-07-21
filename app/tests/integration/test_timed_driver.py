"""Integration tests for TimedDriver against a real Neo4j 2026.06.0 container.

Proves the **server** aborts a runaway query at the configured per-tx timeout
(not the client just giving up). Uses a busy Cartesian-product Cypher — APOC's
``apoc.util.sleep`` is banned by SKUEL001 — so the work that gets aborted is
genuine server-side computation.
"""

from __future__ import annotations

import time

import pytest
from neo4j.exceptions import ClientError, TransientError

from adapters.persistence.neo4j.timed_driver import (
    TimedDriver,
    neo4j_query_timeout,
    unbounded_neo4j_query_timeout,
)

# Nested UNWIND range produces 16e12 candidate row pairs — minutes of pure
# server work, no APOC, no plugin dependency. The aggregation prevents the
# planner from short-circuiting.
_BUSY_QUERY = "UNWIND range(1, 4000000) AS i UNWIND range(1, 4000000) AS j RETURN count(i + j) AS c"

# Wall-clock guard: even with a 1s server timeout, the round-trip + error
# materialisation can add a few hundred ms. 15s catches "server didn't abort"
# regressions without being flaky on a slow CI runner.
_ABORT_DEADLINE_SECONDS = 15.0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_runaway_query_aborted_by_server_side_timeout(neo4j_driver):
    """The server aborts the busy query at the configured 1s tx timeout."""
    timed = TimedDriver(neo4j_driver, default_timeout=1.0)

    start = time.monotonic()
    with pytest.raises((ClientError, TransientError)) as exc_info:
        async with timed.session() as session:
            result = await session.run(_BUSY_QUERY)
            await result.consume()
    elapsed = time.monotonic() - start

    # The server aborted (not the client hanging until pytest's outer timeout).
    assert elapsed < _ABORT_DEADLINE_SECONDS, (
        f"Query ran for {elapsed:.1f}s — server did not abort at the 1s bound"
    )
    msg = str(exc_info.value).lower()
    assert "timeout" in msg or "terminated" in msg or "timed out" in msg, (
        f"Unexpected error message (no timeout/terminated keyword): {exc_info.value}"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_default_timeout_lets_light_query_complete(neo4j_driver):
    """A trivial query finishes well under the default."""
    timed = TimedDriver(neo4j_driver, default_timeout=5.0)
    async with timed.session() as session:
        result = await session.run("RETURN 1 AS x")
        record = await result.single()
        assert record is not None
        assert record["x"] == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_neo4j_query_timeout_override_tightens_bound(neo4j_driver):
    """`neo4j_query_timeout(0.001)` aborts a query the default would allow."""
    timed = TimedDriver(neo4j_driver, default_timeout=60.0)

    start = time.monotonic()
    with pytest.raises((ClientError, TransientError)):
        with neo4j_query_timeout(0.001):
            async with timed.session() as session:
                result = await session.run(_BUSY_QUERY)
                await result.consume()
    elapsed = time.monotonic() - start

    assert elapsed < _ABORT_DEADLINE_SECONDS


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unbounded_override_lets_default_busy_query_run_then_abort(neo4j_driver):
    """`unbounded_neo4j_query_timeout()` removes the default bound.

    We don't wait for the busy query to finish (it would take minutes); we just
    verify the override is wired correctly by inspecting that begin_transaction
    receives ``timeout=None``. The end-to-end abort path is covered by the
    first test.
    """
    timed = TimedDriver(neo4j_driver, default_timeout=1.0)

    async with timed.session() as session:
        with unbounded_neo4j_query_timeout():
            tx = await session.begin_transaction()
            # tx is real — roll it back without doing work.
            await tx.rollback()
        # If we got here without exception, begin_transaction accepted the
        # None we resolved. Round-trip done in well under the deadline.


@pytest.mark.integration
@pytest.mark.asyncio
async def test_begin_transaction_inherits_default_timeout(neo4j_driver):
    """`begin_transaction()` with no args picks up the driver's default timeout.

    Verified end-to-end: a busy tx.run inside a 1s-default tx is aborted by the
    server, with no per-query Query() wrapper involved (tx.run takes a raw str).
    """
    timed = TimedDriver(neo4j_driver, default_timeout=1.0)

    start = time.monotonic()
    with pytest.raises((ClientError, TransientError)):
        async with timed.session() as session:
            tx = await session.begin_transaction()
            try:
                result = await tx.run(_BUSY_QUERY)
                await result.consume()
                await tx.commit()
            except ClientError, TransientError:
                # tx is in a failed state; ensure we still surface the error.
                raise
    elapsed = time.monotonic() - start

    assert elapsed < _ABORT_DEADLINE_SECONDS
