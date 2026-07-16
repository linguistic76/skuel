"""Tests for the shared principle gap insight/recommendation generators.

These pure functions back BOTH alignment paths: the dual-track template
callbacks (ADR-030, _AlignmentIntelligenceMixin) and the single-track
PrinciplesAlignmentService.assess_with_user_input.
"""

from __future__ import annotations

from core.models.enums.entity_enums import EntityType
from core.models.principle.principle import Principle
from core.services.intelligence import principle_gap_insights, principle_gap_recommendations


def _principle(**kwargs) -> Principle:
    return Principle(
        uid="pr_test_001",
        title="Integrity",
        entity_type=EntityType.PRINCIPLE,
        user_uid="user_test",
        **kwargs,
    )


class TestPrincipleGapInsights:
    def test_aligned_names_the_principle(self):
        insights = principle_gap_insights("aligned", 0.0, "Integrity")
        assert len(insights) == 1
        assert "Integrity" in insights[0]
        assert "healthy self-reflection" in insights[0]

    def test_user_higher_small_gap(self):
        insights = principle_gap_insights("user_higher", 0.2, "Integrity")
        assert len(insights) == 1
        assert "20%" in insights[0]

    def test_user_higher_large_gap_adds_blind_spot_insight(self):
        insights = principle_gap_insights("user_higher", 0.5, "Integrity")
        assert len(insights) == 2
        assert "blind spot" in insights[1]

    def test_system_higher_large_gap(self):
        insights = principle_gap_insights("system_higher", 0.4, "Integrity")
        assert len(insights) == 2
        assert "stronger alignment than you perceive" in insights[0]


class TestPrincipleGapRecommendations:
    def test_aligned_with_expressions(self):
        recs = principle_gap_recommendations("aligned", 0.0, _principle(expressions=["daily"]), [])
        assert len(recs) == 2
        assert "documenting new expressions" in recs[1]

    def test_aligned_without_expressions(self):
        recs = principle_gap_recommendations("aligned", 0.0, _principle(), [])
        assert len(recs) == 1

    def test_aligned_non_principle_entity_is_safe(self):
        """Dual-track template passes entity as Any — non-Principle must not raise."""
        recs = principle_gap_recommendations("aligned", 0.0, object(), [])
        assert len(recs) == 1

    def test_user_higher_without_evidence(self):
        recs = principle_gap_recommendations("user_higher", 0.4, _principle(), [])
        assert any("Create at least one goal or habit" in r for r in recs)

    def test_system_higher_with_evidence_capped_at_four(self):
        recs = principle_gap_recommendations(
            "system_higher", 0.4, _principle(), ["e1", "e2", "e3", "e4", "e5"]
        )
        assert len(recs) <= 4
        assert any("5 activities" in r for r in recs)
