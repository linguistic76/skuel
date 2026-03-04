"""
User State Analyzer - State Assessment and Pattern Detection
=============================================================

Focused service for analyzing user's current state and identifying patterns.

Responsibilities:
- Analyze comprehensive user state
- Generate insights across domains
- Identify behavioral patterns
- Calculate health metrics
- Assess risks
- Detect correlations

This service is part of the refactored EnhancedAskesisService architecture:
- UserStateAnalyzer: Analyze current user state and patterns (THIS FILE)
- ActionRecommendationEngine: Generate personalized action recommendations
- QueryProcessor: Process and answer natural language queries
- EntityExtractor: Extract entities from natural language
- ContextRetriever: Retrieve domain-specific context
- EnhancedAskesisService: Facade coordinating all sub-services

Architecture:
- Depends on ActionRecommendationEngine for recommendations (injected)
- Returns Result[T] for error handling
- Uses UserContext as primary input
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.constants import ConfidenceLevel
from core.models.enums import Domain
from core.services.askesis.state_scoring import (
    calculate_domain_balance,
    calculate_momentum,
    find_key_blocker,
    score_current_state,
)
from core.services.askesis.types import (
    AskesisAnalysis,
    AskesisInsight,
    InsightType,
)
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.zpd.zpd_assessment import ZPDAssessment
    from core.services.user import UserContext

logger = get_logger(__name__)


class UserStateAnalyzer:
    """
    Analyze user's current state and identify patterns.

    This service handles state analysis:
    - Comprehensive state assessment
    - Insight generation across domains
    - Pattern detection (habit-goal correlation, learning velocity, workload)
    - Health metric calculation
    - Risk assessment
    - Momentum and balance scoring

    Architecture:
    - Uses pure functions from state_scoring.py (no circular dependencies)
    - Uses UserContext as primary input
    - Returns frozen dataclasses (AskesisAnalysis, AskesisInsight)

    January 2026: Refactored to eliminate circular dependency with ActionRecommendationEngine.
    State scoring functions extracted to state_scoring.py module.
    """

    def __init__(self) -> None:
        """Initialize user state analyzer."""
        logger.info("UserStateAnalyzer initialized")

    # ========================================================================
    # PUBLIC API - STATE ANALYSIS
    # ========================================================================

    @with_error_handling("analyze_user_state", error_type="system")
    async def analyze_user_state(
        self,
        user_context: UserContext,
        focus_areas: list[str] | None = None,
        recommendations: list[Any] | None = None,
        optimizations: list[dict[str, Any]] | None = None,
        zpd_assessment: ZPDAssessment | None = None,
    ) -> Result[AskesisAnalysis]:
        """
        Perform comprehensive analysis of user's state using full context.

        Args:
            user_context: Complete user context
            focus_areas: Optional specific areas to focus on
            recommendations: Pre-generated recommendations (from ActionRecommendationEngine)
            optimizations: Pre-generated optimizations (from ActionRecommendationEngine)

        Returns:
            Result[AskesisAnalysis]: Comprehensive analysis with insights,
                recommendations, health metrics, and optimization opportunities

        Note:
            January 2026: Recommendations and optimizations are now passed in rather than
            generated internally. This eliminates the circular dependency with
            ActionRecommendationEngine. The AskesisService facade orchestrates getting
            recommendations and optimizations from ActionRecommendationEngine.
        """
        # Generate context summary
        context_summary = self._summarize_context(user_context)

        # Generate insights across all domains
        insights = await self._generate_insights(user_context, focus_areas)

        # Calculate health metrics
        health_metrics = self._calculate_health_metrics(user_context)

        # Assess risks
        risk_assessment = self._assess_risks(user_context)

        analysis = AskesisAnalysis(
            user_uid=user_context.user_uid,
            generated_at=datetime.now(),
            context_summary=context_summary,
            insights=insights,
            recommendations=recommendations or [],
            health_metrics=health_metrics,
            risk_assessment=risk_assessment,
            optimization_opportunities=optimizations or [],
            zpd_assessment=zpd_assessment,
        )

        logger.info(
            "Generated Askesis analysis for user %s: %d insights",
            user_context.user_uid,
            len(insights),
        )

        return Result.ok(analysis)

    async def identify_patterns(self, user_context: UserContext) -> Result[list[AskesisInsight]]:
        """
        Identify patterns in user's behavior and progress.

        Detects:
        - Habit-goal correlations
        - Learning velocity patterns
        - Workload patterns

        Args:
            user_context: User context to analyze

        Returns:
            Result[list[AskesisInsight]]: List of pattern insights
        """
        patterns = []

        # Detect habit-goal correlation pattern
        habit_goal_pattern = self._detect_habit_goal_correlation(user_context)
        if habit_goal_pattern:
            patterns.append(habit_goal_pattern)

        # Detect learning velocity pattern
        velocity_pattern = self._detect_learning_velocity_pattern(user_context)
        if velocity_pattern:
            patterns.append(velocity_pattern)

        # Detect workload pattern
        workload_pattern = self._detect_high_workload_pattern(user_context)
        if workload_pattern:
            patterns.append(workload_pattern)

        return Result.ok(patterns)

    def calculate_system_health(self, user_context: UserContext) -> dict[str, float]:
        """
        Calculate overall system health metrics.

        Calculates health scores for:
        - Consistency (habit streaks)
        - Progress (goal advancement)
        - Balance (domain distribution)
        - Momentum (learning velocity)
        - Sustainability (inverse of workload)
        - Overall (weighted average)

        Args:
            user_context: User context

        Returns:
            Health scores for different aspects (0.0 to 1.0)
        """
        health = {
            "consistency": 0.0,
            "progress": 0.0,
            "balance": 0.0,
            "momentum": 0.0,
            "sustainability": 0.0,
            "overall": 0.0,
        }

        # Consistency: Based on habit streaks
        if user_context.habit_streaks:
            avg_streak = sum(user_context.habit_streaks.values()) / len(user_context.habit_streaks)
            health["consistency"] = min(1.0, avg_streak / 30)  # 30-day benchmark

        # Progress: Based on goal advancement
        if user_context.goal_progress:
            health["progress"] = sum(user_context.goal_progress.values()) / (
                len(user_context.goal_progress) * 100
            )

        # Balance: Distribution across domains
        domain_distribution = self._calculate_domain_balance(user_context)
        health["balance"] = domain_distribution

        # Momentum: Learning velocity
        health["momentum"] = min(1.0, user_context.calculate_learning_velocity())

        # Sustainability: Inverse of workload
        health["sustainability"] = 1.0 - user_context.current_workload_score

        # Overall: Weighted average
        weights = {
            "consistency": 0.3,
            "progress": 0.2,
            "balance": 0.15,
            "momentum": 0.15,
            "sustainability": 0.2,
        }
        health["overall"] = sum(health[key] * weight for key, weight in weights.items())

        return health

    # ========================================================================
    # PRIVATE - CONTEXT SUMMARIZATION
    # ========================================================================

    def _summarize_context(self, user_context: UserContext) -> dict[str, Any]:
        """
        Create summary of user context.

        Args:
            user_context: User context

        Returns:
            Summary dict with active items, state flags, and progress metrics
        """
        return {
            "active_items": {
                "tasks": len(user_context.active_task_uids),
                "goals": len(user_context.active_goal_uids),
                "habits": len(user_context.active_habit_uids),
            },
            "state_flags": {
                "is_blocked": user_context.is_blocked,
                "has_overdue": user_context.has_overdue_items,
                "at_risk_habits": len(user_context.at_risk_habits),
            },
            "progress_metrics": {
                "learning_velocity": user_context.calculate_learning_velocity(),
                "workload": user_context.current_workload_score,
                "mastered_knowledge": len(user_context.mastered_knowledge_uids),
            },
        }

    # ========================================================================
    # PRIVATE - INSIGHT GENERATION
    # ========================================================================

    async def _generate_insights(
        self, user_context: UserContext, _focus_areas: list[str] | None
    ) -> list[AskesisInsight]:
        """
        Generate insights from context.

        Identifies critical issues, opportunities, and patterns.

        Args:
            user_context: User context
            _focus_areas: Optional focus areas (unused - for future use)

        Returns:
            List of generated insights
        """
        insights = []

        # Always check for critical issues
        if user_context.at_risk_habits:
            insights.append(
                AskesisInsight(
                    type=InsightType.RISK,
                    title="Habit streaks at risk",
                    description=f"{len(user_context.at_risk_habits)} habits need immediate attention",
                    confidence=ConfidenceLevel.VERY_HIGH,
                    impact="critical",
                    domains_affected=[Domain.PERSONAL],
                    entities_involved={"habits": list(user_context.at_risk_habits)},
                    recommended_actions=[
                        {"action": "Complete habits today", "urgency": "immediate"}
                    ],
                    supporting_data={"count": len(user_context.at_risk_habits)},
                )
            )

        # Check for opportunities
        ready_knowledge = user_context.get_ready_to_learn()
        if len(ready_knowledge) > 3:
            insights.append(
                AskesisInsight(
                    type=InsightType.OPPORTUNITY,
                    title="Multiple learning paths available",
                    description=f"{len(ready_knowledge)} knowledge units ready to learn",
                    confidence=ConfidenceLevel.GOOD,
                    impact="medium",
                    domains_affected=[Domain.KNOWLEDGE],
                    entities_involved={"knowledge": ready_knowledge[:5]},
                    recommended_actions=[
                        {"action": "Choose next learning topic", "benefit": "Continue momentum"}
                    ],
                    supporting_data={"ready_count": len(ready_knowledge)},
                )
            )

        # Check for blocked state
        if user_context.is_blocked:
            insights.append(
                AskesisInsight(
                    type=InsightType.RISK,
                    title="Progress blocked",
                    description="Prerequisites needed to unblock progress",
                    confidence=ConfidenceLevel.HIGH,
                    impact="high",
                    domains_affected=[Domain.KNOWLEDGE, Domain.BUSINESS],
                    entities_involved={
                        "blocked": list(user_context.blocked_task_uids)[:5],
                        "prerequisites": list(user_context.prerequisites_needed.keys())[:5],
                    },
                    recommended_actions=[
                        {"action": "Complete key prerequisites", "benefit": "Unblock progress"}
                    ],
                    supporting_data={"blocked_count": len(user_context.blocked_task_uids)},
                )
            )

        return insights

    # ========================================================================
    # PRIVATE - HEALTH & RISK METRICS
    # ========================================================================

    def _calculate_health_metrics(self, user_context: UserContext) -> dict[str, float]:
        """Calculate health metrics from context."""
        return self.calculate_system_health(user_context)

    def _assess_risks(self, user_context: UserContext) -> dict[str, Any]:
        """
        Assess risks from context.

        Calculates risk scores for:
        - Habit risk (streaks at risk)
        - Goal risk (low progress goals)
        - Overload risk (workload score)
        - Stagnation risk (learning velocity)

        Args:
            user_context: User context

        Returns:
            Risk assessment dict with risk scores (0.0 to 1.0)
        """
        risks = {
            "habit_risk": len(user_context.at_risk_habits)
            / max(len(user_context.active_habit_uids), 1),
            "goal_risk": 0.0,
            "overload_risk": user_context.current_workload_score,
            "stagnation_risk": 0.0,
        }

        # Calculate goal risk
        at_risk_goals = 0
        for goal_uid in user_context.active_goal_uids:
            progress = user_context.goal_progress.get(goal_uid, 0)
            if progress < 25:
                at_risk_goals += 1
        risks["goal_risk"] = at_risk_goals / max(len(user_context.active_goal_uids), 1)

        # Calculate stagnation risk
        if user_context.calculate_learning_velocity() < 0.2:
            risks["stagnation_risk"] = 0.8

        return risks

    # ========================================================================
    # PRIVATE - STATE SCORING
    # ========================================================================

    def _score_current_state(self, user_context: UserContext) -> float:
        """Delegate to pure function. See state_scoring.score_current_state for details."""
        return score_current_state(user_context)

    def _find_key_blocker(self, user_context: UserContext) -> str | None:
        """Delegate to pure function. See state_scoring.find_key_blocker for details."""
        return find_key_blocker(user_context)

    def _calculate_momentum(self, user_context: UserContext) -> float:
        """Delegate to pure function. See state_scoring.calculate_momentum for details."""
        return calculate_momentum(user_context)

    def _calculate_domain_balance(self, user_context: UserContext) -> float:
        """Delegate to pure function. See state_scoring.calculate_domain_balance for details."""
        return calculate_domain_balance(user_context)

    # ========================================================================
    # PRIVATE - PATTERN DETECTION
    # ========================================================================

    def _detect_habit_goal_correlation(self, user_context: UserContext) -> AskesisInsight | None:
        """
        Detect correlation between habit consistency and goal progress.

        Args:
            user_context: User context

        Returns:
            Insight if strong correlation detected, None otherwise
        """
        strong_habits = [h for h, s in user_context.habit_streaks.items() if s > 14]
        progressing_goals = [g for g, p in user_context.goal_progress.items() if p > 50]

        if strong_habits and progressing_goals:
            return AskesisInsight(
                type=InsightType.CORRELATION,
                title="Strong habit-goal correlation",
                description="Your consistent habits are driving goal progress",
                confidence=ConfidenceLevel.STANDARD,
                impact="high",
                domains_affected=[Domain.PERSONAL],
                entities_involved={"habits": strong_habits, "goals": progressing_goals},
                recommended_actions=[
                    {
                        "action": "Maintain habit consistency",
                        "rationale": "Habits are key to your goal achievement",
                    }
                ],
                supporting_data={
                    "avg_habit_streak": sum(user_context.habit_streaks.values())
                    / len(user_context.habit_streaks),
                    "avg_goal_progress": sum(user_context.goal_progress.values())
                    / len(user_context.goal_progress),
                },
            )
        return None

    def _detect_learning_velocity_pattern(self, user_context: UserContext) -> AskesisInsight | None:
        """
        Detect accelerating learning pace pattern.

        Args:
            user_context: User context

        Returns:
            Insight if high velocity detected, None otherwise
        """
        velocity = user_context.calculate_learning_velocity()
        if velocity > 0.7:
            return AskesisInsight(
                type=InsightType.PATTERN,
                title="Accelerating learning pace",
                description="Your learning velocity is increasing",
                confidence=ConfidenceLevel.MEDIUM,
                impact="medium",
                domains_affected=[Domain.KNOWLEDGE],
                entities_involved={"knowledge": list(user_context.mastered_knowledge_uids)[-5:]},
                recommended_actions=[
                    {
                        "action": "Add challenging content",
                        "rationale": "Maintain engagement at higher velocity",
                    }
                ],
                supporting_data={"velocity": velocity},
            )
        return None

    def _detect_high_workload_pattern(self, user_context: UserContext) -> AskesisInsight | None:
        """
        Detect high workload risk pattern.

        Args:
            user_context: User context

        Returns:
            Insight if high workload detected, None otherwise
        """
        if user_context.current_workload_score > 0.8:
            return AskesisInsight(
                type=InsightType.RISK,
                title="High workload detected",
                description="Current workload may impact consistency",
                confidence=ConfidenceLevel.HIGH,
                impact="high",
                domains_affected=[Domain.PERSONAL, Domain.BUSINESS],
                entities_involved={"tasks": user_context.active_task_uids[:10]},
                recommended_actions=[
                    {
                        "action": "Defer non-critical activities",
                        "rationale": "Prevent burnout and maintain quality",
                    }
                ],
                supporting_data={"workload": user_context.current_workload_score},
            )
        return None
