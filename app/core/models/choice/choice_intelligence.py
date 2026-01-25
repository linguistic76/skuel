"""
Choice Intelligence Entities - Revolutionary Decision Architecture
================================================================

Persistent intelligence entities that transform decision-making from reactive
choosing to proactive option generation and choice optimization across all life domains.

The Choices domain elevates choice awareness by:
1. Generating contextual options before decisions are needed
2. Learning from decision outcomes to improve future choice quality
3. Cross-domain choice pattern analysis and optimization
4. Choice awareness training through intelligent option presentation

Key Revolutionary Features:
1. ChoiceIntelligence entities that learn optimal choice patterns
2. Option generation intelligence that creates awareness of possibilities
3. Decision outcome prediction and quality optimization
4. Cross-domain choice synergy and integration
5. Adaptive choice presentation through relationship intelligence
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from operator import itemgetter
from typing import Any


class ChoiceQuality(str, Enum):
    """Quality outcomes of choices made."""

    TRANSFORMATIVE = "transformative"
    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    POOR = "poor"
    REGRETTABLE = "regrettable"


class ChoiceComplexity(str, Enum):
    """Complexity levels of choices."""

    SIMPLE = "simple"  # Binary yes/no choices
    MODERATE = "moderate"  # 3-5 clear options
    COMPLEX = "complex"  # Many variables and options
    SYSTEMIC = "systemic"  # Life-changing, multi-domain impact


class ChoiceContext(str, Enum):
    """Contexts where choices are made."""

    CAREER = "career"
    RELATIONSHIPS = "relationships"
    HEALTH = "health"
    LEARNING = "learning"
    FINANCIAL = "financial"
    CREATIVE = "creative"
    SPIRITUAL = "spiritual"
    DAILY_ROUTINE = "daily_routine"
    EMERGENCY = "emergency"
    STRATEGIC = "strategic"


class DecisionStyle(str, Enum):
    """Styles of decision-making."""

    ANALYTICAL = "analytical"  # Data-driven analysis
    INTUITIVE = "intuitive"  # Gut feeling based
    COLLABORATIVE = "collaborative"  # Seeking input from others
    PRINCIPLES_BASED = "principles_based"  # Values-driven
    EXPERIMENTAL = "experimental"  # Try and iterate approach
    DELEGATED = "delegated"  # Allowing others to choose


@dataclass(frozen=True)
class ChoiceIntelligence:
    """
    Persistent Choice Intelligence Entity.

    Learns from choice patterns, decision outcomes, and option generation
    to optimize choice awareness and decision quality across all life domains.
    Transforms reactive decision-making into proactive choice optimization.
    """

    uid: str
    user_uid: str
    choice_context: ChoiceContext

    # Option Generation Intelligence
    option_generation_patterns: dict[str, list[str]] = field(
        default_factory=dict
    )  # situation_type -> typical_options,
    creative_option_sources: dict[str, float] = field(
        default_factory=dict
    )  # source_type -> innovation_rate,
    option_quality_prediction: dict[str, float] = field(
        default_factory=dict
    )  # option_pattern -> success_probability,
    contextual_option_relevance: dict[str, float] = field(
        default_factory=dict
    )  # context -> option_alignment

    # Choice Quality Intelligence
    choice_outcome_patterns: dict[str, ChoiceQuality] = field(
        default_factory=dict
    )  # choice_pattern -> outcome_quality,
    decision_criteria_effectiveness: dict[str, float] = field(
        default_factory=dict
    )  # criteria -> choice_quality,
    timing_optimization: dict[str, float] = field(
        default_factory=dict
    )  # timing_pattern -> outcome_improvement,
    choice_confidence_accuracy: dict[str, float] = field(
        default_factory=dict
    )  # confidence_level -> actual_outcome

    # Decision Style Intelligence
    style_effectiveness_by_context: dict[ChoiceContext, dict[DecisionStyle, float]] = (
        field(default_factory=dict),
    )
    cognitive_bias_mitigation: dict[str, list[str]] = field(
        default_factory=dict
    )  # bias_type -> mitigation_strategies,
    decision_fatigue_patterns: dict[str, float] = field(
        default_factory=dict
    )  # fatigue_indicator -> quality_impact,
    energy_optimization_for_choices: dict[str, float] = field(
        default_factory=dict
    )  # energy_level -> choice_quality

    # Cross-Domain Choice Intelligence
    choice_habit_reinforcement: dict[str, float] = field(
        default_factory=dict
    )  # habit_uid -> choice_alignment,
    choice_goal_advancement: dict[str, float] = field(
        default_factory=dict
    )  # goal_uid -> choice_contribution,
    choice_principle_alignment: dict[str, float] = field(
        default_factory=dict
    )  # principle_uid -> alignment_strength,
    choice_learning_acceleration: dict[str, float] = field(
        default_factory=dict
    )  # learning_area -> choice_impact

    # Choice Awareness Intelligence
    awareness_expansion_methods: dict[str, float] = field(
        default_factory=dict
    )  # method -> awareness_increase,
    option_blindness_detection: dict[str, list[str]] = field(
        default_factory=dict
    )  # situation -> missed_options,
    choice_architecture_optimization: dict[str, float] = field(
        default_factory=dict
    )  # environment -> choice_improvement,
    meta_choice_patterns: dict[str, float] = field(
        default_factory=dict
    )  # choosing_how_to_choose -> effectiveness

    def generate_contextual_options(
        self, situation: str, current_constraints: dict[str, Any], desired_outcomes: list[str]
    ) -> list[dict[str, Any]]:
        """
        Generate intelligent options for a given situation.

        Creates choice awareness by presenting possibilities the user
        might not have considered, based on learned patterns.
        """
        options = []

        # Extract learned option patterns for this situation type
        situation_key = self._categorize_situation(situation)
        base_options = self.option_generation_patterns.get(situation_key, [])

        for option in base_options:
            option_data = {
                "option": option,
                "feasibility": self._assess_feasibility(option, current_constraints),
                "alignment_score": self._calculate_alignment_score(option, desired_outcomes),
                "predicted_quality": self.option_quality_prediction.get(option, 0.5),
                "novel_factor": self._assess_novelty(option, situation),
                "cross_domain_impacts": self._predict_cross_domain_impacts(option),
            }
            options.append(option_data)

        # Generate creative alternatives using learned sources
        creative_options = self._generate_creative_alternatives(situation, current_constraints)
        options.extend(creative_options)

        return sorted(options, key=itemgetter("alignment_score"), reverse=True)

    def predict_choice_quality(
        self,
        choice_option: str,
        choice_context: dict[str, Any],
        decision_style: DecisionStyle,
        current_energy_level: float,
    ) -> ChoiceQuality:
        """
        Predict the quality of a choice based on learned patterns.

        Uses choice intelligence to estimate decision outcomes and
        suggest optimal timing and approach.
        """
        # Base quality from historical patterns
        base_quality = self.choice_outcome_patterns.get(choice_option, ChoiceQuality.ACCEPTABLE)

        # Adjust for decision style effectiveness in this context
        context_key = choice_context.get("context_type", ChoiceContext.DAILY_ROUTINE)
        style_effectiveness = self.style_effectiveness_by_context.get(context_key, {}).get(
            decision_style, 0.5
        )

        # Factor in energy level impact
        energy_factor = self.energy_optimization_for_choices.get(
            f"energy_{current_energy_level:.1f}", 0.5
        )

        # Calculate composite quality prediction
        quality_score = (
            self._quality_to_score(base_quality) * 0.4
            + style_effectiveness * 0.3
            + energy_factor * 0.3
        )

        return self._score_to_quality(quality_score)

    def optimize_choice_awareness(
        self, current_situation: str, habitual_choice_patterns: list[str], _blind_spots: list[str]
    ) -> dict[str, Any]:
        """
        Enhance choice awareness by identifying option blindness and
        suggesting awareness expansion techniques.
        """
        awareness_optimization = {
            "detected_blind_spots": [],
            "missed_opportunities": [],
            "awareness_expansion_recommendations": [],
            "choice_architecture_improvements": [],
            "meta_choice_suggestions": [],
        }

        # Detect potential blind spots based on patterns
        situation_key = self._categorize_situation(current_situation)
        potential_missed = self.option_blindness_detection.get(situation_key, [])

        for missed_option in potential_missed:
            if missed_option not in habitual_choice_patterns:
                awareness_optimization["detected_blind_spots"].append(
                    {
                        "option": missed_option,
                        "why_missed": self._analyze_blindness_cause(
                            missed_option, habitual_choice_patterns
                        ),
                        "awareness_technique": self._suggest_awareness_technique(missed_option),
                    }
                )

        # Suggest choice architecture improvements
        for environment, improvement_score in self.choice_architecture_optimization.items():
            if improvement_score > 0.7:  # High potential for improvement
                awareness_optimization["choice_architecture_improvements"].append(
                    {
                        "environment": environment,
                        "improvement": self._get_architecture_improvement(environment),
                        "expected_benefit": improvement_score,
                    }
                )

        return awareness_optimization

    def analyze_cross_domain_choice_synergy(
        self, choice_options: list[str], active_contexts: dict[str, Any]
    ) -> dict[str, float]:
        """
        Analyze how choice options create synergy across life domains.

        Identifies choices that strengthen multiple domains simultaneously.
        """
        synergy_analysis = {}

        for option in choice_options:
            synergy_score = 0.0

            # Calculate habit reinforcement synergy
            habit_synergy = sum(
                self.choice_habit_reinforcement.get(habit, 0)
                for habit in active_contexts.get("active_habits", [])
            )

            # Calculate goal advancement synergy
            goal_synergy = sum(
                self.choice_goal_advancement.get(goal, 0)
                for goal in active_contexts.get("active_goals", [])
            )

            # Calculate principle alignment synergy
            principle_synergy = sum(
                self.choice_principle_alignment.get(principle, 0)
                for principle in active_contexts.get("active_principles", [])
            )

            # Calculate learning acceleration synergy
            learning_synergy = sum(
                self.choice_learning_acceleration.get(area, 0)
                for area in active_contexts.get("learning_areas", [])
            )

            synergy_score = (
                habit_synergy + goal_synergy + principle_synergy + learning_synergy
            ) / 4
            synergy_analysis[option] = synergy_score

        return synergy_analysis

    # Helper methods
    def _categorize_situation(self, situation: str) -> str:
        """Categorize situation for pattern matching."""
        situation_lower = situation.lower()

        if any(
            word in situation_lower
            for word in ["career", "job", "work", "professional", "leadership", "transition"]
        ):
            return "career_transition"
        elif any(
            word in situation_lower for word in ["project", "task", "assignment", "selection"]
        ):
            return "project_selection"
        elif any(word in situation_lower for word in ["learn", "skill", "study", "knowledge"]):
            return "learning"
        elif any(word in situation_lower for word in ["health", "exercise", "wellness"]):
            return "health"
        else:
            return "general"

    def _assess_feasibility(self, _option: str, _constraints: dict[str, Any]) -> float:
        """Assess feasibility of an option given constraints.

        NOTE: Returns default 0.8 - requires constraint analysis implementation.
        """
        return 0.8

    def _calculate_alignment_score(self, _option: str, _outcomes: list[str]) -> float:
        """Calculate alignment with desired outcomes.

        NOTE: Returns default 0.7 - requires ML/embedding implementation for actual scoring.
        """
        return 0.7

    def _assess_novelty(self, _option: str, _situation: str) -> float:
        """Assess how novel this option is.

        NOTE: Returns default 0.5 - requires pattern analysis implementation.
        """
        return 0.5

    def _predict_cross_domain_impacts(self, _option: str) -> dict[str, float]:
        """Predict impacts across life domains.

        NOTE: Returns empty - requires cross-domain analysis implementation.
        """
        return {}

    def _generate_creative_alternatives(
        self, _situation: str, _constraints: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Generate creative alternative options.

        NOTE: Returns empty - requires LLM integration for creative generation.
        """
        return []

    def _quality_to_score(self, quality: ChoiceQuality) -> float:
        """Convert quality enum to numeric score."""
        quality_map = {
            ChoiceQuality.TRANSFORMATIVE: 1.0,
            ChoiceQuality.EXCELLENT: 0.9,
            ChoiceQuality.GOOD: 0.7,
            ChoiceQuality.ACCEPTABLE: 0.5,
            ChoiceQuality.POOR: 0.3,
            ChoiceQuality.REGRETTABLE: 0.1,
        }
        return quality_map.get(quality, 0.5)

    def _score_to_quality(self, score: float) -> ChoiceQuality:
        """Convert numeric score to quality enum."""
        if score >= 0.95:
            return ChoiceQuality.TRANSFORMATIVE
        elif score >= 0.8:
            return ChoiceQuality.EXCELLENT
        elif score >= 0.65:
            return ChoiceQuality.GOOD
        elif score >= 0.45:
            return ChoiceQuality.ACCEPTABLE
        elif score >= 0.25:
            return ChoiceQuality.POOR
        else:
            return ChoiceQuality.REGRETTABLE

    def _analyze_blindness_cause(self, _option: str, _patterns: list[str]) -> str:
        """Analyze why an option might be missed."""
        return "habitual thinking patterns"  # Placeholder

    def _suggest_awareness_technique(self, _option: str) -> str:
        """Suggest technique to increase awareness of this option."""
        return "perspective shifting exercise"  # Placeholder

    def _get_architecture_improvement(self, _environment: str) -> str:
        """Get specific improvement for choice architecture."""
        return "environmental cue optimization"  # Placeholder


@dataclass(frozen=True)
class ChoiceApplicationIntelligence:
    """
    Persistent Choice Application Intelligence Entity.

    Tracks specific choice applications, their outcomes, and learning
    generated from decision-making experiences.
    """

    uid: str
    choice_uid: str  # The choice/decision this tracks
    user_uid: str
    application_context: str

    # Choice Details
    situation_description: str
    available_options: list[str] = (field(default_factory=list),)
    chosen_option: str = ""
    decision_criteria: list[str] = (field(default_factory=list),)
    decision_style_used: DecisionStyle = DecisionStyle.INTUITIVE

    # Context Information
    choice_complexity: ChoiceComplexity = ChoiceComplexity.SIMPLE
    time_pressure_level: int = 3  # 1-5 scale,
    energy_level_at_decision: float = 0.5  # 0-1 scale,
    information_availability: float = 0.5  # 0-1 scale

    # Outcome Tracking
    immediate_satisfaction: int = 3  # 1-5 scale,
    short_term_outcome_quality: ChoiceQuality | None = (None,)
    long_term_outcome_quality: ChoiceQuality | None = (None,)

    unexpected_consequences: list[str] = (field(default_factory=list),)
    learning_generated: list[str] = field(default_factory=list)

    # Cross-Domain Integration
    habits_influenced: list[str] = (field(default_factory=list),)
    goals_advanced: list[str] = (field(default_factory=list),)
    principles_aligned: list[str] = (field(default_factory=list),)
    knowledge_applied: list[str] = field(default_factory=list)

    # Meta-Choice Analysis
    choice_process_effectiveness: float = 0.5  # 0-1 scale,
    option_generation_completeness: float = 0.5  # How well did we identify options,
    decision_confidence: float = 0.5  # Confidence at time of decision,
    outcome_prediction_accuracy: float = 0.5  # How accurate were predictions

    # Timing and Processing
    decision_timestamp: datetime = (field(default_factory=datetime.now),)
    decision_duration_minutes: float = 5.0
    follow_up_evaluations: list[datetime] = field(default_factory=list)

    def get_choice_effectiveness_score(self) -> float:
        """Calculate overall effectiveness of this choice application."""
        outcome_score = 0.5
        if self.long_term_outcome_quality:
            outcome_score = self._quality_to_score(self.long_term_outcome_quality)
        elif self.short_term_outcome_quality:
            outcome_score = self._quality_to_score(self.short_term_outcome_quality)

        return (
            outcome_score * 0.4
            + self.choice_process_effectiveness * 0.3
            + (self.immediate_satisfaction / 5.0) * 0.2
            + self.outcome_prediction_accuracy * 0.1
        )

    def generated_learning(self) -> bool:
        """Check if this choice application generated learning."""
        return len(self.learning_generated) > 0

    def had_cross_domain_integration(self) -> bool:
        """Check if choice integrated with other life domains."""
        return (
            len(self.habits_influenced) > 0
            or len(self.goals_advanced) > 0
            or len(self.principles_aligned) > 0
            or len(self.knowledge_applied) > 0
        )

    def extract_choice_patterns(self) -> dict[str, float]:
        """Extract patterns for learning algorithms."""
        return {
            "decision_style_effectiveness": self.choice_process_effectiveness,
            "complexity_handling": self._assess_complexity_handling(),
            "time_pressure_impact": self._assess_time_pressure_impact(),
            "energy_optimization": self._assess_energy_optimization(),
            "cross_domain_synergy": self._calculate_cross_domain_synergy(),
        }

    def _quality_to_score(self, quality: ChoiceQuality) -> float:
        """Convert quality enum to numeric score."""
        quality_map = {
            ChoiceQuality.TRANSFORMATIVE: 1.0,
            ChoiceQuality.EXCELLENT: 0.9,
            ChoiceQuality.GOOD: 0.7,
            ChoiceQuality.ACCEPTABLE: 0.5,
            ChoiceQuality.POOR: 0.3,
            ChoiceQuality.REGRETTABLE: 0.1,
        }
        return quality_map.get(quality, 0.5)

    def _assess_complexity_handling(self) -> float:
        """Assess how well complexity was handled."""
        complexity_factor = {
            ChoiceComplexity.SIMPLE: 1.0,
            ChoiceComplexity.MODERATE: 0.8,
            ChoiceComplexity.COMPLEX: 0.6,
            ChoiceComplexity.SYSTEMIC: 0.4,
        }.get(self.choice_complexity, 0.5)

        return self.choice_process_effectiveness * complexity_factor

    def _assess_time_pressure_impact(self) -> float:
        """Assess impact of time pressure on choice quality."""
        time_pressure_factor = max(0.2, (6 - self.time_pressure_level) / 5.0)
        return self.choice_process_effectiveness * time_pressure_factor

    def _assess_energy_optimization(self) -> float:
        """Assess energy level optimization for choice quality."""
        return self.choice_process_effectiveness * self.energy_level_at_decision

    def _calculate_cross_domain_synergy(self) -> float:
        """Calculate cross-domain integration strength."""
        integration_count = (
            len(self.habits_influenced)
            + len(self.goals_advanced)
            + len(self.principles_aligned)
            + len(self.knowledge_applied)
        )
        return min(1.0, integration_count / 4.0)


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================


def create_choice_intelligence(
    user_uid: str, choice_context: ChoiceContext, initial_patterns: dict[str, Any] | None = None
) -> ChoiceIntelligence:
    """Factory function for creating ChoiceIntelligence entities."""
    uid = f"ci_{user_uid}_{choice_context.value}_{datetime.now().isoformat()}"

    choice_intelligence = ChoiceIntelligence(
        uid=uid, user_uid=user_uid, choice_context=choice_context
    )

    if initial_patterns:
        # Apply initial patterns if provided
        # This would involve updating the intelligence with learned patterns
        pass

    return choice_intelligence


def create_choice_application_intelligence(
    choice_uid: str, user_uid: str, situation: str, chosen_option: str, available_options: list[str]
) -> ChoiceApplicationIntelligence:
    """Factory function for creating ChoiceApplicationIntelligence entities."""
    uid = f"cai_{choice_uid}_{datetime.now().isoformat()}"

    return ChoiceApplicationIntelligence(
        uid=uid,
        choice_uid=choice_uid,
        user_uid=user_uid,
        application_context=f"choice_application_{choice_uid}",
        situation_description=situation,
        chosen_option=chosen_option,
        available_options=available_options,
    )
