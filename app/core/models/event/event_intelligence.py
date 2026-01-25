"""
Events Intelligence Entities - Revolutionary Enhancement
=======================================================

Persistent intelligence entities that transform Events from static calendar
management to adaptive, learning-aware systems that optimize value and engagement.

This implements the revolutionary intelligence pattern established in
Knowledge/Learning/Search/Habits/Goals/Tasks domains for the Events domain.

Key Revolutionary Features:
1. Persistent EventIntelligence entities that learn from participation patterns
2. Optimal timing and frequency intelligence for maximum value realization
3. Preparation and follow-up strategy learning for event success
4. Cross-domain integration with Habits, Goals, and Knowledge
5. Adaptive event optimization through relationship intelligence
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from operator import itemgetter
from typing import Any


class EventParticipationContext(str, Enum):
    """Contexts in which events are participated."""

    IN_PERSON_FOCUSED = "in_person_focused"
    VIRTUAL_ENGAGED = "virtual_engaged"
    HYBRID_BALANCED = "hybrid_balanced"
    NETWORKING_ACTIVE = "networking_active"
    LEARNING_INTENSIVE = "learning_intensive"
    PRESENTATION_MODE = "presentation_mode"
    COLLABORATION_SESSION = "collaboration_session"
    PASSIVE_ATTENDANCE = "passive_attendance"
    LEADERSHIP_ROLE = "leadership_role"
    SUPPORT_CAPACITY = "support_capacity"


class EnergyImpact(str, Enum):
    """Event energy impact on participants."""

    VERY_DRAINING = "very_draining"
    DRAINING = "draining"
    NEUTRAL = "neutral"
    ENERGIZING = "energizing"
    VERY_ENERGIZING = "very_energizing"


class EventPreparationLevel(str, Enum):
    """Level of preparation for events."""

    NONE = "none"
    MINIMAL = "minimal"
    ADEQUATE = "adequate"
    THOROUGH = "thorough"
    OVER_PREPARED = "over_prepared"


@dataclass(frozen=True)
class EventIntelligence:
    """
    Persistent Event Intelligence Entity.

    Learns from user participation patterns to optimize event timing,
    preparation strategies, value realization, and energy management.
    Replaces static calendar management with adaptive intelligence that
    improves through user interaction.
    """

    uid: str
    user_uid: str
    event_category: str  # Intelligence by event type/category

    # Timing Intelligence
    optimal_timing_patterns: dict[str, float] = field(
        default_factory=dict
    )  # time_slot -> attendance_quality,
    duration_optimization_data: dict[str, int] = field(
        default_factory=dict
    )  # event_type -> optimal_duration_minutes,
    frequency_effectiveness_patterns: dict[str, float] = field(
        default_factory=dict
    )  # frequency -> value_gained

    # Preparation Intelligence
    preparation_time_optimization: dict[str, int] = field(
        default_factory=dict
    )  # event_type -> prep_time_needed_minutes,
    resource_requirement_patterns: dict[str, list[str]] = field(
        default_factory=dict
    )  # event_type -> required_resources,
    success_factor_analysis: dict[str, float] = field(
        default_factory=dict
    )  # preparation_factor -> success_correlation

    # Participation Intelligence
    participation_context_effectiveness: dict[EventParticipationContext, float] = (
        field(default_factory=dict),
    )
    energy_impact_patterns: dict[str, EnergyImpact] = field(
        default_factory=dict
    )  # event_characteristics -> energy_impact,
    engagement_optimization_factors: dict[str, float] = field(
        default_factory=dict
    )  # engagement_factor -> effectiveness

    # Value Intelligence
    value_realization_patterns: dict[str, float] = field(
        default_factory=dict
    )  # event_characteristics -> actual_value,
    learning_extraction_effectiveness: dict[str, float] = field(
        default_factory=dict
    )  # extraction_method -> learning_retention,
    networking_value_analysis: dict[str, float] = field(
        default_factory=dict
    )  # networking_approach -> connection_quality

    # Integration Intelligence
    habit_reinforcement_effectiveness: dict[str, float] = field(
        default_factory=dict
    )  # habit_uid -> reinforcement_strength,
    learning_integration_patterns: dict[str, list[str]] = field(
        default_factory=dict
    )  # event_type -> knowledge_gained,
    goal_advancement_correlation: dict[str, float] = field(
        default_factory=dict
    )  # event_participation -> goal_progress

    # Follow-up Intelligence
    follow_up_optimization: dict[str, list[str]] = field(
        default_factory=dict
    )  # event_type -> optimal_follow_up_actions,
    knowledge_retention_strategies: dict[str, float] = field(
        default_factory=dict
    )  # retention_strategy -> effectiveness,
    action_item_completion_patterns: dict[str, float] = field(
        default_factory=dict
    )  # action_type -> completion_rate

    # Scheduling Intelligence
    calendar_load_optimization: dict[str, int] = field(
        default_factory=dict
    )  # day_type -> optimal_event_count,
    transition_time_requirements: dict[str, int] = field(
        default_factory=dict
    )  # event_transition -> minutes_needed,
    energy_management_patterns: dict[str, list[str]] = field(
        default_factory=dict
    )  # energy_level -> suitable_event_types

    # Conflict Intelligence
    conflict_resolution_strategies: dict[str, list[str]] = field(
        default_factory=dict
    )  # conflict_type -> resolution_approaches,
    priority_assessment_accuracy: dict[str, float] = field(
        default_factory=dict
    )  # priority_factors -> actual_importance,
    rescheduling_success_patterns: dict[str, float] = field(
        default_factory=dict
    )  # reschedule_reason -> success_rate

    # Evolution Tracking
    intelligence_confidence: float = 0.5  # How confident we are in our patterns,
    total_events_analyzed: int = 0
    total_participations_analyzed: int = 0
    pattern_recognition_accuracy: float = 0.0
    last_intelligence_update: datetime = field(default_factory=datetime.now)

    # Metadata
    created_at: datetime = (field(default_factory=datetime.now),)
    updated_at: datetime = field(default_factory=datetime.now)

    def get_optimal_timing(self) -> str | None:
        """Get the optimal time of day for this event category based on learned patterns."""
        if not self.optimal_timing_patterns:
            return None

        return max(self.optimal_timing_patterns.keys(), key=self.optimal_timing_patterns.get)

    def get_optimal_duration(self) -> int | None:
        """Get the optimal duration for this event type."""
        if self.event_category not in self.duration_optimization_data:
            return None

        return self.duration_optimization_data[self.event_category]

    def get_optimal_participation_context(self) -> EventParticipationContext | None:
        """Get the optimal participation context for maximum effectiveness."""
        if not self.participation_context_effectiveness:
            return None

        return max(
            self.participation_context_effectiveness.keys(),
            key=self.participation_context_effectiveness.get,
        )

    def predict_event_value(
        self,
        event_characteristics: dict[str, Any],
        preparation_level: EventPreparationLevel,
        participation_context: EventParticipationContext,
    ) -> float:
        """
        Predict the value realization of an event given its characteristics.

        Uses learned patterns to estimate how valuable the event will be.
        """
        factors = []

        # Event characteristics factor
        event_type = event_characteristics.get("type", "general")
        if event_type in self.value_realization_patterns:
            factors.append(self.value_realization_patterns[event_type])

        # Preparation factor
        prep_factor_key = f"preparation_{preparation_level.value}"
        if prep_factor_key in self.success_factor_analysis:
            factors.append(self.success_factor_analysis[prep_factor_key])

        # Participation context factor
        if participation_context in self.participation_context_effectiveness:
            factors.append(self.participation_context_effectiveness[participation_context])

        # Duration factor
        duration = event_characteristics.get("duration_minutes", 60)
        optimal_duration = self.get_optimal_duration()
        if optimal_duration:
            duration_factor = 1.0 - abs(duration - optimal_duration) / max(
                optimal_duration, duration
            )
            factors.append(max(0.1, duration_factor))

        if not factors:
            return 0.5  # Default value when no data

        # Weight by intelligence confidence
        base_value = sum(factors) / len(factors)
        return base_value * self.intelligence_confidence + 0.5 * (1 - self.intelligence_confidence)

    def get_preparation_recommendations(self) -> list[dict[str, Any]]:
        """Get intelligent preparation recommendations based on learned patterns."""
        recommendations = []

        # Optimal preparation time
        if self.event_category in self.preparation_time_optimization:
            prep_time = self.preparation_time_optimization[self.event_category]
            recommendations.append(
                {
                    "type": "preparation_time",
                    "recommendation": f"Allocate {prep_time} minutes for preparation",
                    "reasoning": "Based on learned preparation patterns",
                    "confidence": self.intelligence_confidence,
                }
            )

        # Required resources
        if self.event_category in self.resource_requirement_patterns:
            resources = self.resource_requirement_patterns[self.event_category]
            recommendations.append(
                {
                    "type": "resource_preparation",
                    "resources": resources,
                    "recommendation": f"Prepare these resources: {', '.join(resources)}",
                    "confidence": self.intelligence_confidence,
                }
            )

        # Success factors
        high_impact_factors = [
            (factor, correlation)
            for factor, correlation in self.success_factor_analysis.items()
            if correlation > 0.7
        ]
        high_impact_factors.sort(key=itemgetter(1), reverse=True)

        for factor, correlation in high_impact_factors[:3]:  # Top 3 factors
            recommendations.append(
                {
                    "type": "success_factor",
                    "factor": factor,
                    "correlation": correlation,
                    "recommendation": f"Focus on {factor} for {correlation:.0%} better outcomes",
                    "confidence": self.intelligence_confidence,
                }
            )

        return recommendations

    def get_energy_management_suggestions(self) -> list[dict[str, Any]]:
        """Get suggestions for managing energy around events."""
        suggestions = []

        # Energy impact prediction
        if self.event_category in self.energy_impact_patterns:
            energy_impact = self.energy_impact_patterns[self.event_category]
            suggestions.append(
                {
                    "type": "energy_impact",
                    "impact": energy_impact.value,
                    "recommendation": self._get_energy_recommendation(energy_impact),
                    "confidence": self.intelligence_confidence,
                }
            )

        # Calendar load optimization
        if "weekday" in self.calendar_load_optimization:
            optimal_events = self.calendar_load_optimization["weekday"]
            suggestions.append(
                {
                    "type": "calendar_load",
                    "optimal_daily_events": optimal_events,
                    "recommendation": f"Limit to {optimal_events} events per day for optimal energy",
                    "confidence": self.intelligence_confidence,
                }
            )

        return suggestions

    def get_follow_up_action_plan(self) -> list[dict[str, Any]]:
        """Get intelligent follow-up action plan based on event type."""
        action_plan = []

        if self.event_category in self.follow_up_optimization:
            actions = self.follow_up_optimization[self.event_category]

            for action in actions:
                completion_rate = self.action_item_completion_patterns.get(action, 0.5)
                action_plan.append(
                    {
                        "action": action,
                        "completion_rate": completion_rate,
                        "priority": "high" if completion_rate > 0.8 else "medium",
                        "confidence": self.intelligence_confidence,
                    }
                )

        return action_plan

    def get_learning_extraction_strategies(self) -> list[dict[str, Any]]:
        """Get strategies for extracting maximum learning from events."""
        strategies = []

        # Most effective extraction methods
        effective_methods = [
            (method, effectiveness)
            for method, effectiveness in self.learning_extraction_effectiveness.items()
            if effectiveness > 0.6
        ]
        effective_methods.sort(key=itemgetter(1), reverse=True)

        for method, effectiveness in effective_methods[:3]:  # Top 3 methods
            strategies.append(
                {
                    "method": method,
                    "effectiveness": effectiveness,
                    "recommendation": f"Use {method} for {effectiveness:.0%} better retention",
                    "confidence": self.intelligence_confidence,
                }
            )

        return strategies

    def get_cross_domain_integration_opportunities(self) -> list[dict[str, Any]]:
        """Get opportunities for cross-domain integration based on effectiveness."""
        opportunities = []

        # Habit reinforcement opportunities
        if self.habit_reinforcement_effectiveness:
            effective_habits = [
                (habit_uid, strength)
                for habit_uid, strength in self.habit_reinforcement_effectiveness.items()
                if strength > 0.7
            ]
            effective_habits.sort(key=itemgetter(1), reverse=True)

            for habit_uid, strength in effective_habits[:2]:
                opportunities.append(
                    {
                        "type": "habit_reinforcement",
                        "habit_uid": habit_uid,
                        "reinforcement_strength": strength,
                        "recommendation": f"Schedule events to reinforce {habit_uid}",
                        "confidence": self.intelligence_confidence,
                    }
                )

        # Goal advancement opportunities
        if self.goal_advancement_correlation:
            advancing_participations = [
                (participation, correlation)
                for participation, correlation in self.goal_advancement_correlation.items()
                if correlation > 0.6
            ]
            advancing_participations.sort(key=itemgetter(1), reverse=True)

            for participation, correlation in advancing_participations[:2]:
                opportunities.append(
                    {
                        "type": "goal_advancement",
                        "participation_type": participation,
                        "advancement_correlation": correlation,
                        "recommendation": f"Engage in {participation} for {correlation:.0%} goal advancement",
                        "confidence": self.intelligence_confidence,
                    }
                )

        return opportunities

    def should_accept_event_invitation(
        self, event_details: dict[str, Any], current_calendar_load: int, energy_level: str
    ) -> dict[str, Any]:
        """Intelligent decision support for event invitations."""

        # Predict event value
        predicted_value = self.predict_event_value(
            event_details, EventPreparationLevel.ADEQUATE, EventParticipationContext.VIRTUAL_ENGAGED
        )

        # Check calendar load
        optimal_load = self.calendar_load_optimization.get("weekday", 5)
        calendar_overload = current_calendar_load >= optimal_load

        # Check energy compatibility
        suitable_events = self.energy_management_patterns.get(energy_level, [])
        energy_compatible = event_details.get("type", "unknown") in suitable_events

        recommendation: dict[str, Any] = {
            "should_accept": predicted_value > 0.6 and not calendar_overload and energy_compatible,
            "predicted_value": predicted_value,
            "reasoning": [],
            "confidence": self.intelligence_confidence,
        }

        # Add reasoning
        if predicted_value > 0.7:
            recommendation["reasoning"].append("High predicted value")
        elif predicted_value < 0.4:
            recommendation["reasoning"].append("Low predicted value")

        if calendar_overload:
            recommendation["reasoning"].append("Calendar at capacity")

        if not energy_compatible:
            recommendation["reasoning"].append("Not compatible with current energy level")

        return recommendation

    def _get_energy_recommendation(self, energy_impact: EnergyImpact) -> str:
        """Get energy management recommendation based on impact."""
        recommendations = {
            EnergyImpact.VERY_DRAINING: "Schedule buffer time after and avoid back-to-back events",
            EnergyImpact.DRAINING: "Plan light activities afterward and ensure adequate rest",
            EnergyImpact.NEUTRAL: "Standard scheduling approach works well",
            EnergyImpact.ENERGIZING: "Consider scheduling more demanding tasks afterward",
            EnergyImpact.VERY_ENERGIZING: "Ideal for starting productive work sessions",
        }
        return recommendations.get(energy_impact, "Monitor energy levels and adjust accordingly")

    def predict_energy_impact(
        self, current_energy: float, proposed_schedule: list[dict[str, Any]]
    ) -> float:
        """Predict final energy level after executing a schedule of events."""
        energy_level = current_energy

        for event in proposed_schedule:
            event_type = event.get("type", "unknown")
            duration = event.get("duration", 60)

            # Get energy impact for this event type
            if event_type in self.energy_impact_patterns:
                impact = self.energy_impact_patterns[event_type]

                # Apply energy change based on impact and duration
                impact_multiplier = {
                    EnergyImpact.VERY_DRAINING: -0.25,
                    EnergyImpact.DRAINING: -0.15,
                    EnergyImpact.NEUTRAL: 0.0,
                    EnergyImpact.ENERGIZING: 0.10,
                    EnergyImpact.VERY_ENERGIZING: 0.20,
                }.get(impact, 0.0)

                # Scale by duration (longer events have more impact)
                duration_factor = min(duration / 60.0, 2.0)  # Cap at 2x impact for very long events
                energy_change = impact_multiplier * duration_factor
                energy_level = max(0.0, min(1.0, energy_level + energy_change))

        return energy_level

    def optimize_preparation_strategy(
        self, available_time: int, event_importance: float, event_characteristics: dict[str, Any]
    ) -> EventPreparationLevel:
        """Optimize preparation strategy based on available time and event importance."""
        # Calculate recommended preparation time
        event_type = event_characteristics.get("type", self.event_category)
        recommended_time = self.preparation_time_optimization.get(event_type, 60)

        # Adjust based on importance
        importance_adjusted_time = recommended_time * event_importance

        # Choose strategy based on available vs needed time
        time_ratio = available_time / max(importance_adjusted_time, 1)

        if time_ratio >= 1.5:
            return EventPreparationLevel.THOROUGH
        elif time_ratio >= 1.0:
            return EventPreparationLevel.ADEQUATE
        elif time_ratio >= 0.5:
            return EventPreparationLevel.MINIMAL
        else:
            return EventPreparationLevel.NONE

    def analyze_cross_domain_synergies(self, cross_domain_context: dict[str, Any]) -> list[str]:
        """Analyze potential synergies with other domains."""
        insights = []

        # Habit integration insights
        active_habits = cross_domain_context.get("active_habits", [])
        for habit in active_habits:
            if habit in self.habit_reinforcement_effectiveness:
                strength = self.habit_reinforcement_effectiveness[habit]
                if strength > 0.7:
                    insights.append(f"Events in this category strongly reinforce {habit} habit")

        # Goal advancement insights
        current_goals = cross_domain_context.get("current_goals", [])
        for goal in current_goals:
            if goal in self.goal_advancement_correlation:
                correlation = self.goal_advancement_correlation[goal]
                if correlation > 0.6:
                    insights.append(f"This event type advances {goal} goal by {correlation:.0%}")

        # Knowledge integration insights
        knowledge_areas = cross_domain_context.get("knowledge_areas", [])
        for area in knowledge_areas:
            if area in self.learning_integration_patterns:
                concepts = self.learning_integration_patterns[area]
                insights.append(f"Events reinforce {area} knowledge: {', '.join(concepts[:2])}")

        return insights


@dataclass(frozen=True)
class EventParticipationIntelligence:
    """
    Intelligence data captured from each event participation.

    This entity captures the context and outcome of each event participation
    to feed the learning algorithms in EventIntelligence.
    """

    uid: str
    event_uid: str
    user_uid: str

    # Participation Details
    participated_at: datetime
    planned_duration: int  # minutes
    actual_duration: int  # minutes
    participation_context: EventParticipationContext

    # Preparation
    preparation_time_minutes: int
    preparation_level: EventPreparationLevel
    resources_prepared: list[str] = field(default_factory=list)

    # Experience Metrics
    value_realized: int = 5  # 1-5 scale,
    engagement_level: int = 5  # 1-5 scale,
    learning_gained: int = 3  # 1-5 scale,
    energy_impact: EnergyImpact = EnergyImpact.NEUTRAL

    # Outcomes
    action_items_generated: list[str] = (field(default_factory=list),)
    connections_made: int = 0
    knowledge_applied: list[str] = (field(default_factory=list),)
    goals_advanced: list[str] = field(default_factory=list)

    # Follow-up
    follow_up_actions_completed: list[str] = (field(default_factory=list),)
    knowledge_retention_after_week: int | None = None  # 1-5 scale,
    long_term_value_realized: int | None = None  # 1-5 scale after time

    # Context Factors
    other_attendees_count: int = 0

    technology_issues: bool = False
    external_distractions: int = 0  # count of interruptions

    # Integration
    habits_reinforced: list[str] = (field(default_factory=list),)
    principles_applied: list[str] = field(default_factory=list)

    def was_valuable(self) -> bool:
        """Determine if this participation was valuable based on metrics."""
        return (
            self.value_realized >= 4
            and self.engagement_level >= 4
            and (self.learning_gained >= 3 or len(self.action_items_generated) > 0)
        )

    def was_well_prepared(self) -> bool:
        """Check if preparation was adequate."""
        return (
            self.preparation_level
            in [EventPreparationLevel.ADEQUATE, EventPreparationLevel.THOROUGH]
            and self.preparation_time_minutes > 0
        )

    def had_positive_energy_impact(self) -> bool:
        """Check if event had positive energy impact."""
        return self.energy_impact in [EnergyImpact.ENERGIZING, EnergyImpact.VERY_ENERGIZING]

    def get_roi_score(self) -> float:
        """Calculate return on investment score."""
        time_invested = self.preparation_time_minutes + self.actual_duration
        if time_invested == 0:
            return 0.0

        value_factors = [
            self.value_realized / 5.0,
            self.learning_gained / 5.0,
            len(self.action_items_generated) * 0.1,
            self.connections_made * 0.05,
        ]

        total_value = sum(value_factors)
        base_roi = min(total_value, 1.0)

        # Adjust for energy impact
        energy_multiplier = {
            EnergyImpact.VERY_DRAINING: 0.7,
            EnergyImpact.DRAINING: 0.85,
            EnergyImpact.NEUTRAL: 1.0,
            EnergyImpact.ENERGIZING: 1.15,
            EnergyImpact.VERY_ENERGIZING: 1.3,
        }

        return base_roi * energy_multiplier.get(self.energy_impact, 1.0)

    def preparation_effectiveness(self) -> float:
        """Calculate how effective the preparation was."""
        if self.preparation_time_minutes == 0:
            return 0.0

        # Base effectiveness based on preparation level
        level_effectiveness = {
            EventPreparationLevel.NONE: 0.0,
            EventPreparationLevel.MINIMAL: 0.3,
            EventPreparationLevel.ADEQUATE: 0.7,
            EventPreparationLevel.THOROUGH: 0.9,
            EventPreparationLevel.OVER_PREPARED: 0.8,  # Slight penalty for over-preparation
        }.get(self.preparation_level, 0.5)

        # Adjust based on actual value realized
        value_factor = self.value_realized / 5.0
        return (level_effectiveness + value_factor) / 2.0

    def energy_efficiency(self) -> float:
        """Calculate energy efficiency of the event participation."""
        total_time = self.preparation_time_minutes + self.actual_duration
        if total_time == 0:
            return 0.0

        # Energy efficiency based on energy impact and value
        energy_score = {
            EnergyImpact.VERY_DRAINING: 0.2,
            EnergyImpact.DRAINING: 0.4,
            EnergyImpact.NEUTRAL: 0.6,
            EnergyImpact.ENERGIZING: 0.8,
            EnergyImpact.VERY_ENERGIZING: 1.0,
        }.get(self.energy_impact, 0.5)

        value_score = self.value_realized / 5.0
        return (energy_score + value_score) / 2.0

    def learning_value(self) -> float:
        """Calculate the learning value of the participation."""
        # Base learning score
        learning_score = self.learning_gained / 5.0

        # Bonus for action items and knowledge application
        action_bonus = min(len(self.action_items_generated) * 0.1, 0.3)
        knowledge_bonus = min(len(self.knowledge_applied) * 0.05, 0.2)

        return min(learning_score + action_bonus + knowledge_bonus, 1.0)

    def extract_behavioral_patterns(self) -> dict[str, Any]:
        """Extract behavioral patterns from this participation."""
        return {
            "preparation_to_value_ratio": self.preparation_effectiveness(),
            "energy_efficiency": self.energy_efficiency(),
            "learning_extraction": self.learning_value(),
            "engagement_effectiveness": self.engagement_level / 5.0,
            "follow_up_completion_rate": len(self.follow_up_actions_completed)
            / max(len(self.action_items_generated), 1),
            "connection_rate": self.connections_made / max(self.other_attendees_count, 1)
            if self.other_attendees_count > 0
            else 0,
            "distraction_impact": max(0, 1.0 - (self.external_distractions * 0.1)),
        }


# Factory functions for creating event intelligence entities


def create_event_intelligence(user_uid: str, event_category: str) -> EventIntelligence:
    """Create initial event intelligence entity for a category."""
    intelligence_uid = f"event_intel_{user_uid}_{event_category}"

    return EventIntelligence(uid=intelligence_uid, user_uid=user_uid, event_category=event_category)


def create_event_participation_intelligence(
    event_uid: str, user_uid: str, participation_details: dict[str, Any]
) -> EventParticipationIntelligence:
    """Create event participation intelligence from participation data."""
    participation_uid = f"event_participation_{event_uid}_{int(datetime.now().timestamp())}"

    return EventParticipationIntelligence(
        uid=participation_uid,
        event_uid=event_uid,
        user_uid=user_uid,
        participated_at=participation_details.get("participated_at", datetime.now()),
        planned_duration=participation_details.get("planned_duration", 60),
        actual_duration=participation_details.get("actual_duration", 60),
        participation_context=participation_details.get(
            "context", EventParticipationContext.VIRTUAL_ENGAGED
        ),
        preparation_time_minutes=participation_details.get("preparation_time", 0),
        preparation_level=participation_details.get(
            "preparation_level", EventPreparationLevel.MINIMAL
        ),
        value_realized=participation_details.get("value_realized", 5),
        engagement_level=participation_details.get("engagement_level", 5),
        learning_gained=participation_details.get("learning_gained", 3),
        energy_impact=participation_details.get("energy_impact", EnergyImpact.NEUTRAL),
        connections_made=participation_details.get("connections_made", 0),
    )
