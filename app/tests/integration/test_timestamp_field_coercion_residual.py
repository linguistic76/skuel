"""Real-Neo4j guards for the residual string-stored timestamp comparisons.

Closes the string-stored-temporal bug class (companions: #199 date fields, #202
created_at). These domain timestamp fields are written via DTO `.isoformat()` →
stored as ISO **strings**, but were compared directly to `datetime()`/`date()`:

* Insight.expires_at — `get_active_insights` (TTL'd insights vanished). Its writer
  stores a native (``tests/integration/test_insight_native_stamps.py``); the
  coercion is a no-op on that and keeps a string-stored value readable.
* Habit.last_completed — `get_active_habits_prioritized` (streak-at-risk ordering lost).

`string OP datetime/date` evaluates to null in Neo4j → the row is dropped / the CASE
falls through. Fix: `datetime(field)` / `date(field)` coercion (no-op on native values).

Fields written via Cypher `datetime()` (updated_at, sessions, achieved_at, mastered_at)
are already native and intentionally left uncoerced.
"""

from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from core.models.insight.persisted_insight import ActiveInsightFilter
from core.models.type_hints import Neo4jProperties
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid


@pytest.mark.asyncio
class TestTimestampFieldCoercionResidual:
    """String-stored domain timestamps must match temporal comparisons."""

    async def test_get_active_insights_includes_string_future_expiry(
        self, neo4j_driver, clean_neo4j
    ):
        """An insight with a future string expires_at is active, not filtered out."""
        future = (datetime.now(UTC) + timedelta(days=3)).isoformat()
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MERGE (u:User {uid: $user_insight})
                CREATE (u)-[:HAS_INSIGHT]->(:Insight {
                    insight_id: 'ins_active', user_uid: $user_insight,
                    dismissed: false, actioned: false,
                    impact: 'high', confidence: 0.9,
                    created_at: $now, expires_at: $future})
                """,
                now=datetime.now(UTC).isoformat(),
                future=future,
                user_insight=seed_user_uid("insight"),
            )
        backend = build_production_backends(neo4j_driver)["insight_backend"]

        result = await backend.get_active_insights(
            seed_user_uid("insight"), ActiveInsightFilter(), 10, 0
        )
        assert result.is_ok, f"get_active_insights failed: {result}"
        ids = {cast("Neo4jProperties", row["i"])["insight_id"] for row in result.value}
        assert "ins_active" in ids  # excluded under string-vs-datetime

    async def test_active_habits_prioritized_streak_at_risk_first(self, neo4j_driver, clean_neo4j):
        """A streak-at-risk habit (string last_completed in the past) sorts first.

        An uncoerced `h.last_completed < date($today)` is null → the CASE never flags
        at-risk, so ordering falls back to current_streak DESC and the lower-streak
        at-risk habit sorts LAST. Coerced, it sorts first.

        The stamps are the writer's offset-less strings, at noon on days counted from
        today in the current zone — the day `$today` carries — so the two habits sit
        either side of it whichever hour the test runs.
        """
        today = today_in(current_zone())
        lapsed = f"{(today - timedelta(days=2)).isoformat()}T12:00:00"
        done_today = f"{today.isoformat()}T12:00:00"
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MERGE (u:User {uid: $user_habits})
                CREATE (u)-[:OWNS]->(:Habit {uid: 'h.at-risk', status: 'active',
                    current_streak: 1, last_completed: $lapsed, created_at: $done_today})
                CREATE (u)-[:OWNS]->(:Habit {uid: 'h.safe', status: 'active',
                    current_streak: 10, last_completed: $done_today, created_at: $done_today})
                """,
                lapsed=lapsed,
                done_today=done_today,
                user_habits=seed_user_uid("habits"),
            )
        backend = build_production_backends(neo4j_driver)["habits_backend"]

        result = await backend.get_active_habits_prioritized(
            seed_user_uid("habits"), terminal_statuses=[]
        )
        assert result.is_ok, f"get_active_habits_prioritized failed: {result}"
        order = [row["uid"] for row in result.value]
        # at-risk habit first despite its lower streak (CASE 0 wins over streak DESC).
        assert order.index("h.at-risk") < order.index("h.safe")
