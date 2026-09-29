"""A bounded ``find_by`` over a mixed-shape instant column, proven against a real graph.

``HabitCompletion.completed_at`` is an instant (a ``datetime`` on the model).
The writer decides its storage type, not the reader: the CRUD door stores an
ISO **string**, a Cypher writer a **native** — and a reader that assumes one
writer's choice fails silently when another writes, which reads as "this user
was less consistent", never as an error.

``find_by`` binds a ``datetime`` bound as an ISO string (``convert_value_for_neo4j``).
Compared raw, a native ``completed_at`` against that string satisfies neither
end of the range. The range builder therefore compares an instant field as
instants on both sides — ``datetime(n.completed_at) >= datetime($bound)`` (the
type rule, ``comparable_property``) — and both shapes are inside it. This file
pins that, beside the two other shapes of the read: the unbounded paged fetch
and the mapper's normalisation.
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

    async def test_a_date_bounded_find_by_returns_both_storage_shapes(self, seeded, neo4j_driver):
        """Both rows carry the same instant and both are inside the bounds.

        Compared raw, the native row would drop out — a temporal compared with
        the string bound is not "outside the range", it is not comparable at all.
        The range reads both sides through ``datetime()``, so both come back.
        """
        async with neo4j_driver.session() as session:
            shapes = await session.run(
                "MATCH (hc:HabitCompletion {habit_uid: $habit}) "
                "RETURN hc.uid AS uid, valueType(hc.completed_at) AS type",
                habit=HABIT,
            )
            types = {row["uid"]: row["type"] for row in await shapes.data()}
        assert types == {
            "hc.split_string": "STRING NOT NULL",
            "hc.split_temporal": "ZONED DATETIME NOT NULL",
        }

        result = await seeded.find_by(
            habit_uid=HABIT, completed_at__gte=LOW, completed_at__lte=HIGH, limit=100
        )

        assert result.is_ok
        assert {c.uid for c in result.value} == {"hc.split_string", "hc.split_temporal"}

    async def test_the_unbounded_paged_fetch_returns_both(self, seeded):
        """The shape the adherence path uses: no temporal predicate, a total order.

        ``find_by_date_range`` with neither bound orders by the normalised
        ``completed_at`` and then ``uid``, a plain string on every row whatever
        ``completed_at`` holds, so the ordering that makes paging deterministic
        cannot itself be skewed by the storage split.
        """
        result = await seeded.find_by_date_range(
            start_date=None,
            end_date=None,
            date_field="completed_at",
            additional_filters={"habit_uid": HABIT},
            limit=1000,
        )

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
