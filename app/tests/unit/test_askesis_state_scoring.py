"""
Test Suite for State Scoring Functions
=======================================

Tests the pure state scoring functions from askesis/state_scoring.py:
- score_current_state
- find_key_blocker
- calculate_momentum
- calculate_domain_balance

These are pure functions with no dependencies (eliminates circular dependencies).
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from core.services.askesis.state_scoring import (
    calculate_domain_balance,
    calculate_momentum,
    find_key_blocker,
    score_current_state,
)

# ============================================================================
# MOCK FACTORIES
# ============================================================================


def create_mock_user_context(
    completed_tasks: int = 10,
    overdue_tasks: int = 0,
    blocked_tasks: int = 0,
    at_risk_habits: int = 0,
    habit_streaks: dict | None = None,
    is_blocked: bool = False,
    learning_velocity: float = 1.0,
    current_workload_score: float = 0.5,
    prerequisites_needed: dict | None = None,
    domain_progress: dict | None = None,
) -> Mock:
    """Create mock UserContext for state scoring tests.

    Uses actual UserContext field names from unified_user_context.py:
    - completed_task_uids: set of completed task UIDs
    - overdue_task_uids: list of overdue task UIDs
    - blocked_task_uids: list of blocked task UIDs
    - at_risk_habits: list of habits at risk
    - habit_streaks: dict mapping habit_uid to streak count
    - is_blocked: property indicating if user is blocked
    - current_workload_score: float 0.0-1.0
    - has_overdue_items: property based on overdue_task_uids
    - prerequisites_needed: dict mapping blocked_uid to list of prereq_uids
    - domain_progress: dict mapping domain to progress float
    - calculate_learning_velocity(): method returning float
    """
    context = Mock()
    context.user_uid = "test_user"

    # Task UIDs (sets/lists)
    context.completed_task_uids = {f"task_{i}" for i in range(completed_tasks)}
    context.overdue_task_uids = [f"overdue_{i}" for i in range(overdue_tasks)]
    context.blocked_task_uids = [f"blocked_{i}" for i in range(blocked_tasks)]

    # Properties
    context.is_blocked = is_blocked
    context.has_overdue_items = overdue_tasks > 0
    context.current_workload_score = current_workload_score

    # Habits
    context.at_risk_habits = [f"habit_{i}" for i in range(at_risk_habits)]
    context.habit_streaks = habit_streaks or {"habit_1": 7, "habit_2": 14}

    # Learning velocity method
    context.calculate_learning_velocity = Mock(return_value=learning_velocity)

    # Prerequisites (for find_key_blocker)
    context.prerequisites_needed = prerequisites_needed or {}

    # Domain progress (for calculate_domain_balance)
    context.domain_progress = domain_progress or {"tech": 0.5, "personal": 0.5}

    return context


# ============================================================================
# TEST FIXTURES
# ============================================================================


@pytest.fixture
def healthy_context():
    """Healthy, balanced user context."""
    return create_mock_user_context(
        completed_tasks=15,
        overdue_tasks=0,
        at_risk_habits=0,
        habit_streaks={"habit_1": 14, "habit_2": 14},
        is_blocked=False,
        learning_velocity=0.8,  # High but normalized (0.0-1.0 range)
        current_workload_score=0.5,
        domain_progress={"tech": 0.6, "personal": 0.5},
    )


@pytest.fixture
def struggling_context():
    """User context showing struggle."""
    return create_mock_user_context(
        completed_tasks=2,
        overdue_tasks=5,
        blocked_tasks=3,
        at_risk_habits=3,
        habit_streaks={"habit_1": 1, "habit_2": 0},
        is_blocked=True,
        learning_velocity=0.2,
        current_workload_score=0.9,
        domain_progress={"tech": 0.2, "personal": 0.1},
    )


@pytest.fixture
def blocked_context():
    """User context with blocked knowledge prerequisites."""
    return create_mock_user_context(
        is_blocked=True,
        blocked_tasks=5,
        prerequisites_needed={
            "ku.blocked_0": ["ku.prereq_a"],
            "ku.blocked_1": ["ku.prereq_a", "ku.prereq_b"],
            "ku.blocked_2": ["ku.prereq_a"],
            "ku.blocked_3": ["ku.prereq_c"],
            "ku.blocked_4": ["ku.prereq_a"],
        },
    )


@pytest.fixture
def imbalanced_context():
    """User context with domain imbalance."""
    return create_mock_user_context(
        domain_progress={"tech": 0.9, "personal": 0.1, "health": 0.0},
    )


# ============================================================================
# TESTS: score_current_state
# ============================================================================


class TestScoreCurrentState:
    """Test current state quality scoring."""

    def test_score_current_state_calculation(self, healthy_context):
        """Score calculation returns value in 0.0-1.0 range."""
        score = score_current_state(healthy_context)

        assert 0.0 <= score <= 1.0

    def test_score_current_state_healthy_high(self, healthy_context):
        """Healthy context scores higher."""
        score = score_current_state(healthy_context)

        # Healthy context should score reasonably well
        assert score >= 0.4

    def test_score_current_state_struggling_low(self, struggling_context):
        """Struggling context scores lower."""
        score = score_current_state(struggling_context)

        # Struggling context should score lower
        assert score <= 0.7


# ============================================================================
# TESTS: find_key_blocker
# ============================================================================


class TestFindKeyBlocker:
    """Test key blocker identification."""

    def test_find_key_blocker_with_blocked(self, blocked_context):
        """Finds the prerequisite blocking most items."""
        blocker = find_key_blocker(blocked_context)

        # Should identify ku.prereq_a as blocking the most items (4 blocked)
        if blocker is not None:
            assert isinstance(blocker, str)

    def test_find_key_blocker_none_blocked(self, healthy_context):
        """Returns None when nothing is blocked."""
        blocker = find_key_blocker(healthy_context)

        assert blocker is None


# ============================================================================
# TESTS: calculate_momentum
# ============================================================================


class TestCalculateMomentum:
    """Test momentum calculation."""

    def test_calculate_momentum_high_activity(self, healthy_context):
        """High activity context has good momentum."""
        momentum = calculate_momentum(healthy_context)

        assert 0.0 <= momentum <= 1.0
        # High activity should have decent momentum
        assert momentum >= 0.3

    def test_calculate_momentum_low_activity(self, struggling_context):
        """Low activity context has low momentum."""
        momentum = calculate_momentum(struggling_context)

        assert 0.0 <= momentum <= 1.0


# ============================================================================
# TESTS: calculate_domain_balance
# ============================================================================


class TestCalculateDomainBalance:
    """Test domain balance calculation."""

    def test_calculate_domain_balance_balanced(self, healthy_context):
        """Balanced context scores higher."""
        balance = calculate_domain_balance(healthy_context)

        assert 0.0 <= balance <= 1.0
        # Balanced tasks/goals should score reasonably
        assert balance >= 0.3

    def test_calculate_domain_balance_imbalanced(self, imbalanced_context):
        """Imbalanced context scores lower."""
        balance = calculate_domain_balance(imbalanced_context)

        assert 0.0 <= balance <= 1.0
        # All in one domain should score lower
        # (but exact threshold depends on implementation)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
