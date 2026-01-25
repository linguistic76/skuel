"""
Action Recommendation Engine - Personalized Recommendations
===========================================================

Focused service for generating actionable recommendations.

Responsibilities:
- Generate next best action
- Create personalized recommendations
- Identify optimization opportunities
- Generate workflow optimizations
- Predict future state
- Sort and prioritize recommendations

This service is part of the refactored EnhancedAskesisService architecture:
- UserStateAnalyzer: Analyze current user state and patterns
- ActionRecommendationEngine: Generate personalized action recommendations (THIS FILE)
- QueryProcessor: Process and answer natural language queries
- EntityExtractor: Extract entities from natural language
- ContextRetriever: Retrieve domain-specific context
- EnhancedAskesisService: Facade coordinating all sub-services

Architecture:
- Depends on UserStateAnalyzer for state scoring and blockers (injected)
- Returns Result[T] for error handling
- Uses UserContext as primary input
"""

from __future__ import annotations

from datetime import date
from operator import itemgetter
from typing import TYPE_CHECKING, Any

from core.constants import ConfidenceLevel
from core.models.shared_enums import Priority
from core.services.askesis.state_scoring import (
    calculate_momentum,
    find_key_blocker,
    score_current_state,
)
from core.services.askesis.types import (
    AskesisInsight,
    AskesisRecommendation,
    InsightType,
    RecommendationCategory,
)
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.services.user import UserContext

logger = get_logger(__name__)


class ActionRecommendationEngine:
    """
    Generate personalized action recommendations.

    This service handles recommendation generation:
    - Next best action determination
    - Personalized recommendation generation
    - Optimization opportunity identification
    - Workflow optimization
    - Future state prediction
    - Recommendation sorting and prioritization

    Architecture:
    - Uses pure functions from state_scoring.py (no circular dependencies)
    - Uses UserContext as primary input
    - Returns frozen dataclasses (AskesisRecommendation)

    January 2026: Refactored to eliminate circular dependency with UserStateAnalyzer.
    State scoring functions extracted to state_scoring.py module.
    """

    def __init__(self) -> None:
        """Initialize action recommendation engine."""
        logger.info("ActionRecommendationEngine initialized")

    # ========================================================================
    # PUBLIC API - RECOMMENDATIONS
    # ========================================================================

    @with_error_handling("get_next_best_action", error_type="system")
    async def get_next_best_action(
        self, user_context: UserContext
    ) -> Result[AskesisRecommendation]:
        """
        Get the single best next action based on complete context.

        This is Askesis's "killer feature" - understanding everything
        and recommending the ONE thing to do next.

        Priority:
        1. Prevent habit streak loss (critical)
        2. Unblock if stuck (high)
        3. Advance goals (medium)
        4. Build foundation (low)

        Args:
            user_context: User context

        Returns:
            Result[AskesisRecommendation]: Single best action recommendation
        """
        # Analyze current state using pure function
        score_current_state(user_context)

        # Critical: Prevent habit streak loss
        if user_context.at_risk_habits:
            habit_uid = next(iter(user_context.at_risk_habits))
            streak = user_context.habit_streaks.get(habit_uid, 0)

            if streak > 14:  # Long streak at risk
                return Result.ok(
                    AskesisRecommendation(
                        category=RecommendationCategory.IMMEDIATE,
                        title=f"Protect your {streak}-day streak!",
                        rationale=f"You're about to lose a {streak}-day streak. This represents significant progress.",
                        action_type="complete",
                        target_entity=("habit", habit_uid),
                        priority=Priority.CRITICAL,
                        estimated_time_minutes=30,
                        expected_outcome="Maintain momentum and consistency",
                        prerequisites=[],
                        confidence=ConfidenceLevel.VERY_HIGH,
                        alternative_actions=[],
                    )
                )

        # High priority: Unblock if stuck
        if user_context.is_blocked:
            # Find key blocker using pure function
            blocking_prereq = find_key_blocker(user_context)

            if blocking_prereq:
                return Result.ok(
                    AskesisRecommendation(
                        category=RecommendationCategory.IMMEDIATE,
                        title="Unblock your progress",
                        rationale="Completing this prerequisite will unlock multiple paths",
                        action_type="study",
                        target_entity=("knowledge", blocking_prereq),
                        priority=Priority.HIGH,
                        estimated_time_minutes=60,
                        expected_outcome="Unlock blocked tasks and knowledge",
                        prerequisites=[],
                        confidence=ConfidenceLevel.GOOD,
                        alternative_actions=[],
                    )
                )

        # Medium priority: Advance goals
        if user_context.active_goal_uids:
            goal_action = self._recommend_goal_action(user_context)
            if goal_action:
                return Result.ok(goal_action)

        # Low priority: Build foundation
        return Result.ok(self._recommend_foundation_building(user_context))

    @with_error_handling("generate_recommendations", error_type="system")
    async def generate_recommendations(
        self, user_context: UserContext, insights: list[AskesisInsight]
    ) -> Result[list[AskesisRecommendation]]:
        """
        Generate recommendations based on context and insights.

        Creates prioritized list of actionable recommendations addressing:
        - Critical risks from insights
        - Proactive opportunities

        Args:
            user_context: User context
            insights: List of insights from UserStateAnalyzer

        Returns:
            Result[list[AskesisRecommendation]]: List of recommendations
        """
        recommendations = []

        # Priority 1: Address risks from insights
        recommendations.extend(
            [
                AskesisRecommendation(
                    category=RecommendationCategory.IMMEDIATE,
                    title=f"Address: {insight.title}",
                    rationale=insight.description,
                    action_type="complete",
                    target_entity=("multiple", "various"),
                    priority=Priority.CRITICAL,
                    estimated_time_minutes=30,
                    expected_outcome="Prevent negative consequences",
                    prerequisites=[],
                    confidence=insight.confidence,
                    alternative_actions=[],
                )
                for insight in insights
                if insight.type == InsightType.RISK and insight.impact == "critical"
            ]
        )

        # Add proactive recommendations
        if user_context.current_workload_score < 0.5:
            recommendations.append(
                AskesisRecommendation(
                    category=RecommendationCategory.STRATEGIC,
                    title="Increase challenge level",
                    rationale="You have capacity for more challenging work",
                    action_type="create",
                    target_entity=("goal", "new"),
                    priority=Priority.MEDIUM,
                    estimated_time_minutes=60,
                    expected_outcome="Accelerate growth",
                    prerequisites=[],
                    confidence=ConfidenceLevel.MEDIUM,
                    alternative_actions=[],
                )
            )

        return Result.ok(recommendations)

    @with_error_handling("optimize_workflow", error_type="system")
    async def optimize_workflow(self, user_context: UserContext) -> Result[list[dict[str, Any]]]:
        """
        Suggest workflow optimizations based on context.

        Identifies opportunities for:
        - Batching similar tasks
        - Consolidating habits
        - Goal alignment
        - Learning path optimization

        Args:
            user_context: User context

        Returns:
            Result[list[dict]]: List of optimization opportunities
        """
        optimizations = []

        # Optimization: Consolidate habits
        if len(user_context.active_habit_uids) > 10:
            optimizations.append(
                {
                    "type": "consolidation",
                    "target": "habits",
                    "suggestion": "Combine similar habits into routines",
                    "expected_benefit": "Reduce cognitive load by 30%",
                    "implementation": [
                        "Group morning habits",
                        "Create habit stacks",
                        "Use triggers effectively",
                    ],
                }
            )

        # Optimization: Goal alignment
        overlapping_goals = self._find_overlapping_goals(user_context)
        if overlapping_goals:
            goal_titles = ", ".join(g.get("title", "Untitled") for g in overlapping_goals[:3])
            optimizations.append(
                {
                    "type": "alignment",
                    "target": "goals",
                    "suggestion": "Merge overlapping goals",
                    "expected_benefit": "Increase focus and reduce redundancy",
                    "implementation": [
                        f"Review overlapping goals: {goal_titles}",
                        "Identify common outcomes",
                        "Consolidate into unified goal",
                    ],
                }
            )

        # Optimization: Knowledge paths
        if len(user_context.blocked_knowledge_uids) > 5:
            key_prereqs = self._identify_key_prerequisites(user_context)
            optimizations.append(
                {
                    "type": "learning_path",
                    "target": "knowledge",
                    "suggestion": "Focus on key prerequisites",
                    "expected_benefit": f"Unlock {len(user_context.blocked_knowledge_uids)} knowledge areas",
                    "implementation": key_prereqs,
                }
            )

        # Optimization: MOC navigation
        # Suggest MOC creation when user has scattered knowledge
        if (
            len(user_context.mastered_knowledge_uids) > 10
            and len(user_context.active_moc_uids) == 0
        ):
            optimizations.append(
                {
                    "type": "organization",
                    "target": "moc",
                    "suggestion": "Create a Map of Content for your knowledge",
                    "expected_benefit": "Better knowledge navigation and discovery",
                    "implementation": [
                        "Identify your core knowledge domains",
                        "Create a MOC for your primary learning area",
                        "Link related knowledge units together",
                    ],
                }
            )

        # Suggest MOC review when user has many MOCs but hasn't viewed recently
        elif (
            len(user_context.active_moc_uids) > 0
            and len(user_context.recently_viewed_moc_uids) == 0
        ):
            optimizations.append(
                {
                    "type": "review",
                    "target": "moc",
                    "suggestion": "Review your Maps of Content",
                    "expected_benefit": "Rediscover organized knowledge and find gaps",
                    "implementation": [
                        "Browse your most-used MOCs",
                        "Update outdated content links",
                        "Add new knowledge to existing MOCs",
                    ],
                }
            )

        return Result.ok(optimizations)

    @with_error_handling("predict_future_state", error_type="system")
    async def predict_future_state(
        self, user_context: UserContext, days_ahead: int = 7
    ) -> Result[dict[str, Any]]:
        """
        Predict user's future state based on current trajectory.

        Predictions include:
        - Habits at risk (streak decay)
        - Goals on track vs at risk
        - Knowledge ready to learn
        - Workload trends
        - Momentum score

        Args:
            user_context: User context
            days_ahead: Number of days to predict

        Returns:
            Result[dict]: Predictions about future state and potential issues
        """
        predictions: dict[str, Any] = {
            "habits_at_risk": [],
            "goals_on_track": [],
            "goals_at_risk": [],
            "knowledge_ready": [],
            "workload_trend": "stable",
            "momentum_score": 0.0,
            "recommendations": [],
        }

        # Predict habit maintenance
        for habit_uid, streak in user_context.habit_streaks.items():
            if habit_uid in user_context.at_risk_habits:
                risk_days = self._calculate_habit_risk_days(streak, user_context)
                if risk_days <= days_ahead:
                    predictions["habits_at_risk"].append(
                        {"uid": habit_uid, "risk_day": risk_days, "current_streak": streak}
                    )

        # Predict goal completion
        for goal_uid in user_context.active_goal_uids:
            progress = user_context.goal_progress.get(goal_uid, 0)
            deadline = user_context.goal_deadlines.get(goal_uid)

            if deadline:
                days_remaining = (deadline - date.today()).days
                required_daily_progress = (100 - progress) / max(days_remaining, 1)

                if required_daily_progress > 5:  # More than 5% per day needed
                    predictions["goals_at_risk"].append(
                        {
                            "uid": goal_uid,
                            "current_progress": progress,
                            "required_daily_progress": required_daily_progress,
                        }
                    )
                else:
                    predictions["goals_on_track"].append(goal_uid)

        # Predict knowledge readiness
        ready_soon = []
        for blocked_uid in user_context.blocked_knowledge_uids:
            if blocked_uid in user_context.prerequisites_needed:
                prereqs = user_context.prerequisites_needed[blocked_uid]
                completed = [p for p in prereqs if p in user_context.prerequisites_completed]
                if len(completed) >= len(prereqs) - 1:
                    ready_soon.append(blocked_uid)

        predictions["knowledge_ready"] = ready_soon

        # Calculate momentum using pure function
        predictions["momentum_score"] = calculate_momentum(user_context)

        # Generate predictive recommendations
        if predictions["habits_at_risk"]:
            predictions["recommendations"].append("Schedule habit reinforcement sessions")
        if predictions["goals_at_risk"]:
            predictions["recommendations"].append("Increase focus on at-risk goals")

        return Result.ok(predictions)

    # ========================================================================
    # PRIVATE - RECOMMENDATION HELPERS
    # ========================================================================

    def _recommend_goal_action(self, user_context: UserContext) -> AskesisRecommendation | None:
        """
        Recommend action for goal progress.

        Finds goal closest to completion (50-100% progress).

        Args:
            user_context: User context

        Returns:
            Recommendation for goal action, or None if no suitable goal
        """
        # Find goal closest to completion
        best_goal = None
        best_progress = 0

        for goal_uid in user_context.active_goal_uids:
            progress = user_context.goal_progress.get(goal_uid, 0)
            if 50 < progress < 100 and progress > best_progress:
                best_goal = goal_uid
                best_progress = progress

        if best_goal:
            return AskesisRecommendation(
                category=RecommendationCategory.SHORT_TERM,
                title="Push goal to completion",
                rationale=f"This goal is {best_progress}% complete",
                action_type="progress",
                target_entity=("goal", best_goal),
                priority=Priority.HIGH,
                estimated_time_minutes=120,
                expected_outcome="Complete goal this week",
                prerequisites=[],
                confidence=ConfidenceLevel.STANDARD,
                alternative_actions=[],
            )
        return None

    def _recommend_foundation_building(self, _user_context: UserContext) -> AskesisRecommendation:
        """
        Recommend foundation-building action.

        Returns:
            Generic recommendation for establishing learning habits
        """
        return AskesisRecommendation(
            category=RecommendationCategory.LONG_TERM,
            title="Build learning foundation",
            rationale="Establish consistent learning habits",
            action_type="create",
            target_entity=("habit", "new_learning_habit"),
            priority=Priority.MEDIUM,
            estimated_time_minutes=30,
            expected_outcome="Create sustainable learning system",
            prerequisites=[],
            confidence=ConfidenceLevel.MEDIUM,
            alternative_actions=[],
        )

    def _calculate_habit_risk_days(self, streak: int, _user_context: UserContext) -> int:
        """
        Calculate days until habit is at risk.

        Simple model: habits need reinforcement every 2-3 days.

        Args:
            streak: Current habit streak length
            _user_context: User context (unused - for future use)

        Returns:
            Days until habit at risk
        """
        # Simple model: habits need reinforcement every 2-3 days
        return 2 if streak > 7 else 1

    def _find_overlapping_goals(self, _user_context: UserContext) -> list[dict[str, Any]]:
        """
        Find goals with overlapping scope.

        Args:
            _user_context: User context (unused - would need goal relationship analysis)

        Returns:
            List of overlapping goals (currently empty - for future implementation)
        """
        # This would analyze goal relationships
        # For now, return empty
        return []

    def _identify_key_prerequisites(self, user_context: UserContext) -> list[str]:
        """
        Identify key prerequisite knowledge.

        Counts how many items each prerequisite unlocks and returns top 3.

        Args:
            user_context: User context

        Returns:
            List of top 3 prerequisite UIDs by unlock count
        """
        # Count how many items each prerequisite unlocks
        unlock_counts = {}
        for prereqs in user_context.prerequisites_needed.values():
            for prereq in prereqs:
                unlock_counts[prereq] = unlock_counts.get(prereq, 0) + 1

        # Return top prerequisites by unlock count
        sorted_prereqs = sorted(unlock_counts.items(), key=itemgetter(1), reverse=True)
        return [p[0] for p in sorted_prereqs[:3]]
