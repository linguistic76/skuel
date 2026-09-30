"""Curriculum similarity ranks through the vector-discovery chokepoint.

``PsAIService.find_similar_steps`` / ``LpAIService.find_similar_paths`` and
``PsAIService.search_by_semantic_query`` never rank a ``backend.list()`` pool:
the stored vector (or the canonical text, when there is none) goes to the
vector search service, whose index query withholds draft curriculum. The
integration half — a draft among the nearest neighbours is left out — is
``tests/integration/test_curriculum_similarity_drafts.py``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from core.config.unified_config import VectorSearchConfig
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.path_step import PathStep
from core.models.type_hints import EntityUID
from core.services.lp.lp_ai_service import LpAIService
from core.services.neo4j_vector_search_service import Neo4jVectorSearchService
from core.services.ps.ps_ai_service import PsAIService
from core.utils.embedding_text_builder import build_embedding_text
from core.utils.result_simplified import ErrorCategory, Errors, Result
from tests.fixtures.llm_doubles import embeddings_double, scripted_llm

VECTOR_SEARCH_NAMES = [
    name for name in dir(Neo4jVectorSearchService) if not name.startswith("_")
] + ["config"]


def _hit(uid: str, score: float) -> dict[str, object]:
    return {"node": {"uid": uid, "title": uid}, "score": score}


def _vector_search(
    by_vector: Result[list[dict[str, object]]] | None = None,
    by_text: Result[list[dict[str, object]]] | None = None,
) -> MagicMock:
    double = MagicMock(spec=VECTOR_SEARCH_NAMES)
    double.config = VectorSearchConfig()
    double.find_similar_by_vector = AsyncMock(return_value=by_vector or Result.ok([]))
    double.find_similar_by_text = AsyncMock(return_value=by_text or Result.ok([]))
    return double


def _ps_service(step: PathStep | None, vector_search: MagicMock) -> tuple[PsAIService, Mock]:
    backend = Mock()
    backend.get = AsyncMock(return_value=Result.ok(step))
    backend.list = AsyncMock(side_effect=AssertionError("the listing pool must not be read"))
    backend.search = AsyncMock(side_effect=AssertionError("no keyword fallback"))
    service = PsAIService(
        backend=backend,
        llm_service=scripted_llm(""),
        embeddings_service=embeddings_double(),
        vector_search=vector_search,
    )
    return service, backend


@pytest.mark.asyncio
async def test_find_similar_steps_ranks_the_stored_vector_and_drops_the_source() -> None:
    step = PathStep(uid="ps.x.src", title="Source", embedding=(1.0, 0.0))
    vector_search = _vector_search(
        by_vector=Result.ok([_hit("ps.x.src", 1.0), _hit("ps.x.a", 0.9), _hit("ps.x.b", 0.8)])
    )
    service, _ = _ps_service(step, vector_search)

    result = await service.find_similar_steps("ps.x.src", limit=2)

    assert result.is_ok
    assert result.value == [(EntityUID("ps.x.a"), 0.9), (EntityUID("ps.x.b"), 0.8)]
    vector_search.find_similar_by_vector.assert_awaited_once_with(
        label=NeoLabel.PATH_STEP,
        embedding=[1.0, 0.0],
        limit=3,
        min_score=VectorSearchConfig().ku_similar_min_score,
    )
    vector_search.find_similar_by_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_find_similar_steps_embeds_the_canonical_text_when_the_source_has_no_vector() -> None:
    step = PathStep(uid="ps.x.src", title="Source", intent="learn it", embedding=None)
    vector_search = _vector_search(by_text=Result.ok([_hit("ps.x.a", 0.85)]))
    service, _ = _ps_service(step, vector_search)

    result = await service.find_similar_steps("ps.x.src", limit=5)

    assert result.is_ok
    assert result.value == [(EntityUID("ps.x.a"), 0.85)]
    vector_search.find_similar_by_text.assert_awaited_once_with(
        label=NeoLabel.PATH_STEP,
        text=build_embedding_text(EntityType.PATH_STEP, step),
        limit=6,
        min_score=VectorSearchConfig().ku_similar_min_score,
    )
    vector_search.find_similar_by_vector.assert_not_awaited()


@pytest.mark.asyncio
async def test_find_similar_steps_unknown_uid_is_not_found() -> None:
    vector_search = _vector_search()
    service, _ = _ps_service(None, vector_search)

    result = await service.find_similar_steps("ps.x.missing")

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.NOT_FOUND
    vector_search.find_similar_by_vector.assert_not_awaited()


@pytest.mark.asyncio
async def test_find_similar_steps_index_failure_propagates() -> None:
    step = PathStep(uid="ps.x.src", title="Source", embedding=(1.0, 0.0))
    vector_search = _vector_search(
        by_vector=Result.fail(Errors.database(operation="vector_search", message="index gone"))
    )
    service, _ = _ps_service(step, vector_search)

    result = await service.find_similar_steps("ps.x.src")

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.DATABASE


@pytest.mark.asyncio
async def test_find_similar_paths_ranks_the_learning_path_index() -> None:
    path = LearningPath(uid="lp.x.src", title="Source", embedding=(0.0, 1.0))
    vector_search = _vector_search(by_vector=Result.ok([_hit("lp.x.a", 0.77)]))
    backend = Mock()
    backend.get = AsyncMock(return_value=Result.ok(path))
    backend.list = AsyncMock(side_effect=AssertionError("the listing pool must not be read"))
    service = LpAIService(
        backend=backend,
        llm_service=scripted_llm(""),
        embeddings_service=embeddings_double(),
        vector_search=vector_search,
    )

    result = await service.find_similar_paths("lp.x.src", limit=5)

    assert result.is_ok
    assert result.value == [(EntityUID("lp.x.a"), 0.77)]
    assert vector_search.find_similar_by_vector.await_args.kwargs["label"] == NeoLabel.LEARNING_PATH


@pytest.mark.asyncio
async def test_search_by_semantic_query_reads_the_hits_back_in_score_order() -> None:
    vector_search = _vector_search(
        by_text=Result.ok([_hit("ps.x.b", 0.9), _hit("ps.x.gone", 0.8), _hit("ps.x.a", 0.7)])
    )
    service, backend = _ps_service(None, vector_search)
    step_a = PathStep(uid="ps.x.a", title="A")
    step_b = PathStep(uid="ps.x.b", title="B")
    backend.get_many = AsyncMock(return_value=Result.ok([step_b, None, step_a]))

    result = await service.search_by_semantic_query("how to plan", limit=10, min_score=0.6)

    assert result.is_ok
    assert result.value == [step_b, step_a]
    vector_search.find_similar_by_text.assert_awaited_once_with(
        label=NeoLabel.PATH_STEP, text="how to plan", limit=10, min_score=0.6
    )
    backend.get_many.assert_awaited_once_with(["ps.x.b", "ps.x.gone", "ps.x.a"])


@pytest.mark.asyncio
async def test_search_by_semantic_query_embedding_failure_has_no_keyword_fallback() -> None:
    vector_search = _vector_search(
        by_text=Result.fail(Errors.integration(message="quota", service="embeddings"))
    )
    service, backend = _ps_service(None, vector_search)

    result = await service.search_by_semantic_query("how to plan")

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.INTEGRATION
    backend.search.assert_not_awaited()
