"""
Learning-velocity trend arithmetic guard.

`get_learning_velocity` computes `previous = total - recent`. That subtraction is
only well-founded when both operands count the same thing.

SKUEL030 tranche 3 repointed `recent_kus` off the writer-less
`(:MasteryRecord)-[:HAS_VELOCITY]->` satellites onto the user's real MASTERED
edges. `total_kus` was still being read from `velocity.kus_mastered` — a counter
that ONLY `upsert_learning_velocity` (behind the `KnowledgeMastered` event
handler) increments. A mastery recorded through any of the three non-event
writers — notably `UserBackend.record_knowledge_mastery`, behind the pathways
progress route — bumped `recent` without bumping `total`, so `previous` went
negative and the trend/percentage figures went with it (Codex P2 on #737).

Both totals now come from the same MASTERED match. These tests pin that:
the service must read `total_kus` off the record, never the node counter.
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


def _record(
    *,
    event_counter: int,
    total_kus: int,
    recent_kus: int,
    velocity_node: bool = True,
) -> dict[str, Any]:
    return {
        "velocity": (
            {"kus_mastered": event_counter, "paths_completed": 2} if velocity_node else None
        ),
        "total_kus": total_kus,
        "recent_kus": recent_kus,
        "total_hours": 4.0,
    }


@pytest.mark.asyncio
async def test_previous_period_is_not_negative_when_counter_lags_the_edges():
    """The exact regression: 3 MASTERED edges, only 1 counted by the event handler.

    Reading `kus_mastered` (1) against `recent_kus` (2) gave previous = -1.
    Reading `total_kus` (3) gives previous = 1.
    """
    service = CrossDomainAnalyticsService(
        _FakeBackend(_record(event_counter=1, total_kus=3, recent_kus=2))
    )

    result = await service.get_learning_velocity("user_x", days_back=7)

    assert result.is_ok
    metrics = result.value
    assert metrics.kus_mastered_per_week == pytest.approx(2.0)
    assert metrics.velocity_trend == "accelerating"

    # This is the assertion that actually discriminates. Under the bug,
    # previous_per_week is -1.0, and the `if previous_per_week > 0` guard in
    # the percentage calculation is False, so change_pct silently collapses to
    # 0.0 — a plausible-looking number hiding a negative intermediate. Correct
    # arithmetic: previous = 3 - 2 = 1/wk, recent = 2/wk → +100%.
    #
    # (The trend string does NOT discriminate: `2 > -1.0 * 1.2` is also True,
    # so the buggy path reports "accelerating" as well. Asserting only on the
    # trend would have made this test vacuous.)
    assert metrics.compared_to_previous_period == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_total_kus_comes_from_the_record_not_the_node_counter():
    """A stale/zero node counter must not affect the arithmetic at all."""
    service = CrossDomainAnalyticsService(
        _FakeBackend(_record(event_counter=0, total_kus=10, recent_kus=4))
    )

    result = await service.get_learning_velocity("user_x", days_back=7)

    assert result.is_ok
    # previous = 10 - 4 = 6 per week vs recent 4 per week → slowing, not a
    # divide-by-zero or a negative-driven bogus "accelerating".
    assert result.value.velocity_trend == "slowing"
    assert result.value.compared_to_previous_period < 0.0


@pytest.mark.asyncio
async def test_paths_completed_still_reads_from_the_velocity_node():
    """Only the KU totals moved to the edges — paths_completed has no edge form."""
    service = CrossDomainAnalyticsService(
        _FakeBackend(_record(event_counter=5, total_kus=5, recent_kus=1))
    )

    result = await service.get_learning_velocity("user_x", days_back=30)

    assert result.is_ok
    assert result.value.paths_completed == 2


@pytest.mark.asyncio
async def test_real_velocity_without_a_velocity_node():
    """A missing LearningVelocity node must not suppress edge-derived figures.

    The node is only upserted by the KnowledgeMastered event handler, so a user
    whose masteries all came through non-event writers has none. The query used
    to require it with a mandatory MATCH, yielding zero rows and a bogus
    "no_data" for a user with live MASTERED edges (Codex P2 on #737). It now
    anchors on the User and OPTIONAL-matches the node, so `velocity` is null and
    the service must cope.
    """
    service = CrossDomainAnalyticsService(
        _FakeBackend(_record(event_counter=0, total_kus=8, recent_kus=6, velocity_node=False))
    )

    result = await service.get_learning_velocity("user_x", days_back=7)

    assert result.is_ok
    metrics = result.value
    assert metrics.velocity_trend != "no_data"
    assert metrics.kus_mastered_per_week == pytest.approx(6.0)
    # previous = 8 - 6 = 2/wk vs recent 6/wk → accelerating.
    assert metrics.velocity_trend == "accelerating"
    # No node means no path counter — 0, not an AttributeError on None.
    assert metrics.paths_completed == 0


@pytest.mark.asyncio
async def test_no_mastery_history_still_reports_no_data():
    """ "no_data" must mean "no masteries", not "no LearningVelocity node".

    Since a valid user now always yields a row, the emptiness test moved onto
    total_kus. Without it a brand-new learner would fall through to the trend
    arithmetic and be reported as "steady" with all-zero figures — an absence of
    measurement dressed up as a measurement.
    """
    service = CrossDomainAnalyticsService(
        _FakeBackend(_record(event_counter=0, total_kus=0, recent_kus=0, velocity_node=False))
    )

    result = await service.get_learning_velocity("user_x", days_back=30)

    assert result.is_ok
    assert result.value.velocity_trend == "no_data"
    assert result.value.kus_mastered_per_week == 0.0
