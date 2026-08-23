"""``completion_velocity`` is a rate over a fixed trailing window.

It used to be the lifetime completion count divided by the span between the
user's first-ever completion and their most recent one. That is not a rate: the
denominator can only grow, so the number could only decay, and it degenerated at
both edges. Before the completion stamps were both written, a first completion
left ``last_completion_at`` null and velocity read **0.0** — no rate until you
complete twice. After (#1134), ``first == last`` makes ``days_active or 1``
report **7.0 tasks/week** extrapolated from a zero-length window. Both numbers
are symptoms of the denominator, not of the stamps.

These tests pin the redesign at the service seam: what the window is, that the
divisor is a constant, and that the stored lifetime figures no longer reach the
arithmetic. The window's *edges* are a Cypher predicate and are proven against
the container in ``tests/integration/test_completion_velocity_window.py``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pytest

from core.constants import CompletionVelocityWindow
from core.services.cross_domain_analytics_service import CrossDomainAnalyticsService
from core.utils.result_simplified import Result

USER = "user_velocity"


class _FakeBackend:
    """Serves one productivity row and records the window bound it was asked for."""

    def __init__(
        self,
        *,
        completed_in_window: int,
        analytics: dict[str, Any] | None = None,
    ) -> None:
        self._completed_in_window = completed_in_window
        self._analytics = analytics
        self.window_start: str | None = None
        self.window_end: str | None = None

    async def get_productivity_analytics(
        self, user_uid: str, window_start: str, window_end: str
    ) -> Result[list[dict[str, Any]]]:
        self.window_start = window_start
        self.window_end = window_end
        return Result.ok(
            [{"analytics": self._analytics, "completed_in_window": self._completed_in_window}]
        )


def _stored(tasks_completed: int, *, first: datetime, last: datetime) -> dict[str, Any]:
    """A ProductivityAnalytics node with real lifetime figures on it."""
    return {
        "tasks_completed": tasks_completed,
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
    """12 completions in a 30-day window is 2.8 tasks/week, and nothing else.

    The stored lifetime count (400) and the two-year span are deliberately
    extreme: under the old arithmetic they *were* the metric, so if either still
    reached it this assertion could not pass.
    """
    backend = _FakeBackend(
        completed_in_window=12,
        analytics=_stored(400, first=datetime(2024, 1, 1), last=datetime(2026, 1, 1)),
    )

    result = await _service(backend).get_productivity_metrics(USER)

    assert result.is_ok
    assert result.value["completion_velocity"] == pytest.approx(round(12 / (30 / 7), 2))
    assert result.value["completion_velocity"] == pytest.approx(2.8)
    assert result.value["tasks_completed_in_window"] == 12
    assert result.value["velocity_window_days"] == CompletionVelocityWindow.DAYS


@pytest.mark.asyncio
async def test_completions_all_older_than_the_window_report_zero_not_a_lifetime_figure():
    """0.0 is the honest reading of "nothing completed this month".

    This is the case the redesign is *for*. The user has 85 lifetime
    completions across a real span, so the old arithmetic served a plausible
    non-zero number forever — a rate for work that stopped. A fixed window
    reports what is true now, and the cumulative figures survive untouched
    beside it rather than being erased.
    """
    backend = _FakeBackend(
        completed_in_window=0,
        analytics=_stored(85, first=datetime(2026, 1, 5), last=datetime(2026, 6, 11)),
    )

    result = await _service(backend).get_productivity_metrics(USER)

    assert result.is_ok
    assert result.value["completion_velocity"] == 0.0
    assert result.value["tasks_completed_in_window"] == 0
    # Not erased — the lifetime record is still served, it just is not the rate.
    assert result.value["tasks_completed"] == 85
    assert result.value["first_completion_at"] == datetime(2026, 1, 5)
    assert result.value["last_completion_at"] == datetime(2026, 6, 11)


@pytest.mark.asyncio
async def test_a_single_completion_today_reports_one_task_per_window_not_zero_and_not_seven():
    """One completion is 1/30-days ≈ 0.23 tasks/week — the measured rate.

    Both historical readings were wrong in opposite directions and for the same
    reason. 0.0 said "no rate until you complete twice"; 7.0 extrapolated a full
    week from a window of zero elapsed days. 0.23 claims nothing beyond what
    happened: one task inside a thirty-day window. It is low, and it is supposed
    to be — a first completion is not evidence of a weekly rate, and the window
    is what stops the metric from pretending otherwise.
    """
    today = datetime.now()
    backend = _FakeBackend(completed_in_window=1, analytics=_stored(1, first=today, last=today))

    result = await _service(backend).get_productivity_metrics(USER)

    assert result.is_ok
    velocity = result.value["completion_velocity"]
    assert velocity == pytest.approx(round(1 / (30 / 7), 2))
    assert velocity == pytest.approx(0.23)
    assert velocity != 0.0, "the pre-#1134 degenerate reading"
    assert velocity != 7.0, "the post-#1134 degenerate reading"


# ============================================================================
# THE WINDOW BOUND HANDED TO THE QUERY
# ============================================================================


@pytest.mark.asyncio
async def test_the_query_is_bound_to_the_trailing_window_not_to_stored_history():
    """The service asks for an inclusive ISO date ``DAYS - 1`` days back."""
    backend = _FakeBackend(completed_in_window=3)

    await _service(backend).get_productivity_metrics(USER)

    expected = date.today() - timedelta(days=CompletionVelocityWindow.DAYS - 1)
    assert backend.window_start == expected.isoformat()


@pytest.mark.asyncio
async def test_the_window_is_bounded_at_today_so_a_future_stamp_cannot_inflate_it():
    """A trailing window ends where the present does.

    ``TaskCreateRequest`` refuses a future ``completion_date`` — "semantically
    impossible and would pin itself atop completion-date-ordered reads" — but
    ``TaskUpdateRequest`` does not, so the stamp is reachable. Without an upper
    bound such a task counts in *every* window between now and its date, a
    velocity inflated permanently and silently. Both ends come from the window
    class so they cannot drift from the constant divisor between them.
    """
    backend = _FakeBackend(completed_in_window=3)

    await _service(backend).get_productivity_metrics(USER)

    assert backend.window_end == date.today().isoformat()


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
# ABSENT / EMPTY READS
# ============================================================================


@pytest.mark.asyncio
async def test_completions_with_no_analytics_node_still_report_a_real_velocity():
    """The vault ``- [x]`` door writes no node, and the count does not need one.

    The old read required the node with a mandatory MATCH, so this user got a
    flat 0.0 — the same confident zero the reconciliation instrument exists to
    correct. Velocity is derived from the graph, so an absent node costs only
    the cumulative figures.
    """
    backend = _FakeBackend(completed_in_window=6, analytics=None)

    result = await _service(backend).get_productivity_metrics(USER)

    assert result.is_ok
    assert result.value["completion_velocity"] == pytest.approx(round(6 / (30 / 7), 2))
    assert result.value["tasks_completed"] == 0
    assert result.value["first_completion_at"] is None
    assert result.value["last_completion_at"] is None


@pytest.mark.asyncio
async def test_a_read_that_returns_nothing_at_all_reports_zeros():
    """Defensive: the aggregation always yields a row, but an empty read is 0.0."""

    class _EmptyBackend:
        async def get_productivity_analytics(
            self, user_uid: str, window_start: str, window_end: str
        ) -> Result[list[dict[str, Any]]]:
            return Result.ok([])

    service = CrossDomainAnalyticsService(_EmptyBackend())  # type: ignore[arg-type]  # test double

    result = await service.get_productivity_metrics(USER)

    assert result.is_ok
    assert result.value["completion_velocity"] == 0.0
    assert result.value["tasks_completed"] == 0
