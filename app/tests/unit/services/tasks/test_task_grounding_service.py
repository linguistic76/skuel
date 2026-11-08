"""TaskGroundingService: the Task source of the one grounding pass.

The pass itself is ``KnowledgeGroundingService``'s, held by
``tests/unit/test_entry_grounding_service.py``. What the Task source adds:

- A NEW inferred edge publishes ``KnowledgeAppliedInTask``, the event a task's own
  knowledge link publishes, carrying the task and its owner.
- The judge reads the task's title and description through ``task_ku_grounding_judge``.
- ``EmbeddingStored`` for a task grounds every pending task of that task's owner —
  the stored one, and any whose last pass failed; for any other type, nothing runs.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.events.embedding_events import EmbeddingStored
from core.events.knowledge_substance_events import KnowledgeAppliedInTask
from core.models.enums.entity_enums import EntityType
from core.ports.query_types import GroundingSourceRow
from core.services.tasks.task_grounding_service import TaskGroundingService
from core.utils.result_simplified import Result


def _row(uid: str = "task_0000000000000001") -> GroundingSourceRow:
    return GroundingSourceRow(
        uid=uid,
        user_uid="user_0000000000000001",
        title="Sit with the breath for ten minutes",
        content="Morning practice before work: notice the breath, return when the mind wanders.",
        embedding=[0.1, 0.2, 0.3],
        embedding_text_hash="hash-task",
        applied_ku_uids=[],
        rejected_ku_uids=[],
    )


def _backend(rows: list[GroundingSourceRow]) -> MagicMock:
    backend = MagicMock()
    backend.get_pending = AsyncMock(return_value=Result.ok(rows))
    backend.write_applies_knowledge = AsyncMock(return_value=Result.ok(True))
    backend.stamp_grounded = AsyncMock(return_value=Result.ok(None))
    return backend


def _vector(ku_uid: str = "ku.mind.attention", score: float = 0.81) -> MagicMock:
    vector = MagicMock()
    vector.find_similar_by_vector = AsyncMock(
        return_value=Result.ok([{"node": {"uid": ku_uid, "title": "Attention"}, "score": score}])
    )
    return vector


def _bus() -> MagicMock:
    bus = MagicMock()
    bus.publish_async = AsyncMock()
    return bus


@pytest.mark.anyio
async def test_a_new_inferred_edge_publishes_knowledge_applied_in_task() -> None:
    bus = _bus()
    backend = _backend([_row()])
    service = TaskGroundingService(backend=backend, vector_search=_vector(), event_bus=bus)

    result = await service.ground_pending()

    assert result.is_ok, result
    backend.write_applies_knowledge.assert_awaited_once_with(
        "task_0000000000000001", "ku.mind.attention", 0.81
    )
    applied = [
        call.args[0]
        for call in bus.publish_async.await_args_list
        if isinstance(call.args[0], KnowledgeAppliedInTask)
    ]
    assert len(applied) == 1
    event = applied[0]
    assert isinstance(event, KnowledgeAppliedInTask)
    assert event.knowledge_uid == "ku.mind.attention"
    assert event.task_uid == "task_0000000000000001"
    assert event.user_uid == "user_0000000000000001"
    assert event.task_title == "Sit with the breath for ten minutes"


@pytest.mark.anyio
async def test_the_judge_reads_the_tasks_title_and_description() -> None:
    completion = MagicMock()
    completion.text = json.dumps([{"index": 1, "engages": True, "rationale": "practises it"}])
    llm = MagicMock()
    llm.caller.complete = AsyncMock(return_value=Result.ok(completion))
    service = TaskGroundingService(
        backend=_backend([_row()]), vector_search=_vector(), event_bus=_bus(), llm_service=llm
    )

    result = await service.ground_pending()

    assert result.is_ok, result
    assert result.value.judged
    prompt = llm.caller.complete.await_args.args[0][0]["content"]
    assert "one of a user's tasks" in prompt
    assert "Title: Sit with the breath for ten minutes" in prompt
    assert "notice the breath, return when the mind wanders" in prompt
    assert '1. "Attention" (similarity 0.81)' in prompt


@pytest.mark.anyio
async def test_a_stored_task_embedding_grounds_its_owners_pending_tasks() -> None:
    backend = _backend([])
    service = TaskGroundingService(backend=backend, vector_search=_vector(), event_bus=_bus())

    await service.handle_embedding_stored(
        EmbeddingStored(entity_uid="task_0000000000000009", entity_type=EntityType.TASK.value)
    )

    backend.get_pending.assert_awaited_once_with(
        user_uid=None, force=False, source_uid=None, owner_of="task_0000000000000009"
    )


@pytest.mark.anyio
async def test_another_types_stored_embedding_grounds_nothing() -> None:
    backend = _backend([_row()])
    service = TaskGroundingService(backend=backend, vector_search=_vector(), event_bus=_bus())

    await service.handle_embedding_stored(
        EmbeddingStored(entity_uid="goal_0000000000000001", entity_type=EntityType.GOAL.value)
    )

    backend.get_pending.assert_not_awaited()
    backend.write_applies_knowledge.assert_not_awaited()
