"""
User Context Service - Context-Aware Intelligence API (Orchestration Layer)
==========================================================================

**Architecture Note (November 27, 2025):**
This service is an ORCHESTRATION layer that coordinates existing infrastructure.
It is kept as a separate file because:
1. Routes (context_aware_api.py) depend on it directly
2. It orchestrates multiple services (builder, intelligence, domain services)
3. It provides API-friendly methods not in the core intelligence

**Consolidated Architecture:**
- user_context_builder.py - ALL context building (MEGA-QUERY + graph-sourced)
- user_context_intelligence.py - ALL intelligence operations (including graph-based)
- user_context_service.py - API orchestration layer (THIS FILE)

This service wraps existing context infrastructure to provide context-aware
operations for the Context-Aware API.

Architecture:
- Uses existing UserContextBuilder to build UserContext
- Uses existing UserContextIntelligence for ALL intelligence operations
- Integrates with domain services (tasks, events, habits) for actions

Created: 2025-11-18
Purpose: Enable context-aware API functionality
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.models.ku.ku import Ku as Task
from core.services.protocols.domain_protocols import TasksOperations
from core.services.protocols.query_types import ContextDashboard, ContextSummary
from core.services.user.intelligence import (
    UserContextIntelligenceFactory,
)
from core.services.user.unified_user_context import UserContext
from core.services.user.user_context_builder import UserContextBuilder
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

# Avoid circular import - UserService imports from core.services.user
if TYPE_CHECKING:
    from core.models.enums import ContextHealthScore
    from core.services.user_service import UserService

logger = get_logger(__name__)


class UserContextService:
    """
    Context-Aware Intelligence Service

    Provides context-aware operations by wrapping existing infrastructure:
    - UserContextBuilder: Builds complete user context
    - UserContextIntelligence: ALL intelligence operations (learning + graph-based)
    - Domain Services: For executing context-aware actions

    All methods return Result[T] for consistent error handling.
    """

    def __init__(
        self,
        context_builder: UserContextBuilder,
        user_service: "UserService",  # String annotation to avoid circular import
        tasks_service: TasksOperations | None = None,
        goal_task_generator: Any | None = None,  # GoalTaskGenerator
        habits_service: Any | None = None,  # HabitsService
        intelligence_factory: UserContextIntelligenceFactory | None = None,
    ) -> None:
        """
        Initialize context service with infrastructure dependencies.

        Args:
            context_builder: Builds UserContext
            user_service: For user operations
            tasks_service: For task operations (optional)
            driver: Neo4j driver for graph intelligence (optional)
            goal_task_generator: For generating tasks from goals (optional)
            habits_service: For habit operations including completion (optional)
            intelligence_factory: Factory for creating UserContextIntelligence instances
                                  (requires all 13 domain services; wired post-construction)
        """
        self.context_builder = context_builder
        self.user_service = user_service
        self.tasks_service = tasks_service
        self.goal_task_generator = goal_task_generator
        self.habits_service = habits_service
        self.intelligence_factory = intelligence_factory
        self.logger = get_logger(__name__)

    # =========================================================================
    # CORE CONTEXT OPERATIONS
    # =========================================================================

    async def get_context_dashboard(
        self,
        user_uid: str,
        include_predictions: bool = True,
        time_window: str = "7d",
    ) -> Result[ContextDashboard]:
        """
        Get unified context dashboard for user.

        Returns comprehensive dashboard with:
        - Current state across all domains
        - Learning recommendations
        - Task priorities
        - Habit health
        - Goal progress
        - Optional: Predictions and insights

        Args:
            user_uid: User identifier
            include_predictions: Include predictive insights
            time_window: Time window for analytics (e.g., "7d", "30d")

        Returns:
            Result containing dashboard data
        """
        # Build context - builder owns user resolution (Option A architecture)
        context_result = await self.context_builder.build(user_uid)
        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        context = context_result.value

        # Build dashboard from context
        dashboard = {
            "user_uid": user_uid,
            "context_version": context.context_version,
            "last_refresh": context.last_refresh.isoformat(),
            "time_window": time_window,
            # Task overview
            "tasks": {
                "active_count": len(context.active_task_uids),
                "overdue_count": len(context.overdue_task_uids),
                "today_count": len(context.today_task_uids),
                "current_focus": context.current_task_focus,
                "blocked_count": len(context.blocked_task_uids),
            },
            # Goal overview
            "goals": {
                "active_count": len(context.active_goal_uids),
                "primary_focus": context.primary_goal_focus,
                "learning_goals": len(context.learning_goals),
                "outcome_goals": len(context.outcome_goals),
                "process_goals": len(context.process_goals),
            },
            # Habit overview
            "habits": {
                "active_count": len(context.active_habit_uids),
                "at_risk_count": len(context.at_risk_habits),
                "keystone_count": len(context.keystone_habits),
                "daily_count": len(context.daily_habits),
                "weekly_count": len(context.weekly_habits),
            },
            # Event overview
            "events": {
                "today_count": len(context.today_event_uids),
                "upcoming_count": len(context.upcoming_event_uids),
                "recurring_count": len(context.recurring_event_uids),
                "missed_count": len(context.missed_event_uids),
            },
            # Learning overview
            "learning": {
                "current_path": context.current_learning_path_uid,
                "life_path": context.life_path_uid,
                "life_path_alignment": context.life_path_alignment_score,
                "mastered_knowledge_count": len(context.mastered_knowledge_uids),
                "ready_to_learn_count": len(context.get_ready_to_learn()),
            },
            # Capacity and workload
            "capacity": {
                "available_minutes_daily": context.available_minutes_daily,
                "current_workload": context.current_workload_score,
                "energy_level": context.current_energy_level.value
                if context.current_energy_level
                else None,
                "preferred_time": context.preferred_time.value if context.preferred_time else None,
            },
        }

        # Add predictions if requested - uses simple context method
        if include_predictions:
            # Get ready-to-learn knowledge from cached context
            ready_knowledge = context.get_ready_to_learn()[:5]

            if ready_knowledge:
                dashboard["predictions"] = {
                    "next_learning_steps": [
                        {
                            "ku_uid": ku_uid,
                            "title": ku_uid,  # Context only has UIDs, not titles
                            "priority_score": 0.7,  # Default medium priority
                            "estimated_time_minutes": 60,  # Default 1 hour estimate
                        }
                        for ku_uid in ready_knowledge
                    ]
                }

        return Result.ok(dashboard)

    async def get_context_summary(
        self,
        user_uid: str,
        include_insights: bool = True,
    ) -> Result[ContextSummary]:
        """
        Get concise context summary for user.

        Returns high-level summary suitable for quick overview:
        - Top priorities
        - Key metrics
        - Alerts/warnings

        Args:
            user_uid: User identifier
            include_insights: Include AI-generated insights

        Returns:
            Result containing context summary
        """
        # Build context - builder owns user resolution (Option A architecture)
        context_result = await self.context_builder.build(user_uid)
        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        context = context_result.value

        # Build summary
        summary = {
            "user_uid": user_uid,
            "generated_at": datetime.now().isoformat(),
            # Top priorities (most important items to focus on)
            "top_priorities": {
                "task_focus": context.current_task_focus,
                "goal_focus": context.primary_goal_focus,
                "overdue_tasks": context.overdue_task_uids[:3],  # Top 3
                "at_risk_habits": context.at_risk_habits[:3],  # Top 3
            },
            # Key metrics
            "key_metrics": {
                "active_items": len(context.active_task_uids) + len(context.active_goal_uids),
                "completion_rate": self._calculate_completion_rate(context),
                "learning_progress": context.life_path_alignment_score,
                "energy_level": context.current_energy_level.value
                if context.current_energy_level
                else "unknown",
            },
            # Alerts/warnings
            "alerts": self._generate_alerts(context),
        }

        # Add insights if requested
        if include_insights:
            # Use factory to create intelligence instance (requires all 13 domain services)
            if self.intelligence_factory:
                intel = self.intelligence_factory.create(context)
                # intel can be used for advanced intelligence queries here
                # Currently unused but available for future features
                _ = intel  # Suppress unused variable warning

            ready_to_learn = context.get_ready_to_learn()

            summary["insights"] = {
                "ready_to_learn_count": len(ready_to_learn),
                "blocked_items_count": len(context.blocked_task_uids),
                "capacity_utilization": context.current_workload_score,  # Already 0-1 score
            }

        return Result.ok(summary)

    async def get_active_context(
        self,
        user_uid: str,
    ) -> Result[UserContext]:
        """
        Get raw UserContext for user.

        Returns the complete context object for advanced use cases.
        Most consumers should use get_context_dashboard() instead.

        Args:
            user_uid: User identifier

        Returns:
            Result containing UserContext
        """
        # Build context - builder owns user resolution (Option A architecture)
        return await self.context_builder.build(user_uid)

    async def get_next_action(self, user_uid: str) -> Result[dict[str, Any]]:
        """
        Get AI-recommended next action based on context.

        Args:
            user_uid: User identifier

        Returns:
            Result containing next action recommendation with rationale
        """
        summary_result = await self.get_context_summary(
            user_uid=user_uid,
            include_insights=True,
        )

        if summary_result.is_error:
            return Result.fail(summary_result)

        summary: ContextSummary = summary_result.value

        next_action = {
            "user_uid": user_uid,
            "recommended_action": summary.get("top_priorities", {}),
            "insights": summary.get("insights", {}),
            "alerts": summary.get("alerts", []),
            "rationale": "Based on current priorities, overdue items, and at-risk habits",
        }

        return Result.ok(next_action)

    async def get_at_risk_habits(self, user_uid: str) -> Result[dict[str, Any]]:
        """
        Get habits at risk based on context analysis.

        Args:
            user_uid: User identifier

        Returns:
            Result containing at-risk habits with streaks and completion rates
        """
        context_result = await self.context_builder.build(user_uid)
        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        context = context_result.value

        at_risk_data = {
            "user_uid": user_uid,
            "at_risk_habits": context.at_risk_habits,
            "habit_streaks": {
                uid: streak
                for uid, streak in context.habit_streaks.items()
                if uid in context.at_risk_habits
            },
            "completion_rates": {
                uid: rate
                for uid, rate in context.habit_completion_rates.items()
                if uid in context.at_risk_habits
            },
            "count": len(context.at_risk_habits),
        }

        return Result.ok(at_risk_data)

    async def get_adaptive_learning_path(self, user_uid: str) -> Result[dict[str, Any]]:
        """
        Get adaptive learning path based on context.

        Args:
            user_uid: User identifier

        Returns:
            Result containing learning path with recommendations
        """
        context_result = await self.context_builder.build(user_uid)
        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        context = context_result.value

        learning_path = {
            "user_uid": user_uid,
            "current_path": context.current_learning_path_uid,
            "life_path": context.life_path_uid,
            "life_path_alignment": context.life_path_alignment_score,
            "ready_to_learn": context.get_ready_to_learn(),
            "next_recommended": context.next_recommended_knowledge,
            "mastered_knowledge": list(context.mastered_knowledge_uids),
            "mastered_count": len(context.mastered_knowledge_uids),
        }

        return Result.ok(learning_path)

    async def get_context_health(self, user_uid: str) -> Result[dict[str, Any]]:
        """
        Get overall context system health metrics.

        Args:
            user_uid: User identifier

        Returns:
            Result containing health metrics, alerts, and recommendations
        """
        summary_result = await self.get_context_summary(
            user_uid=user_uid,
            include_insights=True,
        )

        if summary_result.is_error:
            return Result.fail(summary_result)

        summary: ContextSummary = summary_result.value

        health = {
            "user_uid": user_uid,
            "overall_health": self._calculate_health_score(summary),
            "metrics": summary.get("key_metrics", {}),
            "alerts": summary.get("alerts", []),
            "insights": summary.get("insights", {}),
            "recommendations": self._generate_health_recommendations(summary),
        }

        return Result.ok(health)

    # =========================================================================
    # CONTEXT-AWARE ACTIONS
    # =========================================================================

    async def complete_task_with_context(
        self,
        task_uid: str,
        user_uid: str,
        completion_context: dict[str, Any] | None = None,
        reflection_notes: str = "",
    ) -> Result[Task]:
        """
        Complete task with context awareness.

        Completes task and updates context based on:
        - Knowledge applied during completion
        - Time invested
        - Quality/difficulty assessment
        - Learning insights

        Args:
            task_uid: Task identifier
            completion_context: Context data (knowledge applied, time, quality, etc.)
            reflection_notes: Optional reflection on completion

        Returns:
            Result containing completed task
        """
        if not self.tasks_service:
            return Result.fail(
                Errors.system(
                    message="Tasks service not available",
                    operation="complete_task_with_context",
                )
            )

        # Get task to ensure it exists
        task_result = await self.tasks_service.get(task_uid)
        if task_result.is_error:
            return Result.fail(task_result.expect_error())

        task = task_result.value
        if not task:
            return Result.fail(Errors.not_found(resource="Task", identifier=task_uid))

        # Ownership check — return 404 to prevent UID enumeration
        if task.user_uid != user_uid:
            return Result.fail(Errors.not_found(resource="Task", identifier=task_uid))

        # Extract context data
        completion_context = completion_context or {}
        knowledge_applied = completion_context.get("knowledge_applied", [])
        time_invested_minutes = completion_context.get("time_invested_minutes", 0)
        quality_rating = completion_context.get("quality", "good")

        # Complete the task (basic completion)
        complete_result = await self.tasks_service.complete_task(task_uid)
        if complete_result.is_error:
            return Result.fail(complete_result.expect_error())

        # TODO [ENHANCEMENT]: Record context-aware completion data
        # - Update knowledge application tracking
        # - Record time investment
        # - Update learning progress
        # - Trigger context cache invalidation

        logger.info(
            f"Task {task_uid} completed with context",
            extra={
                "knowledge_applied": knowledge_applied,
                "time_invested": time_invested_minutes,
                "quality": quality_rating,
                "reflection": reflection_notes,
            },
        )

        # Fetch updated task to return
        updated_task_result = await self.tasks_service.get(task_uid)
        if updated_task_result.is_error:
            return Result.fail(updated_task_result.expect_error())

        if updated_task_result.value is None:
            return Result.fail(Errors.not_found(resource="Task", identifier=task_uid))

        return Result.ok(updated_task_result.value)

    async def create_tasks_from_goal_context(
        self,
        goal_uid: str,
        user_uid: str,
        context_preferences: dict[str, Any] | None = None,
        auto_create: bool = True,
    ) -> Result[list[Task]]:
        """
        Create contextually relevant tasks from goal.

        Uses GoalTaskGenerator to intelligently create tasks based on:
        - Goal milestones
        - Knowledge requirements
        - Habit dependencies
        - User's current context

        Args:
            goal_uid: Goal identifier
            context_preferences: Optional preferences for task generation
            auto_create: If True, create tasks immediately; if False, return templates

        Returns:
            Result containing list of created (or template) tasks
        """
        if not self.goal_task_generator:
            return Result.fail(
                Errors.system(
                    message="Goal task generator not available",
                    operation="create_tasks_from_goal_context",
                )
            )

        # Get user from goal
        # First, get the goal to find the user
        from core.services.protocols.domain_protocols import GoalsOperations

        try:
            goal_backend: GoalsOperations = self.goal_task_generator.goals_backend
        except AttributeError:
            return Result.fail(
                Errors.system(
                    message="Goal task generator not properly configured",
                    operation="create_tasks_from_goal_context",
                )
            )
        goal_result = await goal_backend.get_goal(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result.expect_error())

        goal = goal_result.value
        if not goal:
            return Result.fail(Errors.not_found(resource="Goal", identifier=goal_uid))

        # Ownership check — return 404 to prevent UID enumeration
        if goal.user_uid != user_uid:
            return Result.fail(Errors.not_found(resource="Goal", identifier=goal_uid))

        # Build user context - builder owns user resolution (Option A architecture)
        context_result = await self.context_builder.build(user_uid)
        if context_result.is_error:
            return Result.fail(context_result.expect_error())

        context = context_result.value

        # Generate tasks using context
        tasks_result = await self.goal_task_generator.generate_tasks_for_goal(
            goal_uid=goal_uid,
            user_context=context,
            auto_create=auto_create,
        )

        if tasks_result.is_error:
            return Result.fail(tasks_result.expect_error())

        # Convert TaskDTOs to Task domain models
        task_dtos = tasks_result.value
        tasks = []
        for dto in task_dtos:
            from core.models.ku.ku import Ku
            from core.utils.dto_helpers import to_domain_model

            task = to_domain_model(dto, type(dto), Ku)
            tasks.append(task)

        logger.info(
            f"Generated {len(tasks)} tasks for goal {goal_uid}",
            extra={
                "goal_uid": goal_uid,
                "task_count": len(tasks),
                "auto_created": auto_create,
            },
        )

        return Result.ok(tasks)

    async def complete_habit_with_context(
        self,
        habit_uid: str,
        user_uid: str,
        completion_quality: str = "good",  # poor, fair, good, excellent
        environmental_factors: dict[str, Any] | None = None,
    ) -> Result[Any]:  # Returns Habit
        """
        Complete habit with context awareness.

        Completes habit with quality tracking and context-based analysis:
        - Quality score (1-5)
        - Environmental factors
        - Time of day
        - Current energy level
        - Learning reinforcement

        Args:
            habit_uid: Habit identifier
            completion_quality: Quality rating (poor/fair/good/excellent)
            environmental_factors: Optional environmental context

        Returns:
            Result containing completed habit
        """
        if not self.habits_service:
            return Result.fail(
                Errors.system(
                    message="Habits service not available",
                    operation="complete_habit_with_context",
                )
            )

        # Map quality string to 1-5 scale
        quality_map = {
            "poor": 1,
            "fair": 2,
            "good": 3,
            "excellent": 5,
        }
        quality_score = quality_map.get(completion_quality, 3)

        # Get habit to find user
        habit_result = await self.habits_service.get(habit_uid)
        if habit_result.is_error:
            return Result.fail(habit_result.expect_error())

        habit = habit_result.value
        if not habit:
            return Result.fail(Errors.not_found(resource="Habit", identifier=habit_uid))

        # Ownership check — return 404 to prevent UID enumeration
        if habit.user_uid != user_uid:
            return Result.fail(Errors.not_found(resource="Habit", identifier=habit_uid))

        # Build user context - builder owns user resolution (Option A architecture)
        context_result = await self.context_builder.build(user_uid)
        if context_result.is_error:
            return context_result

        context = context_result.value

        # Complete habit with quality tracking
        complete_result = await self.habits_service.progress.complete_habit_with_quality(
            habit_uid=habit_uid,
            user_context=context,
            quality_score=quality_score,
        )

        if complete_result.is_error:
            return Result.fail(complete_result.expect_error())

        logger.info(
            f"Habit {habit_uid} completed with context",
            extra={
                "habit_uid": habit_uid,
                "quality": completion_quality,
                "quality_score": quality_score,
                "environmental_factors": environmental_factors,
            },
        )

        return complete_result

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _calculate_health_score(self, summary: ContextSummary) -> "ContextHealthScore":
        """
        Calculate overall health score from context summary.

        Args:
            summary: Context summary with metrics and alerts

        Returns:
            ContextHealthScore: EXCELLENT, GOOD, FAIR, or POOR
        """
        from core.models.enums import ContextHealthScore

        alerts = summary.get("alerts", [])
        metrics = summary.get("key_metrics", {})

        # Count high-severity alerts
        high_severity_count = sum(1 for alert in alerts if alert.get("severity") == "high")

        # Get completion rate (log if missing - could indicate data issues)
        completion_rate = metrics.get("completion_rate")
        if completion_rate is None:
            self.logger.warning(
                "Context health check: completion_rate metric missing, defaulting to 0.0"
            )
            completion_rate = 0.0

        # Determine health based on alerts and metrics
        if high_severity_count >= 2:
            return ContextHealthScore.POOR
        if high_severity_count == 1 or completion_rate < 0.5:
            return ContextHealthScore.FAIR
        if completion_rate >= 0.8 and len(alerts) == 0:
            return ContextHealthScore.EXCELLENT

        return ContextHealthScore.GOOD

    def _generate_health_recommendations(self, summary: ContextSummary) -> list[str]:
        """
        Generate health improvement recommendations from summary.

        Args:
            summary: Context summary with alerts and metrics

        Returns:
            List of actionable recommendations
        """
        recommendations = []
        alerts = summary.get("alerts", [])

        for alert in alerts:
            alert_type = alert.get("type")

            if alert_type == "overdue_tasks":
                item_count = alert.get("item_count", 0)
                recommendations.append(f"Address {item_count} overdue tasks to reduce backlog")
            elif alert_type == "at_risk_habits":
                item_count = alert.get("item_count", 0)
                recommendations.append(f"Focus on {item_count} habits that need attention")
            elif alert_type == "blocked_tasks":
                item_count = alert.get("item_count", 0)
                recommendations.append(f"Unblock {item_count} tasks to maintain workflow")
            elif alert_type == "overloaded":
                recommendations.append(
                    "Reduce workload or increase available capacity to avoid burnout"
                )

        # Add general recommendations if no specific alerts
        if not recommendations:
            metrics = summary.get("key_metrics", {})
            completion_rate = metrics.get("completion_rate", 0.0)

            if completion_rate < 0.7:
                recommendations.append(
                    "Consider reviewing active items - completion rate could be improved"
                )
            else:
                recommendations.append("Context health is good - maintain current momentum!")

        return recommendations

    def _calculate_completion_rate(self, context: UserContext) -> float:
        """Calculate overall completion rate from context."""
        total_completed = len(context.completed_task_uids) + len(context.completed_goal_uids)
        total_items = (
            len(context.active_task_uids)
            + len(context.completed_task_uids)
            + len(context.active_goal_uids)
            + len(context.completed_goal_uids)
        )

        if total_items == 0:
            return 0.0

        return total_completed / total_items

    def _generate_alerts(self, context: UserContext) -> list[dict[str, Any]]:
        """Generate alerts/warnings from context."""
        alerts = []

        # Overdue tasks alert
        if len(context.overdue_task_uids) > 0:
            alerts.append(
                {
                    "type": "overdue_tasks",
                    "severity": "high",
                    "message": f"{len(context.overdue_task_uids)} tasks are overdue",
                    "item_count": len(context.overdue_task_uids),
                }
            )

        # At-risk habits alert
        if len(context.at_risk_habits) > 0:
            alerts.append(
                {
                    "type": "at_risk_habits",
                    "severity": "medium",
                    "message": f"{len(context.at_risk_habits)} habits need attention",
                    "item_count": len(context.at_risk_habits),
                }
            )

        # Blocked tasks alert
        if len(context.blocked_task_uids) > 3:
            alerts.append(
                {
                    "type": "blocked_tasks",
                    "severity": "medium",
                    "message": f"{len(context.blocked_task_uids)} tasks are blocked",
                    "item_count": len(context.blocked_task_uids),
                }
            )

        # Capacity warning (current_workload_score is 0-1, where 1 is at capacity)
        if context.current_workload_score > 1.5:
            alerts.append(
                {
                    "type": "overloaded",
                    "severity": "high",
                    "message": "Workload exceeds available capacity by 50%+",
                    "workload_score": context.current_workload_score,
                    "capacity": context.available_minutes_daily,
                }
            )

        return alerts
