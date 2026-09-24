"""The habit-completion window reads, against both ``completed_at`` storage shapes.

``completed_at`` is written as an ISO **string** by the only writer there is, but
the writer decides the storage type, not the reader. A window read that compares
the stored value against a bound of the other type drops the row silently — Neo4j
orders across types before it compares values — which reads as a missing
completion (a shorter streak, an empty calendar day, a smaller export), never as
an error.

Every windowed read here goes through ``find_by_date_range``, which compares the
stored value's calendar day on both sides and orders by the same normalised
value. This file seeds one completion in each shape inside the window plus one
string outside it, and asserts that each of the three reads returns exactly the
two in-window rows, in chronological order.

The NATIVE row is seeded with raw Cypher because no production writer makes that
shape; the in-window string row goes through ``record_completion`` and the
out-of-window one through ``record_completions_bulk`` — the two production doors.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta, timezone

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.activity_backends import HabitsBackend
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.habit.completion import HabitCompletion
from core.models.habit.habit import Habit
from core.services.habits.habits_completion_service import HabitsCompletionService

USER = "user_completion_range"
HABIT = "habit.completion_range"
NATIVE_UID = "hc.range_native"

TODAY = date.today()
# The native row is the LATER of the two in-window rows, so a type-banded order
# (every string before every temporal, or the reverse) is distinguishable from a
# chronological one in at least one direction the test pins.
STRING_AT = datetime.combine(TODAY, time(hour=8))
NATIVE_AT = datetime.combine(TODAY, time(hour=9))
OUTSIDE_AT = datetime.combine(TODAY - timedelta(days=10), time(hour=8))


async def _seed_native_completion(neo4j_driver) -> None:
    """A completion whose ``completed_at`` is a native Neo4j ``datetime()``.

    Raw Cypher on purpose: no production writer persists this shape, and the
    point is to prove the reads survive one that does.
    """
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (u:User {uid: $user_uid})
            CREATE (hc:HabitCompletion {uid: $uid, user_uid: $user_uid,
                habit_uid: $habit_uid, created_at: $at, updated_at: $at})
            SET hc.completed_at = datetime($at)
            MERGE (u)-[:OWNS]->(hc)
            """,
            user_uid=USER,
            uid=NATIVE_UID,
            habit_uid=HABIT,
            at=NATIVE_AT.isoformat(),
        )
        await result.consume()


@pytest.mark.asyncio
@pytest.mark.integration
class TestHabitCompletionRangeReads:
    @pytest_asyncio.fixture
    async def seeded(self, neo4j_driver, clean_neo4j):
        habits_backend = HabitsBackend(
            neo4j_driver, NeoLabel.HABIT, Habit, base_label=NeoLabel.ENTITY
        )
        completions_backend = UniversalNeo4jBackend[HabitCompletion](
            neo4j_driver, NeoLabel.HABIT_COMPLETION, HabitCompletion
        )
        created = await habits_backend.create(
            Habit(uid=HABIT, user_uid=USER, entity_type=EntityType.HABIT, title="Range")
        )
        assert created.is_ok, created
        service = HabitsCompletionService(habits_backend, completions_backend)

        outside = await service.record_completions_bulk([HABIT], USER, completed_at=OUTSIDE_AT)
        assert outside.is_ok and len(outside.value) == 1, outside
        string_row = await service.record_completion(HABIT, USER, completed_at=STRING_AT)
        assert string_row.is_ok, string_row
        await _seed_native_completion(neo4j_driver)

        async with neo4j_driver.session() as session:
            result = await session.run(
                "MATCH (hc:HabitCompletion) RETURN hc.uid AS uid, valueType(hc.completed_at) AS t"
            )
            shapes = {r["uid"]: r["t"] async for r in result}
        # The premise: both storage shapes are really in the graph.
        assert shapes[NATIVE_UID].startswith("ZONED DATETIME"), shapes
        assert shapes[string_row.value.uid].startswith("STRING"), shapes

        return service, string_row.value.uid, outside.value[0].uid

    async def test_ranged_read_returns_both_shapes_newest_first(self, seeded):
        service, string_uid, _ = seeded

        result = await service.get_completions_for_habit(
            HABIT, start_date=TODAY - timedelta(days=2), end_date=TODAY
        )

        assert result.is_ok, result
        # Both in-window rows, the out-of-window one excluded, and chronological
        # across the type split: the native 09:00 row before the string 08:00 one.
        assert [c.uid for c in result.value] == [NATIVE_UID, string_uid]

    async def test_today_view_counts_both_shapes(self, seeded):
        service, _, _ = seeded

        result = await service.get_today_completions(USER)

        assert result.is_ok, result
        assert len(result.value) == 1
        entry = result.value[0]
        assert entry["completions_today"] == 2
        assert entry["latest_completion"].uid == NATIVE_UID

    async def test_export_window_carries_both_shapes_oldest_first(self, seeded):
        service, string_uid, _ = seeded

        result = await service.export_completion_history(
            USER, start_date=TODAY - timedelta(days=2), end_date=TODAY, format="json"
        )

        assert result.is_ok, result
        assert [row["uid"] for row in json.loads(result.value)] == [string_uid, NATIVE_UID]

    async def test_unwindowed_reads_carry_every_row(self, seeded):
        """No range at all: the full history, both shapes, still in order."""
        service, string_uid, outside_uid = seeded

        history = await service.get_all_completions_for_habit(HABIT)
        exported = await service.export_completion_history(USER, format="json")

        assert history.is_ok, history
        assert [c.uid for c in history.value] == [NATIVE_UID, string_uid, outside_uid]
        assert exported.is_ok, exported
        assert [row["uid"] for row in json.loads(exported.value)] == [
            outside_uid,
            string_uid,
            NATIVE_UID,
        ]

    async def test_offset_bearing_strings_order_by_instant_not_wall_clock(
        self, seeded, neo4j_driver
    ):
        """An ISO string with a UTC offset orders by the instant it names.

        ``track_habit`` passes the request's ISO text through ``fromisoformat``,
        so an offset reaches the stored string. String order is wall-clock order:
        ``10:00+02:00`` (08:00 UTC) sorts after ``09:00+00:00`` (09:00 UTC),
        although it is an hour earlier. Both rows go through the production
        writers, on a habit of their own.
        """
        service, _, _ = seeded
        habit_uid = "habit.completion_range_offsets"
        created = await service.habits_backend.create(
            Habit(uid=habit_uid, user_uid=USER, entity_type=EntityType.HABIT, title="Offsets")
        )
        assert created.is_ok, created
        earlier = datetime.combine(TODAY, time(hour=10), tzinfo=timezone(timedelta(hours=2)))
        later = datetime.combine(TODAY, time(hour=9), tzinfo=UTC)

        first = await service.record_completion(habit_uid, USER, completed_at=earlier)
        second = await service.record_completions_bulk([habit_uid], USER, completed_at=later)
        assert first.is_ok, first
        assert second.is_ok and len(second.value) == 1, second

        result = await service.get_completions_for_habit(
            habit_uid, start_date=TODAY, end_date=TODAY
        )

        assert result.is_ok, result
        assert [c.uid for c in result.value] == [second.value[0].uid, first.value.uid]
