"""
Tests for Profile Domain Stats Configuration
=============================================

Verifies the configuration-driven approach for calculating domain statistics
from UserContext.
"""

import pytest

from core.services.user.unified_user_context import UserContext
from ui.profile.domain_stats_config import (
    DOMAIN_STATS_CONFIG,
    choices_active,
    choices_count,
    choices_status_args,
    events_active,
    events_count,
    events_status_args,
    goals_active,
    goals_count,
    goals_status_args,
    habits_active,
    habits_count,
    habits_status_args,
    learning_active,
    learning_count,
    learning_status,
    principles_active,
    principles_count,
    principles_status_args,
    tasks_active,
    tasks_count,
    tasks_status_args,
)


@pytest.fixture
def mock_context() -> UserContext:
    """
    Create a mock UserContext with sample data.

    Uses minimal initialization - UserContext provides defaults for all fields.
    """
    context = UserContext(
        user_uid="user_test_123",
        username="testuser",
    )

    # Populate test data by modifying the context object
    # Tasks
    context.active_task_uids = ["task_1", "task_2", "task_3"]
    context.completed_task_uids = ["task_4", "task_5"]
    context.overdue_task_uids = ["task_1"]
    context.blocked_task_uids = ["task_2"]

    # Events
    context.upcoming_event_uids = ["event_1", "event_2"]
    context.today_event_uids = ["event_3"]
    context.missed_event_uids = ["event_4"]

    # Goals
    context.active_goal_uids = ["goal_1", "goal_2"]
    context.completed_goal_uids = ["goal_3"]
    context.at_risk_goals = ["goal_1"]

    # Habits
    context.active_habit_uids = ["habit_1", "habit_2", "habit_3"]
    context.at_risk_habits = ["habit_1"]

    # Principles
    context.core_principle_uids = ["principle_1", "principle_2"]
    context.decisions_aligned_with_principles = 5
    context.decisions_against_principles = 2

    # Choices
    context.pending_choice_uids = ["choice_1", "choice_2"]
    context.resolved_choice_uids = ["choice_3"]

    # Curriculum
    context.mastered_knowledge_uids = ["ku_1", "ku_2"]
    context.in_progress_knowledge_uids = ["ku_3"]
    context.ready_to_learn_uids = ["ku_4", "ku_5"]
    context.prerequisites_needed = ["ku_6"]
    context.enrolled_path_uids = ["lp_1"]

    return context


# ============================================================================
# TASKS DOMAIN TESTS
# ============================================================================


def test_tasks_count(mock_context: UserContext) -> None:
    """Test tasks count calculation (active + completed)."""
    assert tasks_count(mock_context) == 5  # 3 active + 2 completed


def test_tasks_active(mock_context: UserContext) -> None:
    """Test tasks active count calculation."""
    assert tasks_active(mock_context) == 3  # 3 active


def test_tasks_status_args(mock_context: UserContext) -> None:
    """Test tasks status args extraction."""
    assert tasks_status_args(mock_context) == (1, 1)  # 1 overdue, 1 blocked


def test_tasks_config() -> None:
    """Test tasks configuration exists and has correct structure."""
    config = DOMAIN_STATS_CONFIG.get("tasks")
    assert config is not None
    assert config.count_fn is not None
    assert config.active_fn is not None
    assert config.status_fn is not None
    assert config.status_args_fn is not None


# ============================================================================
# EVENTS DOMAIN TESTS
# ============================================================================


def test_events_count(mock_context: UserContext) -> None:
    """Test events count calculation (upcoming + today)."""
    assert events_count(mock_context) == 3  # 2 upcoming + 1 today


def test_events_active(mock_context: UserContext) -> None:
    """Test events active count calculation (today's events)."""
    assert events_active(mock_context) == 1  # 1 today


def test_events_status_args(mock_context: UserContext) -> None:
    """Test events status args extraction (first arg always 0)."""
    assert events_status_args(mock_context) == (0, 1)  # 0 missed today, 1 missed total


def test_events_config() -> None:
    """Test events configuration exists and has correct structure."""
    config = DOMAIN_STATS_CONFIG.get("events")
    assert config is not None


# ============================================================================
# GOALS DOMAIN TESTS
# ============================================================================


def test_goals_count(mock_context: UserContext) -> None:
    """Test goals count calculation (active + completed)."""
    assert goals_count(mock_context) == 3  # 2 active + 1 completed


def test_goals_active(mock_context: UserContext) -> None:
    """Test goals active count calculation."""
    assert goals_active(mock_context) == 2  # 2 active


def test_goals_status_args(mock_context: UserContext) -> None:
    """Test goals status args extraction."""
    result = goals_status_args(mock_context)
    assert result[0] == 1  # 1 at risk
    assert isinstance(result[1], int)  # stalled count (computed via get_stalled_goals())


def test_goals_config() -> None:
    """Test goals configuration exists and has correct structure."""
    config = DOMAIN_STATS_CONFIG.get("goals")
    assert config is not None


# ============================================================================
# HABITS DOMAIN TESTS
# ============================================================================


def test_habits_count(mock_context: UserContext) -> None:
    """Test habits count calculation (all active)."""
    assert habits_count(mock_context) == 3  # 3 active


def test_habits_active(mock_context: UserContext) -> None:
    """Test habits active count calculation (same as total)."""
    assert habits_active(mock_context) == 3  # Same as total


def test_habits_status_args(mock_context: UserContext) -> None:
    """Test habits status args extraction."""
    assert habits_status_args(mock_context) == (1,)  # 1 at risk


def test_habits_config() -> None:
    """Test habits configuration exists and has correct structure."""
    config = DOMAIN_STATS_CONFIG.get("habits")
    assert config is not None


# ============================================================================
# PRINCIPLES DOMAIN TESTS
# ============================================================================


def test_principles_count(mock_context: UserContext) -> None:
    """Test principles count calculation (all core principles)."""
    assert principles_count(mock_context) == 2  # 2 core principles


def test_principles_active(mock_context: UserContext) -> None:
    """Test principles active count calculation (same as total)."""
    assert principles_active(mock_context) == 2  # Same as total


def test_principles_status_args(mock_context: UserContext) -> None:
    """Test principles status args extraction."""
    assert principles_status_args(mock_context) == (5, 2)  # 5 aligned, 2 against


def test_principles_config() -> None:
    """Test principles configuration exists and has correct structure."""
    config = DOMAIN_STATS_CONFIG.get("principles")
    assert config is not None


# ============================================================================
# CHOICES DOMAIN TESTS
# ============================================================================


def test_choices_count(mock_context: UserContext) -> None:
    """Test choices count calculation (pending + resolved)."""
    assert choices_count(mock_context) == 3  # 2 pending + 1 resolved


def test_choices_active(mock_context: UserContext) -> None:
    """Test choices active count calculation (pending only)."""
    assert choices_active(mock_context) == 2  # 2 pending


def test_choices_status_args(mock_context: UserContext) -> None:
    """Test choices status args extraction."""
    assert choices_status_args(mock_context) == (2,)  # 2 pending


def test_choices_config() -> None:
    """Test choices configuration exists and has correct structure."""
    config = DOMAIN_STATS_CONFIG.get("choices")
    assert config is not None


# ============================================================================
# LEARNING DOMAIN TESTS
# ============================================================================


def test_learning_count(mock_context: UserContext) -> None:
    """Test learning count calculation (mastered + in_progress + ready)."""
    assert learning_count(mock_context) == 5  # 2 mastered + 1 in_progress + 2 ready


def test_learning_active(mock_context: UserContext) -> None:
    """Test learning active count calculation (in_progress + ready)."""
    assert learning_active(mock_context) == 3  # 1 in_progress + 2 ready


def test_learning_status_healthy(mock_context: UserContext) -> None:
    """Test learning status calculation with low blocking."""
    # 1 prerequisite needed, 1 enrolled path = 100% blocked but threshold is 50%
    status = learning_status(mock_context)
    assert status == "critical"  # 1 > 1 * 0.5


def test_learning_status_no_enrolled_paths() -> None:
    """Test learning status with no enrolled paths."""
    context = UserContext(
        user_uid="user_test",
        username="test",
    )
    context.prerequisites_needed = ["ku_1", "ku_2"]
    context.enrolled_path_uids = []

    status = learning_status(context)
    assert status == "warning"  # Blocked but no enrolled paths = warning


# ============================================================================
# CONFIGURATION COMPLETENESS TESTS
# ============================================================================


def test_all_activity_domains_have_config() -> None:
    """Test that all 6 activity domains have configuration."""
    expected_domains = {"tasks", "events", "goals", "habits", "principles", "choices"}
    assert set(DOMAIN_STATS_CONFIG.keys()) == expected_domains


def test_config_lookup_fallback() -> None:
    """Test that unknown domains return None (for fallback handling)."""
    config = DOMAIN_STATS_CONFIG.get("unknown_domain")
    assert config is None


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


def test_config_with_status_calculator(mock_context: UserContext) -> None:
    """Test full workflow: config lookup -> extract data -> calculate status."""
    config = DOMAIN_STATS_CONFIG.get("tasks")
    assert config is not None

    count = config.count_fn(mock_context)
    active = config.active_fn(mock_context)
    status_args = config.status_args_fn(mock_context)
    status = config.status_fn(*status_args)

    assert count == 5
    assert active == 3
    assert status_args == (1, 1)
    assert status == "warning"  # 1 overdue, 1 blocked = warning
