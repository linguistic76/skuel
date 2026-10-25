"""The relationship statements bind every endpoint kind a live caller passes.

Each statement binds its uid through ``build_uid_anchor`` — an index seek under
``:Entity``, ``:User`` and ``:Group`` (plus the backend's own label) — instead of a
label-less match that scans the graph. These tests drive the statements with the
non-Entity endpoints their callers write: an exercise's teacher (Exercise→User,
``REVIEWED_BY``) through the registry-validated single-edge path, and a membership
(User→Group, ``MEMBER_OF``) through the query executor's mixed-label batch. The
batch delete is directed, like the single delete: it removes ``(from)-[r]->(to)``
and keeps an edge of the same type running the other way.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from tests.helpers.production_backends import build_production_backends

if TYPE_CHECKING:
    from neo4j import AsyncDriver

EXERCISE_UID = "ex.anchor.probe"
TEACHER_UID = "user_a1c3e5f7b9d0a2c4"
GROUP_UID = "group_b2d4f6a8c0e1b3d5"
KU_A_UID = "ku.anchor.first"
KU_B_UID = "ku.anchor.second"


@pytest_asyncio.fixture
async def seeded(neo4j_driver: AsyncDriver, clean_neo4j: None) -> AsyncIterator[AsyncDriver]:
    """An exercise, a teacher and a group; the teacher is removed afterwards
    (``clean_neo4j`` keeps every :User across tests)."""
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (:Entity:Exercise {uid: $ex, entity_type: 'exercise', title: 'Anchor probe'})
            MERGE (:User {uid: $teacher, title: 'anchorprobe'})
            CREATE (:Group {uid: $group, name: 'Anchor probe group'})
            CREATE (:Entity:Ku {uid: $ku_a, entity_type: 'ku', title: 'First'})
            CREATE (:Entity:Ku {uid: $ku_b, entity_type: 'ku', title: 'Second'})
            """,
            ex=EXERCISE_UID,
            teacher=TEACHER_UID,
            group=GROUP_UID,
            ku_a=KU_A_UID,
            ku_b=KU_B_UID,
        )
    yield neo4j_driver
    async with neo4j_driver.session() as session:
        await session.run("MATCH (u:User {uid: $uid}) DETACH DELETE u", uid=TEACHER_UID)


@pytest.mark.asyncio
async def test_an_exercise_to_teacher_edge_binds_the_user_endpoint(seeded: AsyncDriver) -> None:
    backend = build_production_backends(seeded)["exercise_backend"]
    reviewed_by = RelationshipName.REVIEWED_BY

    created = await backend.create_relationship(EXERCISE_UID, TEACHER_UID, reviewed_by)
    assert created.is_ok, created
    assert (await backend.has_relationship(EXERCISE_UID, TEACHER_UID, reviewed_by)).value is True

    metadata = await backend.get_relationship_metadata(EXERCISE_UID, TEACHER_UID, reviewed_by)
    assert metadata.is_ok
    assert metadata.value == {}

    # The teacher's side of the edge, read with the User as the anchor.
    rows = await backend.get_relationships(TEACHER_UID, reviewed_by, "incoming")
    assert rows.is_ok
    assert [(row["target_uid"], row["direction"]) for row in rows.value] == [
        (EXERCISE_UID, "incoming")
    ]

    # A source-kind filter that the exercise does not carry keeps the edge.
    kept = await backend.delete_relationship(
        EXERCISE_UID, TEACHER_UID, reviewed_by, from_label=NeoLabel.KU
    )
    assert kept.is_ok
    assert (await backend.has_relationship(EXERCISE_UID, TEACHER_UID, reviewed_by)).value is True

    deleted = await backend.delete_relationship(
        EXERCISE_UID, TEACHER_UID, reviewed_by, to_label=NeoLabel.USER
    )
    assert deleted.is_ok
    assert (await backend.has_relationship(EXERCISE_UID, TEACHER_UID, reviewed_by)).value is False


@pytest.mark.asyncio
async def test_a_mixed_label_batch_binds_user_and_group_endpoints(seeded: AsyncDriver) -> None:
    executor = Neo4jQueryExecutor(seeded)

    created = await executor.create_relationships_batch(
        [(TEACHER_UID, GROUP_UID, RelationshipName.MEMBER_OF.value, {"role": "teacher"})]
    )
    assert created.is_ok
    assert created.value == 1

    async with seeded.session() as session:
        result = await session.run(
            "MATCH (:User {uid: $u})-[r:MEMBER_OF]->(:Group {uid: $g}) RETURN r.role AS role",
            u=TEACHER_UID,
            g=GROUP_UID,
        )
        assert [record["role"] async for record in result] == ["teacher"]


@pytest.mark.asyncio
async def test_the_batch_delete_keeps_the_edge_running_the_other_way(seeded: AsyncDriver) -> None:
    backend = build_production_backends(seeded)["exercise_backend"]
    organizes = RelationshipName.ORGANIZES.value
    async with seeded.session() as session:
        await session.run(
            f"""
            MATCH (a:Entity {{uid: $a}}), (b:Entity {{uid: $b}})
            CREATE (a)-[:{organizes}]->(b), (b)-[:{organizes}]->(a)
            """,
            a=KU_A_UID,
            b=KU_B_UID,
        )

    deleted = await backend.delete_relationships_batch([(KU_A_UID, KU_B_UID, organizes)])
    assert deleted.is_ok
    assert deleted.value == 1

    async with seeded.session() as session:
        result = await session.run(
            f"MATCH (a:Entity)-[:{organizes}]->(b:Entity) RETURN a.uid AS a, b.uid AS b"
        )
        assert [(record["a"], record["b"]) async for record in result] == [(KU_B_UID, KU_A_UID)]
