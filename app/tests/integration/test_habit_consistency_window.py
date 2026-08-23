"""``consistency_score``'s trailing window, against a real graph.

The window is a Cypher predicate over ``HabitCompletion.completed_at``, so
everything load-bearing about it — which rows fall inside, what the edges do,
and how the timestamp's storage type is compared — is proven against the
container rather than a fake. The arithmetic that consumes the count, and the
three degenerate readings it replaces, are pinned DB-free in
``tests/unit/test_habit_consistency_window.py`` so they run on every CI job;
this file is path-filtered.

What has to hold here:

1. **The boundary.** ``HabitConsistencyWindow.start_date`` is the first day
   *inside*. A completion on that exact day counts; one a single day older does
   not. An off-by-one is invisible in the reported number and silently skews
   every consistency score in the app.
2. **Membership is the completion record's own timestamp**, truncated to its
   calendar day — the window is defined in days, so the comparison is too, and
   a completion at 23:59 on the boundary day is inside it.
3. **Ownership.** Scoped by the universal ``:OWNS`` edge (ADR-086), so another
   user's completions cannot leak into the score.
4. **The timestamp's storage type.** It is an ISO datetime **string** on every
   live row (the mapper ``isoformat()``s the ``datetime`` the DTO carries), but
   the writer decides the storage type, not this reader. The normalisation is
   what keeps a temporally-typed value comparing correctly instead of silently
   matching nothing, which would read as "this user was less consistent", never
   as an error.
5. **No analytics node required.** The count is derived, so the bulk-logging
   door — ``HabitCompletionBulk``, an event no analytics handler subscribes to —
   still yields a real score instead of a confident 0.0.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest
import pytest_asyncio

from core.constants import HabitConsistencyWindow

WINDOW = "user_consistency_window"
STALE = "user_consistency_stale"
BULK = "user_consistency_bulk"

TODAY = date.today()
FIRST_DAY_IN = HabitConsistencyWindow.start_date(TODAY)
LAST_DAY_OUT = TODAY - timedelta(days=HabitConsistencyWindow.DAYS)


def _score_for(count: int) -> float:
    return round(count / HabitConsistencyWindow.WEEKS, 2)


def _at(day: date, hour: int = 9) -> str:
    """The ISO datetime string every live writer produces for ``completed_at``."""
    return datetime.combine(day, time(hour=hour)).isoformat()


async def _seed_completion(
    neo4j_driver,
    user_uid: str,
    completion_uid: str,
    *,
    completed_at: str | None,
    temporal_stamp: bool = False,
) -> None:
    """Own a HabitCompletion off the user — the shape the window counts (ADR-086).

    Mirrors the writer: ``user_uid`` as a property **and** the ``:OWNS`` edge,
    the invariant every user-owned entity holds. ``temporal_stamp`` writes
    ``completed_at`` as a native Neo4j ``datetime()`` instead of the ISO string,
    to prove the reader survives a writer that changes its mind.
    """
    stamp_clause = ""
    if completed_at is not None:
        stamp_clause = (
            "SET hc.completed_at = datetime($completed_at)"
            if temporal_stamp
            else "SET hc.completed_at = $completed_at"
        )

    async with neo4j_driver.session() as session:
        result = await session.run(
            f"""
            MATCH (u:User {{uid: $user_uid}})
            MERGE (hc:HabitCompletion {{uid: $completion_uid}})
            SET hc.user_uid = $user_uid,
                hc.habit_uid = 'habit.exercise'
            {stamp_clause}
            MERGE (u)-[:OWNS]->(hc)
            """,
            user_uid=user_uid,
            completion_uid=completion_uid,
            completed_at=completed_at,
        )
        await result.consume()


async def _seed_analytics(neo4j_driver, user_uid: str, total_completions: int) -> None:
    """A node carrying cumulative figures — the numbers the rate no longer reads."""
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MERGE (a:HabitAnalytics {user_uid: $user_uid})
            SET a.total_completions = $total_completions,
                a.first_completion_at = datetime('2025-01-05T09:00:00'),
                a.last_completion_at = datetime('2026-01-05T17:30:00')
            """,
            user_uid=user_uid,
            total_completions=total_completions,
        )
        await result.consume()


@pytest.mark.asyncio
@pytest.mark.integration
class TestHabitConsistencyWindow:
    """The trailing window, exercised against the Neo4j testcontainer."""

    @pytest_asyncio.fixture
    async def backend(self, neo4j_driver, clean_neo4j):
        from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
        from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

        return CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver))

    @pytest_asyncio.fixture
    async def service(self, backend):
        from core.services.cross_domain_analytics_service import CrossDomainAnalyticsService

        return CrossDomainAnalyticsService(backend)

    @pytest_asyncio.fixture
    async def seeded(self, neo4j_driver, backend):
        """One user per shape the window has to discriminate."""
        # WINDOW: four rows that count and three that must not.
        await _seed_analytics(neo4j_driver, WINDOW, 400)
        await _seed_completion(neo4j_driver, WINDOW, "hc.win_today", completed_at=_at(TODAY))
        await _seed_completion(
            neo4j_driver, WINDOW, "hc.win_yesterday", completed_at=_at(TODAY - timedelta(days=1))
        )
        # The boundary itself, late in the day: the first day inside the window.
        await _seed_completion(
            neo4j_driver, WINDOW, "hc.win_boundary", completed_at=_at(FIRST_DAY_IN, hour=23)
        )
        # A timestamp written as a native temporal rather than an ISO string.
        await _seed_completion(
            neo4j_driver,
            WINDOW,
            "hc.win_temporal",
            completed_at=_at(TODAY),
            temporal_stamp=True,
        )
        # One day past the boundary — exactly DAYS old, and late in that day, so
        # a truncation that rounded up rather than down would wrongly admit it.
        await _seed_completion(
            neo4j_driver, WINDOW, "hc.out_boundary", completed_at=_at(LAST_DAY_OUT, hour=23)
        )
        await _seed_completion(
            neo4j_driver, WINDOW, "hc.out_ancient", completed_at=_at(TODAY - timedelta(days=200))
        )
        # A record with no timestamp at all — excluded, not assumed recent.
        await _seed_completion(neo4j_driver, WINDOW, "hc.out_unstamped", completed_at=None)

        # STALE: a real year of history, nothing inside the window.
        await _seed_analytics(neo4j_driver, STALE, 365)
        for offset in (31, 90, 400):
            await _seed_completion(
                neo4j_driver,
                STALE,
                f"hc.stale_{offset}",
                completed_at=_at(TODAY - timedelta(days=offset)),
            )

        # BULK: completions in the window, no analytics node at all.
        for n in range(6):
            await _seed_completion(
                neo4j_driver, BULK, f"hc.bulk_{n}", completed_at=_at(TODAY - timedelta(days=n))
            )

        return backend

    # ====================================================================
    # THE WINDOW PREDICATE
    # ====================================================================

    async def test_only_completions_inside_the_window_are_counted(self, seeded):
        """Four of the user's seven records fall inside; three are excluded, each
        for its own reason (too old, exactly DAYS old, unstamped)."""
        result = await seeded.get_habit_analytics(
            user_uid=WINDOW, window_start=FIRST_DAY_IN.isoformat()
        )

        assert result.is_ok
        assert result.value[0]["completions_in_window"] == 4

    async def test_the_boundary_day_is_inside_and_one_day_older_is_outside(
        self, neo4j_driver, backend
    ):
        """Isolated from the mixed fixture so the two rows are the whole answer.

        ``start_date`` is inclusive, and the comparison is by calendar day: a
        completion at one minute to midnight on the boundary day is inside, and
        the last minute of the day before it is the first one outside. Both rows
        are seeded, so this discriminates the boundary rather than merely
        counting.
        """
        await _seed_completion(
            neo4j_driver, WINDOW, "hc.edge_in", completed_at=_at(FIRST_DAY_IN, hour=23)
        )
        await _seed_completion(
            neo4j_driver, WINDOW, "hc.edge_out", completed_at=_at(LAST_DAY_OUT, hour=23)
        )

        result = await backend.get_habit_analytics(
            user_uid=WINDOW, window_start=FIRST_DAY_IN.isoformat()
        )

        assert result.is_ok
        assert result.value[0]["completions_in_window"] == 1

    async def test_a_temporally_typed_timestamp_still_compares(self, neo4j_driver, backend):
        """The normalisation earns its place: the writer decides the storage type.

        A ``completed_at`` stored as a native ``datetime`` compared raw against a
        date bound yields null, which drops the row — the failure would read as
        "this user was less consistent", never as an error.
        """
        await _seed_completion(
            neo4j_driver,
            WINDOW,
            "hc.temporal_only",
            completed_at=_at(TODAY),
            temporal_stamp=True,
        )

        result = await backend.get_habit_analytics(
            user_uid=WINDOW, window_start=FIRST_DAY_IN.isoformat()
        )

        assert result.is_ok
        assert result.value[0]["completions_in_window"] == 1

    async def test_a_completion_written_by_the_real_writer_is_counted(self, neo4j_driver, backend):
        """The fixture's shape is the writer's shape — proven, not assumed.

        Every other test in this file seeds ``:HabitCompletion`` nodes by hand.
        If the real write door labelled, owned or stamped them differently, the
        window would count zero in production while every hand-seeded assertion
        here stayed green. One round-trip through the backend the habits service
        actually writes through closes that gap: the label, the ``:OWNS`` edge
        the create statement writes alongside the node, and the ISO-string
        ``completed_at`` the mapper produces all have to line up with what the
        query matches.
        """
        from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
        from core.models.enums.neo_labels import NeoLabel
        from core.models.habit.completion import HabitCompletion

        completions_backend = UniversalNeo4jBackend[HabitCompletion](
            neo4j_driver, NeoLabel.HABIT_COMPLETION, HabitCompletion
        )
        now = datetime.now()
        created = await completions_backend.create(
            HabitCompletion(
                uid="hc.real_writer",
                habit_uid="habit.exercise",
                user_uid=WINDOW,
                completed_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        assert created.is_ok, "the writer refused the record; the rest proves nothing"

        result = await backend.get_habit_analytics(
            user_uid=WINDOW, window_start=FIRST_DAY_IN.isoformat()
        )

        assert result.is_ok
        assert result.value[0]["completions_in_window"] == 1

    async def test_another_users_completions_do_not_leak(self, seeded):
        """Scoped by the ``:OWNS`` edge, not by label.

        BULK owns six completions inside the same window as WINDOW's four. Each
        user must see only their own — a label-scoped count would report ten for
        both.
        """
        window = await seeded.get_habit_analytics(
            user_uid=WINDOW, window_start=FIRST_DAY_IN.isoformat()
        )
        bulk = await seeded.get_habit_analytics(
            user_uid=BULK, window_start=FIRST_DAY_IN.isoformat()
        )

        assert window.value[0]["completions_in_window"] == 4
        assert bulk.value[0]["completions_in_window"] == 6

    # ====================================================================
    # THE RATE, END TO END
    # ====================================================================

    async def test_a_steady_rate_reports_completions_per_week(self, service, seeded):
        """Four completions in a 30-day window ≈ 0.93 per week.

        The stored tally is 400 across a year-long span. Under the first→last
        denominator that pair *was* the metric, so if either still reached the
        arithmetic this could not pass.
        """
        result = await service.get_habit_consistency(WINDOW)

        assert result.is_ok
        assert result.value["consistency_score"] == pytest.approx(_score_for(4))
        assert result.value["completions_in_window"] == 4
        assert result.value["consistency_window_days"] == HabitConsistencyWindow.DAYS

    async def test_a_habit_that_stopped_reports_zero(self, service, seeded):
        """The case the redesign is for: a year of completions, none this month.

        The old arithmetic served a plausible non-zero rate for a habit that had
        stopped. The cumulative figures are still reported beside the 0.0 — the
        history is not erased, it just is not the rate.
        """
        result = await service.get_habit_consistency(STALE)

        assert result.is_ok
        assert result.value["consistency_score"] == 0.0
        assert result.value["completions_in_window"] == 0
        assert result.value["total_completions"] == 365, "positive control: the node was read"
        assert result.value["first_completion_at"] is not None

    async def test_bulk_logged_completions_with_no_analytics_node_still_report_a_real_score(
        self, service, seeded
    ):
        """``HabitCompletionBulk`` writes records but no node, and the rate does
        not need one.

        The old read required the node with a mandatory MATCH, so a user who
        logged every completion through the bulk door got a flat 0.0 for a habit
        they were actually keeping — and no instrument existed to notice, since
        nothing subscribes to that event.

        **This is also the shape where the payload contradicts itself**, and it
        is pinned deliberately rather than tolerated silently: six completions
        inside the window against a cumulative count of zero. Read from one
        graph state the window is a subset of the total, so that pair is
        impossible — which makes it a legible signal that the tally never saw
        those completions. Only the cumulative figures are behind; the score is
        correct.
        """
        result = await service.get_habit_consistency(BULK)

        assert result.is_ok
        assert result.value["consistency_score"] == pytest.approx(_score_for(6))
        assert result.value["total_completions"] == 0, "no node — cumulative figures are absent"
        assert result.value["last_completion_at"] is None
        # The impossible relation, asserted as the diagnostic it is.
        assert result.value["completions_in_window"] > result.value["total_completions"]

    async def test_a_user_with_nothing_at_all_reports_zeros(self, service, seeded):
        """No node, no completions — not even a ``:User`` row.

        Every match in the read is OPTIONAL and it aggregates, so it yields
        exactly one row of nulls rather than an empty result the service would
        have to treat as a separate case.
        """
        result = await service.get_habit_consistency("user_consistency_nobody")

        assert result.is_ok
        assert result.value["consistency_score"] == 0.0
        assert result.value["total_completions"] == 0
        assert result.value["completions_in_window"] == 0
