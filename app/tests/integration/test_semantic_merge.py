"""``build_semantic_merge`` writes one edge between two entities, and nothing for an absent one.

Both endpoints are MATCHed and only the edge is MERGEd, so a triple naming a uid
that names no node creates no node and returns no row — the caller reads the
empty result as not found.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from adapters.persistence.neo4j.query.cypher.semantic_queries import build_semantic_merge
from core.infrastructure.relationships.semantic_relationships import (
    RelationshipMetadata,
    SemanticRelationshipType,
    SemanticTriple,
)
from core.models.enums.entity_enums import EntityType

pytestmark = pytest.mark.asyncio(loop_scope="session")

SUBJECT = "ku.semantic-merge.subject"
OBJECT = "ku.semantic-merge.object"
ABSENT_UID = "ku.semantic-merge.absent"
_UIDS = [SUBJECT, OBJECT, ABSENT_UID]
_PREDICATE = SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING

_EDGES_BETWEEN = """
MATCH (a:Entity {uid: $a})-[r]->(b:Entity {uid: $b})
WHERE type(r) = $rel
RETURN count(r) AS edges
"""
# Unlabeled: a bare node the MERGE created would carry no label.
_NODES_ON_UID = "MATCH (n {uid: $uid}) RETURN count(n) AS nodes"


async def _scalar(driver: AsyncDriver, query: str, **params: Any) -> int:  # boundary: cypher-params
    async with driver.session() as session:
        record = await (await session.run(query, params)).single()
    assert record is not None
    return int(record[0])


async def _merge(driver: AsyncDriver, obj: str) -> list[Any]:  # boundary: cypher-params
    query, params = build_semantic_merge(
        SemanticTriple(
            subject=SUBJECT,
            predicate=_PREDICATE,
            object=obj,
            metadata=RelationshipMetadata(confidence=0.9),
        )
    )
    async with driver.session() as session:
        return [record async for record in await session.run(query, params)]


@pytest_asyncio.fixture(loop_scope="session")
async def two_kus(neo4j_driver):
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) WHERE n.uid IN $uids DETACH DELETE n", uids=_UIDS)
        await session.run(
            """
            CREATE (:Entity:Ku {uid: $subject, title: 'Subject', entity_type: $ku})
            CREATE (:Entity:Ku {uid: $object, title: 'Object', entity_type: $ku})
            """,
            subject=SUBJECT,
            object=OBJECT,
            ku=EntityType.KU.value,
        )
    yield
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n) WHERE n.uid IN $uids DETACH DELETE n", uids=_UIDS)


@pytest.mark.usefixtures("two_kus")
async def test_the_merge_writes_one_edge_and_returns_one_row(neo4j_driver) -> None:
    rows = await _merge(neo4j_driver, OBJECT)
    assert len(rows) == 1

    rel = _PREDICATE.to_neo4j_name().value
    assert await _scalar(neo4j_driver, _EDGES_BETWEEN, a=SUBJECT, b=OBJECT, rel=rel) == 1


@pytest.mark.usefixtures("two_kus")
async def test_an_absent_endpoint_creates_nothing_and_returns_no_row(neo4j_driver) -> None:
    assert await _merge(neo4j_driver, ABSENT_UID) == []
    assert await _scalar(neo4j_driver, _NODES_ON_UID, uid=ABSENT_UID) == 0
