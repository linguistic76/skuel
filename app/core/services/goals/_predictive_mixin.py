"""
Predictive Mixin — GoalsIntelligenceService
=============================================

Goal success prediction, habit impact analysis, risk assessment, and scenario analysis.
Merged from GoalAnalyticsService (November 2025).

Part of goals_intelligence_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from operator import attrgetter
from typing import TYPE_CHECKING, Any

from core.models.goal.goal import Goal
from core.services.intelligence import (
    MetricsCalculator,
    RecommendationEngine,
    compare_progress_to_expected,
)
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.habit.habit import Habit

    from .goals_intelligence_service import GoalPrediction, HabitImpactAnalysis

logger = get_logger(__name__)


class _PredictiveMixin:
    """
    Predictive analytics for GoalsIntelligenceService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by GoalsIntelligenceService.__init__
    backend: Any
    relationships: Any
    habits_service: Any
    logger: Any

    @with_error_handling("predict_goal_success", error_type="system", uid_param="goal_uid")
    async def predict_goal_success(
        self,
        goal_uid: str,
        lookback_days: int = 30,
    ) -> Result[GoalPrediction]:
        """
        Predict probability of successfully achieving a goal.

        Uses multiple factors:
        - Current progress vs expected progress
        - Habit consistency trends
        - Time remaining
        - Historical performance patterns
        """
        from .goals_intelligence_service import GoalPrediction as _GoalPrediction

        # Get goal
        goal_result = await self.backend.get(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result)
        if not goal_result.value:
            return Result.fail(Errors.not_found(resource="Goal", identifier=goal_uid))
        goal = goal_result.value

        # Get supporting habits (from graph relationships)
        from core.services.goals.goal_relationships import GoalRelationships

        rels = await GoalRelationships.fetch(goal_uid, self.relationships)

        habits: list[Habit] = []
        if self.habits_service:
            for habit_uid in rels.supporting_habit_uids:
                result = await self.habits_service.get(habit_uid)
                if result.is_ok and result.value:
                    habits.append(result.value)

        # Calculate various probability factors
        progress_factor = self._calculate_progress_factor(goal)
        consistency_factor = self._calculate_consistency_factor(habits, lookback_days)
        time_factor = self._calculate_time_factor(goal)
        momentum_factor = self._calculate_momentum_factor(goal, habits, lookback_days)

        # Combine factors using weighted model
        success_probability = self._combine_probability_factors(
            progress_factor, consistency_factor, time_factor, momentum_factor
        )

        # Predict completion date
        predicted_date = self._predict_completion_date(goal, success_probability, momentum_factor)

        # Determine confidence level
        confidence = self._determine_confidence_level(
            lookback_days, len(habits), goal.get_days_remaining()
        )

        # Identify risk and success factors
        risk_factors = self._identify_risk_factors(
            goal, habits, progress_factor, consistency_factor
        )

        success_factors = self._identify_success_factors(
            goal, habits, progress_factor, consistency_factor
        )

        # Generate recommendations
        recommendations = self._generate_prediction_recommendations(
            goal, habits, success_probability, risk_factors
        )

        # Determine trend
        trend = self._determine_trend(goal, habits, lookback_days)

        # Create prediction
        prediction = _GoalPrediction(
            goal_uid=goal.uid,
            goal_title=goal.title,
            success_probability=success_probability,
            predicted_completion_date=predicted_date,
            confidence_level=confidence,
            risk_factors=risk_factors,
            success_factors=success_factors,
            recommended_actions=recommendations,
            trend=trend,
        )

        logger.info(
            f"Generated prediction for goal {goal_uid}: {success_probability:.0%} success probability"
        )
        return Result.ok(prediction)

    @with_error_handling("analyze_habit_impact", error_type="system", uid_param="goal_uid")
    async def analyze_habit_impact(
        self,
        goal_uid: str,
    ) -> Result[list[HabitImpactAnalysis]]:
        """
        Analyze the impact of each habit on goal success.

        Returns list of habit impact analyses sorted by impact score.
        """
        from .goals_intelligence_service import HabitImpactAnalysis as _HabitImpactAnalysis

        if not self.habits_service:
            return Result.fail(
                Errors.system(
                    message="Habits service not available", operation="analyze_habit_impact"
                )
            )

        goal_result = await self.backend.get(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result)
        if not goal_result.value:
            return Result.fail(Errors.not_found(resource="Goal", identifier=goal_uid))

        # GRAPH-NATIVE: Fetch goal relationships from graph
        from core.services.goals.goal_relationships import GoalRelationships

        rels = await GoalRelationships.fetch(goal_uid, self.relationships)

        analyses = []

        for habit_uid in rels.supporting_habit_uids:
            result = await self.habits_service.get(habit_uid)
            if not result.is_ok:
                continue

            habit = result.value
            if not habit:
                continue

            # Calculate impact score
            # GRAPH-NATIVE: habit_weights removed - using default weight
            weight = 1.0  # Default weight for all habits
            consistency = habit.success_rate  # Already 0.0-1.0, not 0-100
            impact_score = weight * consistency

            # Determine criticality
            if weight >= 1.5:
                criticality = "critical"
            elif weight >= 1.0:
                criticality = "important"
            else:
                criticality = "supportive"

            # Calculate consistency gap
            # GRAPH-NATIVE: required_habit_consistency removed - using default threshold
            required = 0.8  # Default 80% consistency requirement
            gap = required - consistency

            analysis = _HabitImpactAnalysis(
                habit_uid=habit_uid,
                habit_title=habit.title,
                impact_score=impact_score,
                criticality=criticality,
                current_consistency=consistency,
                required_consistency=required,
                consistency_gap=max(0, gap),
            )

            analyses.append(analysis)

        # Sort by impact score
        analyses.sort(key=attrgetter("impact_score"), reverse=True)

        return Result.ok(analyses)

    @with_error_handling("assess_goal_risk", error_type="system", uid_param="goal_uid")
    async def assess_goal_risk(
        self,
        goal_uid: str,
    ) -> Result[dict[str, Any]]:
        """
        Assess risk factors for goal achievement.

        Returns risk level, factors, recommended actions, and trend
        derived from the goal prediction.
        """
        prediction_result = await self.predict_goal_success(goal_uid=goal_uid)

        if prediction_result.is_error:
            return Result.fail(prediction_result)

        prediction = prediction_result.value

        return Result.ok(
            {
                "goal_uid": goal_uid,
                "risk_level": prediction.risk_level,
                "risk_factors": prediction.risk_factors,
                "recommended_actions": prediction.recommended_actions,
                "trend": prediction.trend,
            }
        )

    @with_error_handling("run_scenario_analysis", error_type="system", uid_param="goal_uid")
    async def run_scenario_analysis(
        self,
        goal_uid: str,
        consistency_adjustments: dict[str, float],
    ) -> Result[GoalPrediction]:
        """
        Run what-if scenario with adjusted habit consistencies.

        Args:
            goal_uid: Goal to analyze
            consistency_adjustments: Dict of habit_uid -> new_consistency (0-1)
        """
        from dataclasses import replace

        from .goals_intelligence_service import GoalPrediction as _GoalPrediction

        if not self.habits_service:
            return Result.fail(
                Errors.system(
                    message="Habits service not available", operation="run_scenario_analysis"
                )
            )

        # Get goal
        goal_result = await self.backend.get(goal_uid)
        if goal_result.is_error:
            return Result.fail(goal_result)
        if not goal_result.value:
            return Result.fail(Errors.not_found(resource="Goal", identifier=goal_uid))
        goal = goal_result.value

        # Fetch relationships from graph
        from core.services.goals.goal_relationships import GoalRelationships

        rels = await GoalRelationships.fetch(goal_uid, self.relationships)

        # Apply adjustments to habits (in memory only)
        adjusted_habits: list[Habit] = []
        for habit_uid in rels.supporting_habit_uids:
            result = await self.habits_service.get(habit_uid)
            if result.is_ok:
                habit = result.value
                if not habit:
                    continue
                if habit_uid in consistency_adjustments:
                    # Create adjusted version with new success_rate
                    habit = replace(habit, success_rate=consistency_adjustments[habit_uid])
                adjusted_habits.append(habit)

        # Recalculate with adjusted values
        consistency_factor = self._calculate_consistency_factor(adjusted_habits, 30)
        progress_factor = self._calculate_progress_factor(goal)
        time_factor = self._calculate_time_factor(goal)
        momentum_factor = 0.5  # Neutral for scenario

        success_probability = self._combine_probability_factors(
            progress_factor, consistency_factor, time_factor, momentum_factor
        )

        prediction = _GoalPrediction(
            goal_uid=goal.uid,
            goal_title=f"{goal.title} (Scenario)",
            success_probability=success_probability,
            predicted_completion_date=self._predict_completion_date(
                goal, success_probability, momentum_factor
            ),
            confidence_level="medium",  # Scenarios have medium confidence
            risk_factors=[],
            success_factors=[],
            recommended_actions=["This is a what-if scenario"],
            trend="stable",
        )

        return Result.ok(prediction)

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def _calculate_progress_factor(self, goal: Goal) -> float:
        """Calculate progress factor based on current vs expected progress.

        Uses MetricsCalculator.sigmoid_scale for smooth scaling.
        Returns value between 0.0 and 1.0.
        """
        if not goal.target_date or not goal.start_date:
            return 0.5  # No deadline or start date, neutral factor

        total_days = (goal.target_date - goal.start_date).days
        elapsed_days = (date.today() - goal.start_date).days

        if total_days <= 0:
            return 0.0

        # Expected progress based on linear progression
        expected_progress = (elapsed_days / total_days) * 100
        actual_progress = goal.calculate_progress()

        # Calculate factor with sigmoid function for smooth scaling
        diff = actual_progress - expected_progress

        return MetricsCalculator.sigmoid_scale(
            value=diff,
            midpoint=0.0,  # When on schedule (diff=0), factor = 0.5
            steepness=0.1,  # Gentle slope for progress differences
            output_range=(0.0, 1.0),
        )

    def _calculate_consistency_factor(self, habits: list[Habit], _lookback_days: int) -> float:
        """Calculate consistency factor based on habit performance.

        Uses MetricsCalculator.weighted_average for consistent calculation.
        Returns value between 0.0 and 1.0.
        """
        if not habits:
            return 0.5  # No habits, neutral factor

        # Priority weight mapping
        priority_weights = {"high": 1.5, "medium": 1.0, "low": 0.5}

        def get_priority_weight(habit: Habit) -> float:
            if habit.priority:
                return priority_weights.get(habit.priority.lower(), 1.0)
            return 1.0

        def get_normalized_success_rate(habit: Any) -> float:
            # Habit.success_rate is already 0.0-1.0 (completions/attempts)
            return habit.success_rate

        result = MetricsCalculator.weighted_average(
            items=habits,
            value_fn=get_normalized_success_rate,
            weight_fn=get_priority_weight,
        )

        return result if result > 0 else 0.5

    def _calculate_time_factor(self, goal: Goal) -> float:
        """Calculate time pressure factor.

        Uses logarithmic scale: more time remaining = higher success probability.
        Returns value between 0.1 and 1.0.
        """
        days_remaining = goal.get_days_remaining()
        if days_remaining is None:
            return 0.8  # No deadline, good factor

        if days_remaining <= 0:
            return 0.1  # Past deadline

        # Use logarithmic scale for time factor
        factor = math.log(days_remaining + 1) / math.log(365)

        return MetricsCalculator.clamp(factor, min_val=0.1, max_val=1.0)

    def _calculate_momentum_factor(
        self, goal: Goal, habits: list[Habit], _lookback_days: int
    ) -> float:
        """Calculate momentum based on recent trends."""
        # Calculate recent progress rate (simplified)
        days_elapsed = (date.today() - goal.start_date).days if goal.start_date else 1
        recent_progress_rate = goal.calculate_progress() / max(days_elapsed, 1)

        # Calculate habit streak momentum
        streak_momentum = 0.0
        for habit in habits:
            if habit.current_streak > 7:
                streak_momentum += 0.2
            elif habit.current_streak > 3:
                streak_momentum += 0.1

        return min(1.0, recent_progress_rate / 100 + streak_momentum)

    def _combine_probability_factors(
        self, progress: float, consistency: float, time: float, momentum: float
    ) -> float:
        """Combine all factors into final probability.

        Uses MetricsCalculator.combine_weighted_factors with non-linear scaling.
        Returns value between 0.05 and 0.95.
        """
        factors = {
            "progress": progress,
            "consistency": consistency,
            "time": time,
            "momentum": momentum,
        }
        weights = {"progress": 0.35, "consistency": 0.35, "time": 0.15, "momentum": 0.15}

        probability = MetricsCalculator.combine_weighted_factors(
            factors=factors,
            weights=weights,
            normalize=True,
        )

        # Apply non-linear scaling for more realistic probabilities
        if probability > 0.8:
            probability = 0.8 + (probability - 0.8) * 0.5
        elif probability < 0.2:
            probability = 0.2 * probability

        return MetricsCalculator.clamp(probability, min_val=0.05, max_val=0.95)

    def _predict_completion_date(
        self, goal: Goal, success_probability: float, momentum: float
    ) -> date | None:
        """Predict when the goal will be completed."""
        if goal.calculate_progress() >= 100:
            return date.today()

        if success_probability < 0.3:
            return None  # Unlikely to complete

        if not goal.start_date:
            return goal.target_date  # No start date, use target as best guess

        days_elapsed = (date.today() - goal.start_date).days
        if days_elapsed <= 0:
            return goal.target_date

        daily_rate = goal.calculate_progress() / days_elapsed

        # Adjust rate based on momentum
        adjusted_rate = daily_rate * (0.5 + momentum)

        if adjusted_rate <= 0:
            return None

        # Calculate days needed
        remaining_progress = 100 - goal.calculate_progress()
        days_needed = int(remaining_progress / adjusted_rate)

        # Add buffer based on success probability
        buffer = int(days_needed * (1 - success_probability) * 0.5)

        predicted_date = date.today() + timedelta(days=days_needed + buffer)

        # Don't predict beyond target date if high probability
        if goal.target_date and success_probability > 0.7:
            return min(predicted_date, goal.target_date)

        return predicted_date

    def _determine_confidence_level(
        self, data_points: int, habit_count: int, days_remaining: int | None
    ) -> str:
        """Determine confidence level in the prediction."""
        confidence_score = 0

        # More data = higher confidence
        if data_points >= 30:
            confidence_score += 3
        elif data_points >= 14:
            confidence_score += 2
        else:
            confidence_score += 1

        # More habits = more reliable prediction
        if habit_count >= 3:
            confidence_score += 2
        elif habit_count >= 1:
            confidence_score += 1

        # Reasonable time remaining = higher confidence
        if days_remaining and 30 <= days_remaining <= 180:
            confidence_score += 2
        elif days_remaining and days_remaining > 7:
            confidence_score += 1

        if confidence_score >= 6:
            return "high"
        elif confidence_score >= 3:
            return "medium"
        else:
            return "low"

    def _identify_risk_factors(
        self, goal: Goal, habits: list[Habit], progress_factor: float, consistency_factor: float
    ) -> list[str]:
        """Identify factors that might prevent goal achievement."""
        risks = []

        if progress_factor < 0.4:
            risks.append("Behind schedule - need to accelerate progress")

        if consistency_factor < 0.5:
            risks.append("Low habit consistency threatening goal achievement")

        days_remaining = goal.get_days_remaining()
        if days_remaining and days_remaining < 30:
            risks.append("Less than 30 days remaining - time pressure high")

        # Check for broken streaks
        broken_streaks = sum(1 for h in habits if h.current_streak == 0)
        if broken_streaks > len(habits) / 2:
            risks.append("Multiple broken habit streaks")

        # Check for low-performing critical habits (success_rate is 0.0-1.0)
        critical_habits = [h for h in habits if h.success_rate < 0.5]
        if critical_habits:
            risks.append(f"{len(critical_habits)} critical habits underperforming")

        return risks

    def _identify_success_factors(
        self, goal: Goal, habits: list[Habit], progress_factor: float, consistency_factor: float
    ) -> list[str]:
        """Identify factors supporting goal achievement."""
        factors = []

        if progress_factor > 0.7:
            factors.append("Ahead of schedule")

        if consistency_factor > 0.8:
            factors.append("Strong habit consistency")

        # Check for strong streaks
        strong_streaks = sum(1 for h in habits if h.current_streak > 14)
        if strong_streaks > 0:
            factors.append(f"{strong_streaks} habits with 2+ week streaks")

        if goal.calculate_progress() > 50:
            factors.append("Over halfway to goal")

        days_remaining = goal.get_days_remaining()
        if days_remaining and days_remaining > 90:
            factors.append("Plenty of time remaining")

        return factors

    def _generate_prediction_recommendations(
        self,
        goal: Goal,
        habits: list[Habit],
        success_probability: float,
        _risk_factors: list[str],
    ) -> list[str]:
        """Generate actionable recommendations to improve success probability."""
        # Find weakest habit for targeted recommendations
        weakest_habit = min(habits, key=attrgetter("success_rate")) if habits else None
        inconsistent = [h for h in habits if h.success_rate < 0.7]
        days_remaining = goal.get_days_remaining()
        has_long_habits = any((h.duration_minutes or 0) > 45 for h in habits)

        return (
            RecommendationEngine()
            .with_metrics({"success_probability": success_probability})
            # Goal at risk (< 0.5)
            .add_conditional(
                success_probability < 0.5,
                "Focus exclusively on this goal for next 2 weeks",
            )
            .add_conditional(
                success_probability < 0.5 and weakest_habit is not None,
                f"Fix '{weakest_habit.title}' - currently at {weakest_habit.success_rate * 100:.0f}%"
                if weakest_habit
                else "",
            )
            .add_conditional(
                success_probability < 0.5 and days_remaining is not None and days_remaining < 60,
                "Consider extending deadline or reducing scope",
            )
            # Goal needs attention (0.5 - 0.7)
            .add_conditional(
                0.5 <= success_probability < 0.7,
                "Increase habit frequency for 1-2 weeks",
            )
            .add_conditional(
                0.5 <= success_probability < 0.7 and len(inconsistent) > 0,
                f"Set reminders for {len(inconsistent)} inconsistent habits",
            )
            # Goal on track (>= 0.7)
            .add_conditional(
                success_probability >= 0.7,
                "Maintain current momentum",
            )
            .add_conditional(
                success_probability >= 0.7 and has_long_habits,
                "Consider optimizing long habit sessions",
            )
            .build()
        )

    def _determine_trend(self, goal: Goal, habits: list[Habit], _lookback_days: int) -> str:
        """Determine if goal achievement probability is improving, stable, or declining."""
        # Calculate actual vs expected progress
        recent_progress = goal.calculate_progress()
        expected_progress = (
            (date.today() - goal.start_date).days
            / max((goal.target_date - goal.start_date).days, 1)
            * 100
            if goal.target_date and goal.start_date
            else 50
        )

        # Check habit trends
        improving_habits = sum(1 for h in habits if h.current_streak > 7)
        declining_habits = sum(1 for h in habits if h.current_streak == 0)

        return compare_progress_to_expected(
            actual_progress=recent_progress,
            expected_progress=expected_progress,
            improving_items=improving_habits,
            declining_items=declining_habits,
        )
