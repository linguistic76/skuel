"""
Integration Tests for UserContext Query Methods
=======================================================

Tests all intelligence/query methods on UserContext that filter
and analyze the user's domain data.

Coverage:
- Task query methods (get_tasks_for_today, get_blocked_tasks, etc.)
- Event query methods (get_events_for_habit, get_events_needing_attendance)
- Goal query methods (get_goals_nearing_deadline, get_stalled_goals)
- Habit query methods (get_habits_needing_reinforcement, get_high_impact_habits)
- Knowledge query methods (get_life_path_gaps)
- Facet query methods (evaluate_against_facets, get_top_facets)
- Principle query methods (get_principle_aligned_tasks, has_principle_conflict)
- Workload query methods (calculate_current_workload, has_capacity_for_new_goal)
- Recommendation methods (get_recommended_next_action)
"""

from datetime import date, timedelta

import pytest

from core.models.enums import Domain
from core.services.user.unified_user_context import UserContext


class TestTaskQueryMethods:
    """Test task filtering and query methods"""

    def test_get_tasks_for_today(self):
        """Should return tasks due today"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            today_task_uids=["task:today_1", "task:today_2"],
        )

        today_tasks = context.get_tasks_for_today()

        assert len(today_tasks) == 2
        assert "task:today_1" in today_tasks
        assert "task:today_2" in today_tasks

    def test_get_tasks_for_goal(self):
        """Should return tasks contributing to a specific goal"""
        context = UserContext(
            user_uid="user:test",
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
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            blocked_task_uids={"task:blocked_1", "task:blocked_2"},
        )

        blocked = context.get_blocked_tasks()

        assert len(blocked) == 2
        assert "task:blocked_1" in blocked
        assert "task:blocked_2" in blocked

    def test_get_high_impact_tasks(self):
        """Should return tasks with high goal contribution"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            active_task_uids=["task:1", "task:2", "task:3", "task:4"],
            task_priorities={
                "task:1": 0.9,  # High impact
                "task:2": 0.8,  # High impact
                "task:3": 0.5,  # Low impact
                "task:4": 0.6,  # Below threshold
            },
        )

        # Default threshold (0.7)
        high_impact = context.get_high_impact_tasks()
        assert len(high_impact) == 2
        assert "task:1" in high_impact
        assert "task:2" in high_impact

        # Custom threshold (0.6)
        high_impact_lower = context.get_high_impact_tasks(threshold=0.6)
        assert len(high_impact_lower) == 3
        assert "task:4" in high_impact_lower


class TestEventQueryMethods:
    """Test event filtering and query methods"""

    def test_get_events_for_habit(self):
        """Should return events that reinforce a specific habit"""
        context = UserContext(
            user_uid="user:test",
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

    def test_get_events_needing_attendance(self):
        """Should return upcoming recurring events with active streaks"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            upcoming_event_uids=["event:1", "event:2", "event:3", "event:4"],
            recurring_event_uids=["event:1", "event:2", "event:3"],
            event_streaks={
                "event:1": 10,  # 10-day streak (needs attendance)
                "event:2": 5,  # 5-day streak (not critical yet)
                "event:3": 14,  # 14-day streak (critical)
            },
        )

        critical_events = context.get_events_needing_attendance()

        # Should return events with streak > 7 days
        assert len(critical_events) == 2
        assert "event:1" in critical_events  # 10-day streak
        assert "event:3" in critical_events  # 14-day streak
        assert "event:2" not in critical_events  # 5-day streak not critical yet


class TestGoalQueryMethods:
    """Test goal filtering and query methods"""

    def test_get_goals_nearing_deadline(self):
        """Should return goals with deadlines within specified days"""
        today = date.today()
        context = UserContext(
            user_uid="user:test",
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
            user_uid="user:test",
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
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            at_risk_habits=["habit:meditation", "habit:exercise"],
        )

        at_risk = context.get_habits_needing_reinforcement()

        assert len(at_risk) == 2
        assert "habit:meditation" in at_risk
        assert "habit:exercise" in at_risk

    def test_get_habits_for_goal(self):
        """Should return habits supporting a specific goal"""
        context = UserContext(
            user_uid="user:test",
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

    def test_get_high_impact_habits(self):
        """Should return keystone habits affecting multiple goals"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            keystone_habits=["habit:meditation", "habit:journaling"],
        )

        keystone = context.get_high_impact_habits()

        assert len(keystone) == 2
        assert "habit:meditation" in keystone
        assert "habit:journaling" in keystone


class TestLifePathQueryMethods:
    """Test life path and knowledge query methods"""

    def test_get_life_path_gaps(self):
        """Should return life path knowledge with low substance"""
        context = UserContext(
            user_uid="user:test",
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
            user_uid="user:test",
            username="testuser",
            life_path_uid=None,
            knowledge_mastery={"ku:something": 0.2},
        )

        gaps = context.get_life_path_gaps()

        assert len(gaps) == 0


class TestFacetQueryMethods:
    """Test facet profile and content preference methods"""

    def test_evaluate_against_facets_perfect_match(self):
        """Should return high score for perfect facet match"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            facet_profile={
                "tags": ["python", "testing", "docker"],
                "difficulty": ["intermediate"],
            },
        )

        required_facets = {
            "tags": ["python", "testing"],
            "difficulty": ["intermediate"],
        }

        score = context.evaluate_against_facets(required_facets)

        # Perfect match should be 1.0
        assert score == pytest.approx(1.0, abs=0.01)

    def test_evaluate_against_facets_partial_match(self):
        """Should return proportional score for partial match"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            facet_profile={
                "tags": ["python", "testing"],  # Missing "docker"
            },
        )

        required_facets = {
            "tags": ["python", "testing", "docker"],  # 2 of 3 match
        }

        score = context.evaluate_against_facets(required_facets)

        # 2/3 match = ~0.67
        assert 0.6 < score < 0.7

    def test_evaluate_against_facets_no_match(self):
        """Should return low score for no match"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            facet_profile={
                "tags": ["java", "spring"],
            },
        )

        required_facets = {
            "tags": ["python", "testing"],  # No overlap
        }

        score = context.evaluate_against_facets(required_facets)

        assert score == 0.0

    def test_get_top_facets(self):
        """Should return top facets sorted by affinity"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            facet_profile={
                "tags": ["python", "testing", "docker", "kubernetes", "react"],
            },
            facet_affinities={
                "python": 0.9,
                "testing": 0.7,
                "docker": 0.6,
                "kubernetes": 0.5,
                "react": 0.4,
            },
        )

        top_3 = context.get_top_facets("tags", n=3)

        assert len(top_3) == 3
        assert top_3[0] == "python"  # Highest affinity
        assert top_3[1] == "testing"
        assert top_3[2] == "docker"

    def test_get_facet_recommendations(self):
        """Should return comprehensive facet recommendations"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            facet_profile={
                "tags": ["python", "testing"],
                "domains": ["tech", "health"],
                "difficulty": ["intermediate"],
            },
            facet_affinities={
                "python": 0.9,
                "testing": 0.7,
            },
            content_type_preferences={
                "video": 0.8,
                "text": 0.6,
                "audio": 0.3,
            },
        )

        recommendations = context.get_facet_recommendations()

        # Should have all recommendation categories
        assert "preferred_tags" in recommendations
        assert "preferred_domains" in recommendations
        assert "preferred_difficulty" in recommendations
        assert "content_types" in recommendations

        # Check top tags are sorted by affinity
        assert len(recommendations["preferred_tags"]) <= 10
        assert recommendations["preferred_tags"][0] == "python"


class TestPrincipleQueryMethods:
    """Test principle alignment methods"""

    def test_get_principle_aligned_tasks(self):
        """Should return high-impact tasks when principle is important"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            core_principle_uids=["principle:minimalism", "principle:health"],
            principle_priorities={
                "principle:minimalism": 0.9,  # Very important
                "principle:health": 0.5,  # Moderate importance
            },
            active_task_uids=["task:1", "task:2", "task:3"],
            task_priorities={
                "task:1": 0.9,
                "task:2": 0.8,
                "task:3": 0.5,
            },
        )

        # High-priority principle should return high-impact tasks
        minimalism_tasks = context.get_principle_aligned_tasks("principle:minimalism")
        assert len(minimalism_tasks) == 2  # task:1, task:2 have priority >=0.7

        # Moderate-priority principle should return empty (importance <= 0.7)
        health_tasks = context.get_principle_aligned_tasks("principle:health")
        assert len(health_tasks) == 0

    def test_has_principle_conflict(self):
        """Should detect low alignment with domain"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            principle_alignment_by_domain={
                Domain.TECH: 0.9,  # Well aligned
                Domain.FINANCE: 0.3,  # Conflict!
            },
        )

        # No conflict with tech
        assert context.has_principle_conflict(Domain.TECH) is False

        # Conflict with finance
        assert context.has_principle_conflict(Domain.FINANCE) is True

        # No data for domain defaults to 1.0 (no conflict)
        assert context.has_principle_conflict(Domain.HEALTH) is False


class TestWorkloadQueryMethods:
    """Test workload and capacity methods"""

    def test_calculate_current_workload(self):
        """Should calculate workload based on active items"""
        context = UserContext(
            user_uid="user:test",
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
            user_uid="user:test",
            username="testuser",
            active_task_uids=["task:1", "task:2", "task:3", "task:4", "task:5"],
            today_event_uids=["event:1", "event:2", "event:3"],
            daily_habits=["habit:1", "habit:2"],
            available_minutes_daily=60,  # 1 hour = 4 items @ 15min each
        )

        workload = context.calculate_current_workload()

        # 10 items / 4 capacity = 2.5, but capped at 1.0
        assert workload == 1.0

    def test_has_capacity_for_new_goal_available(self):
        """Should allow new goal when under capacity"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            current_workload_score=0.5,  # 50% capacity
            active_goal_uids=["goal:1", "goal:2"],  # 2 active goals
            is_overwhelmed=False,
        )

        has_capacity = context.has_capacity_for_new_goal()

        assert has_capacity is True  # Under 80%, under 5 goals, not overwhelmed

    def test_has_capacity_for_new_goal_overloaded(self):
        """Should reject new goal when overloaded"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            current_workload_score=0.9,  # 90% capacity (over threshold)
            active_goal_uids=["goal:1", "goal:2"],
            is_overwhelmed=False,
        )

        has_capacity = context.has_capacity_for_new_goal()

        assert has_capacity is False  # Workload too high

    def test_has_capacity_for_new_goal_too_many_goals(self):
        """Should reject new goal when at goal limit"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            current_workload_score=0.5,
            active_goal_uids=["goal:1", "goal:2", "goal:3", "goal:4", "goal:5"],  # 5 goals
            is_overwhelmed=False,
        )

        has_capacity = context.has_capacity_for_new_goal()

        assert has_capacity is False  # At goal limit

    def test_has_capacity_for_new_goal_overwhelmed(self):
        """Should reject new goal when user is overwhelmed"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            current_workload_score=0.5,
            active_goal_uids=["goal:1"],
            is_overwhelmed=True,  # User is overwhelmed
        )

        has_capacity = context.has_capacity_for_new_goal()

        assert has_capacity is False  # User overwhelmed


class TestRecommendationMethods:
    """Test recommendation generation methods"""

    def test_get_recommended_next_action_blocked(self):
        """Should recommend unblocking when user is blocked"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            is_blocked=True,
            prerequisites_needed={
                "ku:advanced": ["ku:basic"],
                "ku:expert": ["ku:advanced"],
            },
        )

        action = context.get_recommended_next_action()

        assert action["type"] == "unblock"
        assert action["action"] == "complete_prerequisites"
        assert len(action["items"]) <= 3  # Returns top 3

    def test_get_recommended_next_action_at_risk_habits(self):
        """Should recommend habit reinforcement when streaks at risk"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            is_blocked=False,
            at_risk_habits=["habit:meditation", "habit:exercise", "habit:reading"],
        )

        action = context.get_recommended_next_action()

        assert action["type"] == "maintain"
        assert action["action"] == "reinforce_habits"
        assert len(action["items"]) == 2  # Returns top 2 at-risk

    def test_get_recommended_next_action_overdue(self):
        """Should recommend catching up on overdue tasks"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            is_blocked=False,
            at_risk_habits=[],
            overdue_task_uids=["task:1", "task:2", "task:3"],
        )

        action = context.get_recommended_next_action()

        assert action["type"] == "catch_up"
        assert action["action"] == "complete_overdue"
        assert len(action["items"]) == 2  # Returns top 2 overdue

    def test_get_recommended_next_action_progress_goal(self):
        """Should recommend goal progress when no urgent issues"""
        context = UserContext(
            user_uid="user:test",
            username="testuser",
            is_blocked=False,
            at_risk_habits=[],
            overdue_task_uids=[],
            primary_goal_focus="goal:launch_app",
            tasks_by_goal={
                "goal:launch_app": ["task:design", "task:implement", "task:deploy"],
            },
        )

        action = context.get_recommended_next_action()

        assert action["type"] == "progress"
        assert action["action"] == "advance_goal"
        assert len(action["items"]) == 2  # Returns top 2 tasks for goal
