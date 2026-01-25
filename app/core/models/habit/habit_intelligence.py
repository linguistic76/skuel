"""
Habit Intelligence Entities - Revolutionary Enhancement
======================================================

Persistent intelligence entities that transform Habits from static tracking
to adaptive, learning-aware systems that optimize user behavior patterns.

This implements the revolutionary intelligence pattern established in
Knowledge/Learning/Search domains for the Habits domain.

Key Revolutionary Features:
1. Persistent HabitIntelligence entities that learn from user behavior
2. Optimal timing and context intelligence for maximum success
3. Failure pattern analysis and recovery strategy learning
4. Cross-domain integration with Goals, Tasks, and Knowledge
5. Adaptive habit optimization through relationship intelligence
"""

from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from operator import itemgetter
from typing import Any


class HabitCompletionContext(str, Enum):
    """Contexts in which habits are completed."""

    HOME = "home"
    WORK = "work"
    GYM = "gym"
    COMMUTE = "commute"
    MORNING_ROUTINE = "morning_routine"
    EVENING_ROUTINE = "evening_routine"
    TRAVEL = "travel"
    WEEKEND = "weekend"
    SOCIAL = "social"
    ALONE = "alone"


class EnergyLevel(str, Enum):
    """User energy levels for habit execution optimization."""

    VERY_LOW = "very_low"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"


class FailureReason(str, Enum):
    """Common reasons for habit failure."""

    FORGOT = "forgot"
    NO_TIME = "no_time"
    LOW_ENERGY = "low_energy"
    NO_MOTIVATION = "no_motivation"
    CONFLICTING_PRIORITY = "conflicting_priority"
    ENVIRONMENTAL_BARRIER = "environmental_barrier"
    SOCIAL_PRESSURE = "social_pressure"
    ILLNESS = "illness"
    TRAVEL_DISRUPTION = "travel_disruption"
    EMOTIONAL_STATE = "emotional_state"


@dataclass(frozen=True)
class HabitIntelligence:
    """
    Persistent Habit Intelligence Entity.

    Learns from user behavior patterns to optimize habit execution,
    timing, context, and success strategies. Replaces static tracking
    with adaptive intelligence that improves through user interaction.
    """

    uid: str
    user_uid: str
    habit_uid: str

    # Timing Intelligence
    optimal_time_patterns: dict[str, float] = field(
        default_factory=dict
    )  # "09:00" -> success_rate,
    day_of_week_patterns: dict[str, float] = field(
        default_factory=dict
    )  # "monday" -> success_rate,
    seasonal_patterns: dict[str, float] = field(default_factory=dict)  # "winter" -> success_rate

    # Context Intelligence
    energy_level_correlations: dict[EnergyLevel, float] = field(
        default_factory=dict
    )  # energy -> success_rate,
    context_success_patterns: dict[HabitCompletionContext, float] = (field(default_factory=dict),)
    weather_impact_analysis: dict[str, float] = field(
        default_factory=dict
    )  # weather_type -> impact

    # Behavioral Intelligence
    effective_cue_patterns: list[str] = (field(default_factory=list),)
    successful_trigger_combinations: list[tuple[str, str]] = (field(default_factory=list),)
    reward_effectiveness_scores: dict[str, float] = field(default_factory=dict)

    # Failure Analysis Intelligence
    failure_pattern_analysis: dict[FailureReason, int] = (field(default_factory=dict),)
    recovery_strategy_effectiveness: dict[str, float] = field(
        default_factory=dict
    )  # strategy -> success_rate,
    streak_breaking_predictors: list[dict[str, Any]] = field(default_factory=list)

    # Progression Intelligence
    difficulty_progression_success: dict[str, float] = field(
        default_factory=dict
    )  # difficulty_level -> success_rate,
    optimal_frequency_learned: dict[str, int] = field(
        default_factory=dict
    )  # context -> optimal_frequency,
    plateau_breakthrough_strategies: list[dict[str, Any]] = field(default_factory=list)

    # Relationship Intelligence
    habit_stacking_effectiveness: dict[str, float] = field(
        default_factory=dict
    )  # other_habit_uid -> synergy,
    goal_contribution_patterns: dict[str, float] = field(
        default_factory=dict
    )  # goal_uid -> contribution,
    knowledge_reinforcement_strength: dict[str, float] = field(
        default_factory=dict
    )  # knowledge_uid -> reinforcement,
    task_integration_success: dict[str, float] = field(
        default_factory=dict
    )  # task_type -> integration

    # Progress Tracking Intelligence (consolidated from Progress domain)
    completion_rate_patterns: dict[str, float] = field(
        default_factory=dict
    )  # time_period -> completion_rate,
    streak_effectiveness_analysis: dict[int, float] = field(
        default_factory=dict
    )  # streak_length -> effectiveness_score,
    mastery_progression_rates: dict[str, float] = field(
        default_factory=dict
    )  # skill_area -> mastery_growth_rate,
    quality_outcome_tracking: dict[str, float] = field(
        default_factory=dict
    )  # execution_quality -> outcome_value,
    session_duration_optimization: dict[str, int] = field(
        default_factory=dict
    )  # context -> optimal_duration_minutes,
    milestone_achievement_patterns: dict[str, datetime] = field(
        default_factory=dict
    )  # milestone -> achievement_date,
    improvement_area_identification: dict[str, float] = field(
        default_factory=dict
    )  # area -> improvement_urgency,
    time_investment_analysis: dict[str, int] = field(
        default_factory=dict
    )  # period -> minutes_invested,
    efficiency_score_tracking: dict[str, float] = field(
        default_factory=dict
    )  # execution_context -> efficiency

    # Evolution Tracking
    intelligence_confidence: float = 0.5  # How confident we are in our patterns,
    total_completions_analyzed: int = 0
    total_failures_analyzed: int = 0
    total_progress_sessions_tracked: int = 0  # New: track progress sessions,
    pattern_recognition_accuracy: float = 0.0
    last_intelligence_update: datetime = field(default_factory=datetime.now)

    # Metadata
    created_at: datetime = (field(default_factory=datetime.now),)
    updated_at: datetime = field(default_factory=datetime.now)

    def get_optimal_execution_time(self) -> time | None:
        """Get the optimal time of day for this habit based on learned patterns."""
        if not self.optimal_time_patterns:
            return None

        best_time_str = max(self.optimal_time_patterns.keys(), key=self.optimal_time_patterns.get)

        try:
            hour, minute = map(int, best_time_str.split(":"))
            return time(hour, minute)
        except (ValueError, AttributeError):
            return None

    def get_optimal_context(self) -> HabitCompletionContext | None:
        """Get the optimal context for habit execution."""
        if not self.context_success_patterns:
            return None

        return max(self.context_success_patterns.keys(), key=self.context_success_patterns.get)

    def get_optimal_energy_level(self) -> EnergyLevel | None:
        """Get the energy level when this habit is most successful."""
        if not self.energy_level_correlations:
            return None

        return max(self.energy_level_correlations.keys(), key=self.energy_level_correlations.get)

    # ==========================================================================
    # PROGRESS TRACKING METHODS (consolidated from Progress domain)
    # ==========================================================================

    def get_completion_rate(self, time_period: str = "weekly") -> float:
        """Get completion rate for specified time period."""
        return self.completion_rate_patterns.get(time_period, 0.0)

    def calculate_streak_effectiveness(self, current_streak: int) -> float:
        """Calculate effectiveness based on current streak length."""
        if current_streak in self.streak_effectiveness_analysis:
            return self.streak_effectiveness_analysis[current_streak]

        # Interpolate or use closest known streak effectiveness
        if not self.streak_effectiveness_analysis:
            return 0.5  # Default

        def _streak_distance(x) -> Any:
            return abs(x - current_streak)

        closest_streak = min(self.streak_effectiveness_analysis.keys(), key=_streak_distance)
        return self.streak_effectiveness_analysis[closest_streak]

    def get_mastery_progression_rate(self, skill_area: str) -> float:
        """Get mastery progression rate for a specific skill area."""
        return self.mastery_progression_rates.get(skill_area, 0.0)

    def predict_quality_outcome(self, execution_quality: str) -> float:
        """Predict outcome value based on execution quality."""
        return self.quality_outcome_tracking.get(execution_quality, 0.5)

    def get_optimal_session_duration(self, context: str) -> int:
        """Get optimal session duration in minutes for given context."""
        return self.session_duration_optimization.get(context, 30)  # Default 30 minutes

    def calculate_efficiency_score(self, execution_context: str) -> float:
        """Calculate efficiency score for given execution context."""
        return self.efficiency_score_tracking.get(execution_context, 0.5)

    def identify_improvement_areas(self) -> list[str]:
        """Identify areas that need improvement based on urgency scores."""
        if not self.improvement_area_identification:
            return []

        # Sort by urgency and return top areas
        sorted_areas = sorted(
            self.improvement_area_identification.items(), key=itemgetter(1), reverse=True
        )
        return [area for area, urgency in sorted_areas if urgency > 0.7]

    def get_time_investment_analysis(self, period: str = "weekly") -> int:
        """Get time investment analysis for specified period."""
        return self.time_investment_analysis.get(period, 0)

    def calculate_overall_progress_score(self) -> float:
        """Calculate overall progress score combining multiple metrics."""
        factors = []

        # Completion rate factor
        weekly_completion = self.get_completion_rate("weekly")
        if weekly_completion > 0:
            factors.append(weekly_completion)

        # Quality factor
        if self.quality_outcome_tracking:
            avg_quality = sum(self.quality_outcome_tracking.values()) / len(
                self.quality_outcome_tracking
            )
            factors.append(avg_quality)

        # Efficiency factor
        if self.efficiency_score_tracking:
            avg_efficiency = sum(self.efficiency_score_tracking.values()) / len(
                self.efficiency_score_tracking
            )
            factors.append(avg_efficiency)

        # Mastery progression factor
        if self.mastery_progression_rates:
            avg_mastery = sum(self.mastery_progression_rates.values()) / len(
                self.mastery_progression_rates
            )
            factors.append(avg_mastery)

        if not factors:
            return 0.5  # Default score

        # Weight by intelligence confidence
        base_score = sum(factors) / len(factors)
        return base_score * self.intelligence_confidence + 0.5 * (1 - self.intelligence_confidence)

    def predict_success_probability(
        self,
        execution_time: time,
        context: HabitCompletionContext,
        energy_level: EnergyLevel,
        day_of_week: str,
    ) -> float:
        """
        Predict probability of success given execution parameters.

        Uses learned patterns to estimate likelihood of successful completion.
        """
        factors = []

        # Time factor
        time_str = f"{execution_time.hour:02d}:{execution_time.minute:02d}"
        if time_str in self.optimal_time_patterns:
            factors.append(self.optimal_time_patterns[time_str])

        # Context factor
        if context in self.context_success_patterns:
            factors.append(self.context_success_patterns[context])

        # Energy factor
        if energy_level in self.energy_level_correlations:
            factors.append(self.energy_level_correlations[energy_level])

        # Day factor
        if day_of_week.lower() in self.day_of_week_patterns:
            factors.append(self.day_of_week_patterns[day_of_week.lower()])

        if not factors:
            return 0.5  # Default probability when no data

        # Weight by intelligence confidence
        base_probability = sum(factors) / len(factors)
        return base_probability * self.intelligence_confidence + 0.5 * (
            1 - self.intelligence_confidence
        )

    def get_failure_prevention_strategies(self) -> list[dict[str, Any]]:
        """Get strategies to prevent common failure patterns."""
        strategies = []

        # Most common failure reasons
        if self.failure_pattern_analysis:
            top_failures = sorted(
                self.failure_pattern_analysis.items(), key=itemgetter(1), reverse=True
            )[:3]

            for failure_reason, count in top_failures:
                # Get effective recovery strategies for this failure type
                relevant_strategies = [
                    strategy
                    for strategy, effectiveness in self.recovery_strategy_effectiveness.items()
                    if effectiveness > 0.6 and failure_reason.value in strategy.lower()
                ]

                if relevant_strategies:
                    strategies.append(
                        {
                            "failure_reason": failure_reason.value,
                            "frequency": count,
                            "prevention_strategies": relevant_strategies[:2],  # Top 2 strategies
                            "confidence": min(1.0, count / max(1, self.total_failures_analyzed)),
                        }
                    )

        return strategies

    def get_habit_stacking_recommendations(self) -> list[dict[str, Any]]:
        """Get recommendations for habit stacking based on learned effectiveness."""
        recommendations = []

        # Sort by effectiveness
        effective_stackings = [
            (habit_uid, effectiveness)
            for habit_uid, effectiveness in self.habit_stacking_effectiveness.items()
            if effectiveness > 0.7
        ]
        effective_stackings.sort(key=itemgetter(1), reverse=True)

        for habit_uid, effectiveness in effective_stackings[:3]:  # Top 3
            recommendations.append(
                {
                    "habit_uid": habit_uid,
                    "stacking_effectiveness": effectiveness,
                    "recommendation": f"Stack with habit {habit_uid} for {effectiveness:.0%} better results",
                    "confidence": self.intelligence_confidence,
                }
            )

        return recommendations

    def get_progression_recommendations(self) -> list[dict[str, Any]]:
        """Get recommendations for habit progression based on success patterns."""
        recommendations = []

        # Analyze difficulty progression
        if len(self.difficulty_progression_success) > 1:
            current_success_rates = list(self.difficulty_progression_success.values())
            avg_success = sum(current_success_rates) / len(current_success_rates)

            if avg_success > 0.8:  # High success rate
                recommendations.append(
                    {
                        "type": "increase_difficulty",
                        "reasoning": "High success rate suggests readiness for increased challenge",
                        "confidence": avg_success * self.intelligence_confidence,
                    }
                )
            elif avg_success < 0.5:  # Low success rate
                recommendations.append(
                    {
                        "type": "decrease_difficulty",
                        "reasoning": "Low success rate suggests need to simplify habit",
                        "confidence": (1 - avg_success) * self.intelligence_confidence,
                    }
                )

        # Frequency optimization
        if self.optimal_frequency_learned:
            most_successful_frequency = max(self.optimal_frequency_learned.values())
            recommendations.append(
                {
                    "type": "optimize_frequency",
                    "recommended_frequency": most_successful_frequency,
                    "reasoning": "Learned optimal frequency from behavior patterns",
                    "confidence": self.intelligence_confidence,
                }
            )

        return recommendations

    def should_suggest_habit_today(
        self, current_context: HabitCompletionContext, current_energy: EnergyLevel, day_of_week: str
    ) -> bool:
        """Determine if habit should be suggested today based on intelligent patterns."""
        success_probability = self.predict_success_probability(
            execution_time=self.get_optimal_execution_time() or time(9, 0),
            context=current_context,
            energy_level=current_energy,
            day_of_week=day_of_week,
        )

        # Suggest if success probability is above threshold
        return success_probability > 0.6 and self.intelligence_confidence > 0.3


@dataclass(frozen=True)
class HabitCompletionIntelligence:
    """
    Intelligence data captured from each habit completion.

    This entity captures the context and outcome of each habit execution
    to feed the learning algorithms in HabitIntelligence.
    """

    uid: str
    habit_uid: str
    user_uid: str

    # Execution Details
    completed_at: datetime
    planned_time: time | None
    actual_time: time
    duration_minutes: int

    # Context
    completion_context: HabitCompletionContext
    energy_level_before: EnergyLevel
    energy_level_after: EnergyLevel
    weather_condition: str | None = None

    # Success Metrics
    completion_quality: int = 5  # 1-5 scale,
    difficulty_experienced: int = 3  # 1-5 scale,
    satisfaction_level: int = 5  # 1-5 scale

    # Environmental Factors
    location: str | None = (None,)

    social_context: str | None = None  # "alone", "with_family", etc.,
    preceding_activity: str | None = None

    # Integration Data
    reinforced_other_habits: list[str] = (field(default_factory=list),)
    contributed_to_goals: list[str] = (field(default_factory=list),)
    applied_knowledge: list[str] = field(default_factory=list)

    # Failure Analysis (if completion_quality < 3)
    obstacles_encountered: list[str] = (field(default_factory=list),)
    failure_reason: FailureReason | None = (None,)

    recovery_strategy_used: str | None = None

    def was_successful(self) -> bool:
        """Determine if this completion was successful based on quality metrics."""
        return self.completion_quality >= 4 and self.satisfaction_level >= 4

    def was_optimal_timing(self) -> bool:
        """Check if execution happened at planned time."""
        if not self.planned_time:
            return True

        planned_minutes = self.planned_time.hour * 60 + self.planned_time.minute
        actual_minutes = self.actual_time.hour * 60 + self.actual_time.minute

        # Within 30 minutes of planned time
        return abs(planned_minutes - actual_minutes) <= 30


# Factory functions for creating habit intelligence entities


def create_habit_intelligence(user_uid: str, habit_uid: str) -> HabitIntelligence:
    """Create initial habit intelligence entity."""
    intelligence_uid = f"habit_intel_{user_uid}_{habit_uid}"

    return HabitIntelligence(uid=intelligence_uid, user_uid=user_uid, habit_uid=habit_uid)


def create_habit_completion_intelligence(
    habit_uid: str, user_uid: str, completion_details: dict[str, Any]
) -> HabitCompletionIntelligence:
    """Create habit completion intelligence from completion event."""
    completion_uid = f"habit_completion_{habit_uid}_{int(datetime.now().timestamp())}"

    return HabitCompletionIntelligence(
        uid=completion_uid,
        habit_uid=habit_uid,
        user_uid=user_uid,
        completed_at=completion_details.get("completed_at", datetime.now()),
        planned_time=completion_details.get("planned_time"),
        actual_time=completion_details.get("actual_time", datetime.now().time()),
        duration_minutes=completion_details.get("duration_minutes", 15),
        completion_context=completion_details.get("context", HabitCompletionContext.HOME),
        energy_level_before=completion_details.get("energy_before", EnergyLevel.MODERATE),
        energy_level_after=completion_details.get("energy_after", EnergyLevel.MODERATE),
        completion_quality=completion_details.get("quality", 5),
        difficulty_experienced=completion_details.get("difficulty", 3),
        satisfaction_level=completion_details.get("satisfaction", 5),
    )
