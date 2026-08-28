"""
Ingestion data hygiene — OWNS edges + canonical enum casing (PR #513 residue)
=============================================================================

Two write-side guarantees the read-side fixes in #513 tolerated but did not
enforce:

1. **OWNS on ingest** — every activity entity persisted with a ``user_uid``
   gets its ``(User)-[:OWNS]->(entity)`` edge at ingestion time (both ingest
   doors run through ``build_node_upsert_template``). Before this fix the
   bulk engine wrote the property only, so OWNS-consuming read paths
   (faceted search ownership MATCH, ``get_user_entities``) silently missed
   vault-authored activities.
2. **Canonical enum casing** — authored ``learning_level: BEGINNER`` /
   ``sel_category: SELF_AWARENESS`` is normalized to canonical lowercase at
   the preparer, so exact-match property filters keep working; the
   ``parse_enum_field`` read tolerance (#513) stays as belt-and-suspenders.

Plus the invariant guard ruled in the design pass: after ingestion, zero
user_uid-bearing Entities lack a matching OWNS edge — this keeps #513's two
scoping mechanisms (edge-based faceted vs property-based strategies)
equivalent without converging them.

Requires: Docker running with Neo4j testcontainer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

OWNER_UID = "user_test_integration"  # seeded by the ensure_test_users fixture


def _write_task_file(directory: Path, slug: str, extra_frontmatter: str = "") -> Path:
    path = directory / f"{slug}.md"
    path.write_text(
        f"""---
type: task
uid: task.{slug}
title: Task {slug}
user_uid: {OWNER_UID}
{extra_frontmatter}---

Body of {slug}.
"""
    )
    return path


def _write_curriculum_exercise_file(directory: Path, slug: str) -> Path:
    """Exercise authored with UPPERCASE enum values (the 0vault/Exer/ drift)."""
    path = directory / f"{slug}.md"
    path.write_text(
        f"""---
type: exercise
uid: ex.{slug}
title: Exercise {slug}
instructions: Reflect on the practice and describe one concrete observation.
scope: CURRICULUM
learning_level: BEGINNER
sel_category: SELF_AWARENESS
---

Exercise body.
"""
    )
    return path


async def _owns_edges(neo4j_driver, uid: str) -> list[dict]:
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (o:User)-[r:OWNS]->(n:Entity {uid: $uid}) "
            "RETURN o.uid AS owner, properties(r) AS props",
            {"uid": uid},
        )
        return [dict(record) async for record in result]


async def _node_props(neo4j_driver, uid: str) -> dict | None:
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (n:Entity {uid: $uid}) RETURN properties(n) AS props", {"uid": uid}
        )
        record = await result.single()
        return dict(record["props"]) if record else None


@pytest.mark.asyncio
async def test_batch_door_writes_owns_edge_for_activity(
    clean_neo4j, neo4j_driver, ingestion_service, tmp_path: Path
) -> None:
    """The directory door persists user_uid AND the :OWNS edge (the #513 gap)."""
    vault = tmp_path / "vault"
    vault.mkdir()
    _write_task_file(vault, "ownstest-alpha")

    result = await ingestion_service.ingest_directory(vault)
    assert result.is_ok, f"ingestion failed: {result}"

    edges = await _owns_edges(neo4j_driver, "task.ownstest-alpha")
    assert len(edges) == 1, "ingested activity must carry exactly one :OWNS edge"
    assert edges[0]["owner"] == OWNER_UID
    props = edges[0]["props"]
    # Edge props mirror the CRUD create door's :OWNS edge defaults (ADR-086)
    assert props["access_count"] == 0
    assert props["is_active"] is True
    assert isinstance(props["created_at"], str)
    assert isinstance(props["last_accessed"], str)


@pytest.mark.asyncio
async def test_single_file_door_writes_owns_edge(
    clean_neo4j, neo4j_driver, ingestion_service, tmp_path: Path
) -> None:
    """Both ingest doors share the node-upsert template — the file door too."""
    path = _write_task_file(tmp_path, "ownstest-single")

    result = await ingestion_service.ingest_file(path)
    assert result.is_ok, f"ingestion failed: {result}"

    edges = await _owns_edges(neo4j_driver, "task.ownstest-single")
    assert len(edges) == 1
    assert edges[0]["owner"] == OWNER_UID


@pytest.mark.asyncio
async def test_reingest_is_idempotent_one_owns_edge(
    clean_neo4j, neo4j_driver, ingestion_service, tmp_path: Path
) -> None:
    """Re-syncing the same file must MERGE, never duplicate, the owner edge."""
    vault = tmp_path / "vault"
    vault.mkdir()
    _write_task_file(vault, "ownstest-idem")

    assert (await ingestion_service.ingest_directory(vault)).is_ok
    assert (await ingestion_service.ingest_directory(vault)).is_ok

    assert len(await _owns_edges(neo4j_driver, "task.ownstest-idem")) == 1


@pytest.mark.asyncio
async def test_reingest_removes_stale_owner_edge(
    clean_neo4j, neo4j_driver, ingestion_service, tmp_path: Path
) -> None:
    """
    Single-owner invariant (Kody #514 finding, accepted): when a node carries
    an :OWNS edge from a user other than its resolved owner (owner change or
    an out-of-band edge), re-ingest removes the stale edge — a former owner
    must not keep access.
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    _write_task_file(vault, "ownstest-stale")
    assert (await ingestion_service.ingest_directory(vault)).is_ok

    # Simulate the out-of-band edge (bare, propertyless — the walk-era shape)
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n:Entity {uid: 'task.ownstest-stale'}) "
            "MATCH (u:User {uid: 'user_test_123'}) "
            "MERGE (u)-[:OWNS]->(n)"
        )
    assert len(await _owns_edges(neo4j_driver, "task.ownstest-stale")) == 2

    # Touch the file so incremental hashing re-processes it, then re-ingest
    _write_task_file(vault, "ownstest-stale", extra_frontmatter="description: touched\n")
    assert (await ingestion_service.ingest_directory(vault)).is_ok

    edges = await _owns_edges(neo4j_driver, "task.ownstest-stale")
    assert [e["owner"] for e in edges] == [OWNER_UID]


@pytest.mark.asyncio
async def test_unknown_owner_is_refused_and_nothing_lands(
    clean_neo4j, neo4j_driver, ingestion_service, tmp_path: Path
) -> None:
    """An owner with no :User node refuses the batch — it does not orphan a node.

    The template's owner ``MATCH`` sits in a row-preserving unit ``CALL``
    subquery *after* the node persists, so this used to be the silent case:
    node written with ``user_uid``, no ``:OWNS`` edge, ingest reports success,
    and the entity is invisible to every ``:OWNS``-traversing read. That is
    ADR-086's door-2 soft spot; ``BulkUpsertBackend._refuse_unknown_owners``
    is the loud half. The door still never MERGEs a ``:User`` — it refuses
    rather than inventing one.
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    ghost = "user_owns_ghost_never_created"
    path = vault / "ownstest-ghost.md"
    path.write_text(
        f"""---
type: task
uid: task.ownstest-ghost
title: Task owned by nobody
user_uid: {ghost}
---

Body.
"""
    )
    # The ghost must NOT exist — :User nodes survive clean_neo4j.
    async with neo4j_driver.session() as session:
        await session.run("MATCH (u:User {uid: $uid}) DETACH DELETE u", {"uid": ghost})

    result = await ingestion_service.ingest_directory(vault)

    stats = result.value
    assert stats.successful == 0 and stats.failed == 1, (
        f"an ingest naming an owner with no :User node was not counted as failed: {stats}"
    )
    assert stats.errors and ghost in stats.errors[0]["error"], (
        "the refusal must name the owner — that is what makes the cause "
        "(deleted user / stale descriptor / mistyped SKUEL_DEFAULT_USER_UID) diagnosable"
    )
    assert await _node_props(neo4j_driver, "task.ownstest-ghost") is None, (
        "the node landed anyway — the refusal must precede the write, not report "
        "orphans it already created"
    )


@pytest.mark.asyncio
async def test_known_owner_still_ingests(
    clean_neo4j, neo4j_driver, ingestion_service, tmp_path: Path
) -> None:
    """Positive control for the refusal above — a real owner is unaffected.

    Without this, a pre-flight that refused *every* batch would pass the test
    above and look like a working guard.
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    _write_task_file(vault, "ownstest-known")

    assert (await ingestion_service.ingest_directory(vault)).is_ok
    assert await _node_props(neo4j_driver, "task.ownstest-known") is not None
    assert len(await _owns_edges(neo4j_driver, "task.ownstest-known")) == 1


@pytest.mark.asyncio
async def test_invariant_no_user_uid_bearing_entity_without_owns(
    clean_neo4j, neo4j_driver, ingestion_service, tmp_path: Path
) -> None:
    """
    The divergence guard from the design ruling: user_uid property implies
    :OWNS edge (for existing, non-system owners). This is what keeps #513's
    edge-based faceted scoping and property-based strategy scoping
    equivalent without converging the two mechanisms.
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    _write_task_file(vault, "ownstest-inv-task")
    _write_curriculum_exercise_file(vault, "ownstest-inv-exercise")

    result = await ingestion_service.ingest_directory(vault)
    assert result.is_ok, f"ingestion failed: {result}"

    async with neo4j_driver.session() as session:
        res = await session.run(
            "MATCH (e:Entity) "
            "WHERE e.user_uid IS NOT NULL AND e.user_uid <> 'user_system' "
            "MATCH (owner:User {uid: e.user_uid}) "
            "WHERE NOT (owner)-[:OWNS]->(e) "
            "RETURN count(e) AS missing"
        )
        record = await res.single()
        assert record["missing"] == 0


@pytest.mark.asyncio
async def test_curriculum_exercise_carveout_stays_ownerless(
    clean_neo4j, neo4j_driver, ingestion_service, tmp_path: Path
) -> None:
    """File-ingested exercises are shared curriculum content — NO user OWNS."""
    vault = tmp_path / "vault"
    vault.mkdir()
    _write_curriculum_exercise_file(vault, "ownstest-carveout")

    result = await ingestion_service.ingest_directory(vault)
    assert result.is_ok, f"ingestion failed: {result}"

    props = await _node_props(neo4j_driver, "ex.ownstest-carveout")
    assert props is not None, "exercise must have been ingested"
    assert props.get("user_uid") is None
    assert await _owns_edges(neo4j_driver, "ex.ownstest-carveout") == []


@pytest.mark.asyncio
async def test_uppercase_enum_values_stored_canonical(
    clean_neo4j, neo4j_driver, ingestion_service, tmp_path: Path
) -> None:
    """
    Authored UPPERCASE enum values are normalized at the preparer so
    exact-match property filters (faceted sel_category) keep working —
    the graph must never store non-canonical casing.
    """
    vault = tmp_path / "vault"
    vault.mkdir()
    _write_curriculum_exercise_file(vault, "ownstest-casing")

    result = await ingestion_service.ingest_directory(vault)
    assert result.is_ok, f"ingestion failed: {result}"

    props = await _node_props(neo4j_driver, "ex.ownstest-casing")
    assert props is not None
    assert props["learning_level"] == "beginner"
    assert props["sel_category"] == "self_awareness"
    assert props["scope"] == "curriculum"
