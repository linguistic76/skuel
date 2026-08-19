"""
Analytics Mixin — TasksIntelligenceService
==========================================

Behavioral insights and performance analytics.

Part of tasks_intelligence_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from core.models.enums import CompletionStatus, Priority
from core.services.intelligence import (
    PatternAnalyzer,
    RecommendationEngine,
    analyze_completion_trend,
)
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from collections.abc import Sequence

    from core.models.type_hints import UserUID
    from core.ports.domain_protocols import TasksOperations


# =============================================================================
# HELPER FUNCTIONS (SKUEL012 - no lambdas)
# =============================================================================


def _has_high_priority_focus(tasks: Sequence[Any]) -> bool:
    """Check if more than 40% of tasks are high priority."""
    if not tasks:
        return False
    high_priority_count = len(
        [t for t in tasks if t.priority and Priority(t.priority).to_numeric() >= 3]
    )
    return high_priority_count / len(tasks) > 0.4


def _has_detailed_descriptions(tasks: Sequence[Any]) -> bool:
    """Check if more than 60% of tasks have descriptions."""
    if not tasks:
        return False
    with_description = len([t for t in tasks if t.description])
    return with_description / len(tasks) > 0.6


def _extract_completion_hour(task: Any) -> int | None:
    """Extract completion hour from task, or None if not completed."""
    return task.completed_at.hour if task.completed_at else None


class _AnalyticsMixin:
    """
    Behavioral and performance analytics for TasksIntelligenceService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by TasksIntelligenceService.__init__
    backend: "TasksOperations"
    logger: Any

    async def get_behavioral_insights(
        self, user_uid: UserUID, period_days: int = 90
    ) -> Result[dict[str, Any]]:
        """
        Analyze behavioral patterns from tasks.

        Analyzes:
        - Task completion patterns (time of day, day of week)
        - Procrastination patterns
        - Energy-task matching
        - Context productivity patterns

        Returns:
            Result containing:
            - behavior_patterns: Identified patterns
            - success_factors: Key success factors
            - recommendations: Behavioral recommendations
        """
        self.logger.info(f"Analyzing behavioral insights for user {user_uid}")

        # Get completed tasks in period
        cutoff_date = datetime.now() - timedelta(days=period_days)
        tasks_result = await self.backend.find_by(user_uid=user_uid, status=CompletionStatus.DONE)

        if tasks_result.is_error:
            return Result.fail(tasks_result)

        tasks = tasks_result.value
        recent_tasks = [
            task for task in tasks if task.completion_date and task.completion_date >= cutoff_date
        ]

        behavior_patterns = self._analyze_completion_patterns(recent_tasks)
        success_factors = self._identify_success_factors(recent_tasks)
        recommendations = self._generate_behavioral_recommendations(
            behavior_patterns, success_factors
        )

        return Result.ok(
            {
                "behavior_patterns": behavior_patterns,
                "success_factors": success_factors,
                "recommendations": recommendations,
                "metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "user_uid": user_uid,
                    "period_days": period_days,
                    "tasks_analyzed": len(recent_tasks),
                },
            }
        )

    def _analyze_completion_patterns(self, tasks: list) -> list[dict[str, Any]]:
        """Analyze task completion patterns."""
        peak_time = PatternAnalyzer.find_peak_time(tasks, _extract_completion_hour)
        if peak_time:
            return [
                {
                    "pattern": "peak_productivity",
                    "description": f"Most tasks completed around {peak_time['peak_hour']}:00",
                    "confidence": peak_time["confidence"],
                }
            ]
        return []

    def _identify_success_factors(self, tasks: list) -> list[str]:
        """Identify factors contributing to successful task completion."""
        if not tasks:
            return []
        return PatternAnalyzer.identify_factors(
            tasks,
            conditions=[
                (
                    _has_high_priority_focus,
                    "High priority focus drives completion",
                ),
                (
                    _has_detailed_descriptions,
                    "Detailed task descriptions improve completion",
                ),
            ],
        )

    def _generate_behavioral_recommendations(
        self, patterns: list[dict], success_factors: list[str]
    ) -> list[str]:
        """Generate behavioral recommendations."""
        engine = RecommendationEngine()

        for pattern in patterns:
            if pattern.get("pattern") == "peak_productivity":
                engine.add_message(
                    f"Schedule high-priority tasks during your peak hours: {pattern.get('description', '')}"
                )

        engine.add_conditional(
            "Detailed task descriptions improve completion" in success_factors,
            "Continue adding detailed descriptions to tasks",
        )

        return engine.build()

    def _analyze_performance_trends(self, tasks: list) -> dict[str, Any]:
        """Analyze performance trends over time from task completion data."""
        completed_count = sum(1 for task in tasks if task.status == CompletionStatus.DONE)
        result = analyze_completion_trend(completed_count, len(tasks))

        return {
            "completion_trend": result["trend"],
            "efficiency_trend": "stable",
            "quality_trend": "stable",
            "completion_rate": result["completion_rate"],
            "tasks_analyzed": result["analyzed_count"],
        }

    def _identify_optimization_opportunities(
        self, tasks: list, metrics: dict
    ) -> list[dict[str, Any]]:
        """Identify opportunities for optimization based on tasks and metrics."""
        opportunities = []

        if metrics["completion_rate"] < 70:
            opportunities.append(
                {
                    "area": "task_completion",
                    "suggestion": "Consider breaking down large tasks into smaller, manageable subtasks",
                    "potential_impact": "15-25% improvement in completion rate",
                }
            )

        if metrics.get("overdue_tasks", 0) > 5:
            opportunities.append(
                {
                    "area": "deadline_management",
                    "suggestion": "Review and adjust deadlines based on actual completion times",
                    "potential_impact": "Reduced stress and more realistic planning",
                }
            )

        if tasks:
            avg_title_length = sum(len(task.title) for task in tasks) / len(tasks)
            if avg_title_length < 10:
                # Explicit type annotation to allow mixed str/int values
                opportunity: dict[str, Any] = {
                    "area": "task_clarity",
                    "suggestion": "Add more descriptive task titles for better clarity",
                    "potential_impact": "Improved focus and reduced ambiguity",
                    "tasks_affected": len(tasks),
                }
                opportunities.append(opportunity)

        if tasks:
            tasks_without_description = sum(1 for task in tasks if not task.description)
            if tasks_without_description > len(tasks) * 0.5:
                # Explicit type annotation to allow mixed str/int values
                documentation_opportunity: dict[str, Any] = {
                    "area": "task_documentation",
                    "suggestion": "Add descriptions to tasks for better context and execution",
                    "potential_impact": "Clearer expectations and easier execution",
                    "tasks_needing_description": tasks_without_description,
                }
                opportunities.append(documentation_opportunity)

        # Duration calibration insights (ADR-048)
        learned_ratio = metrics.get("learned_duration_ratio")
        if learned_ratio is not None:
            if learned_ratio > 1.3:
                opportunities.append(
                    {
                        "area": "duration_estimation",
                        "suggestion": "Tasks consistently take longer than estimated — add buffer time",
                        "potential_impact": "More realistic planning and less overcommitment",
                        "learned_ratio": round(learned_ratio, 2),
                    }
                )
            elif learned_ratio < 0.7:
                opportunities.append(
                    {
                        "area": "duration_estimation",
                        "suggestion": "Tasks consistently finish faster than estimated — take on more",
                        "potential_impact": "Better use of available time",
                        "learned_ratio": round(learned_ratio, 2),
                    }
                )

        return opportunities
