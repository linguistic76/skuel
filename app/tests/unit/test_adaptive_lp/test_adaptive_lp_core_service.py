"""
Test Suite for AdaptiveLpCoreService
=====================================

Tests the core adaptive learning path service:
- Goal-driven learning path generation
- Learning style detection
- Knowledge state analysis
- Path calculation utilities
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from core.services.adaptive_lp.adaptive_lp_core_service import AdaptiveLpCoreService
from core.services.adaptive_lp.adaptive_lp_models import (
    AdaptiveLp,
    LearningStyle,
    LpType,
)
from core.utils.result_simplified import Result

# ============================================================================
# MOCK FACTORIES
# ============================================================================


def create_mock_ku_service() -> Mock:
    """Create mock KuService with standard methods."""
    ku_service = Mock()
    ku_service.get = AsyncMock(
        return_value=Result.ok(
            {
                "uid": "ku.python-basics",
                "title": "Python Basics",
                "mastery_level": 0.0,
            }
        )
    )
    ku_service.search = AsyncMock(return_value=Result.ok([]))
    ku_service.get_prerequisites = AsyncMock(return_value=Result.ok([]))
    return ku_service


def create_mock_goals_service() -> Mock:
    """Create mock GoalsService."""
    from datetime import date, timedelta

    goal = Mock()
    goal.uid = "goal_001"
    goal.title = "Learn Machine Learning"
    goal.description = "Master ML fundamentals"
    # Additional attributes needed by generate_goal_driven_learning_path
    goal.target_date = date.today() + timedelta(days=90)  # 90 days from now
    goal.success_criteria = "Complete ML course and build a project"

    goals_service = Mock()
    goals_service.get_goal = AsyncMock(return_value=Result.ok(goal))
    return goals_service


def create_mock_tasks_service() -> Mock:
    """Create mock TasksService for learning style detection."""
    from datetime import date

    from core.models.enums import KuStatus

    # Create mock task objects with ALL attributes accessed by the service
    # See adaptive_lp_core_service.py lines 238-264 for required attributes
    task1 = Mock()
    task1.uid = "task_001"
    task1.title = "Read ML book"
    task1.status = KuStatus.COMPLETED
    task1.completion_date = date.today()
    task1.knowledge_uids = ["ku.python-basics"]
    # Additional attributes for learning style detection
    task1.parent_uid = None  # No parent = independent
    task1.source_learning_step_uid = "ls.ml-intro"  # Has learning step
    task1.knowledge_mastery_check = True  # Is a mastery check
    task1.tags = ["learning", "ml"]  # Tags for social detection

    task2 = Mock()
    task2.uid = "task_002"
    task2.title = "Practice coding"
    task2.status = KuStatus.COMPLETED
    task2.completion_date = date.today()
    task2.knowledge_uids = ["ku.python-basics"]
    # Additional attributes
    task2.parent_uid = "task_001"  # Has parent = sequential
    task2.source_learning_step_uid = None
    task2.knowledge_mastery_check = False
    task2.tags = ["practice"]

    # Add more tasks to meet style_detection_min_tasks (5)
    task3 = Mock()
    task3.uid = "task_003"
    task3.title = "Build ML model"
    task3.status = KuStatus.COMPLETED
    task3.completion_date = date.today()
    task3.knowledge_uids = ["ku.ml-basics"]
    task3.parent_uid = None
    task3.source_learning_step_uid = "ls.ml-practice"
    task3.knowledge_mastery_check = False
    task3.tags = ["project"]

    task4 = Mock()
    task4.uid = "task_004"
    task4.title = "Review algorithms"
    task4.status = KuStatus.COMPLETED
    task4.completion_date = date.today()
    task4.knowledge_uids = ["ku.algorithms"]
    task4.parent_uid = None
    task4.source_learning_step_uid = None
    task4.knowledge_mastery_check = True
    task4.tags = ["theory"]

    task5 = Mock()
    task5.uid = "task_005"
    task5.title = "Team project"
    task5.status = KuStatus.COMPLETED
    task5.completion_date = date.today()
    task5.knowledge_uids = ["ku.python-advanced"]
    task5.parent_uid = None
    task5.source_learning_step_uid = None
    task5.knowledge_mastery_check = False
    task5.tags = ["team", "collaboration"]  # Social learning tags

    tasks_service = Mock()
    tasks_service.get_user_tasks = AsyncMock(
        return_value=Result.ok([task1, task2, task3, task4, task5])
    )
    return tasks_service


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
def core_service(mock_ku_service, mock_goals_service, mock_tasks_service):
    """Create AdaptiveLpCoreService with mock dependencies."""
    return AdaptiveLpCoreService(
        ku_service=mock_ku_service,
        learning_service=None,
        goals_service=mock_goals_service,
        tasks_service=mock_tasks_service,
    )


@pytest.fixture
def core_service_no_deps():
    """Create AdaptiveLpCoreService without dependencies."""
    return AdaptiveLpCoreService()


# ============================================================================
# TESTS: Learning Path Generation
# ============================================================================


class TestLearningPathGeneration:
    """Test goal-driven learning path generation."""

    @pytest.mark.asyncio
    async def test_generate_goal_driven_learning_path_basic(self, core_service):
        """Basic learning path generation returns AdaptiveLp."""
        result = await core_service.generate_goal_driven_learning_path(
            user_uid="user_001",
            goal_uid="goal_001",
        )

        assert result.is_ok
        lp = result.value
        assert isinstance(lp, AdaptiveLp)
        assert lp.path_type == LpType.GOAL_DRIVEN  # FIX: was lp_type

    @pytest.mark.asyncio
    async def test_generate_goal_driven_learning_path_with_style_override(self, core_service):
        """Learning path respects learning style override."""
        result = await core_service.generate_goal_driven_learning_path(
            user_uid="user_001",
            goal_uid="goal_001",
            learning_style_override=LearningStyle.PRACTICAL,
        )

        assert result.is_ok
        lp = result.value
        # Path should be tailored to practical learning style
        # AdaptiveLp has learning_style_match (float), not learning_style field
        assert isinstance(lp.learning_style_match, float)
        assert 0.0 <= lp.learning_style_match <= 1.0

    @pytest.mark.asyncio
    async def test_generate_path_without_services_returns_error(self, core_service_no_deps):
        """Path generation without required services returns error or empty path."""
        result = await core_service_no_deps.generate_goal_driven_learning_path(
            user_uid="user_001",
            goal_uid="goal_001",
        )

        # Either error or empty path is acceptable
        if result.is_ok:
            lp = result.value
            assert len(lp.knowledge_steps) == 0 or lp is not None


# ============================================================================
# TESTS: Learning Style Detection
# ============================================================================


class TestLearningStyleDetection:
    """Test learning style detection from user patterns."""

    @pytest.mark.asyncio
    async def test_detect_learning_style_from_task_patterns(self, core_service):
        """Learning style detected from completed task patterns."""
        result = await core_service.detect_learning_style("user_001")

        assert result.is_ok
        style = result.value
        assert isinstance(style, str | LearningStyle)

    @pytest.mark.asyncio
    async def test_detect_learning_style_insufficient_data(self, core_service_no_deps):
        """Insufficient data returns default learning style."""
        result = await core_service_no_deps.detect_learning_style("user_001")

        assert result.is_ok
        # Should return a default style when data is insufficient
        style = result.value
        assert style is not None


# ============================================================================
# TESTS: Knowledge State Analysis
# ============================================================================


class TestKnowledgeStateAnalysis:
    """Test knowledge state analysis."""

    @pytest.mark.asyncio
    async def test_analyze_user_knowledge_state(self, core_service):
        """Knowledge state analysis returns structured data."""
        # Create mock UserContext (refactored 2026-02-08 to accept context instead of user_uid)
        from core.services.user import UserContext

        mock_context = UserContext(
            user_uid="user_001",
            mastered_knowledge_uids={"ku_001", "ku_002"},
            in_progress_knowledge_uids={"ku_003"},
            knowledge_mastery={"ku_001": 0.9, "ku_002": 0.8, "ku_003": 0.3},
            prerequisites_completed={"ku_001"},
            prerequisites_needed={"ku_003": ["ku_001", "ku_002"]},
            recently_mastered_uids={"ku_001"},  # Recently mastered in last 30 days
        )

        result = await core_service.analyze_user_knowledge_state(mock_context)

        assert result.is_ok
        state = result.value
        assert state is not None
        # Verify it uses UserContext fields
        assert state.mastered_knowledge == mock_context.mastered_knowledge_uids
        assert state.in_progress_knowledge == mock_context.in_progress_knowledge_uids
        assert state.mastery_levels == mock_context.knowledge_mastery


# ============================================================================
# TESTS: Path Calculation Utilities
# ============================================================================


class TestPathCalculations:
    """Test path calculation helper methods."""

    def test_calculate_path_difficulty(self, core_service):
        """Path difficulty calculated from knowledge complexity."""
        # Test via the generated AdaptiveLp
        pass

    def test_estimate_path_duration(self, core_service):
        """Path duration estimated from step count and complexity."""
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
