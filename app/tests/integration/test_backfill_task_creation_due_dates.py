"""The task due-date backfill dates the right rows, with the right day, in the right shape.

Four ways this migration could go wrong, each exercised against a real graph:

1. **Over-matching.** The write is an unconditional ``SET`` over whatever the
   ``WHERE`` matches; a guard that missed either date field would overwrite a
   real deadline, or invent one beside a work date the user chose. So the seed
   holds rows it must NOT touch — a task with a due date, a task with only a
   scheduled date — asserted unchanged.
2. **Wrong day.** The rule is the creation day, except a completion day that
   came first (a historical ``✅`` line). Both branches are seeded, plus the
   "completed later" shape that must keep the creation day.
3. **Wrong storage shape.** ``due_date`` round-trips through the mappers as an
   ISO ``YYYY-MM-DD`` string; a native DATE would read back and still diverge
   from every app writer. ``created_at`` is seeded both as a string and as a
   native ZONED DATETIME — the projection must flatten both.
4. **Non-idempotence.** A second run must write nothing.

The queries are **imported from the script**, not retyped.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import backfill_task_creation_due_dates as migration  # type: ignore[import-not-found]

pytestmark = pytest.mark.asyncio(loop_scope="session")

CREATED_AT = "2026-09-09T19:02:55.625354"
EARLIER_DONE = "2026-07-01"
LATER_DONE = "2026-09-12"
DUE = "2026-09-30"
SCHEDULED = "2026-09-20"
_UIDS = [
    "task_bf_undated_draft",
    "task_bf_undated_native_created_at",
    "task_bf_done_earlier",
    "task_bf_done_later",
    "task_bf_has_due",
    "task_bf_has_scheduled",
]


@pytest.fixture
async def seeded(neo4j_driver):
    """One row per way the two date fields, created_at and completion_date combine."""
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (:Entity:Task {uid: $undated, entity_type: 'task',
                status: 'draft', created_at: $created_at})
            CREATE (:Entity:Task {uid: $native, entity_type: 'task',
                status: 'draft', created_at: datetime($created_at)})
            CREATE (:Entity:Task {uid: $earlier, entity_type: 'task',
                status: 'completed', created_at: $created_at, completion_date: $earlier_done})
            CREATE (:Entity:Task {uid: $later, entity_type: 'task',
                status: 'completed', created_at: $created_at, completion_date: $later_done})
            CREATE (:Entity:Task {uid: $has_due, entity_type: 'task',
                status: 'draft', created_at: $created_at, due_date: $due})
            CREATE (:Entity:Task {uid: $has_sched, entity_type: 'task',
                status: 'draft', created_at: $created_at, scheduled_date: $scheduled})
            """,
            undated=_UIDS[0],
            native=_UIDS[1],
            earlier=_UIDS[2],
            later=_UIDS[3],
            has_due=_UIDS[4],
            has_sched=_UIDS[5],
            created_at=CREATED_AT,
            earlier_done=EARLIER_DONE,
            later_done=LATER_DONE,
            due=DUE,
            scheduled=SCHEDULED,
        )
    yield
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n:Entity) WHERE n.uid IN $uids DETACH DELETE n", uids=_UIDS)


async def _run(driver) -> int:
    records, _, _ = await driver.execute_query(migration.BACKFILL_QUERY)
    return int(records[0]["n"])


async def _props(driver, uid: str, field: str) -> tuple[object, str]:
    """One property's value and its Neo4j storage type (``"NULL"`` when absent)."""
    records, _, _ = await driver.execute_query(
        f"MATCH (n:Entity {{uid: $uid}}) RETURN n.{field} AS value, valueType(n.{field}) AS vt",
        uid=uid,
    )
    assert records, f"{uid} is not in the graph"
    return records[0]["value"], str(records[0]["vt"])


async def test_dates_only_the_undated_by_the_creation_rule(neo4j_driver, seeded):
    # Positive control: the census sees the seed, so a query matching nothing
    # cannot make the assertions below trivially true.
    before, _, _ = await neo4j_driver.execute_query(migration.CENSUS_QUERY)
    assert int(before[0]["fillable"]) >= 4

    written = await _run(neo4j_driver)
    assert written >= 4

    # The creation day, stored as the ISO date string every app writer stores.
    value, vt = await _props(neo4j_driver, _UIDS[0], "due_date")
    assert value == CREATED_AT[:10]
    assert vt.startswith("STRING"), f"stored as {vt} — writers store ISO strings"

    # Same day, same shape, from a NATIVE ZONED DATETIME created_at.
    value, vt = await _props(neo4j_driver, _UIDS[1], "due_date")
    assert value == CREATED_AT[:10]
    assert vt.startswith("STRING")

    # A completion that came before the creation day is the day it was lived.
    value, _ = await _props(neo4j_driver, _UIDS[2], "due_date")
    assert value == EARLIER_DONE

    # Completed later: it was due on its creation day and finished after.
    value, _ = await _props(neo4j_driver, _UIDS[3], "due_date")
    assert value == CREATED_AT[:10]

    # Controls: a deadline is never overwritten, a work date never gets a
    # deadline invented beside it.
    value, _ = await _props(neo4j_driver, _UIDS[4], "due_date")
    assert value == DUE
    value, _ = await _props(neo4j_driver, _UIDS[5], "due_date")
    assert value is None
    value, _ = await _props(neo4j_driver, _UIDS[5], "scheduled_date")
    assert value == SCHEDULED


async def test_second_run_changes_nothing(neo4j_driver, seeded):
    assert await _run(neo4j_driver) >= 4
    after_first = [await _props(neo4j_driver, uid, "due_date") for uid in _UIDS]

    await _run(neo4j_driver)

    # Scoped to the seed: the shared container may hold other suites' undated
    # tasks, so the global count is not the claim — these rows are.
    assert [await _props(neo4j_driver, uid, "due_date") for uid in _UIDS] == after_first
    records, _, _ = await neo4j_driver.execute_query(
        f"MATCH (n:Entity) WHERE n.uid IN $uids AND {migration.UNDATED} RETURN count(*) AS n",
        uids=_UIDS,
    )
    assert int(records[0]["n"]) == 0, "a seeded row is still undated after two runs"
