"""Real-Neo4j: a neighbourhood's summary reports what kind of entity each node is.

``GraphIntelligenceService.get_entity_context`` reads a task's every-edge neighbourhood,
and ``GraphContext.get_summary()`` names the origin's domain and every node's. Both come
from the stored ``entity_type``: the task's stored ``domain: knowledge`` (the model's
default) and the choice's ``domain: personal`` (a subject area) are what those nodes are
about, not what they are. The node domains are the ``domains`` of the JSON ``context``
that ``/api/{domain}/context`` returns.

Fixtures mirror the writers: a user-owned entity carries ``user_uid`` and its owner's
``OWNS`` edge; curriculum carries no owner.
"""

from __future__ import annotations

import pytest

from core.constants import GraphDepth
from core.models.enums import Domain
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid

P = "gcd."  # uid prefix for this module's fixture graph

ME = seed_user_uid("test_123")  # a User node the session's ``ensure_test_users`` keeps

CENTER = P + "task-center"
OTHER_TASK = P + "task-other"
CHOICE = P + "choice"
HABIT = P + "habit"
KU = P + "ku"
STEP = P + "step"


@pytest.fixture
def graph_intel(neo4j_driver) -> GraphIntelligenceService:
    return GraphIntelligenceService(build_production_backends(neo4j_driver)["cross_domain_backend"])


async def _seed(neo4j_driver) -> None:
    async with neo4j_driver.session() as s:
        # Both label orders; every activity stores the Entity model's default subject,
        # except the choice, which stores its own.
        owned = [
            (CENTER, "Task:Entity", "task", "knowledge"),
            (OTHER_TASK, "Entity:Task", "task", "knowledge"),
            (CHOICE, "Entity:Choice", "choice", "personal"),
            (HABIT, "Habit:Entity", "habit", "knowledge"),
        ]
        for uid, labels, etype, subject in owned:
            await s.run(
                f"CREATE (n:{labels} {{uid:$u, entity_type:$t, domain:$d, title:$u, "
                "user_uid:$o, status:'active', created_at:datetime()}) "
                "WITH n MATCH (u:User {uid:$o}) CREATE (u)-[:OWNS]->(n)",
                u=uid,
                t=etype,
                d=subject,
                o=ME,
            )
        await s.run(
            "CREATE (:Entity:Ku {uid:$u, entity_type:'ku', title:$u, created_at:datetime()})",
            u=KU,
        )
        await s.run(
            "CREATE (:Entity:PathStep {uid:$u, entity_type:'path_step', domain:'spiritual', "
            "title:$u, created_at:datetime()})",
            u=STEP,
        )
        for edge, target in [
            ("DEPENDS_ON", OTHER_TASK),
            ("IMPLEMENTS_CHOICE", CHOICE),
            ("REQUIRES_HABIT", HABIT),
            ("APPLIES_KNOWLEDGE", KU),
            ("APPLIES_KNOWLEDGE", STEP),
        ]:
            await s.run(
                f"MATCH (a {{uid:$a}}), (b {{uid:$b}}) CREATE (a)-[:{edge}]->(b)",
                a=CENTER,
                b=target,
            )


@pytest.mark.asyncio
async def test_the_summary_names_each_nodes_kind(neo4j_driver, graph_intel, clean_neo4j):
    await _seed(neo4j_driver)

    result = await graph_intel.get_entity_context(CENTER, GraphDepth.DIRECT)

    assert result.is_ok, result
    context = result.value
    assert {n.uid: n.domain for n in context.all_nodes} == {
        OTHER_TASK: Domain.TASKS,
        CHOICE: Domain.CHOICES,
        HABIT: Domain.HABITS,
        KU: Domain.KNOWLEDGE,
        STEP: Domain.LEARNING,
        ME: Domain.SYSTEM,
    }
    summary = context.get_summary()
    assert summary["origin"] == f"tasks:{CENTER}"
    assert sorted(summary["domains"]) == sorted(
        ["tasks", "choices", "habits", "knowledge", "learning", "system"]
    )
    assert summary["cross_domain"] is True
