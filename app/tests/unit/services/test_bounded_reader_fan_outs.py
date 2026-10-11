"""
Per-entity graph reads over a user's set run a bounded number at a time.
========================================================================

Two reads have no batch form: a principle's alignment evidence and an entity's
graph context. Over a user's whole set they run through ``gather_bounded`` —
concurrently, never more than ``RelationshipFanOut.MAX_ENTITIES_IN_FLIGHT`` in
flight — and every entity is still read once.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from core.constants import RelationshipFanOut
from core.models.enums.entity_enums import EntityType
from core.models.enums.principle_enums import PrincipleCategory
from core.models.principle.principle import Principle
from core.models.task.task import Task
from core.services.knowledge.activity_knowledge_intelligence_service import (
    ActivityKnowledgeIntelligenceService,
)
from core.services.principles.principles_alignment_service import PrinciplesAlignmentService
from core.utils.result_simplified import Errors, Result

USER = "user_fan_out"
COUNT = 12


class _ReadRecorder:
    """Stands in for one per-entity read: records each uid and the peak in flight."""

    def __init__(self) -> None:
        self.uids: list[str] = []
        self.now = 0
        self.peak = 0

    async def read(self, uid: str, *_args: object) -> Result[object]:
        self.uids.append(uid)
        self.now += 1
        self.peak = max(self.peak, self.now)
        await asyncio.sleep(0)
        self.now -= 1
        return Result.fail(Errors.not_found("Context"))


@pytest.mark.asyncio
async def test_principle_evidence_reads_are_bounded() -> None:
    principles = [
        Principle(
            uid=f"principle_{i}",
            user_uid=USER,
            title=f"Principle {i}",
            statement="Act on it",
            principle_category=PrincipleCategory.PERSONAL,
        )
        for i in range(COUNT)
    ]
    backend = AsyncMock()
    backend.find_by = AsyncMock(return_value=Result.ok(principles))
    recorder = _ReadRecorder()
    cross_domain_query = AsyncMock()
    cross_domain_query.get_principle_alignment_evidence = recorder.read
    service = PrinciplesAlignmentService(backend=backend, cross_domain_query=cross_domain_query)

    result = await service.assess_goal_alignment("goal_1", USER)

    assert result.is_ok, result
    assert sorted(recorder.uids) == sorted(p.uid for p in principles)
    assert recorder.peak == RelationshipFanOut.MAX_ENTITIES_IN_FLIGHT
    assert result.value.entity_type == EntityType.GOAL


class _Backend:
    async def find_by(self, limit: int = 100, **_filters: object) -> Result[list[Task]]:
        return Result.ok(
            [Task(uid=f"task_{i}", title=f"Task {i}", user_uid=USER) for i in range(COUNT)]
        )


class _GraphIntel:
    def __init__(self, recorder: _ReadRecorder) -> None:
        self.get_entity_context = recorder.read
        self.backend = AsyncMock()
        self.backend.get_ku_titles_and_tags = AsyncMock(return_value=Result.ok([]))


@pytest.mark.asyncio
async def test_learning_opportunity_context_reads_are_bounded() -> None:
    recorder = _ReadRecorder()
    service = ActivityKnowledgeIntelligenceService(
        backend=_Backend(), graph_intel=_GraphIntel(recorder)
    )

    result = await service.get_learning_opportunities(USER)

    assert result.is_ok, result
    assert sorted(recorder.uids) == sorted(f"task_{i}" for i in range(COUNT))
    assert recorder.peak == RelationshipFanOut.MAX_ENTITIES_IN_FLIGHT
