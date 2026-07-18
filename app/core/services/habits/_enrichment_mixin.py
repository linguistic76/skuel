"""
Enrichment Mixin — HabitsService
==================================

Analytics delegates and enriched data views for habit entities.

Part of habits_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums import EntityStatus
from core.models.type_hints import UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.habit.habit import Habit


class _EnrichmentMixin:
    """
    Analytics delegates and enriched data views for HabitsService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by HabitsService.__init__
    intelligence: Any
    relationships: Any

    # ========================================================================
    # ANALYTICS - Delegates to HabitsIntelligenceService
    # ========================================================================

    async def get_habit_analytics(
        self,
        habit_uid: str,
        _period: str = "month",
        _include_predictions: bool = False,
    ) -> Result[dict[str, Any]]:
        """
        Get analytics for a specific habit.

        Delegates to HabitsIntelligenceService.analyze_habit_performance().

        Args:
            habit_uid: UID of the habit
            _period: Placeholder - period filtering not yet implemented
            _include_predictions: Placeholder - AI predictions not yet implemented

        Returns:
            Result with analytics data including performance metrics,
            knowledge reinforcement, and goal support analysis
        """
        return await self.intelligence.analyze_habit_performance(habit_uid)

    async def get_habits_summary_analytics(
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """
        Get summary analytics for all user habits.

        Delegates to HabitsIntelligenceService.get_performance_analytics().

        Args:
            user_uid: User UID to get analytics for
            period_days: Number of days for analytics period (default: 30)

        Returns:
            Result with summary analytics including totals, averages, and at-risk counts
        """
        return await self.intelligence.get_performance_analytics(user_uid, period_days)

    async def get_habit_trends(
        self, user_uid: UserUID, time_range: str = "30d"
    ) -> Result[dict[str, Any]]:
        """
        Get habit completion trends for a user.

        Calculates trend data from habit metrics over time.

        Args:
            user_uid: User UID to get trends for
            time_range: Time range for trends (e.g., "7d", "30d", "90d")

        Returns:
            Result with trend data including streak trends and consistency patterns
        """
        from core.utils.validation_helpers import parse_timeframe_days

        days = parse_timeframe_days(time_range, default=30)

        # Get performance analytics which includes trend-relevant data
        analytics_result = await self.intelligence.get_performance_analytics(user_uid, days)
        if analytics_result.is_error:
            return Result.fail(analytics_result)

        analytics = analytics_result.value

        # Build trend response from analytics
        return Result.ok(
            {
                "user_uid": user_uid,
                "time_range": time_range,
                "period_days": days,
                "trends": {
                    "total_habits": analytics.get("total_habits", 0),
                    "active_habits": analytics.get("active_habits", 0),
                    "habits_with_streak": analytics.get("habits_with_streak", 0),
                    "at_risk_habits": analytics.get("at_risk_habits", 0),
                    "avg_consistency": analytics.get("avg_consistency", 0.0),
                    "avg_streak": analytics.get("avg_streak", 0.0),
                },
                "summary": {
                    "consistency_trend": "stable"
                    if analytics.get("avg_consistency", 0) >= 0.5
                    else "declining",
                    "streak_health": "healthy"
                    if analytics.get("habits_with_streak", 0) > analytics.get("at_risk_habits", 0)
                    else "at_risk",
                },
            }
        )

    # ========================================================================
    # ENRICHMENT METHODS (Moved from routes - November 28, 2025)
    # ========================================================================
    # These methods fetch graph relationships and create enriched views.
    # Previously inline in habits_api.py routes, now properly in service layer.

    async def get_enriched_learning_summary(self, habit: Habit) -> Result[dict[str, Any]]:
        """
        Get learning summary with relationship data from graph.

        Args:
            habit: Habit domain model (entity_type='habit')

        Returns:
            Result containing enriched learning summary dict
        """
        # Fetch knowledge relationships
        knowledge_result = await self.relationships.get_related_uids("knowledge", habit.uid)
        knowledge_uids = knowledge_result.value if knowledge_result.is_ok else []

        # Fetch goal relationships
        goals_result = await self.relationships.get_related_uids("supported_goals", habit.uid)
        goal_uids = goals_result.value if goals_result.is_ok else []

        # Fetch principle relationships
        principles_result = await self.relationships.get_related_uids("principles", habit.uid)
        principle_uids = principles_result.value if principles_result.is_ok else []

        # Learning step relationships - not in config, return empty for now
        step_uids: list[str] = []

        # Integration level calculation
        integration_count = 0
        if habit.source_path_step_uid:
            integration_count += 3
        if habit.is_identity_habit:
            integration_count += 2

        if integration_count == 0:
            integration_level = "standalone"
        elif integration_count <= 2:
            integration_level = "basic"
        elif integration_count <= 5:
            integration_level = "moderate"
        elif integration_count <= 9:
            integration_level = "high"
        else:
            integration_level = "comprehensive"

        polarity_value = habit.polarity.value if habit.polarity else "neutral"
        category_value = habit.habit_category.value if habit.habit_category else "other"
        difficulty_value = habit.habit_difficulty.value if habit.habit_difficulty else "moderate"

        enriched = {
            "uid": habit.uid,
            "name": habit.title,
            "category": category_value,
            "polarity": polarity_value,
            "difficulty": difficulty_value,
            "linked_knowledge_count": len(knowledge_uids),
            "knowledge_uids": knowledge_uids,
            "linked_goal_count": len(goal_uids),
            "goal_uids": goal_uids,
            "linked_principle_count": len(principle_uids),
            "principle_uids": principle_uids,
            "is_curriculum_habit": habit.source_path_step_uid is not None,
            "source_step_uid": habit.source_path_step_uid,
            "reinforces_step_count": len(step_uids),
            "step_uids": step_uids,
            "practice_type": habit.curriculum_practice_type,
            "is_identity_habit": habit.is_identity_habit,
            "reinforces_identity": habit.reinforces_identity,
            "identity_votes_cast": habit.identity_votes_cast,
            "current_streak": habit.current_streak,
            "best_streak": habit.best_streak,
            "total_completions": habit.total_completions,
            "success_rate": habit.success_rate,
            "learning_integration_level": integration_level,
        }

        return Result.ok(enriched)

    def get_enriched_curriculum_metadata(self, habit: Habit) -> Result[dict[str, Any]]:
        """
        Get curriculum metadata with relationship data from graph.

        Args:
            habit: Habit domain model (entity_type='habit')

        Returns:
            Result containing curriculum metadata dict
        """
        # Learning step relationships - not in config, return empty for now
        step_uids: list[str] = []

        enriched = {
            "uid": habit.uid,
            "name": habit.title,
            "is_curriculum_habit": habit.source_path_step_uid is not None,
            "source_step_uid": habit.source_path_step_uid,
            "reinforces_step_uids": step_uids,
            "reinforces_step_count": len(step_uids),
            "practice_type": habit.curriculum_practice_type,
            "supports_multiple_steps": len(step_uids) > 1,
        }
        return Result.ok(enriched)

    async def get_enriched_prerequisite_metadata(self, habit: Habit) -> Result[dict[str, Any]]:
        """
        Get prerequisite chain metadata with relationship data from graph.

        Args:
            habit: Habit domain model (entity_type='habit')

        Returns:
            Result containing prerequisite metadata dict
        """
        # Fetch prerequisite relationships
        prereqs_result = await self.relationships.get_related_uids("prerequisite_habits", habit.uid)
        prerequisite_uids = prereqs_result.value if prereqs_result.is_ok else []

        difficulty_value = habit.habit_difficulty.value if habit.habit_difficulty else "moderate"
        status_value = habit.status.value if habit.status else "active"

        enriched = {
            "uid": habit.uid,
            "name": habit.title,
            "has_prerequisites": len(prerequisite_uids) > 0,
            "prerequisite_uids": prerequisite_uids,
            "prerequisite_count": len(prerequisite_uids),
            "is_foundational": len(prerequisite_uids) == 0,
            "difficulty": difficulty_value,
            "is_active": status_value == EntityStatus.ACTIVE,
        }
        return Result.ok(enriched)
