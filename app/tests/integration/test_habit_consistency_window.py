"""The user's habit-completion figures, derived from the completion records — against a real graph.

Every figure ``get_habit_analytics`` serves is a Cypher aggregate over the
user's ``:HabitCompletion`` records, so everything load-bearing about them —
which rows fall inside the window, what the edges do, how the timestamp's
storage type is compared, what the cumulative total includes, and which moments
are the first and last completion — is proven against the container rather than
a fake. The arithmetic that consumes the count, and the three degenerate
readings a span-based score would produce, are pinned DB-free in
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
3. **The total is every completion record the user owns**, inside the window or
   not, so the window is a subset of it by construction. The records are what
   every completion door writes — the bulk door included, which announces its
   completions as one ``HabitCompletionBulk`` — so the total counts them all.
4. **First and last are the records' own moments**, the earliest and latest
   ``completed_at`` up to the end of today: a record with no timestamp names no
   moment, and a future-stamped one has not happened yet.
5. **Ownership.** Scoped by the universal ``:OWNS`` edge (ADR-086), so another
   user's completions cannot leak into any figure.
6. **The upper bound.** A trailing window ends where the present does. Nothing
   refuses a future ``completed_at`` — ``TrackHabitRequest`` takes any ISO date,
   and the calendar's day-scoped complete door bounds ``on_date`` to genuine
   occurrence days but not to today — so a lower-bound-only predicate would
   count such a record in every window between now and its date, inflating the
   score permanently and silently.
7. **The timestamp's storage type.** It is an ISO datetime **string** on every
   live row (the mapper ``isoformat()``s the ``datetime`` the DTO carries), but
   the writer decides the storage type, not this reader. The normalisation is
   what keeps a temporally-typed value comparing correctly instead of silently
   matching nothing, which would read as "this user was less consistent", never
   as an error.

Nothing here seeds an analytics node: every figure stands on the records alone.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest
import pytest_asyncio

from core.constants import HabitConsistencyWindow
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid

WINDOW = seed_user_uid("consistency_window")
STALE = seed_user_uid("consistency_stale")
BULK = seed_user_uid("consistency_bulk")

TODAY = today_in(current_zone())
FIRST_DAY_IN = HabitConsistencyWindow.start_date(TODAY)
LAST_DAY_IN = HabitConsistencyWindow.end_date(TODAY)
LAST_DAY_OUT = TODAY - timedelta(days=HabitConsistencyWindow.DAYS)


def _score_for(count: int) -> float:
    return round(count / HabitConsistencyWindow.WEEKS, 2)


def _at(day: date, hour: int = 9) -> str:
    """The ISO datetime string every live writer produces for ``completed_at``."""
    return datetime.combine(day, time(hour=hour)).isoformat()


def _moment(day: date, hour: int = 9) -> datetime:
    """The instant ``_at`` stores, as the read returns it — the stored clock is UTC."""
    return datetime.combine(day, time(hour=hour), tzinfo=UTC)


async def _seed_completion(
    neo4j_driver,
    user_uid: str,
    completion_uid: str,
    *,
    completed_at: str | None,
    temporal_stamp: bool = False,
) -> None:
    """Own a HabitCompletion off the user — the shape every figure counts (ADR-086).

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


@pytest.mark.asyncio
@pytest.mark.integration
class TestHabitConsistencyWindow:
    """The trailing window, the derived total and the derived moments, against the testcontainer."""

    @pytest_asyncio.fixture
    async def backend(self, neo4j_driver, clean_neo4j):

        return build_production_backends(neo4j_driver)["cross_domain_backend"]

    @pytest_asyncio.fixture
    async def service(self, backend):
        from core.services.cross_domain_analytics_service import CrossDomainAnalyticsService

        return CrossDomainAnalyticsService(backend)

    @pytest_asyncio.fixture
    async def seeded(self, neo4j_driver, backend):
        """One user per shape the figures have to discriminate."""
        # WINDOW: four rows that count and four that must not. Total 8.
        await _seed_completion(neo4j_driver, WINDOW, "hc.win-today", completed_at=_at(TODAY))
        await _seed_completion(
            neo4j_driver, WINDOW, "hc.win-yesterday", completed_at=_at(TODAY - timedelta(days=1))
        )
        # The boundary itself, late in the day: the first day inside the window.
        await _seed_completion(
            neo4j_driver, WINDOW, "hc.win-boundary", completed_at=_at(FIRST_DAY_IN, hour=23)
        )
        # A timestamp written as a native temporal rather than an ISO string.
        await _seed_completion(
            neo4j_driver,
            WINDOW,
            "hc.win-temporal",
            completed_at=_at(TODAY, hour=10),
            temporal_stamp=True,
        )
        # One day past the boundary — exactly DAYS old, and late in that day, so
        # a truncation that rounded up rather than down would wrongly admit it.
        await _seed_completion(
            neo4j_driver, WINDOW, "hc.out-boundary", completed_at=_at(LAST_DAY_OUT, hour=23)
        )
        await _seed_completion(
            neo4j_driver, WINDOW, "hc.out-ancient", completed_at=_at(TODAY - timedelta(days=200))
        )
        # A record with no timestamp at all — excluded, not assumed recent.
        await _seed_completion(neo4j_driver, WINDOW, "hc.out-unstamped", completed_at=None)
        # Stamped in the future — outside a *trailing* window until its day comes.
        await _seed_completion(
            neo4j_driver, WINDOW, "hc.out-future", completed_at=_at(TODAY + timedelta(days=1))
        )

        # STALE: a real year of history, nothing inside the window.
        for offset in (31, 90, 400):
            await _seed_completion(
                neo4j_driver,
                STALE,
                f"hc.stale-{offset}",
                completed_at=_at(TODAY - timedelta(days=offset)),
            )

        # BULK: completions in the window.
        for n in range(6):
            await _seed_completion(
                neo4j_driver, BULK, f"hc.bulk-{n}", completed_at=_at(TODAY - timedelta(days=n))
            )

        return backend

    async def _read(self, backend, user_uid: str):
        result = await backend.get_habit_analytics(
            user_uid=user_uid,
            window_start=FIRST_DAY_IN.isoformat(),
            window_end=LAST_DAY_IN.isoformat(),
        )
        assert result.is_ok, result
        return result.value[0]

    # ====================================================================
    # THE WINDOW PREDICATE
    # ====================================================================

    async def test_only_completions_inside_the_window_are_counted(self, seeded):
        """Four of the user's eight records fall inside; four are excluded, each
        for its own reason (too old, exactly DAYS old, unstamped, future)."""
        row = await self._read(seeded, WINDOW)

        assert row["completions_in_window"] == 4

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
            neo4j_driver, WINDOW, "hc.edge-in", completed_at=_at(FIRST_DAY_IN, hour=23)
        )
        await _seed_completion(
            neo4j_driver, WINDOW, "hc.edge-out", completed_at=_at(LAST_DAY_OUT, hour=23)
        )

        row = await self._read(backend, WINDOW)

        assert row["completions_in_window"] == 1
        assert row["total_completions"] == 2, "both are records; only one is recent"

    async def test_a_future_stamped_completion_is_outside_the_trailing_window(
        self, neo4j_driver, backend
    ):
        """The upper bound, isolated so the two rows are the whole answer.

        Nothing refuses a future ``completed_at``: ``TrackHabitRequest`` takes
        any ISO date, and the calendar's day-scoped complete door bounds
        ``on_date`` to genuine occurrence days without bounding it at today. A
        lower-bound-only predicate would count such a record in *every* window
        between now and its date — a score inflated permanently, and silently,
        because nothing about the number looks wrong. Today's row is seeded
        beside it so this discriminates the bound rather than merely counting.
        """
        await _seed_completion(neo4j_driver, WINDOW, "hc.bound-today", completed_at=_at(TODAY))
        await _seed_completion(
            neo4j_driver,
            WINDOW,
            "hc.bound-tomorrow",
            completed_at=_at(TODAY + timedelta(days=1)),
        )

        row = await self._read(backend, WINDOW)

        assert row["completions_in_window"] == 1
        assert row["last_completed_at"] == _moment(TODAY), "a future record has not happened"

    async def test_a_temporally_typed_timestamp_still_compares(self, neo4j_driver, backend):
        """The normalisation earns its place: the writer decides the storage type.

        A ``completed_at`` stored as a native ``datetime`` compared raw against a
        date bound yields null, which drops the row — the failure would read as
        "this user was less consistent", never as an error. The derived moments
        read it too.
        """
        await _seed_completion(
            neo4j_driver,
            WINDOW,
            "hc.temporal-only",
            completed_at=_at(TODAY),
            temporal_stamp=True,
        )

        row = await self._read(backend, WINDOW)

        assert row["completions_in_window"] == 1
        assert row["first_completed_at"] == _moment(TODAY)

    # The writer stamps the host clock and the window counts a stamp by its stored
    # digits' day (the day of an instant reads through the zone from PR 3); the
    # window's own days are the zone's. The laptop's case keeps the two one clock.
    @pytest.mark.usefixtures("laptop_zone")
    async def test_a_completion_written_by_the_real_writer_is_counted(self, neo4j_driver, backend):
        """The fixture's shape is the writer's shape — proven, not assumed.

        Every other test in this file seeds ``:HabitCompletion`` nodes by hand.
        If the real write door labelled, owned or stamped them differently, the
        figures would read zero in production while every hand-seeded assertion
        here stayed green. One round-trip through the backend the habits service
        actually writes through closes that gap: the label, the ``:OWNS`` edge
        the create statement writes alongside the node, and the ISO-string
        ``completed_at`` the mapper produces all have to line up with what the
        query matches.
        """
        from core.models.habit.completion import HabitCompletion

        completions_backend = build_production_backends(neo4j_driver)["habit_completions_backend"]
        now = datetime.now()
        created = await completions_backend.create(
            HabitCompletion(
                uid="hc.real-writer",
                habit_uid="habit.exercise",
                user_uid=WINDOW,
                completed_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        assert created.is_ok, "the writer refused the record; the rest proves nothing"

        row = await self._read(backend, WINDOW)

        assert row["completions_in_window"] == 1
        assert row["total_completions"] == 1

    async def test_another_users_completions_do_not_leak(self, seeded):
        """Scoped by the ``:OWNS`` edge, not by label — in every figure.

        BULK owns six completions inside the same window as WINDOW's four, and
        STALE's oldest is older than any of WINDOW's. Each user must see only
        their own — a label-scoped read would report ten in the window and
        seventeen in total for all three, and one shared first moment.
        """
        window = await self._read(seeded, WINDOW)
        bulk = await self._read(seeded, BULK)
        stale = await self._read(seeded, STALE)

        assert (window["completions_in_window"], window["total_completions"]) == (4, 8)
        assert (bulk["completions_in_window"], bulk["total_completions"]) == (6, 6)
        assert (stale["completions_in_window"], stale["total_completions"]) == (0, 3)
        assert window["first_completed_at"] == _moment(TODAY - timedelta(days=200))
        assert stale["first_completed_at"] == _moment(TODAY - timedelta(days=400))

    # ====================================================================
    # THE DERIVED TOTAL AND MOMENTS
    # ====================================================================

    async def test_the_total_counts_every_record_and_the_moments_span_the_stamped_past(
        self, seeded
    ):
        """WINDOW's eight records all count; the moments run from 200 days ago to today.

        The unstamped record is a completion with no moment, so it is in the
        total and names neither end; tomorrow's record is in the total too, and
        has not happened yet. The latest moment is the native-typed row at 10:00
        today — later than the 09:00 string row — so the ordering compares
        instants across both storage shapes rather than the strings' digits.
        """
        row = await self._read(seeded, WINDOW)

        assert row["total_completions"] == 8
        assert row["first_completed_at"] == _moment(TODAY - timedelta(days=200))
        assert row["last_completed_at"] == _moment(TODAY, hour=10)

    async def test_bulk_logged_completions_reach_the_total(self, neo4j_driver, backend):
        """The bulk door's completions are records, so the total counts them.

        ``record_completions_bulk`` announces one ``HabitCompletionBulk`` rather
        than a ``HabitCompleted`` per habit; a total kept by a ``HabitCompleted``
        handler would never see these two. Driven through the real door, on two
        days, so the moments are the door's own.
        """
        from core.models.enums.entity_enums import EntityType
        from core.models.habit.habit import Habit
        from core.services.habits.habits_completion_service import HabitsCompletionService

        backends = build_production_backends(neo4j_driver)
        habits_backend = backends["habits_backend"]
        completions_backend = backends["habit_completions_backend"]
        habit_uid = "habit.bulk-logged"
        created = await habits_backend.create(
            Habit(uid=habit_uid, user_uid=BULK, entity_type=EntityType.HABIT, title="Bulk")
        )
        assert created.is_ok, created
        service = HabitsCompletionService(habits_backend, completions_backend)

        earlier = datetime.combine(TODAY - timedelta(days=3), time(hour=7))
        later = datetime.combine(TODAY - timedelta(days=1), time(hour=8))
        for moment in (earlier, later):
            logged = await service.record_completions_bulk([habit_uid], BULK, completed_at=moment)
            assert logged.is_ok and len(logged.value) == 1, logged

        row = await self._read(backend, BULK)

        assert row["total_completions"] == 2
        assert row["completions_in_window"] == 2
        assert row["first_completed_at"] == earlier.replace(tzinfo=UTC)
        assert row["last_completed_at"] == later.replace(tzinfo=UTC)

    # ====================================================================
    # THE PAYLOAD, END TO END
    # ====================================================================

    async def test_a_steady_rate_reports_completions_per_week(self, service, seeded):
        """Four completions in a 30-day window ≈ 0.93 per week, beside a total of 8.

        The moments span 200 days, so if the span between them reached the
        arithmetic this could not pass.
        """
        result = await service.get_habit_consistency(WINDOW)

        assert result.is_ok
        assert result.value["consistency_score"] == pytest.approx(_score_for(4))
        assert result.value["completions_in_window"] == 4
        assert result.value["total_completions"] == 8
        assert result.value["consistency_window_days"] == HabitConsistencyWindow.DAYS

    async def test_a_habit_that_stopped_reports_zero(self, service, seeded):
        """A year of completions, none this month: the score is 0.0 and the record stands beside it."""
        result = await service.get_habit_consistency(STALE)

        assert result.is_ok
        assert result.value["consistency_score"] == 0.0
        assert result.value["completions_in_window"] == 0
        assert result.value["total_completions"] == 3
        assert result.value["first_completion_at"] == _moment(TODAY - timedelta(days=400))
        assert result.value["last_completion_at"] == _moment(TODAY - timedelta(days=31))

    async def test_the_window_is_a_subset_of_the_total(self, service, seeded):
        """Both figures count the same records, so the window never exceeds the total."""
        for user_uid in (WINDOW, STALE, BULK):
            result = await service.get_habit_consistency(user_uid)

            assert result.is_ok
            assert result.value["completions_in_window"] <= result.value["total_completions"]

    async def test_a_user_with_nothing_at_all_reports_zeros(self, service, seeded):
        """No completions — not even a ``:User`` row.

        Every match in the read is OPTIONAL and it aggregates, so it yields
        exactly one row rather than an empty result the service would have to
        treat as a separate case.
        """
        result = await service.get_habit_consistency(seed_user_uid("consistency_nobody"))

        assert result.is_ok
        assert result.value["consistency_score"] == 0.0
        assert result.value["total_completions"] == 0
        assert result.value["completions_in_window"] == 0
        assert result.value["first_completion_at"] is None
        assert result.value["last_completion_at"] is None
