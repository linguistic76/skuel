"""
Learning-velocity arithmetic over the derived row.

`get_learning_velocity` computes `previous = total - recent`. That subtraction is
only well-founded when both operands count the same thing — and they do: the
backend counts `total_kus` and `recent_kus` from the same MASTERED edges, so the
previous period can never be negative. `paths_completed` is the row's count of the
user's completed enrollments, passed through.

These tests pin the service seam over a fake row; the counts themselves are Cypher
and are proven in `tests/integration/test_mastered_readers_count_kus_only.py` and
`tests/integration/test_learning_velocity_paths_completed.py`.
"""

from typing import Any

import pytest

from core.services.cross_domain_analytics_service import CrossDomainAnalyticsService
from core.utils.result_simplified import Result


class _FakeBackend:
    """Returns one velocity record verbatim."""

    def __init__(self, record: dict[str, Any]) -> None:
        self._record = record

    async def get_learning_velocity_metrics(
        self, user_uid: str, start_date: str
    ) -> Result[list[dict[str, Any]]]:
        return Result.ok([self._record])


def _record(*, total_kus: int, recent_kus: int, paths_completed: int = 2) -> dict[str, Any]:
    return {
        "total_kus": total_kus,
        "recent_kus": recent_kus,
        "total_hours": 4.0,
        "paths_completed": paths_completed,
    }


@pytest.mark.asyncio
async def test_the_previous_period_is_total_minus_recent():
    """3 masteries, 2 of them this week: previous = 1/wk, recent = 2/wk → +100%.

    The percentage is the discriminating assertion. A negative `previous` would
    fail the `previous_per_week > 0` guard and collapse the percentage to 0.0 — a
    plausible-looking number hiding a negative intermediate — while the trend
    string would still read "accelerating" (`2 > -1.0 * 1.2` is also true).
    """
    service = CrossDomainAnalyticsService(_FakeBackend(_record(total_kus=3, recent_kus=2)))

    result = await service.get_learning_velocity("user_x", days_back=7)

    assert result.is_ok
    metrics = result.value
    assert metrics.kus_mastered_per_week == pytest.approx(2.0)
    assert metrics.velocity_trend == "accelerating"
    assert metrics.compared_to_previous_period == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_a_slower_recent_period_reads_slowing():
    """previous = 10 - 4 = 6 per week vs recent 4 per week → slowing."""
    service = CrossDomainAnalyticsService(_FakeBackend(_record(total_kus=10, recent_kus=4)))

    result = await service.get_learning_velocity("user_x", days_back=7)

    assert result.is_ok
    assert result.value.velocity_trend == "slowing"
    assert result.value.compared_to_previous_period < 0.0


@pytest.mark.asyncio
async def test_paths_completed_is_the_rows_count():
    service = CrossDomainAnalyticsService(
        _FakeBackend(_record(total_kus=5, recent_kus=1, paths_completed=3))
    )

    result = await service.get_learning_velocity("user_x", days_back=30)

    assert result.is_ok
    assert result.value.paths_completed == 3


@pytest.mark.asyncio
async def test_no_mastery_history_reports_no_data_and_still_its_paths():
    """ "no_data" means "no masteries" — the paths a learner completed are still served.

    Without the emptiness test a brand-new learner would fall through to the trend
    arithmetic and be reported as "steady" with all-zero figures — an absence of
    measurement dressed up as a measurement.
    """
    service = CrossDomainAnalyticsService(
        _FakeBackend(_record(total_kus=0, recent_kus=0, paths_completed=1))
    )

    result = await service.get_learning_velocity("user_x", days_back=30)

    assert result.is_ok
    assert result.value.velocity_trend == "no_data"
    assert result.value.kus_mastered_per_week == 0.0
    assert result.value.paths_completed == 1
