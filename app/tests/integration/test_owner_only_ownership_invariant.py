"""OWNER_ONLY ownership — the two read mechanisms and the invariant that couples them.

SKUEL scopes OWNER_ONLY reads two different ways, by ruling (see
``docs/architecture/SEARCH_ARCHITECTURE.md`` § *Ownership Scoping — SearchVisibility
(July 2026 ruling)*):

* the **faceted** path anchors on the ``(User)-[:OWNS]->(entity)`` edge
  (``faceted_search_raw``), and
* every other strategy filters the denormalized ``user_uid`` **property**
  (``build_search_visibility_clause``, reached here through ``text_search_raw``).

They return the same rows only because both write doors hold one invariant:
**``user_uid`` property == ``:OWNS`` owner.** The ingestion door holds it inside
``build_node_upsert_template`` and is guarded by
``test_ingestion_owns_enum_casing.py::test_invariant_no_user_uid_bearing_entity_without_owns``.

These tests hold the **CRUD door** — the other half, which used to CREATE the node and
then write the edge in a *separate* query, merely ``logger.warning``-ing when the second
one failed and returning ``Result.ok``. That left a property-only node: still visible to
property-scoped reads, invisible to every ``:OWNS``-traversing read. A 2026-07 ingest batch
shipped exactly that shape and an owner's own Principles vanished from ``/search``.

Requires: Docker running with Neo4j testcontainer.
"""

from __future__ import annotations

import pytest

from core.models.enums import EntityStatus
from core.models.enums.metadata_enums import SearchVisibility
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task

pytestmark = pytest.mark.asyncio

OWNER = "user_owns_invariant_owner"
STRANGER = "user_owns_invariant_stranger"
GHOST = "user_owns_invariant_ghost_never_created"

# Distinctive enough that no fixture task in the shared container matches it.
MARKER = "zzqqowninv"

SEARCH_FIELDS = ("title", "description")


async def _seed_users(driver) -> None:
    async with driver.session() as session:
        await session.run("UNWIND $uids AS uid MERGE (u:User {uid: uid})", uids=[OWNER, STRANGER])
        # The ghost must NOT exist — a previous run may have created it.
        await session.run("MATCH (u:User {uid: $uid}) DETACH DELETE u", uid=GHOST)


async def _node_state(driver, uid: str) -> dict | None:
    """Return the node's property owner and its :OWNS edge owners, or None if absent."""
    async with driver.session() as session:
        result = await session.run(
            f"""
            MATCH (n:Task {{uid: $uid}})
            OPTIONAL MATCH (u:User)-[:{RelationshipName.OWNS.value}]->(n)
            RETURN n.user_uid AS prop, collect(u.uid) AS edge_owners
            """,
            uid=uid,
        )
        record = await result.single()
    return dict(record) if record else None


def _task(uid: str, user_uid: str, title: str) -> Task:
    return Task(
        uid=uid,
        user_uid=user_uid,
        title=title,
        description="owner-invariant fixture",
        status=EntityStatus.ACTIVE,
    )


async def _edge_mechanism_uids(backend, user_uid: str) -> set[str]:
    """The faceted path — ownership expressed as the anchor :OWNS MATCH."""
    result = await backend.faceted_search_raw(
        user_uid,
        user_ownership_relationship=RelationshipName.OWNS,
        search_fields=SEARCH_FIELDS,
        search_order_by="created_at",
        graph_enrichment_patterns=(),
        property_filters={},
        query_text=MARKER,
        visibility=SearchVisibility.OWNER_ONLY,
    )
    assert result.is_ok, result.expect_error()
    return {row["entity"]["uid"] for row in result.value}


async def _property_mechanism_uids(backend, user_uid: str) -> set[str]:
    """Every other strategy — ownership expressed as build_search_visibility_clause."""
    result = await backend.text_search_raw(
        MARKER,
        SEARCH_FIELDS,
        user_uid=user_uid,
        visibility=SearchVisibility.OWNER_ONLY,
    )
    assert result.is_ok, result.expect_error()
    return {row["uid"] for row in result.value}


async def _unscoped_uids(driver) -> set[str]:
    """Ungated control: no ownership predicate at all.

    Without this, a scoped assertion would also pass against a query that returned
    nothing, or one that filtered by accident.
    """
    async with driver.session() as session:
        result = await session.run(
            "MATCH (n:Task) WHERE toLower(n.title) CONTAINS $q RETURN n.uid AS uid",
            q=MARKER,
        )
        return {record["uid"] async for record in result}


# =============================================================================
# The CRUD door writes both halves, or neither
# =============================================================================


async def test_create_writes_property_and_owns_edge_together(
    clean_neo4j, neo4j_driver, tasks_service
) -> None:
    """The happy path leaves the invariant intact: property owner == :OWNS owner."""
    await _seed_users(neo4j_driver)
    uid = f"task_{MARKER}_both_halves"

    result = await tasks_service.create(_task(uid, OWNER, f"{MARKER} both halves"))
    assert result.is_ok, result.expect_error()

    state = await _node_state(neo4j_driver, uid)
    assert state is not None, "node must exist"
    assert state["prop"] == OWNER
    assert state["edge_owners"] == [OWNER]


async def test_create_with_unknown_owner_persists_nothing(
    clean_neo4j, neo4j_driver, tasks_service
) -> None:
    """A user_uid naming no :User fails the create — it does NOT leave a property-only node.

    This is the regression the whole file exists for. Against the pre-fix
    ``_create_node`` this failed twice over: ``create`` returned ``Result.ok`` and the
    orphan node was left behind, reachable by property-scoped reads and invisible to
    every :OWNS-traversing one.
    """
    await _seed_users(neo4j_driver)
    uid = f"task_{MARKER}_ghost_owner"

    result = await tasks_service.create(_task(uid, GHOST, f"{MARKER} ghost owner"))

    assert result.is_error, "create must not report success when the owner edge cannot be written"
    assert await _node_state(neo4j_driver, uid) is None, (
        "no node may survive a create whose owner edge could not be written — "
        "a property-only node is exactly the divergence this guards"
    )


async def test_create_with_spawned_from_holds_the_same_invariant(
    clean_neo4j, neo4j_driver, tasks_backend
) -> None:
    """The second _create_node caller gets the same guarantee, not a weaker one."""
    await _seed_users(neo4j_driver)
    async with neo4j_driver.session() as session:
        await session.run(
            "MERGE (t:Entity {uid: $uid}) ON CREATE SET t.entity_type = 'task_template'",
            uid=f"tt_{MARKER}_template",
        )

    ok_uid = f"task_{MARKER}_spawned_ok"
    ok = await tasks_backend.create_with_spawned_from(
        _task(ok_uid, OWNER, f"{MARKER} spawned ok"), f"tt_{MARKER}_template"
    )
    assert ok.is_ok, ok.expect_error()
    state = await _node_state(neo4j_driver, ok_uid)
    assert state is not None and state["edge_owners"] == [OWNER]

    ghost_uid = f"task_{MARKER}_spawned_ghost"
    ghost = await tasks_backend.create_with_spawned_from(
        _task(ghost_uid, GHOST, f"{MARKER} spawned ghost"), f"tt_{MARKER}_template"
    )
    assert ghost.is_error
    assert await _node_state(neo4j_driver, ghost_uid) is None


async def test_ownerless_entity_still_creates_without_an_owns_edge(
    clean_neo4j, neo4j_driver, ku_backend
) -> None:
    """The carve-out survives: no user_uid means no owner MATCH and no edge.

    Curriculum content (Ku here) is ownerless by design — it carries no
    ``user_uid`` field at all. Making the owner MATCH unconditional would have
    made every curriculum create fail.
    """
    from core.models.ku.ku import Ku

    uid = f"ku.{MARKER}.ownerless"
    result = await ku_backend.create(Ku(uid=uid, title=f"{MARKER} ownerless"))
    assert result.is_ok, result.expect_error()

    async with neo4j_driver.session() as session:
        record = await (
            await session.run(
                f"""
                MATCH (n:Entity {{uid: $uid}})
                OPTIONAL MATCH (u:User)-[:{RelationshipName.OWNS.value}]->(n)
                RETURN n.user_uid AS prop, collect(u.uid) AS edge_owners
                """,
                uid=uid,
            )
        ).single()

    assert record is not None, "an ownerless entity must still be created"
    assert record["prop"] is None
    assert record["edge_owners"] == []


async def test_crud_door_leaves_no_user_uid_bearing_entity_without_owns(
    clean_neo4j, neo4j_driver, tasks_service
) -> None:
    """The CRUD-door twin of the ingestion door's corpus-wide invariant guard.

    Deliberately the same query as
    ``test_ingestion_owns_enum_casing.py::test_invariant_no_user_uid_bearing_entity_without_owns``
    so the two write doors are held to one standard, stated one way.
    """
    await _seed_users(neo4j_driver)
    for i, user in enumerate((OWNER, STRANGER, OWNER)):
        created = await tasks_service.create(
            _task(f"task_{MARKER}_corpus_{i}", user, f"{MARKER} corpus {i}")
        )
        assert created.is_ok, created.expect_error()

    async with neo4j_driver.session() as session:
        record = await (
            await session.run(
                f"""
                MATCH (e:Entity)
                WHERE e.user_uid IS NOT NULL AND e.user_uid <> 'user_system'
                MATCH (owner:User {{uid: e.user_uid}})
                WHERE NOT (owner)-[:{RelationshipName.OWNS.value}]->(e)
                RETURN count(e) AS missing
                """
            )
        ).single()

    assert record["missing"] == 0


# =============================================================================
# The two read mechanisms agree — and the invariant is what makes them agree
# =============================================================================


async def test_both_mechanisms_return_the_same_owner_scoped_set(
    clean_neo4j, neo4j_driver, tasks_service, tasks_backend
) -> None:
    """Edge-anchored and property-scoped reads return the same rows on a healthy graph."""
    await _seed_users(neo4j_driver)
    owner_uid = f"task_{MARKER}_agree_owner"
    stranger_uid = f"task_{MARKER}_agree_stranger"

    for uid, user in ((owner_uid, OWNER), (stranger_uid, STRANGER)):
        created = await tasks_service.create(_task(uid, user, f"{MARKER} agree {user}"))
        assert created.is_ok, created.expect_error()

    # Ungated control — both rows are reachable, so a scoped assertion can fail.
    assert await _unscoped_uids(neo4j_driver) == {owner_uid, stranger_uid}

    edge_hits = await _edge_mechanism_uids(tasks_backend, OWNER)
    property_hits = await _property_mechanism_uids(tasks_backend, OWNER)

    assert edge_hits == {owner_uid}, "faceted path must return only the owner's row"
    assert property_hits == {owner_uid}, "property path must return only the owner's row"
    assert edge_hits == property_hits


async def test_breaking_the_invariant_out_of_band_makes_the_paths_disagree(
    clean_neo4j, neo4j_driver, tasks_service, tasks_backend
) -> None:
    """Characterisation: the two mechanisms are NOT interchangeable — the invariant is load-bearing.

    Deleting the :OWNS edge behind the CRUD door's back reproduces the 2026-07 shape.
    The property path still finds the row; the edge path loses it. This is deliberately
    asserted rather than fixed: it is the reason the write doors must keep both halves
    inseparable, and it fails loudly if someone decides the two mechanisms are equivalent
    and drops one guard.
    """
    await _seed_users(neo4j_driver)
    uid = f"task_{MARKER}_divergent"

    created = await tasks_service.create(_task(uid, OWNER, f"{MARKER} divergent"))
    assert created.is_ok, created.expect_error()
    assert await _edge_mechanism_uids(tasks_backend, OWNER) == {uid}  # baseline: agrees

    async with neo4j_driver.session() as session:
        await session.run(
            f"MATCH (:User {{uid: $uid}})-[r:{RelationshipName.OWNS.value}]->(n:Task {{uid: $node}}) "
            "DELETE r",
            uid=OWNER,
            node=uid,
        )

    assert await _property_mechanism_uids(tasks_backend, OWNER) == {uid}, (
        "the property half survives — the node still carries user_uid"
    )
    assert await _edge_mechanism_uids(tasks_backend, OWNER) == set(), (
        "the edge half is gone — the owner's own row has vanished from faceted search"
    )
