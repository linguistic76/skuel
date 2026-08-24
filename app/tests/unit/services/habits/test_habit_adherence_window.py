"""``success_rate``'s trailing window — HabitsProgressService._calculate_consistency_from_completions.

This is the habit's own **adherence ratio**: completions inside the window over
the number its frequency expects there, clamped to 1.0. It is not the
completions-per-week *rate* ``CrossDomainAnalyticsService.get_habit_consistency``
reports; both read :class:`HabitConsistencyWindow` so the span they share is one
constant rather than two coincidences.

It had no direct tests at all, and two defects that a test would have caught:

1. **No upper bound.** The filter was ``completed_at.date() >= as_of_date - 30``.
   Completing a *future* habit occurrence is legitimate behaviour — the
   calendar's day-scoped complete door admits any genuine occurrence day, and
   ``TrackHabitRequest`` takes any ISO date with no ceiling — so work that had
   not happened yet counted toward present adherence, and went on counting every
   day until its date arrived. The number is persisted as ``Habit.success_rate``,
   the canonical field every reader consumes, so the inflation outlived the read.
2. **A thirty-one day span against an expectation of thirty.** ``as_of_date - 30``
   with ``>=`` is inclusive of both ends, so the numerator was drawn from one day
   more than the denominator asks for. Invisible under the ``min(1.0, …)`` clamp
   for a well-kept habit, and a quiet over-report for every partially-kept one.

3. **The sample it filtered was arbitrary.** ``find_by`` caps at its limit and
   says nothing about having done so, and emits no ``ORDER BY`` unless asked, so
   the fetch behind both callers returned an arbitrary hundred of the habit's
   completions. Past a hundred records — a daily habit kept four months, or one
   carrying a run of legitimate future pre-completions — the window's own rows
   can be absent from that page entirely, and filtering it computes adherence
   from the wrong sample. Fixing which rows *count* is worth nothing if the rows
   are never fetched, so the fetch pages instead of capping.

   It pages **without** a date predicate, which is the non-obvious half.
   ``find_by`` binds a ``datetime`` bound as an ISO string, so pushing the window
   into the query would drop any ``completed_at`` stored as a native Neo4j
   temporal — Neo4j orders across types before it compares values, so such a row
   satisfies neither end of the range and vanishes from a query that looks
   correct. Windowing in Python is type-tolerant by construction: the mapper has
   normalised both storage forms to ``datetime`` before the filter runs.

The scoring method is synchronous and pure — it reads the habit, the completion
list and the anchor, and touches no backend and no clock — so those tests run
mock-free against sentinel dependencies. The fetch tests use a recording stub to
assert what the query was asked for.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

from core.constants import HabitConsistencyWindow
from core.models.enums import Priority, RecurrencePattern
from core.models.enums.entity_enums import EntityStatus as HabitStatus
from core.models.enums.entity_enums import EntityType
from core.models.habit.completion import HabitCompletion
from core.models.habit.habit import Habit
from core.services.habits.habits_progress_service import HabitsProgressService
from core.utils.result_simplified import Errors, Result

ANCHOR = date(2026, 8, 23)
FIRST_DAY_IN = HabitConsistencyWindow.start_date(ANCHOR)
LAST_DAY_OUT = ANCHOR - timedelta(days=HabitConsistencyWindow.DAYS)
FIXED_NOW = datetime(2026, 8, 23, 8, 0, 0)


@pytest.fixture
def service() -> HabitsProgressService:
    """Sentinel dependencies — the method under test is pure computation."""
    return HabitsProgressService(
        backend=object(),  # type: ignore[arg-type]  # test double
        completions_service=object(),
        relationship_service=object(),
    )


def _habit(
    pattern: RecurrencePattern = RecurrencePattern.DAILY, target_days_per_week: int = 7
) -> Habit:
    return Habit(
        uid="habit.test.1",
        user_uid="user_mike",
        title="Morning Exercise",
        entity_type=EntityType.HABIT,
        recurrence_pattern=pattern,
        target_days_per_week=target_days_per_week,
        current_streak=5,
        best_streak=10,
        status=HabitStatus.ACTIVE,
        priority=Priority.HIGH,
        created_at=FIXED_NOW,
        updated_at=FIXED_NOW,
    )


def _completions(*days: date) -> list[HabitCompletion]:
    """One completion per day, at the shape the writer stores."""
    return [
        HabitCompletion(
            uid=f"hc.{day.isoformat()}",
            habit_uid="habit.test.1",
            user_uid="user_mike",
            completed_at=datetime.combine(day, time(hour=9)),
            created_at=FIXED_NOW,
            updated_at=FIXED_NOW,
        )
        for day in days
    ]


# ============================================================================
# THE UPPER BOUND
# ============================================================================


def test_a_future_completion_does_not_count_toward_present_adherence(service):
    """The defect, stated as the assertion that used to fail.

    Two days kept out of thirty is 0.07. Marking tomorrow's occurrence complete
    is legitimate and the record is real, but it is not evidence about how
    consistent this habit has been *as of the anchor* — and under the old filter
    it would have read 0.1 today, tomorrow, and every day until it aged out.
    """
    kept = _completions(ANCHOR, ANCHOR - timedelta(days=1))
    ahead = _completions(ANCHOR + timedelta(days=1))

    without_future = service._calculate_consistency_from_completions(_habit(), kept, ANCHOR)
    with_future = service._calculate_consistency_from_completions(_habit(), kept + ahead, ANCHOR)

    assert without_future == pytest.approx(2 / HabitConsistencyWindow.DAYS)
    assert with_future == without_future, "a day that has not happened moved the number"


def test_pre_completing_a_run_of_future_days_cannot_reach_full_adherence(service):
    """The reachable shape, not just the single-row case.

    Nothing bounds how many future occurrences may be completed in one sitting —
    for a daily habit with no recurrence end, every future day is a genuine
    occurrence day. A lower-bound-only window let one sitting drive adherence
    to a perfect 1.0 with a single day actually kept.
    """
    kept = _completions(ANCHOR)
    ahead = _completions(*(ANCHOR + timedelta(days=n) for n in range(1, 40)))

    score = service._calculate_consistency_from_completions(_habit(), kept + ahead, ANCHOR)

    assert score == pytest.approx(1 / HabitConsistencyWindow.DAYS)
    assert score != 1.0, "forty pre-completions bought a perfect score"


def test_the_anchor_day_itself_counts(service):
    """The upper bound is inclusive — today's completion is inside today's window."""
    score = service._calculate_consistency_from_completions(_habit(), _completions(ANCHOR), ANCHOR)

    assert score == pytest.approx(1 / HabitConsistencyWindow.DAYS)


# ============================================================================
# THE SPAN
# ============================================================================


def test_the_window_is_exactly_days_long_so_the_numerator_matches_the_denominator(service):
    """Thirty distinct days in, thirty expected — the ratio is 1.0 exactly.

    The old span reached one day further back than ``expected`` accounts for, so
    a habit kept every day for thirty-one days scored above 1.0 before the clamp
    hid it. Here the count and the expectation are the same number by
    construction, which is only true if the window is exactly ``DAYS`` long.
    """
    every_day = _completions(
        *(FIRST_DAY_IN + timedelta(days=n) for n in range(HabitConsistencyWindow.DAYS))
    )

    assert len(every_day) == HabitConsistencyWindow.DAYS
    score = service._calculate_consistency_from_completions(_habit(), every_day, ANCHOR)

    assert score == pytest.approx(1.0)


def test_the_boundary_day_is_inside_and_one_day_older_is_outside(service):
    """``start_date`` is the first day *inside*; ``DAYS`` days back is the first outside."""
    inside = service._calculate_consistency_from_completions(
        _habit(), _completions(FIRST_DAY_IN), ANCHOR
    )
    outside = service._calculate_consistency_from_completions(
        _habit(), _completions(LAST_DAY_OUT), ANCHOR
    )

    assert inside == pytest.approx(1 / HabitConsistencyWindow.DAYS)
    assert outside == 0.0


# ============================================================================
# THE DENOMINATOR, PER FREQUENCY
# ============================================================================


def test_a_weekly_habit_is_measured_against_its_own_expectation(service):
    """Four expected across the window, not thirty — kept twice is 0.5."""
    kept = _completions(ANCHOR, ANCHOR - timedelta(days=7))

    score = service._calculate_consistency_from_completions(
        _habit(RecurrencePattern.WEEKLY), kept, ANCHOR
    )

    assert score == pytest.approx(2 / (HabitConsistencyWindow.DAYS // 7))
    assert score == pytest.approx(0.5)


def test_a_custom_habit_scales_its_weekly_target_to_the_window(service):
    """Three days a week over thirty days expects twelve."""
    kept = _completions(*(ANCHOR - timedelta(days=n) for n in range(6)))

    score = service._calculate_consistency_from_completions(
        _habit(RecurrencePattern.CUSTOM, target_days_per_week=3), kept, ANCHOR
    )

    expected = (3 * HabitConsistencyWindow.DAYS) // 7
    assert expected == 12
    assert score == pytest.approx(6 / expected)


def test_a_custom_habit_with_no_target_reports_zero_rather_than_dividing_by_it(service):
    """The guard: an expectation of zero is not a ratio, and must not raise."""
    score = service._calculate_consistency_from_completions(
        _habit(RecurrencePattern.CUSTOM, target_days_per_week=0), _completions(ANCHOR), ANCHOR
    )

    assert score == 0.0


def test_no_completions_at_all_reports_zero(service):
    assert service._calculate_consistency_from_completions(_habit(), [], ANCHOR) == 0.0


# ============================================================================
# THE FETCH — bounded in the QUERY, not after it
# ============================================================================


class _RecordingCompletions:
    """Records which fetch the scoring path reached for, and with what."""

    def __init__(self, rows: list[HabitCompletion] | None = None) -> None:
        self.paged_calls: list[dict] = []
        self.ranged_calls: list[dict] = []
        self._rows = rows or []

    async def get_all_completions_for_habit(self, habit_uid: str):
        self.paged_calls.append({"habit_uid": habit_uid})
        return Result.ok(self._rows)

    async def get_completions_for_habit(self, **kwargs):
        self.ranged_calls.append(kwargs)
        return Result.ok(self._rows)


@pytest.mark.asyncio
async def test_the_fetch_pages_the_whole_history_instead_of_taking_a_capped_page(service):
    """The finding, stated as the assertion that used to be impossible.

    The old fetch asked ``get_completions_for_habit(start_date=None,
    end_date=None, limit=100)``. ``find_by`` truncates at the limit without
    saying so and emits no ``ORDER BY`` unless asked, so that page was an
    arbitrary hundred rows — and a habit past a hundred completions could have
    every in-window row missing from it.
    """
    recorder = _RecordingCompletions()
    service.completions = recorder

    await service._completion_history("habit.test.1")

    assert recorder.paged_calls == [{"habit_uid": "habit.test.1"}]


@pytest.mark.asyncio
async def test_no_date_bound_reaches_the_query(service):
    """The non-obvious half: the window must NOT be pushed into Cypher.

    ``find_by`` binds a ``datetime`` bound as an ISO string, so a range predicate
    drops any ``completed_at`` stored as a native Neo4j temporal — it satisfies
    neither end, and the row vanishes from a query that looks correct. This
    pins that the ranged fetch is not the one this path uses; the window is
    applied in Python, after the mapper has normalised both storage forms.
    """
    recorder = _RecordingCompletions()
    service.completions = recorder

    await service._completion_history("habit.test.1")

    assert recorder.ranged_calls == [], "a date-bounded query would drop temporal rows"


@pytest.mark.asyncio
async def test_a_failed_read_reports_no_completions_rather_than_raising(service):
    """Degrades to the reading a habit with no completions gets: 0.0."""

    class _FailingCompletions:
        async def get_all_completions_for_habit(self, habit_uid: str):
            return Result.fail(Errors.database("read", "graph unavailable"))

    service.completions = _FailingCompletions()

    assert await service._completion_history("habit.test.1") == []
