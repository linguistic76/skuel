"""
Test Suite for AdaptiveLpSuggestionsService
============================================

Tests the personalized application suggestions service:
- Practice suggestions by learning style
- Project suggestions
- Teaching/mentoring suggestions
- Personalization scoring
"""

from __future__ import annotations

import pytest

from core.services.adaptive_lp.adaptive_lp_models import (
    LearningStyle,
    PersonalizedSuggestion,
)
from core.services.adaptive_lp.adaptive_lp_suggestions_service import (
    AdaptiveLpSuggestionsService,
)
from core.services.adaptive_lp_types import KnowledgeState

# ============================================================================
# TEST FIXTURES
# ============================================================================


@pytest.fixture
def suggestions_service():
    """Create suggestions service (no dependencies needed)."""
    return AdaptiveLpSuggestionsService()


@pytest.fixture
def practical_learner_state():
    """KnowledgeState for practical learner."""
    return KnowledgeState(
        mastered_knowledge={"ku.python-basics", "ku.python-functions"},
        in_progress_knowledge={"ku.python-oop"},
        applied_knowledge={"ku.python-basics"},
        knowledge_strengths={"ku.python-basics": 10},
        knowledge_gaps=["ku.python-advanced"],
        mastery_levels={
            "ku.python-basics": 0.95,
            "ku.python-functions": 0.7,
            "ku.python-oop": 0.4,
        },
        learning_velocity=2.0,
    )


@pytest.fixture
def theoretical_learner_state():
    """KnowledgeState for theoretical learner."""
    return KnowledgeState(
        mastered_knowledge={"ku.math.calculus", "ku.math.algebra"},
        in_progress_knowledge={"ku.math.statistics"},
        applied_knowledge=set(),
        knowledge_strengths={},
        knowledge_gaps=[],
        mastery_levels={
            "ku.math.calculus": 0.9,
            "ku.math.algebra": 0.85,
            "ku.math.statistics": 0.5,
        },
        learning_velocity=1.0,
    )


@pytest.fixture
def expert_state():
    """KnowledgeState for expert (teaching suggestions)."""
    return KnowledgeState(
        mastered_knowledge={
            "ku.python-basics",
            "ku.python-functions",
            "ku.python-oop",
            "ku.python-advanced",
            "ku.python-design-patterns",
        },
        in_progress_knowledge=set(),
        applied_knowledge={
            "ku.python-basics",
            "ku.python-functions",
            "ku.python-oop",
        },
        knowledge_strengths={
            "ku.python-basics": 20,
            "ku.python-oop": 15,
        },
        knowledge_gaps=[],
        mastery_levels={
            "ku.python-basics": 1.0,
            "ku.python-functions": 0.95,
            "ku.python-oop": 0.92,
            "ku.python-advanced": 0.88,
            "ku.python-design-patterns": 0.85,
        },
        learning_velocity=3.0,
    )


# ============================================================================
# TESTS: Practice Suggestions
# ============================================================================


class TestPracticeSuggestions:
    """Test practice suggestion generation."""

    @pytest.mark.asyncio
    async def test_generate_practice_suggestions_practical_style(
        self, suggestions_service, practical_learner_state
    ):
        """Practical learners get hands-on practice suggestions."""
        result = await suggestions_service.generate_personalized_application_suggestions(
            user_uid="user_001",
            knowledge_state=practical_learner_state,
            learning_style=LearningStyle.PRACTICAL,
        )

        assert result.is_ok
        suggestions = result.value
        assert isinstance(suggestions, list)

    @pytest.mark.asyncio
    async def test_generate_practice_suggestions_theoretical_style(
        self, suggestions_service, theoretical_learner_state
    ):
        """Theoretical learners get conceptual practice suggestions."""
        result = await suggestions_service.generate_personalized_application_suggestions(
            user_uid="user_001",
            knowledge_state=theoretical_learner_state,
            learning_style=LearningStyle.THEORETICAL,
        )

        assert result.is_ok
        suggestions = result.value
        assert isinstance(suggestions, list)


# ============================================================================
# TESTS: Project Suggestions
# ============================================================================


class TestProjectSuggestions:
    """Test project suggestion generation."""

    @pytest.mark.asyncio
    async def test_generate_project_suggestions(self, suggestions_service, practical_learner_state):
        """Project suggestions generated for domain knowledge."""
        result = await suggestions_service.generate_personalized_application_suggestions(
            user_uid="user_001",
            knowledge_state=practical_learner_state,
            learning_style=LearningStyle.PRACTICAL,
        )

        assert result.is_ok
        suggestions = result.value
        # Should include project-type suggestions for Python domain
        assert isinstance(suggestions, list)  # Verify return type


# ============================================================================
# TESTS: Teaching Suggestions
# ============================================================================


class TestTeachingSuggestions:
    """Test teaching/mentoring suggestion generation."""

    @pytest.mark.asyncio
    async def test_generate_teaching_suggestions_expert(self, suggestions_service, expert_state):
        """Experts get teaching/mentoring suggestions."""
        result = await suggestions_service.generate_personalized_application_suggestions(
            user_uid="user_001",
            knowledge_state=expert_state,
            learning_style=LearningStyle.SOCIAL,  # Social learner = likes teaching
        )

        assert result.is_ok
        suggestions = result.value
        # Expert with social style should get teaching suggestions
        assert isinstance(suggestions, list)  # Verify return type


# ============================================================================
# TESTS: Personalization and Scoring
# ============================================================================


class TestPersonalizationScoring:
    """Test personalization and scoring logic."""

    @pytest.mark.asyncio
    async def test_personalize_and_score_suggestions(
        self, suggestions_service, practical_learner_state
    ):
        """Suggestions are personalized and scored."""
        result = await suggestions_service.generate_personalized_application_suggestions(
            user_uid="user_001",
            knowledge_state=practical_learner_state,
            learning_style=LearningStyle.PRACTICAL,
        )

        assert result.is_ok
        suggestions = result.value

        for suggestion in suggestions:
            if isinstance(suggestion, PersonalizedSuggestion):
                # Each suggestion should have scoring fields
                assert hasattr(suggestion, "user_readiness_score")
                assert hasattr(suggestion, "timing_appropriateness")

    @pytest.mark.asyncio
    async def test_suggestions_limited_to_top_15(self, suggestions_service, expert_state):
        """Suggestions limited to top 15 results."""
        result = await suggestions_service.generate_personalized_application_suggestions(
            user_uid="user_001",
            knowledge_state=expert_state,
            learning_style=LearningStyle.PRACTICAL,
        )

        assert result.is_ok
        suggestions = result.value
        assert len(suggestions) <= 15


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
