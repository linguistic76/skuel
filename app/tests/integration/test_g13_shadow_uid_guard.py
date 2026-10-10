"""A uid-anchored write or read binds the entity, never its ``:Content`` shadow (G13).

The chunk store gives every Ku / PathStep with a body a second node carrying the
SAME uid (``MERGE (c:Content {uid: $uid})`` in ``neo4j_content_adapter.py``). A
uid-anchored pattern with no label binds both nodes, so a write doubles its edge
and a read doubles its rows. Every such pattern under ``adapters/persistence/``
binds ``:Entity`` (or the domain label); ``tests/unit/test_g13_shadow_uid_census.py``
holds that over the tree, and this file proves the doors a learner reaches on a
real Neo4j: the lateral writer, the engagement opener, the semantic-triple
writer and the pin writer each leave exactly one edge, the lateral reads return
one row per entity, and a triple naming an absent endpoint creates nothing.

The shadow is written by the REAL content adapter, and the control assertion
(two nodes on the uid) runs first — a one-edge assertion means nothing unless
the shadow provably exists.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from neo4j import AsyncDriver, Record

from adapters.persistence.neo4j.backends.collab_backends import LateralRelationshipBackend
from adapters.persistence.neo4j.neo4j_content_adapter import Neo4jContentAdapter
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.ps_engagement_backend import PsEngagementBackend
from adapters.persistence.neo4j.query.cypher.semantic_queries import build_semantic_merge
from adapters.persistence.neo4j.user_relationship_backend import UserRelationshipBackend
from core.infrastructure.relationships.semantic_relationships import (
    RelationshipMetadata,
    SemanticRelationshipType,
    SemanticTriple,
)
from core.models.enums.entity_enums import EntityType
from core.models.ps_content.content import CurriculumContent
from core.models.relationship_names import RelationshipName
from core.services.lateral_relationships.lateral_relationship_service import (
    LateralRelationshipService,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

KU_WITH_BODY = "ku.g13.shadowed"
KU_PLAIN = "ku.g13.plain"
PS_WITH_BODY = "ps.g13.shadowed"
ABSENT_UID = "ku.g13.absent"
USER_UID = "user_g13_shadow"
ENGAGEMENT_UID = "engagement_g13_shadow"

_UIDS = [KU_WITH_BODY, KU_PLAIN, PS_WITH_BODY, ABSENT_UID, USER_UID]

# Deliberately unlabeled: the count must see the shadow's edges too.
_EDGES_BETWEEN = """
MATCH (a {uid: $a})-[r]->(b {uid: $b})
WHERE type(r) = $rel
RETURN count(r) AS edges
"""
_EDGES_ON_SHADOW = """
MATCH (c:Content {uid: $uid})-[r]-()
WHERE NOT type(r) IN ['HAS_CONTENT', 'HAS_CHUNK']
RETURN count(r) AS edges
"""
_NODES_ON_UID = "MATCH (n {uid: $uid}) RETURN count(n) AS nodes"


class _DriverConnection:
    """Adapts the driver fixture to the connection shape the content adapter wants."""

    def __init__(self, driver: AsyncDriver) -> None:
        self.driver = driver

    # boundary: cypher-params — mirrors the real execute_query signature this
    # double substitutes for; Cypher params are genuinely heterogeneous.
    async def execute_query(self, query: str, params: dict[str, Any] | None = None) -> list[Record]:
        async with self.driver.session() as session:
            result = await session.run(query, params or {})
            return [record async for record in result]


async def _scalar(driver: AsyncDriver, query: str, **params: Any) -> int:  # boundary: cypher-params
    async with driver.session() as session:
        record = await (await session.run(query, params)).single()
    assert record is not None
    return int(record[0])


@pytest_asyncio.fixture(loop_scope="session")
async def shadowed_graph(neo4j_driver):
    """Two Kus and a PathStep; the first Ku and the PathStep carry a body, so a shadow."""
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) WHERE n.uid IN $uids DETACH DELETE n", uids=_UIDS)
        await session.run(
            """
            CREATE (:Entity:Ku {uid: $ku_body, title: 'Shadowed', entity_type: $ku})
            CREATE (:Entity:Ku {uid: $ku_plain, title: 'Plain', entity_type: $ku})
            CREATE (:Entity:PathStep {uid: $ps, title: 'Step', entity_type: $path_step,
                                      status: 'published'})
            CREATE (:User {uid: $user, title: 'g13', username: 'g13'})
            """,
            ku_body=KU_WITH_BODY,
            ku_plain=KU_PLAIN,
            ps=PS_WITH_BODY,
            user=USER_UID,
            ku=EntityType.KU.value,
            path_step=EntityType.PATH_STEP.value,
        )
    adapter = Neo4jContentAdapter(_DriverConnection(neo4j_driver))
    for uid in (KU_WITH_BODY, PS_WITH_BODY):
        stored = await adapter.store_content_with_chunks(
            uid, CurriculumContent(unit_uid=uid, body="A body, so a shadow.", chunks=())
        )
        assert stored, f"content adapter failed to persist the body under {uid}"
    # Control: the shadow exists, so every one-edge assertion below is a real one.
    for uid in (KU_WITH_BODY, PS_WITH_BODY):
        assert await _scalar(neo4j_driver, _NODES_ON_UID, uid=uid) == 2
    assert await _scalar(neo4j_driver, _NODES_ON_UID, uid=KU_PLAIN) == 1
    yield
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) WHERE n.uid IN $uids DETACH DELETE n", uids=_UIDS)


@pytest.fixture
def executor(neo4j_driver) -> Neo4jQueryExecutor:
    return Neo4jQueryExecutor(neo4j_driver)


@pytest.mark.integration
@pytest.mark.usefixtures("shadowed_graph")
class TestLateralWriterAndReads:
    async def test_the_writer_leaves_one_edge_and_the_reads_one_row(
        self, neo4j_driver, executor: Neo4jQueryExecutor
    ) -> None:
        backend = LateralRelationshipBackend(executor=executor)
        service = LateralRelationshipService(backend=backend)

        created = await service.create_lateral_relationship(
            KU_WITH_BODY, KU_PLAIN, RelationshipName.PREREQUISITE_FOR
        )
        assert created.is_ok, created

        rel = RelationshipName.PREREQUISITE_FOR.value
        inverse = RelationshipName.REQUIRES_PREREQUISITE.value
        assert await _scalar(neo4j_driver, _EDGES_BETWEEN, a=KU_WITH_BODY, b=KU_PLAIN, rel=rel) == 1
        assert (
            await _scalar(neo4j_driver, _EDGES_BETWEEN, a=KU_PLAIN, b=KU_WITH_BODY, rel=inverse)
            == 1
        )
        assert await _scalar(neo4j_driver, _EDGES_ON_SHADOW, uid=KU_WITH_BODY) == 0

        rows = await backend.get_relationships(KU_WITH_BODY, rel, "outgoing")
        assert [row["related_uid"] for row in rows.value] == [KU_PLAIN]
        graph = await backend.get_relationship_graph(KU_WITH_BODY, rel, 1)
        assert [row["related_uid"] for row in graph.value] == [KU_PLAIN]

        # The delete reaches the one edge and reports the one it deleted.
        deleted = await service.delete_lateral_relationship(
            KU_WITH_BODY, KU_PLAIN, RelationshipName.PREREQUISITE_FOR
        )
        assert deleted.is_ok, deleted
        assert await _scalar(neo4j_driver, _EDGES_BETWEEN, a=KU_WITH_BODY, b=KU_PLAIN, rel=rel) == 0
        assert (
            await _scalar(neo4j_driver, _EDGES_BETWEEN, a=KU_PLAIN, b=KU_WITH_BODY, rel=inverse)
            == 0
        )


@pytest.mark.integration
@pytest.mark.usefixtures("shadowed_graph")
class TestEngagementOpener:
    async def test_opening_an_engagement_writes_one_edge(
        self, neo4j_driver, executor: Neo4jQueryExecutor
    ) -> None:
        backend = PsEngagementBackend(executor)

        opened = await backend.create_engagement_edge(
            USER_UID, PS_WITH_BODY, ENGAGEMENT_UID, "2026-10-10T00:00:00+00:00"
        )
        assert opened.is_ok, opened

        rel = RelationshipName.ENGAGED_WITH.value
        assert await _scalar(neo4j_driver, _EDGES_BETWEEN, a=USER_UID, b=PS_WITH_BODY, rel=rel) == 1
        assert await _scalar(neo4j_driver, _EDGES_ON_SHADOW, uid=PS_WITH_BODY) == 0

        active = await backend.find_active_engagement(USER_UID, PS_WITH_BODY)
        assert [row["uid"] for row in active.value] == [ENGAGEMENT_UID]


@pytest.mark.integration
@pytest.mark.usefixtures("shadowed_graph")
class TestSemanticTripleWriter:
    @staticmethod
    def _triple(obj: str) -> SemanticTriple:
        return SemanticTriple(
            subject=KU_WITH_BODY,
            predicate=SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
            object=obj,
            metadata=RelationshipMetadata(confidence=0.9),
        )

    async def test_the_merge_binds_the_entity_and_writes_one_edge(self, neo4j_driver) -> None:
        query, params = build_semantic_merge(self._triple(KU_PLAIN))
        async with neo4j_driver.session() as session:
            rows = [record async for record in await session.run(query, params)]
        assert len(rows) == 1

        rel = SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING.to_neo4j_name().value
        assert await _scalar(neo4j_driver, _EDGES_BETWEEN, a=KU_WITH_BODY, b=KU_PLAIN, rel=rel) == 1
        assert await _scalar(neo4j_driver, _EDGES_ON_SHADOW, uid=KU_WITH_BODY) == 0

    async def test_an_absent_endpoint_creates_nothing_and_returns_no_row(
        self, neo4j_driver
    ) -> None:
        query, params = build_semantic_merge(self._triple(ABSENT_UID))
        async with neo4j_driver.session() as session:
            rows = [record async for record in await session.run(query, params)]
        assert rows == []
        assert await _scalar(neo4j_driver, _NODES_ON_UID, uid=ABSENT_UID) == 0


@pytest.mark.integration
@pytest.mark.usefixtures("shadowed_graph")
class TestPinWriter:
    async def test_pinning_a_shadowed_ku_writes_one_edge(
        self, neo4j_driver, executor: Neo4jQueryExecutor
    ) -> None:
        backend = UserRelationshipBackend(executor)

        pinned = await backend.pin_entity(USER_UID, KU_WITH_BODY)
        assert pinned.is_ok, pinned

        rel = RelationshipName.PINNED.value
        assert await _scalar(neo4j_driver, _EDGES_BETWEEN, a=USER_UID, b=KU_WITH_BODY, rel=rel) == 1
        assert await _scalar(neo4j_driver, _EDGES_ON_SHADOW, uid=KU_WITH_BODY) == 0
