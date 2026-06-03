"""Real-Neo4j guards for the residual string-stored timestamp comparisons.

Closes the string-stored-temporal bug class (companions: #199 date fields, #202
created_at). These domain timestamp fields are written via DTO `.isoformat()` →
stored as ISO **strings**, but were compared directly to `datetime()`/`date()`:

* ReportSchedule.next_due_at / last_generated_at — `get_due_schedules` (the scheduled
  -report worker never saw due schedules).
* Insight.expires_at — `get_active_insights` (TTL'd insights vanished).
* Habit.last_completed — `get_active_habits_prioritized` (streak-at-risk ordering lost).

`string OP datetime/date` evaluates to null in Neo4j → the row is dropped / the CASE
falls through. Fix: `datetime(field)` / `date(field)` coercion (no-op on native values).

Fields written via Cypher `datetime()` (updated_at, sessions, achieved_at, mastered_at)
are already native and intentionally left uncoerced.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, cast

import pytest

from adapters.persistence.neo4j.backends.activity_backends import HabitsBackend
from adapters.persistence.neo4j.backends.misc_backends import ReportScheduleBackend
from adapters.persistence.neo4j.insight_backend import InsightBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.enums.neo_labels import NeoLabel
from core.models.habit.habit import Habit
from core.models.report_schedule.report_schedule import ReportSchedule


@pytest.mark.asyncio
class TestTimestampFieldCoercionResidual:
    """String-stored domain timestamps must match temporal comparisons."""

    async def test_get_due_schedules_matches_string_next_due_at(self, neo4j_driver, clean_neo4j):
        """A schedule whose string next_due_at is in the past is returned as due."""
        past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        async with neo4j_driver.session() as session:
            await session.run(
                """
                CREATE (:ReportSchedule {uid: 'sched_due', is_active: true,
                    next_due_at: $past, last_generated_at: null})
                """,
                past=past,
            )
        backend = ReportScheduleBackend(neo4j_driver, NeoLabel.REPORT_SCHEDULE, ReportSchedule)

        result = await backend.get_due_schedules(min_interval_hours=1)
        assert result.is_ok, f"get_due_schedules failed: {result}"
        uids = {cast("dict[str, Any]", row["s"])["uid"] for row in result.value}
        assert "sched_due" in uids  # empty under string-vs-datetime

    async def test_get_active_insights_includes_string_future_expiry(
        self, neo4j_driver, clean_neo4j
    ):
        """An insight with a future string expires_at is active, not filtered out."""
        future = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MERGE (u:User {uid: 'user_insight'})
                CREATE (u)-[:HAS_INSIGHT]->(:Insight {
                    insight_id: 'ins_active', user_uid: 'user_insight',
                    dismissed: false, actioned: false,
                    impact: 'high', confidence: 0.9,
                    created_at: $now, expires_at: $future})
                """,
                now=datetime.now(timezone.utc).isoformat(),
                future=future,
            )
        backend = InsightBackend(Neo4jQueryExecutor(neo4j_driver))

        result = await backend.get_active_insights("user_insight", None, 10)
        assert result.is_ok, f"get_active_insights failed: {result}"
        ids = {cast("dict[str, Any]", row["i"])["insight_id"] for row in result.value}
        assert "ins_active" in ids  # excluded under string-vs-datetime

    async def test_active_habits_prioritized_streak_at_risk_first(self, neo4j_driver, clean_neo4j):
        """A streak-at-risk habit (string last_completed in the past) sorts first.

        Pre-fix `h.last_completed < date()` is null → the CASE never flags at-risk, so
        ordering falls back to current_streak DESC and the lower-streak at-risk habit
        sorts LAST. Post-fix it sorts first.
        """
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        today = datetime.now(timezone.utc).isoformat()
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MERGE (u:User {uid: 'user_habits'})
                CREATE (u)-[:OWNS]->(:Habit {uid: 'h_at_risk', status: 'active',
                    current_streak: 1, last_completed: $yesterday, created_at: $today})
                CREATE (u)-[:OWNS]->(:Habit {uid: 'h_safe', status: 'active',
                    current_streak: 10, last_completed: $today, created_at: $today})
                """,
                yesterday=yesterday,
                today=today,
            )
        backend = HabitsBackend(neo4j_driver, NeoLabel.HABIT, Habit, base_label=NeoLabel.ENTITY)

        result = await backend.get_active_habits_prioritized("user_habits", terminal_statuses=[])
        assert result.is_ok, f"get_active_habits_prioritized failed: {result}"
        order = [row["uid"] for row in result.value]
        # at-risk habit first despite its lower streak (CASE 0 wins over streak DESC).
        assert order.index("h_at_risk") < order.index("h_safe")
