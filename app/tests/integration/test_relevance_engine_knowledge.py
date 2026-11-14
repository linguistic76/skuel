"""Real-Neo4j guard: the relevance engine finds the published knowledge around my
activities — through knowledge only, never through another activity or another user.

A task that applies a Ku and contributes to a goal, a habit that reinforces the same
Ku, the Ku's prerequisite, and a PathStep that uses it. The engine reads each
activity's own links, then the knowledge one edge from those links. So:

- the goal's own Ku is credited to the goal when the goal is asked about, and never
  to the task that contributes to it;
- a draft Ku is not returned, nor another user's task that applies the same Ku;
- the prerequisite comes before the Ku that requires it in the recommended order.

The in-memory guard is ``tests/unit/services/test_context_relevance_engine.py``.
"""

from __future__ import annotations

import pytest

from core.models.enums import Domain, EntityType, KuComplexity, RelevanceRing
from core.services.askesis.context_relevance_engine import ContextRelevanceEngine
from core.services.infrastructure.graph_intelligence_service import GraphIntelligenceService
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid

P = "rlv."  # uid prefix for this module's fixture graph

ME = seed_user_uid("relevance-mine")
THEM = seed_user_uid("relevance-theirs")
TASK = P + "task-mine"
THEIR_TASK = P + "task-theirs"
HABIT = P + "habit-mine"
GOAL = P + "goal-mine"
KU = P + "ku"
PREREQUISITE = P + "ku-prerequisite"
GOAL_KU = P + "ku-goal"
DRAFT = P + "ku-draft"
STEP = P + "ps-step"


@pytest.fixture
def engine(neo4j_driver) -> ContextRelevanceEngine:
    backend = build_production_backends(neo4j_driver)["cross_domain_backend"]
    return ContextRelevanceEngine(graph_intel=GraphIntelligenceService(backend))


async def _seed(neo4j_driver) -> None:
    async with neo4j_driver.session() as s:
        for user in (ME, THEM):
            await s.run("MERGE (:User {uid:$u, title:$u})", u=user)
        for uid, label, entity_type, owner in [
            (TASK, "Task", "task", ME),
            (THEIR_TASK, "Task", "task", THEM),
            (HABIT, "Habit", "habit", ME),
            (GOAL, "Goal", "goal", ME),
        ]:
            await s.run(
                f"MATCH (u:User {{uid:$o}}) CREATE (u)-[:OWNS]->(:Entity:{label} "
                "{uid:$u, entity_type:$et, title:$u, user_uid:$o, status:'active', "
                "created_at:datetime()})",
                u=uid,
                et=entity_type,
                o=owner,
            )
        for uid in (KU, PREREQUISITE, GOAL_KU):
            await s.run(
                "CREATE (:Entity:Ku {uid:$u, entity_type:'ku', title:$u, created_at:datetime()})",
                u=uid,
            )
        await s.run(
            "CREATE (:Entity:Ku {uid:$u, entity_type:'ku', title:$u, "
            "publication_state:'draft', created_at:datetime()})",
            u=DRAFT,
        )
        await s.run(
            "CREATE (:Entity:PathStep {uid:$u, entity_type:'path_step', title:$u, "
            "domain:'health', complexity:'basic', publication_state:'published', "
            "created_at:datetime()})",
            u=STEP,
        )
        for start, rel, end in [
            (TASK, "APPLIES_KNOWLEDGE", KU),
            (TASK, "APPLIES_KNOWLEDGE", DRAFT),
            (THEIR_TASK, "APPLIES_KNOWLEDGE", KU),
            (HABIT, "REINFORCES_KNOWLEDGE", KU),
            (TASK, "CONTRIBUTES_TO_GOAL", GOAL),
            (GOAL, "REQUIRES_KNOWLEDGE", GOAL_KU),
            (KU, "REQUIRES_KNOWLEDGE", PREREQUISITE),
            (KU, "REQUIRES_KNOWLEDGE", DRAFT),
            (STEP, "USES_KU", KU),
        ]:
            await s.run(
                f"MATCH (a {{uid:$a}}), (b {{uid:$b}}) CREATE (a)-[:{rel}]->(b)", a=start, b=end
            )


@pytest.mark.asyncio
async def test_knowledge_around_my_activities_is_reached_through_knowledge_only(
    neo4j_driver, engine, clean_neo4j
):
    await _seed(neo4j_driver)

    result = await engine.find_relevant_for_context(
        current_habits=[HABIT], pending_tasks=[TASK], min_relevance_score=0.0
    )

    assert result.is_ok, result
    found = result.value
    assert {unit["uid"] for unit in found["knowledge_units"]} == {KU, PREREQUISITE, STEP}
    assert {
        (reason["activity_uid"], reason["ring"], reason["via_uid"], reason["relationship"])
        for reason in found["relevance_reasons"][PREREQUISITE]
    } == {
        (HABIT, RelevanceRing.ADJACENT, KU, "REQUIRES_KNOWLEDGE"),
        (TASK, RelevanceRing.ADJACENT, KU, "REQUIRES_KNOWLEDGE"),
    }
    step = next(unit for unit in found["knowledge_units"] if unit["uid"] == STEP)
    assert (step["entity_type"], step["domain"], step["complexity"]) == (
        EntityType.PATH_STEP,
        Domain.HEALTH,
        KuComplexity.BASIC,
    )
    order = found["recommended_order"]
    assert order.index(PREREQUISITE) < order.index(KU)


@pytest.mark.asyncio
async def test_the_goals_knowledge_is_credited_to_the_goal(neo4j_driver, engine, clean_neo4j):
    await _seed(neo4j_driver)

    result = await engine.find_relevant_for_context(
        active_goals=[GOAL], pending_tasks=[TASK], min_relevance_score=0.0
    )

    assert result.is_ok, result
    assert result.value["domain_coverage"][GOAL_KU] == [EntityType.GOAL]
    assert [
        (reason["activity_uid"], reason["ring"])
        for reason in result.value["relevance_reasons"][GOAL_KU]
    ] == [(GOAL, RelevanceRing.DIRECT)]
