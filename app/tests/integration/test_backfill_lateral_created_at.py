"""The lateral ``created_at`` backfill strips the literal and nothing else.

The migration runs an unconditional ``REMOVE r.created_at`` over whatever its
``WHERE`` clause matches. A clause that matched too widely would strip the
property from every edge in the graph and still print a cheerful "removed N" —
so the destructive statement is exercised here against a seeded graph that
deliberately contains edges it must NOT touch.

The queries are **imported from the script**, not retyped. A copy would drift,
and then this file would be testing a query that never runs.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backfill_lateral_created_at.py"


def _load_migration():
    """Import the migration module by path (``scripts/`` is not a package)."""
    spec = importlib.util.spec_from_file_location("backfill_lateral_created_at", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = _load_migration()

GOOD_STAMP = "2026-01-02T03:04:05.678901"
_UIDS = ["ku_bf_a", "ku_bf_b", "ku_bf_c", "ku_bf_d"]


@pytest.fixture
async def seeded(neo4j_driver):
    """Three edges: two literal-stamped, one legitimately stamped.

    The legitimate edge is the control — if the migration is over-broad it
    loses its stamp, and the assertions below catch it.
    """
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (a:Entity:Ku {uid: $a}) CREATE (b:Entity:Ku {uid: $b})
            CREATE (c:Entity:Ku {uid: $c}) CREATE (d:Entity:Ku {uid: $d})
            CREATE (a)-[:BLOCKS {created_at: $literal, reason: 'keep me'}]->(b)
            CREATE (b)-[:BLOCKED_BY {created_at: $literal}]->(a)
            CREATE (c)-[:ALTERNATIVE_TO {created_at: $good}]->(d)
            """,
            a=_UIDS[0],
            b=_UIDS[1],
            c=_UIDS[2],
            d=_UIDS[3],
            literal=migration.LITERAL,
            good=GOOD_STAMP,
        )
    yield
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n:Entity) WHERE n.uid IN $uids DETACH DELETE n", uids=_UIDS)


def test_guard_rejects_a_census_that_does_not_add_up():
    """The guard predicate, exercised directly.

    Testing the decision separately means the failure branch has real coverage
    without having to manufacture a concurrent writer mid-transaction.
    """
    holds = migration.guard_holds
    assert holds(total_before=10, literal_before=3, total_after=7, literal_after=0)
    # Literals survived the REMOVE.
    assert not holds(total_before=10, literal_before=3, total_after=7, literal_after=1)
    # Too many edges lost the property — an over-broad WHERE.
    assert not holds(total_before=10, literal_before=3, total_after=5, literal_after=0)
    # Too few — the REMOVE under-matched.
    assert not holds(total_before=10, literal_before=3, total_after=9, literal_after=0)


async def test_guard_failure_rolls_the_removal_back(neo4j_driver, seeded):
    """A failing guard must leave the graph untouched, not half-migrated.

    The guard is forced to fail by making it expect an impossible outcome. What
    matters is the consequence: the REMOVE ran inside the same transaction, so
    the literal-stamped edges must still be there afterwards.
    """
    literal_before = await migration._count_literal(neo4j_driver)
    assert literal_before >= 2, "positive control: nothing seeded, rollback would prove nothing"

    removed_inside_tx: list[int] = []

    async def always_fails(tx):
        removed_inside_tx.append(
            await migration._tx_scalar(tx, migration._REMOVE_LITERAL, literal=migration.LITERAL)
        )
        raise migration.GuardFailedError("forced")

    async with neo4j_driver.session() as session:
        with pytest.raises(migration.GuardFailedError):
            await session.execute_write(always_fails)

    # Positive control: the destructive statement really ran and really matched.
    # Without it, a REMOVE that silently matched nothing would make the
    # "still there afterwards" assertion below prove nothing about rollback.
    assert removed_inside_tx == [literal_before]

    assert await migration._count_literal(neo4j_driver) == literal_before


async def test_removes_only_the_literal_stamped_edges(neo4j_driver, seeded):
    literal_before = await migration._count_literal(neo4j_driver)
    total_before = await migration._scalar(neo4j_driver, migration._COUNT_ALL_WITH_CREATED_AT)

    # Positive control: the census can see the seed. Without this a query that
    # silently matched nothing would make every assertion below trivially true.
    assert literal_before >= 2
    assert total_before >= literal_before + 1, "the legitimately-stamped control edge is missing"

    # The real guarded path, not a hand-rolled equivalent.
    async with neo4j_driver.session() as session:
        outcome = await session.execute_write(migration._remove_literals_guarded)
    removed = outcome["removed"]
    assert removed == literal_before

    assert await migration._count_literal(neo4j_driver) == 0
    total_after = await migration._scalar(neo4j_driver, migration._COUNT_ALL_WITH_CREATED_AT)
    assert total_after == total_before - literal_before

    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (a:Entity {uid: $a})-[blocks:BLOCKS]->(:Entity {uid: $b})
            MATCH (:Entity {uid: $c})-[alt:ALTERNATIVE_TO]->(:Entity {uid: $d})
            RETURN 'created_at' IN keys(blocks) AS literal_edge_still_stamped,
                   blocks.reason AS untouched_sibling_property,
                   alt.created_at AS control_stamp
            """,
            a=_UIDS[0],
            b=_UIDS[1],
            c=_UIDS[2],
            d=_UIDS[3],
        )
        record = await result.single()

    assert record["literal_edge_still_stamped"] is False
    # REMOVE must take the one property, not the edge and not its neighbours.
    assert record["untouched_sibling_property"] == "keep me"
    assert record["control_stamp"] == GOOD_STAMP
    # And the control is still a real instant afterwards.
    datetime.fromisoformat(record["control_stamp"])
