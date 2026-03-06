"""
Test Suite for AdaptiveLpFacade
================================

Tests the unified facade that orchestrates adaptive learning path services:
- Core service delegation
- Recommendations service delegation
- Cross-domain service delegation
- Suggestions service delegation
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from core.services.adaptive_lp import AdaptiveLpFacade
from core.services.adaptive_lp.adaptive_lp_models import LearningStyle
from core.utils.result_simplified import Result

# ============================================================================
# MOCK FACTORIES
# ============================================================================


def create_mock_ku_service() -> Mock:
    """Create mock ArticleService."""
    ku_service = Mock()
    ku_service.get = AsyncMock(return_value=Result.ok({"uid": "ku.test", "title": "Test KU"}))
    ku_service.search = AsyncMock(return_value=Result.ok([]))
    return ku_service


def create_mock_goals_service() -> Mock:
    """Create mock GoalsService."""
    goals_service = Mock()
    goals_service.get = AsyncMock(return_value=Result.ok({"uid": "goal_001", "title": "Test Goal"}))
    goals_service.list_by_user = AsyncMock(return_value=Result.ok([]))
    return goals_service


def create_mock_tasks_service() -> Mock:
    """Create mock TasksService."""
    tasks_service = Mock()
    tasks_service.list_by_user = AsyncMock(return_value=Result.ok([]))
    return tasks_service


def create_mock_learning_service() -> Mock:
    """Create mock LearningService."""
    learning_service = Mock()
    learning_service.get = AsyncMock(return_value=Result.ok(None))
    return learning_service


def create_mock_user_service() -> Mock:
    """Create mock UserService (needed after 2026-02-08 refactor)."""
    from core.services.user import UserContext

    user_service = Mock()
    # Mock UserContext returned by get_user_context()
    mock_context = UserContext(
        user_uid="user_001",
        mastered_knowledge_uids={"ku_001", "ku_002"},
        in_progress_knowledge_uids={"ku_003"},
        knowledge_mastery={"ku_001": 0.9, "ku_002": 0.8, "ku_003": 0.3},
        prerequisites_completed={"ku_001"},
        prerequisites_needed={"ku_003": ["ku_001"]},
    )
    user_service.get_user_context = AsyncMock(return_value=Result.ok(mock_context))
    return user_service


# ============================================================================
# TEST FIXTURES
# ============================================================================


@pytest.fixture
def mock_ku_service():
    return create_mock_ku_service()


@pytest.fixture
def mock_goals_service():
    return create_mock_goals_service()


@pytest.fixture
def mock_tasks_service():
    return create_mock_tasks_service()


@pytest.fixture
def mock_learning_service():
    return create_mock_learning_service()


@pytest.fixture
def mock_user_service():
    return create_mock_user_service()


@pytest.fixture
def facade(
    mock_ku_service,
    mock_goals_service,
    mock_tasks_service,
    mock_learning_service,
    mock_user_service,
):
    """Create AdaptiveLpFacade with mock services."""
    return AdaptiveLpFacade(
        ku_service=mock_ku_service,
        learning_service=mock_learning_service,
        goals_service=mock_goals_service,
        tasks_service=mock_tasks_service,
        user_service=mock_user_service,
    )


@pytest.fixture
def facade_no_services():
    """Create AdaptiveLpFacade without services (graceful degradation)."""
    return AdaptiveLpFacade()


# ============================================================================
# TESTS: Initialization
# ============================================================================


class TestFacadeInitialization:
    """Test AdaptiveLpFacade initialization."""

    def test_facade_initialization_creates_sub_services(self, facade):
        """Facade creates all sub-services on initialization."""
        assert facade.core_service is not None
        assert facade.recommendations_service is not None
        assert facade.cross_domain_service is not None
        assert facade.suggestions_service is not None

    def test_facade_initialization_without_services(self, facade_no_services):
        """Facade initializes without services (graceful degradation)."""
        # Should not raise
        assert facade_no_services.core_service is not None

    def test_getter_methods_return_correct_services(self, facade):
        """Getter methods return the correct sub-service instances."""
        assert facade.get_core_service() == facade.core_service
        assert facade.get_recommendations_service() == facade.recommendations_service
        assert facade.get_cross_domain_service() == facade.cross_domain_service
        assert facade.get_suggestions_service() == facade.suggestions_service


# ============================================================================
# TESTS: Delegation
# ============================================================================


class TestFacadeDelegation:
    """Test facade delegates to sub-services."""

    @pytest.mark.asyncio
    async def test_facade_delegates_to_core_service(self, facade):
        """generate_goal_driven_learning_path delegates to core_service."""
        # Mock the core_service method
        facade.core_service.generate_goal_driven_learning_path = AsyncMock(
            return_value=Result.ok(Mock())
        )

        result = await facade.generate_goal_driven_learning_path(
            user_uid="user_001",
            goal_uid="goal_001",
        )

        assert result.is_ok  # Verify behavior
        facade.core_service.generate_goal_driven_learning_path.assert_called_once()

    @pytest.mark.asyncio
    async def test_facade_delegates_to_recommendations_service(self, facade):
        """generate_adaptive_recommendations delegates to recommendations_service."""
        from core.services.adaptive_lp_types import KnowledgeState

        # Mock the internal knowledge state and learning style derivation
        knowledge_state = KnowledgeState(
            mastered_knowledge=set(),
            in_progress_knowledge=set(),
            applied_knowledge=set(),
            knowledge_strengths={},
            knowledge_gaps=[],
            mastery_levels={},
            learning_velocity=1.0,
        )
        facade.core_service.analyze_user_knowledge_state = AsyncMock(
            return_value=Result.ok(knowledge_state)
        )
        facade.core_service.detect_learning_style = AsyncMock(
            return_value=Result.ok(LearningStyle.SEQUENTIAL)
        )
        facade.recommendations_service.generate_adaptive_recommendations = AsyncMock(
            return_value=Result.ok([])
        )

        # Facade takes context, not knowledge_state (derives it internally)
        result = await facade.generate_adaptive_recommendations(
            user_uid="user_001",
            context={"source": "test"},
        )

        assert result.is_ok  # Verify behavior
        # After refactor, facade calls user_service.get_user_context() first
        facade.user_service.get_user_context.assert_called_once_with("user_001")
        facade.core_service.analyze_user_knowledge_state.assert_called_once()
        facade.recommendations_service.generate_adaptive_recommendations.assert_called_once()

    @pytest.mark.asyncio
    async def test_facade_delegates_to_cross_domain_service(self, facade):
        """discover_cross_domain_opportunities delegates to cross_domain_service."""
        from core.services.adaptive_lp_types import KnowledgeState

        # Mock the internal knowledge state derivation
        knowledge_state = KnowledgeState(
            mastered_knowledge={"ku.tech.python", "ku.data.ml"},
            in_progress_knowledge=set(),
            applied_knowledge=set(),
            knowledge_strengths={},
            knowledge_gaps=[],
            mastery_levels={"ku.tech.python": 0.9, "ku.data.ml": 0.8},
            learning_velocity=1.0,
        )
        facade.core_service.analyze_user_knowledge_state = AsyncMock(
            return_value=Result.ok(knowledge_state)
        )
        facade.cross_domain_service.discover_cross_domain_opportunities = AsyncMock(
            return_value=Result.ok([])
        )

        # Facade takes (user_uid, min_confidence), derives knowledge_state internally
        result = await facade.discover_cross_domain_opportunities(
            user_uid="user_001",
            min_confidence=0.5,
        )

        assert result.is_ok  # Verify behavior
        # After refactor, facade calls user_service.get_user_context() first
        facade.user_service.get_user_context.assert_called_once_with("user_001")
        facade.core_service.analyze_user_knowledge_state.assert_called_once()
        facade.cross_domain_service.discover_cross_domain_opportunities.assert_called_once()

    @pytest.mark.asyncio
    async def test_facade_delegates_to_suggestions_service(self, facade):
        """generate_personalized_application_suggestions delegates to suggestions_service."""
        from core.services.adaptive_lp_types import KnowledgeState

        # Mock the internal knowledge state and learning style derivation
        knowledge_state = KnowledgeState(
            mastered_knowledge={"ku.python-basics"},
            in_progress_knowledge=set(),
            applied_knowledge=set(),
            knowledge_strengths={},
            knowledge_gaps=[],
            mastery_levels={"ku.python-basics": 0.8},
            learning_velocity=1.0,
        )
        facade.core_service.analyze_user_knowledge_state = AsyncMock(
            return_value=Result.ok(knowledge_state)
        )
        facade.core_service.detect_learning_style = AsyncMock(
            return_value=Result.ok(LearningStyle.PRACTICAL)
        )
        facade.suggestions_service.generate_personalized_application_suggestions = AsyncMock(
            return_value=Result.ok([])
        )

        # Facade takes context, not knowledge_state (derives it internally)
        result = await facade.generate_personalized_application_suggestions(
            user_uid="user_001",
            context={"source": "test"},
        )

        assert result.is_ok  # Verify behavior
        # After refactor, facade calls user_service.get_user_context() first
        facade.user_service.get_user_context.assert_called_once_with("user_001")
        facade.core_service.analyze_user_knowledge_state.assert_called_once()
        facade.suggestions_service.generate_personalized_application_suggestions.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
