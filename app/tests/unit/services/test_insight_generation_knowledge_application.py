"""Tests for the graph-native knowledge-application pattern detector.

Guards the rewired ``InsightGenerationService._analyze_knowledge_application_patterns``
(see /docs/patterns/KNOWLEDGE_APPLICATION_TRACKING.md): it must fetch APPLIES_KNOWLEDGE
edges via the relationship service — never a node property — and emit a
``KNOWLEDGE_APPLICATION`` pattern only when the knowledge-applying cohort is meaningfully
more efficient.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.models.enums import EntityStatus, Priority
from core.models.insight import PatternType
from core.models.task.task import Task
from core.services.insight.insight_generation_service import InsightGenerationService
from core.utils.result_simplified import Result


class _FakeRelationshipService:
    """Minimal stand-in for UnifiedRelationshipService.

    Implements ``batch_get_related_uids(key, uids)`` — the single-query path the
    detector uses — returning the seeded knowledge UIDs per task for the
    ``"knowledge"`` key and empty lists for any other relationship key.
    """

    def __init__(self, knowledge_by_task: dict[str, list[str]]) -> None:
        self._knowledge_by_task = knowledge_by_task

    async def batch_get_related_uids(
        self, relationship_key: str, entity_uids: list[str]
    ) -> Result[dict[str, list[str]]]:
        if relationship_key != "knowledge":
            return Result.ok({uid: [] for uid in entity_uids})
        return Result.ok({uid: list(self._knowledge_by_task.get(uid, [])) for uid in entity_uids})


def _task(uid: str, *, actual: int, estimated: int) -> Task:
    """A completed task whose efficiency is driven by actual-vs-estimated minutes."""
    return Task(
        uid=uid,
        title=uid,
        user_uid="user_test",
        status=EntityStatus.COMPLETED,
        priority=Priority.MEDIUM,
        duration_minutes=estimated,
        actual_minutes=actual,
    )


def _service(knowledge_by_task: dict[str, list[str]] | None = None) -> InsightGenerationService:
    rel = _FakeRelationshipService(knowledge_by_task or {})
    return InsightGenerationService(tasks_service=SimpleNamespace(relationships=rel))


async def test_emits_pattern_when_knowledge_cohort_more_efficient() -> None:
    # 3 knowledge tasks finish on time (efficiency 1.0); 3 others overrun (efficiency 0.5).
    knowledge = {f"k{i}": ["ku_python"] for i in range(3)}
    tasks = [_task(f"k{i}", actual=10, estimated=10) for i in range(3)]
    tasks += [_task(f"n{i}", actual=20, estimated=10) for i in range(3)]

    patterns = await _service(knowledge)._analyze_knowledge_application_patterns(tasks)

    assert len(patterns) == 1
    pattern = patterns[0]
    assert pattern.pattern_type is PatternType.KNOWLEDGE_APPLICATION
    assert sorted(pattern.supporting_tasks) == ["k0", "k1", "k2"]
    assert pattern.knowledge_uids_involved == ["ku_python"]
    assert pattern.metadata["knowledge_benefit"] > 1.1


async def test_no_pattern_without_knowledge_edges() -> None:
    # Edges absent → no cohort to compare, regardless of efficiency.
    tasks = [_task(f"t{i}", actual=10, estimated=10) for i in range(4)]
    patterns = await _service({})._analyze_knowledge_application_patterns(tasks)
    assert patterns == []


async def test_no_pattern_below_frequency_threshold() -> None:
    # Only 2 knowledge tasks (< min_pattern_frequency=3) → suppressed.
    knowledge = {f"k{i}": ["ku_python"] for i in range(2)}
    tasks = [_task(f"k{i}", actual=10, estimated=10) for i in range(2)]
    tasks += [_task(f"n{i}", actual=20, estimated=10) for i in range(3)]
    patterns = await _service(knowledge)._analyze_knowledge_application_patterns(tasks)
    assert patterns == []


async def test_no_pattern_when_no_efficiency_benefit() -> None:
    # Knowledge cohort is no more efficient than the whole → no claim.
    knowledge = {f"k{i}": ["ku_python"] for i in range(3)}
    tasks = [_task(f"k{i}", actual=10, estimated=10) for i in range(3)]
    tasks += [_task(f"n{i}", actual=10, estimated=10) for i in range(3)]
    patterns = await _service(knowledge)._analyze_knowledge_application_patterns(tasks)
    assert patterns == []


async def test_graceful_when_no_relationship_service() -> None:
    # tasks_service unwired → degrade to empty, never raise.
    svc = InsightGenerationService()
    tasks = [_task(f"t{i}", actual=10, estimated=10) for i in range(4)]
    assert await svc._analyze_knowledge_application_patterns(tasks) == []


async def test_bootstrap_late_wire_activates_detector() -> None:
    """Pins the production wiring contract (services_bootstrap/compose.py).

    The generator is constructed with no ``tasks_service`` (true circular dependency:
    it is built before TasksService). Bootstrap then assigns the facade back onto it.
    Before that assignment the detector is dead; after it, it works — so the
    back-reference is load-bearing, not decorative.
    """
    knowledge = {f"k{i}": ["ku_python"] for i in range(3)}
    tasks = [_task(f"k{i}", actual=10, estimated=10) for i in range(3)]
    tasks += [_task(f"n{i}", actual=20, estimated=10) for i in range(3)]

    # Constructed bare, exactly like compose.py `InsightGenerationService()`.
    svc = InsightGenerationService()
    assert await svc._analyze_knowledge_application_patterns(tasks) == []

    # Bootstrap late-wire: `ku_generation_service.tasks_service = tasks_service`.
    svc.tasks_service = SimpleNamespace(relationships=_FakeRelationshipService(knowledge))
    patterns = await svc._analyze_knowledge_application_patterns(tasks)
    assert len(patterns) == 1
    assert patterns[0].pattern_type is PatternType.KNOWLEDGE_APPLICATION


@pytest.mark.parametrize("benefit_ratio_pattern", ["knowledge_application_benefit"])
async def test_pattern_id_drives_learning_insight(benefit_ratio_pattern: str) -> None:
    # The detected pattern must flow through to a LEARNING insight end-to-end.
    knowledge = {f"k{i}": ["ku_python", "ku_async"] for i in range(3)}
    tasks = [_task(f"k{i}", actual=10, estimated=10) for i in range(3)]
    tasks += [_task(f"n{i}", actual=20, estimated=10) for i in range(3)]
    svc = _service(knowledge)

    result = await svc.analyze_task_completion_patterns(tasks)
    assert result.is_ok
    ka_patterns = [p for p in result.value if p.pattern_type is PatternType.KNOWLEDGE_APPLICATION]
    assert len(ka_patterns) == 1
    assert benefit_ratio_pattern in ka_patterns[0].pattern_id

    insights_result = svc.generate_insights_from_patterns(ka_patterns)
    assert insights_result.is_ok
    assert any(i.title == "Knowledge Application Drives Efficiency" for i in insights_result.value)
