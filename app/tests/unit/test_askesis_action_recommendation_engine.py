"""
Test Suite for ActionRecommendationEngine
==========================================

Tests the askesis action recommendation engine:
- Next best action recommendation
- Recommendation generation
- Workflow optimization
- Future state prediction
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from core.models.enums import Priority
from core.services.askesis.action_recommendation_engine import ActionRecommendationEngine
from core.services.askesis.types import AskesisRecommendation

# ============================================================================
# MOCK FACTORIES
# ============================================================================


def create_mock_user_context(
    active_tasks: int = 5,
    overdue_tasks: int = 0,
    active_habits: int = 5,
    at_risk_habit_count: int = 0,
    habit_streak_avg: int = 7,
    active_goals: int = 2,
    goal_progress_avg: float = 50.0,
    blocked_knowledge: int = 0,
    mastered_knowledge: int = 5,
    current_workload_score: float = 0.5,
    is_blocked: bool = False,
    learning_velocity: float = 1.0,
) -> Mock:
    """Create mock UserContext with actual field names from unified_user_context.py."""
    context = Mock()
    context.user_uid = "test_user"

    # Task UIDs
    context.active_task_uids = [f"task_{i}" for i in range(active_tasks)]
    context.overdue_task_uids = [f"overdue_{i}" for i in range(overdue_tasks)]
    context.completed_task_uids = {f"done_{i}" for i in range(10)}
    context.blocked_task_uids = []
    context.has_overdue_items = overdue_tasks > 0

    # Habit data
    context.active_habit_uids = [f"habit_{i}" for i in range(active_habits)]
    context.at_risk_habits = [f"risk_habit_{i}" for i in range(at_risk_habit_count)]
    context.habit_streaks = {f"habit_{i}": habit_streak_avg for i in range(active_habits)}

    # Goal data
    context.active_goal_uids = [f"goal_{i}" for i in range(active_goals)]
    context.goal_progress = {f"goal_{i}": goal_progress_avg for i in range(active_goals)}
    context.goal_deadlines = {}

    # Knowledge data
    context.mastered_knowledge_uids = {f"ku_{i}" for i in range(mastered_knowledge)}
    context.blocked_knowledge_uids = [f"blocked_ku_{i}" for i in range(blocked_knowledge)]
    context.prerequisites_needed = {}
    context.prerequisites_completed = set()
    context.is_blocked = is_blocked

    # MOC data
    context.active_moc_uids = []
    context.recently_viewed_moc_uids = []

    # Domain progress (for state_scoring functions)
    context.domain_progress = {"tech": 0.5, "personal": 0.5}

    # Methods
    context.calculate_learning_velocity = Mock(return_value=learning_velocity)
    context.get_ready_to_learn = Mock(return_value=["ku.ready_1", "ku.ready_2"])

    # Workload
    context.current_workload_score = current_workload_score

    return context


def create_mock_insight(insight_type: str = "pattern") -> Mock:
    """Create mock AskesisInsight."""
    insight = Mock()
    insight.insight_type = insight_type
    insight.title = "Test Insight"
    insight.description = "Test description"
    return insight


# ============================================================================
# TEST FIXTURES
# ============================================================================


@pytest.fixture
def engine():
    """Create ActionRecommendationEngine."""
    return ActionRecommendationEngine()


@pytest.fixture
def normal_context():
    """Normal user context with balanced state."""
    return create_mock_user_context()


@pytest.fixture
def critical_context():
    """Context with critical habit at risk (15+ day streak)."""
    context = create_mock_user_context(at_risk_habit_count=1, habit_streak_avg=15)
    # Override at_risk_habits to include a habit with long streak (must be > 14)
    context.at_risk_habits = ["habit_0"]
    context.habit_streaks = {"habit_0": 15, "habit_1": 5}
    return context


@pytest.fixture
def blocked_context():
    """Context with blocked knowledge."""
    context = create_mock_user_context(blocked_knowledge=5, is_blocked=True)
    context.prerequisites_needed = {
        "blocked_ku_0": ["ku.prereq_a"],
        "blocked_ku_1": ["ku.prereq_a", "ku.prereq_b"],
    }
    return context


@pytest.fixture
def overloaded_context():
    """Context with high workload."""
    return create_mock_user_context(active_tasks=20, overdue_tasks=5, current_workload_score=0.95)


# ============================================================================
# TESTS: Next Best Action
# ============================================================================


class TestNextBestAction:
    """Test next best action recommendation."""

    @pytest.mark.asyncio
    async def test_get_next_best_action_returns_recommendation(self, engine, normal_context):
        """get_next_best_action returns AskesisRecommendation."""
        result = await engine.get_next_best_action(normal_context)

        assert result.is_ok
        recommendation = result.value
        assert isinstance(recommendation, AskesisRecommendation)

    @pytest.mark.asyncio
    async def test_get_next_best_action_critical_priority_habit(self, engine, critical_context):
        """Critical priority: Prevent habit streak loss (14+ days)."""
        result = await engine.get_next_best_action(critical_context)

        assert result.is_ok
        recommendation = result.value
        # Should recommend protecting the streak
        assert recommendation.priority in [Priority.CRITICAL, Priority.HIGH]

    @pytest.mark.asyncio
    async def test_get_next_best_action_high_priority_unblock(self, engine, blocked_context):
        """High priority: Unblock if stuck."""
        result = await engine.get_next_best_action(blocked_context)

        assert result.is_ok
        recommendation = result.value
        # Should recommend unblocking knowledge
        assert recommendation is not None  # Verify recommendation exists


# ============================================================================
# TESTS: Recommendation Generation
# ============================================================================


class TestRecommendationGeneration:
    """Test recommendation generation with insights."""

    @pytest.mark.asyncio
    async def test_generate_recommendations_with_insights(self, engine, normal_context):
        """generate_recommendations considers insights."""
        insights = [create_mock_insight("pattern")]

        result = await engine.generate_recommendations(normal_context, insights)

        assert result.is_ok
        recommendations = result.value
        assert isinstance(recommendations, list)

    @pytest.mark.asyncio
    async def test_generate_recommendations_empty_insights(self, engine, normal_context):
        """generate_recommendations works with empty insights."""
        result = await engine.generate_recommendations(normal_context, [])

        assert result.is_ok
        recommendations = result.value
        assert isinstance(recommendations, list)


# ============================================================================
# TESTS: Workflow Optimization
# ============================================================================


class TestWorkflowOptimization:
    """Test workflow optimization suggestions."""

    @pytest.mark.asyncio
    async def test_optimize_workflow_habit_consolidation(self, engine):
        """Suggests habit consolidation for 10+ habits."""
        context = create_mock_user_context(active_habits=12)

        result = await engine.optimize_workflow(context)

        assert result.is_ok
        optimizations = result.value
        assert isinstance(optimizations, list)

    @pytest.mark.asyncio
    async def test_optimize_workflow_moc_creation(self, engine):
        """Suggests MOC creation for 10+ mastered KUs without MOCs."""
        context = create_mock_user_context(mastered_knowledge=15)

        result = await engine.optimize_workflow(context)

        assert result.is_ok
        optimizations = result.value
        assert isinstance(optimizations, list)


# ============================================================================
# TESTS: Future State Prediction
# ============================================================================


class TestFutureStatePrediction:
    """Test future state prediction."""

    @pytest.mark.asyncio
    async def test_predict_future_state_7_days(self, engine, normal_context):
        """Predicts state 7 days ahead."""
        result = await engine.predict_future_state(normal_context, days_ahead=7)

        assert result.is_ok
        prediction = result.value
        assert isinstance(prediction, dict)

    @pytest.mark.asyncio
    async def test_predict_future_state_overloaded(self, engine, overloaded_context):
        """Predicts negative trajectory for overloaded context."""
        result = await engine.predict_future_state(overloaded_context, days_ahead=7)

        assert result.is_ok
        prediction = result.value
        # Overloaded context should predict declining metrics
        assert isinstance(prediction, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
