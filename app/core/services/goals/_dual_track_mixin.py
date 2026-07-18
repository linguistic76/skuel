"""
Dual-Track Mixin — GoalsIntelligenceService
=============================================

Dual-track progress assessment: user vision vs system measurement.

Part of goals_intelligence_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from core.models.enums import EntityStatus
from core.models.enums.activity_enums import ProgressLevel
from core.models.shared.dual_track import DualTrackResult
from core.models.type_hints import UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.goal.goal import Goal


class _DualTrackMixin:
    """
    Dual-track assessment for GoalsIntelligenceService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by GoalsIntelligenceService.__init__
    backend: Any
    logger: Any
    # Provided by BaseAnalyticsService on the composed service.
    _dual_track_assessment: Any
    _store_dual_track_checkin: Any

    async def assess_progress_dual_track(
        self,
        goal_uid: str,
        user_uid: UserUID,
        user_progress_level: ProgressLevel,
        user_evidence: str,
        user_reflection: str | None = None,
    ) -> Result[DualTrackResult[ProgressLevel]]:
        """
        Dual-track progress assessment for goals.

        Compares user self-assessment (vision) with system measurement (action)
        to generate perception gap analysis and insights.

        Uses BaseIntelligenceService._dual_track_assessment() template (ADR-030).
        """
        return await self._dual_track_assessment(
            uid=goal_uid,
            user_uid=user_uid,
            user_level=user_progress_level,
            user_evidence=user_evidence,
            user_reflection=user_reflection,
            system_calculator=self._calculate_system_progress,
            level_scorer=self._progress_level_to_score,
            entity_type="goal",
            insight_generator=self._generate_progress_gap_insights,
            recommendation_generator=self._generate_progress_gap_recommendations,
            store_callback=self._store_dual_track_checkin,
        )

    async def _calculate_system_progress(  # skuel-lint: disable=SKUEL029 -- dual-track system_calculator callback: typed Awaitable + awaited by base_analytics_service
        self, goal: Goal, _user_uid: UserUID
    ) -> tuple[ProgressLevel, float, list[str]]:
        """
        Calculate system progress from goal metrics.

        Examines:
        - Current progress percentage
        - Time elapsed vs time remaining
        - Milestone completion
        - Activity support (tasks, habits)
        """
        evidence: list[str] = []

        # Base progress from goal
        progress_percentage = goal.progress_percentage
        evidence.append(f"Current progress: {progress_percentage:.0f}%")

        # Calculate expected progress based on timeline
        expected_progress = 50.0  # Default if no dates
        if goal.target_date and goal.start_date:
            total_days = (goal.target_date - goal.start_date).days
            elapsed_days = (date.today() - goal.start_date).days
            if total_days > 0:
                expected_progress = (elapsed_days / total_days) * 100
                evidence.append(f"Expected progress: {expected_progress:.0f}%")

        # Calculate progress relative to expectation
        if expected_progress > 0:
            relative_progress = progress_percentage / expected_progress
        else:
            relative_progress = 1.0 if progress_percentage > 0 else 0.5

        # Adjust for goal status
        status_factor = 1.0
        if goal.status == EntityStatus.COMPLETED:
            status_factor = 1.0
            evidence.append("Goal achieved!")
        elif goal.status == EntityStatus.PAUSED:
            status_factor = 0.7
            evidence.append("Goal is currently paused")
        elif goal.status == EntityStatus.CANCELLED:
            status_factor = 0.2
            evidence.append("Goal was cancelled")

        # Final score calculation
        score = min(relative_progress * status_factor, 1.0)

        # Check for overdue
        days_remaining = goal.get_days_remaining()
        if days_remaining is not None and days_remaining < 0:
            evidence.append(f"Overdue by {abs(days_remaining)} days")
            score *= 0.7  # Penalty for being overdue

        # Convert score to level
        system_level = ProgressLevel.from_score(score)

        return system_level, score, evidence

    def _progress_level_to_score(self, level: ProgressLevel) -> float:
        """Convert ProgressLevel to numeric score (0.0-1.0)."""
        return level.to_score()

    def _generate_progress_gap_insights(
        self, direction: str, gap: float, entity_name: str
    ) -> list[str]:
        """Generate progress-specific gap insights."""
        insights: list[str] = []

        if direction == "aligned":
            insights.append(
                f"Your self-perception of progress on '{entity_name}' matches the data. "
                "This indicates accurate self-awareness about your goal advancement."
            )
        elif direction == "user_higher":
            insights.append(
                f"Your self-assessment is more optimistic than the metrics suggest "
                f"(gap: {gap:.0%}). Consider: Are there recent setbacks not reflected in your perception?"
            )
            if gap > 0.3:
                insights.append(
                    "This significant gap may indicate optimism bias. "
                    "Review your milestones to ground your assessment."
                )
        else:  # system_higher
            insights.append(
                f"Your progress metrics show more advancement than you perceive (gap: {gap:.0%}). "
                "You may be undervaluing your achievements."
            )
            if gap > 0.3:
                insights.append(
                    "Consider reviewing your completed milestones - you're making more progress than you realize!"
                )

        return insights

    def _generate_progress_gap_recommendations(
        self, direction: str, _gap: float, entity: Any, evidence: list[str]
    ) -> list[str]:
        """Generate progress-specific gap recommendations."""
        recommendations: list[str] = []
        goal = entity

        if direction == "aligned":
            recommendations.append(
                "Continue your current approach - your progress self-awareness is accurate."
            )
            if goal.progress_percentage < 50:
                recommendations.append(
                    "Consider adding more supporting tasks or habits to accelerate progress."
                )
        elif direction == "user_higher":
            recommendations.append("Review your goal milestones and update progress tracking.")
            recommendations.append("Break down remaining work into smaller, trackable tasks.")
            if any("overdue" in e.lower() for e in evidence):
                recommendations.append(
                    "Address timeline issues to align perceived and actual progress."
                )
        else:  # system_higher
            recommendations.append("Celebrate your progress - you're doing better than you think!")
            if evidence:
                recommendations.append(f"Your metrics show: {evidence[0]}")
            recommendations.append(
                "Consider why you underestimate progress - perfectionism can skew perception."
            )

        return recommendations[:4]
