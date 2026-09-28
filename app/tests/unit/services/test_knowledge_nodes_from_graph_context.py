"""The two knowledge readers of an entity's graph context read only knowledge.

``get_learning_opportunities`` and ``get_knowledge_prerequisites`` both walk an
entity's neighbourhood (``GraphIntelligenceService.get_entity_context``) and keep
the nodes that are curriculum knowledge. That neighbourhood is every edge type,
both directions, with no owner scoping — so a neighbour two hops out through a
shared Ku can be another user's Task. The filter is ``GraphContext.
get_knowledge_nodes()``: kind from the stored ``entity_type``
(``EntityType.is_knowledge()`` — Ku, PathStep), never the ``:Entity`` label every
node carries.

The real-traversal half (two users' tasks sharing a Ku) is
``tests/integration/test_knowledge_reads_owner_isolation.py``.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from core.models.enums import Domain, EntityType
from core.models.graph_context import ContextRelevance, GraphContext, GraphNode
from core.models.task.task import Task
from core.models.type_hints import Neo4jProperties, Neo4jValue
from core.services.knowledge.activity_knowledge_intelligence_service import (
    ActivityKnowledgeIntelligenceService,
)
from core.utils.intelligence_queries import get_knowledge_prerequisites
from core.utils.result_simplified import Result

ORIGIN = "task_mine"


def _node(uid: str, entity_type: EntityType, labels: list[str]) -> GraphNode:
    return GraphNode(
        uid=uid,
        labels=labels,
        domain=Domain.KNOWLEDGE,
        properties={"uid": uid, "title": f"title of {uid}", "entity_type": entity_type.value},
        distance_from_origin=1,
        relevance=ContextRelevance.MEDIUM,
    )


def _context() -> GraphContext:
    nodes = [
        _node("ku.sel.focus", EntityType.KU, ["Entity", "Ku"]),
        _node("ps.sel.attention", EntityType.PATH_STEP, ["Entity", "PathStep"]),
        # Two hops out through the shared Ku — another user's task.
        _node("task_theirs", EntityType.TASK, ["Entity", "Task"]),
        _node("goal_mine", EntityType.GOAL, ["Entity", "Goal"]),
    ]
    return GraphContext(
        origin_uid=ORIGIN,
        origin_domain=Domain.TASKS,
        query_intent="relationship",
        all_nodes=nodes,
        all_relationships=[],
        domain_contexts={},
        cross_domain_insights=[],
        relationship_patterns={},
        total_nodes=len(nodes),
        total_relationships=0,
        domains_involved=[Domain.KNOWLEDGE],
        max_depth_reached=2,
        query_timestamp=datetime(2026, 9, 28),
    )


class _FakeCrossDomainBackend:
    async def get_ku_titles_and_tags(self) -> Result[list[Neo4jProperties]]:
        return Result.ok([])


class _FakeGraphIntel:
    backend = _FakeCrossDomainBackend()

    async def get_entity_context(self, entity_uid: str, depth: int = 2) -> Result[GraphContext]:
        return Result.ok(_context())


class _FakeBackend:
    async def find_by(self, limit: int = 100, **filters: Neo4jValue) -> Result[list[Task]]:
        return Result.ok([Task(uid=ORIGIN, title="Practise focus", user_uid="user_mine")])


def test_knowledge_nodes_are_the_knowledge_entity_types() -> None:
    assert [n.uid for n in _context().get_knowledge_nodes()] == [
        "ku.sel.focus",
        "ps.sel.attention",
    ]


@pytest.mark.asyncio
async def test_learning_opportunities_name_only_knowledge() -> None:
    service = ActivityKnowledgeIntelligenceService(
        backend=_FakeBackend(),
        graph_intel=_FakeGraphIntel(),
    )

    result = await service.get_learning_opportunities("user_mine")

    assert result.is_ok, result
    gaps = [o for o in result.value["opportunities"] if o["type"] == "knowledge_gap"]
    assert gaps == [
        {
            "type": "knowledge_gap",
            "title": "Learn concepts for: Practise focus",
            "entity_uid": ORIGIN,
            "required_knowledge": ["title of ku.sel.focus", "title of ps.sel.attention"],
            "priority": "medium",
        }
    ]


@pytest.mark.asyncio
async def test_prerequisites_name_only_knowledge() -> None:
    result = await get_knowledge_prerequisites(
        graph=_FakeGraphIntel(),
        entity_uid=ORIGIN,
    )

    assert result.is_ok, result
    assert [item["uid"] for item in result.value["required_knowledge"]] == [
        "ku.sel.focus",
        "ps.sel.attention",
    ]
