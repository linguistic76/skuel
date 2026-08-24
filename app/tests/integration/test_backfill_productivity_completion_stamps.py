"""The productivity stamp backfill writes the right stamps on the right nodes — and only those.

Five ways this migration could go wrong, each exercised against a real graph:

1. **Moving an existing stamp.** The fill is a ``coalesce`` on each stamp, so
   the handler's real moment always wins. The seed contains a node with both
   stamps set beside completed tasks whose days disagree with them, and both
   are asserted byte-identical after the write.
2. **Crossing the stamp that exists.** A filled ``last`` must not order before
   an existing ``first`` (and vice versa) — a day-grained reconstruction sits
   at midnight, and the real stamp on the same day sits later. The guard
   substitutes the existing stamp, so ``first <= last`` holds after the write.
3. **Inventing a moment.** A node with null stamps and no stamped completed
   task stays null. Truth over coverage.
4. **Wrong storage shape.** The handler writes ``datetime(...)`` — ZONED
   DATETIME. So must this, and it must read a native-``date`` stamp as the same
   day as its ISO-string twin (the writer decides the storage type).
5. **Leaving the retired count behind**, anywhere — including on a node whose
   ``:User`` row is gone and which no per-user census would reach.

Plus: the census writes nothing, and a second run is a no-op.

The queries are **imported from the script**, not retyped. A copy would drift,
and then this file would be testing a query that never runs. The classification
the census prints is pinned DB-free in
``tests/unit/scripts/test_backfill_productivity_completion_stamps.py``.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
import pytest_asyncio

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import backfill_productivity_completion_stamps as backfill  # type: ignore[import-not-found]

from core.models.enums.entity_enums import EntityStatus

VAULT = "user_stampfill_vault"  # completions, no node
LEGACY = "user_stampfill_legacy"  # both stamps + retired count; stamps must not move
FIRST_ONLY = "user_stampfill_first_only"  # first set (17:30 on the max day); last null
LAST_ONLY = "user_stampfill_last_only"  # last set, EARLIER than the min day; first null
IDLE = "user_stampfill_idle"  # node with null stamps, no tasks
NATIVE = "user_stampfill_native"  # stamp stored as a native date()
ORPHAN = "user_stampfill_orphan"  # analytics node, no :User row

TODAY = date.today()


def _day(offset: int) -> str:
    return (TODAY - timedelta(days=offset)).isoformat()


async def _seed_task(
    neo4j_driver,
    user_uid: str,
    task_uid: str,
    completion_date: str | None,
    *,
    status: EntityStatus = EntityStatus.COMPLETED,
    temporal_stamp: bool = False,
) -> None:
    stamp_clause = ""
    if completion_date is not None:
        stamp_clause = (
            "SET t.completion_date = date($completion_date)"
            if temporal_stamp
            else "SET t.completion_date = $completion_date"
        )
    async with neo4j_driver.session() as session:
        result = await session.run(
            f"""
            MATCH (u:User {{uid: $user_uid}})
            MERGE (t:Entity:Task {{uid: $task_uid}})
            SET t.user_uid = $user_uid, t.entity_type = 'task', t.title = $task_uid,
                t.status = $status
            {stamp_clause}
            MERGE (u)-[:OWNS]->(t)
            """,
            user_uid=user_uid,
            task_uid=task_uid,
            status=status.value,
            completion_date=completion_date,
        )
        await result.consume()


async def _seed_node(neo4j_driver, user_uid: str, set_clause: str) -> None:
    async with neo4j_driver.session() as session:
        result = await session.run(
            f"MERGE (a:ProductivityAnalytics {{user_uid: $user_uid}}) {set_clause}",
            user_uid=user_uid,
        )
        await result.consume()


async def _node(neo4j_driver, user_uid: str):
    """``(first, last, retired_count, valueType(first), valueType(last))`` or ``None``."""
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (a:ProductivityAnalytics {user_uid: $user_uid})
            RETURN a.first_completion_at AS first, a.last_completion_at AS last,
                   a.tasks_completed AS retired,
                   valueType(a.first_completion_at) AS first_type,
                   valueType(a.last_completion_at) AS last_type
            """,
            user_uid=user_uid,
        )
        return await result.single()


def _midnight_utc(day: str):
    from datetime import UTC, datetime

    return datetime.fromisoformat(day).replace(tzinfo=UTC)


@pytest.mark.asyncio
@pytest.mark.integration
class TestBackfillProductivityCompletionStamps:
    @pytest_asyncio.fixture
    async def seeded(self, neo4j_driver, clean_neo4j):
        # VAULT: three completions, no node. Both stamps derive; a node is created.
        for offset in (10, 5, 1):
            await _seed_task(neo4j_driver, VAULT, f"task.vault_{offset}", _day(offset))
        # An open task and an unstamped completed task — neither reaches min/max.
        await _seed_task(
            neo4j_driver, VAULT, "task.vault_open", _day(0), status=EntityStatus.ACTIVE
        )
        await _seed_task(neo4j_driver, VAULT, "task.vault_unstamped", None)

        # LEGACY: both stamps set, days that disagree with the tasks, retired count.
        await _seed_node(
            neo4j_driver,
            LEGACY,
            "SET a.first_completion_at = datetime('2026-01-05T09:00:00'), "
            "a.last_completion_at = datetime('2026-06-11T17:30:00'), a.tasks_completed = 9",
        )
        await _seed_task(neo4j_driver, LEGACY, "task.legacy_a", "2026-02-01")
        await _seed_task(neo4j_driver, LEGACY, "task.legacy_b", "2026-08-01")

        # FIRST_ONLY: first set at 17:30 on the same day as the latest completed
        # task. A midnight fill for last would order BEFORE first.
        await _seed_node(
            neo4j_driver, FIRST_ONLY, "SET a.first_completion_at = datetime('2026-06-11T17:30:00')"
        )
        await _seed_task(neo4j_driver, FIRST_ONLY, "task.first_only_a", "2026-05-01")
        await _seed_task(neo4j_driver, FIRST_ONLY, "task.first_only_b", "2026-06-11")

        # LAST_ONLY: last set EARLIER than the earliest completed task still in
        # the graph (its early completions were reopened or deleted since). A
        # raw fill for first would order AFTER last.
        await _seed_node(
            neo4j_driver, LAST_ONLY, "SET a.last_completion_at = datetime('2026-02-20T08:00:00')"
        )
        await _seed_task(neo4j_driver, LAST_ONLY, "task.last_only_a", "2026-03-01")

        # IDLE: node, null stamps, retired count, no tasks — unfillable.
        await _seed_node(neo4j_driver, IDLE, "SET a.tasks_completed = 0")

        # NATIVE: the stamp stored as a native date() — same day as an ISO twin.
        await _seed_task(neo4j_driver, NATIVE, "task.native_a", "2026-07-04", temporal_stamp=True)
        await _seed_task(neo4j_driver, NATIVE, "task.native_b", "2026-07-09")

        # ORPHAN: a node with no :User row, still carrying the retired count.
        await _seed_node(neo4j_driver, ORPHAN, "SET a.tasks_completed = 4")

    async def test_the_census_reports_every_shape_and_writes_nothing(self, neo4j_driver, seeded):
        plans, retired = await backfill.census(neo4j_driver)
        by_user = {p.user_uid: p for p in plans}

        assert set(by_user) == {VAULT, LEGACY, FIRST_ONLY, LAST_ONLY, IDLE, NATIVE}, (
            "in scope = has a node or owns a stamped completed task; the orphan has no User row"
        )
        assert by_user[VAULT].creates_node
        assert by_user[VAULT].fill_first == _day(10) and by_user[VAULT].fill_last == _day(1)
        assert not by_user[LEGACY].fill_first and not by_user[LEGACY].fill_last
        assert by_user[LEGACY].drops_retired_count
        assert (
            by_user[FIRST_ONLY].fill_first is None and by_user[FIRST_ONLY].fill_last == "2026-06-11"
        )
        assert (
            by_user[LAST_ONLY].fill_first == "2026-03-01" and by_user[LAST_ONLY].fill_last is None
        )
        assert by_user[IDLE].unfillable and by_user[IDLE].drops_retired_count
        assert by_user[NATIVE].fill_first == "2026-07-04", "a native date() projects to its day"
        assert retired == 3, "LEGACY + IDLE + the orphan — counted off the label"

        exit_code = await backfill.run_backfill(neo4j_driver, confirm=False)
        assert exit_code == 0
        assert await _node(neo4j_driver, VAULT) is None, "census only — no node created"
        assert (await _node(neo4j_driver, LEGACY))["retired"] == 9, "census only — nothing dropped"

    async def test_the_write_fills_only_nulls_in_the_writers_shape(self, neo4j_driver, seeded):
        exit_code = await backfill.run_backfill(neo4j_driver, confirm=True)
        assert exit_code == 0

        vault = await _node(neo4j_driver, VAULT)
        assert vault is not None, "the vault door's user gets a node"
        assert vault["first"].to_native() == _midnight_utc(_day(10))
        assert vault["last"].to_native() == _midnight_utc(_day(1))
        assert vault["first_type"].startswith("ZONED DATETIME"), "the handler's storage type"
        assert vault["last_type"].startswith("ZONED DATETIME")

        legacy = await _node(neo4j_driver, LEGACY)
        assert legacy["first"].to_native() == _midnight_utc("2026-01-05T09:00:00")
        assert legacy["last"].to_native() == _midnight_utc("2026-06-11T17:30:00")
        assert legacy["retired"] is None

        native = await _node(neo4j_driver, NATIVE)
        assert native["first"].to_native() == _midnight_utc("2026-07-04")
        assert native["last"].to_native() == _midnight_utc("2026-07-09")

    async def test_a_filled_stamp_never_crosses_the_one_that_exists(self, neo4j_driver, seeded):
        await backfill.run_backfill(neo4j_driver, confirm=True)

        first_only = await _node(neo4j_driver, FIRST_ONLY)
        assert first_only["first"].to_native() == _midnight_utc("2026-06-11T17:30:00"), "untouched"
        assert first_only["last"] == first_only["first"], (
            "the latest completed day is the day of the existing first stamp; a midnight "
            "fill would order before it, so the guard substitutes the existing stamp"
        )

        last_only = await _node(neo4j_driver, LAST_ONLY)
        assert last_only["last"].to_native() == _midnight_utc("2026-02-20T08:00:00"), "untouched"
        assert last_only["first"] == last_only["last"], (
            "the earliest completed day still in the graph is after the existing last stamp"
        )

    async def test_a_node_with_nothing_to_derive_from_stays_null(self, neo4j_driver, seeded):
        await backfill.run_backfill(neo4j_driver, confirm=True)

        idle = await _node(neo4j_driver, IDLE)
        assert idle["first"] is None and idle["last"] is None, "no invented moment"
        assert idle["retired"] is None, "but the retired count still goes"

    async def test_the_retired_count_is_dropped_even_off_an_orphaned_node(
        self, neo4j_driver, seeded
    ):
        await backfill.run_backfill(neo4j_driver, confirm=True)

        orphan = await _node(neo4j_driver, ORPHAN)
        assert orphan is not None
        assert orphan["retired"] is None

    async def test_a_second_run_is_a_no_op(self, neo4j_driver, seeded):
        assert await backfill.run_backfill(neo4j_driver, confirm=True) == 0
        snapshot = {u: await _node(neo4j_driver, u) for u in (VAULT, LEGACY, FIRST_ONLY, LAST_ONLY)}

        plans, retired = await backfill.census(neo4j_driver)
        assert retired == 0
        assert not any(p.fill_first or p.fill_last or p.drops_retired_count for p in plans)

        assert await backfill.run_backfill(neo4j_driver, confirm=True) == 0
        for user_uid, before in snapshot.items():
            after = await _node(neo4j_driver, user_uid)
            assert (after["first"], after["last"]) == (before["first"], before["last"])
