"""``BaseAIService._rank_similar_entities`` ranks the stored vectors.

The shared tail of the six Activity ``find_similar_*`` methods. Uses real
``Task`` models so the ``Entity.embedding`` contract is what the helper reads —
a candidate without a stored vector is left out, the source is embedded once
only when it has none, and an embedding failure is the ranking's failure.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.models.enums.entity_enums import EntityType
from core.models.task.task import Task
from core.models.type_hints import EntityUID
from core.services.base_ai_service import BaseAIService
from core.utils.embedding_text_builder import build_embedding_text
from core.utils.result_simplified import ErrorCategory, Errors, Result
from tests.fixtures.llm_doubles import embeddings_double


class _StubAIService(BaseAIService[object, Task]):
    _service_name = "test.ai"


def _task(uid: str, embedding: tuple[float, ...] | None) -> Task:
    return Task(uid=uid, title=uid, description="", user_uid="user_1", embedding=embedding)


def _service(create_embedding: AsyncMock | None = None) -> _StubAIService:
    return _StubAIService(backend=object(), embeddings_service=embeddings_double(create_embedding))


@pytest.mark.asyncio
async def test_ranks_stored_vectors_and_leaves_out_a_candidate_without_one() -> None:
    source = _task("task.src", (1.0, 0.0, 0.0))
    near = _task("task.near", (1.0, 0.1, 0.0))
    far = _task("task.far", (0.0, 1.0, 0.0))
    unembedded = _task("task.none", None)
    create_embedding = AsyncMock()
    service = _service(create_embedding)

    result = await service._rank_similar_entities(
        source,
        EntityType.TASK,
        [source, unembedded, far, near],
        exclude_uid="task.src",
        limit=5,
    )

    assert result.is_ok
    uids = [uid for uid, _ in result.value]
    assert uids == [EntityUID("task.near"), EntityUID("task.far")]
    scores = [score for _, score in result.value]
    assert scores[0] > scores[1]
    # the index's scale: orthogonal vectors score 0.5, not 0.0
    assert scores[1] == pytest.approx(0.5)
    # the source has a vector, so nothing is embedded
    create_embedding.assert_not_awaited()


@pytest.mark.asyncio
async def test_limit_keeps_the_top_of_the_ranking() -> None:
    source = _task("task.src", (1.0, 0.0))
    pool = [_task(f"task.{i}", (1.0, 0.1 * i)) for i in range(1, 5)]
    service = _service()

    result = await service._rank_similar_entities(
        source, EntityType.TASK, pool, exclude_uid="task.src", limit=2
    )

    assert result.is_ok
    assert [uid for uid, _ in result.value] == [EntityUID("task.1"), EntityUID("task.2")]


@pytest.mark.asyncio
async def test_source_without_a_vector_is_embedded_once_from_its_canonical_text() -> None:
    source = _task("task.src", None)
    candidate = _task("task.other", (0.0, 1.0))
    create_embedding = AsyncMock(return_value=Result.ok([0.0, 1.0]))
    service = _service(create_embedding)

    result = await service._rank_similar_entities(
        source, EntityType.TASK, [candidate], exclude_uid="task.src", limit=5
    )

    assert result.is_ok
    [(uid, score)] = result.value
    assert uid == EntityUID("task.other")
    assert score == pytest.approx(1.0)
    create_embedding.assert_awaited_once_with(build_embedding_text(EntityType.TASK, source))


@pytest.mark.asyncio
async def test_embedding_failure_is_the_rankings_failure() -> None:
    source = _task("task.src", None)
    candidate = _task("task.other", (0.0, 1.0))
    create_embedding = AsyncMock(
        return_value=Result.fail(Errors.integration(message="quota", service="embeddings"))
    )
    service = _service(create_embedding)

    result = await service._rank_similar_entities(
        source, EntityType.TASK, [candidate], exclude_uid="task.src", limit=5
    )

    assert result.is_error
    error = result.expect_error()
    assert error.category == ErrorCategory.INTEGRATION
    # the embedding client's own failure, not one the ranking manufactured
    assert "quota" in error.message


@pytest.mark.asyncio
async def test_empty_pool_short_circuits_before_any_embedding() -> None:
    source = _task("task.src", None)
    create_embedding = AsyncMock()
    service = _service(create_embedding)

    result = await service._rank_similar_entities(
        source, EntityType.TASK, [source, _task("task.none", None)], exclude_uid="task.src", limit=5
    )

    assert result.is_ok
    assert result.value == []
    create_embedding.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_embeddings_service_and_no_source_vector_is_unavailable() -> None:
    service = _StubAIService(backend=object())
    source = _task("task.src", None)

    result = await service._rank_similar_entities(
        source, EntityType.TASK, [_task("task.other", (1.0,))], exclude_uid="task.src", limit=5
    )

    assert result.is_error
    assert result.expect_error().category == ErrorCategory.SYSTEM
