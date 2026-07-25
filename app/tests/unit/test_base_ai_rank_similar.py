"""Unit tests for BaseAIService._rank_similar_entities (DRY arc #2).

Locks in the shared find_similar_* ranking tail extracted from the 8 domain AI
services: source exclusion, canonical embedding text for BOTH query and candidates
(the divergence fix — every domain now uses build_embedding_text), and the
empty-pool short-circuit that never touches embeddings.

Uses real ``Task`` domain models as doubles so the ``DomainModelProtocol`` contract
of the helper is genuinely exercised (not bypassed with ``Any`` stand-ins).
"""

from __future__ import annotations

import pytest

from core.models.enums.entity_enums import EntityType
from core.models.task.task import Task
from core.models.type_hints import EntityUID
from core.services.base_ai_service import BaseAIService
from core.utils.embedding_text_builder import build_embedding_text
from core.utils.result_simplified import Result


class _StubAIService(BaseAIService[object, Task]):
    _service_name = "test.ai"


@pytest.fixture
def service() -> _StubAIService:
    return _StubAIService(backend=object())


@pytest.mark.asyncio
async def test_rank_similar_excludes_source_and_uses_canonical_text(
    service: _StubAIService, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured_query = ""
    captured_candidates: list[tuple[EntityUID, str]] = []
    captured_top_k = 0

    async def fake_semantic_search(
        query: str, candidates: list[tuple[EntityUID, str]], top_k: int = 5
    ) -> Result[list[tuple[EntityUID, float]]]:
        nonlocal captured_query, captured_candidates, captured_top_k
        captured_query = query
        captured_candidates = candidates
        captured_top_k = top_k
        return Result.ok([(EntityUID("task.2"), 0.9)])

    monkeypatch.setattr(service, "_semantic_search", fake_semantic_search)

    source = Task(uid="task.1", title="Learn Python", description="the basics", user_uid="user_1")
    other = Task(uid="task.2", title="Master Python", description="advanced", user_uid="user_1")

    result = await service._rank_similar_entities(
        source, EntityType.TASK, [source, other], exclude_uid="task.1", limit=3
    )

    assert result.is_ok
    # The source is excluded and the candidate text is the canonical build_embedding_text
    assert captured_candidates == [
        (EntityUID("task.2"), build_embedding_text(EntityType.TASK, other))
    ]
    # Query text is canonical for the source — the divergence fix (all domains use this now)
    assert captured_query == build_embedding_text(EntityType.TASK, source)
    assert captured_top_k == 3


@pytest.mark.asyncio
async def test_rank_similar_empty_pool_short_circuits(
    service: _StubAIService, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = False

    async def fail_if_called(
        query: str, candidates: list[tuple[EntityUID, str]], top_k: int = 5
    ) -> Result[list[tuple[EntityUID, float]]]:
        nonlocal called
        called = True
        return Result.ok([])

    monkeypatch.setattr(service, "_semantic_search", fail_if_called)

    source = Task(uid="task.1", title="Solo", description="", user_uid="user_1")
    result = await service._rank_similar_entities(
        source, EntityType.TASK, [source], exclude_uid="task.1", limit=5
    )

    assert result.is_ok
    assert result.value == []
    assert called is False  # an empty candidate pool never reaches embeddings
