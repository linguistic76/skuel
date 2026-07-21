"""
Unit tests for LifePathIntelligenceService — pure recommendation logic.

The service takes pre-computed alignment data and derives prioritized
recommendations and a daily focus; there is no graph or LLM involved, so
these are honest unit tests (no mocks required).
"""

from __future__ import annotations

import pytest

from core.ports.query_types import AlignmentDimensions, LifePathAlignmentResult
from core.services.lifepath.lifepath_intelligence_service import LifePathIntelligenceService

pytestmark = pytest.mark.asyncio

_USER = "user_test_lifepath_intel_unit"


@pytest.fixture
def intelligence() -> LifePathIntelligenceService:
    return LifePathIntelligenceService(user_service=None)


def _alignment(
    dimensions: AlignmentDimensions,
    knowledge_stats: dict[str, int] | None = None,
) -> LifePathAlignmentResult:
    return {
        "life_path_uid": "lp.test.intel",
        "alignment_score": 0.5,
        "alignment_level": "exploring",
        "dimensions": dimensions,
        "knowledge_stats": knowledge_stats or {"total": 0, "embodied": 0, "theoretical": 0},
        "recommendations": [],
    }


class TestGetRecommendations:
    async def test_no_alignment_data_yields_getting_started_defaults(self, intelligence):
        result = await intelligence.get_recommendations(_USER, None)

        assert result.is_ok
        recs = result.value
        assert all(r["type"] == "getting_started" for r in recs)
        assert recs[0]["priority"] == "high"

    async def test_empty_dimensions_yields_defaults_not_crash(self, intelligence):
        """LifePathAlignmentResult is total=False — a dimensions-less payload
        must degrade to the getting-started defaults, not ValueError on min()."""
        result = await intelligence.get_recommendations(_USER, {"alignment_score": 0.2})

        assert result.is_ok
        assert all(r["type"] == "getting_started" for r in result.value)

    async def test_lowest_dimension_is_first_recommendation(self, intelligence):
        data = _alignment(
            {"knowledge": 0.2, "activity": 0.9, "goal": 0.8, "principle": 0.9, "momentum": 0.9}
        )

        result = await intelligence.get_recommendations(_USER, data)

        assert result.is_ok
        first = result.value[0]
        assert first["type"] == "dimension_knowledge"
        assert first["dimension"] == "knowledge"
        assert first["priority"] == "high"  # score < 0.3
        assert first["score"] == pytest.approx(0.2)
        assert first["actions"]  # every dimension rec ships concrete actions

    async def test_all_weak_dimensions_are_covered_without_duplicating_lowest(self, intelligence):
        data = _alignment(
            {"knowledge": 0.1, "activity": 0.4, "goal": 0.45, "principle": 0.9, "momentum": 0.9}
        )

        result = await intelligence.get_recommendations(_USER, data)

        assert result.is_ok
        dimension_recs = [r for r in result.value if r["type"].startswith("dimension_")]
        covered = [r["dimension"] for r in dimension_recs]
        assert covered[0] == "knowledge"
        assert set(covered) == {"knowledge", "activity", "goal"}
        assert len(covered) == len(set(covered)), "lowest dimension must not repeat"

    async def test_theoretical_surplus_adds_knowledge_gap_recommendation(self, intelligence):
        data = _alignment(
            {"knowledge": 0.8, "activity": 0.9, "goal": 0.8, "principle": 0.9, "momentum": 0.9},
            knowledge_stats={"total": 10, "embodied": 2, "theoretical": 6},
        )

        result = await intelligence.get_recommendations(_USER, data)

        assert result.is_ok
        assert any(r["type"] == "knowledge_gap" for r in result.value)

    async def test_low_momentum_adds_high_priority_momentum_recommendation(self, intelligence):
        data = _alignment(
            {"knowledge": 0.8, "activity": 0.9, "goal": 0.8, "principle": 0.9, "momentum": 0.2}
        )

        result = await intelligence.get_recommendations(_USER, data)

        assert result.is_ok
        momentum_recs = [r for r in result.value if r["type"] == "momentum"]
        assert momentum_recs and momentum_recs[0]["priority"] == "high"

    async def test_priority_bands_follow_score(self, intelligence):
        rec_high = intelligence._dimension_recommendation("activity", 0.1)
        rec_medium = intelligence._dimension_recommendation("activity", 0.5)
        rec_low = intelligence._dimension_recommendation("activity", 0.65)

        assert rec_high["priority"] == "high"
        assert rec_medium["priority"] == "medium"
        assert rec_low["priority"] == "low"

    async def test_unknown_dimension_falls_back_to_activity_config(self, intelligence):
        rec = intelligence._dimension_recommendation("unheard_of", 0.4)

        assert rec["type"] == "dimension_unheard_of"
        assert rec["title"] == "Align daily activities"


class TestGetDailyFocus:
    async def test_no_alignment_data_focuses_on_vision(self, intelligence):
        result = await intelligence.get_daily_focus(_USER, None)

        assert result.is_ok
        assert result.value["focus"] == "Express your vision"
        assert result.value["dimension"] is None

    async def test_actionable_order_prefers_activity_over_later_dimensions(self, intelligence):
        data = _alignment(
            {"knowledge": 0.1, "activity": 0.2, "goal": 0.1, "principle": 0.1, "momentum": 0.1}
        )

        result = await intelligence.get_daily_focus(_USER, data)

        assert result.is_ok
        focus = result.value
        # activity is first in the actionable order even though others are lower
        assert focus["dimension"] == "activity"
        assert focus["current_score"] == pytest.approx(0.2)

    async def test_healthy_earlier_dimensions_are_skipped(self, intelligence):
        data = _alignment(
            {"knowledge": 0.6, "activity": 0.9, "goal": 0.9, "principle": 0.9, "momentum": 0.8}
        )

        result = await intelligence.get_daily_focus(_USER, data)

        assert result.is_ok
        assert result.value["dimension"] == "knowledge"

    async def test_all_dimensions_healthy_yields_maintenance_focus(self, intelligence):
        data = _alignment(
            {"knowledge": 0.8, "activity": 0.9, "goal": 0.75, "principle": 0.9, "momentum": 0.7}
        )

        result = await intelligence.get_daily_focus(_USER, data)

        assert result.is_ok
        focus = result.value
        assert focus["dimension"] is None
        assert "Maintain" in focus["focus"]
