"""
Goals Intelligence Entities - Revolutionary Enhancement
=====================================================

Persistent intelligence entities that transform Goals from static tracking
to adaptive, learning-aware systems that optimize achievement strategies.

This implements the revolutionary intelligence pattern established in
Knowledge/Learning/Search/Habits domains for the Goals domain.

Key Revolutionary Features:
1. Persistent GoalIntelligence entities that learn from achievement patterns
2. Optimal timeline and strategy intelligence for maximum success
3. Obstacle pattern analysis and prevention strategy learning
4. Cross-domain integration with Habits, Tasks, and Knowledge
5. Adaptive goal optimization through relationship intelligence
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from operator import itemgetter
from typing import Any


class GoalAchievementContext(str, Enum):
    """Contexts in which goals are achieved."""

    SOLO_WORK = "solo_work"
    COLLABORATIVE = "collaborative"
    INTENSIVE_FOCUS = "intensive_focus"
    CONSISTENT_DAILY = "consistent_daily"
    WEEKEND_SPRINT = "weekend_sprint"
    STRUCTURED_COURSE = "structured_course"
    SELF_DIRECTED = "self_directed"
    MENTORED = "mentored"
    PROJECT_BASED = "project_based"
    RESEARCH_BASED = "research_based"


class MotivationLevel(str, Enum):
    """User motivation levels for goal pursuit optimization."""

    VERY_LOW = "very_low"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"


class ObstacleReason(str, Enum):
    """Common reasons for goal obstacles."""

    UNREALISTIC_TIMELINE = "unrealistic_timeline"
    INSUFFICIENT_KNOWLEDGE = "insufficient_knowledge"
    COMPETING_PRIORITIES = "competing_priorities"
    LACK_OF_MOTIVATION = "lack_of_motivation"
    POOR_PLANNING = "poor_planning"
    EXTERNAL_CIRCUMSTANCES = "external_circumstances"
    SCOPE_CREEP = "scope_creep"
    RESOURCE_CONSTRAINTS = "resource_constraints"
    SKILL_GAPS = "skill_gaps"
    PROCRASTINATION = "procrastination"


@dataclass(frozen=True)
class GoalIntelligence:
    """
    Persistent Goal Intelligence Entity.

    Learns from user achievement patterns to optimize goal setting,
    timeline estimation, strategy selection, and success probability.
    Replaces static goal tracking with adaptive intelligence that
    improves through user interaction.
    """

    uid: str
    user_uid: str
    goal_uid: str

    # Timeline Intelligence
    optimal_timeline_patterns: dict[str, float] = field(
        default_factory=dict
    )  # goal_type -> optimal_duration_weeks
    milestone_effectiveness_scores: dict[str, float] = field(
        default_factory=dict
    )  # milestone_strategy -> success_rate
    progress_velocity_patterns: dict[str, float] = field(
        default_factory=dict
    )  # context -> velocity_per_week

    # Strategy Intelligence
    successful_approach_patterns: list[dict[str, Any]] = field(default_factory=list)
    obstacle_overcome_strategies: dict[ObstacleReason, list[str]] = field(
        default_factory=dict
    )  # obstacle -> strategies
    motivation_sustaining_factors: dict[str, float] = field(
        default_factory=dict
    )  # factor -> impact_score

    # Resource Intelligence
    optimal_time_investment_patterns: dict[str, int] = field(
        default_factory=dict
    )  # phase -> hours_per_week
    energy_allocation_optimization: dict[str, float] = field(
        default_factory=dict
    )  # activity -> energy_efficiency
    skill_gap_bridging_strategies: dict[str, list[str]] = field(
        default_factory=dict
    )  # skill -> learning_path

    # Context Intelligence
    achievement_context_success: dict[GoalAchievementContext, float] = field(default_factory=dict)
    motivation_level_correlations: dict[MotivationLevel, float] = field(default_factory=dict)
    seasonal_achievement_patterns: dict[str, float] = field(
        default_factory=dict
    )  # season -> success_rate

    # Integration Intelligence
    task_contribution_effectiveness: dict[str, float] = field(
        default_factory=dict
    )  # task_type -> goal_progress
    habit_support_correlation: dict[str, float] = field(
        default_factory=dict
    )  # habit_uid -> goal_support
    knowledge_prerequisite_patterns: dict[str, list[str]] = field(
        default_factory=dict
    )  # goal_phase -> knowledge_needed
    principle_alignment_strength: dict[str, float] = field(
        default_factory=dict
    )  # principle_uid -> alignment_strength

    # Failure Analysis Intelligence
    obstacle_pattern_analysis: dict[ObstacleReason, int] = field(default_factory=dict)
    failure_recovery_strategies: dict[str, float] = field(
        default_factory=dict
    )  # recovery_strategy -> success_rate
    revision_success_patterns: list[dict[str, Any]] = field(default_factory=list)

    # Progression Intelligence
    goal_type_success_patterns: dict[str, float] = field(
        default_factory=dict
    )  # goal_type -> success_rate
    optimal_goal_breakdown_patterns: dict[str, int] = field(
        default_factory=dict
    )  # goal_size -> optimal_sub_goals
    achievement_momentum_factors: list[dict[str, Any]] = field(default_factory=list)

    # Evolution Tracking
    intelligence_confidence: float = 0.5  # How confident we are in our patterns
    total_goals_analyzed: int = 0
    total_achievements_analyzed: int = 0
    pattern_recognition_accuracy: float = 0.0
    last_intelligence_update: datetime = field(default_factory=datetime.now)

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def get_optimal_timeline(self, goal_type: str) -> timedelta | None:
        """Get the optimal timeline for this goal type based on learned patterns."""
        if goal_type not in self.optimal_timeline_patterns:
            return None

        optimal_weeks = self.optimal_timeline_patterns[goal_type]
        return timedelta(weeks=optimal_weeks)

    def get_optimal_context(self) -> GoalAchievementContext | None:
        """Get the optimal context for goal achievement."""
        if not self.achievement_context_success:
            return None

        return max(
            self.achievement_context_success.keys(), key=self.achievement_context_success.get
        )

    def get_optimal_motivation_level(self) -> MotivationLevel | None:
        """Get the motivation level when goals are most successful."""
        if not self.motivation_level_correlations:
            return None

        return max(
            self.motivation_level_correlations.keys(), key=self.motivation_level_correlations.get
        )

    def predict_success_probability(
        self,
        goal_type: str,
        timeline_weeks: int,
        context: GoalAchievementContext,
        motivation_level: MotivationLevel,
    ) -> float:
        """
        Predict probability of success given goal parameters.

        Uses learned patterns to estimate likelihood of successful achievement.
        """
        factors = []

        # Timeline factor
        if goal_type in self.optimal_timeline_patterns:
            optimal_weeks = self.optimal_timeline_patterns[goal_type]
            # Closer to optimal timeline = higher success probability
            timeline_factor = 1.0 - abs(timeline_weeks - optimal_weeks) / max(
                optimal_weeks, timeline_weeks
            )
            factors.append(max(0.1, timeline_factor))

        # Context factor
        if context in self.achievement_context_success:
            factors.append(self.achievement_context_success[context])

        # Motivation factor
        if motivation_level in self.motivation_level_correlations:
            factors.append(self.motivation_level_correlations[motivation_level])

        # Goal type factor
        if goal_type in self.goal_type_success_patterns:
            factors.append(self.goal_type_success_patterns[goal_type])

        if not factors:
            return 0.5  # Default probability when no data

        # Weight by intelligence confidence
        base_probability = sum(factors) / len(factors)
        return base_probability * self.intelligence_confidence + 0.5 * (
            1 - self.intelligence_confidence
        )

    def get_obstacle_prevention_strategies(self) -> list[dict[str, Any]]:
        """Get strategies to prevent common obstacle patterns."""
        strategies = []

        # Most common obstacle reasons
        if self.obstacle_pattern_analysis:
            top_obstacles = sorted(
                self.obstacle_pattern_analysis.items(), key=itemgetter(1), reverse=True
            )[:3]

            for obstacle_reason, count in top_obstacles:
                # Get effective strategies for this obstacle type
                if obstacle_reason in self.obstacle_overcome_strategies:
                    relevant_strategies = self.obstacle_overcome_strategies[obstacle_reason]

                    strategies.append(
                        {
                            "obstacle_reason": obstacle_reason.value,
                            "frequency": count,
                            "prevention_strategies": relevant_strategies[:3],  # Top 3 strategies
                            "confidence": min(1.0, count / max(1, self.total_goals_analyzed)),
                        }
                    )

        return strategies

    def get_optimal_milestone_strategy(self) -> str | None:
        """Get the most effective milestone strategy based on learned patterns."""
        if not self.milestone_effectiveness_scores:
            return None

        return max(
            self.milestone_effectiveness_scores.keys(), key=self.milestone_effectiveness_scores.get
        )

    def get_motivation_sustaining_recommendations(self) -> list[dict[str, Any]]:
        """Get recommendations for sustaining motivation based on effectiveness patterns."""
        recommendations = []

        # Sort by effectiveness
        effective_factors = [
            (factor, effectiveness)
            for factor, effectiveness in self.motivation_sustaining_factors.items()
            if effectiveness > 0.6
        ]
        effective_factors.sort(key=itemgetter(1), reverse=True)

        for factor, effectiveness in effective_factors[:3]:  # Top 3
            recommendations.append(
                {
                    "motivation_factor": factor,
                    "effectiveness": effectiveness,
                    "recommendation": f"Use {factor} for {effectiveness:.0%} better motivation",
                    "confidence": self.intelligence_confidence,
                }
            )

        return recommendations

    def get_resource_optimization_suggestions(self) -> list[dict[str, Any]]:
        """Get suggestions for optimal resource allocation based on success patterns."""
        suggestions = []

        # Time investment optimization
        if self.optimal_time_investment_patterns:
            most_effective_phase = max(
                self.optimal_time_investment_patterns.keys(),
                key=self.optimal_time_investment_patterns.get,
            )
            optimal_hours = self.optimal_time_investment_patterns[most_effective_phase]

            suggestions.append(
                {
                    "type": "time_allocation",
                    "phase": most_effective_phase,
                    "recommended_hours_per_week": optimal_hours,
                    "reasoning": "Most effective phase for time investment",
                    "confidence": self.intelligence_confidence,
                }
            )

        # Energy allocation optimization
        if self.energy_allocation_optimization:
            best_activities = sorted(
                self.energy_allocation_optimization.items(), key=itemgetter(1), reverse=True
            )[:2]

            for activity, efficiency in best_activities:
                suggestions.append(
                    {
                        "type": "energy_allocation",
                        "activity": activity,
                        "efficiency_score": efficiency,
                        "reasoning": "High energy efficiency activity",
                        "confidence": self.intelligence_confidence,
                    }
                )

        return suggestions

    def get_cross_domain_integration_opportunities(self) -> list[dict[str, Any]]:
        """Get opportunities for cross-domain integration based on learned effectiveness."""
        opportunities = []

        # Habit support integration
        if self.habit_support_correlation:
            supportive_habits = [
                (habit_uid, correlation)
                for habit_uid, correlation in self.habit_support_correlation.items()
                if correlation > 0.7
            ]
            supportive_habits.sort(key=itemgetter(1), reverse=True)

            for habit_uid, correlation in supportive_habits[:2]:
                opportunities.append(
                    {
                        "type": "habit_integration",
                        "habit_uid": habit_uid,
                        "support_strength": correlation,
                        "recommendation": f"Integrate with {habit_uid} for {correlation:.0%} better goal support",
                        "confidence": self.intelligence_confidence,
                    }
                )

        # Knowledge prerequisite patterns
        if self.knowledge_prerequisite_patterns:
            for phase, knowledge_list in list(self.knowledge_prerequisite_patterns.items())[:2]:
                opportunities.append(
                    {
                        "type": "knowledge_preparation",
                        "goal_phase": phase,
                        "required_knowledge": knowledge_list,
                        "recommendation": f"Prepare knowledge for {phase} phase",
                        "confidence": self.intelligence_confidence,
                    }
                )

        return opportunities

    def should_suggest_goal_revision(
        self,
        current_progress: float,
        time_elapsed_ratio: float,
        current_motivation: MotivationLevel,
    ) -> bool:
        """Determine if goal should be revised based on intelligent patterns."""

        # Check if progress is significantly behind timeline
        expected_progress = time_elapsed_ratio * 100
        progress_gap = expected_progress - current_progress

        if progress_gap > 30:  # More than 30% behind
            return True

        # Check motivation level correlation
        if (
            current_motivation in self.motivation_level_correlations
            and self.motivation_level_correlations[current_motivation] < 0.4
        ):
            return True

        # Check if this goal type typically needs revision
        historical_revision_success = any(
            pattern.get("resulted_in_success", False) for pattern in self.revision_success_patterns
        )

        return historical_revision_success and self.intelligence_confidence > 0.6


@dataclass(frozen=True)
class GoalAchievementIntelligence:
    """
    Intelligence data captured from each goal achievement or milestone.

    This entity captures the context and outcome of each goal progress event
    to feed the learning algorithms in GoalIntelligence.
    """

    uid: str
    goal_uid: str
    user_uid: str

    # Achievement Details
    achieved_at: datetime
    planned_completion: date | None
    actual_completion: date
    achievement_type: str  # "goal_completed", "milestone_reached", "goal_revised"

    # Context
    achievement_context: GoalAchievementContext
    motivation_level_during: MotivationLevel
    primary_strategy_used: str
    time_investment_per_week: int  # hours

    # Success Metrics
    achievement_quality: int = 5  # 1-5 scale,
    satisfaction_level: int = 5  # 1-5 scale,
    effort_level: int = 3  # 1-5 scale,
    timeline_accuracy: float = 1.0  # actual_time / planned_time

    # Contributing Factors
    supporting_habits_active: list[str] = field(default_factory=list)
    knowledge_applied: list[str] = field(default_factory=list)
    strategies_that_worked: list[str] = field(default_factory=list)
    motivation_factors: list[str] = field(default_factory=list)

    # Obstacles and Solutions
    obstacles_encountered: list[str] = field(default_factory=list)
    obstacles_overcome: list[str] = field(default_factory=list)
    recovery_strategies_used: list[str] = field(default_factory=list)

    # Integration Data
    contributed_to_parent_goals: list[str] = field(default_factory=list)
    unlocked_new_opportunities: list[str] = field(default_factory=list)
    reinforced_principles: list[str] = field(default_factory=list)

    def was_successful(self) -> bool:
        """Determine if this achievement was successful based on quality metrics."""
        return (
            self.achievement_quality >= 4
            and self.satisfaction_level >= 4
            and self.achievement_type in ["goal_completed", "milestone_reached"]
        )

    def was_on_time(self) -> bool:
        """Check if achievement happened within planned timeline."""
        if not self.planned_completion:
            return True
        return self.actual_completion <= self.planned_completion

    def get_efficiency_score(self) -> float:
        """Calculate efficiency based on effort and timeline accuracy."""
        effort_efficiency = (6 - self.effort_level) / 5  # Lower effort = higher efficiency
        timeline_efficiency = min(1.0, 1.0 / max(0.1, self.timeline_accuracy))
        return (effort_efficiency + timeline_efficiency) / 2


# Factory functions for creating goal intelligence entities


def create_goal_intelligence(user_uid: str, goal_uid: str) -> GoalIntelligence:
    """Create initial goal intelligence entity."""
    intelligence_uid = f"goal_intel_{user_uid}_{goal_uid}"

    return GoalIntelligence(uid=intelligence_uid, user_uid=user_uid, goal_uid=goal_uid)


def create_goal_achievement_intelligence(
    goal_uid: str, user_uid: str, achievement_details: dict[str, Any]
) -> GoalAchievementIntelligence:
    """Create goal achievement intelligence from achievement event."""
    achievement_uid = f"goal_achievement_{goal_uid}_{int(datetime.now().timestamp())}"

    return GoalAchievementIntelligence(
        uid=achievement_uid,
        goal_uid=goal_uid,
        user_uid=user_uid,
        achieved_at=achievement_details.get("achieved_at", datetime.now()),
        planned_completion=achievement_details.get("planned_completion"),
        actual_completion=achievement_details.get("actual_completion", date.today()),
        achievement_type=achievement_details.get("achievement_type", "milestone_reached"),
        achievement_context=achievement_details.get("context", GoalAchievementContext.SOLO_WORK),
        motivation_level_during=achievement_details.get("motivation", MotivationLevel.MODERATE),
        primary_strategy_used=achievement_details.get("strategy", "consistent_progress"),
        time_investment_per_week=achievement_details.get("time_per_week", 5),
        achievement_quality=achievement_details.get("quality", 5),
        satisfaction_level=achievement_details.get("satisfaction", 5),
        effort_level=achievement_details.get("effort", 3),
    )
