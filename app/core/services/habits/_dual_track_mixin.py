"""
Dual-Track Mixin — HabitsIntelligenceService
=============================================

Dual-track consistency assessment and ZPD knowledge signals:
  assess_consistency_dual_track, _calculate_system_consistency,
  _consistency_level_to_score, _generate_consistency_gap_insights,
  _generate_consistency_gap_recommendations, get_zpd_knowledge_signals.

Part of habits_intelligence_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums.activity_enums import ConsistencyLevel
from core.models.type_hints import UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.habit.habit import Habit
    from core.models.shared.dual_track import DualTrackResult
    from core.services.cross_domain import CrossDomainQueryService


class _DualTrackMixin:
    """
    Dual-track assessment and ZPD bridge methods for HabitsIntelligenceService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by HabitsIntelligenceService.__init__
    orchestrator: Any
    relationships: Any
    cross_domain_query: CrossDomainQueryService
    logger: Any
    # Provided by BaseAnalyticsService on the composed service.
    _store_dual_track_checkin: Any

    async def assess_consistency_dual_track(
        self,
        habit_uid: str,
        user_uid: UserUID,
        user_consistency_level: ConsistencyLevel,
        user_evidence: str,
        user_reflection: str | None = None,
    ) -> Result[DualTrackResult[ConsistencyLevel]]:
        """
        Dual-track consistency assessment for habits.

        Compares user self-assessment (vision) with system measurement (action)
        to generate perception gap analysis and insights.

        This implements SKUEL's core philosophy:
        "The user's vision is understood via the words they use to communicate,
        the UserContext is determined via user's actions."

        Uses BaseIntelligenceService._dual_track_assessment() template (ADR-030).

        Args:
            habit_uid: Habit UID to assess
            user_uid: User making the assessment
            user_consistency_level: User's self-reported consistency level
            user_evidence: User's evidence for their assessment
            user_reflection: Optional reflection on their consistency

        Returns:
            Result[DualTrackResult[ConsistencyLevel]] with dual-track analysis

        Example:
            >>> from core.models.enums.activity_enums import ConsistencyLevel
            >>> result = await service.assess_consistency_dual_track(
            ...     habit_uid="habit.morning-meditation",
            ...     user_uid="user_mike",
            ...     user_consistency_level=ConsistencyLevel.CONSISTENT,
            ...     user_evidence="I meditate most mornings",
            ...     user_reflection="Sometimes skip on weekends",
            ... )
            >>> if result.is_ok:
            ... dual_track = result.value
            ... print(f"Gap: {dual_track.perception_gap:.0%}")
        """
        return await self._dual_track_assessment(  # type: ignore[attr-defined]
            uid=habit_uid,
            user_uid=user_uid,
            user_level=user_consistency_level,
            user_evidence=user_evidence,
            user_reflection=user_reflection,
            system_calculator=self._calculate_system_consistency,
            level_scorer=self._consistency_level_to_score,
            entity_type="habit",
            insight_generator=self._generate_consistency_gap_insights,
            recommendation_generator=self._generate_consistency_gap_recommendations,
            store_callback=self._store_dual_track_checkin,
        )

    async def _calculate_system_consistency(  # skuel-lint: disable=SKUEL029 -- dual-track system_calculator callback: typed Awaitable + awaited by base_analytics_service
        self, habit: Habit, _user_uid: UserUID
    ) -> tuple[ConsistencyLevel, float, list[str]]:
        """
        Calculate system consistency from habit metrics.

        Examines:
        - Success rate (completions / attempts)
        - Current streak
        - Best streak
        - Recent completion pattern

        Args:
            habit: The Habit entity
            _user_uid: User UID (unused in habit-specific calculation)

        Returns:
            Tuple of (ConsistencyLevel, score, evidence_list)
        """
        evidence: list[str] = []

        # Primary metric: success rate
        success_rate = habit.success_rate  # 0.0-1.0
        evidence.append(f"Success rate: {success_rate * 100:.0f}%")

        # Streak metrics
        current_streak = habit.current_streak
        best_streak = habit.best_streak

        if current_streak > 0:
            evidence.append(f"Current streak: {current_streak} days")
        if best_streak > 0:
            evidence.append(f"Best streak: {best_streak} days")

        # Calculate streak factor (bonus for active streaks)
        streak_factor = 0.0
        if current_streak >= 21:  # 3 weeks = established habit
            streak_factor = 0.2
            evidence.append("Habit is well-established (21+ day streak)")
        elif current_streak >= 7:  # 1 week = building
            streak_factor = 0.1
            evidence.append("Building momentum (7+ day streak)")
        elif current_streak == 0 and habit.total_completions > 0:
            streak_factor = -0.1
            evidence.append("Streak recently broken")

        # Calculate consistency score from Habit model
        consistency_score = habit.calculate_consistency_score()

        # Final score: weighted combination
        score = min(1.0, (success_rate * 0.6) + (consistency_score * 0.3) + streak_factor + 0.1)

        # Adjust for very new habits (give benefit of doubt)
        if habit.total_completions < 5:
            score = max(score, 0.5)  # At least "building" for new habits
            evidence.append("Early stage habit - limited data")

        # Convert score to level
        system_level = ConsistencyLevel.from_score(score)

        return system_level, score, evidence

    def _consistency_level_to_score(self, level: ConsistencyLevel) -> float:
        """Convert ConsistencyLevel to numeric score (0.0-1.0)."""
        return level.to_score()

    def _generate_consistency_gap_insights(
        self, direction: str, gap: float, entity_name: str
    ) -> list[str]:
        """Generate consistency-specific gap insights."""
        insights: list[str] = []

        if direction == "aligned":
            insights.append(
                f"Your self-perception of consistency with '{entity_name}' matches your tracking data. "
                "This indicates accurate self-awareness about your habit patterns."
            )
        elif direction == "user_higher":
            insights.append(
                f"Your self-assessment is more positive than your habit data suggests "
                f"(gap: {gap:.0%}). Consider: Are you remembering completions that weren't tracked?"
            )
            if gap > 0.3:
                insights.append(
                    "This significant gap may indicate memory bias - we often remember doing things "
                    "more consistently than we actually did. The data helps ground our perception."
                )
        else:  # system_higher
            insights.append(
                f"Your habit data shows stronger consistency than you perceive (gap: {gap:.0%}). "
                "You're doing better than you think!"
            )
            if gap > 0.3:
                insights.append(
                    "Consider why you underestimate your consistency - "
                    "focusing on misses rather than successes can skew perception."
                )

        return insights

    def _generate_consistency_gap_recommendations(
        self, direction: str, _gap: float, entity: Any, evidence: list[str]
    ) -> list[str]:
        """Generate consistency-specific gap recommendations."""
        recommendations: list[str] = []
        habit = entity

        if direction == "aligned":
            recommendations.append(
                "Continue your current approach - your self-awareness is accurate."
            )
            if habit.current_streak > 0:
                recommendations.append(
                    f"Protect your {habit.current_streak}-day streak - momentum matters!"
                )
        elif direction == "user_higher":
            recommendations.append(
                "Trust the data - it provides an objective view of your consistency."
            )
            recommendations.append(
                "Consider setting reminders to help bridge the gap between intention and action."
            )
            if any("streak" in e.lower() and "broken" in e.lower() for e in evidence):
                recommendations.append(
                    "Focus on rebuilding your streak with small, achievable completions."
                )
        else:  # system_higher
            recommendations.append(
                "Celebrate your consistency - you're more disciplined than you realize!"
            )
            if evidence:
                recommendations.append(f"Your data shows: {evidence[0]}")
            recommendations.append(
                "Consider tracking wins more visibly to improve self-perception."
            )

        return recommendations[:4]

    # =========================================================================
    # ZPD BRIDGE (March 2026)
    # =========================================================================

    async def get_zpd_knowledge_signals(self, user_uid: UserUID) -> Result[dict[str, Any]]:
        """
        Extract knowledge reinforcement signals for ZPDService consumption.

        Returns signals derived from habit→KU relationships that indicate
        which Knowledge Units the user has actively reinforced through practice.
        Called by ZPDService.assess_zone() to enrich the current_zone calculation.

        Returns:
            Result containing:
            - reinforced_ku_uids: list[str] — KUs reinforced by active habits
            - reinforcement_strength: dict[str, float] — ku_uid → strength (0.0-1.0)
            - at_risk_ku_uids: list[str] — KUs whose reinforcing habit is at risk
                               (streak broken or low success rate)

        See: core/services/zpd/zpd_service.py — ZPDService.assess_zone()
             counts reinforced KUs toward current_zone scoring.
        """
        # Cross-domain row fetch: habits + their reinforced KUs. Single Cypher,
        # typed rows — see CrossDomainQueryService.get_habit_knowledge_reinforcement.
        rows_result = await self.cross_domain_query.get_habit_knowledge_reinforcement(user_uid)
        if rows_result.is_error:
            return Result.fail(rows_result)

        reinforced_ku_uids: list[str] = []
        reinforcement_strength: dict[str, float] = {}
        at_risk_ku_uids: list[str] = []

        for row in rows_result.value or ():
            current_streak = row.current_streak
            success_rate = row.success_rate

            # Strength: blend streak (cap at 30 days) and success rate
            streak_factor = min(1.0, current_streak / 30.0)
            strength = round((streak_factor * 0.5) + (success_rate * 0.5), 3)

            # A habit is "at risk" if its streak just broke (streak=0) or
            # success rate has dropped below 50%
            is_at_risk = current_streak == 0 or success_rate < 0.5

            for ku_uid in row.ku_uids:
                if ku_uid not in reinforced_ku_uids:
                    reinforced_ku_uids.append(ku_uid)
                # Take max strength if the same KU is reinforced by multiple habits
                reinforcement_strength[ku_uid] = max(
                    reinforcement_strength.get(ku_uid, 0.0), strength
                )
                if is_at_risk and ku_uid not in at_risk_ku_uids:
                    at_risk_ku_uids.append(ku_uid)

        return Result.ok(
            {
                "reinforced_ku_uids": reinforced_ku_uids,
                "reinforcement_strength": reinforcement_strength,
                "at_risk_ku_uids": at_risk_ku_uids,
            }
        )
