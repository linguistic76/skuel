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

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

from adapters.persistence.neo4j.backends.misc_backends import ActivityReportGeneratorBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from tests.helpers.seed_uids import seed_user_uid

_COOLDOWN = seed_user_uid("cooldown")
_ORDER = seed_user_uid("order")


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
            await session.run("MERGE (u:User {uid: $user})", user=_COOLDOWN)
            # Majority shape: created_at as an ISO string, recent.
            await session.run(
                """
                MATCH (u:User {uid: $user})
                CREATE (u)-[:OWNS]->(:Entity {uid: 'ar.str',
                    entity_type: 'activity_report', time_period: '7d', created_at: $c})
                """,
                c=recent_iso,
                user=_COOLDOWN,
            )
            # Minority shape: created_at as a real zoned datetime, recent.
            await session.run(
                """
                MATCH (u:User {uid: $user})
                CREATE (u)-[:OWNS]->(:Entity {uid: 'ar.dt',
                    entity_type: 'activity_report', time_period: '7d',
                    created_at: datetime() - duration({minutes: 5})})
                """,
                user=_COOLDOWN,
            )
            # String, but outside the cooldown window — must NOT count.
            await session.run(
                """
                MATCH (u:User {uid: $user})
                CREATE (u)-[:OWNS]->(:Entity {uid: 'ar.old',
                    entity_type: 'activity_report', time_period: '7d', created_at: $c})
                """,
                c=old_iso,
                user=_COOLDOWN,
            )

            # Recent, but for another period — the cooldown is keyed per (user, period).
            await session.run(
                """
                MATCH (u:User {uid: $user})
                CREATE (u)-[:OWNS]->(:Entity {uid: 'ar.other-period',
                    entity_type: 'activity_report', time_period: '2026-09', created_at: $c})
                """,
                c=recent_iso,
                user=_COOLDOWN,
            )
            # Recent and the right period, but an admin's report on the user
            # (theirs to own — Submit & Share arc R11): a review, not a generation, so it
            # never puts them in cooldown.
            await session.run(
                """
                MATCH (u:User {uid: $user})
                CREATE (u)-[:OWNS]->(:Entity {uid: 'ar.admin',
                    entity_type: 'activity_report', time_period: '7d',
                    processor_type: 'human', created_at: $c})
                """,
                c=recent_iso,
                user=_COOLDOWN,
            )
        backend = ActivityReportGeneratorBackend(Neo4jQueryExecutor(neo4j_driver))
        result = await backend.check_cooldown(_COOLDOWN, cooldown_minutes=60, time_period="7d")
        assert result.is_ok, f"check_cooldown failed: {result}"
        # str + datetime are both in-window; the old string one and the
        # admin's report are excluded.
        assert result.value[0]["recent_count"] == 2


@pytest.mark.asyncio
class TestNewestFirstCoercion:
    """A "newest first" read over the mixed ``created_at`` column must order by
    the coerced value: Neo4j orders a string and a datetime by TYPE (strings
    after temporals, so first in DESC), so a raw ``ORDER BY n.created_at DESC
    LIMIT 1`` returns the string-stored row whatever its age. The case where
    the NEWER report is the datetime-stored one is the negative control: the
    raw ordering hands back the older string row."""

    @pytest.mark.parametrize("newer_is_datetime", [True, False])
    async def test_newest_first_reads_order_by_the_coerced_value(
        self, neo4j_driver, clean_neo4j, newer_is_datetime
    ):
        from adapters.persistence.neo4j.backends.misc_backends import ActivityReportBackend
        from core.models.enums.neo_labels import NeoLabel
        from core.models.report.activity_report import ActivityReport

        now = datetime.now(UTC)
        older_iso = (now - timedelta(days=2)).isoformat()
        newer_iso = (now - timedelta(hours=1)).isoformat()
        common = "entity_type: 'activity_report', user_uid: $order, subject_uid: $order, time_period: '2026-09'"
        if newer_is_datetime:
            older_created = "$older"
            newer_created = "datetime() - duration({hours: 1})"
        else:
            older_created = "datetime() - duration({days: 2})"
            newer_created = "$newer"
        async with neo4j_driver.session() as session:
            # ar.admin is the newest of all and the user's own (Submit & Share arc R11),
            # but an admin's review: the period read skips it, the GradeBook
            # history lists it, the comparison history (generated_only) does not.
            await session.run(
                f"""
                CREATE (:Entity {{uid: 'ar.older', {common}, created_at: {older_created}}})
                CREATE (:Entity {{uid: 'ar.newer', {common}, created_at: {newer_created}}})
                CREATE (:Entity {{uid: 'ar.admin', {common}, processor_type: 'human',
                                  created_at: datetime()}})
                """,
                older=older_iso,
                newer=newer_iso,
                order=_ORDER,
            )
        backend = ActivityReportBackend(
            neo4j_driver, NeoLabel.ACTIVITY_REPORT, ActivityReport, base_label=NeoLabel.ENTITY
        )

        found = await backend.find_by_period(_ORDER, _ORDER, "2026-09")
        history = await backend.get_history(_ORDER)
        generated = await backend.get_history(_ORDER, generated_only=True)

        assert found.is_ok and history.is_ok and generated.is_ok
        assert _uid(found.value[0]) == "ar.newer"
        assert [_uid(row) for row in history.value] == ["ar.admin", "ar.newer", "ar.older"]
        assert [_uid(row) for row in generated.value] == ["ar.newer", "ar.older"]


def _uid(row: Mapping[str, object]) -> str:
    """The uid of a ``RETURN n`` row's node (a neo4j ``Node``, a Mapping at runtime)."""
    node = cast("Mapping[str, object]", row["n"])  # boundary: neo4j Node
    return str(node["uid"])
