"""Real-Neo4j guards for the date-as-string range-query bug.

SKUEL stores date fields (due_date, event_date, ...) as ISO **strings**, but
several range queries compared them directly against ``date($param)``. Neo4j
evaluates ``string >= date`` as ``null``, so the row is silently dropped and the
query returns nothing — quietly breaking calendar / today / Gantt date-range reads
wherever they routed through an uncoerced builder.

The fix wraps the stored field in ``date(left(toString(n.due_date), 10))`` — the
YYYY-MM-DD prefix of the stringified value. A *date-only* string was already handled
by a bare ``date(n.due_date)``; but a **datetime** string ("2026-06-17T09:00:00")
makes bare ``date()`` THROW ("Text cannot be parsed to a Date"), which takes the whole
range query / mega-query CASE down (#766). The prefix tolerates every storage shape —
date/datetime temporal types and date-only/datetime strings alike.

These tests create entities whose dates sit squarely in range and assert they come
back — against the pre-fix code the date-only cases return an empty list and the
**datetime**-string cases raise ``CypherSyntaxError``; against the fix they all pass.

Covered builders:
* ``build_user_activity_query`` (domain_queries) via ``tasks.get_user_items_in_range``
* the raw event-range query (activity_backends) via ``events.get_events_in_range``
"""

from datetime import date, time, timedelta

import pytest

from core.models.event.event_request import EventCreateRequest
from core.models.task.task_request import TaskCreateRequest


@pytest.mark.asyncio
class TestDateRangeStringCoercion:
    """Date-range reads must match ISO-string-stored date fields."""

    async def _user(self, neo4j_driver, uid: str) -> str:
        async with neo4j_driver.session() as session:
            await session.run(
                "MERGE (u:User {uid: $uid}) ON CREATE SET u.created_at = datetime()",
                uid=uid,
            )
        return uid

    async def test_get_user_items_in_range_matches_string_due_date(
        self, services, neo4j_driver, clean_neo4j
    ):
        """tasks.get_user_items_in_range returns a task whose string due_date is in range."""
        user = await self._user(neo4j_driver, "user_date_range_tasks")
        due = date.today() + timedelta(days=3)

        task = (
            await services.tasks.create_task(
                TaskCreateRequest(title="In-range task", due_date=due), user
            )
        ).value

        result = await services.tasks.get_user_items_in_range(
            user_uid=user,
            start_date=date.today() - timedelta(days=7),
            end_date=date.today() + timedelta(days=60),
            include_completed=True,
        )
        assert result.is_ok, f"get_user_items_in_range failed: {result}"
        assert task.uid in {t.uid for t in result.value}

    async def test_get_user_items_in_range_excludes_out_of_range(
        self, services, neo4j_driver, clean_neo4j
    ):
        """A task dated outside the window is correctly excluded (coercion didn't over-match)."""
        user = await self._user(neo4j_driver, "user_date_range_excl")
        far = date.today() + timedelta(days=120)  # beyond the +60 window

        task = (
            await services.tasks.create_task(
                TaskCreateRequest(title="Out-of-range task", due_date=far), user
            )
        ).value

        result = await services.tasks.get_user_items_in_range(
            user_uid=user,
            start_date=date.today() - timedelta(days=7),
            end_date=date.today() + timedelta(days=60),
            include_completed=True,
        )
        assert result.is_ok
        assert task.uid not in {t.uid for t in result.value}

    async def test_overdue_stat_counts_string_past_due_date(
        self, services, neo4j_driver, clean_neo4j
    ):
        """get_stats_for_user counts a task whose string due_date is in the past as overdue."""
        user = await self._user(neo4j_driver, "user_overdue")
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        # create_task forbids past due_dates, so seed the overdue node directly.
        async with neo4j_driver.session() as session:
            await session.run(
                """
                CREATE (n:Entity:Task {uid: 't_overdue', user_uid: $u,
                                       entity_type: 'task', status: 'active', due_date: $d})
                """,
                u=user,
                d=yesterday,
            )

        stats = await services.tasks.backend.get_stats_for_user(user)
        assert stats.is_ok, f"get_stats_for_user failed: {stats}"
        assert stats.value["overdue"] >= 1  # 0 under string-vs-date comparison

    async def test_get_events_in_range_matches_string_event_date(
        self, services, neo4j_driver, clean_neo4j
    ):
        """events.get_events_in_range returns an event whose string event_date is in range."""
        user = await self._user(neo4j_driver, "user_date_range_events")
        when = date.today() + timedelta(days=2)

        event = (
            await services.events.create_event(
                EventCreateRequest(
                    title="In-range event",
                    event_date=when,
                    start_time=time(9, 0),
                    end_time=time(10, 0),
                ),
                user,
            )
        ).value

        result = await services.events.get_events_in_range(
            start_date=date.today() - timedelta(days=7),
            end_date=date.today() + timedelta(days=30),
            user_uid=user,
        )
        assert result.is_ok, f"get_events_in_range failed: {result}"
        assert event.uid in {e.uid for e in result.value}

    # ------------------------------------------------------------------ #
    # #766 — a *datetime* string in a date field must not blow up the query
    # ------------------------------------------------------------------ #

    async def test_get_user_items_in_range_matches_datetime_string_due_date(
        self, services, neo4j_driver, clean_neo4j
    ):
        """A task whose due_date is a full datetime STRING is returned, not thrown on.

        Pre-fix, ``date('2026-06-17T09:00:00')`` raises CypherSyntaxError and the
        whole range fetch fails → the calendar silently loses every task in range.
        """
        user = await self._user(neo4j_driver, "user_dt_range_tasks")
        in_range = (date.today() + timedelta(days=3)).isoformat()
        # Seed directly: create_task normalizes to a date-only string, so a datetime
        # value can only arrive via a mis-writing path — which is exactly the bug.
        async with neo4j_driver.session() as session:
            await session.run(
                """
                CREATE (n:Entity:Task {uid: 't_dt_due', user_uid: $u,
                                       entity_type: 'task', status: 'active',
                                       due_date: $d, created_at: datetime()})
                """,
                u=user,
                d=f"{in_range}T09:00:00.000000",
            )

        result = await services.tasks.get_user_items_in_range(
            user_uid=user,
            start_date=date.today() - timedelta(days=7),
            end_date=date.today() + timedelta(days=60),
            include_completed=True,
        )
        assert result.is_ok, f"get_user_items_in_range raised/failed: {result}"
        assert "t_dt_due" in {t.uid for t in result.value}

    async def test_get_events_in_range_matches_datetime_string_event_date(
        self, services, neo4j_driver, clean_neo4j
    ):
        """An event whose event_date is a full datetime STRING is returned, not thrown on."""
        user = await self._user(neo4j_driver, "user_dt_range_events")
        in_range = (date.today() + timedelta(days=2)).isoformat()
        async with neo4j_driver.session() as session:
            await session.run(
                """
                CREATE (e:Entity:Event {uid: 'e_dt_date', user_uid: $u,
                                        entity_type: 'event', status: 'scheduled',
                                        event_date: $d, start_time: '09:00:00',
                                        end_time: '10:00:00', created_at: datetime()})
                """,
                u=user,
                d=f"{in_range}T09:00:00.000000",
            )

        result = await services.events.get_events_in_range(
            start_date=date.today() - timedelta(days=7),
            end_date=date.today() + timedelta(days=30),
            user_uid=user,
        )
        assert result.is_ok, f"get_events_in_range raised/failed: {result}"
        assert "e_dt_date" in {e.uid for e in result.value}
