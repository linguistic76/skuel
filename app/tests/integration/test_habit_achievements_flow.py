"""
Integration Tests: Habit Streak→Achievement Badges Flow (Phase 4)
=====================================================================

Tests the complete event-driven flow:
1. Habit reaches streak milestone (7, 30, 100, 365 days)
2. HabitStreakMilestone event published
3. HabitAchievementService awards badge
4. Achievement node created in Neo4j
5. EARNED_BADGE relationship established
6. AchievementEarned event published

Version: 1.0.0
Date: 2025-11-05
"""

from datetime import datetime

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.events.habit_events import AchievementEarned, HabitStreakMilestone
from core.models.enums import RecurrencePattern
from core.models.enums.entity_enums import EntityStatus as HabitStatus
from core.models.enums.entity_enums import EntityType
from core.models.enums.habit_enums import HabitCategory
from core.models.habit.habit import Habit as Habit
from core.services.habits.habit_achievement_service import HabitAchievementService


@pytest.mark.asyncio
@pytest.mark.integration
class TestHabitAchievementsFlow:
    """
    Integration tests for Habit→Achievement Badges event-driven flow.

    Tests cover:
    - Badge awarding for all 4 milestones (7, 30, 100, 365 days)
    - Duplicate badge prevention
    - Graph relationship creation
    - Event publishing
    - Error handling
    """

    @pytest_asyncio.fixture
    async def event_bus(self):
        """Create event bus for capturing published events."""
        return InMemoryEventBus(capture_history=True)

    @pytest_asyncio.fixture
    async def habit_backend(self, neo4j_driver, clean_neo4j):
        """Create Habit backend with clean database."""
        return UniversalNeo4jBackend[Habit](
            neo4j_driver, "Entity", Habit, default_filters={"ku_type": "habit"}
        )

    @pytest_asyncio.fixture
    async def achievement_service(self, habit_backend, event_bus):
        """Create HabitAchievementService with backend and event bus."""
        return HabitAchievementService(backend=habit_backend, event_bus=event_bus)

    @pytest_asyncio.fixture
    async def test_user(self, neo4j_driver, test_user_uid):
        """Create test user node in Neo4j."""
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MERGE (u:User {uid: $user_uid})
                ON CREATE SET
                    u.username = $username,
                    u.email = $email,
                    u.created_at = datetime()
                RETURN u
                """,
                user_uid=test_user_uid,
                username="test_habit_achiever",
                email="achiever@test.com",
            )
        return test_user_uid

    @pytest_asyncio.fixture
    async def daily_habit(self, habit_backend, neo4j_driver, test_user_uid, test_user):
        """Create a daily habit for testing."""
        habit = Habit(
            uid="habit.daily_coding",
            user_uid=test_user_uid,
            ku_type=EntityType.HABIT,
            title="Daily Coding Practice",
            description="Code for at least 30 minutes every day",
            habit_category=HabitCategory.LEARNING,
            status=HabitStatus.ACTIVE,
            recurrence_pattern=RecurrencePattern.DAILY,
        )
        result = await habit_backend.create(habit)
        assert result.is_ok

        # Add :Habit secondary label so production Cypher MATCH (habit:Habit ...) works
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (h:Entity {uid: $uid}) SET h:Habit",
                uid=habit.uid,
            )

        return result.value

    # ========================================================================
    # MILESTONE BADGE TESTS
    # ========================================================================

    async def test_week_warrior_badge_awarded(
        self, achievement_service, event_bus, daily_habit, test_user_uid
    ):
        """Test that Week Warrior badge is awarded for 7-day streak."""
        # Publish HabitStreakMilestone event for 7 days
        event = HabitStreakMilestone(
            habit_uid=daily_habit.uid,
            user_uid=test_user_uid,
            streak_length=7,
            occurred_at=datetime.now(),
            milestone_name="one_week",
        )

        # Handle event
        await achievement_service.handle_habit_streak_milestone(event)

        # Verify AchievementEarned event was published
        achievement_events = [
            e for e in event_bus.get_event_history() if isinstance(e, AchievementEarned)
        ]
        assert len(achievement_events) == 1

        earned_event = achievement_events[0]
        assert earned_event.user_uid == test_user_uid
        assert earned_event.habit_uid == daily_habit.uid
        assert earned_event.badge_id == "habit_week_warrior"
        assert earned_event.badge_name == "Week Warrior"
        assert earned_event.badge_tier == "bronze"
        assert earned_event.streak_length == 7

        # Verify badge exists in database
        badges_result = await achievement_service.get_user_badges(test_user_uid)
        assert badges_result.is_ok
        badges = badges_result.value
        assert len(badges) == 1
        assert badges[0]["badge_id"] == "habit_week_warrior"

    async def test_month_master_badge_awarded(
        self, achievement_service, event_bus, daily_habit, test_user_uid
    ):
        """Test that Month Master badge is awarded for 30-day streak."""
        event = HabitStreakMilestone(
            habit_uid=daily_habit.uid,
            user_uid=test_user_uid,
            streak_length=30,
            occurred_at=datetime.now(),
            milestone_name="one_month",
        )

        await achievement_service.handle_habit_streak_milestone(event)

        # Verify AchievementEarned event
        achievement_events = [
            e for e in event_bus.get_event_history() if isinstance(e, AchievementEarned)
        ]
        assert len(achievement_events) == 1
        earned_event = achievement_events[0]
        assert earned_event.badge_id == "habit_month_master"
        assert earned_event.badge_tier == "silver"
        assert earned_event.streak_length == 30

    async def test_century_champion_badge_awarded(
        self, achievement_service, event_bus, daily_habit, test_user_uid
    ):
        """Test that Century Champion badge is awarded for 100-day streak."""
        event = HabitStreakMilestone(
            habit_uid=daily_habit.uid,
            user_uid=test_user_uid,
            streak_length=100,
            occurred_at=datetime.now(),
            milestone_name="one_hundred",
        )

        await achievement_service.handle_habit_streak_milestone(event)

        # Verify AchievementEarned event
        achievement_events = [
            e for e in event_bus.get_event_history() if isinstance(e, AchievementEarned)
        ]
        assert len(achievement_events) == 1
        earned_event = achievement_events[0]
        assert earned_event.badge_id == "habit_century_champion"
        assert earned_event.badge_tier == "gold"
        assert earned_event.streak_length == 100

    async def test_year_legend_badge_awarded(
        self, achievement_service, event_bus, daily_habit, test_user_uid
    ):
        """Test that Year Legend badge is awarded for 365-day streak."""
        event = HabitStreakMilestone(
            habit_uid=daily_habit.uid,
            user_uid=test_user_uid,
            streak_length=365,
            occurred_at=datetime.now(),
            milestone_name="one_year",
        )

        await achievement_service.handle_habit_streak_milestone(event)

        # Verify AchievementEarned event
        achievement_events = [
            e for e in event_bus.get_event_history() if isinstance(e, AchievementEarned)
        ]
        assert len(achievement_events) == 1
        earned_event = achievement_events[0]
        assert earned_event.badge_id == "habit_year_legend"
        assert earned_event.badge_tier == "platinum"
        assert earned_event.streak_length == 365

    # ========================================================================
    # DUPLICATE PREVENTION TESTS
    # ========================================================================

    async def test_duplicate_badge_prevention(
        self, achievement_service, event_bus, daily_habit, test_user_uid
    ):
        """Test that the same badge is not awarded twice for the same habit."""
        # Award badge first time
        event = HabitStreakMilestone(
            habit_uid=daily_habit.uid,
            user_uid=test_user_uid,
            streak_length=7,
            occurred_at=datetime.now(),
            milestone_name="one_week",
        )
        await achievement_service.handle_habit_streak_milestone(event)

        # Clear event bus
        event_bus.clear_event_history()

        # Try to award same badge again
        event2 = HabitStreakMilestone(
            habit_uid=daily_habit.uid,
            user_uid=test_user_uid,
            streak_length=7,
            occurred_at=datetime.now(),
            milestone_name="one_week",
        )
        await achievement_service.handle_habit_streak_milestone(event2)

        # Verify NO new AchievementEarned event was published
        achievement_events = [
            e for e in event_bus.get_event_history() if isinstance(e, AchievementEarned)
        ]
        assert len(achievement_events) == 0

        # Verify only one badge in database
        badges_result = await achievement_service.get_user_badges(test_user_uid)
        assert badges_result.is_ok
        badges = badges_result.value
        assert len(badges) == 1

    async def test_multiple_milestones_same_habit(
        self, achievement_service, event_bus, daily_habit, test_user_uid
    ):
        """Test that a habit can earn multiple milestone badges (7, 30, 100, 365)."""
        # Award Week Warrior (7 days)
        event1 = HabitStreakMilestone(
            habit_uid=daily_habit.uid,
            user_uid=test_user_uid,
            streak_length=7,
            occurred_at=datetime.now(),
            milestone_name="one_week",
        )
        await achievement_service.handle_habit_streak_milestone(event1)

        # Award Month Master (30 days)
        event2 = HabitStreakMilestone(
            habit_uid=daily_habit.uid,
            user_uid=test_user_uid,
            streak_length=30,
            occurred_at=datetime.now(),
            milestone_name="one_month",
        )
        await achievement_service.handle_habit_streak_milestone(event2)

        # Award Century Champion (100 days)
        event3 = HabitStreakMilestone(
            habit_uid=daily_habit.uid,
            user_uid=test_user_uid,
            streak_length=100,
            occurred_at=datetime.now(),
            milestone_name="one_hundred",
        )
        await achievement_service.handle_habit_streak_milestone(event3)

        # Verify 3 badges earned
        badges_result = await achievement_service.get_user_badges(test_user_uid)
        assert badges_result.is_ok
        badges = badges_result.value
        assert len(badges) == 3

        # Verify badge IDs
        badge_ids = {b["badge_id"] for b in badges}
        assert badge_ids == {
            "habit_week_warrior",
            "habit_month_master",
            "habit_century_champion",
        }

    # ========================================================================
    # GRAPH RELATIONSHIP TESTS
    # ========================================================================

    async def test_badge_graph_relationships(
        self, achievement_service, neo4j_driver, daily_habit, test_user_uid
    ):
        """Test that correct graph relationships are created."""
        # Award badge
        event = HabitStreakMilestone(
            habit_uid=daily_habit.uid,
            user_uid=test_user_uid,
            streak_length=7,
            occurred_at=datetime.now(),
            milestone_name="one_week",
        )
        await achievement_service.handle_habit_streak_milestone(event)

        # Verify User→EARNED_BADGE→Achievement relationship
        query = """
        MATCH (user:User {uid: $user_uid})-[r:EARNED_BADGE]->(badge:Achievement {badge_id: $badge_id})
        RETURN r.streak_length as streak_length,
               r.habit_uid as habit_uid,
               badge.name as badge_name,
               badge.tier as badge_tier
        """
        async with neo4j_driver.session() as session:
            result = await session.run(
                query, {"user_uid": test_user_uid, "badge_id": "habit_week_warrior"}
            )
            record = await result.single()

        assert record is not None
        assert record["streak_length"] == 7
        assert record["habit_uid"] == daily_habit.uid
        assert record["badge_name"] == "Week Warrior"
        assert record["badge_tier"] == "bronze"

        # Verify Habit→UNLOCKED_ACHIEVEMENT→Achievement relationship
        query2 = """
        MATCH (habit:Entity {uid: $habit_uid})-[:UNLOCKED_ACHIEVEMENT]->(badge:Achievement {badge_id: $badge_id})
        RETURN badge.name as badge_name
        """
        async with neo4j_driver.session() as session:
            result = await session.run(
                query2, {"habit_uid": daily_habit.uid, "badge_id": "habit_week_warrior"}
            )
            record = await result.single()

        assert record is not None
        assert record["badge_name"] == "Week Warrior"

    # ========================================================================
    # ERROR HANDLING TESTS
    # ========================================================================

    async def test_non_milestone_streak_ignored(
        self, achievement_service, event_bus, daily_habit, test_user_uid
    ):
        """Test that non-milestone streak lengths don't award badges."""
        # Try 15-day streak (not a milestone)
        event = HabitStreakMilestone(
            habit_uid=daily_habit.uid,
            user_uid=test_user_uid,
            streak_length=15,
            occurred_at=datetime.now(),
            milestone_name="custom",
        )

        await achievement_service.handle_habit_streak_milestone(event)

        # Verify NO AchievementEarned event was published
        achievement_events = [
            e for e in event_bus.get_event_history() if isinstance(e, AchievementEarned)
        ]
        assert len(achievement_events) == 0

        # Verify no badges in database
        badges_result = await achievement_service.get_user_badges(test_user_uid)
        assert badges_result.is_ok
        badges = badges_result.value
        assert len(badges) == 0

    # NOTE: test_missing_driver_warning removed - driver is now REQUIRED (fail-fast philosophy)

    # ========================================================================
    # QUERY METHODS TESTS
    # ========================================================================

    async def test_get_user_badges(
        self, achievement_service, daily_habit, test_user_uid, habit_backend, neo4j_driver
    ):
        """Test retrieving all badges earned by a user."""
        # Create second habit
        habit2 = Habit(
            uid="habit.daily_reading",
            user_uid=test_user_uid,
            ku_type=EntityType.HABIT,
            title="Daily Reading",
            description="Read for 20 minutes daily",
            habit_category=HabitCategory.LEARNING,
            status=HabitStatus.ACTIVE,
            recurrence_pattern=RecurrencePattern.DAILY,
        )
        result = await habit_backend.create(habit2)
        assert result.is_ok

        # Add :Habit secondary label so production Cypher MATCH (habit:Habit ...) works
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (h:Entity {uid: $uid}) SET h:Habit",
                uid=habit2.uid,
            )

        # Award badges for both habits
        event1 = HabitStreakMilestone(
            habit_uid=daily_habit.uid,
            user_uid=test_user_uid,
            streak_length=7,
            occurred_at=datetime.now(),
            milestone_name="one_week",
        )
        await achievement_service.handle_habit_streak_milestone(event1)

        event2 = HabitStreakMilestone(
            habit_uid=habit2.uid,
            user_uid=test_user_uid,
            streak_length=30,
            occurred_at=datetime.now(),
            milestone_name="one_month",
        )
        await achievement_service.handle_habit_streak_milestone(event2)

        # Get all user badges
        badges_result = await achievement_service.get_user_badges(test_user_uid)
        assert badges_result.is_ok
        badges = badges_result.value
        assert len(badges) == 2

        # Verify badge details
        badge_ids = {b["badge_id"] for b in badges}
        assert badge_ids == {"habit_week_warrior", "habit_month_master"}

    async def test_get_habit_badges(self, achievement_service, daily_habit, test_user_uid):
        """Test retrieving all badges unlocked by a specific habit."""
        # Award multiple badges for same habit
        milestones = [
            (7, "one_week"),
            (30, "one_month"),
            (100, "one_hundred"),
        ]

        for streak_length, milestone_name in milestones:
            event = HabitStreakMilestone(
                habit_uid=daily_habit.uid,
                user_uid=test_user_uid,
                streak_length=streak_length,
                occurred_at=datetime.now(),
                milestone_name=milestone_name,
            )
            await achievement_service.handle_habit_streak_milestone(event)

        # Get habit badges
        badges_result = await achievement_service.get_habit_badges(daily_habit.uid)
        assert badges_result.is_ok
        badges = badges_result.value
        assert len(badges) == 3

        # Verify badge tiers (bronze → silver → gold)
        tiers = [b["tier"] for b in badges]
        assert "bronze" in tiers
        assert "silver" in tiers
        assert "gold" in tiers
