"""
Integration tests for CrossDomainBackend.get_recent_activities against real Neo4j.
==================================================================================

Pins the ownership edge AND the completion properties the query reads. Two
defects shaped this file, in order:

1. The pre-2026-08-21 query walked ``(u)-[:HAS_TASK]->`` / ``(u)-[:HAS_GOAL]->``
   — relationship types no write door creates (both write doors create
   ``:OWNS``) — and gated on ``completed_at``, a property no Task/Goal writer
   stamps. Both completion legs returned zero real rows, while the
   ``OPTIONAL MATCH`` + ``collect({map})`` shape emitted one phantom all-null
   activity per empty leg (#1116).
2. The fix that followed read ``coalesce(canonical field, updated_at)``, because
   at the time only the explicit complete paths stamped anything (measured 5/85
   on the live graph). ``updated_at`` is *mutable*, so editing a long-completed
   task re-dated its completion and bounced it to the top of this list.

The completion-stamping arc closed (2) at the write side: every transition into
completed now stamps the domain's canonical field, and history was frozen once
by ``scripts/backfill_activity_completion_stamps.py``. So the read is down to
the stamp alone — Task ``completion_date``, Goal ``achieved_date`` — and a
completed row carrying no stamp is **excluded** rather than approximated.

The fixture therefore seeds the shapes the real writers produce (ISO **strings**
for completion fields, matching ``to_neo4j_node``; ``datetime()`` for
``MASTERED.mastered_at``) plus the two shapes that must now drop out, and gives
the stamped rows a deliberately *newer* ``updated_at`` than their stamp so a
regression to the coalesce would reorder the list visibly.
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
    """Seed every completion shape, one per day so ordering is decisive.

    Included (carry a canonical stamp):
    - day 1: task completed through a stamping path — ``completion_date``
    - day 2: goal completed through a stamping path — ``achieved_date``
    - day 4: Ku mastered — ``MASTERED.mastered_at`` stored as ``datetime()``

    Excluded (completed but no stamp — truth over coverage):
    - day 0: task completed before the stamp existed and missed by the backfill
      (no ``updated_at`` to freeze) — nothing records *when*, so it is absent
    - day 3: goal carrying only the legacy ``completion_date`` alias, which
      ``migrate_activity_completion_aliases.py`` retires and the read no longer
      falls back to

    Both stamped rows carry ``updated_at`` at day 0 — newer than either stamp.
    If the read ever coalesces onto it again they tie for first place and the
    order assertion fails.

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
                uid: 'task_unstamped_ra', title: 'Closed before the stamp existed',
                entity_type: 'task', user_uid: $user_uid, status: 'completed'
            })
            CREATE (u)-[:OWNS]->(:Task:Entity {
                uid: 'task_stamped_ra', title: 'Ship the fix', entity_type: 'task',
                user_uid: $user_uid, status: 'completed',
                completion_date: $d1_date, updated_at: $d0_dt
            })
            CREATE (u)-[:OWNS]->(:Goal:Entity {
                uid: 'goal_achieved_ra', title: 'Hit 100 percent', entity_type: 'goal',
                user_uid: $user_uid, status: 'completed',
                achieved_date: $d2_date, updated_at: $d0_dt
            })
            CREATE (u)-[:OWNS]->(:Goal:Entity {
                uid: 'goal_legacy_ra', title: 'Close the arc', entity_type: 'goal',
                user_uid: $user_uid, status: 'completed',
                completion_date: $d3_date, updated_at: $d0_dt
            })
            CREATE (u)-[:MASTERED {mastered_at: datetime($d4_dt)}]->(:Ku:Entity {
                uid: 'ku_done_ra', title: 'Cypher subqueries', entity_type: 'ku'
            })
            CREATE (u)-[:OWNS]->(:Task:Entity {
                uid: 'task_active_ra', title: 'Still open', entity_type: 'task',
                user_uid: $user_uid, status: 'active',
                completion_date: $d0_date, updated_at: $d0_dt
            })
            CREATE (u)-[:OWNS]->(:Goal:Entity {
                uid: 'goal_active_ra', title: 'Still going', entity_type: 'goal',
                user_uid: $user_uid, status: 'active', updated_at: $d0_dt
            })
            """,
            user_uid=USER_UID,
            d0_dt=day_dt[0],
            d0_date=day_date[0],
            d1_date=day_date[1],
            d2_date=day_date[2],
            d3_date=day_date[3],
            d4_dt=day_dt[4],
        )

        await s.run(
            """
            MATCH (u:User {uid: $user_uid})
            CREATE (u)-[:OWNS]->(:Task:Entity {
                uid: 'task_done_other_ra', title: 'Someone else finished this',
                entity_type: 'task', user_uid: $user_uid,
                status: 'completed', completion_date: $d5_date
            })
            """,
            user_uid=OTHER_USER_UID,
            d5_date=day_date[5],
        )

    yield  # graph is ready; clean_neo4j tears it down


@pytest.fixture
def backend(neo4j_driver):
    """CrossDomainBackend wired to a real Neo4j executor."""
    return CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver))


@pytest.mark.asyncio
class TestGetRecentActivities:
    async def test_stamped_completions_come_back_newest_first(self, backend, graph):
        """Every stamped shape surfaces via :OWNS, ordered across mixed timestamp types."""
        result = await backend.get_recent_activities(USER_UID)

        assert result.is_ok
        activities = [r["activity"] for r in result.value]
        by_uid = {a["entity_uid"]: a for a in activities}

        assert by_uid["task_stamped_ra"]["type"] == "task"  # completion_date
        assert by_uid["goal_achieved_ra"]["type"] == "goal"  # achieved_date
        assert by_uid["ku_done_ra"]["type"] == "knowledge"  # datetime() edge
        assert by_uid["ku_done_ra"]["action"] == "mastered"
        assert all(a["action"] == "completed" for a in activities if a["type"] in ("task", "goal"))

        # Ordered by the stamp, not by updated_at — both stamped rows were
        # touched at day 0, so a coalesce regression would float them to the top.
        assert [a["entity_uid"] for a in activities] == [
            "task_stamped_ra",
            "goal_achieved_ra",
            "ku_done_ra",
        ]

    async def test_completed_without_a_stamp_is_excluded_not_approximated(self, backend, graph):
        """A completion with no recorded moment is absent — a wrong date is worse.

        Covers both null-stamp shapes: the unstamped task and the goal carrying
        only the retired ``completion_date`` alias.
        """
        result = await backend.get_recent_activities(USER_UID)

        assert result.is_ok
        uids = {r["activity"]["entity_uid"] for r in result.value}
        assert "task_unstamped_ra" not in uids
        assert "goal_legacy_ra" not in uids

    async def test_no_phantom_rows_and_no_incomplete_work(self, backend, graph):
        """Empty/partial legs contribute nothing — no all-null phantom activities.

        The active task carries a ``completion_date`` on purpose: the status
        filter, not the stamp's presence, is what excludes unfinished work.
        """
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
