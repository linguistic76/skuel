"""
Habit Event Handler Service
============================

Handles event-driven reactive logic for habit domain events.

Fire-and-forget handlers that analyze completion patterns, streak breaks,
missed habits, and achievement milestones.

Part of the HabitsService decomposition — separates event handling from
graph analytics (HabitsIntelligenceService) and absorbs HabitAchievementService.

Responsibilities:
- Timing/scheduling learning from completions (migrated from intelligence)
- Recovery insight generation on streak breaks (migrated from intelligence)
- Difficulty pattern detection on missed habits (migrated from intelligence)
- Achievement badge awarding on streak milestones (migrated from achievements)
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from core.constants import LearningLoop
from core.events import publish_event
from core.events.habit_events import (
    HabitCompleted,
    HabitMissed,
    HabitStreakBroken,
    HabitStreakMilestone,
)
from core.models.insight.persisted_insight import InsightImpact, InsightType, PersistedInsight
from core.models.type_hints import EntityUID, UserUID
from core.utils.decorators import with_error_handling
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS, NEO4J_EXCEPTIONS
from core.utils.logging import get_logger
from core.utils.neo4j_props import coerce_int, parse_neo4j_json
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports.domain_protocols import HabitsOperations
    from core.services.insight.insight_store import InsightStore
    from core.services.relationships import UnifiedRelationshipService


# ========================================================================
# MODULE-LEVEL HELPERS
# ========================================================================


def _calculate_recovery_difficulty(
    streak_length: int,
    days_since_completion: int,
) -> float:
    """Calculate recovery difficulty score (0.0 - 1.0).

    Factors:
    - Longer streaks are harder to restart (more emotional investment lost)
    - Longer gaps make it harder to resume (habit momentum lost)

    Args:
        streak_length: Length of the broken streak in days
        days_since_completion: Days since last habit completion

    Returns:
        Recovery difficulty from 0.0 (easy) to 1.0 (hard)
    """
    # Streak factor: logarithmic scaling (7-day streak = 0.3, 30-day = 0.5, 100-day = 0.7)
    streak_factor = min(1.0, math.log10(max(1, streak_length) + 1) / 2.5)

    # Gap factor: linear scaling capped at 14 days
    gap_factor = min(1.0, days_since_completion / 14.0)

    # Weighted combination (streak matters more than gap)
    difficulty = (streak_factor * 0.6) + (gap_factor * 0.4)

    return max(0.0, min(1.0, difficulty))


def _calculate_miss_severity(
    consecutive_misses: int,
    days_overdue: int,
) -> str:
    """Calculate miss severity based on pattern.

    Args:
        consecutive_misses: Number of consecutive misses
        days_overdue: Days since scheduled completion

    Returns:
        Severity level: "low", "medium", "high", "critical"
    """
    # Score based on consecutive misses (0-6 points)
    miss_score = min(6, consecutive_misses)

    # Score based on days overdue (0-4 points)
    overdue_score = min(4, days_overdue // 2)

    total_score = miss_score + overdue_score

    if total_score >= 8:
        return "critical"
    elif total_score >= 5:
        return "high"
    elif total_score >= 2:
        return "medium"
    else:
        return "low"


class HabitEventHandlerService:
    """Event-driven handlers for habit domain events.

    Fire-and-forget handlers that analyze completion patterns, streak breaks,
    missed habits, and achievement milestones.

    Handles:
    - HabitCompleted: Timing/scheduling learning + completion/quality/identity badges
    - HabitStreakBroken: Recovery difficulty calculation, knowledge impact
    - HabitMissed: Difficulty pattern detection, insight persistence
    - HabitStreakMilestone: Streak badge awarding (per-habit)

    Badge System:
        Two awarding paths, both persisted as Achievement nodes in Neo4j:

        1. Per-habit streak badges (via HabitStreakMilestone): 4 tiers at
           7/30/100/365 days. Linked to both User and Habit nodes.

        2. Cross-habit aggregate badges (via HabitCompleted): completion count,
           quality, and identity badges. Linked to User only (no single habit).

        Cross-domain badges (system strength, velocity, mastery) defined in
        AtomicHabitsBadges remain UI-computed — they require GoalAchieved and
        other cross-domain events not yet wired.
    """

    # Per-habit streak badges (triggered by HabitStreakMilestone)
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

    # Cross-habit aggregate badges (triggered by HabitCompleted)
    # Each entry: (badge_id, name, description, tier, stat_key, threshold)
    AGGREGATE_BADGES: ClassVar[list[tuple[str, str, str, str, str, int]]] = [
        # Completion count badges
        (
            "getting_started",
            "Getting Started",
            "Completed habits 10 times total",
            "bronze",
            "total_completions",
            10,
        ),
        (
            "habit_builder",
            "Habit Builder",
            "Completed habits 50 times total",
            "silver",
            "total_completions",
            50,
        ),
        (
            "habit_master",
            "Habit Master",
            "Completed habits 500 times total — relentless consistency",
            "platinum",
            "total_completions",
            500,
        ),
        # Quality badges
        (
            "quality_focused",
            "Quality Focused",
            "Logged 100 high-quality completions (4+ rating)",
            "gold",
            "high_quality_completions",
            100,
        ),
        # Identity badges
        (
            "identity_established",
            "Identity Established",
            "Cast 50 votes for a single identity — you've become who you wanted to be",
            "silver",
            "max_identity_votes",
            50,
        ),
        (
            "identity_master",
            "Identity Master",
            "Cast 200 votes for a single identity — absolute mastery",
            "gold",
            "max_identity_votes",
            200,
        ),
        (
            "multi_identity",
            "Renaissance Person",
            "Established 3 different identities simultaneously",
            "platinum",
            "established_identity_count",
            3,
        ),
    ]

    # Map stat_key → badge category for AchievementEarned events
    _STAT_CATEGORY: ClassVar[dict[str, str]] = {
        "total_completions": "completion",
        "high_quality_completions": "quality",
        "max_identity_votes": "identity",
        "established_identity_count": "identity",
    }

    def __init__(
        self,
        backend: HabitsOperations,
        relationship_service: UnifiedRelationshipService | None = None,
        insight_store: InsightStore | None = None,
        event_bus: Any = None,
    ) -> None:
        """Initialize habit event handler service.

        Args:
            backend: Backend for habit operations (REQUIRED)
            relationship_service: For querying related entities (optional)
            insight_store: For persisting event-driven insights (optional)
            event_bus: For publishing achievement events (optional)
        """
        self.backend = backend
        self.relationships = relationship_service
        self.insight_store = insight_store
        self.event_bus = event_bus
        self.logger = get_logger("skuel.services.habits.event_handler")

    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================

    async def handle_habit_completed(self, event: HabitCompleted) -> None:
        """Learn scheduling and timing patterns from habit completions.

        Tracks completion hour histogram and on-time rate via EMA,
        persisted on the Habit node. Fire-and-forget: errors logged,
        never propagated.

        Migrated from HabitsIntelligenceService.learn_from_completion().

        See: /docs/decisions/ADR-048
        """
        try:
            # 1. Get current habit to read existing learning state
            habit_result = await self.backend.get(event.habit_uid)
            if habit_result.is_error or not habit_result.value:
                return

            habit = habit_result.value

            # 2. Update completion hour histogram
            hour = event.occurred_at.hour
            hours_hist: dict[str, int] = parse_neo4j_json(
                getattr(habit, "completion_hours_json", None), default={}
            )

            hour_key = str(hour)
            hours_hist[hour_key] = hours_hist.get(hour_key, 0) + 1

            # 3. Calculate preferred hour (mode of histogram)
            from core.utils.sort_functions import make_dict_value_getter

            preferred_hour = int(max(hours_hist, key=make_dict_value_getter(hours_hist)))

            # 4. EMA on-time rate
            old_on_time_rate = getattr(habit, "learned_on_time_rate", None)
            if old_on_time_rate is None:
                old_on_time_rate = 1.0 if event.completed_on_time else 0.0
            on_time_value = 1.0 if event.completed_on_time else 0.0
            alpha = LearningLoop.EMA_ALPHA_HABIT_TIMING
            new_on_time_rate = alpha * on_time_value + (1 - alpha) * old_on_time_rate

            # 5. Increment completion count
            old_count = getattr(habit, "learned_completion_count", None) or 0
            new_count = old_count + 1

            # 6. Persist to Habit node
            await self.backend.update(
                event.habit_uid,
                {
                    "completion_hours_json": hours_hist,  # type: ignore[dict-item]
                    "learned_preferred_hour": preferred_hour,
                    "learned_on_time_rate": round(new_on_time_rate, 4),
                    "learned_completion_count": new_count,
                },
            )

            self.logger.info(
                f"Habit timing learning: preferred_hour={preferred_hour}, "
                f"on_time_rate={new_on_time_rate:.4f} (sample {new_count})",
                extra={
                    "habit_uid": event.habit_uid,
                    "user_uid": event.user_uid,
                    "preferred_hour": preferred_hour,
                    "on_time_rate": round(new_on_time_rate, 4),
                    "sample_count": new_count,
                    "event_type": "habit.timing.learned",
                },
            )

            # 7. Check and award aggregate badges (completion, quality, identity)
            await self._check_aggregate_badges(event.user_uid)

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                f"handle_habit_completed failed (non-fatal): {e}",
                extra={
                    "habit_uid": event.habit_uid,
                    "user_uid": event.user_uid,
                    "error": str(e),
                },
            )

    async def handle_habit_streak_broken(self, event: HabitStreakBroken) -> None:
        """Generate recovery insights when a habit streak breaks.

        Analyzes streak breaks to provide contextual recovery suggestions.
        Connects habit failures to knowledge reinforcement impact.

        Migrated from HabitsIntelligenceService.handle_habit_streak_broken().

        Args:
            event: HabitStreakBroken event with streak context

        Note:
            Fire-and-forget — errors are logged, never propagated.
        """
        try:
            # 1. Get habit details
            habit_result = await self.backend.get(event.habit_uid)
            if habit_result.is_error:
                self.logger.warning(f"Failed to get habit for streak analysis: {event.habit_uid}")
                return

            habit = habit_result.value
            if not habit:
                self.logger.warning(f"Habit not found for streak analysis: {event.habit_uid}")
                return

            # 2. Query knowledge reinforcement relationships
            knowledge_uids: list[str] = []
            if self.relationships is not None:
                # "knowledge" is the Habit→Knowledge config key (REINFORCES_KNOWLEDGE);
                # the service takes a method_key, not a raw RelationshipName.value.
                rel_result = await self.relationships.get_related_uids(
                    "knowledge",
                    EntityUID(event.habit_uid),
                )
                if rel_result.is_ok:
                    knowledge_uids = rel_result.value

            # 3. Calculate recovery metrics
            streak_length = event.streak_length
            days_since = event.days_since_last_completion

            recovery_difficulty = _calculate_recovery_difficulty(
                streak_length=streak_length,
                days_since_completion=days_since,
            )

            # 4. Determine recovery suggestion based on difficulty
            if recovery_difficulty < 0.3:
                suggestion = "Quick restart - your momentum is still fresh"
            elif recovery_difficulty < 0.6:
                suggestion = "Gentle restart - consider a lighter version of this habit"
            else:
                suggestion = "Fresh start - rebuild gradually with small wins"

            # 5. Log structured insights
            self.logger.info(
                f"Habit streak broken: {habit.title}",
                extra={
                    "habit_uid": event.habit_uid,
                    "user_uid": event.user_uid,
                    "streak_length": streak_length,
                    "days_since_last": days_since,
                    "recovery_difficulty": round(recovery_difficulty, 2),
                    "knowledge_areas_affected": len(knowledge_uids),
                    "recovery_suggestion": suggestion,
                    "event_type": "habit.streak_broken.analyzed",
                },
            )

            # Log knowledge impact if habit reinforced knowledge
            if knowledge_uids:
                self.logger.info(
                    f"Knowledge reinforcement interrupted for {len(knowledge_uids)} areas",
                    extra={
                        "habit_uid": event.habit_uid,
                        "knowledge_uids": knowledge_uids[:5],  # Log first 5
                        "event_type": "habit.knowledge_impact",
                    },
                )

            # Persist learning state (ADR-048)
            await self.backend.update(
                event.habit_uid,
                {
                    "learned_recovery_difficulty": round(recovery_difficulty, 2),
                    "last_streak_length": streak_length,
                    "last_break_date": event.occurred_at.isoformat(),
                },
            )

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                f"handle_habit_streak_broken failed (non-fatal): {e}",
                extra={
                    "habit_uid": event.habit_uid,
                    "user_uid": event.user_uid,
                    "error": str(e),
                },
            )

    async def handle_habit_missed(self, event: HabitMissed) -> None:
        """Track habit difficulty patterns when habits are missed.

        Detects difficulty patterns when habits are missed. Unlike
        streak_broken (fires once), this fires for each missed occurrence,
        enabling pattern detection.

        Migrated from HabitsIntelligenceService.handle_habit_missed().

        Args:
            event: HabitMissed event with miss context

        Note:
            Fire-and-forget — errors are logged, never propagated.
        """
        try:
            # 1. Get habit details
            habit_result = await self.backend.get(event.habit_uid)
            if habit_result.is_error:
                self.logger.warning(f"Failed to get habit for miss analysis: {event.habit_uid}")
                return

            habit = habit_result.value
            if not habit:
                self.logger.warning(f"Habit not found for miss analysis: {event.habit_uid}")
                return

            # 2. Analyze consecutive misses for difficulty detection
            consecutive_misses = event.consecutive_misses
            days_overdue = event.days_overdue

            # 3. Calculate difficulty indicators
            is_difficult = consecutive_misses >= 3
            is_very_difficult = consecutive_misses >= 5
            severity = _calculate_miss_severity(consecutive_misses, days_overdue)

            # 4. Generate difficulty assessment
            if is_very_difficult:
                difficulty_assessment = "very_difficult"
                suggestion = "Consider reducing frequency or simplifying this habit"
            elif is_difficult:
                difficulty_assessment = "difficult"
                suggestion = "Try a smaller version of this habit to rebuild momentum"
            elif consecutive_misses >= 2:
                difficulty_assessment = "challenging"
                suggestion = "Set a reminder or link this habit to an existing routine"
            else:
                difficulty_assessment = "normal"
                suggestion = None

            # 5. Log structured insights
            self.logger.info(
                f"Habit missed: {habit.title}",
                extra={
                    "habit_uid": event.habit_uid,
                    "user_uid": event.user_uid,
                    "consecutive_misses": consecutive_misses,
                    "days_overdue": days_overdue,
                    "severity": severity,
                    "difficulty_assessment": difficulty_assessment,
                    "frequency": habit.recurrence_pattern
                    if habit.recurrence_pattern
                    else "unknown",
                    "event_type": "habit.missed.analyzed",
                },
            )

            # Log difficulty insight for significant patterns
            if is_difficult:
                self.logger.info(
                    f"Habit difficulty detected: {consecutive_misses} consecutive misses",
                    extra={
                        "habit_uid": event.habit_uid,
                        "user_uid": event.user_uid,
                        "consecutive_misses": consecutive_misses,
                        "difficulty_assessment": difficulty_assessment,
                        "suggestion": suggestion,
                        "event_type": "habit.difficulty.detected",
                    },
                )

                # Persist insight to InsightStore
                if self.insight_store:
                    impact = InsightImpact.HIGH if is_very_difficult else InsightImpact.MEDIUM
                    insight = PersistedInsight(
                        uid=PersistedInsight.generate_uid(
                            InsightType.DIFFICULTY_PATTERN, EntityUID(event.habit_uid)
                        ),
                        user_uid=event.user_uid,
                        insight_type=InsightType.DIFFICULTY_PATTERN,
                        domain="habits",
                        title=f"{habit.title}: Difficulty Detected",
                        description=f"You've missed this habit {consecutive_misses} times in a row.",
                        confidence=0.85,
                        impact=impact,
                        entity_uid=EntityUID(event.habit_uid),
                        recommended_actions=[
                            {"action": "Adjust frequency", "rationale": suggestion}
                        ]
                        if suggestion
                        else [],
                        supporting_data={
                            "consecutive_misses": consecutive_misses,
                            "days_overdue": days_overdue,
                            "severity": severity,
                            "difficulty_assessment": difficulty_assessment,
                        },
                    )
                    create_result = await self.insight_store.create_insight(insight)
                    if create_result.is_error:
                        self.logger.warning(
                            f"Failed to persist difficulty insight: {create_result.error}"
                        )

            # Persist learned difficulty to Habit node (ADR-048)
            await self.backend.update(
                event.habit_uid,
                {
                    "learned_difficulty_level": difficulty_assessment,
                    "miss_pattern_updated_at": datetime.now().isoformat(),
                },
            )

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                f"handle_habit_missed failed (non-fatal): {e}",
                extra={
                    "habit_uid": event.habit_uid,
                    "user_uid": event.user_uid,
                    "error": str(e),
                },
            )

    async def handle_habit_streak_milestone(self, event: HabitStreakMilestone) -> None:
        """Award achievement badge when a habit reaches a streak milestone.

        Migrated from HabitAchievementService.handle_habit_streak_milestone().

        Milestone badges:
        - 7 days: Week Warrior (bronze)
        - 30 days: Month Master (silver)
        - 100 days: Century Champion (gold)
        - 365 days: Year Legend (platinum)

        Args:
            event: HabitStreakMilestone event containing streak details

        Note:
            Fire-and-forget — errors are logged, never propagated.
        """
        try:
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
                    badge_id=badge_info["badge_id"],
                    badge_name=badge_info["name"],
                    badge_tier=badge_info["tier"],
                    badge_category="streak",
                    habit_uid=event.habit_uid,
                    streak_length=streak_length,
                )
                await publish_event(self.event_bus, achievement_event, self.logger)

        except (*NEO4J_EXCEPTIONS, *DATA_CONVERSION_EXCEPTIONS) as e:
            self.logger.error(
                f"handle_habit_streak_milestone failed (non-fatal): {e}",
                extra={
                    "habit_uid": event.habit_uid,
                    "user_uid": event.user_uid,
                    "error": str(e),
                },
            )

    # ========================================================================
    # QUERY METHODS (badge queries, migrated from HabitAchievementService)
    # ========================================================================

    @with_error_handling("get_user_badges", error_type="database", uid_param="user_uid")
    async def get_user_badges(self, user_uid: UserUID) -> Result[list[dict]]:
        """Get all badges earned by a user.

        Args:
            user_uid: User identifier

        Returns:
            Result containing list of badge dicts with details
        """
        result = await self.backend.get_user_badges(user_uid)
        if result.is_error:
            return result

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
            for record in result.value
        ]

        return Result.ok(badges)

    @with_error_handling("get_habit_badges", error_type="database", uid_param="habit_uid")
    async def get_habit_badges(self, habit_uid: str) -> Result[list[dict]]:
        """Get all badges unlocked by a specific habit.

        Args:
            habit_uid: Habit identifier

        Returns:
            Result containing list of badge dicts
        """
        result = await self.backend.get_habit_badges(habit_uid)
        if result.is_error:
            return result

        badges = [
            {
                "badge_id": record["badge_id"],
                "badge_name": record["badge_name"],
                "description": record["description"],
                "tier": record["tier"],
            }
            for record in result.value
        ]

        return Result.ok(badges)

    # ========================================================================
    # INTERNAL HELPERS (badge operations, migrated from HabitAchievementService)
    # ========================================================================

    async def _check_badge_already_earned(
        self, user_uid: UserUID, habit_uid: str, badge_id: str
    ) -> bool:
        """Check if user has already earned this badge for this habit."""
        result = await self.backend.check_badge_already_earned(user_uid, habit_uid, badge_id)
        if result.is_error:
            self.logger.error(f"Failed to check badge: {result.error}")
            return False
        return result.value

    async def _award_badge(
        self,
        user_uid: UserUID,
        habit_uid: str,
        badge_info: dict,
        streak_length: int,
        occurred_at: datetime,
    ) -> Result[bool]:
        """Create achievement record and link to user and habit (per-habit badges)."""
        return await self.backend.award_badge(
            user_uid=user_uid,
            habit_uid=habit_uid,
            badge_id=badge_info["badge_id"],
            badge_name=badge_info["name"],
            badge_description=badge_info["description"],
            badge_tier=badge_info["tier"],
            streak_length=streak_length,
            occurred_at=occurred_at.isoformat(),
        )

    async def _check_aggregate_badges(self, user_uid: UserUID) -> None:
        """Check and award cross-habit aggregate badges.

        Queries aggregated stats (total completions, high-quality count,
        identity votes) and awards any newly-crossed thresholds.

        Fire-and-forget: errors are logged, never propagated.
        """
        # 1. Get aggregated stats
        stats_result = await self.backend.get_user_badge_stats(user_uid)
        if stats_result.is_error:
            self.logger.warning(f"Failed to get badge stats for {user_uid}: {stats_result.error}")
            return

        stats = stats_result.value
        now_iso = datetime.now().isoformat()

        # 2. Check each aggregate badge threshold
        for badge_id, name, description, tier, stat_key, threshold in self.AGGREGATE_BADGES:
            current_value = coerce_int(stats.get(stat_key))
            if current_value < threshold:
                continue

            # 3. Check if already earned
            already_result = await self.backend.check_user_badge_earned(user_uid, badge_id)
            if already_result.is_error:
                self.logger.warning(f"Failed to check badge {badge_id}: {already_result.error}")
                continue
            if already_result.value:
                continue

            # 4. Award the badge
            category = self._STAT_CATEGORY.get(stat_key, "completion")
            result = await self.backend.award_user_badge(
                user_uid=user_uid,
                badge_id=badge_id,
                badge_name=name,
                badge_description=description,
                badge_tier=tier,
                badge_category=category,
                threshold_value=threshold,
                occurred_at=now_iso,
            )

            if result.is_ok:
                self.logger.info(
                    f"Awarded aggregate badge '{name}' ({category}) to user {user_uid} "
                    f"(threshold: {threshold}, actual: {current_value})"
                )

                # 5. Publish AchievementEarned event
                from core.events.habit_events import AchievementEarned

                achievement_event = AchievementEarned(
                    user_uid=user_uid,
                    badge_id=badge_id,
                    badge_name=name,
                    badge_tier=tier,
                    badge_category=category,
                    threshold_value=threshold,
                )
                await publish_event(self.event_bus, achievement_event, self.logger)
