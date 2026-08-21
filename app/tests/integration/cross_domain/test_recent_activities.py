"""
Integration tests for CrossDomainBackend.get_recent_activities against real Neo4j.
==================================================================================

Pins the ownership edge the query traverses. The pre-2026-08-21 query walked
``(u)-[:HAS_TASK]->`` / ``(u)-[:HAS_GOAL]->`` — relationship types no write
door creates (both write doors create ``:OWNS``) — so the completed-task and
completed-goal legs always returned zero real rows. Worse, the
``OPTIONAL MATCH`` + ``collect({map})`` shape emitted one phantom all-null
activity per empty leg, which ``UserStatsAggregator._get_recent_activities``
passed through (a map with null fields is truthy).

These tests assert the fixed contract: real completed entities reached via
``:OWNS`` come back, phantoms never do.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

USER_UID = "user_recent_acts"
OTHER_USER_UID = "user_recent_acts_other"
EMPTY_USER_UID = "user_recent_acts_empty"


@pytest_asyncio.fixture
async def graph(neo4j_driver, clean_neo4j):
    """Seed: one user owning completed/active tasks and goals, one mastered Ku.

    A second user owns their own completed task to prove per-user scoping.
    """
    now = datetime.now(tz=UTC)
    ts = [(now - timedelta(days=d)).isoformat() for d in range(6)]

    async with neo4j_driver.session() as s:
        for uid in (USER_UID, OTHER_USER_UID, EMPTY_USER_UID):
            await s.run("MERGE (u:User {uid: $uid})", uid=uid)

        # Completed task (newest), completed goal (older), mastered Ku (oldest)
        await s.run(
            """
            MATCH (u:User {uid: $user_uid})
            CREATE (u)-[:OWNS]->(:Task:Entity {
                uid: 'task_done_ra', title: 'Ship the fix', entity_type: 'task',
                user_uid: $user_uid, status: 'completed', completed_at: $t0
            })
            CREATE (u)-[:OWNS]->(:Goal:Entity {
                uid: 'goal_done_ra', title: 'Close the arc', entity_type: 'goal',
                user_uid: $user_uid, status: 'completed', completed_at: $t1
            })
            CREATE (u)-[:MASTERED {mastered_at: $t2}]->(:Ku:Entity {
                uid: 'ku_done_ra', title: 'Cypher subqueries', entity_type: 'ku'
            })
            CREATE (u)-[:OWNS]->(:Task:Entity {
                uid: 'task_active_ra', title: 'Still open', entity_type: 'task',
                user_uid: $user_uid, status: 'active'
            })
            CREATE (u)-[:OWNS]->(:Goal:Entity {
                uid: 'goal_active_ra', title: 'Still going', entity_type: 'goal',
                user_uid: $user_uid, status: 'active'
            })
            """,
            user_uid=USER_UID,
            t0=ts[0],
            t1=ts[1],
            t2=ts[2],
        )

        await s.run(
            """
            MATCH (u:User {uid: $user_uid})
            CREATE (u)-[:OWNS]->(:Task:Entity {
                uid: 'task_done_other_ra', title: 'Someone else finished this',
                entity_type: 'task', user_uid: $user_uid,
                status: 'completed', completed_at: $t0
            })
            """,
            user_uid=OTHER_USER_UID,
            t0=ts[3],
        )

    yield  # graph is ready; clean_neo4j tears it down


@pytest.fixture
def backend(neo4j_driver):
    """CrossDomainBackend wired to a real Neo4j executor."""
    return CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver))


@pytest.mark.asyncio
class TestGetRecentActivities:
    async def test_completed_work_reached_via_owns_edge(self, backend, graph):
        """Completed tasks and goals come back — the legs the HAS_* edges killed."""
        result = await backend.get_recent_activities(USER_UID)

        assert result.is_ok
        activities = [r["activity"] for r in result.value]
        by_uid = {a["entity_uid"]: a for a in activities}

        assert by_uid["task_done_ra"]["type"] == "task"
        assert by_uid["task_done_ra"]["action"] == "completed"
        assert by_uid["goal_done_ra"]["type"] == "goal"
        assert by_uid["goal_done_ra"]["action"] == "completed"
        assert by_uid["ku_done_ra"]["type"] == "knowledge"
        assert by_uid["ku_done_ra"]["action"] == "mastered"

        # Newest first across legs
        assert [a["entity_uid"] for a in activities] == [
            "task_done_ra",
            "goal_done_ra",
            "ku_done_ra",
        ]

    async def test_no_phantom_rows_and_no_incomplete_work(self, backend, graph):
        """Empty/partial legs contribute nothing — no all-null phantom activities."""
        result = await backend.get_recent_activities(USER_UID)

        assert result.is_ok
        activities = [r["activity"] for r in result.value]
        assert all(a["entity_uid"] is not None for a in activities)
        uids = {a["entity_uid"] for a in activities}
        assert "task_active_ra" not in uids
        assert "goal_active_ra" not in uids

    async def test_scoped_to_the_requesting_user(self, backend, graph):
        """Another user's completed work never appears."""
        result = await backend.get_recent_activities(USER_UID)

        assert result.is_ok
        uids = {r["activity"]["entity_uid"] for r in result.value}
        assert "task_done_other_ra" not in uids

    async def test_user_with_no_activity_gets_empty_list(self, backend, graph):
        """The pre-fix query returned 3 phantom null activities here."""
        result = await backend.get_recent_activities(EMPTY_USER_UID)

        assert result.is_ok
        assert result.value == []
