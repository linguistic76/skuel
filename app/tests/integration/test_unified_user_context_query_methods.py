"""
Integration Tests for UserContext Query Methods
=======================================================

Tests all intelligence/query methods on UserContext that filter
and analyze the user's domain data.

Coverage:
- Task query methods (get_tasks_for_goal, get_blocked_tasks)
- Event query methods (get_events_for_habit)
- Goal query methods (get_goals_nearing_deadline, get_stalled_goals)
- Habit query methods (get_habits_needing_reinforcement, get_habits_for_goal)
- Knowledge query methods (get_life_path_gaps)
- Workload query methods (calculate_current_workload)
"""

from datetime import date, timedelta

import pytest

from core.services.user.unified_user_context import RichUserContext, UserContext


class TestTaskQueryMethods:
    """Test task filtering and query methods"""

    def test_get_tasks_for_goal(self):
        """Should return tasks contributing to a specific goal"""
        context = RichUserContext(
            user_uid="user_test",
            username="testuser",
            tasks_by_goal={
                "goal:launch_app": ["task:1", "task:2", "task:3"],
                "goal:learn_python": ["task:4"],
            },
        )

        launch_tasks = context.get_tasks_for_goal("goal:launch_app")
        python_tasks = context.get_tasks_for_goal("goal:learn_python")
        nonexistent_tasks = context.get_tasks_for_goal("goal:nonexistent")

        assert len(launch_tasks) == 3
        assert "task:1" in launch_tasks
        assert len(python_tasks) == 1
        assert "task:4" in python_tasks
        assert len(nonexistent_tasks) == 0  # Returns empty list for missing goal

    def test_get_blocked_tasks(self):
        """Should return tasks blocked by prerequisites"""
        context = RichUserContext(
            user_uid="user_test",
            username="testuser",
            blocked_task_uids={"task:blocked_1", "task:blocked_2"},
        )

        blocked = context.get_blocked_tasks()

        assert len(blocked) == 2
        assert "task:blocked_1" in blocked
        assert "task:blocked_2" in blocked


class TestEventQueryMethods:
    """Test event filtering and query methods"""

    def test_get_events_for_habit(self):
        """Should return events that reinforce a specific habit"""
        context = UserContext(
            user_uid="user_test",
            username="testuser",
            events_by_habit={
                "habit:meditation": ["event:1", "event:2", "event:3"],
                "habit:exercise": ["event:4"],
            },
        )

        meditation_events = context.get_events_for_habit("habit:meditation")
        exercise_events = context.get_events_for_habit("habit:exercise")
        nonexistent_events = context.get_events_for_habit("habit:nonexistent")

        assert len(meditation_events) == 3
        assert "event:1" in meditation_events
        assert len(exercise_events) == 1
        assert len(nonexistent_events) == 0


class TestGoalQueryMethods:
    """Test goal filtering and query methods"""

    def test_get_goals_nearing_deadline(self):
        """Should return goals with deadlines within specified days"""
        today = date.today()
        context = UserContext(
            user_uid="user_test",
            username="testuser",
            goal_deadlines={
                "goal:soon": today + timedelta(days=10),  # Within 30 days
                "goal:urgent": today + timedelta(days=5),  # Within 30 days
                "goal:later": today + timedelta(days=60),  # Outside 30 days
                "goal:past": today - timedelta(days=5),  # Past deadline
            },
            completed_goal_uids={"goal:finished"},
        )

        # Default 30-day window
        near_deadline = context.get_goals_nearing_deadline()
        assert len(near_deadline) == 3  # soon, urgent, past
        assert "goal:soon" in near_deadline
        assert "goal:urgent" in near_deadline
        assert "goal:past" in near_deadline  # Overdue counts as near deadline
        assert "goal:later" not in near_deadline

        # Custom 7-day window
        very_near = context.get_goals_nearing_deadline(days=7)
        assert len(very_near) == 2  # urgent, past
        assert "goal:urgent" in very_near
        assert "goal:soon" not in very_near  # 10 days away

    def test_get_stalled_goals(self):
        """Should return goals with minimal progress"""
        context = UserContext(
            user_uid="user_test",
            username="testuser",
            active_goal_uids=["goal:1", "goal:2", "goal:3", "goal:4"],
            goal_progress={
                "goal:1": 0.05,  # Stalled (5%)
                "goal:2": 0.09,  # Stalled (9%)
                "goal:3": 0.50,  # Making progress
                "goal:4": 0.0,  # Not started / stalled
            },
        )

        stalled = context.get_stalled_goals()

        # Should return goals with <10% progress
        assert len(stalled) == 3
        assert "goal:1" in stalled
        assert "goal:2" in stalled
        assert "goal:4" in stalled
        assert "goal:3" not in stalled  # Has 50% progress


class TestHabitQueryMethods:
    """Test habit filtering and query methods"""

    def test_get_habits_needing_reinforcement(self):
        """Should return at-risk habits"""
        context = RichUserContext(
            user_uid="user_test",
            username="testuser",
            at_risk_habits=["habit:meditation", "habit:exercise"],
        )

        at_risk = context.get_habits_needing_reinforcement()

        assert len(at_risk) == 2
        assert "habit:meditation" in at_risk
        assert "habit:exercise" in at_risk

    def test_get_habits_for_goal(self):
        """Should return habits supporting a specific goal"""
        context = RichUserContext(
            user_uid="user_test",
            username="testuser",
            habits_by_goal={
                "goal:fitness": ["habit:run", "habit:yoga", "habit:diet"],
                "goal:mindfulness": ["habit:meditation"],
            },
        )

        fitness_habits = context.get_habits_for_goal("goal:fitness")
        mindfulness_habits = context.get_habits_for_goal("goal:mindfulness")
        nonexistent_habits = context.get_habits_for_goal("goal:nonexistent")

        assert len(fitness_habits) == 3
        assert "habit:run" in fitness_habits
        assert len(mindfulness_habits) == 1
        assert len(nonexistent_habits) == 0


class TestLifePathQueryMethods:
    """Test life path and knowledge query methods"""

    def test_get_life_path_gaps(self):
        """Should return life path knowledge with low substance"""
        context = UserContext(
            user_uid="user_test",
            username="testuser",
            life_path_uid="lp:wellness",
            knowledge_mastery={
                "ku:meditation": 0.3,  # Low substance (gap)
                "ku:yoga": 0.4,  # Low substance (gap)
                "ku:nutrition": 0.7,  # Well practiced
                "ku:mindfulness": 0.9,  # Lifestyle integrated
            },
        )

        gaps = context.get_life_path_gaps()

        # Should return knowledge with <0.5 substance
        assert len(gaps) == 2
        assert "ku:meditation" in gaps
        assert "ku:yoga" in gaps
        assert "ku:nutrition" not in gaps
        assert "ku:mindfulness" not in gaps

    def test_get_life_path_gaps_no_life_path(self):
        """Should return empty list when no life path set"""
        context = UserContext(
            user_uid="user_test",
            username="testuser",
            life_path_uid=None,
            knowledge_mastery={"ku:something": 0.2},
        )

        gaps = context.get_life_path_gaps()

        assert len(gaps) == 0


class TestWorkloadQueryMethods:
    """Test workload and capacity methods"""

    def test_calculate_current_workload(self):
        """Should calculate workload based on active items"""
        context = UserContext(
            user_uid="user_test",
            username="testuser",
            active_task_uids=["task:1", "task:2", "task:3"],  # 3 tasks
            today_event_uids=["event:1", "event:2"],  # 2 events
            daily_habits=["habit:1"],  # 1 habit
            available_minutes_daily=300,  # 5 hours = 20 items @ 15min each
        )

        workload = context.calculate_current_workload()

        # 6 items / 20 capacity = 0.3
        assert workload == pytest.approx(0.3, abs=0.01)

    def test_calculate_current_workload_overloaded(self):
        """Should cap workload at 1.0 when overloaded"""
        context = UserContext(
            user_uid="user_test",
            username="testuser",
            active_task_uids=["task:1", "task:2", "task:3", "task:4", "task:5"],
            today_event_uids=["event:1", "event:2", "event:3"],
            daily_habits=["habit:1", "habit:2"],
            available_minutes_daily=60,  # 1 hour = 4 items @ 15min each
        )

        workload = context.calculate_current_workload()

        # 10 items / 4 capacity = 2.5, but capped at 1.0
        assert workload == 1.0
