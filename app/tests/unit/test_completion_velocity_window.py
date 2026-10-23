"""``completion_velocity`` is a rate over a fixed trailing window, beside a derived total.

A rate needs a constant divisor. Divided instead by the span between the user's
first-ever completion and their most recent one, the number could only decay as
the span grew, and it would degenerate at both edges: a single completion makes
the span zero, which reads either as no rate at all or — with ``days_active or
1`` — as a full week's rate extrapolated from no elapsed time.

Every figure in the payload is derived from the user's tasks on one read: the
total, the window inside it, and the first and last completion days. Nothing is
stored that could drift from the graph, so the payload cannot contradict itself.

These tests pin the service seam: what the window is, that the divisor is a
constant, that the counts and days are the backend's derived row passed through,
and that the span between the days never reaches the arithmetic. The window's
*edges* and the derivation are Cypher and are proven against the container in
``tests/integration/test_completion_velocity_window.py``.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from core.constants import CompletionVelocityWindow
from core.ports.query_types import ProductivityAnalyticsRow
from core.services.cross_domain_analytics_service import CrossDomainAnalyticsService
from core.utils.result_simplified import Result
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone

USER = "user_velocity"


class _FakeBackend:
    """Serves one productivity row and records the window bound it was asked for."""

    def __init__(
        self,
        *,
        completed_in_window: int,
        tasks_completed: int | None = None,
        first: date | None = None,
        last: date | None = None,
    ) -> None:
        self._completed_in_window = completed_in_window
        # Both counts come from one traversal, so the window is a subset of the
        # total; a test that does not care about the total gets a consistent one.
        self._tasks_completed = completed_in_window if tasks_completed is None else tasks_completed
        self._first = first
        self._last = last
        self.window_start: str | None = None
        self.window_end: str | None = None

    async def get_productivity_analytics(
        self, user_uid: str, window_start: str, window_end: str
    ) -> Result[list[ProductivityAnalyticsRow]]:
        self.window_start = window_start
        self.window_end = window_end
        return Result.ok(
            [
                {
                    "tasks_completed": self._tasks_completed,
                    "completed_in_window": self._completed_in_window,
                    "first_completed_on": self._first,
                    "last_completed_on": self._last,
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
    """12 completions in a 30-day window is 2.8 tasks/week, and nothing else.

    The derived total (400) and the two-year span between the completion days
    are deliberately extreme: were either a divisor, this assertion could not
    pass.
    """
    backend = _FakeBackend(
        completed_in_window=12,
        tasks_completed=400,
        first=date(2024, 1, 1),
        last=date(2026, 1, 1),
    )

    result = await _service(backend).get_productivity_metrics(USER)

    assert result.is_ok
    assert result.value["completion_velocity"] == pytest.approx(round(12 / (30 / 7), 2))
    assert result.value["completion_velocity"] == pytest.approx(2.8)
    assert result.value["tasks_completed_in_window"] == 12
    assert result.value["tasks_completed"] == 400
    assert result.value["velocity_window_days"] == CompletionVelocityWindow.DAYS


@pytest.mark.asyncio
async def test_completions_all_older_than_the_window_report_zero_not_a_lifetime_figure():
    """0.0 is the honest reading of "nothing completed this month".

    The user has 85 completed tasks across a real span, so a span-based rate
    would serve a plausible non-zero number forever — a rate for work that
    stopped. A fixed window reports what is true now, and the cumulative figures
    stand beside it.
    """
    backend = _FakeBackend(
        completed_in_window=0,
        tasks_completed=85,
        first=date(2026, 1, 5),
        last=date(2026, 6, 11),
    )

    result = await _service(backend).get_productivity_metrics(USER)

    assert result.is_ok
    assert result.value["completion_velocity"] == 0.0
    assert result.value["tasks_completed_in_window"] == 0
    assert result.value["tasks_completed"] == 85
    assert result.value["first_completion_at"] == date(2026, 1, 5)
    assert result.value["last_completion_at"] == date(2026, 6, 11)


@pytest.mark.asyncio
async def test_a_single_completion_today_reports_one_task_per_window_not_zero_and_not_seven():
    """One completion is 1/30-days ≈ 0.23 tasks/week — the measured rate.

    A span-based rate would be wrong here in one of two opposite directions:
    0.0 ("no rate until you complete twice") or 7.0 (a full week extrapolated
    from a span of zero days). 0.23 claims nothing beyond what happened: one
    task inside a thirty-day window.
    """
    today = today_in(current_zone())
    backend = _FakeBackend(completed_in_window=1, first=today, last=today)

    result = await _service(backend).get_productivity_metrics(USER)

    assert result.is_ok
    velocity = result.value["completion_velocity"]
    assert velocity == pytest.approx(round(1 / (30 / 7), 2))
    assert velocity == pytest.approx(0.23)
    assert velocity != 0.0, "the no-span degenerate reading"
    assert velocity != 7.0, "the one-day-span degenerate reading"


# ============================================================================
# THE DERIVED FIGURES PASS THROUGH
# ============================================================================


@pytest.mark.asyncio
async def test_the_first_and_last_completion_days_are_the_derived_days():
    """The payload's ``first_completion_at`` / ``last_completion_at`` are the
    backend's derived days, unchanged — calendar dates, as ``completion_date`` is."""
    backend = _FakeBackend(
        completed_in_window=30,
        tasks_completed=85,
        first=date(2026, 1, 5),
        last=date(2026, 8, 22),
    )

    result = await _service(backend).get_productivity_metrics(USER)

    assert result.is_ok
    assert result.value["tasks_completed"] == 85
    assert result.value["first_completion_at"] == date(2026, 1, 5)
    assert result.value["last_completion_at"] == date(2026, 8, 22)


@pytest.mark.asyncio
async def test_a_user_with_completions_but_no_stamped_day_reports_no_days():
    """Completed tasks that carry no ``completion_date`` are in the total and
    name no day, so both days are ``None`` beside a real count."""
    backend = _FakeBackend(completed_in_window=0, tasks_completed=3)

    result = await _service(backend).get_productivity_metrics(USER)

    assert result.is_ok
    assert result.value["tasks_completed"] == 3
    assert result.value["first_completion_at"] is None
    assert result.value["last_completion_at"] is None


# ============================================================================
# THE WINDOW BOUND HANDED TO THE QUERY
# ============================================================================


@pytest.mark.asyncio
async def test_the_query_is_bound_to_the_trailing_window_not_to_stored_history():
    """The service asks for an inclusive ISO date ``DAYS - 1`` days back."""
    backend = _FakeBackend(completed_in_window=3)

    await _service(backend).get_productivity_metrics(USER)

    expected = today_in(current_zone()) - timedelta(days=CompletionVelocityWindow.DAYS - 1)
    assert backend.window_start == expected.isoformat()


@pytest.mark.asyncio
async def test_the_window_is_bounded_at_today_so_a_future_stamp_cannot_inflate_it():
    """A trailing window ends where the present does.

    Without an upper bound a future-stamped task would count in *every* window
    between now and its date: a velocity inflated permanently and silently,
    because nothing about the number looks wrong. The bound is the reader's own
    guarantee, not a writer's — a stamp already in the graph is contained by it
    alone. Both ends come from the window class so they cannot drift from the
    constant divisor between them.
    """
    backend = _FakeBackend(completed_in_window=3)

    await _service(backend).get_productivity_metrics(USER)

    assert backend.window_end == today_in(current_zone()).isoformat()


def test_the_window_is_exactly_days_calendar_days_inclusive_of_today():
    """``start_date`` and ``WEEKS`` describe the same span, or the rate is wrong.

    The divisor is a constant, so it is only correct if the counted span is
    exactly that long. Off by one day here and every velocity in the app is
    off by 3%, invisibly.
    """
    today = date(2026, 8, 23)
    start = CompletionVelocityWindow.start_date(today)

    assert (today - start).days + 1 == CompletionVelocityWindow.DAYS
    assert pytest.approx(CompletionVelocityWindow.DAYS / 7) == CompletionVelocityWindow.WEEKS


def test_a_completion_exactly_days_old_falls_outside_the_window():
    """The boundary, stated once here and enforced in Cypher by ``>=``.

    ``start_date`` is the first day *inside*. A stamp one day older is outside;
    the stamp on the boundary itself is inside.
    """
    today = date(2026, 8, 23)
    start = CompletionVelocityWindow.start_date(today)

    assert (today - timedelta(days=CompletionVelocityWindow.DAYS)).isoformat() < start.isoformat()
    assert (
        today - timedelta(days=CompletionVelocityWindow.DAYS - 1)
    ).isoformat() == start.isoformat()


# ============================================================================
# EMPTY READS
# ============================================================================


@pytest.mark.asyncio
async def test_a_read_that_returns_nothing_at_all_reports_zeros():
    """Defensive: the aggregation always yields a row, but an empty read is 0.0."""

    class _EmptyBackend:
        async def get_productivity_analytics(
            self, user_uid: str, window_start: str, window_end: str
        ) -> Result[list[ProductivityAnalyticsRow]]:
            return Result.ok([])

    service = CrossDomainAnalyticsService(_EmptyBackend())  # type: ignore[arg-type]  # test double

    result = await service.get_productivity_metrics(USER)

    assert result.is_ok
    assert result.value["completion_velocity"] == 0.0
    assert result.value["tasks_completed"] == 0
    assert result.value["tasks_completed_in_window"] == 0
    assert result.value["first_completion_at"] is None
    assert result.value["last_completion_at"] is None
