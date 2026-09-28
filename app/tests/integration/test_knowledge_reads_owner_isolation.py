"""Real-Neo4j guard: a knowledge read of my task names published knowledge — never
your task, never an unpublished Ku.

``get_entity_context`` walks every edge type, both directions, with no owner
scoping. Two users whose tasks apply the same Ku are therefore two hops apart,
so the reader's filter is the only thing between one user and the other's task
title in ``GET /api/tasks/insights``' ``knowledge_prerequisites``. Both knowledge
readers keep only ``GraphContext.get_published_knowledge_nodes()``, which also
withholds curriculum explicitly marked ``publication_state: draft``.

The in-memory guard is
``tests/unit/services/test_knowledge_nodes_from_graph_context.py``.
"""

from __future__ import annotations

import pytest

from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.constants import GraphDepth
from core.models.enums import PublicationState
from core.models.task.task import Task
from core.models.type_hints import Neo4jValue
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
from core.services.knowledge.activity_knowledge_intelligence_service import (
    ActivityKnowledgeIntelligenceService,
)
from core.utils.intelligence_queries import get_knowledge_prerequisites
from core.utils.result_simplified import Result

P = "koi_"  # uid prefix for this module's fixture graph

MY_TASK = P + "task_mine"
THEIR_TASK = P + "task_theirs"
KU = P + "ku"
DRAFT_KU = P + "ku_draft"


@pytest.fixture
def graph_intel(neo4j_driver):
    backend = CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver))
    return GraphIntelligenceService(backend)


async def _seed(neo4j_driver) -> None:
    async with neo4j_driver.session() as s:
        for uid, owner in [(MY_TASK, "user_mine"), (THEIR_TASK, "user_theirs")]:
            await s.run(
                "CREATE (:Entity:Task {uid:$u, entity_type:'task', title:$u, "
                "user_uid:$o, status:'active', created_at:datetime()})",
                u=uid,
                o=owner,
            )
        await s.run(
            "CREATE (:Entity:Ku {uid:$u, entity_type:'ku', title:$u, created_at:datetime()})",
            u=KU,
        )
        await s.run(
            "CREATE (:Entity:Ku {uid:$u, entity_type:'ku', title:$u, "
            "publication_state:$draft, created_at:datetime()})",
            u=DRAFT_KU,
            draft=PublicationState.DRAFT.value,
        )
        for task in (MY_TASK, THEIR_TASK):
            await s.run(
                "MATCH (t {uid:$t}), (k {uid:$k}) CREATE (t)-[:APPLIES_KNOWLEDGE]->(k)",
                t=task,
                k=KU,
            )
        await s.run(
            "MATCH (t {uid:$t}), (k {uid:$k}) CREATE (t)-[:APPLIES_KNOWLEDGE]->(k)",
            t=MY_TASK,
            k=DRAFT_KU,
        )


@pytest.mark.asyncio
async def test_prerequisites_of_my_task_omit_their_task(neo4j_driver, graph_intel, clean_neo4j):
    await _seed(neo4j_driver)

    # The traversal itself reaches their task and the draft — the filter keeps them out.
    context = await graph_intel.get_entity_context(MY_TASK, GraphDepth.DEFAULT)
    assert context.is_ok, context
    reached = [n.uid for n in context.value.all_nodes]
    assert THEIR_TASK in reached and DRAFT_KU in reached

    result = await get_knowledge_prerequisites(
        graph=graph_intel, entity_uid=MY_TASK, depth=GraphDepth.DEFAULT
    )

    assert result.is_ok, result
    assert [item["uid"] for item in result.value["required_knowledge"]] == [KU]


class _MyTasksBackend:
    async def find_by(self, limit: int = 100, **filters: Neo4jValue) -> Result[list[Task]]:
        return Result.ok([Task(uid=MY_TASK, title=MY_TASK, user_uid="user_mine")])


@pytest.mark.asyncio
async def test_learning_opportunities_of_my_task_omit_their_task(
    neo4j_driver, graph_intel, clean_neo4j
):
    await _seed(neo4j_driver)
    service = ActivityKnowledgeIntelligenceService(
        backend=_MyTasksBackend(), graph_intel=graph_intel
    )

    result = await service.get_learning_opportunities("user_mine")

    assert result.is_ok, result
    gaps = [o for o in result.value["opportunities"] if o["type"] == "knowledge_gap"]
    assert [(g["entity_uid"], g["required_knowledge"]) for g in gaps] == [(MY_TASK, [KU])]
