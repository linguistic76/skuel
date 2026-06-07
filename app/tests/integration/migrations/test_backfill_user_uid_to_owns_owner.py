"""
Ownership-signal reconciliation — ``backfill_user_uid_to_owns_owner_2026_06.cypher``
=====================================================================================

A node's denormalized ``user_uid`` PROPERTY can diverge from its authoritative
``(User)-[:OWNS]->(entity)`` edge (onboarding/demo seed content was :OWNS-linked
to a real user but kept ``user_uid="user_system"``). The migration backfills the
property to match the :OWNS owner.

Seeds a real Neo4j container with three node shapes and asserts:

1. A diverging owned node (property ≠ owner) is rewritten so property == owner.
2. An already-consistent owned node is left unchanged.
3. An ownerless system catalog node (``user_system``, no :OWNS) is NOT touched —
   ownerless system content is legitimately system-owned.
4. The property==:OWNS-owner invariant holds globally after the migration.
5. Re-running the migration is a no-op (idempotent).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "migrations"
    / "backfill_user_uid_to_owns_owner_2026_06.cypher"
)


def _load_statements() -> list[str]:
    """Split the migration file into individual Cypher statements."""
    raw = MIGRATION_PATH.read_text()
    no_comments = "\n".join(
        line for line in raw.splitlines() if not line.lstrip().startswith("//")
    )
    chunks = [c.strip() for c in no_comments.split(";")]
    return [c for c in chunks if c and not re.fullmatch(r"\s*", c)]


async def _run_migration(neo4j_driver) -> None:
    statements = _load_statements()
    async with neo4j_driver.session() as session:
        for stmt in statements:
            result = await session.run(stmt)
            await result.consume()


async def _seed(neo4j_driver) -> None:
    """Seed an owner user plus diverging / consistent / ownerless nodes."""
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (owner:User {uid: 'user_owns_mig'})
            // Diverging: owned by user_owns_mig but property says user_system
            CREATE (t:Entity:Task {
                uid: 'owns.mig.diverging',
                entity_type: 'task',
                user_uid: 'user_system',
                status: 'pending',
                created_at: datetime()
            })
            // Consistent: owned by user_owns_mig and property agrees
            CREATE (g:Entity:Goal {
                uid: 'owns.mig.consistent',
                entity_type: 'goal',
                user_uid: 'user_owns_mig',
                status: 'active',
                created_at: datetime()
            })
            // Ownerless system catalog node — no :OWNS edge, must stay untouched
            CREATE (c:Entity:Habit {
                uid: 'owns.mig.catalog',
                entity_type: 'habit',
                user_uid: 'user_system',
                status: 'active',
                created_at: datetime()
            })
            CREATE (owner)-[:OWNS]->(t)
            CREATE (owner)-[:OWNS]->(g)
            """
        )


async def _prop(neo4j_driver, uid: str) -> str | None:
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (n:Entity {uid: $uid}) RETURN n.user_uid AS prop", {"uid": uid}
        )
        record = await result.single()
        return record["prop"] if record else None


async def _count(neo4j_driver, query: str, **params) -> int:
    async with neo4j_driver.session() as session:
        result = await session.run(query, params)
        record = await result.single()
        return int(record[0]) if record else 0


@pytest.mark.asyncio
async def test_backfill_aligns_property_to_owns_owner(
    clean_neo4j,
    neo4j_driver,
) -> None:
    await _seed(neo4j_driver)

    # Sanity: divergence exists before migration
    assert await _prop(neo4j_driver, "owns.mig.diverging") == "user_system"

    await _run_migration(neo4j_driver)

    # 1. Diverging node rewritten to its :OWNS owner
    assert await _prop(neo4j_driver, "owns.mig.diverging") == "user_owns_mig"

    # 2. Consistent node unchanged
    assert await _prop(neo4j_driver, "owns.mig.consistent") == "user_owns_mig"

    # 3. Ownerless catalog node NOT touched
    assert await _prop(neo4j_driver, "owns.mig.catalog") == "user_system"

    # 4. Global invariant: no owned node's property disagrees with its owner
    assert (
        await _count(
            neo4j_driver,
            "MATCH (o:User)-[:OWNS]->(e:Entity) WHERE o.uid <> e.user_uid RETURN count(e)",
        )
        == 0
    )

    # 5. Idempotence — re-running rewrites nothing
    await _run_migration(neo4j_driver)
    assert await _prop(neo4j_driver, "owns.mig.diverging") == "user_owns_mig"
    assert await _prop(neo4j_driver, "owns.mig.catalog") == "user_system"
