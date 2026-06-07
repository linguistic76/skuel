"""Integration — consolidated learning-requirements lens reads REAL graph mastery.

Proves the mastery half of the daily-plan path end-to-end over local Docker Neo4j:

    (User)-[:MASTERED {mastery_score}]->(Ku)  →  UserContextBuilder MEGA-QUERY
        →  context.knowledge_mastery  →  ContextualGoal.from_entity_and_context
            →  learning_requirements (single PrerequisiteChecker split)

A required KU the user has MASTERED in the graph is reported as mastered (gap closed);
an unmastered required KU stays an open gap. This is the consolidated lens
(ContextualGoal now sources gaps from ``build_learning_requirements``) telling the
truth against real graph-sourced mastery — not a stub. Mirrors
``test_goal_learning_requirements_mastery_is_real_with_context`` for the new consumer.
"""

import pytest

from core.models.context_types import ContextualGoal
from core.models.user.user import User

USER = "user_ctxgoal_mastery_test"
KU_MASTERED = "ku:ctxgoal_mastered"
KU_GAP = "ku:ctxgoal_gap"


@pytest.mark.asyncio
async def test_contextual_goal_learning_requirements_reads_real_mastery(user_service, clean_neo4j):
    driver = user_service.context_builder._query_executor.executor.driver

    async with driver.session() as session:
        await session.run(
            "MATCH (u:User {uid:$u}) OPTIONAL MATCH (u)-[r]-() DETACH DELETE r, u",
            u=USER,
        )
        await session.run(
            "MATCH (k:Entity) WHERE k.uid IN $uids DETACH DELETE k",
            uids=[KU_MASTERED, KU_GAP],
        )
        # User with a MASTERED edge to one of two required KUs.
        await session.run(
            """
            CREATE (u:User {uid:$u, title:'Ctx Goal Mastery', email:'cg@test.com',
                            display_name:'Ctx Goal Mastery', created_at:datetime(),
                            updated_at:datetime()})
            CREATE (k1:Entity {uid:$mastered, title:'Mastered KU', created_at:datetime()})
            CREATE (k2:Entity {uid:$gap, title:'Gap KU', created_at:datetime()})
            CREATE (u)-[:MASTERED {mastery_score:0.9}]->(k1)
            """,
            u=USER,
            mastered=KU_MASTERED,
            gap=KU_GAP,
        )

    # Build a real context from the graph (mastery comes from the MASTERED edge).
    ctx_result = await user_service.context_builder.build_user_context(
        USER, User(uid=USER, title="Ctx Goal Mastery", email="cg@test.com")
    )
    assert ctx_result.is_ok, ctx_result
    context = ctx_result.value
    assert context.knowledge_mastery.get(KU_MASTERED) == pytest.approx(0.9)

    # Consolidated lens: the MASTERED KU is mastered, the other is an open gap.
    goal = ContextualGoal.from_entity_and_context(
        uid="goal_ctxgoal_test",
        title="Real-graph goal",
        context=context,
        required_knowledge_uids=[KU_MASTERED, KU_GAP],
    )
    reqs = goal.learning_requirements
    assert reqs is not None
    knowledge = reqs["knowledge_requirements"]
    assert knowledge["total_required"] == 2
    assert [k["uid"] for k in knowledge["mastered_knowledge"]] == [KU_MASTERED]
    assert [g["uid"] for g in knowledge["knowledge_gaps"]] == [KU_GAP]
    assert reqs["learning_analysis"]["ready_to_start"] is False
    # Flat field agrees with the rich payload (one source).
    assert set(goal.learning_gaps) == {KU_GAP}
