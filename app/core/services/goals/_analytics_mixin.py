"""
Analytics Mixin — GoalsIntelligenceService
============================================

Progress dashboard and learning requirements analysis.

Part of goals_intelligence_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from core.models.goal.goal import Goal
from core.models.goal.goal_dto import GoalDTO
from core.models.graph.path_aware_types import GoalCrossContext
from core.services.infrastructure.prerequisite_checker import build_learning_requirements
from core.services.intelligence import (
    calculate_goal_progress_metrics,
    goal_learning_recommendations,
    goal_recommendations,
)
from core.utils.decorators import requires_graph_intelligence
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.user.unified_user_context import UserContext


class _AnalyticsMixin:
    """
    Progress dashboard and learning requirements for GoalsIntelligenceService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by GoalsIntelligenceService.__init__
    relationships: Any
    progress: Any
    logger: Any
    # Provided by BaseAnalyticsService via multiple inheritance on the composed service.
    _analyze_entity_with_typed_context: Any
    _to_domain_model: Any

    @requires_graph_intelligence("get_goal_progress_dashboard")
    async def get_goal_progress_dashboard(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """
        Get comprehensive goal progress dashboard.

        Provides complete view including:
        - Current progress and status
        - Supporting tasks with completion status
        - Supporting habits with consistency metrics
        - Learning paths and knowledge requirements
        - Timeline tracking and insights
        - Actionable recommendations
        """
        # Use base class template over the CANONICAL typed (path-aware) reader.
        analysis_result = await self._analyze_entity_with_typed_context(
            uid,
            metrics_fn=calculate_goal_progress_metrics,
            recommendations_fn=goal_recommendations,
            min_confidence=min_confidence,
        )

        if analysis_result.is_error:
            return analysis_result

        analysis = analysis_result.value
        goal = self._to_domain_model(analysis["entity"], GoalDTO, Goal)
        context: GoalCrossContext = analysis["context"]
        metrics = analysis["metrics"]

        # GRAPH-NATIVE: Fetch relationships from graph (for additional knowledge requirements)
        from core.services.goals.goal_relationships import GoalRelationships

        rels = await GoalRelationships.fetch(uid, self.relationships)

        # Extract supporting activities — read UIDs off the path-aware entities.
        supporting_tasks = [{"uid": t.uid} for t in context.tasks]
        supporting_habits = [{"uid": h.uid} for h in context.habits]
        learning_paths = [{"uid": lp.uid} for lp in context.learning_paths]

        # Calculate timeline
        days_remaining = None
        if goal.target_date:
            days_remaining = (goal.target_date - date.today()).days

        # Calculate contributions (from metrics)
        total_tasks = metrics["task_support_count"]
        completed_tasks = 0  # Would need task status from actual task entities
        task_contribution = 0.0  # Simplified
        habit_contribution = metrics["support_coverage"] * 100 if metrics["has_habit_system"] else 0
        learning_contribution = (len(learning_paths) * 10.0) if learning_paths else 0

        # Generate insights
        has_knowledge_requirements = rels and rels.required_knowledge_uids
        insights = {
            "needs_more_tasks": metrics["task_support_count"] < 3,
            "needs_habit_support": not metrics["has_habit_system"],
            "has_learning_gaps": not metrics["has_curriculum_alignment"]
            and has_knowledge_requirements,
            "on_track": goal.is_active and goal.progress_percentage >= 10.0,
        }

        return Result.ok(
            {
                "goal": goal,
                "progress": {
                    "percentage": goal.progress_percentage,
                    "status": goal.status,
                    "is_on_track": goal.is_active and goal.progress_percentage >= 10.0,
                    "target_date": goal.target_date,
                    "days_remaining": days_remaining,
                },
                "supporting_activities": {
                    "tasks": supporting_tasks,
                    "habits": supporting_habits,
                    "learning_paths": learning_paths,
                    "total_tasks": total_tasks,
                    "completed_tasks": completed_tasks,
                    "active_habits": metrics["habit_support_count"],
                },
                "contributions": {
                    "task_contribution": task_contribution,
                    "habit_contribution": habit_contribution,
                    "learning_contribution": learning_contribution,
                },
                "insights": insights,
                "recommendations": analysis["recommendations"],
                "metrics": metrics,  # Include standard metrics
            }
        )

    @requires_graph_intelligence("get_goal_completion_forecast")
    async def get_goal_completion_forecast(
        self, uid: str, depth: int = 2, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """
        Get goal completion forecast.

        Analyzes completion trajectory based on:
        - Current progress rate
        - Task completion velocity
        - Habit consistency trends
        - Historical patterns
        """
        # Use base class template over the CANONICAL typed (path-aware) reader.
        analysis_result = await self._analyze_entity_with_typed_context(
            uid,
            metrics_fn=calculate_goal_progress_metrics,
            depth=depth,
            min_confidence=min_confidence,
        )

        if analysis_result.is_error:
            return analysis_result

        # Progress service is required for forecast calculations
        if not self.progress:
            return Result.fail(
                Errors.system(
                    message="Progress service required for completion forecast",
                    operation="get_goal_completion_forecast",
                )
            )

        analysis = analysis_result.value
        goal = self._to_domain_model(analysis["entity"], GoalDTO, Goal)
        context: GoalCrossContext = analysis["context"]
        metrics = analysis["metrics"]

        # Calculate all metrics using progress service helpers
        velocity_metrics = self.progress.calculate_velocity_metrics(None, goal)
        current_progress_rate = velocity_metrics["current_progress_rate"]

        forecast = self.progress.generate_forecast(goal, current_progress_rate)
        days_ahead_or_behind = forecast["days_ahead_or_behind"]

        timeline_analysis = self.progress.calculate_timeline_analysis(
            goal, velocity_metrics, days_ahead_or_behind
        )
        required_velocity = timeline_analysis["required_velocity"]
        confidence_level = timeline_analysis["confidence_level"]

        risk_factors = self.progress.identify_risk_factors(velocity_metrics, None)
        acceleration_opportunities = self.progress.identify_acceleration_opportunities(
            velocity_metrics, None, required_velocity
        )

        return Result.ok(
            {
                "goal": goal,
                "forecast": {
                    "estimated_completion_date": forecast["estimated_completion_date"],
                    "confidence_level": confidence_level,
                    "on_track": goal.is_active and goal.progress_percentage >= 10.0,
                    "days_ahead_or_behind": days_ahead_or_behind,
                    "completion_probability": forecast["completion_probability"],
                },
                "velocity_metrics": {
                    "current_progress_rate": velocity_metrics["current_progress_rate"],
                    "task_completion_velocity": velocity_metrics["task_completion_velocity"],
                    "habit_consistency_score": velocity_metrics["habit_consistency_score"],
                    "learning_progress_rate": 0.5,  # Placeholder
                },
                "timeline_analysis": {
                    "target_date": timeline_analysis["target_date"],
                    "days_remaining": timeline_analysis["days_remaining"],
                    "required_velocity": timeline_analysis["required_velocity"],
                    "current_pace": timeline_analysis["current_pace"],
                },
                "risk_factors": risk_factors,
                "acceleration_opportunities": acceleration_opportunities,
                "metrics": metrics,  # Include standard metrics
                "graph_context": {
                    "task_support_count": len(context.tasks),
                    "habit_support_count": len(context.habits),
                    "support_coverage": metrics["support_coverage"],
                },
            }
        )

    @requires_graph_intelligence("get_goal_learning_requirements")
    async def get_goal_learning_requirements(
        self,
        uid: str,
        depth: int = 2,
        min_confidence: float = 0.7,
        user_context: UserContext | None = None,
    ) -> Result[dict[str, Any]]:
        """
        Get goal's learning requirements.

        Analyzes learning needs for goal achievement:
        - Required knowledge areas
        - Current mastery status
        - Learning paths available
        - Knowledge gaps to fill

        Mastery is real, not stubbed: when ``user_context`` is supplied the
        ``knowledge_gaps`` / ``mastered_knowledge`` / ``ready_to_start`` fields reflect
        the user's actual ``knowledge_mastery`` (via the shared
        :func:`build_learning_requirements` helper, which reuses the same readiness
        threshold as planning/scheduling). Context-free callers degrade to the prior
        behaviour (every requirement treated as an open gap).
        """
        # Use base class template over the CANONICAL typed (path-aware) reader.
        analysis_result = await self._analyze_entity_with_typed_context(
            uid,
            metrics_fn=calculate_goal_progress_metrics,
            recommendations_fn=goal_learning_recommendations,
            depth=depth,
            min_confidence=min_confidence,
        )

        if analysis_result.is_error:
            return analysis_result

        analysis = analysis_result.value
        goal = self._to_domain_model(analysis["entity"], GoalDTO, Goal)
        context: GoalCrossContext = analysis["context"]
        metrics = analysis["metrics"]

        # Mastery-aware learning-requirements payload (shared with the Task lens).
        learning = build_learning_requirements(
            required_knowledge_uids=[k.uid for k in context.knowledge],
            learning_path_uids=[lp.uid for lp in context.learning_paths],
            context=user_context,
        )

        return Result.ok(
            {
                "goal": goal,
                "knowledge_requirements": learning["knowledge_requirements"],
                "learning_paths": learning["learning_paths"],
                "learning_analysis": learning["learning_analysis"],
                "recommendations": analysis["recommendations"],
                "metrics": metrics,  # Include standard metrics
                "graph_context": {
                    "knowledge_requirement_count": metrics["knowledge_requirement_count"],
                    "learning_path_count": metrics["learning_path_count"],
                    "has_curriculum_alignment": metrics["has_curriculum_alignment"],
                },
            }
        )
