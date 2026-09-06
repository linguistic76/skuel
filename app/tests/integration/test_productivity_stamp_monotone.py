"""``last_completion_at`` holds the LATEST completion moment, whatever order they arrive in.

Until the born-completed create doors started publishing, every ``occurred_at`` reaching
:meth:`CrossDomainBackend.stamp_productivity_completion` was ``now``, so a plain
``SET analytics.last_completion_at = datetime($occurred_at)`` was correct by accident:
moments arrived in the order they happened.

They no longer do. A ``- [x] … ✅ 2026-03-04`` line publishes ``TaskCompleted`` with
March 4th as its ``occurred_at``, and a vault sync hands those to the graph in FILE
order, not chronological order. An assignment would let ingesting a March completion
after an April one move "when did this user most recently complete something" backward.

This has to be driven through the real Cypher: the ordering lives in the statement, and
a Python-side assertion would pass against the broken write. The sibling counter node
(:meth:`upsert_habit_analytics` / :meth:`upsert_event_analytics`) is pinned too — its
``ON CREATE`` never writes ``last_*``, so the second completion is always comparing
against null, which is the arm a naive ``<`` comparison drops.

``first_completion_at`` was already a ``coalesce`` and is asserted to stay put.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

APRIL = "2026-04-10T09:00:00"
MARCH = "2026-03-04T17:30:00"

PRODUCTIVITY_USER = "user_monotone_productivity"
ATTENDANCE_USER = "user_monotone_attendance"


def _utc(moment: str) -> datetime:
    return datetime.fromisoformat(moment).replace(tzinfo=UTC)


async def _productivity(neo4j_driver, user_uid: str):
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (a:ProductivityAnalytics {user_uid: $user_uid})
            RETURN a.first_completion_at AS first, a.last_completion_at AS last
            """,
            user_uid=user_uid,
        )
        return await result.single()


async def _attendance(neo4j_driver, user_uid: str):
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (a:EventAnalytics {user_uid: $user_uid})
            RETURN a.first_attendance_at AS first, a.last_attendance_at AS last,
                   a.events_attended AS attended
            """,
            user_uid=user_uid,
        )
        return await result.single()


@pytest.mark.asyncio
@pytest.mark.integration
class TestProductivityStampIsMonotone:
    async def test_an_out_of_order_completion_does_not_move_last_backward(
        self, neo4j_driver, clean_neo4j
    ) -> None:
        backend = CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver))

        assert (await backend.stamp_productivity_completion(PRODUCTIVITY_USER, APRIL)).is_ok
        assert (await backend.stamp_productivity_completion(PRODUCTIVITY_USER, MARCH)).is_ok

        row = await _productivity(neo4j_driver, PRODUCTIVITY_USER)
        assert row["last"].to_native() == _utc(APRIL)
        # first is a coalesce — the April write created it and March must not move it.
        assert row["first"].to_native() == _utc(APRIL)

    async def test_a_later_completion_still_advances_last(self, neo4j_driver, clean_neo4j) -> None:
        backend = CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver))

        assert (await backend.stamp_productivity_completion(PRODUCTIVITY_USER, MARCH)).is_ok
        assert (await backend.stamp_productivity_completion(PRODUCTIVITY_USER, APRIL)).is_ok

        row = await _productivity(neo4j_driver, PRODUCTIVITY_USER)
        assert row["last"].to_native() == _utc(APRIL)
        assert row["first"].to_native() == _utc(MARCH)


@pytest.mark.asyncio
@pytest.mark.integration
class TestCounterAnalyticsLastStampIsMonotone:
    async def test_the_null_arm_is_covered_and_out_of_order_does_not_move_last(
        self, neo4j_driver, clean_neo4j
    ) -> None:
        """``ON CREATE`` writes no ``last_attendance_at``, so the second call compares
        against null — the arm a bare ``<`` would drop, leaving the stamp null forever."""
        backend = CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver))

        assert (await backend.upsert_event_analytics(ATTENDANCE_USER, APRIL)).is_ok
        row = await _attendance(neo4j_driver, ATTENDANCE_USER)
        assert row["last"] is None

        assert (await backend.upsert_event_analytics(ATTENDANCE_USER, MARCH)).is_ok
        row = await _attendance(neo4j_driver, ATTENDANCE_USER)
        assert row["last"].to_native() == _utc(MARCH)

        assert (await backend.upsert_event_analytics(ATTENDANCE_USER, APRIL)).is_ok
        row = await _attendance(neo4j_driver, ATTENDANCE_USER)
        assert row["last"].to_native() == _utc(APRIL)

        assert (await backend.upsert_event_analytics(ATTENDANCE_USER, MARCH)).is_ok
        row = await _attendance(neo4j_driver, ATTENDANCE_USER)
        assert row["last"].to_native() == _utc(APRIL)
        assert row["attended"] == 4
