"""
Tasks Intelligence Entities - Revolutionary Enhancement
======================================================

Persistent intelligence entities that transform Tasks from static scheduling
to adaptive, learning-aware systems that optimize productivity and execution.

This implements the revolutionary intelligence pattern established in
Knowledge/Learning/Search/Habits/Goals domains for the Tasks domain.

Key Revolutionary Features:
1. Persistent TaskIntelligence entities that learn from completion patterns
2. Optimal scheduling and duration intelligence for maximum productivity
3. Procrastination trigger analysis and intervention strategy learning
4. Cross-domain integration with Goals, Habits, and Knowledge
5. Adaptive task optimization through relationship intelligence
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from operator import itemgetter
from typing import Any


class TaskCompletionContext(str, Enum):
    """Contexts in which tasks are completed."""

    FOCUSED_WORK = "focused_work"
    COLLABORATIVE_SESSION = "collaborative_session"
    QUICK_BURST = "quick_burst"
    DEEP_WORK_BLOCK = "deep_work_block"
    BETWEEN_MEETINGS = "between_meetings"
    MORNING_ROUTINE = "morning_routine"
    EVENING_ROUTINE = "evening_routine"
    WEEKEND_PROJECT = "weekend_project"
    DEADLINE_PRESSURE = "deadline_pressure"
    FLOW_STATE = "flow_state"


class EnergyLevel(str, Enum):
    """User energy levels for task execution optimization."""

    VERY_LOW = "very_low"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"


class ProcrastinationTrigger(str, Enum):
    """Common reasons for task procrastination."""

    UNCLEAR_REQUIREMENTS = "unclear_requirements"
    OVERWHELMING_SCOPE = "overwhelming_scope"
    LACK_OF_MOTIVATION = "lack_of_motivation"
    PERFECTIONISM = "perfectionism"
    FEAR_OF_FAILURE = "fear_of_failure"
    BORING_REPETITIVE = "boring_repetitive"
    TOO_DIFFICULT = "too_difficult"
    MISSING_RESOURCES = "missing_resources"
    COMPETING_PRIORITIES = "competing_priorities"
    DISTRACTION_PRONE = "distraction_prone"


@dataclass(frozen=True)
class TaskIntelligence:
    """
    Persistent Task Intelligence Entity.

    Learns from user completion patterns to optimize task scheduling,
    duration estimation, procrastination prevention, and productivity.
    Replaces static task management with adaptive intelligence that
    improves through user interaction.
    """

    uid: str
    user_uid: str
    task_category: str  # Intelligence by task type/category

    # Scheduling Intelligence
    optimal_scheduling_patterns: dict[str, float] = field(
        default_factory=dict
    )  # time_slot -> productivity_score,
    energy_task_matching: dict[EnergyLevel, list[str]] = field(
        default_factory=dict
    )  # energy_level -> optimal_task_types,
    context_productivity_patterns: dict[TaskCompletionContext, float] = field(
        default_factory=dict
    )  # context -> productivity

    # Duration Intelligence
    duration_estimation_accuracy: dict[str, float] = field(
        default_factory=dict
    )  # task_type -> estimation_accuracy,
    actual_vs_estimated_patterns: dict[str, float] = field(
        default_factory=dict
    )  # task_type -> actual/estimated_ratio,
    complexity_duration_correlations: dict[str, int] = field(
        default_factory=dict
    )  # complexity_level -> avg_minutes

    # Completion Intelligence
    procrastination_trigger_analysis: dict[ProcrastinationTrigger, int] = field(
        default_factory=dict
    )  # trigger -> frequency,
    intervention_strategy_effectiveness: dict[str, float] = field(
        default_factory=dict
    )  # strategy -> success_rate,
    completion_momentum_patterns: list[tuple[str, str]] = field(
        default_factory=list
    )  # (task_sequence, momentum_effect)

    # Dependency Intelligence
    prerequisite_optimization_patterns: dict[str, list[str]] = field(
        default_factory=dict
    )  # goal -> optimal_task_order,
    knowledge_application_effectiveness: dict[str, float] = field(
        default_factory=dict
    )  # knowledge_uid -> application_success,
    blocking_factor_analysis: dict[str, list[str]] = field(
        default_factory=dict
    )  # blocker -> resolution_strategies

    # Prioritization Intelligence
    impact_prediction_patterns: dict[str, float] = field(
        default_factory=dict
    )  # task_characteristics -> actual_impact,
    urgency_assessment_accuracy: dict[str, float] = field(
        default_factory=dict
    )  # urgency_factors -> time_pressure_reality,
    goal_contribution_optimization: dict[str, float] = field(
        default_factory=dict
    )  # task_type -> goal_advancement

    # Context Intelligence
    time_of_day_productivity: dict[str, float] = field(
        default_factory=dict
    )  # hour -> productivity_score,
    day_of_week_patterns: dict[str, float] = field(
        default_factory=dict
    )  # weekday -> completion_rate,
    workload_capacity_patterns: dict[str, int] = field(
        default_factory=dict
    )  # day_type -> max_tasks

    # Integration Intelligence
    habit_reinforcement_effectiveness: dict[str, float] = field(
        default_factory=dict
    )  # habit_uid -> task_support,
    goal_progress_acceleration: dict[str, float] = field(
        default_factory=dict
    )  # task_approach -> goal_velocity,
    knowledge_mastery_contribution: dict[str, float] = field(
        default_factory=dict
    )  # task_type -> mastery_gain

    # Flow State Intelligence
    flow_state_triggers: list[dict[str, Any]] = (field(default_factory=list),)
    distraction_vulnerability_patterns: dict[str, float] = field(
        default_factory=dict
    )  # context -> distraction_risk,
    focus_session_optimization: dict[str, int] = field(
        default_factory=dict
    )  # task_type -> optimal_session_minutes

    # Progress Tracking Intelligence (consolidated from Progress domain)
    completion_rate_patterns: dict[str, float] = field(
        default_factory=dict
    )  # time_period -> completion_rate,
    quality_outcome_tracking: dict[str, float] = field(
        default_factory=dict
    )  # task_quality -> outcome_value,
    efficiency_score_tracking: dict[str, float] = field(
        default_factory=dict
    )  # execution_context -> efficiency,
    time_investment_analysis: dict[str, int] = field(
        default_factory=dict
    )  # period -> minutes_invested,
    milestone_achievement_patterns: dict[str, datetime] = field(
        default_factory=dict
    )  # milestone -> achievement_date,
    session_duration_optimization: dict[str, int] = field(
        default_factory=dict
    )  # task_type -> optimal_duration_minutes,
    improvement_area_identification: dict[str, float] = field(
        default_factory=dict
    )  # area -> improvement_urgency,
    mastery_progression_rates: dict[str, float] = field(
        default_factory=dict
    )  # skill_area -> mastery_growth_rate

    # Evolution Tracking
    intelligence_confidence: float = 0.5  # How confident we are in our patterns,
    total_tasks_analyzed: int = 0
    total_completions_analyzed: int = 0
    total_progress_sessions_tracked: int = 0  # New: track progress sessions,
    pattern_recognition_accuracy: float = 0.0
    last_intelligence_update: datetime = field(default_factory=datetime.now)

    # Metadata
    created_at: datetime = (field(default_factory=datetime.now),)
    updated_at: datetime = field(default_factory=datetime.now)

    def get_optimal_scheduling_time(self) -> str | None:
        """Get the optimal time of day for this task category based on learned patterns."""
        if not self.optimal_scheduling_patterns:
            return None

        def get_score(time_slot: str) -> float:
            return self.optimal_scheduling_patterns.get(time_slot, 0.0)

        return max(self.optimal_scheduling_patterns.keys(), key=get_score)

    def get_optimal_context(self) -> TaskCompletionContext | None:
        """Get the optimal context for task execution."""
        if not self.context_productivity_patterns:
            return None

        def get_productivity(context: TaskCompletionContext) -> float:
            return self.context_productivity_patterns.get(context, 0.0)

        return max(self.context_productivity_patterns.keys(), key=get_productivity)

    def get_optimal_energy_level(self) -> EnergyLevel | None:
        """Get the energy level when this task type is most productive."""
        if not self.energy_task_matching:
            return None

        # Find energy level where this task category appears most effectively
        for energy, task_types in self.energy_task_matching.items():
            if self.task_category in task_types:
                return energy
        return None

    # ==========================================================================
    # PROGRESS TRACKING METHODS (consolidated from Progress domain)
    # ==========================================================================

    def get_completion_rate(self, time_period: str = "weekly") -> float:
        """Get completion rate for specified time period."""
        return self.completion_rate_patterns.get(time_period, 0.0)

    def calculate_quality_outcome(self, task_quality: str) -> float:
        """Calculate expected outcome based on task quality."""
        return self.quality_outcome_tracking.get(task_quality, 0.5)

    def calculate_efficiency_score(self, execution_context: str) -> float:
        """Calculate efficiency score for given execution context."""
        return self.efficiency_score_tracking.get(execution_context, 0.5)

    def get_time_investment_analysis(self, period: str = "weekly") -> int:
        """Get time investment analysis for specified period."""
        return self.time_investment_analysis.get(period, 0)

    def get_optimal_session_duration(self, task_type: str) -> int:
        """Get optimal session duration in minutes for given task type."""
        return self.session_duration_optimization.get(task_type, 60)  # Default 60 minutes

    def get_mastery_progression_rate(self, skill_area: str) -> float:
        """Get mastery progression rate for a specific skill area."""
        return self.mastery_progression_rates.get(skill_area, 0.0)

    def identify_improvement_areas(self) -> list[str]:
        """Identify areas that need improvement based on urgency scores."""
        if not self.improvement_area_identification:
            return []

        # Sort by urgency and return top areas
        sorted_areas = sorted(
            self.improvement_area_identification.items(), key=itemgetter(1), reverse=True
        )
        return [area for area, urgency in sorted_areas if urgency > 0.7]

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

    def predict_completion_probability(
        self,
        scheduled_time: str,
        context: TaskCompletionContext,
        energy_level: EnergyLevel,
        current_workload: int,
    ) -> float:
        """
        Predict probability of task completion given execution parameters.

        Uses learned patterns to estimate likelihood of successful completion.
        """
        factors = []

        # Time factor
        if scheduled_time in self.optimal_scheduling_patterns:
            factors.append(self.optimal_scheduling_patterns[scheduled_time])

        # Context factor
        if context in self.context_productivity_patterns:
            factors.append(self.context_productivity_patterns[context])

        # Energy factor
        if energy_level in self.energy_task_matching:
            if self.task_category in self.energy_task_matching[energy_level]:
                factors.append(0.8)  # Good energy match
            else:
                factors.append(0.4)  # Poor energy match

        # Workload factor
        if current_workload <= 3:
            factors.append(0.9)  # Light workload
        elif current_workload <= 6:
            factors.append(0.7)  # Moderate workload
        else:
            factors.append(0.4)  # Heavy workload

        if not factors:
            return 0.5  # Default probability when no data

        # Weight by intelligence confidence
        base_probability = sum(factors) / len(factors)
        return base_probability * self.intelligence_confidence + 0.5 * (
            1 - self.intelligence_confidence
        )

    def get_duration_estimate(self, task_complexity: str = "moderate") -> int | None:
        """Get intelligent duration estimate based on learned patterns."""
        if task_complexity in self.complexity_duration_correlations:
            base_estimate = self.complexity_duration_correlations[task_complexity]

            # Adjust based on estimation accuracy
            if self.task_category in self.duration_estimation_accuracy:
                accuracy = self.duration_estimation_accuracy[self.task_category]
                # If historically underestimated, increase estimate
                if accuracy < 0.8:
                    base_estimate = int(base_estimate * 1.2)

            return base_estimate

        # Fallback defaults
        complexity_defaults = {
            "trivial": 15,
            "simple": 30,
            "moderate": 60,
            "complex": 120,
            "very_complex": 240,
        }
        return complexity_defaults.get(task_complexity, 60)

    def get_procrastination_prevention_strategies(self) -> list[dict[str, Any]]:
        """Get strategies to prevent common procrastination patterns."""
        strategies = []

        # Most common procrastination triggers
        if self.procrastination_trigger_analysis:
            top_triggers = sorted(
                self.procrastination_trigger_analysis.items(), key=itemgetter(1), reverse=True
            )[:3]

            for trigger, count in top_triggers:
                # Get effective intervention strategies for this trigger
                relevant_strategies = [
                    strategy
                    for strategy, effectiveness in self.intervention_strategy_effectiveness.items()
                    if effectiveness > 0.6 and trigger.value in strategy.lower()
                ]

                if relevant_strategies:
                    strategies.append(
                        {
                            "procrastination_trigger": trigger.value,
                            "frequency": count,
                            "intervention_strategies": relevant_strategies[:2],  # Top 2 strategies
                            "confidence": min(1.0, count / max(1, self.total_tasks_analyzed)),
                        }
                    )

        return strategies

    def get_optimal_task_sequence(self) -> list[dict[str, Any]]:
        """Get optimal task sequencing based on momentum patterns."""
        recommendations = []

        for sequence, momentum_effect in self.completion_momentum_patterns:
            if "positive" in momentum_effect.lower():
                task_a, task_b = sequence.split(" -> ")
                recommendations.append(
                    {
                        "sequence": f"{task_a} followed by {task_b}",
                        "momentum_effect": momentum_effect,
                        "recommendation": f"Complete {task_a} before {task_b} for better momentum",
                        "confidence": self.intelligence_confidence,
                    }
                )

        return recommendations[:3]  # Top 3 sequences

    def get_focus_optimization_suggestions(self) -> list[dict[str, Any]]:
        """Get suggestions for optimizing focus and flow state."""
        suggestions = []

        # Flow state triggers
        suggestions.extend(
            [
                {
                    "type": "flow_trigger",
                    "trigger": trigger.get("trigger_type", "Unknown"),
                    "conditions": trigger.get("conditions", []),
                    "effectiveness": trigger.get("effectiveness", 0.5),
                    "confidence": self.intelligence_confidence,
                }
                for trigger in self.flow_state_triggers
            ]
        )

        # Optimal session durations
        if self.focus_session_optimization:
            optimal_duration = max(self.focus_session_optimization.values())
            suggestions.append(
                {
                    "type": "session_duration",
                    "optimal_minutes": optimal_duration,
                    "reasoning": "Based on learned focus patterns",
                    "confidence": self.intelligence_confidence,
                }
            )

        return suggestions

    def get_cross_domain_integration_opportunities(self) -> list[dict[str, Any]]:
        """Get opportunities for cross-domain integration based on effectiveness."""
        opportunities = []

        # Habit reinforcement
        if self.habit_reinforcement_effectiveness:
            effective_habits = [
                (habit_uid, effectiveness)
                for habit_uid, effectiveness in self.habit_reinforcement_effectiveness.items()
                if effectiveness > 0.7
            ]
            effective_habits.sort(key=itemgetter(1), reverse=True)

            for habit_uid, effectiveness in effective_habits[:2]:
                opportunities.append(
                    {
                        "type": "habit_reinforcement",
                        "habit_uid": habit_uid,
                        "effectiveness": effectiveness,
                        "recommendation": f"Schedule tasks to reinforce {habit_uid}",
                        "confidence": self.intelligence_confidence,
                    }
                )

        # Goal progress acceleration
        if self.goal_progress_acceleration:
            accelerating_approaches = [
                (approach, velocity)
                for approach, velocity in self.goal_progress_acceleration.items()
                if velocity > 0.8
            ]
            accelerating_approaches.sort(key=itemgetter(1), reverse=True)

            for approach, velocity in accelerating_approaches[:2]:
                opportunities.append(
                    {
                        "type": "goal_acceleration",
                        "approach": approach,
                        "velocity_multiplier": velocity,
                        "recommendation": f"Use {approach} approach for faster goal progress",
                        "confidence": self.intelligence_confidence,
                    }
                )

        return opportunities

    def should_suggest_task_breakdown(
        self, estimated_duration: int, complexity_level: str, historical_completion_rate: float
    ) -> bool:
        """Determine if task should be broken down based on intelligent patterns."""

        # Large tasks have lower completion rates
        if estimated_duration > 120:  # More than 2 hours
            return True

        # Complex tasks with poor historical completion
        if complexity_level in ["complex", "very_complex"] and historical_completion_rate < 0.6:
            return True

        # Based on learned patterns for this task category
        if self.task_category in self.duration_estimation_accuracy:
            accuracy = self.duration_estimation_accuracy[self.task_category]
            if accuracy < 0.7 and estimated_duration > 60:
                return True

        return False

    def get_workload_optimization_suggestions(self) -> dict[str, Any]:
        """Get suggestions for optimal daily/weekly workload based on capacity patterns."""
        suggestions = {}

        if self.workload_capacity_patterns:
            # Average capacity across day types
            avg_capacity = sum(self.workload_capacity_patterns.values()) / len(
                self.workload_capacity_patterns
            )

            suggestions["optimal_daily_tasks"] = int(avg_capacity)
            suggestions["high_capacity_days"] = [
                day
                for day, capacity in self.workload_capacity_patterns.items()
                if capacity > avg_capacity * 1.2
            ]
            suggestions["low_capacity_days"] = [
                day
                for day, capacity in self.workload_capacity_patterns.items()
                if capacity < avg_capacity * 0.8
            ]

        if self.day_of_week_patterns:
            # Best days for task completion
            best_days = sorted(self.day_of_week_patterns.items(), key=itemgetter(1), reverse=True)[
                :3
            ]

            suggestions["high_productivity_days"] = [day for day, rate in best_days]

        return suggestions


@dataclass(frozen=True)
class TaskCompletionIntelligence:
    """
    Intelligence data captured from each task completion.

    This entity captures the context and outcome of each task execution
    to feed the learning algorithms in TaskIntelligence.
    """

    uid: str
    task_uid: str
    user_uid: str

    # Execution Details
    completed_at: datetime
    planned_duration: int  # minutes
    actual_duration: int  # minutes
    completion_context: TaskCompletionContext
    energy_level_before: EnergyLevel
    energy_level_after: EnergyLevel

    # Optional fields with defaults
    scheduled_time: str | None = None  # "09:00", "14:30", etc.,
    focus_quality: int = 5  # 1-5 scale

    # Success Metrics
    completion_quality: int = 5  # 1-5 scale,
    effort_level: int = 3  # 1-5 scale,
    satisfaction_level: int = 5  # 1-5 scale,
    met_requirements: bool = True

    # Environmental Factors
    location: str | None = (None,)

    tools_used: list[str] = (field(default_factory=list),)
    interruptions_count: int = 0

    distractions_encountered: list[str] = field(default_factory=list)

    # Productivity Factors
    flow_state_achieved: bool = False

    procrastination_overcome: bool = False
    momentum_from_previous: bool = False

    created_momentum_for_next: bool = False

    # Integration Data
    reinforced_habits: list[str] = (field(default_factory=list),)
    contributed_to_goals: list[str] = (field(default_factory=list),)
    applied_knowledge: list[str] = (field(default_factory=list),)
    unlocked_dependencies: list[str] = field(default_factory=list)

    # Challenge and Learning
    obstacles_overcome: list[str] = (field(default_factory=list),)
    skills_improved: list[str] = (field(default_factory=list),)
    lessons_learned: list[str] = field(default_factory=list)

    def was_successful(self) -> bool:
        """Determine if this completion was successful based on quality metrics."""
        return (
            self.completion_quality >= 4 and self.satisfaction_level >= 4 and self.met_requirements
        )

    def was_efficient(self) -> bool:
        """Check if task was completed efficiently (within estimated time)."""
        if self.planned_duration <= 0:
            return True
        return self.actual_duration <= self.planned_duration * 1.2  # 20% buffer

    def get_productivity_score(self) -> float:
        """Calculate overall productivity score for this completion."""
        factors = [
            self.completion_quality / 5.0,
            self.satisfaction_level / 5.0,
            self.focus_quality / 5.0,
            1.0 if self.met_requirements else 0.0,
            1.0 if self.was_efficient() else 0.5,
            1.0 if self.flow_state_achieved else 0.0,
        ]

        # Penalties for issues
        interruption_penalty = min(0.2, self.interruptions_count * 0.05)
        distraction_penalty = min(0.2, len(self.distractions_encountered) * 0.05)

        base_score = sum(factors) / len(factors)
        return max(0.0, base_score - interruption_penalty - distraction_penalty)


# Factory functions for creating task intelligence entities


def create_task_intelligence(
    user_uid: str,
    task_category: str,
    optimal_scheduling_patterns: dict[str, Any] | None = None,
    energy_task_matching: dict[EnergyLevel, float] | None = None,
    context_productivity_patterns: dict[str, float] | None = None,
) -> TaskIntelligence:
    """Create initial task intelligence entity for a category with optional intelligence data."""
    intelligence_uid = f"task_intel_{user_uid}_{task_category}"

    return TaskIntelligence(
        uid=intelligence_uid,
        user_uid=user_uid,
        task_category=task_category,
        optimal_scheduling_patterns=optimal_scheduling_patterns or {},
        energy_task_matching=energy_task_matching or {},
        context_productivity_patterns=context_productivity_patterns or {},
    )


def create_task_completion_intelligence(
    task_uid: str, user_uid: str, completion_details: dict[str, Any]
) -> TaskCompletionIntelligence:
    """Create task completion intelligence from completion event."""
    completion_uid = f"task_completion_{task_uid}_{int(datetime.now().timestamp())}"

    return TaskCompletionIntelligence(
        uid=completion_uid,
        task_uid=task_uid,
        user_uid=user_uid,
        completed_at=completion_details.get("completed_at", datetime.now()),
        planned_duration=completion_details.get("planned_duration", 60),
        actual_duration=completion_details.get("actual_duration", 60),
        scheduled_time=completion_details.get("scheduled_time"),
        completion_context=completion_details.get("context", TaskCompletionContext.FOCUSED_WORK),
        energy_level_before=completion_details.get("energy_before", EnergyLevel.MODERATE),
        energy_level_after=completion_details.get("energy_after", EnergyLevel.MODERATE),
        focus_quality=completion_details.get("focus_quality", 5),
        completion_quality=completion_details.get("quality", 5),
        effort_level=completion_details.get("effort", 3),
        satisfaction_level=completion_details.get("satisfaction", 5),
        met_requirements=completion_details.get("met_requirements", True),
        flow_state_achieved=completion_details.get("flow_state", False),
        procrastination_overcome=completion_details.get("overcame_procrastination", False),
    )
