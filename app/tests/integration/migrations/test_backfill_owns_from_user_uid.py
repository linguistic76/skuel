"""
Ownership-signal reconciliation — ``backfill_owns_from_user_uid_2026_07.cypher``
================================================================================

The bulk ingestion engine stamped ``user_uid`` on vault-authored activity
entities but never wrote the ``(User)-[:OWNS]->(entity)`` edge, so every
OWNS-consuming read path silently missed them. The migration restores the
edge from the property — the mirror of the June-2026 migration
(``backfill_user_uid_to_owns_owner_2026_06.cypher``), which restored the
property from the edge. Both enforce the same invariant:
``user_uid property == :OWNS owner``.

Seeds a real Neo4j container with four node shapes and asserts:

1. A property-only node (user_uid set, User exists, no edge) gains exactly
   one :OWNS edge carrying the CRUD-shaped edge properties.
2. An already-consistent node (edge exists) is untouched — still exactly one
   edge afterward.
3. A dangling-owner node (user_uid names no existing User) is skipped — no
   edge, no stub User.
4. A ``user_system``-stamped node is excluded even when a User node with that
   uid exists — ownerless system catalog content stays edge-free (June
   migration philosophy).
5. A dual-owned node (out-of-band :OWNS edge from another user) is reduced to
   its single property owner — Phase 1b, single-owner invariant (Kody #514
   finding accepted; property is authoritative on this side, unlike June).
6. The property==:OWNS-owner invariant (restricted to existing, non-system
   owners) holds globally after the migration.
7. Re-running the migration is a no-op (idempotent).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "migrations"
    / "backfill_owns_from_user_uid_2026_07.cypher"
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
    """Seed owner users plus property-only / consistent / dangling / system nodes."""
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (owner:User {uid: 'user_owns_bf'})
            CREATE (walker:User {uid: 'user_owns_bf_walker'})
            CREATE (sys:User {uid: 'user_system'})
            // Property-only: user_uid set, owner exists, edge missing (the bug)
            CREATE (t:Entity:Task {
                uid: 'ownsbf.property-only',
                entity_type: 'task',
                user_uid: 'user_owns_bf',
                status: 'pending',
                created_at: datetime()
            })
            // Consistent: property and edge already agree
            CREATE (g:Entity:Goal {
                uid: 'ownsbf.consistent',
                entity_type: 'goal',
                user_uid: 'user_owns_bf',
                status: 'active',
                created_at: datetime()
            })
            // Dangling owner: user_uid names a User that does not exist
            CREATE (e:Entity:Event {
                uid: 'ownsbf.dangling',
                entity_type: 'event',
                user_uid: 'user_never_registered',
                status: 'scheduled',
                created_at: datetime()
            })
            // System catalog: excluded even though a user_system User exists
            CREATE (h:Entity:Habit {
                uid: 'ownsbf.catalog',
                entity_type: 'habit',
                user_uid: 'user_system',
                status: 'active',
                created_at: datetime()
            })
            // Dual-owned: property says owner, but a bare out-of-band edge
            // from another user exists (the PR-3-walk-era shape)
            CREATE (p:Entity:Principle {
                uid: 'ownsbf.dual-owned',
                entity_type: 'principle',
                user_uid: 'user_owns_bf',
                status: 'active',
                created_at: datetime()
            })
            CREATE (owner)-[:OWNS {access_count: 7, is_active: true}]->(g)
            CREATE (walker)-[:OWNS]->(p)
            """
        )


async def _owns_edges(neo4j_driver, uid: str) -> list[dict]:
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (o:User)-[r:OWNS]->(n:Entity {uid: $uid}) "
            "RETURN o.uid AS owner, properties(r) AS props",
            {"uid": uid},
        )
        return [dict(record) async for record in result]


async def _count(neo4j_driver, query: str, **params) -> int:
    async with neo4j_driver.session() as session:
        result = await session.run(query, params)
        record = await result.single()
        return int(record[0]) if record else 0


@pytest.mark.asyncio
async def test_backfill_creates_owns_edges_from_user_uid(
    clean_neo4j,
    neo4j_driver,
) -> None:
    await _seed(neo4j_driver)

    # Sanity: the bug state exists before migration
    assert await _owns_edges(neo4j_driver, "ownsbf.property-only") == []

    await _run_migration(neo4j_driver)

    # 1. Property-only node gains exactly one edge with CRUD-shaped props
    edges = await _owns_edges(neo4j_driver, "ownsbf.property-only")
    assert len(edges) == 1
    assert edges[0]["owner"] == "user_owns_bf"
    props = edges[0]["props"]
    assert props["access_count"] == 0
    assert props["is_active"] is True
    assert isinstance(props["created_at"], str)
    assert isinstance(props["last_accessed"], str)

    # 2. Consistent node untouched — still exactly one edge, original props kept
    edges = await _owns_edges(neo4j_driver, "ownsbf.consistent")
    assert len(edges) == 1
    assert edges[0]["props"]["access_count"] == 7

    # 3. Dangling owner skipped — no edge, no stub User created
    assert await _owns_edges(neo4j_driver, "ownsbf.dangling") == []
    assert (
        await _count(
            neo4j_driver,
            "MATCH (u:User {uid: 'user_never_registered'}) RETURN count(u)",
        )
        == 0
    )

    # 4. System catalog node excluded despite an existing user_system User
    assert await _owns_edges(neo4j_driver, "ownsbf.catalog") == []

    # 5. Dual-owned node reduced to its single property owner (Phase 1b)
    edges = await _owns_edges(neo4j_driver, "ownsbf.dual-owned")
    assert [e["owner"] for e in edges] == ["user_owns_bf"]

    # 6. Global invariant: every user_uid-bearing Entity whose (non-system)
    # owner exists has its :OWNS edge, and no other user owns it
    assert (
        await _count(
            neo4j_driver,
            "MATCH (e:Entity) "
            "WHERE e.user_uid IS NOT NULL AND e.user_uid <> 'user_system' "
            "MATCH (owner:User {uid: e.user_uid}) "
            "WHERE NOT (owner)-[:OWNS]->(e) RETURN count(e)",
        )
        == 0
    )
    assert (
        await _count(
            neo4j_driver,
            "MATCH (stale:User)-[:OWNS]->(e:Entity) "
            "WHERE e.user_uid IS NOT NULL AND e.user_uid <> 'user_system' "
            "AND stale.uid <> e.user_uid RETURN count(e)",
        )
        == 0
    )

    # 7. Idempotence — re-running creates and deletes nothing new
    await _run_migration(neo4j_driver)
    assert len(await _owns_edges(neo4j_driver, "ownsbf.property-only")) == 1
    assert len(await _owns_edges(neo4j_driver, "ownsbf.consistent")) == 1
    assert await _owns_edges(neo4j_driver, "ownsbf.catalog") == []
    assert len(await _owns_edges(neo4j_driver, "ownsbf.dual-owned")) == 1
