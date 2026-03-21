"""
Tasks Productivity Service
===========================

Dual-track productivity assessment for Tasks domain (ADR-030).

Compares user self-assessment (vision) with system measurement (action)
to generate perception gap analysis and insights.

NOTE: Uses custom implementation (not BaseAnalyticsService template).
Tasks is unique — it assesses USER productivity across all tasks,
not a single entity. The template expects entity_uid → entity lookup,
which doesn't apply here. See ADR-030 § "Each domain can choose".

Architecture:
- Pure graph queries + Python calculations (NO AI dependencies)
- Uses BaseAnalyticsService for backend access
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.models.enums import EntityStatus, Priority
from core.models.enums.activity_enums import ProductivityLevel
from core.models.shared.dual_track import DualTrackResult
from core.models.task.task import Task
from core.services.base_analytics_service import BaseAnalyticsService
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports.domain_protocols import TasksOperations  # noqa: F401


class TasksProductivityService(BaseAnalyticsService["TasksOperations", Task]):
    """
    Dual-track productivity assessment for tasks.

    Compares user self-assessment with system-measured metrics
    to generate perception gap analysis and insights.

    Pure calculation — no AI dependencies.
    """

    _service_name = "tasks.productivity"

    async def assess_productivity_dual_track(
        self,
        user_uid: str,
        user_productivity_level: ProductivityLevel,
        user_evidence: str,
        user_reflection: str | None = None,
        period_days: int = 30,
    ) -> Result[DualTrackResult[ProductivityLevel]]:
        """
        Dual-track productivity assessment for tasks.

        Compares user self-assessment (vision) with system measurement (action)
        to generate perception gap analysis and insights.

        This implements SKUEL's core philosophy:
        "The user's vision is understood via the words they use to communicate,
        the UserContext is determined via user's actions."

        Pure calculation method - no AI dependencies.

        Args:
            user_uid: User UID to assess
            user_productivity_level: User's self-reported productivity level
            user_evidence: User's evidence for their assessment
            user_reflection: Optional reflection on their productivity
            period_days: Period to analyze (default 30 days)

        Returns:
            Result[DualTrackResult[ProductivityLevel]] with dual-track analysis

        Example:
            >>> from core.models.enums.activity_enums import ProductivityLevel
            >>> result = await service.assess_productivity_dual_track(
            ...     user_uid="user_mike",
            ...     user_productivity_level=ProductivityLevel.PRODUCTIVE,
            ...     user_evidence="I complete most tasks on time",
            ...     user_reflection="Could improve on complex tasks",
            ... )
            >>> if result.is_ok:
            ... dual_track = result.value
            ... print(f"Gap: {dual_track.perception_gap:.0%}")
        """
        # Calculate system assessment
        system_level, system_score, system_evidence = await self._calculate_system_productivity(
            None, user_uid, period_days
        )

        # Calculate user score
        user_score = self._productivity_level_to_score(user_productivity_level)

        # Calculate perception gap
        perception_gap = abs(user_score - system_score)

        # Determine gap direction
        if perception_gap < 0.1:
            direction = "aligned"
        elif user_score > system_score:
            direction = "user_higher"
        else:
            direction = "system_higher"

        # Generate insights and recommendations
        insights = self._generate_productivity_gap_insights(direction, perception_gap, "task")
        recommendations = self._generate_productivity_gap_recommendations(
            direction, perception_gap, None, system_evidence
        )

        # Build result
        # Note: Tasks is unique - assesses USER productivity, not a single entity.
        # entity_uid=user_uid and entity_type="productivity" reflect this.
        result = DualTrackResult[ProductivityLevel](
            entity_uid=user_uid,
            entity_type="productivity",
            user_level=user_productivity_level,
            user_score=user_score,
            user_evidence=user_evidence,
            user_reflection=user_reflection,
            system_level=system_level,
            system_score=system_score,
            system_evidence=tuple(system_evidence),
            perception_gap=perception_gap,
            gap_direction=direction,
            insights=tuple(insights),
            recommendations=tuple(recommendations[:4]),  # Limit to top 4
        )

        return Result.ok(result)

    async def _calculate_system_productivity(
        self, _entity: Any, user_uid: str, period_days: int = 30
    ) -> tuple[ProductivityLevel, float, list[str]]:
        """
        Calculate system productivity from task completion metrics.

        Examines:
        - Task completion rate
        - Overdue ratio
        - On-time completion rate
        - Priority handling

        Args:
            _entity: Unused (user assessment doesn't target a single entity)
            user_uid: User UID
            period_days: Period to analyze (default 30 days)

        Returns:
            Tuple of (ProductivityLevel, score, evidence_list)
        """
        evidence: list[str] = []
        cutoff_date = datetime.now() - timedelta(days=period_days)

        # Get tasks in period
        tasks_result = await self.backend.find_by(user_uid=user_uid)
        if tasks_result.is_error:
            return ProductivityLevel.MODERATELY_PRODUCTIVE, 0.5, ["Unable to fetch tasks"]

        all_tasks = tasks_result.value or []
        period_tasks = [task for task in all_tasks if task.created_at >= cutoff_date]

        if not period_tasks:
            return ProductivityLevel.MODERATELY_PRODUCTIVE, 0.5, ["No tasks in assessment period"]

        # Calculate metrics
        completed_tasks = [t for t in period_tasks if t.status == EntityStatus.COMPLETED]
        completion_rate = len(completed_tasks) / len(period_tasks)

        # Calculate overdue ratio
        overdue_tasks = [
            t
            for t in period_tasks
            if t.due_date
            and t.due_date < datetime.now().date()
            and t.status != EntityStatus.COMPLETED
        ]
        overdue_ratio = len(overdue_tasks) / len(period_tasks) if period_tasks else 0

        # Calculate on-time completion rate
        on_time_completed = [
            t
            for t in completed_tasks
            if t.due_date and t.completion_date and t.completion_date <= t.due_date
        ]
        on_time_rate = len(on_time_completed) / len(completed_tasks) if completed_tasks else 0

        # Calculate priority handling score
        high_priority_tasks = [
            t for t in period_tasks if t.priority and Priority(t.priority).to_numeric() >= 3
        ]
        high_priority_completed = [
            t for t in high_priority_tasks if t.status == EntityStatus.COMPLETED
        ]
        priority_rate = (
            len(high_priority_completed) / len(high_priority_tasks) if high_priority_tasks else 1.0
        )

        # Weighted score calculation
        score = (
            completion_rate * 0.4  # 40% weight on completion rate
            + (1 - overdue_ratio) * 0.25  # 25% weight on avoiding overdue
            + on_time_rate * 0.20  # 20% weight on on-time completion
            + priority_rate * 0.15  # 15% weight on priority handling
        )

        # Build evidence
        evidence.append(
            f"Completed {len(completed_tasks)}/{len(period_tasks)} tasks ({completion_rate:.0%})"
        )
        if overdue_tasks:
            evidence.append(f"{len(overdue_tasks)} tasks currently overdue")
        if on_time_completed:
            evidence.append(
                f"{len(on_time_completed)} tasks completed on time ({on_time_rate:.0%})"
            )
        if high_priority_tasks:
            evidence.append(
                f"High-priority completion: {len(high_priority_completed)}/{len(high_priority_tasks)}"
            )

        # Convert score to level
        system_level = ProductivityLevel.from_score(score)

        return system_level, score, evidence

    def _productivity_level_to_score(self, level: ProductivityLevel) -> float:
        """Convert ProductivityLevel to numeric score (0.0-1.0)."""
        return level.to_score()

    def _generate_productivity_gap_insights(
        self, direction: str, gap: float, entity_name: str
    ) -> list[str]:
        """Generate productivity-specific gap insights."""
        insights: list[str] = []

        if direction == "aligned":
            insights.append(
                "Your self-perception of productivity matches your task completion data. "
                "This indicates accurate self-awareness about your work output."
            )
        elif direction == "user_higher":
            insights.append(
                f"Your self-assessment is more positive than your task metrics suggest "
                f"(gap: {gap:.0%}). Consider: Are there completed tasks not tracked in SKUEL?"
            )
            if gap > 0.3:
                insights.append(
                    "This significant gap may indicate optimism bias, "
                    "or external work not reflected in your task list."
                )
        else:  # system_higher
            insights.append(
                f"Your task completion shows higher productivity than you perceive (gap: {gap:.0%}). "
                "You may be undervaluing your accomplishments."
            )
            if gap > 0.3:
                insights.append(
                    "Consider celebrating your wins - you're accomplishing more than you realize!"
                )

        return insights

    def _generate_productivity_gap_recommendations(
        self, direction: str, _gap: float, _entity: Any, evidence: list[str]
    ) -> list[str]:
        """Generate productivity-specific gap recommendations."""
        recommendations: list[str] = []

        if direction == "aligned":
            recommendations.append(
                "Continue your current approach - your productivity self-awareness is accurate."
            )
            recommendations.append(
                "Consider setting stretch goals to push your productivity further."
            )
        elif direction == "user_higher":
            recommendations.append("Review your task list to ensure all work is tracked.")
            recommendations.append(
                "Consider breaking down large tasks to better visualize progress."
            )
            # Check for overdue tasks in evidence
            if any("overdue" in e.lower() for e in evidence):
                recommendations.append(
                    "Address overdue tasks to align perceived and actual productivity."
                )
        else:  # system_higher
            recommendations.append(
                "Acknowledge your accomplishments - you're more productive than you think!"
            )
            if evidence:
                recommendations.append(
                    f"Review your metrics: {evidence[0]} shows solid productivity."
                )
            recommendations.append(
                "Consider why you underestimate your productivity - impostor syndrome can affect perception."
            )

        return recommendations[:4]
