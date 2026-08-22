"""The completion-stamp backfill freezes the proxy — on the right rows, in the right shape.

Three ways this migration could go wrong, each exercised against a real graph:

1. **Over-matching.** The write is an unconditional ``SET`` over whatever the
   ``WHERE`` matches. A clause that missed the NULL guard would overwrite a real
   completion date with a later ``updated_at`` and report success. So the seed
   contains rows it must NOT touch — an already-stamped completion and an
   unfinished task — and they are asserted unchanged.
2. **Wrong storage shape.** Every completion field round-trips through
   ``to_neo4j_node``/``from_neo4j_node`` as an ISO **string**. Writing a native
   Neo4j DATE/DATETIME would read back and still be wrong, so the assertions
   check ``valueType()``, not just the value. ``updated_at`` is a live mix of
   STRING and ZONED DATETIME (measured on AuraDB ``d2d160c4``), and both are
   seeded — the projection must flatten them to one shape.
3. **Non-idempotence.** A second run must be a no-op, not a re-approximation.

The queries are **imported from the script**, not retyped. A copy would drift,
and then this file would be testing a query that never runs. The script's
DB-free invariants (spec coverage, field names) are pinned in
``tests/unit/scripts/test_backfill_activity_completion_stamps.py`` so they run
on every CI job, not only the path-filtered integration one.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import pytest

# scripts/ has no __init__.py — add it to sys.path for import
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import backfill_activity_completion_stamps as migration  # type: ignore[import-not-found]

pytestmark = pytest.mark.asyncio(loop_scope="session")

STAMPED = "2026-04-02"
EDITED_AT = "2026-08-20T11:22:33.444555"  # later than STAMPED — the re-dating risk
UNSTAMPED_AT = "2026-06-15T08:09:10.111213"
_UIDS = [
    "task_bf_unstamped",
    "task_bf_native_dt",
    "task_bf_already_stamped",
    "task_bf_active",
    "goal_bf_unstamped",
    "choice_bf_unstamped",
    "principle_bf_illegal",
]


@pytest.fixture
async def seeded(neo4j_driver):
    """One row per way ``updated_at`` and the stamp can combine."""
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (:Entity:Task {uid: $t_unstamped, entity_type: 'task',
                status: 'completed', updated_at: $unstamped_at})
            CREATE (:Entity:Task {uid: $t_native, entity_type: 'task',
                status: 'completed', updated_at: datetime($unstamped_at)})
            CREATE (:Entity:Task {uid: $t_stamped, entity_type: 'task',
                status: 'completed', completion_date: $stamped, updated_at: $edited_at})
            CREATE (:Entity:Task {uid: $t_active, entity_type: 'task',
                status: 'active', updated_at: $edited_at})
            CREATE (:Entity:Goal {uid: $g_unstamped, entity_type: 'goal',
                status: 'completed', updated_at: $unstamped_at})
            CREATE (:Entity:Choice {uid: $c_unstamped, entity_type: 'choice',
                status: 'completed', updated_at: $unstamped_at})
            CREATE (:Entity:Principle {uid: $p_illegal, entity_type: 'principle',
                status: 'completed', updated_at: $unstamped_at})
            """,
            t_unstamped=_UIDS[0],
            t_native=_UIDS[1],
            t_stamped=_UIDS[2],
            t_active=_UIDS[3],
            g_unstamped=_UIDS[4],
            c_unstamped=_UIDS[5],
            p_illegal=_UIDS[6],
            stamped=STAMPED,
            edited_at=EDITED_AT,
            unstamped_at=UNSTAMPED_AT,
        )
    yield
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n:Entity) WHERE n.uid IN $uids DETACH DELETE n", uids=_UIDS)


def _spec(entity_type_value: str):
    return next(s for s in migration.SPECS if s.entity_type.value == entity_type_value)


async def _run_all(driver) -> int:
    """Drive the real backfill query for every spec; return rows written."""
    written = 0
    for spec in migration.SPECS:
        records, _, _ = await driver.execute_query(
            migration.backfill_query(spec), completed=migration.COMPLETED
        )
        written += int(records[0]["n"])
    return written


async def _props(driver, uid: str, field: str) -> tuple[object, str]:
    """One property's value and its Neo4j storage type.

    ``valueType()`` is never null for a matched node — an absent property reports
    ``"NULL"`` — so the shape assertions can read it unconditionally.
    """
    records, _, _ = await driver.execute_query(
        f"MATCH (n:Entity {{uid: $uid}}) RETURN n.{field} AS value, valueType(n.{field}) AS vt",
        uid=uid,
    )
    assert records, f"{uid} is not in the graph"
    return records[0]["value"], str(records[0]["vt"])


async def test_freezes_only_the_unstamped_completions(neo4j_driver, seeded):
    census = migration.census_query(_spec("task"))
    before, _, _ = await neo4j_driver.execute_query(census, completed=migration.COMPLETED)
    # Positive control: the census can see the seed. Without it a query that
    # matched nothing would make every assertion below trivially true.
    assert int(before[0]["fillable"]) >= 2

    written = await _run_all(neo4j_driver)
    assert written >= 4  # 2 tasks + 1 goal + 1 choice

    # Frozen from a string updated_at, truncated to the date the field stores.
    value, vt = await _props(neo4j_driver, _UIDS[0], "completion_date")
    assert value == UNSTAMPED_AT[:10]
    assert vt.startswith("STRING"), f"stored as {vt} — writers store ISO strings"
    assert date.fromisoformat(value) == date(2026, 6, 15)

    # Same result from a NATIVE ZONED DATETIME updated_at — one shape out.
    value, vt = await _props(neo4j_driver, _UIDS[1], "completion_date")
    assert value == UNSTAMPED_AT[:10]
    assert vt.startswith("STRING")

    # The control: a real completion date is never overwritten by a later touch.
    value, _ = await _props(neo4j_driver, _UIDS[2], "completion_date")
    assert value == STAMPED, "an already-stamped completion was re-dated from updated_at"

    # The other control: unfinished work is not given a completion date.
    value, _ = await _props(neo4j_driver, _UIDS[3], "completion_date")
    assert value is None


async def test_each_domain_fills_its_own_canonical_field(neo4j_driver, seeded):
    await _run_all(neo4j_driver)

    value, vt = await _props(neo4j_driver, _UIDS[4], "achieved_date")
    assert value == UNSTAMPED_AT[:10]
    assert vt.startswith("STRING")

    # Choice stamps a datetime — the full moment survives, not just the day.
    value, vt = await _props(neo4j_driver, _UIDS[5], "completed_at")
    assert value == UNSTAMPED_AT
    assert vt.startswith("STRING")
    assert datetime.fromisoformat(value) == datetime(2026, 6, 15, 8, 9, 10, 111213)


async def test_illegal_completed_principle_is_reported_not_stamped(neo4j_driver, seeded):
    """COMPLETED is not a valid Principle status — there is nothing to freeze."""
    records, _, _ = await neo4j_driver.execute_query(
        migration.ILLEGAL_COMPLETED, completed=migration.COMPLETED
    )
    assert int(records[0]["n"]) >= 1

    await _run_all(neo4j_driver)

    props, _, _ = await neo4j_driver.execute_query(
        "MATCH (n:Entity {uid: $uid}) RETURN keys(n) AS keys", uid=_UIDS[6]
    )
    assert "completed_at" not in props[0]["keys"]
    assert "completion_date" not in props[0]["keys"]


async def test_second_run_is_a_no_op(neo4j_driver, seeded):
    """Idempotent: the freeze happens once, and re-running never re-approximates."""
    assert await _run_all(neo4j_driver) >= 4

    first, _ = await _props(neo4j_driver, _UIDS[0], "completion_date")
    assert await _run_all(neo4j_driver) == 0
    second, _ = await _props(neo4j_driver, _UIDS[0], "completion_date")
    assert second == first
