"""Why the adherence fetch carries no date predicate, proven against a real graph.

``HabitCompletion.completed_at`` is written as an ISO **string** by the only
writer there is (``UniversalNeo4jBackend.create`` ``isoformat()``s what the DTO
carries, reached from exactly two call sites in ``HabitsCompletionService``). The
writer decides the storage type, not the reader — and a reader that assumes the
current writer's choice fails silently when it changes, which is the one failure
mode a metric can least afford: it reads as "this user was less consistent",
never as an error.

This file pins the mechanism that decision rests on. ``find_by`` binds a
``datetime`` bound as an ISO string (``convert_value_for_neo4j``), so a range
predicate compares a **string** against whatever ``completed_at`` holds. Neo4j
orders values across types before it compares them, so a natively-typed
``completed_at`` satisfies neither end of that range and the row disappears from
a query that looks entirely correct.

If Neo4j ever changes those comparison semantics, the first assertion here fails
and the whole justification can be revisited — which is the point of pinning a
mechanism rather than describing one.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
import pytest_asyncio

USER = "user_temporal_split"
HABIT = "habit.temporal_split"

NOW = datetime.now()
LOW = datetime.combine((NOW - timedelta(days=29)).date(), time.min)
HIGH = datetime.combine(NOW.date(), time.max)


async def _seed_completion(neo4j_driver, uid: str, *, temporal_stamp: bool) -> None:
    """One completion at the writer's shape, stamped as a string or as a temporal."""
    stamp = (
        "SET hc.completed_at = datetime($completed_at)"
        if temporal_stamp
        else "SET hc.completed_at = $completed_at"
    )
    async with neo4j_driver.session() as session:
        result = await session.run(
            f"""
            MATCH (u:User {{uid: $user_uid}})
            MERGE (hc:HabitCompletion {{uid: $uid}})
            SET hc.user_uid = $user_uid,
                hc.habit_uid = $habit_uid,
                hc.created_at = $completed_at,
                hc.updated_at = $completed_at
            {stamp}
            MERGE (u)-[:OWNS]->(hc)
            """,
            user_uid=USER,
            uid=uid,
            habit_uid=HABIT,
            completed_at=NOW.isoformat(),
        )
        await result.consume()


@pytest.mark.asyncio
@pytest.mark.integration
class TestHabitCompletionTemporalSplit:
    @pytest_asyncio.fixture
    async def completions_backend(self, neo4j_driver, clean_neo4j):
        from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
        from core.models.enums.neo_labels import NeoLabel
        from core.models.habit.completion import HabitCompletion

        return UniversalNeo4jBackend[HabitCompletion](
            neo4j_driver, NeoLabel.HABIT_COMPLETION, HabitCompletion
        )

    @pytest_asyncio.fixture
    async def seeded(self, neo4j_driver, completions_backend):
        """Two completions on the same instant, differing only in storage type."""
        await _seed_completion(neo4j_driver, "hc.split_string", temporal_stamp=False)
        await _seed_completion(neo4j_driver, "hc.split_temporal", temporal_stamp=True)
        return completions_backend

    async def test_a_date_bounded_find_by_silently_drops_a_temporally_typed_row(self, seeded):
        """The hazard, reproduced — this is why the adherence fetch has no range.

        Both rows carry the same instant and both are inside the bounds. Only the
        string-stamped one comes back: the bound reaches Cypher as a string, and
        a temporal value compared against a string is not "outside the range", it
        is not comparable at all. No error, no warning, one row fewer.
        """
        result = await seeded.find_by(
            habit_uid=HABIT, completed_at__gte=LOW, completed_at__lte=HIGH, limit=100
        )

        assert result.is_ok
        uids = {c.uid for c in result.value}
        assert uids == {"hc.split_string"}, (
            "if this now returns both rows, Neo4j's cross-type comparison changed "
            "and the no-date-predicate decision can be revisited"
        )

    async def test_the_unbounded_paged_fetch_returns_both(self, seeded):
        """The shape the adherence path uses: no temporal predicate, sorted by uid.

        ``uid`` is a plain string on every row whatever ``completed_at`` holds, so
        the ordering that makes paging deterministic cannot itself be skewed by
        the storage split.
        """
        result = await seeded.find_by(habit_uid=HABIT, limit=1000, sort_by="uid")

        assert result.is_ok
        assert {c.uid for c in result.value} == {"hc.split_string", "hc.split_temporal"}

    async def test_both_rows_arrive_as_python_datetimes_for_the_window_filter(self, seeded):
        """Why filtering in Python is type-tolerant *by construction*.

        The mapper normalises both storage forms on the way out, so by the time
        ``_calculate_consistency_from_completions`` compares
        ``completed_at.date()`` there is only one type left to compare.
        """
        result = await seeded.find_by(habit_uid=HABIT, limit=1000, sort_by="uid")

        assert result.is_ok
        assert len(result.value) == 2
        for completion in result.value:
            assert isinstance(completion.completed_at, datetime)
            assert completion.completed_at.date() == NOW.date()
