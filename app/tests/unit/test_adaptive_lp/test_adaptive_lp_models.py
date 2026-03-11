"""
Test Suite for Adaptive LP Models
==================================

Tests the data models used by adaptive learning path services:
- AdaptiveLp (frozen dataclass)
- AdaptiveRecommendation (frozen dataclass)
- CrossDomainOpportunity (frozen dataclass)
- PersonalizedSuggestion (frozen dataclass)
- KnowledgeState (frozen dataclass)
- Enums (LpType, RecommendationType, LearningStyle)
"""

from __future__ import annotations

import pytest

from core.models.enums import Domain
from core.services.adaptive_lp.adaptive_lp_models import (
    AdaptiveLp,
    AdaptiveRecommendation,
    CrossDomainOpportunity,
    LearningStyle,
    LpType,
    PersonalizedSuggestion,
    RecommendationType,
)
from core.services.adaptive_lp_types import KnowledgeState

# ============================================================================
# TESTS: AdaptiveLp Model
# ============================================================================


class TestAdaptiveLpModel:
    """Test AdaptiveLp frozen dataclass."""

    def test_adaptive_lp_model_creation(self):
        """AdaptiveLp can be created with required fields."""
        lp = AdaptiveLp(
            path_id="lp_001",
            title="Python Learning Path",
            description="Learn Python from basics to advanced",
            path_type=LpType.GOAL_DRIVEN,
            target_goals=["goal_001"],
            learning_outcomes=["Understand Python basics"],
            estimated_duration_hours=10,
            difficulty_level=5.0,
            knowledge_steps=["ku.basics", "ku.intermediate"],
            alternative_paths=[],
            prerequisites=[],
            unlocks=[],
            adaptation_factors={},
            learning_style_match=0.8,
            confidence_score=0.9,
        )

        assert lp.path_id == "lp_001"
        assert lp.path_type == LpType.GOAL_DRIVEN
        assert len(lp.knowledge_steps) == 2

    def test_adaptive_lp_model_is_mutable(self):
        """AdaptiveLp is mutable (regular dataclass for progress tracking)."""
        lp = AdaptiveLp(
            path_id="lp_001",
            title="Test Path",
            description="Test description",
            path_type=LpType.GOAL_DRIVEN,
            target_goals=[],
            learning_outcomes=[],
            estimated_duration_hours=5,
            difficulty_level=3.0,
            knowledge_steps=[],
            alternative_paths=[],
            prerequisites=[],
            unlocks=[],
            adaptation_factors={},
            learning_style_match=0.5,
            confidence_score=0.5,
        )

        # AdaptiveLp is intentionally mutable for progress tracking
        lp.completion_percentage = 0.5
        assert lp.completion_percentage == 0.5

    def test_adaptive_lp_model_default_values(self):
        """AdaptiveLp has sensible default values for optional fields."""
        lp = AdaptiveLp(
            path_id="lp_001",
            title="Test Path",
            description="Test description",
            path_type=LpType.GOAL_DRIVEN,
            target_goals=[],
            learning_outcomes=[],
            estimated_duration_hours=0,
            difficulty_level=0.0,
            knowledge_steps=[],
            alternative_paths=[],
            prerequisites=[],
            unlocks=[],
            adaptation_factors={},
            learning_style_match=0.0,
            confidence_score=0.0,
        )

        # Check default values for optional fields
        assert lp.completion_percentage == 0.0
        assert lp.current_step_index == 0
        assert lp.adaptation_count == 0


# ============================================================================
# TESTS: AdaptiveRecommendation Model
# ============================================================================


class TestAdaptiveRecommendationModel:
    """Test AdaptiveRecommendation frozen dataclass."""

    def test_adaptive_recommendation_creation(self):
        """AdaptiveRecommendation can be created with required fields."""
        rec = AdaptiveRecommendation(
            recommendation_id="rec_001",
            recommendation_type=RecommendationType.NEXT_STEP,
            title="Learn Python Basics",
            description="Start your Python journey",
            knowledge_uid="ku.python-basics",
            related_goals=["goal_001"],
            application_suggestions=["Build a CLI tool"],
            relevance_score=0.9,
            impact_score=0.8,
            confidence_score=0.85,
            urgency_score=0.7,
            gap_address_score=0.75,
            goal_alignment_score=0.9,
            style_match_score=0.8,
            difficulty_appropriateness=0.7,
            reasoning="This fills a knowledge gap",
            prerequisites_met=True,
            estimated_time_minutes=60,
        )

        assert rec.recommendation_type == RecommendationType.NEXT_STEP
        assert rec.knowledge_uid == "ku.python-basics"
        assert rec.relevance_score == 0.9

    def test_adaptive_recommendation_scoring_fields(self):
        """AdaptiveRecommendation has all scoring fields."""
        rec = AdaptiveRecommendation(
            recommendation_id="rec_002",
            recommendation_type=RecommendationType.PREREQUISITE,
            title="Fill Knowledge Gap",
            description="Address missing prerequisites",
            knowledge_uid="ku.test",
            related_goals=[],
            application_suggestions=[],
            relevance_score=0.8,
            impact_score=0.7,
            confidence_score=0.75,
            urgency_score=0.6,
            gap_address_score=0.9,
            goal_alignment_score=0.7,
            style_match_score=0.65,
            difficulty_appropriateness=0.85,
            reasoning="Addresses a knowledge gap",
            prerequisites_met=False,
            estimated_time_minutes=45,
        )

        assert rec.relevance_score == 0.8
        assert rec.impact_score == 0.7
        assert rec.urgency_score == 0.6
        assert rec.gap_address_score == 0.9
        assert rec.difficulty_appropriateness == 0.85


# ============================================================================
# TESTS: CrossDomainOpportunity Model
# ============================================================================


class TestCrossDomainOpportunityModel:
    """Test CrossDomainOpportunity frozen dataclass."""

    def test_cross_domain_opportunity_creation(self):
        """CrossDomainOpportunity can be created with domain pair."""
        opp = CrossDomainOpportunity(
            opportunity_id="opp_001",
            title="Tech to Data Science",
            description="Apply programming skills to data science",
            source_domain=Domain.TECH,
            target_domain=Domain.TECH,  # Both programming and data are TECH
            bridging_knowledge=["ku.python-basics", "ku.data-ml"],
            application_type="data_science",
            practical_projects=["Build a data pipeline"],
            skill_transfer_potential=0.85,
            innovation_potential=0.8,
            prerequisite_knowledge=["ku.python-basics"],
            source_knowledge_uids=["ku.python-basics"],
            target_knowledge_uids=["ku.data-ml"],
            estimated_difficulty=6.0,
            estimated_value=0.9,
            supporting_examples=["Data engineering roles"],
            success_patterns=["Python to ML transition"],
            confidence_score=0.85,
        )

        assert opp.source_domain == Domain.TECH
        assert opp.target_domain == Domain.TECH
        assert len(opp.bridging_knowledge) == 2


# ============================================================================
# TESTS: PersonalizedSuggestion Model
# ============================================================================


class TestPersonalizedSuggestionModel:
    """Test PersonalizedSuggestion frozen dataclass."""

    def test_personalized_suggestion_creation(self):
        """PersonalizedSuggestion can be created."""
        suggestion = PersonalizedSuggestion(
            suggestion_id="sug_001",
            title="Apply Python Skills",
            description="Practice Python by building a CLI tool",
            knowledge_to_apply=["ku.python-basics"],
            application_context="Build a CLI tool",
            expected_outcomes=["Better command line skills"],
            personalization_factors={"skill_level": "intermediate"},
            user_readiness_score=0.9,
            timing_appropriateness=0.85,
            concrete_steps=["Set up project", "Write main function"],
            resources_needed=["Python 3.9+"],
            time_investment=120,
            success_indicators=["Working CLI app"],
        )

        assert suggestion.suggestion_id == "sug_001"
        assert suggestion.user_readiness_score == 0.9


# ============================================================================
# TESTS: KnowledgeState Model
# ============================================================================


class TestKnowledgeStateModel:
    """Test KnowledgeState frozen dataclass."""

    def test_knowledge_state_creation(self):
        """KnowledgeState can be created with knowledge sets."""
        state = KnowledgeState(
            mastered_knowledge={"ku.python-basics"},
            in_progress_knowledge={"ku.python-advanced"},
            applied_knowledge=set(),
            knowledge_strengths={"ku.python-basics": 5},
            knowledge_gaps=["ku.data-structures"],
            mastery_levels={"ku.python-basics": 0.9},
            learning_velocity=1.5,
        )

        assert "ku.python-basics" in state.mastered_knowledge
        assert state.learning_velocity == 1.5

    def test_knowledge_state_frozen(self):
        """KnowledgeState is immutable."""
        state = KnowledgeState(
            mastered_knowledge=set(),
            in_progress_knowledge=set(),
            applied_knowledge=set(),
            knowledge_strengths={},
            knowledge_gaps=[],
            mastery_levels={},
            learning_velocity=0.0,
        )

        with pytest.raises((AttributeError, TypeError)):
            state.learning_velocity = 5.0  # type: ignore[misc]


# ============================================================================
# TESTS: Enums
# ============================================================================


class TestEnums:
    """Test enum definitions."""

    def test_lp_type_enum_values(self):
        """LpType enum has expected values."""
        assert LpType.GOAL_DRIVEN.value == "goal_driven"
        assert LpType.GAP_FILLING.value == "gap_filling"
        assert LpType.CROSS_DOMAIN.value == "cross_domain"

    def test_recommendation_type_enum_values(self):
        """RecommendationType enum has expected values."""
        assert RecommendationType.NEXT_STEP.value == "next_step"
        assert RecommendationType.PREREQUISITE.value == "prerequisite"
        assert RecommendationType.APPLICATION.value == "application"

    def test_learning_style_enum_values(self):
        """LearningStyle enum has expected values."""
        assert LearningStyle.SEQUENTIAL.value == "sequential"
        assert LearningStyle.HOLISTIC.value == "holistic"
        assert LearningStyle.PRACTICAL.value == "practical"
        assert LearningStyle.THEORETICAL.value == "theoretical"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
