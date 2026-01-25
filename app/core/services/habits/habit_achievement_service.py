"""
Habit Achievement Service
=========================

Handles achievement badge awarding based on habit streak milestones.

Responsibilities:
- Listen to HabitStreakMilestone events
- Award achievement badges for streak milestones
- Track user achievements in Neo4j
- Publish AchievementEarned events

Version: 1.0.0
Date: 2025-11-05
"""

from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from core.events import publish_event
from core.events.habit_events import HabitStreakMilestone
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver


class HabitAchievementService:
    """
    Achievement badge service for habit streak milestones.

    Handles automatic achievement badge awarding when habits reach
    streak milestones, using Neo4j to track earned badges.

    Event-Driven Architecture (Phase 4):
    - Subscribes to HabitStreakMilestone events
    - Awards badges based on milestone thresholds
    - Publishes AchievementEarned events
    - Stores achievement records in Neo4j


    Source Tag: "habit_achievement_explicit"
    - Format: "habit_achievement_explicit" for user-created relationships
    - Format: "habit_achievement_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    """

    # Achievement badge definitions
    MILESTONE_BADGES: ClassVar[dict[int, dict[str, str]]] = {
        7: {
            "badge_id": "habit_week_warrior",
            "name": "Week Warrior",
            "description": "Maintained a habit for 7 consecutive days",
            "tier": "bronze",
        },
        30: {
            "badge_id": "habit_month_master",
            "name": "Month Master",
            "description": "Maintained a habit for 30 consecutive days",
            "tier": "silver",
        },
        100: {
            "badge_id": "habit_century_champion",
            "name": "Century Champion",
            "description": "Maintained a habit for 100 consecutive days",
            "tier": "gold",
        },
        365: {
            "badge_id": "habit_year_legend",
            "name": "Year Legend",
            "description": "Maintained a habit for 365 consecutive days",
            "tier": "platinum",
        },
    }

    def __init__(
        self,
        driver: "AsyncDriver",
        event_bus=None,
    ) -> None:
        """
        Initialize habit achievement service.

        Args:
            driver: Neo4j driver for achievement storage (REQUIRED)
            event_bus: Optional event bus for publishing achievement events

        Migration Note (January 2026 - Fail-Fast):
            Made driver REQUIRED - achievements need database access.
        """
        self.driver = driver
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.habits.achievements")

    # ========================================================================
    # EVENT HANDLERS (Phase 4: Event-Driven Architecture)
    # ========================================================================

    async def handle_habit_streak_milestone(self, event: HabitStreakMilestone) -> None:
        """
        Award achievement badge when a habit reaches a streak milestone.

        This handler implements event-driven achievement tracking,
        awarding badges for streak milestones:
        - 7 days: Week Warrior (bronze)
        - 30 days: Month Master (silver)
        - 100 days: Century Champion (gold)
        - 365 days: Year Legend (platinum)

        When a milestone is reached:
        1. Check if achievement already earned
        2. Award badge if new achievement
        3. Create achievement record in Neo4j
        4. Publish AchievementEarned event

        Args:
            event: HabitStreakMilestone event containing streak details

        Raises:
            Exception: Propagates exceptions after logging.
        """
        streak_length = event.streak_length

        # Check if this streak length earns a badge
        if streak_length not in self.MILESTONE_BADGES:
            self.logger.debug(
                f"Streak length {streak_length} does not correspond to a badge milestone"
            )
            return

        badge_info = self.MILESTONE_BADGES[streak_length]

        self.logger.info(
            f"Awarding badge '{badge_info['name']}' to user {event.user_uid} "
            f"for habit {event.habit_uid} (streak: {streak_length} days)"
        )

        # Check if user already has this badge for this habit
        already_earned = await self._check_badge_already_earned(
            event.user_uid, event.habit_uid, badge_info["badge_id"]
        )

        if already_earned:
            self.logger.info(
                f"User {event.user_uid} already has badge {badge_info['badge_id']} "
                f"for habit {event.habit_uid}"
            )
            return

        # Award the badge
        result = await self._award_badge(
            user_uid=event.user_uid,
            habit_uid=event.habit_uid,
            badge_info=badge_info,
            streak_length=streak_length,
            occurred_at=event.occurred_at,
        )

        if result.is_ok:
            self.logger.info(
                f"Successfully awarded badge '{badge_info['name']}' to user {event.user_uid}"
            )

            # Publish AchievementEarned event
            from core.events.habit_events import AchievementEarned

            achievement_event = AchievementEarned(
                user_uid=event.user_uid,
                habit_uid=event.habit_uid,
                badge_id=badge_info["badge_id"],
                badge_name=badge_info["name"],
                badge_tier=badge_info["tier"],
                streak_length=streak_length,
                occurred_at=datetime.now(),
            )
            await publish_event(self.event_bus, achievement_event, self.logger)

    async def _check_badge_already_earned(
        self, user_uid: str, habit_uid: str, badge_id: str
    ) -> bool:
        """
        Check if user has already earned this badge for this habit.

        Args:
            user_uid: User identifier
            habit_uid: Habit identifier
            badge_id: Badge identifier

        Returns:
            True if badge already earned, False otherwise
        """
        query = """
        MATCH (user:User {uid: $user_uid})-[r:EARNED_BADGE]->(badge:Achievement {badge_id: $badge_id})
        WHERE r.habit_uid = $habit_uid
        RETURN count(r) > 0 as already_earned
        """

        async with self.driver.session() as session:
            result = await session.run(
                query,
                {
                    "user_uid": user_uid,
                    "habit_uid": habit_uid,
                    "badge_id": badge_id,
                },
            )
            record = await result.single()

        return record["already_earned"] if record else False

    async def _award_badge(
        self,
        user_uid: str,
        habit_uid: str,
        badge_info: dict,
        streak_length: int,
        occurred_at: datetime,
    ) -> Result[bool]:
        """
        Create achievement record and link to user.

        Args:
            user_uid: User earning the badge
            habit_uid: Habit that earned the badge
            badge_info: Badge details (id, name, description, tier)
            streak_length: Streak length that triggered the badge
            occurred_at: When the milestone was reached

        Returns:
            Result[bool] indicating success/failure
        """
        query = """
        // Get or create achievement badge
        MERGE (badge:Achievement {badge_id: $badge_id})
        ON CREATE SET
            badge.name = $badge_name,
            badge.description = $badge_description,
            badge.tier = $badge_tier,
            badge.created_at = datetime()

        // Get user and habit
        WITH badge
        MATCH (user:User {uid: $user_uid})
        MATCH (habit:Habit {uid: $habit_uid})

        // Create EARNED_BADGE relationship
        CREATE (user)-[r:EARNED_BADGE {
            earned_at: datetime($occurred_at),
            streak_length: $streak_length,
            habit_uid: $habit_uid
        }]->(badge)

        // Also link achievement to the habit for context
        MERGE (habit)-[:UNLOCKED_ACHIEVEMENT]->(badge)

        RETURN badge.badge_id as badge_id
        """
        async with self.driver.session() as session:
            result = await session.run(
                query,
                {
                    "user_uid": user_uid,
                    "habit_uid": habit_uid,
                    "badge_id": badge_info["badge_id"],
                    "badge_name": badge_info["name"],
                    "badge_description": badge_info["description"],
                    "badge_tier": badge_info["tier"],
                    "streak_length": streak_length,
                    "occurred_at": occurred_at.isoformat(),
                },
            )
            await result.single()

        return Result.ok(True)

    # ========================================================================
    # QUERY METHODS
    # ========================================================================

    @with_error_handling("get_user_badges", error_type="database", uid_param="user_uid")
    async def get_user_badges(self, user_uid: str) -> Result[list[dict]]:
        """
        Get all badges earned by a user.

        Args:
            user_uid: User identifier

        Returns:
            Result containing list of badge dicts with details
        """
        query = """
        MATCH (user:User {uid: $user_uid})-[r:EARNED_BADGE]->(badge:Achievement)
        RETURN badge.badge_id as badge_id,
               badge.name as badge_name,
               badge.description as description,
               badge.tier as tier,
               r.earned_at as earned_at,
               r.streak_length as streak_length,
               r.habit_uid as habit_uid
        ORDER BY r.earned_at DESC
        """

        async with self.driver.session() as session:
            result = await session.run(query, {"user_uid": user_uid})
            records = await result.data()

        badges = [
            {
                "badge_id": record["badge_id"],
                "badge_name": record["badge_name"],
                "description": record["description"],
                "tier": record["tier"],
                "earned_at": record["earned_at"],
                "streak_length": record["streak_length"],
                "habit_uid": record["habit_uid"],
            }
            for record in records
        ]

        return Result.ok(badges)

    @with_error_handling("get_habit_badges", error_type="database", uid_param="habit_uid")
    async def get_habit_badges(self, habit_uid: str) -> Result[list[dict]]:
        """
        Get all badges unlocked by a specific habit.

        Args:
            habit_uid: Habit identifier

        Returns:
            Result containing list of badge dicts
        """
        query = """
        MATCH (habit:Habit {uid: $habit_uid})-[:UNLOCKED_ACHIEVEMENT]->(badge:Achievement)
        RETURN badge.badge_id as badge_id,
               badge.name as badge_name,
               badge.description as description,
               badge.tier as tier
        ORDER BY badge.tier
        """

        async with self.driver.session() as session:
            result = await session.run(query, {"habit_uid": habit_uid})
            records = await result.data()

        badges = [
            {
                "badge_id": record["badge_id"],
                "badge_name": record["badge_name"],
                "description": record["description"],
                "tier": record["tier"],
            }
            for record in records
        ]

        return Result.ok(badges)
