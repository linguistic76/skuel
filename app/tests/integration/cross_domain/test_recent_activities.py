"""
Integration tests for CrossDomainBackend.get_recent_activities against real Neo4j.
==================================================================================

Pins the ownership edge AND the completion properties the query reads. The
pre-2026-08-21 query walked ``(u)-[:HAS_TASK]->`` / ``(u)-[:HAS_GOAL]->`` —
relationship types no write door creates (both write doors create ``:OWNS``)
— and gated on ``completed_at``, a property no Task/Goal writer stamps
(explicit completion writes ``completion_date`` / ``achieved_date``;
status-route and vault completions stamp only ``updated_at`` — the dominant
shape on the live graph, 80/85). So the completed-task and completed-goal
legs always returned zero real rows, while the ``OPTIONAL MATCH`` +
``collect({map})`` shape emitted one phantom all-null activity per empty
leg, which ``UserStatsAggregator._get_recent_activities`` passed through.

The fixture therefore seeds the shapes the real writers produce — string
dates for completion fields, ``datetime()`` for ``MASTERED.mastered_at`` —
and asserts the fixed contract: every completed shape comes back via
``:OWNS``, ordered newest-first across legs, phantoms never.
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
    """Seed every real completion shape, one per day so ordering is decisive.

    - day 0: task completed via status route / vault sync — updated_at only
    - day 1: task completed via the explicit complete path — completion_date
      (string date), with a much older updated_at to prove coalesce prefers it
    - day 2: goal auto-completed at 100% progress — achieved_date only
    - day 3: goal completed via complete_goal — completion_date
    - day 4: Ku mastered — MASTERED.mastered_at stored as datetime()
    Plus active entities (excluded) and a second user's completed task (scoping).
    """
    now = datetime.now(tz=UTC)
    day_dt = [(now - timedelta(days=d)).isoformat() for d in range(7)]
    day_date = [(now - timedelta(days=d)).date().isoformat() for d in range(7)]

    async with neo4j_driver.session() as s:
        for uid in (USER_UID, OTHER_USER_UID, EMPTY_USER_UID):
            await s.run("MERGE (u:User {uid: $uid})", uid=uid)

        await s.run(
            """
            MATCH (u:User {uid: $user_uid})
            CREATE (u)-[:OWNS]->(:Task:Entity {
                uid: 'task_status_ra', title: 'Closed from the vault', entity_type: 'task',
                user_uid: $user_uid, status: 'completed', updated_at: $d0_dt
            })
            CREATE (u)-[:OWNS]->(:Task:Entity {
                uid: 'task_explicit_ra', title: 'Ship the fix', entity_type: 'task',
                user_uid: $user_uid, status: 'completed',
                completion_date: $d1_date, updated_at: $d6_dt
            })
            CREATE (u)-[:OWNS]->(:Goal:Entity {
                uid: 'goal_achieved_ra', title: 'Hit 100 percent', entity_type: 'goal',
                user_uid: $user_uid, status: 'completed',
                achieved_date: $d2_date, updated_at: $d6_dt
            })
            CREATE (u)-[:OWNS]->(:Goal:Entity {
                uid: 'goal_explicit_ra', title: 'Close the arc', entity_type: 'goal',
                user_uid: $user_uid, status: 'completed',
                completion_date: $d3_date, updated_at: $d6_dt
            })
            CREATE (u)-[:MASTERED {mastered_at: datetime($d4_dt)}]->(:Ku:Entity {
                uid: 'ku_done_ra', title: 'Cypher subqueries', entity_type: 'ku'
            })
            CREATE (u)-[:OWNS]->(:Task:Entity {
                uid: 'task_active_ra', title: 'Still open', entity_type: 'task',
                user_uid: $user_uid, status: 'active', updated_at: $d0_dt
            })
            CREATE (u)-[:OWNS]->(:Goal:Entity {
                uid: 'goal_active_ra', title: 'Still going', entity_type: 'goal',
                user_uid: $user_uid, status: 'active', updated_at: $d0_dt
            })
            """,
            user_uid=USER_UID,
            d0_dt=day_dt[0],
            d1_date=day_date[1],
            d2_date=day_date[2],
            d3_date=day_date[3],
            d4_dt=day_dt[4],
            d6_dt=day_dt[6],
        )

        await s.run(
            """
            MATCH (u:User {uid: $user_uid})
            CREATE (u)-[:OWNS]->(:Task:Entity {
                uid: 'task_done_other_ra', title: 'Someone else finished this',
                entity_type: 'task', user_uid: $user_uid,
                status: 'completed', updated_at: $d5_dt
            })
            """,
            user_uid=OTHER_USER_UID,
            d5_dt=day_dt[5],
        )

    yield  # graph is ready; clean_neo4j tears it down


@pytest.fixture
def backend(neo4j_driver):
    """CrossDomainBackend wired to a real Neo4j executor."""
    return CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver))


@pytest.mark.asyncio
class TestGetRecentActivities:
    async def test_every_real_completion_shape_comes_back_newest_first(self, backend, graph):
        """All writer shapes surface via :OWNS, ordered across mixed timestamp types."""
        result = await backend.get_recent_activities(USER_UID)

        assert result.is_ok
        activities = [r["activity"] for r in result.value]
        by_uid = {a["entity_uid"]: a for a in activities}

        assert by_uid["task_status_ra"]["type"] == "task"  # updated_at fallback
        assert by_uid["task_explicit_ra"]["type"] == "task"  # completion_date
        assert by_uid["goal_achieved_ra"]["type"] == "goal"  # achieved_date
        assert by_uid["goal_explicit_ra"]["type"] == "goal"  # completion_date
        assert by_uid["ku_done_ra"]["type"] == "knowledge"  # datetime() edge
        assert by_uid["ku_done_ra"]["action"] == "mastered"
        assert all(a["action"] == "completed" for a in activities if a["type"] in ("task", "goal"))

        # Newest first across legs — completion_date outranks the stale
        # updated_at on the explicit shapes (coalesce order)
        assert [a["entity_uid"] for a in activities] == [
            "task_status_ra",
            "task_explicit_ra",
            "goal_achieved_ra",
            "goal_explicit_ra",
            "ku_done_ra",
        ]

    async def test_no_phantom_rows_and_no_incomplete_work(self, backend, graph):
        """Empty/partial legs contribute nothing — no all-null phantom activities."""
        result = await backend.get_recent_activities(USER_UID)

        assert result.is_ok
        activities = [r["activity"] for r in result.value]
        assert all(a["entity_uid"] is not None for a in activities)
        assert all(a["timestamp"] is not None for a in activities)
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
