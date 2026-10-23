"""``consistency_score`` is a rate over a fixed trailing window, beside a derived record.

A rate needs a constant divisor. Divided instead by the span between the user's
first-ever habit completion and their most recent one, the score would
degenerate at three edges at once:

1. **One completion ever.** The span is zero, so the score is either nothing at
   all or — with ``days_active or 1`` — a week's rate invented from no time.
2. **Several completions on one day.** ``days_active or 1`` turns a zero-length
   span into one day, and one day is a seventh of a week, so four completions
   in an afternoon would read as **28 per week**.
3. **Stopping.** The denominator only grows, so a user who kept a habit for a
   year and then stopped would keep a plausible non-zero score forever,
   decaying slowly instead of reporting the truth.

Every figure in the payload is derived from the user's completion records on one
read: the cumulative total, the window inside it, and the first and last
completion moments. These tests pin the service seam: what the window is, that
the divisor is a constant, that the record is the backend's derived row passed
through, and that the span between the moments never reaches the arithmetic.
The window's *edges* and the derivation are Cypher and are proven against the
container in ``tests/integration/test_habit_consistency_window.py``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from core.constants import HabitConsistencyWindow
from core.ports.query_types import HabitAnalyticsRow
from core.services.cross_domain_analytics_service import CrossDomainAnalyticsService
from core.utils.result_simplified import Result
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone

USER = "user_consistency"


class _FakeBackend:
    """Serves one habit-analytics row and records the window bound it was asked for."""

    def __init__(
        self,
        *,
        completions_in_window: int,
        total_completions: int | None = None,
        first: datetime | None = None,
        last: datetime | None = None,
    ) -> None:
        self._completions_in_window = completions_in_window
        # Both counts come from the same records, so the window is a subset of
        # the total; a test that does not care about the total gets a consistent one.
        self._total_completions = (
            completions_in_window if total_completions is None else total_completions
        )
        self._first = first
        self._last = last
        self.window_start: str | None = None
        self.window_end: str | None = None

    async def get_habit_analytics(
        self, user_uid: str, window_start: str, window_end: str
    ) -> Result[list[HabitAnalyticsRow]]:
        self.window_start = window_start
        self.window_end = window_end
        return Result.ok(
            [
                {
                    "total_completions": self._total_completions,
                    "completions_in_window": self._completions_in_window,
                    "first_completed_at": self._first,
                    "last_completed_at": self._last,
                }
            ]
        )


def _service(backend: _FakeBackend) -> CrossDomainAnalyticsService:
    return CrossDomainAnalyticsService(backend)  # type: ignore[arg-type]  # test double


# ============================================================================
# THE RATE
# ============================================================================


@pytest.mark.asyncio
async def test_a_steady_completion_rate_reports_that_rate():
    """12 completions in a 30-day window is 2.8 per week, and nothing else.

    The derived total (400) and the two-year span between the moments are
    deliberately extreme: were either a divisor, this assertion could not pass.
    """
    backend = _FakeBackend(
        completions_in_window=12,
        total_completions=400,
        first=datetime(2024, 1, 1, tzinfo=UTC),
        last=datetime(2026, 1, 1, tzinfo=UTC),
    )

    result = await _service(backend).get_habit_consistency(USER)

    assert result.is_ok
    assert result.value["consistency_score"] == pytest.approx(round(12 / (30 / 7), 2))
    assert result.value["consistency_score"] == pytest.approx(2.8)
    assert result.value["completions_in_window"] == 12
    assert result.value["total_completions"] == 400
    assert result.value["consistency_window_days"] == HabitConsistencyWindow.DAYS


# ============================================================================
# THE THREE DEGENERATE READINGS A SPAN-BASED SCORE WOULD GIVE
# ============================================================================


@pytest.mark.asyncio
async def test_a_first_ever_completion_reports_a_rate_not_a_degenerate_span():
    """One completion is 1/30-days ≈ 0.23 per week — the measured rate.

    Degenerate edge 1: the first and last moments are the same instant, a span
    of zero. The window does not consult the span, so the score is what the
    window counted.
    """
    now = datetime.now(UTC)
    backend = _FakeBackend(completions_in_window=1, first=now, last=now)

    result = await _service(backend).get_habit_consistency(USER)

    assert result.is_ok
    score = result.value["consistency_score"]
    assert score == pytest.approx(round(1 / (30 / 7), 2))
    assert score == pytest.approx(0.23)
    assert score != 0.0, "the no-span degenerate reading"
    assert score != 7.0, "the one-day-span degenerate reading"


@pytest.mark.asyncio
async def test_completions_all_on_one_day_are_not_extrapolated_to_a_weekly_rate():
    """Degenerate edge 2: four completions in an afternoon are 0.93/week, not 28.

    ``days_active or 1`` would turn a zero-length span into a single day and
    then divide by a seventh of a week, inventing a rate from no elapsed time at
    all. A fixed denominator cannot do that: four completions inside thirty days
    is four completions inside thirty days, whichever day they landed on.
    """
    same_day = datetime(2026, 8, 23, 14, 0, tzinfo=UTC)
    backend = _FakeBackend(completions_in_window=4, first=same_day, last=same_day)

    result = await _service(backend).get_habit_consistency(USER)

    assert result.is_ok
    score = result.value["consistency_score"]
    assert score == pytest.approx(round(4 / (30 / 7), 2))
    assert score == pytest.approx(0.93)
    assert score != pytest.approx(28.0), "the one-day extrapolation"


@pytest.mark.asyncio
async def test_a_habit_that_stopped_reports_zero_not_a_decaying_lifetime_average():
    """Degenerate edge 3: 365 completions across a real year, none of them this month.

    A span-based score would serve a confident ~7/week that only ever crept
    downwards — a rate for a habit that had already stopped. The cumulative
    record stands beside the 0.0.
    """
    backend = _FakeBackend(
        completions_in_window=0,
        total_completions=365,
        first=datetime(2025, 1, 5, 9, 0, tzinfo=UTC),
        last=datetime(2026, 1, 5, 9, 0, tzinfo=UTC),
    )

    result = await _service(backend).get_habit_consistency(USER)

    assert result.is_ok
    assert result.value["consistency_score"] == 0.0
    assert result.value["completions_in_window"] == 0
    assert result.value["total_completions"] == 365
    assert result.value["first_completion_at"] == datetime(2025, 1, 5, 9, 0, tzinfo=UTC)
    assert result.value["last_completion_at"] == datetime(2026, 1, 5, 9, 0, tzinfo=UTC)


# ============================================================================
# THE WINDOW BOUND HANDED TO THE QUERY
# ============================================================================


@pytest.mark.asyncio
async def test_the_query_is_bound_to_the_trailing_window_not_to_stored_history():
    """The service asks for an inclusive ISO date ``DAYS - 1`` days back."""
    backend = _FakeBackend(completions_in_window=3)

    await _service(backend).get_habit_consistency(USER)

    expected = today_in(current_zone()) - timedelta(days=HabitConsistencyWindow.DAYS - 1)
    assert backend.window_start == expected.isoformat()


@pytest.mark.asyncio
async def test_the_window_is_bounded_at_today_so_a_future_stamp_cannot_inflate_it():
    """A trailing window ends where the present does.

    Nothing refuses a future ``completed_at``: ``TrackHabitRequest`` takes any
    ISO date, and the calendar's day-scoped complete door bounds ``on_date`` to
    genuine occurrence days without bounding it at today. Without an upper bound
    a record stamped next year would count in *every* window between now and
    then — a score inflated permanently and silently, since nothing about the
    reading looks wrong. Both ends come from the window class so they cannot
    drift from the constant divisor between them.
    """
    backend = _FakeBackend(completions_in_window=3)

    await _service(backend).get_habit_consistency(USER)

    assert backend.window_end == today_in(current_zone()).isoformat()


def test_the_window_is_exactly_days_calendar_days_inclusive_of_today():
    """``start_date`` and ``WEEKS`` describe the same span, or the rate is wrong.

    The divisor is a constant, so it is only correct if the counted span is
    exactly that long. Off by one day here and every consistency score in the
    app is off by 3%, invisibly.
    """
    today = date(2026, 8, 23)
    start = HabitConsistencyWindow.start_date(today)

    assert (today - start).days + 1 == HabitConsistencyWindow.DAYS
    assert pytest.approx(HabitConsistencyWindow.DAYS / 7) == HabitConsistencyWindow.WEEKS


def test_a_completion_exactly_days_old_falls_outside_the_window():
    """The boundary, stated once here and enforced in Cypher by ``>=``.

    ``start_date`` is the first day *inside*. A completion one day older is
    outside; one on the boundary itself is inside.
    """
    today = date(2026, 8, 23)
    start = HabitConsistencyWindow.start_date(today)

    assert (today - timedelta(days=HabitConsistencyWindow.DAYS)).isoformat() < start.isoformat()
    assert (
        today - timedelta(days=HabitConsistencyWindow.DAYS - 1)
    ).isoformat() == start.isoformat()


# ============================================================================
# EMPTY READS
# ============================================================================


@pytest.mark.asyncio
async def test_a_read_that_returns_nothing_at_all_reports_zeros():
    """Defensive: the aggregation always yields a row, but an empty read is 0.0."""

    class _EmptyBackend:
        async def get_habit_analytics(
            self, user_uid: str, window_start: str, window_end: str
        ) -> Result[list[HabitAnalyticsRow]]:
            return Result.ok([])

    service = CrossDomainAnalyticsService(_EmptyBackend())  # type: ignore[arg-type]  # test double

    result = await service.get_habit_consistency(USER)

    assert result.is_ok
    assert result.value["consistency_score"] == 0.0
    assert result.value["total_completions"] == 0
    assert result.value["completions_in_window"] == 0
    assert result.value["first_completion_at"] is None
    assert result.value["last_completion_at"] is None
