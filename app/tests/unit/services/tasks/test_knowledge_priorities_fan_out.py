"""
The Tasks knowledge pipeline fetches relationships for the tasks it scores.

``calculate_knowledge_aware_priorities`` reads the user's whole task set, and a
per-task relationship fetch costs a dozen graph queries. These tests hold the
fetches to the tasks whose relationships are read — the ones being scored — and
to a bounded number in flight, whatever the size of the set.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from core.constants import RelationshipFanOut
from core.models.enums import EntityStatus
from core.models.task.task import Task
from core.services.tasks.task_relationships import TASK_KNOWLEDGE_KEYS, TaskRelationships
from core.services.tasks.tasks_intelligence_service import TasksIntelligenceService
from core.utils.result_simplified import Result

USER = "user_fan_out"
TASK_COUNT = 40
# Older than the learning-pattern window, so the pattern pass fetches nothing
# and every fetch counted below belongs to the priority pass.
CREATED = datetime.now(UTC) - timedelta(days=90)


def _tasks() -> list[Task]:
    return [
        Task(
            uid=f"task_{i}",
            title=f"Task {i}",
            user_uid=USER,
            status=EntityStatus.ACTIVE,
            created_at=CREATED,
            updated_at=CREATED,
        )
        for i in range(TASK_COUNT)
    ]


class _FetchRecorder:
    """Stands in for ``TaskRelationships.fetch``: records each uid and the peak in flight."""

    def __init__(self) -> None:
        self.uids: list[str] = []
        self.now = 0
        self.peak = 0

    async def fetch(self, task_uid: str, _service: object) -> TaskRelationships:
        self.uids.append(task_uid)
        self.now += 1
        self.peak = max(self.peak, self.now)
        await asyncio.sleep(0)
        self.now -= 1
        return TaskRelationships.empty()


@pytest.fixture
def recorder(monkeypatch) -> _FetchRecorder:
    recorder = _FetchRecorder()
    monkeypatch.setattr(TaskRelationships, "fetch", recorder.fetch)
    return recorder


@pytest.fixture
def intelligence() -> TasksIntelligenceService:
    backend = Mock()
    backend.find_by = AsyncMock(return_value=Result.ok(_tasks()))
    relationships = Mock()
    relationships.batch_get_related_uids = AsyncMock(return_value=Result.ok({}))
    return TasksIntelligenceService(backend=backend, relationship_service=relationships)


async def test_one_requested_task_fetches_one_tasks_relationships(intelligence, recorder):
    result = await intelligence.calculate_knowledge_aware_priorities(USER, task_uids=["task_7"])

    assert result.is_ok, result
    assert [priority.task_uid for priority in result.value] == ["task_7"]
    assert set(recorder.uids) == {"task_7"}


async def test_scoring_every_open_task_keeps_a_bounded_number_in_flight(intelligence, recorder):
    result = await intelligence.calculate_knowledge_aware_priorities(USER)

    assert result.is_ok, result
    assert len(result.value) == TASK_COUNT
    assert set(recorder.uids) == {f"task_{i}" for i in range(TASK_COUNT)}
    assert recorder.peak <= RelationshipFanOut.MAX_ENTITIES_IN_FLIGHT


async def test_mastery_progression_reads_the_whole_set_in_one_batch_per_key(intelligence, recorder):
    """The knowledge every task links is one batched read per relationship key, not a
    per-task relationship fetch."""
    result = await intelligence.track_knowledge_mastery_progression(USER)

    assert result.is_ok, result
    assert result.value == {}
    assert recorder.uids == []
    batch = intelligence.relationships.batch_get_related_uids
    assert [call.args[0] for call in batch.await_args_list] == list(TASK_KNOWLEDGE_KEYS)
    assert all(len(call.args[1]) == TASK_COUNT for call in batch.await_args_list)
