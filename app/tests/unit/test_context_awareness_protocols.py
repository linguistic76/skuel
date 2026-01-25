"""
Tests for Context Awareness Protocols
=====================================

Verifies that:
1. UserContext satisfies all awareness protocols
2. Protocol inheritance works correctly
3. Protocols can be used for type checking

These tests ensure the protocol-based slices work as designed.
"""

import pytest

from core.services.protocols.context_awareness_protocols import (
    ChoiceAwareness,
    CoreIdentity,
    CrossDomainAwareness,
    EventAwareness,
    FullAwareness,
    GoalAwareness,
    HabitAwareness,
    KnowledgeAwareness,
    LearningPathAwareness,
    PrincipleAwareness,
    TaskAwareness,
)
from core.services.user.unified_user_context import UserContext


class TestUserContextSatisfiesProtocols:
    """Verify UserContext implements all awareness protocols."""

    @pytest.fixture
    def context(self) -> UserContext:
        """Create a minimal UserContext for testing."""
        return UserContext(
            user_uid="test_user_001",
            username="test_user",
        )

    def test_satisfies_core_identity(self, context: UserContext):
        """UserContext should satisfy CoreIdentity protocol."""
        assert isinstance(context, CoreIdentity)
        assert context.user_uid == "test_user_001"
        assert context.username == "test_user"

    def test_satisfies_task_awareness(self, context: UserContext):
        """UserContext should satisfy TaskAwareness protocol."""
        assert isinstance(context, TaskAwareness)

        # Verify required fields exist
        assert hasattr(context, "active_task_uids")
        assert hasattr(context, "blocked_task_uids")
        assert hasattr(context, "completed_task_uids")
        assert hasattr(context, "overdue_task_uids")
        assert hasattr(context, "today_task_uids")
        assert hasattr(context, "task_priorities")
        assert hasattr(context, "tasks_by_goal")
        assert hasattr(context, "active_tasks_rich")

    def test_satisfies_knowledge_awareness(self, context: UserContext):
        """UserContext should satisfy KnowledgeAwareness protocol."""
        assert isinstance(context, KnowledgeAwareness)

        # Verify required fields exist
        assert hasattr(context, "knowledge_mastery")
        assert hasattr(context, "mastered_knowledge_uids")
        assert hasattr(context, "in_progress_knowledge_uids")
        assert hasattr(context, "prerequisites_needed")
        assert hasattr(context, "knowledge_units_rich")

    def test_satisfies_habit_awareness(self, context: UserContext):
        """UserContext should satisfy HabitAwareness protocol."""
        assert isinstance(context, HabitAwareness)

        # Verify required fields exist
        assert hasattr(context, "active_habit_uids")
        assert hasattr(context, "habit_streaks")
        assert hasattr(context, "at_risk_habits")
        assert hasattr(context, "habits_by_goal")
        assert hasattr(context, "active_habits_rich")

    def test_satisfies_goal_awareness(self, context: UserContext):
        """UserContext should satisfy GoalAwareness protocol."""
        assert isinstance(context, GoalAwareness)

        # Verify required fields exist
        assert hasattr(context, "active_goal_uids")
        assert hasattr(context, "completed_goal_uids")
        assert hasattr(context, "goal_progress")
        assert hasattr(context, "tasks_by_goal")
        assert hasattr(context, "active_goals_rich")

    def test_satisfies_event_awareness(self, context: UserContext):
        """UserContext should satisfy EventAwareness protocol."""
        assert isinstance(context, EventAwareness)

        # Verify required fields exist
        assert hasattr(context, "upcoming_event_uids")
        assert hasattr(context, "today_event_uids")
        assert hasattr(context, "scheduled_event_uids")
        assert hasattr(context, "active_events_rich")

    def test_satisfies_principle_awareness(self, context: UserContext):
        """UserContext should satisfy PrincipleAwareness protocol."""
        assert isinstance(context, PrincipleAwareness)

        # Verify required fields exist
        assert hasattr(context, "core_principle_uids")
        assert hasattr(context, "core_principles_rich")

    def test_satisfies_choice_awareness(self, context: UserContext):
        """UserContext should satisfy ChoiceAwareness protocol."""
        assert isinstance(context, ChoiceAwareness)

        # Verify required fields exist
        assert hasattr(context, "pending_choice_uids")
        assert hasattr(context, "recent_choices_rich")

    def test_satisfies_learning_path_awareness(self, context: UserContext):
        """UserContext should satisfy LearningPathAwareness protocol."""
        assert isinstance(context, LearningPathAwareness)

        # Verify required fields exist
        assert hasattr(context, "enrolled_path_uids")
        assert hasattr(context, "completed_path_uids")
        assert hasattr(context, "learning_path_step_uids")
        assert hasattr(context, "enrolled_paths_rich")

    def test_satisfies_cross_domain_awareness(self, context: UserContext):
        """UserContext should satisfy CrossDomainAwareness protocol."""
        assert isinstance(context, CrossDomainAwareness)

    def test_satisfies_full_awareness(self, context: UserContext):
        """UserContext should satisfy FullAwareness protocol."""
        assert isinstance(context, FullAwareness)


class TestProtocolUsagePatterns:
    """Test that protocols work correctly for type checking."""

    def test_function_accepting_task_awareness(self):
        """Functions can accept TaskAwareness and receive UserContext."""

        def get_blocked_count(ctx: TaskAwareness) -> int:
            return len(ctx.blocked_task_uids)

        context = UserContext(user_uid="test", username="test")
        context.blocked_task_uids = {"task1", "task2", "task3"}

        # UserContext satisfies TaskAwareness
        result = get_blocked_count(context)
        assert result == 3

    def test_function_accepting_knowledge_awareness(self):
        """Functions can accept KnowledgeAwareness and receive UserContext."""

        def get_average_mastery(ctx: KnowledgeAwareness) -> float:
            if not ctx.knowledge_mastery:
                return 0.0
            return sum(ctx.knowledge_mastery.values()) / len(ctx.knowledge_mastery)

        context = UserContext(user_uid="test", username="test")
        context.knowledge_mastery = {"ku1": 0.8, "ku2": 0.6, "ku3": 1.0}

        result = get_average_mastery(context)
        assert result == pytest.approx(0.8, rel=0.01)

    def test_function_accepting_habit_awareness(self):
        """Functions can accept HabitAwareness and receive UserContext."""

        def get_at_risk_count(ctx: HabitAwareness) -> int:
            return len(ctx.at_risk_habits)

        context = UserContext(user_uid="test", username="test")
        context.at_risk_habits = ["habit1", "habit2"]

        result = get_at_risk_count(context)
        assert result == 2

    def test_function_accepting_cross_domain_awareness(self):
        """Functions can accept CrossDomainAwareness for multi-domain analysis."""

        def calculate_productivity_score(ctx: CrossDomainAwareness) -> float:
            """Simple productivity metric using multiple domains."""
            task_factor = len(ctx.active_task_uids) - len(ctx.overdue_task_uids)
            habit_factor = sum(ctx.habit_streaks.values()) if ctx.habit_streaks else 0
            goal_factor = sum(ctx.goal_progress.values()) if ctx.goal_progress else 0

            return (task_factor + habit_factor + goal_factor) / 10.0

        context = UserContext(user_uid="test", username="test")
        context.active_task_uids = ["t1", "t2", "t3", "t4", "t5"]
        context.overdue_task_uids = ["t1"]
        context.habit_streaks = {"h1": 7, "h2": 14}
        context.goal_progress = {"g1": 0.5, "g2": 0.8}

        result = calculate_productivity_score(context)
        assert result > 0  # Some positive productivity


class TestProtocolDocumentation:
    """Test that protocol documentation is helpful."""

    def test_protocols_have_docstrings(self):
        """All protocols should have documentation."""
        protocols = [
            CoreIdentity,
            TaskAwareness,
            KnowledgeAwareness,
            HabitAwareness,
            GoalAwareness,
            EventAwareness,
            PrincipleAwareness,
            ChoiceAwareness,
            LearningPathAwareness,
            CrossDomainAwareness,
            FullAwareness,
        ]

        for protocol in protocols:
            assert protocol.__doc__ is not None, f"{protocol.__name__} missing docstring"
            assert len(protocol.__doc__) > 50, f"{protocol.__name__} docstring too short"

    def test_full_awareness_has_warning(self):
        """FullAwareness docstring should warn about overuse."""
        assert "WARNING" in FullAwareness.__doc__ or "sparingly" in FullAwareness.__doc__


class TestProtocolFieldCoverage:
    """Verify protocols cover the most-used UserContext fields."""

    def test_task_awareness_covers_key_fields(self):
        """TaskAwareness should cover frequently-used task fields."""
        # These are the most commonly accessed fields based on grep analysis
        key_fields = [
            "active_task_uids",
            "blocked_task_uids",
            "overdue_task_uids",
            "today_task_uids",
            "tasks_by_goal",
        ]

        context = UserContext(user_uid="test", username="test")

        # All key fields should be accessible via TaskAwareness
        task_ctx: TaskAwareness = context
        for field in key_fields:
            assert hasattr(task_ctx, field), f"TaskAwareness missing {field}"

    def test_knowledge_awareness_covers_key_fields(self):
        """KnowledgeAwareness should cover frequently-used knowledge fields."""
        key_fields = [
            "knowledge_mastery",
            "mastered_knowledge_uids",
            "in_progress_knowledge_uids",
            "prerequisites_needed",
        ]

        context = UserContext(user_uid="test", username="test")

        knowledge_ctx: KnowledgeAwareness = context
        for field in key_fields:
            assert hasattr(knowledge_ctx, field), f"KnowledgeAwareness missing {field}"
