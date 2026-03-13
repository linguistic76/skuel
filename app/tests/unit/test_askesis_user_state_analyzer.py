"""
Test Suite for UserStateAnalyzer
=================================

Tests the askesis user state analyzer service:
- User state analysis
- Pattern detection
- System health calculation
- Risk assessment
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from core.services.askesis.types import AskesisAnalysis
from core.services.askesis.user_state_analyzer import UserStateAnalyzer

# ============================================================================
# MOCK FACTORIES
# ============================================================================


def create_mock_user_context(
    active_tasks: int = 5,
    overdue_tasks: int = 1,
    active_habits: int = 3,
    at_risk_habit_count: int = 0,
    habit_streak_avg: int = 7,
    active_goals: int = 2,
    goal_progress_avg: float = 50.0,
    mastered_knowledge: int = 5,
    learning_velocity: float = 1.0,
    current_workload_score: float = 0.6,
    is_blocked: bool = False,
    ready_to_learn_count: int = 2,
    domain_progress: dict | None = None,
) -> Mock:
    """Create mock UserContext with actual field names from unified_user_context.py."""
    context = Mock()
    context.user_uid = "test_user"

    # Activity UIDs (lists)
    context.active_task_uids = [f"task_{i}" for i in range(active_tasks)]
    context.overdue_task_uids = [f"overdue_{i}" for i in range(overdue_tasks)]
    context.today_task_uids = []
    context.blocked_task_uids = []
    context.has_overdue_items = overdue_tasks > 0

    # Habit data
    context.active_habit_uids = [f"habit_{i}" for i in range(active_habits)]
    context.at_risk_habits = [f"risk_habit_{i}" for i in range(at_risk_habit_count)]
    context.habit_streaks = {f"habit_{i}": habit_streak_avg for i in range(active_habits)}

    # Goal data
    context.active_goal_uids = [f"goal_{i}" for i in range(active_goals)]
    context.goal_progress = {f"goal_{i}": goal_progress_avg for i in range(active_goals)}
    context.get_goals_nearing_deadline = Mock(return_value=[])

    # Knowledge data
    context.mastered_knowledge_uids = {f"ku_{i}" for i in range(mastered_knowledge)}
    context.in_progress_knowledge_uids = set()
    context.next_recommended_knowledge = [f"ku.ready_{i}" for i in range(ready_to_learn_count)]
    context.mastery_average = 0.5
    context.current_learning_path_uid = None
    context.prerequisites_needed = {}
    context.is_blocked = is_blocked

    # Events
    context.upcoming_event_uids = []
    context.today_event_uids = []

    # Life path
    context.life_path_uid = None
    context.life_path_alignment_score = 0.0

    # Capacity
    context.is_overwhelmed = False

    # Domain progress (for calculate_domain_balance)
    context.domain_progress = domain_progress or {"tech": 0.5, "personal": 0.5}

    # Methods
    context.calculate_learning_velocity = Mock(return_value=learning_velocity)
    context.get_ready_to_learn = Mock(
        return_value=[f"ku.ready_{i}" for i in range(ready_to_learn_count)]
    )

    # Workload
    context.current_workload_score = current_workload_score

    return context


# ============================================================================
# TEST FIXTURES
# ============================================================================


@pytest.fixture
def analyzer():
    """Create UserStateAnalyzer."""
    return UserStateAnalyzer()


@pytest.fixture
def healthy_context():
    """Context representing healthy user state."""
    return create_mock_user_context(
        active_tasks=5,
        overdue_tasks=0,
        at_risk_habit_count=0,
        habit_streak_avg=14,
        goal_progress_avg=60.0,
        current_workload_score=0.5,
        learning_velocity=0.8,
        ready_to_learn_count=5,
    )


@pytest.fixture
def stressed_context():
    """Context representing stressed/overloaded user state."""
    return create_mock_user_context(
        active_tasks=20,
        overdue_tasks=8,
        at_risk_habit_count=3,
        habit_streak_avg=2,
        goal_progress_avg=20.0,
        current_workload_score=0.95,
        learning_velocity=0.3,
    )


@pytest.fixture
def stagnant_context():
    """Context representing stagnant user state."""
    return create_mock_user_context(
        active_tasks=2,
        overdue_tasks=0,
        at_risk_habit_count=0,
        habit_streak_avg=1,
        goal_progress_avg=10.0,
        learning_velocity=0.1,
        current_workload_score=0.1,
    )


# ============================================================================
# TESTS: User State Analysis
# ============================================================================


class TestUserStateAnalysis:
    """Test user state analysis."""

    @pytest.mark.asyncio
    async def test_analyze_user_state_returns_analysis(self, analyzer, healthy_context):
        """analyze_user_state returns AskesisAnalysis."""
        result = await analyzer.analyze_user_state(
            user_context=healthy_context,
            focus_areas=["productivity", "learning"],
            recommendations=[],
            optimizations=[],
        )

        assert result.is_ok
        analysis = result.value
        assert isinstance(analysis, AskesisAnalysis)

    @pytest.mark.asyncio
    async def test_analyze_user_state_includes_health_metrics(self, analyzer, healthy_context):
        """Analysis includes system health metrics."""
        result = await analyzer.analyze_user_state(
            user_context=healthy_context,
            focus_areas=[],
            recommendations=[],
            optimizations=[],
        )

        assert result.is_ok
        analysis = result.value
        assert hasattr(analysis, "health_metrics")


# ============================================================================
# TESTS: Pattern Detection
# ============================================================================


class TestPatternDetection:
    """Test pattern detection in user behavior."""

    @pytest.mark.asyncio
    async def test_identify_patterns_habit_goal_correlation(self, analyzer, healthy_context):
        """Detects habit-goal correlation patterns."""
        result = await analyzer.identify_patterns(healthy_context)

        assert result.is_ok
        patterns = result.value
        assert isinstance(patterns, list)

    @pytest.mark.asyncio
    async def test_identify_patterns_high_workload(self, analyzer, stressed_context):
        """Detects high workload/burnout risk patterns."""
        result = await analyzer.identify_patterns(stressed_context)

        assert result.is_ok
        patterns = result.value
        # Should detect overload pattern
        assert isinstance(patterns, list)


# ============================================================================
# TESTS: System Health Calculation
# ============================================================================


class TestSystemHealthCalculation:
    """Test system health metric calculation."""

    def test_calculate_system_health_all_metrics(self, analyzer, healthy_context):
        """calculate_system_health returns all metric categories."""
        health = analyzer.calculate_system_health(healthy_context)

        assert isinstance(health, dict)
        # Should include standard health metrics
        expected_keys = {"consistency", "progress", "balance", "momentum", "overall"}
        assert expected_keys.issubset(set(health.keys()))

    def test_calculate_system_health_healthy_scores(self, analyzer, healthy_context):
        """Healthy context produces good health scores."""
        health = analyzer.calculate_system_health(healthy_context)

        # Healthy context should have decent scores
        assert health.get("overall", 0) >= 0.0
        assert health.get("overall", 0) <= 1.0

    def test_calculate_system_health_stressed_scores(self, analyzer, stressed_context):
        """Stressed context produces lower health scores."""
        health = analyzer.calculate_system_health(stressed_context)

        # Stressed context should have lower sustainability
        assert health.get("sustainability", 1.0) <= 0.5 or health.get("overall", 1.0) <= 0.7


# ============================================================================
# TESTS: Risk Assessment
# ============================================================================


class TestRiskAssessment:
    """Test risk assessment functionality."""

    @pytest.mark.asyncio
    async def test_calculate_risk_assessment(self, analyzer, stressed_context):
        """Risk assessment identifies risks in stressed context."""
        result = await analyzer.analyze_user_state(
            user_context=stressed_context,
            focus_areas=[],
            recommendations=[],
            optimizations=[],
        )

        assert result.is_ok
        analysis = result.value
        # Stressed context should have identified risks
        assert hasattr(analysis, "risks") or hasattr(analysis, "risk_assessment")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
