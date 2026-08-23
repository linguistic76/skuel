"""``consistency_score`` is a rate over a fixed trailing window.

It used to be the cumulative ``HabitAnalytics.total_completions`` divided by the
span between the user's first-ever habit completion and their most recent one.
That is not a rate, and it degenerated at three edges at once:

1. **One completion ever.** The tally upsert writes ``last_completion_at`` only
   ``ON MATCH``, so a user's first completion leaves it null — no span, no
   score, a flat **0.0** until they complete a second time.
2. **Several completions on one day.** ``days_active or 1`` turns a zero-length
   span into one day, and one day is a seventh of a week, so four completions
   in an afternoon read as **28 per week**.
3. **Stopping.** The denominator can only grow, so a user who kept a habit for a
   year and then stopped keeps a plausible non-zero score forever, decaying
   slowly instead of reporting the truth.

These tests pin the redesign at the service seam: what the window is, that the
divisor is a constant, and that neither the stored tally nor the stored stamps
reach the arithmetic. The window's *edges* are a Cypher predicate and are proven
against the container in ``tests/integration/test_habit_consistency_window.py``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pytest

from core.constants import HabitConsistencyWindow
from core.services.cross_domain_analytics_service import CrossDomainAnalyticsService
from core.utils.result_simplified import Result

USER = "user_consistency"


class _FakeBackend:
    """Serves one habit-analytics row and records the window bound it was asked for."""

    def __init__(
        self,
        *,
        completions_in_window: int,
        analytics: dict[str, Any] | None = None,
    ) -> None:
        self._completions_in_window = completions_in_window
        self._analytics = analytics
        self.window_start: str | None = None

    async def get_habit_analytics(
        self, user_uid: str, window_start: str
    ) -> Result[list[dict[str, Any]]]:
        self.window_start = window_start
        return Result.ok(
            [{"analytics": self._analytics, "completions_in_window": self._completions_in_window}]
        )


def _stored(
    total_completions: int, *, first: datetime | None, last: datetime | None
) -> dict[str, Any]:
    """A HabitAnalytics node with real cumulative figures on it."""
    return {
        "total_completions": total_completions,
        "first_completion_at": first,
        "last_completion_at": last,
    }


def _service(backend: _FakeBackend) -> CrossDomainAnalyticsService:
    return CrossDomainAnalyticsService(backend)  # type: ignore[arg-type]  # test double


# ============================================================================
# THE RATE
# ============================================================================


@pytest.mark.asyncio
async def test_a_steady_completion_rate_reports_that_rate():
    """12 completions in a 30-day window is 2.8 per week, and nothing else.

    The stored tally (400) and the two-year span are deliberately extreme: under
    the old arithmetic that pair *was* the metric, so if either still reached it
    this assertion could not pass.
    """
    backend = _FakeBackend(
        completions_in_window=12,
        analytics=_stored(400, first=datetime(2024, 1, 1), last=datetime(2026, 1, 1)),
    )

    result = await _service(backend).get_habit_consistency(USER)

    assert result.is_ok
    assert result.value["consistency_score"] == pytest.approx(round(12 / (30 / 7), 2))
    assert result.value["consistency_score"] == pytest.approx(2.8)
    assert result.value["completions_in_window"] == 12
    assert result.value["consistency_window_days"] == HabitConsistencyWindow.DAYS


# ============================================================================
# THE THREE DEGENERATE READINGS THIS REPLACES
# ============================================================================


@pytest.mark.asyncio
async def test_a_first_ever_completion_reports_a_rate_instead_of_the_unwritten_stamp_zero():
    """One completion is 1/30-days ≈ 0.23 per week — the measured rate.

    This is degenerate edge 1. ``upsert_habit_analytics`` stamps
    ``last_completion_at`` only ``ON MATCH``, so after a user's very first
    completion the node carries a ``first`` and no ``last``. The old score
    required both and read 0.0: "no consistency until you do it twice". The
    stamp is left null here on purpose — the window does not consult it.
    """
    today = datetime.now()
    backend = _FakeBackend(completions_in_window=1, analytics=_stored(1, first=today, last=None))

    result = await _service(backend).get_habit_consistency(USER)

    assert result.is_ok
    score = result.value["consistency_score"]
    assert score == pytest.approx(round(1 / (30 / 7), 2))
    assert score == pytest.approx(0.23)
    assert score != 0.0, "the unwritten-stamp degenerate reading"
    assert result.value["last_completion_at"] is None, "still reported, just not consulted"


@pytest.mark.asyncio
async def test_completions_all_on_one_day_are_not_extrapolated_to_a_weekly_rate():
    """Degenerate edge 2: four completions in an afternoon are 0.93/week, not 28.

    ``days_active or 1`` turned a zero-length span into a single day and then
    divided by a seventh of a week, inventing a rate from no elapsed time at
    all. A fixed denominator cannot do that: four completions inside thirty days
    is four completions inside thirty days, whichever day they landed on.
    """
    same_day = datetime(2026, 8, 23, 14, 0)
    backend = _FakeBackend(
        completions_in_window=4,
        analytics=_stored(4, first=same_day, last=same_day),
    )

    result = await _service(backend).get_habit_consistency(USER)

    assert result.is_ok
    score = result.value["consistency_score"]
    assert score == pytest.approx(round(4 / (30 / 7), 2))
    assert score == pytest.approx(0.93)
    assert score != pytest.approx(28.0), "the one-day extrapolation"


@pytest.mark.asyncio
async def test_a_habit_that_stopped_reports_zero_not_a_decaying_lifetime_average():
    """Degenerate edge 3, and the case the redesign is for.

    365 completions across a real year, none of them this month. The old
    arithmetic served a confident ~7/week that only ever crept downwards — a
    rate for a habit that had already stopped. The cumulative record survives
    beside the 0.0 rather than being erased.
    """
    backend = _FakeBackend(
        completions_in_window=0,
        analytics=_stored(365, first=datetime(2025, 1, 5), last=datetime(2026, 1, 5)),
    )

    result = await _service(backend).get_habit_consistency(USER)

    assert result.is_ok
    assert result.value["consistency_score"] == 0.0
    assert result.value["completions_in_window"] == 0
    # Not erased — the cumulative record is still served, it just is not the rate.
    assert result.value["total_completions"] == 365
    assert result.value["first_completion_at"] == datetime(2025, 1, 5)
    assert result.value["last_completion_at"] == datetime(2026, 1, 5)


# ============================================================================
# THE WINDOW BOUND HANDED TO THE QUERY
# ============================================================================


@pytest.mark.asyncio
async def test_the_query_is_bound_to_the_trailing_window_not_to_stored_history():
    """The service asks for an inclusive ISO date ``DAYS - 1`` days back."""
    backend = _FakeBackend(completions_in_window=3)

    await _service(backend).get_habit_consistency(USER)

    expected = date.today() - timedelta(days=HabitConsistencyWindow.DAYS - 1)
    assert backend.window_start == expected.isoformat()


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
# ABSENT / EMPTY READS
# ============================================================================


@pytest.mark.asyncio
async def test_bulk_logged_completions_with_no_analytics_node_still_report_a_real_score():
    """``HabitCompletionBulk`` has no analytics subscriber, and the count does not need one.

    The old read required the node with a mandatory MATCH, so a user who logged
    every completion through the bulk door got a flat 0.0 for a habit they were
    actually keeping. Counting ``:HabitCompletion`` records instead costs only
    the cumulative figures, which stay behind because their writer never saw
    those completions — reported honestly as 0 rather than back-filled.
    """
    backend = _FakeBackend(completions_in_window=6, analytics=None)

    result = await _service(backend).get_habit_consistency(USER)

    assert result.is_ok
    assert result.value["consistency_score"] == pytest.approx(round(6 / (30 / 7), 2))
    assert result.value["total_completions"] == 0
    assert result.value["first_completion_at"] is None
    assert result.value["last_completion_at"] is None
    # The tally's blindness to the bulk door, made visible rather than hidden.
    assert result.value["completions_in_window"] > result.value["total_completions"]


@pytest.mark.asyncio
async def test_a_read_that_returns_nothing_at_all_reports_zeros():
    """Defensive: the aggregation always yields a row, but an empty read is 0.0."""

    class _EmptyBackend:
        async def get_habit_analytics(
            self, user_uid: str, window_start: str
        ) -> Result[list[dict[str, Any]]]:
            return Result.ok([])

    service = CrossDomainAnalyticsService(_EmptyBackend())  # type: ignore[arg-type]  # test double

    result = await service.get_habit_consistency(USER)

    assert result.is_ok
    assert result.value["consistency_score"] == 0.0
    assert result.value["total_completions"] == 0
    assert result.value["completions_in_window"] == 0
