"""Real-Neo4j guard for created_at window-filter coercion.

`created_at` is stored INCONSISTENTLY — most entities carry an ISO **string**, a
minority carry a real ZONED DATETIME (verified in-DB). Several window filters
compared it directly to `datetime(...)` / `datetime() - duration(...)`:

    WHERE ar.created_at >= datetime() - duration({minutes: $cooldown})

Neo4j evaluates `string >= datetime` as null, so the string-stored majority was
silently dropped — cooldown checks, choice-adherence/conflict windows, and the
UserContext submissions/feedback in-window counts all undercounted.

Fix: coerce the stored field with `datetime(...)` — `datetime(x.created_at) >= ...`.
`datetime()` parses the ISO string AND is a no-op on an already-datetime value, so
it handles the mixed column uniformly.

This test seeds both shapes (string + zoned datetime) plus an out-of-window report
and asserts the cooldown count sees both recent ones. Pre-fix it would see only the
datetime one (count 1), so `== 2` is a built-in negative control.
"""

from datetime import UTC, datetime, timedelta

import pytest

from adapters.persistence.neo4j.backends.misc_backends import ActivityReportGeneratorBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor


@pytest.mark.asyncio
class TestCreatedAtWindowCoercion:
    """created_at window filters must match both string- and datetime-stored values."""

    async def test_check_cooldown_matches_string_and_datetime_created_at(
        self, neo4j_driver, clean_neo4j
    ):
        now = datetime.now(UTC)
        recent_iso = (now - timedelta(minutes=5)).isoformat()  # string, in window
        old_iso = (now - timedelta(hours=5)).isoformat()  # string, out of window

        async with neo4j_driver.session() as session:
            await session.run("MERGE (u:User {uid: 'user_cooldown'})")
            # Majority shape: created_at as an ISO string, recent.
            await session.run(
                """
                MATCH (u:User {uid: 'user_cooldown'})
                CREATE (u)-[:OWNS]->(:Entity {uid: 'ar_str',
                    entity_type: 'activity_report', created_at: $c})
                """,
                c=recent_iso,
            )
            # Minority shape: created_at as a real zoned datetime, recent.
            await session.run(
                """
                MATCH (u:User {uid: 'user_cooldown'})
                CREATE (u)-[:OWNS]->(:Entity {uid: 'ar_dt',
                    entity_type: 'activity_report',
                    created_at: datetime() - duration({minutes: 5})})
                """
            )
            # String, but outside the cooldown window — must NOT count.
            await session.run(
                """
                MATCH (u:User {uid: 'user_cooldown'})
                CREATE (u)-[:OWNS]->(:Entity {uid: 'ar_old',
                    entity_type: 'activity_report', created_at: $c})
                """,
                c=old_iso,
            )

        backend = ActivityReportGeneratorBackend(Neo4jQueryExecutor(neo4j_driver))
        result = await backend.check_cooldown("user_cooldown", cooldown_minutes=60)
        assert result.is_ok, f"check_cooldown failed: {result}"
        # str + datetime are both in-window; the old string one is excluded.
        # Pre-fix only the datetime one counted (string >= datetime → null) → 1.
        assert result.value[0]["recent_count"] == 2
