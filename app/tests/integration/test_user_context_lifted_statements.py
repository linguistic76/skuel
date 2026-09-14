"""
The reads that run beside the MEGA-QUERY return what the rich context is built from.

``SUBMISSION_STATS_QUERY`` and ``ENTRY_KNOWLEDGE_APPLIED_QUERY`` are statements of
their own (see ``user_context_queries.py``); this seeds the learning-loop
graph they read — entries, feedback, group-assigned exercises, a pending
revision, APPLIES_KNOWLEDGE edges at and below the confidence floor, a
PathStep→Ku rollup — and asserts each figure through the executor and then
through ``build_rich_user_context``, the path the app takes.
"""

from datetime import datetime, timedelta

import pytest
from neo4j import AsyncDriver

from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.user_context_queries import UserContextQueryExecutor
from core.models.type_hints import UserUID
from core.models.user.user import User
from core.services.user.user_context_builder import UserContextBuilder

_USER_UID = UserUID("user_test")


@pytest.fixture
async def learning_loop_graph(neo4j_driver: AsyncDriver, clean_neo4j) -> dict[str, str]:
    """Seed the learning-loop tail for ``user_test``; ``clean_neo4j`` wipes it after."""
    now = datetime.now()
    recent = now.isoformat()
    stale = (now - timedelta(days=60)).isoformat()
    uids = {
        "entry_recent": "ue.lifted.recent",
        "entry_stale": "ue.lifted.stale",
        "feedback": "er.lifted.feedback",
        "group": "group.lifted",
        "exercise_done": "ex.lifted.done",
        "exercise_open": "ex.lifted.open",
        "fulfilment": "ue.lifted.fulfilment",
        "revision": "rex.lifted.pending",
        "ku_confident": "ku.lifted.confident",
        "ku_doubtful": "ku.lifted.doubtful",
        "ps": "ps.lifted.step",
        "ku_composed": "ku.lifted.composed",
    }
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (u:User {uid: $user_uid})
            CREATE (u)-[:OWNS]->(recent:Entity:UserEntry {uid: $entry_recent, entity_type: 'user_entry',
                                                          pipeline: 'je_pro', created_at: $recent})
            CREATE (u)-[:OWNS]->(stale:Entity:UserEntry {uid: $entry_stale, entity_type: 'user_entry',
                                                         pipeline: 'je_pro', created_at: $stale})
            CREATE (fb:Entity:EntryReport {uid: $feedback, entity_type: 'entry_report', created_at: $recent})
            CREATE (fb)-[:REPORT_FOR]->(recent)
            CREATE (g:Group {uid: $group, name: 'Lifted'})
            CREATE (u)-[:MEMBER_OF]->(g)
            CREATE (done:Entity:Exercise {uid: $exercise_done, entity_type: 'exercise', scope: 'assigned',
                                          title: 'Done'})
            CREATE (open:Entity:Exercise {uid: $exercise_open, entity_type: 'exercise', scope: 'assigned',
                                          title: 'Open', due_date: '2026-10-01'})
            CREATE (done)-[:SHARED_WITH_GROUP]->(g)
            CREATE (open)-[:SHARED_WITH_GROUP]->(g)
            CREATE (:Entity:UserEntry {uid: $fulfilment, entity_type: 'user_entry', user_uid: $user_uid,
                                       pipeline: 'je_pro', created_at: $recent})-[:FULFILLS_EXERCISE]->(done)
            CREATE (:RevisedExercise {uid: $revision, student_uid: $user_uid, title: 'Try again',
                                      revision_number: 2, created_at: $recent})
            CREATE (kc:Entity:Ku {uid: $ku_confident, entity_type: 'ku', title: 'Confident'})
            CREATE (kd:Entity:Ku {uid: $ku_doubtful, entity_type: 'ku', title: 'Doubtful'})
            CREATE (recent)-[:APPLIES_KNOWLEDGE {confidence: 0.9}]->(kc)
            CREATE (recent)-[:APPLIES_KNOWLEDGE {confidence: 0.2}]->(kd)
            CREATE (ps:Entity:PathStep {uid: $ps, entity_type: 'path_step', title: 'Step'})
            CREATE (kk:Entity:Ku {uid: $ku_composed, entity_type: 'ku', title: 'Composed'})
            CREATE (ps)-[:CONTAINS_KNOWLEDGE]->(kk)
            CREATE (stale)-[:APPLIES_KNOWLEDGE]->(ps)
            """,
            user_uid=_USER_UID,
            recent=recent,
            stale=stale,
            **uids,
        )
    return uids


@pytest.mark.asyncio
async def test_submission_stats_statement_counts_the_learning_loop(
    neo4j_driver: AsyncDriver, learning_loop_graph: dict[str, str]
) -> None:
    executor = UserContextQueryExecutor(Neo4jQueryExecutor(neo4j_driver))
    window_start = datetime.now() - timedelta(days=30)

    result = await executor.fetch_submission_stats(_USER_UID, window_start)

    assert result.is_ok, result.error
    stats = result.value
    assert stats["total_submission_count"] == 2
    assert stats["submissions_in_window"] == 1
    assert stats["feedback_received_count"] == 1
    assert stats["feedback_in_window"] == 1
    assert stats["pending_feedback_count"] == 1
    assert stats["assigned_exercise_count"] == 2
    assert stats["completed_exercise_count"] == 1
    assert [ex["uid"] for ex in stats["unsubmitted_exercises"]] == [
        learning_loop_graph["exercise_open"]
    ]
    assert [rev["uid"] for rev in stats["pending_revised_exercises"]] == [
        learning_loop_graph["revision"]
    ]


@pytest.mark.asyncio
async def test_submission_stats_count_nothing_for_a_learner_with_no_assignments(
    neo4j_driver: AsyncDriver, clean_neo4j
) -> None:
    """No group, no assigned exercise: zero assigned, zero completed, nothing unsubmitted.

    ``NOT`` over a pattern whose endpoint is null is true, so an unguarded
    ``collect(CASE WHEN NOT (…)-[:FULFILLS_EXERCISE]->(ex) …)`` emitted one
    phantom map for the null ``ex`` row and ``completed_exercise_count`` read
    ``0 - 1 = -1`` for every learner without an assignment.
    """
    executor = UserContextQueryExecutor(Neo4jQueryExecutor(neo4j_driver))

    result = await executor.fetch_submission_stats(_USER_UID, datetime.now() - timedelta(days=30))

    assert result.is_ok, result.error
    assert result.value["assigned_exercise_count"] == 0
    assert result.value["completed_exercise_count"] == 0
    assert result.value["unsubmitted_exercises"] == []


@pytest.mark.asyncio
async def test_submission_stats_statement_is_empty_for_an_unknown_user(
    neo4j_driver: AsyncDriver, clean_neo4j
) -> None:
    executor = UserContextQueryExecutor(Neo4jQueryExecutor(neo4j_driver))

    result = await executor.fetch_submission_stats(UserUID("user_nobody"), datetime.now())

    assert result.is_ok and result.value == {}


@pytest.mark.asyncio
async def test_entry_knowledge_statement_applies_the_floor_and_the_rollup(
    neo4j_driver: AsyncDriver, learning_loop_graph: dict[str, str]
) -> None:
    executor = UserContextQueryExecutor(Neo4jQueryExecutor(neo4j_driver))

    result = await executor.fetch_entry_knowledge_applied(_USER_UID, min_confidence=0.7)

    assert result.is_ok, result.error
    rows = {row["uid"]: row["ku_uids"] for row in result.value}
    assert rows == {
        # the 0.2-confidence edge is below the floor
        learning_loop_graph["entry_recent"]: [learning_loop_graph["ku_confident"]],
        # a PathStep target rolls up to the Kus it composes
        learning_loop_graph["entry_stale"]: [learning_loop_graph["ku_composed"]],
    }


@pytest.mark.asyncio
async def test_rich_build_carries_both_lifted_reads(
    neo4j_driver: AsyncDriver, learning_loop_graph: dict[str, str]
) -> None:
    builder = UserContextBuilder(UserContextQueryExecutor(Neo4jQueryExecutor(neo4j_driver)))
    user = User(uid=_USER_UID, title="Lifted", email="lifted@test.com")

    result = await builder.build_rich_user_context(_USER_UID, user)

    assert result.is_ok, result.error
    context = result.value
    assert context.total_submission_count == 2
    assert context.pending_feedback_count == 1
    assert [ex["uid"] for ex in context.unsubmitted_exercises] == [
        learning_loop_graph["exercise_open"]
    ]
    assert [rev["uid"] for rev in context.pending_revised_exercises] == [
        learning_loop_graph["revision"]
    ]
    assert context.entry_knowledge_applied == {
        learning_loop_graph["entry_recent"]: [learning_loop_graph["ku_confident"]],
        learning_loop_graph["entry_stale"]: [learning_loop_graph["ku_composed"]],
    }
