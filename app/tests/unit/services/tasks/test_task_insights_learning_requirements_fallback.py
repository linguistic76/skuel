"""Branch-selection guard for the Task insights learning-requirements source.

``get_domain_insights`` builds its ``learning_requirements`` block from the typed
cross-domain reader's ``required_knowledge`` when that block is available, but must fall
back to the graph-intel ``prerequisites`` source when the typed reader is unavailable —
otherwise a task with required knowledge would falsely report ``ready_to_start=True`` /
no gaps while the sibling ``has_prerequisites`` readiness lens says otherwise (Codex P2).

This exercises pure orchestration (which source feeds the helper), so a lightweight
in-memory harness is appropriate; the real-Cypher composition is covered by
tests/integration/test_tasks_analytics_pipeline.py.
"""

from __future__ import annotations

from typing import Any

import pytest

import core.utils.intelligence_queries as intelligence_queries
from core.models.task.task import Task
from core.services.tasks.tasks_intelligence_service import TasksIntelligenceService
from core.utils.logging import get_logger
from core.utils.result_simplified import Result


class _FakeBackend:
    async def get(self, _uid: str) -> Result[Task]:
        return Result.ok(Task(uid="t1", title="Write the report", user_uid="u1"))


class _Harness:
    """Binds the real ``get_domain_insights`` onto a minimal object; the cross-domain block
    is stubbed per-test so we control the available/unavailable branch without Neo4j."""

    get_domain_insights = TasksIntelligenceService.get_domain_insights

    def __init__(self, cross_domain_block: dict[str, Any]) -> None:
        self.backend = _FakeBackend()
        self.graph_intel = object()  # non-None so the prerequisites call runs
        self.logger = get_logger("test.tasks.intel.fallback")
        self._cross_domain_block = cross_domain_block

    async def _build_cross_domain_block(self, _uid: str, _min_confidence: float) -> dict[str, Any]:
        return self._cross_domain_block


def _patch_prereqs(monkeypatch: pytest.MonkeyPatch, *uids: str) -> None:
    async def _fake(graph: Any, entity_uid: Any, depth: Any) -> Result[dict[str, Any]]:
        return Result.ok(
            {
                "required_knowledge": [{"uid": u} for u in uids],
                "learning_path": [],
                "estimated_prep_time": "5 hours",
            }
        )

    monkeypatch.setattr(intelligence_queries, "get_knowledge_prerequisites", _fake)


@pytest.mark.asyncio
async def test_falls_back_to_prereqs_when_cross_domain_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_prereqs(monkeypatch, "ku_pre")
    unavailable = {"available": False, "context": {}, "metrics": {}, "recommendations": []}
    svc = _Harness(unavailable)

    res = await svc.get_domain_insights("t1")
    assert res.is_ok, res
    lr = res.value["learning_requirements"]
    # Sourced from the prerequisites fallback, NOT the empty unavailable block.
    assert [k["uid"] for k in lr["knowledge_requirements"]["required_knowledge"]] == ["ku_pre"]
    assert lr["learning_analysis"]["has_prerequisites"] is True
    assert lr["learning_analysis"]["ready_to_start"] is False
    # Consistent with the top-level readiness lens (no contradiction).
    assert res.value["has_prerequisites"] is True


@pytest.mark.asyncio
async def test_prefers_cross_domain_source_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_prereqs(monkeypatch, "ku_pre")  # should be ignored when cross-domain is available
    available = {
        "available": True,
        "context": {"required_knowledge": ["ku_cd"]},
        "metrics": {},
        "recommendations": [],
    }
    svc = _Harness(available)

    res = await svc.get_domain_insights("t1")
    assert res.is_ok, res
    lr = res.value["learning_requirements"]
    assert [k["uid"] for k in lr["knowledge_requirements"]["required_knowledge"]] == ["ku_cd"]
