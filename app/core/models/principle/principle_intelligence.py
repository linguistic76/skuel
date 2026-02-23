"""
Principles Intelligence Entities - Revolutionary Enhancement
==========================================================

Persistent intelligence entities that transform Principles from static value
statements to adaptive, learning-aware systems that optimize values alignment
across all life domains.

This implements the revolutionary intelligence pattern established in
Knowledge/Learning/Search/Habits/Goals/Tasks/Events/Choices domains for the Principles domain.

Key Revolutionary Features:
1. Persistent PrincipleIntelligence entities that learn from alignment patterns
2. Values-based guidance that informs the Choices domain
3. Conflict resolution patterns for competing values
4. Cross-domain integration with all other domains through value alignment
5. Adaptive principle application through relationship intelligence
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from operator import itemgetter
from typing import Any

from core.models.enums.principle_enums import AlignmentLevel, PrincipleStrength


class ValueConflictIntensity(str, Enum):
    """Intensity of conflicts between values."""

    SEVERE = "severe"
    MODERATE = "moderate"
    MILD = "mild"
    MINIMAL = "minimal"


class AlignmentMethod(str, Enum):
    """Methods for measuring and improving alignment."""

    REFLECTION = "reflection"
    BEHAVIORAL_TRACKING = "behavioral_tracking"
    OUTCOME_ANALYSIS = "outcome_analysis"
    PEER_FEEDBACK = "peer_feedback"
    JOURNALING = "journaling"
    MEDITATION = "meditation"
    VALUES_ASSESSMENT = "values_assessment"


@dataclass(frozen=True)
class PrincipleIntelligence:
    """
    Persistent Principle Intelligence Entity.

    Learns from alignment patterns, decision outcomes, and value conflicts
    to optimize principle application and integration across all life domains.
    Replaces static value statements with adaptive intelligence that
    improves through continuous application.
    """

    uid: str
    user_uid: str
    principle_uid: str  # The principle this intelligence supports

    # Alignment Intelligence
    alignment_pattern_analysis: dict[str, float] = field(
        default_factory=dict
    )  # context -> alignment_strength,
    behavioral_manifestation_effectiveness: dict[str, float] = field(
        default_factory=dict
    )  # behavior -> value_impact,
    alignment_measurement_accuracy: dict[AlignmentMethod, float] = (field(default_factory=dict),)
    alignment_improvement_strategies: dict[str, float] = field(
        default_factory=dict
    )  # strategy -> effectiveness

    # Values Weight Intelligence (for informing Choices domain)
    value_weight_optimization: dict[str, float] = field(
        default_factory=dict
    )  # context -> principle_weight,
    value_criteria_importance: dict[str, float] = field(
        default_factory=dict
    )  # criteria -> value_importance

    # Conflict Intelligence
    value_conflict_resolution_patterns: dict[str, str] = field(
        default_factory=dict
    )  # conflict_type -> resolution_strategy,
    conflict_intensity_management: dict[ValueConflictIntensity, list[str]] = (
        field(default_factory=dict),
    )
    principle_hierarchy_effectiveness: dict[str, float] = field(
        default_factory=dict
    )  # priority_context -> hierarchy_success,
    tension_resolution_success_rates: dict[str, float] = field(
        default_factory=dict
    )  # tension_type -> resolution_rate

    # Integration Intelligence
    cross_domain_alignment_patterns: dict[str, float] = field(
        default_factory=dict
    )  # domain -> alignment_strength,
    habit_principle_synergy_effectiveness: dict[str, float] = field(
        default_factory=dict
    )  # habit_uid -> synergy_strength,
    goal_principle_alignment_success: dict[str, float] = field(
        default_factory=dict
    )  # goal_uid -> alignment_success,
    learning_principle_integration: dict[str, list[str]] = field(
        default_factory=dict
    )  # knowledge_area -> integration_methods

    # Application Intelligence
    context_specific_expression_effectiveness: dict[str, float] = field(
        default_factory=dict
    )  # context -> expression_impact,
    behavioral_change_pattern_success: dict[str, float] = field(
        default_factory=dict
    )  # change_pattern -> success_rate,
    environmental_alignment_factors: dict[str, float] = field(
        default_factory=dict
    )  # environment -> alignment_support,
    social_context_alignment_variations: dict[str, float] = field(
        default_factory=dict
    )  # social_context -> alignment_variance

    # Evolution Intelligence
    principle_strength_evolution_patterns: dict[PrincipleStrength, int] = field(
        default_factory=dict
    )  # strength -> days_to_transition,
    understanding_deepening_indicators: dict[str, float] = field(
        default_factory=dict
    )  # indicator -> understanding_growth,
    practice_refinement_effectiveness: dict[str, float] = field(
        default_factory=dict
    )  # practice -> refinement_impact,
    wisdom_integration_patterns: dict[str, list[str]] = field(
        default_factory=dict
    )  # experience_type -> wisdom_gained

    # Measurement Intelligence
    alignment_assessment_reliability: dict[str, float] = field(
        default_factory=dict
    )  # assessment_method -> reliability,
    progress_tracking_effectiveness: dict[str, float] = field(
        default_factory=dict
    )  # tracking_method -> effectiveness,
    feedback_loop_optimization: dict[str, int] = field(
        default_factory=dict
    )  # feedback_type -> optimal_frequency_days

    # Evolution Tracking
    intelligence_confidence: float = 0.5  # How confident we are in our patterns,
    total_alignments_measured: int = 0
    total_conflicts_resolved: int = 0
    pattern_recognition_accuracy: float = 0.0
    last_intelligence_update: datetime = field(default_factory=datetime.now)

    # Metadata
    created_at: datetime = (field(default_factory=datetime.now),)
    updated_at: datetime = field(default_factory=datetime.now)

    def get_optimal_alignment_method(self) -> AlignmentMethod | None:
        """Get the most effective alignment measurement method for this principle."""
        if not self.alignment_measurement_accuracy:
            return None

        return max(
            self.alignment_measurement_accuracy.keys(), key=self.alignment_measurement_accuracy.get
        )

    def get_value_guidance_for_choices(
        self, choice_context: dict[str, Any], choice_criteria: list[str]
    ) -> dict[str, float]:
        """
        Provide values-based guidance to inform the Choices domain.

        Returns value weights and criteria importance for decision-making.
        """
        guidance: dict[str, Any] = {
            "value_weights": {},
            "criteria_importance": {},
            "alignment_considerations": [],
        }

        # Value weight optimization for this context
        context_type = choice_context.get("type", "general")
        if context_type in self.value_weight_optimization:
            guidance["value_weights"][self.principle_uid] = self.value_weight_optimization[
                context_type
            ]

        # Criteria importance based on values alignment
        for criteria in choice_criteria:
            if criteria in self.value_criteria_importance:
                guidance["criteria_importance"][criteria] = self.value_criteria_importance[criteria]

        # Cross-domain alignment considerations
        for domain in choice_context.get("affected_domains", []):
            if domain in self.cross_domain_alignment_patterns:
                strength = self.cross_domain_alignment_patterns[domain]
                if strength > 0.7:
                    guidance["alignment_considerations"].append(
                        {
                            "domain": domain,
                            "alignment_strength": strength,
                            "guidance": f"High {self.principle_uid} alignment in {domain} domain",
                        }
                    )

        return guidance

    def get_conflict_resolution_strategy(
        self,
        conflicting_principle_uid: str,
        conflict_context: str,
        conflict_intensity: ValueConflictIntensity,
    ) -> str | None:
        """Get the optimal strategy for resolving a value conflict."""
        conflict_key = f"{conflicting_principle_uid}_{conflict_context}"

        if conflict_key in self.value_conflict_resolution_patterns:
            return self.value_conflict_resolution_patterns[conflict_key]

        # Fallback to intensity-based strategies
        if conflict_intensity in self.conflict_intensity_management:
            strategies = self.conflict_intensity_management[conflict_intensity]
            return strategies[0] if strategies else None

        return None

    def optimize_values_expression(
        self,
        application_context: str,
        available_behaviors: list[str],
        environmental_factors: dict[str, Any],
    ) -> dict[str, Any]:
        """Optimize how this principle's values should be expressed in a specific context."""
        recommendations: dict[str, Any] = {
            "recommended_behaviors": [],
            "context_adaptations": [],
            "environmental_considerations": [],
            "values_alignment_probability": 0.5,
        }

        # Recommend most effective behaviors for values expression
        effective_behaviors = []
        for behavior in available_behaviors:
            effectiveness = self.behavioral_manifestation_effectiveness.get(behavior, 0.5)
            if effectiveness > 0.6:
                effective_behaviors.append((behavior, effectiveness))

        effective_behaviors.sort(key=itemgetter(1), reverse=True)
        recommendations["recommended_behaviors"] = [b[0] for b in effective_behaviors[:3]]

        # Context-specific values adaptations
        if application_context in self.context_specific_expression_effectiveness:
            context_effectiveness = self.context_specific_expression_effectiveness[
                application_context
            ]
            if context_effectiveness > 0.7:
                recommendations["context_adaptations"].append(
                    "High values alignment context - express principle strongly"
                )
            elif context_effectiveness < 0.4:
                recommendations["context_adaptations"].append(
                    "Challenging values context - express principle carefully with adaptation"
                )

        # Environmental considerations for values alignment
        for env_factor in environmental_factors:
            if env_factor in self.environmental_alignment_factors:
                factor_impact = self.environmental_alignment_factors[env_factor]
                if factor_impact > 0.7:
                    recommendations["environmental_considerations"].append(
                        f"{env_factor} strongly supports values expression"
                    )
                elif factor_impact < 0.3:
                    recommendations["environmental_considerations"].append(
                        f"{env_factor} may hinder values expression - consider adaptation"
                    )

        # Calculate values alignment probability
        context_score = self.context_specific_expression_effectiveness.get(application_context, 0.5)
        behavior_score = (
            sum(
                self.behavioral_manifestation_effectiveness.get(b, 0.5) for b in available_behaviors
            )
            / len(available_behaviors)
            if available_behaviors
            else 0.5
        )
        env_score = (
            sum(self.environmental_alignment_factors.get(f, 0.5) for f in environmental_factors)
            / len(environmental_factors)
            if environmental_factors
            else 0.5
        )

        recommendations["values_alignment_probability"] = (
            context_score + behavior_score + env_score
        ) / 3

        return recommendations

    def analyze_cross_domain_integration_opportunities(
        self, domain_context: dict[str, Any]
    ) -> list[str]:
        """Analyze opportunities for stronger principle integration across domains."""
        opportunities = []

        # Habit integration opportunities
        current_habits = domain_context.get("active_habits", [])
        for habit_uid in current_habits:
            if habit_uid in self.habit_principle_synergy_effectiveness:
                synergy = self.habit_principle_synergy_effectiveness[habit_uid]
                if synergy > 0.7:
                    opportunities.append(
                        f"Strong synergy with {habit_uid} habit - reinforce connection"
                    )
                elif synergy < 0.4:
                    opportunities.append(
                        f"Weak synergy with {habit_uid} habit - explore alignment improvements"
                    )

        # Goal integration opportunities
        current_goals = domain_context.get("active_goals", [])
        for goal_uid in current_goals:
            if goal_uid in self.goal_principle_alignment_success:
                alignment = self.goal_principle_alignment_success[goal_uid]
                if alignment > 0.8:
                    opportunities.append(f"Excellent principle-goal alignment with {goal_uid}")
                elif alignment < 0.5:
                    opportunities.append(
                        f"Poor principle-goal alignment with {goal_uid} - needs attention"
                    )

        # Learning integration opportunities
        learning_areas = domain_context.get("knowledge_areas", [])
        for area in learning_areas:
            if area in self.learning_principle_integration:
                methods = self.learning_principle_integration[area]
                opportunities.append(
                    f"Integrate principle through {area} learning via: {', '.join(methods[:2])}"
                )

        # Cross-domain alignment opportunities
        for domain, alignment_strength in self.cross_domain_alignment_patterns.items():
            if alignment_strength > 0.8:
                opportunities.append(
                    f"Strong principle alignment in {domain} domain - leverage success pattern"
                )
            elif alignment_strength < 0.4:
                opportunities.append(
                    f"Weak principle alignment in {domain} domain - focus improvement here"
                )

        return opportunities

    def get_alignment_improvement_recommendations(self) -> list[dict[str, Any]]:
        """Get intelligent recommendations for improving principle alignment."""
        recommendations = []

        # Most effective improvement strategies
        effective_strategies = [
            (strategy, effectiveness)
            for strategy, effectiveness in self.alignment_improvement_strategies.items()
            if effectiveness > 0.6
        ]
        effective_strategies.sort(key=itemgetter(1), reverse=True)

        for strategy, effectiveness in effective_strategies[:3]:
            recommendations.append(
                {
                    "strategy": strategy,
                    "effectiveness": effectiveness,
                    "recommendation": f"Focus on {strategy} for {effectiveness:.0%} improvement",
                    "confidence": self.intelligence_confidence,
                }
            )

        # Behavioral manifestation improvements
        weak_behaviors = [
            (behavior, effectiveness)
            for behavior, effectiveness in self.behavioral_manifestation_effectiveness.items()
            if effectiveness < 0.5
        ]

        for behavior, effectiveness in weak_behaviors[:2]:
            recommendations.append(
                {
                    "type": "behavioral_improvement",
                    "behavior": behavior,
                    "current_effectiveness": effectiveness,
                    "recommendation": f"Strengthen {behavior} behavior - currently low impact",
                    "confidence": self.intelligence_confidence,
                }
            )

        # Context-specific improvements
        challenging_contexts = [
            (context, effectiveness)
            for context, effectiveness in self.context_specific_expression_effectiveness.items()
            if effectiveness < 0.4
        ]

        for context, effectiveness in challenging_contexts[:2]:
            recommendations.append(
                {
                    "type": "context_improvement",
                    "context": context,
                    "current_effectiveness": effectiveness,
                    "recommendation": f"Develop better principle expression in {context} context",
                    "confidence": self.intelligence_confidence,
                }
            )

        return recommendations

    def predict_principle_evolution_timeline(self) -> dict[str, Any]:
        """Predict how this principle understanding and strength will evolve."""
        evolution_prediction = {
            "current_trajectory": "stable",
            "next_strength_level": None,
            "estimated_days_to_next_level": None,
            "understanding_growth_rate": 0.0,
            "integration_maturity": 0.5,
        }

        # Analyze strength evolution patterns
        current_strength = PrincipleStrength.MODERATE  # Would get from actual principle
        if current_strength in self.principle_strength_evolution_patterns:
            days_to_next = self.principle_strength_evolution_patterns[current_strength]
            evolution_prediction["estimated_days_to_next_level"] = days_to_next

            # Determine next level
            strength_progression = {
                PrincipleStrength.EXPLORING: PrincipleStrength.DEVELOPING,
                PrincipleStrength.DEVELOPING: PrincipleStrength.MODERATE,
                PrincipleStrength.MODERATE: PrincipleStrength.STRONG,
                PrincipleStrength.STRONG: PrincipleStrength.CORE,
            }
            evolution_prediction["next_strength_level"] = strength_progression.get(current_strength)

        # Understanding growth rate
        if self.understanding_deepening_indicators:
            growth_indicators = list(self.understanding_deepening_indicators.values())
            evolution_prediction["understanding_growth_rate"] = sum(growth_indicators) / len(
                growth_indicators
            )

        # Integration maturity
        integration_factors = [
            len(self.habit_principle_synergy_effectiveness) > 0,
            len(self.goal_principle_alignment_success) > 0,
            len(self.cross_domain_alignment_patterns) > 2,
            self.pattern_recognition_accuracy > 0.7,
        ]
        evolution_prediction["integration_maturity"] = sum(integration_factors) / len(
            integration_factors
        )

        return evolution_prediction


@dataclass(frozen=True)
class PrincipleApplicationIntelligence:
    """
    Intelligence data captured from each principle application.

    This entity captures the context and outcome of each principle application
    to feed the learning algorithms in PrincipleIntelligence.
    """

    uid: str
    principle_uid: str
    user_uid: str

    # Application Context
    application_context: str
    application_method: AlignmentMethod
    intended_behavior: str

    # Outcome Assessment
    alignment_achieved: AlignmentLevel

    # Optional fields with defaults
    environmental_factors: dict[str, Any] = field(default_factory=dict)

    # Decision Context (if applicable)
    was_decision_context: bool = False

    decision_options: list[str] = (field(default_factory=list),)
    chosen_option: str | None = (None,)

    decision_criteria: list[str] = field(default_factory=list)

    # Outcome Assessment with defaults
    behavioral_effectiveness: int = 5  # 1-5 scale,
    value_expression_quality: int = 5  # 1-5 scale,
    decision_satisfaction: int | None = None  # 1-5 scale if decision

    # Impact Analysis
    immediate_impact: str = ""
    long_term_consequences: str | None = (None,)
    unintended_effects: list[str] = field(default_factory=list)

    # Learning Outcomes
    insights_gained: list[str] = (field(default_factory=list),)
    principle_understanding_shift: str | None = (None,)
    behavioral_adjustments_identified: list[str] = field(default_factory=list)

    # Integration Effects
    habits_reinforced: list[str] = (field(default_factory=list),)
    goals_advanced: list[str] = (field(default_factory=list),)
    knowledge_applied: list[str] = (field(default_factory=list),)
    relationships_impacted: dict[str, str] = field(
        default_factory=dict
    )  # relationship -> impact_type

    # Conflict & Resolution
    value_conflicts_encountered: list[str] = (field(default_factory=list),)
    conflict_resolution_used: str | None = (None,)
    resolution_effectiveness: int | None = None  # 1-5 scale

    # Context Factors
    social_context: str = ""
    emotional_state: str = ""
    stress_level: int = 3  # 1-5 scale,
    external_pressures: list[str] = field(default_factory=list)

    # Tracking
    applied_at: datetime = (field(default_factory=datetime.now),)
    duration_of_application: int | None = None  # minutes,
    follow_up_assessment_date: date | None = None  # type: ignore[assignment]

    def was_successful_application(self) -> bool:
        """Determine if this was a successful principle application."""
        return (
            self.alignment_achieved in [AlignmentLevel.ALIGNED, AlignmentLevel.MOSTLY_ALIGNED]
            and self.behavioral_effectiveness >= 4
            and self.value_expression_quality >= 4
        )

    def had_positive_integration_effects(self) -> bool:
        """Check if application had positive cross-domain effects."""
        return (
            len(self.habits_reinforced) > 0
            or len(self.goals_advanced) > 0
            or len(self.insights_gained) > 0
        )

    def generated_learning(self) -> bool:
        """Check if application generated valuable learning."""
        return (
            len(self.insights_gained) > 0
            or self.principle_understanding_shift is not None
            or len(self.behavioral_adjustments_identified) > 0
        )

    def get_effectiveness_score(self) -> float:
        """Calculate overall effectiveness score for this application."""
        factors = [
            self._alignment_score(),
            self.behavioral_effectiveness / 5.0,
            self.value_expression_quality / 5.0,
        ]

        # Add decision satisfaction if applicable
        if self.was_decision_context and self.decision_satisfaction is not None:
            factors.append(self.decision_satisfaction / 5.0)

        # Bonus for positive integration effects
        if self.had_positive_integration_effects():
            factors.append(0.8)

        # Penalty for unresolved conflicts
        if self.value_conflicts_encountered and not self.conflict_resolution_used:
            factors.append(0.2)

        return sum(factors) / len(factors)

    def _alignment_score(self) -> float:
        """Convert alignment level to numeric score."""
        scores = {
            AlignmentLevel.ALIGNED: 1.0,
            AlignmentLevel.MOSTLY_ALIGNED: 0.8,
            AlignmentLevel.PARTIAL: 0.6,
            AlignmentLevel.MISALIGNED: 0.2,
            AlignmentLevel.UNKNOWN: 0.5,
        }
        return scores.get(self.alignment_achieved, 0.5)

    def extract_application_patterns(self) -> dict[str, Any]:
        """Extract behavioral patterns from this application."""
        return {
            "context_effectiveness": self._alignment_score(),
            "method_effectiveness": self.behavioral_effectiveness / 5.0,
            "stress_impact": max(0, 1.0 - (self.stress_level - 3) * 0.2),
            "social_context_support": 1.0 if self.social_context else 0.5,
            "integration_success": 1.0 if self.had_positive_integration_effects() else 0.0,
            "learning_generation": 1.0 if self.generated_learning() else 0.0,
            "conflict_resolution_success": (self.resolution_effectiveness / 5.0)
            if self.resolution_effectiveness
            else 0.5,
        }


# Factory functions for creating principle intelligence entities


def create_principle_intelligence(user_uid: str, principle_uid: str) -> PrincipleIntelligence:
    """Create initial principle intelligence entity."""
    intelligence_uid = f"principle_intel_{user_uid}_{principle_uid}"

    return PrincipleIntelligence(
        uid=intelligence_uid, user_uid=user_uid, principle_uid=principle_uid
    )


def create_principle_application_intelligence(
    principle_uid: str, user_uid: str, application_details: dict[str, Any]
) -> PrincipleApplicationIntelligence:
    """Create principle application intelligence from application data."""
    application_uid = f"principle_app_{principle_uid}_{int(datetime.now().timestamp())}"

    return PrincipleApplicationIntelligence(
        uid=application_uid,
        principle_uid=principle_uid,
        user_uid=user_uid,
        application_context=application_details.get("context", ""),
        application_method=application_details.get("method", AlignmentMethod.REFLECTION),
        intended_behavior=application_details.get("intended_behavior", ""),
        alignment_achieved=application_details.get("alignment_achieved", AlignmentLevel.UNKNOWN),
        behavioral_effectiveness=application_details.get("behavioral_effectiveness", 5),
        value_expression_quality=application_details.get("value_expression_quality", 5),
        immediate_impact=application_details.get("immediate_impact", ""),
        social_context=application_details.get("social_context", ""),
        emotional_state=application_details.get("emotional_state", ""),
        stress_level=application_details.get("stress_level", 3),
    )
