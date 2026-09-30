"""A curriculum similarity listing leaves draft-marked content out.

``PsAIService.find_similar_steps`` ranks through the PathStep vector index,
whose query is the vector-discovery chokepoint that withholds a node
explicitly marked ``publication_state: draft``. Seeds four steps whose
vectors put the draft nearest the source, and checks the ranking a learner
gets: the two published neighbours, in score order, on the index's scale.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.curriculum_backends import PsBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.vector_search_backend import VectorSearchBackend
from core.constants import EmbeddingGeometry
from core.models.enums.curriculum_enums import PublicationState
from core.models.enums.neo_labels import NeoLabel
from core.models.pathways.path_step import PathStep
from core.models.type_hints import EntityUID
from core.services.neo4j_vector_search_service import Neo4jVectorSearchService
from core.services.ps.ps_ai_service import PsAIService
from core.utils.result_simplified import Result
from core.utils.vector_math import normalized_cosine_similarity
from tests.fixtures.llm_doubles import embeddings_double, scripted_llm

DIM = EmbeddingGeometry.DIMENSION


def _vector(*head: float) -> list[float]:
    vector = [0.0] * DIM
    vector[: len(head)] = head
    return vector


SOURCE = _vector(1.0, 0.0)
DRAFT_NEAREST = _vector(1.0, 0.05)
PUBLISHED_NEAR = _vector(1.0, 0.2)
PUBLISHED_FAR = _vector(1.0, 0.6)


@pytest_asyncio.fixture
async def seeded_steps(neo4j_driver, clean_neo4j):
    async with neo4j_driver.session() as session:
        await session.run(
            f"""
            CREATE VECTOR INDEX pathstep_embedding_idx IF NOT EXISTS
            FOR (n:{NeoLabel.PATH_STEP}) ON (n.embedding)
            OPTIONS {{indexConfig: {{
                `vector.dimensions`: {DIM},
                `vector.similarity_function`: 'cosine'
            }}}}
            """
        )
        await session.run(
            f"""
            UNWIND $steps AS step
            CREATE (n:{NeoLabel.ENTITY}:{NeoLabel.PATH_STEP} {{
                uid: step.uid, title: step.uid, entity_type: 'path_step',
                status: 'active', created_at: datetime(), updated_at: datetime()
            }})
            SET n.publication_state = step.publication_state
            WITH n, step
            CALL db.create.setNodeVectorProperty(n, 'embedding', step.embedding)
            """,
            {
                "steps": [
                    {"uid": "ps.sim.source", "publication_state": None, "embedding": SOURCE},
                    {
                        "uid": "ps.sim.draft",
                        "publication_state": PublicationState.DRAFT.value,
                        "embedding": DRAFT_NEAREST,
                    },
                    {
                        "uid": "ps.sim.near",
                        "publication_state": PublicationState.PUBLISHED.value,
                        "embedding": PUBLISHED_NEAR,
                    },
                    {"uid": "ps.sim.far", "publication_state": None, "embedding": PUBLISHED_FAR},
                ]
            },
        )
        await session.run("CALL db.awaitIndexes(120)")
    yield


def _ps_ai(neo4j_driver, query_embedding: AsyncMock | None = None) -> PsAIService:
    executor = Neo4jQueryExecutor(neo4j_driver)
    embeddings = embeddings_double(
        query_embedding
        or AsyncMock(side_effect=AssertionError("a source with a stored vector is never embedded"))
    )
    vector_search = Neo4jVectorSearchService(VectorSearchBackend(executor=executor), embeddings)
    backend = PsBackend(neo4j_driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY)
    return PsAIService(
        backend=backend,
        llm_service=scripted_llm(""),
        embeddings_service=embeddings_double(),
        vector_search=vector_search,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_control_the_raw_index_holds_the_draft_nearest(neo4j_driver, seeded_steps):
    """Control: the draft IS the source's nearest neighbour in the index."""
    async with neo4j_driver.session() as session:
        result = await session.run(
            "CALL db.index.vector.queryNodes('pathstep_embedding_idx', 4, $vector) "
            "YIELD node, score RETURN node.uid AS uid ORDER BY score DESC",
            {"vector": SOURCE},
        )
        uids = [record["uid"] async for record in result]
    assert uids == ["ps.sim.source", "ps.sim.draft", "ps.sim.near", "ps.sim.far"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_similar_steps_leaves_the_draft_out(neo4j_driver, seeded_steps):
    service = _ps_ai(neo4j_driver)

    result = await service.find_similar_steps("ps.sim.source", limit=3)

    assert result.is_ok, result
    uids = [uid for uid, _ in result.value]
    assert uids == [EntityUID("ps.sim.near"), EntityUID("ps.sim.far")]
    scores = [score for _, score in result.value]
    assert scores == pytest.approx(
        [
            normalized_cosine_similarity(SOURCE, PUBLISHED_NEAR),
            normalized_cosine_similarity(SOURCE, PUBLISHED_FAR),
        ],
        abs=1e-5,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_similar_steps_unknown_uid_is_not_found(neo4j_driver, seeded_steps):
    service = _ps_ai(neo4j_driver)

    result = await service.find_similar_steps("ps.sim.missing")

    assert result.is_error
    assert result.expect_error().category.value == "not_found"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_search_by_semantic_query_leaves_the_draft_out(neo4j_driver, seeded_steps):
    service = _ps_ai(neo4j_driver, query_embedding=AsyncMock(return_value=Result.ok(SOURCE)))

    result = await service.search_by_semantic_query("anything", limit=10, min_score=0.5)

    assert result.is_ok, result
    assert [step.uid for step in result.value] == ["ps.sim.source", "ps.sim.near", "ps.sim.far"]
