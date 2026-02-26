"""
Askesis Intelligence Entities - Domain Integration Orchestrator
==============================================================

Persistent intelligence entities that transform Askesis from a simple AI assistant
into a sophisticated domain integration orchestrator that learns how to coordinate
and synthesize across all life domains.

Askesis serves as the 10th primary domain with unique meta-intelligence capabilities:
1. Cross-domain pattern recognition and orchestration
2. User interaction preference learning
3. Conversation effectiveness optimization
4. Domain combination success prediction

Implementation: Essential foundation with elegant simplicity
- Basic cross-domain reading and correlation patterns
- Simple domain suggestion based on user queries
- Conversation effectiveness tracking
- Foundation for future meta-intelligence capabilities
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from operator import itemgetter
from typing import Any, TypedDict


class ConversationStyle(str, Enum):
    """Communication styles for Askesis interactions."""

    DIRECT = "direct"  # Concise, to-the-point responses
    EXPLORATORY = "exploratory"  # Deep-dive, questioning approach
    SUPPORTIVE = "supportive"  # Encouraging, empathetic tone
    ANALYTICAL = "analytical"  # Data-driven, logical responses
    CREATIVE = "creative"  # Brainstorming, ideation focus
    COACHING = "coaching"  # Guiding questions, self-discovery


class QueryComplexity(str, Enum):
    """Complexity levels of user queries."""

    SIMPLE = "simple"  # Single domain, straightforward
    MODERATE = "moderate"  # 2-3 domains, some complexity
    COMPLEX = "complex"  # Multiple domains, interconnected
    SYSTEMIC = "systemic"  # Life-wide implications, many domains


class IntegrationSuccess(str, Enum):
    """Success levels of domain integration."""

    EXCELLENT = "excellent"  # Perfect synthesis, high user value
    GOOD = "good"  # Effective integration, clear benefit
    ACCEPTABLE = "acceptable"  # Basic integration, some value
    POOR = "poor"  # Weak integration, limited value
    FAILED = "failed"  # No meaningful integration achieved


class TemporalEffectiveness(TypedDict):
    """Temporal effectiveness analysis results."""

    current_effectiveness: float
    optimal_timing: str
    timing_optimization_potential: float


@dataclass(frozen=True)
class AskesisIntelligence:
    """
    Persistent Askesis Intelligence Entity - Domain Integration Orchestrator.

    Learns cross-domain patterns, user preferences, and conversation effectiveness
    to provide sophisticated domain coordination and synthesis.

    Essential foundation with simple but powerful capabilities.
    Smart orchestration with proactive guidance and context awareness.
    """

    uid: str
    user_uid: str

    # Domain Coordination Intelligence
    domain_interaction_patterns: dict[str, float] = field(
        default_factory=dict
    )  # domain_pair -> synergy_score,
    domain_relevance_patterns: dict[str, list[str]] = field(
        default_factory=dict
    )  # query_type -> relevant_domains,
    successful_domain_combinations: dict[str, float] = field(
        default_factory=dict
    )  # domain_set -> success_rate,
    domain_query_mapping: dict[frozenset[str], set[str]] = field(
        default_factory=dict
    )  # keywords -> relevant_domains

    # User Interaction Intelligence
    user_context_preferences: dict[str, float] = field(
        default_factory=dict
    )  # context_type -> preference_strength,
    conversation_style_effectiveness: dict[ConversationStyle, float] = (
        field(default_factory=dict),
    )
    query_complexity_handling: dict[QueryComplexity, float] = (field(default_factory=dict),)
    response_satisfaction_patterns: dict[str, float] = field(
        default_factory=dict
    )  # response_type -> satisfaction

    # Integration Success Intelligence
    cross_domain_synthesis_effectiveness: dict[str, float] = field(
        default_factory=dict
    )  # synthesis_pattern -> effectiveness,
    domain_coordination_success_rates: dict[str, float] = field(
        default_factory=dict
    )  # coordination_type -> success_rate,
    integration_timing_optimization: dict[str, float] = field(
        default_factory=dict
    )  # timing_pattern -> success_impact

    # Conversation Intelligence
    conversation_flow_patterns: dict[str, list[str]] = field(
        default_factory=dict
    )  # flow_type -> effective_sequence,
    followup_question_effectiveness: dict[str, float] = field(
        default_factory=dict
    )  # question_type -> engagement_score,
    context_retention_patterns: dict[str, int] = field(
        default_factory=dict
    )  # context_type -> optimal_retention_days

    # Learning and Adaptation Intelligence
    user_learning_preferences: dict[str, float] = field(
        default_factory=dict
    )  # learning_style -> effectiveness,
    guidance_delivery_optimization: dict[str, float] = field(
        default_factory=dict
    )  # delivery_method -> acceptance_rate,
    feedback_integration_patterns: dict[str, str] = field(
        default_factory=dict
    )  # feedback_type -> integration_strategy

    # Smart Orchestration Intelligence
    domain_state_monitoring: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )  # domain -> current_state_analysis,
    proactive_guidance_patterns: dict[str, list[str]] = field(
        default_factory=dict
    )  # situation_pattern -> guidance_suggestions,
    context_awareness_memory: dict[str, Any] = field(
        default_factory=dict
    )  # user_context -> retained_information,
    conflict_detection_patterns: dict[str, str] = field(
        default_factory=dict
    )  # conflict_type -> resolution_strategy,
    optimization_opportunity_detection: dict[str, float] = field(
        default_factory=dict
    )  # opportunity_type -> impact_score

    # Advanced Pattern Recognition
    temporal_pattern_analysis: dict[str, dict[str, float]] = field(
        default_factory=dict
    )  # time_pattern -> domain_effectiveness,
    user_lifecycle_stage_patterns: dict[str, list[str]] = field(
        default_factory=dict
    )  # lifecycle_stage -> optimal_domains,
    domain_readiness_assessment: dict[str, float] = field(
        default_factory=dict
    )  # domain -> user_readiness_score

    # Meta-Intelligence Tracking
    intelligence_confidence: float = 0.5  # Confidence in pattern accuracy,
    total_conversations_analyzed: int = 0
    total_domain_integrations: int = 0
    integration_success_rate: float = 0.0
    pattern_recognition_accuracy: float = 0.0
    proactive_guidance_success_rate: float = 0.0  # Track proactive guidance effectiveness,
    last_intelligence_update: datetime = field(default_factory=datetime.now)

    # Metadata
    created_at: datetime = (field(default_factory=datetime.now),)
    updated_at: datetime = field(default_factory=datetime.now)

    def suggest_relevant_domains(
        self, user_query: str, query_context: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """
        Suggest relevant domains based on user query and learned patterns.

        Simple keyword-based suggestion with learned preferences.
        """
        query_lower = user_query.lower()
        suggested_domains = []

        # Extract domain suggestions based on learned patterns
        for keywords, domains in self.domain_query_mapping.items():
            if any(keyword in query_lower for keyword in keywords):
                for domain in domains:
                    relevance_score = self._calculate_domain_relevance(
                        domain, query_lower, query_context
                    )
                    suggested_domains.append(
                        {
                            "domain": domain,
                            "relevance_score": relevance_score,
                            "integration_potential": self._assess_integration_potential(
                                domain, query_context
                            ),
                        }
                    )

        # Add default domain mapping if no patterns match
        if not suggested_domains:
            default_domains = self._get_default_domain_suggestions(query_lower)
            suggested_domains.extend(default_domains)

        # Sort by relevance and return top suggestions
        suggested_domains.sort(key=itemgetter("relevance_score"), reverse=True)
        return suggested_domains[:5]  # Return top 5 relevant domains

    def predict_integration_success(
        self, domains: list[str], integration_context: dict[str, Any]
    ) -> float:
        """
        Predict how successfully these domains will integrate for the user.

        Simple pattern-based prediction with learned success rates.
        """
        if len(domains) <= 1:
            return 0.8  # Single domain is usually successful

        # Calculate success based on learned domain combinations
        domain_set_key = "_".join(sorted(domains))
        base_success = self.successful_domain_combinations.get(domain_set_key, 0.5)

        # Adjust for domain interaction patterns
        interaction_bonus = 0.0
        interaction_count = 0

        for i, domain1 in enumerate(domains):
            for domain2 in domains[i + 1 :]:
                pair_key = f"{domain1}_{domain2}"
                reverse_key = f"{domain2}_{domain1}"

                interaction_score = (
                    self.domain_interaction_patterns.get(pair_key, 0.5)
                    + self.domain_interaction_patterns.get(reverse_key, 0.5)
                ) / 2

                interaction_bonus += interaction_score
                interaction_count += 1

        if interaction_count > 0:
            avg_interaction = interaction_bonus / interaction_count
            predicted_success = (base_success * 0.6) + (avg_interaction * 0.4)
        else:
            predicted_success = base_success

        # Adjust for user context preferences
        context_factor = self._calculate_context_alignment(integration_context)
        final_prediction = predicted_success * context_factor

        return min(1.0, max(0.0, final_prediction))

    def optimize_conversation_approach(
        self,
        user_query: str,
        user_context: dict[str, Any],
        _conversation_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Optimize conversation style and approach based on learned patterns.

        Simple style selection and response planning.
        """
        # Determine query complexity
        query_complexity = self._assess_query_complexity(user_query, user_context)

        # Select optimal conversation style
        optimal_style = self._select_optimal_conversation_style(query_complexity, user_context)

        # Plan response structure
        return {
            "conversation_style": optimal_style,
            "complexity_level": query_complexity,
            "recommended_domains": self.suggest_relevant_domains(user_query, user_context),
            "integration_approach": self._plan_integration_approach(query_complexity),
            "followup_suggestions": self._generate_followup_suggestions(user_query, optimal_style),
        }

    def learn_from_conversation(
        self,
        conversation_data: dict[str, Any],
        user_feedback: dict[str, Any],
        outcome_quality: IntegrationSuccess,
    ) -> None:
        """
        Learn from conversation outcomes to improve future interactions.

        Simple pattern updates based on feedback.
        """
        # Update domain interaction patterns
        domains_used = conversation_data.get("domains_involved", [])
        if len(domains_used) > 1:
            success_score = self._integration_success_to_score(outcome_quality)
            domain_set_key = "_".join(sorted(domains_used))

            # Update successful combinations
            current_success = self.successful_domain_combinations.get(domain_set_key, 0.5)
            (current_success * 0.8) + (success_score * 0.2)  # Simple learning
            # Note: In actual implementation, this would need to be handled differently due to frozen dataclass

        # Update conversation style effectiveness
        style_used = conversation_data.get("conversation_style")
        if style_used:
            user_feedback.get("satisfaction_score", 0.5)
            self.conversation_style_effectiveness.get(style_used, 0.5)
            # Learning would be applied in actual mutable implementation

        # Update pattern recognition accuracy
        predicted_success = conversation_data.get("predicted_success", 0.5)
        actual_success = self._integration_success_to_score(outcome_quality)
        1.0 - abs(predicted_success - actual_success)
        # Accuracy updates would be applied in actual implementation

    # Helper Methods for Implementation
    def _calculate_domain_relevance(
        self, domain: str, query: str, _context: dict[str, Any]
    ) -> float:
        """Calculate relevance score for a domain given the query."""
        # Simple keyword-based relevance calculation
        domain_keywords = {
            "knowledge": ["learn", "know", "understand", "information", "research"],
            "learning": ["study", "skill", "course", "practice", "develop"],
            "tasks": ["do", "complete", "work", "project", "deadline"],
            "events": ["meeting", "appointment", "schedule", "calendar", "time"],
            "habits": ["routine", "daily", "regular", "practice", "habit"],
            "goals": ["achieve", "target", "objective", "aim", "accomplish"],
            "principles": ["values", "ethics", "moral", "principle", "belief"],
            "choices": ["decide", "choose", "option", "decision", "alternative"],
            "user_context": ["me", "my", "personal", "profile", "preference"],
        }

        keywords = domain_keywords.get(domain.lower(), [])
        relevance = (
            sum(1 for keyword in keywords if keyword in query) / len(keywords) if keywords else 0.1
        )

        # Boost based on user preferences
        preference_boost = self.user_context_preferences.get(domain, 0.5)
        return min(1.0, relevance + (preference_boost * 0.3))

    def _assess_integration_potential(self, domain: str, _context: dict[str, Any]) -> float:
        """Assess how well this domain might integrate with others."""
        # Simple assessment based on learned patterns
        avg_interaction = 0.5
        interaction_count = 0

        for other_domain in [
            "knowledge",
            "learning",
            "tasks",
            "events",
            "habits",
            "goals",
            "principles",
            "choices",
        ]:
            if other_domain != domain:
                pair_key = f"{domain}_{other_domain}"
                interaction_score = self.domain_interaction_patterns.get(pair_key, 0.5)
                avg_interaction += interaction_score
                interaction_count += 1

        return avg_interaction / interaction_count if interaction_count > 0 else 0.5

    def _get_default_domain_suggestions(self, _query: str) -> list[dict[str, Any]]:
        """Get default domain suggestions when no patterns match."""
        return [
            {"domain": "knowledge", "relevance_score": 0.6, "integration_potential": 0.7},
            {"domain": "tasks", "relevance_score": 0.5, "integration_potential": 0.8},
            {"domain": "goals", "relevance_score": 0.5, "integration_potential": 0.9},
        ]

    def _calculate_context_alignment(self, context: dict[str, Any]) -> float:
        """Calculate how well the integration aligns with user context."""
        # Simple context alignment calculation
        context_type = context.get("type", "general")
        return self.user_context_preferences.get(context_type, 0.8)

    def _assess_query_complexity(self, query: str, _context: dict[str, Any]) -> QueryComplexity:
        """Assess complexity of user query."""
        # Simple complexity assessment
        word_count = len(query.split())
        question_count = query.count("?")
        complex_words = ["how", "why", "integrate", "coordinate", "optimize", "balance"]

        complexity_score = 0
        if word_count > 20:
            complexity_score += 1
        if question_count > 1:
            complexity_score += 1
        if any(word in query.lower() for word in complex_words):
            complexity_score += 1

        if complexity_score >= 3:
            return QueryComplexity.SYSTEMIC
        elif complexity_score == 2:
            return QueryComplexity.COMPLEX
        elif complexity_score == 1:
            return QueryComplexity.MODERATE
        else:
            return QueryComplexity.SIMPLE

    def _select_optimal_conversation_style(
        self, complexity: QueryComplexity, _context: dict[str, Any]
    ) -> ConversationStyle:
        """Select optimal conversation style based on complexity and context."""
        # Simple style selection logic
        complexity_style_map = {
            QueryComplexity.SIMPLE: ConversationStyle.DIRECT,
            QueryComplexity.MODERATE: ConversationStyle.ANALYTICAL,
            QueryComplexity.COMPLEX: ConversationStyle.EXPLORATORY,
            QueryComplexity.SYSTEMIC: ConversationStyle.COACHING,
        }

        suggested_style = complexity_style_map.get(complexity, ConversationStyle.DIRECT)

        # Check user preferences for this style
        style_effectiveness = self.conversation_style_effectiveness.get(suggested_style, 0.5)
        if style_effectiveness < 0.4:  # If this style doesn't work well for user
            # Fall back to most effective style for this user
            return max(
                self.conversation_style_effectiveness.items(),
                key=itemgetter(1),
                default=(ConversationStyle.DIRECT, 0.5),
            )[0]

        return suggested_style

    def _plan_integration_approach(self, complexity: QueryComplexity) -> str:
        """Plan approach for domain integration based on complexity."""
        approach_map = {
            QueryComplexity.SIMPLE: "direct_domain_lookup",
            QueryComplexity.MODERATE: "dual_domain_synthesis",
            QueryComplexity.COMPLEX: "multi_domain_coordination",
            QueryComplexity.SYSTEMIC: "full_ecosystem_integration",
        }
        return approach_map.get(complexity, "direct_domain_lookup")

    def _generate_followup_suggestions(self, _query: str, style: ConversationStyle) -> list[str]:
        """Generate followup suggestions based on query and style."""
        # Simple followup generation
        style_followups = {
            ConversationStyle.DIRECT: ["Would you like specific next steps?"],
            ConversationStyle.EXPLORATORY: ["What aspects would you like to explore further?"],
            ConversationStyle.SUPPORTIVE: ["How does this align with your current situation?"],
            ConversationStyle.ANALYTICAL: ["Would you like me to analyze the data patterns?"],
            ConversationStyle.CREATIVE: ["What other approaches might we consider?"],
            ConversationStyle.COACHING: ["What insights does this give you about your goals?"],
        }
        return style_followups.get(style, ["How else can I help?"])

    def _integration_success_to_score(self, success: IntegrationSuccess) -> float:
        """Convert integration success enum to numeric score."""
        success_map = {
            IntegrationSuccess.EXCELLENT: 1.0,
            IntegrationSuccess.GOOD: 0.8,
            IntegrationSuccess.ACCEPTABLE: 0.6,
            IntegrationSuccess.POOR: 0.4,
            IntegrationSuccess.FAILED: 0.2,
        }
        return success_map.get(success, 0.5)

    # ========================================================================
    # SMART ORCHESTRATION METHODS
    # ========================================================================

    def analyze_domain_states(
        self, current_user_context: dict[str, Any], domain_data_snapshots: dict[str, dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        """
        Analyze current state of all domains to identify patterns and opportunities.

        Returns comprehensive domain state analysis with actionable insights.
        """
        domain_analysis = {}

        for domain, data_snapshot in domain_data_snapshots.items():
            analysis = {
                "activity_level": self._assess_domain_activity(domain, data_snapshot),
                "alignment_with_goals": self._assess_goal_alignment(
                    domain, data_snapshot, current_user_context
                ),
                "optimization_potential": self._identify_optimization_opportunities(
                    domain, data_snapshot
                ),
                "conflict_indicators": self._detect_domain_conflicts(
                    domain, data_snapshot, domain_data_snapshots
                ),
                "readiness_for_enhancement": self.domain_readiness_assessment.get(domain, 0.5),
                "temporal_patterns": self._analyze_temporal_effectiveness(
                    domain, current_user_context
                ),
            }
            domain_analysis[domain] = analysis

        return domain_analysis

    def generate_proactive_guidance(
        self,
        user_context: dict[str, Any],
        domain_states: dict[str, dict[str, Any]],
        recent_patterns: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Generate proactive guidance based on domain states and learned patterns.

        Identifies opportunities for improvement and suggests actions before user asks.
        """
        guidance_suggestions = []

        # Analyze lifecycle stage and suggest appropriate actions
        lifecycle_stage = self._determine_user_lifecycle_stage(user_context, recent_patterns)
        stage_guidance = self.user_lifecycle_stage_patterns.get(lifecycle_stage, [])

        for guidance_type in stage_guidance:
            if guidance_type in self.proactive_guidance_patterns:
                suggestions = self.proactive_guidance_patterns[guidance_type]
                for suggestion in suggestions:
                    impact_score = self.optimization_opportunity_detection.get(guidance_type, 0.5)

                    guidance_suggestions.append(
                        {
                            "type": guidance_type,
                            "suggestion": suggestion,
                            "impact_score": impact_score,
                            "relevant_domains": self._identify_relevant_domains_for_guidance(
                                guidance_type
                            ),
                            "timing": self._optimize_guidance_timing(guidance_type, user_context),
                            "confidence": self._calculate_guidance_confidence(
                                guidance_type, recent_patterns
                            ),
                        }
                    )

        # Detect cross-domain conflicts and suggest resolutions
        conflicts = self._detect_cross_domain_conflicts(domain_states)
        for conflict in conflicts:
            resolution_strategy = self.conflict_detection_patterns.get(
                conflict["type"], "general_alignment"
            )
            guidance_suggestions.append(
                {
                    "type": "conflict_resolution",
                    "suggestion": f"Resolve {conflict['description']} using {resolution_strategy}",
                    "impact_score": conflict["severity"],
                    "relevant_domains": conflict["affected_domains"],
                    "timing": "immediate",
                    "confidence": 0.8,
                }
            )

        # Sort by impact score and return top suggestions
        guidance_suggestions.sort(key=itemgetter("impact_score"), reverse=True)
        return guidance_suggestions[:5]  # Return top 5 actionable guidance items

    def monitor_context_changes(
        self, previous_context: dict[str, Any], current_context: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Monitor changes in user context and adapt orchestration accordingly.

        Tracks context evolution and adjusts domain coordination strategies.
        """
        context_changes = {
            "significant_changes": [],
            "emerging_patterns": [],
            "adaptation_recommendations": [],
            "memory_updates": [],
        }

        # Identify significant changes
        for key, current_value in current_context.items():
            previous_value = previous_context.get(key)
            if previous_value != current_value:
                change_significance = self._assess_change_significance(
                    key, previous_value, current_value
                )
                if change_significance > 0.7:  # Significant change threshold
                    context_changes["significant_changes"].append(
                        {
                            "attribute": key,
                            "previous": previous_value,
                            "current": current_value,
                            "significance": change_significance,
                            "adaptation_needed": self._determine_adaptation_needs(
                                key, current_value
                            ),
                        }
                    )

        # Update context awareness memory
        memory_updates = self._update_context_memory(current_context)
        context_changes["memory_updates"] = memory_updates

        # Generate adaptation recommendations
        for change in context_changes["significant_changes"]:
            recommendations = self._generate_adaptation_recommendations(change)
            context_changes["adaptation_recommendations"].extend(recommendations)

        return context_changes

    def optimize_domain_coordination(
        self,
        target_outcome: str,
        available_domains: list[str],
        current_constraints: dict[str, Any],
        _user_preferences: dict[str, float],
    ) -> dict[str, Any]:
        """
        Optimize coordination between domains for specific outcomes.

        Intelligently sequences and coordinates domain interactions for maximum effectiveness.
        """
        coordination_plan = {
            "primary_sequence": [],
            "parallel_opportunities": [],
            "synergy_maximization": [],
            "constraint_mitigation": [],
            "success_probability": 0.0,
        }

        # Determine optimal domain sequence for target outcome
        domain_effectiveness_for_outcome = {}
        for domain in available_domains:
            effectiveness = self._calculate_domain_effectiveness_for_outcome(domain, target_outcome)
            domain_effectiveness_for_outcome[domain] = effectiveness

        # Sort domains by effectiveness and create primary sequence
        sorted_domains = sorted(
            available_domains, key=domain_effectiveness_for_outcome.get, reverse=True
        )

        # Build coordination sequence with synergy optimization
        primary_sequence = []
        for i, domain in enumerate(sorted_domains):
            step = {
                "domain": domain,
                "sequence_position": i + 1,
                "effectiveness_score": domain_effectiveness_for_outcome[domain],
                "synergy_opportunities": self._identify_synergy_opportunities(
                    domain, sorted_domains[i + 1 :]
                ),
            }
            primary_sequence.append(step)

        coordination_plan["primary_sequence"] = primary_sequence

        # Identify parallel processing opportunities
        parallel_opportunities = self._identify_parallel_opportunities(
            sorted_domains, current_constraints
        )
        coordination_plan["parallel_opportunities"] = parallel_opportunities

        # Calculate overall success probability
        base_probability = sum(domain_effectiveness_for_outcome.values()) / len(available_domains)
        synergy_bonus = self._calculate_synergy_bonus(sorted_domains)
        constraint_penalty = self._assess_constraint_impact(current_constraints)

        coordination_plan["success_probability"] = min(
            1.0, base_probability + synergy_bonus - constraint_penalty
        )

        return coordination_plan

    def learn_from_orchestration_outcomes(
        self,
        orchestration_session: dict[str, Any],
        actual_outcomes: dict[str, Any],
        _user_feedback: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Learn from orchestration outcomes to improve future coordination.

        Continuous learning from real orchestration results to enhance intelligence.
        """
        learning_insights = {
            "pattern_updates": [],
            "strategy_refinements": [],
            "confidence_adjustments": [],
            "new_discoveries": [],
        }

        # Analyze prediction accuracy
        predicted_success = orchestration_session.get("predicted_success", 0.5)
        actual_success = self._calculate_actual_success_score(actual_outcomes)
        1.0 - abs(predicted_success - actual_success)

        # Update domain interaction patterns based on observed outcomes
        domains_used = orchestration_session.get("domains_involved", [])
        for i, domain1 in enumerate(domains_used):
            for domain2 in domains_used[i + 1 :]:
                pair_key = f"{domain1}_{domain2}"
                current_synergy = self.domain_interaction_patterns.get(pair_key, 0.5)
                observed_synergy = actual_outcomes.get("domain_synergies", {}).get(
                    pair_key, current_synergy
                )

                # Learning would update patterns in actual mutable implementation
                learning_insights["pattern_updates"].append(
                    {
                        "pair": pair_key,
                        "previous_synergy": current_synergy,
                        "observed_synergy": observed_synergy,
                        "adjustment_needed": abs(current_synergy - observed_synergy) > 0.1,
                    }
                )

        # Learn from proactive guidance effectiveness
        guidance_given = orchestration_session.get("proactive_guidance", [])
        guidance_outcomes = actual_outcomes.get("guidance_effectiveness", {})

        for guidance in guidance_given:
            guidance_type = guidance.get("type")
            actual_effectiveness = guidance_outcomes.get(guidance_type, 0.5)
            predicted_impact = guidance.get("impact_score", 0.5)

            learning_insights["strategy_refinements"].append(
                {
                    "guidance_type": guidance_type,
                    "predicted_impact": predicted_impact,
                    "actual_effectiveness": actual_effectiveness,
                    "learning_delta": actual_effectiveness - predicted_impact,
                }
            )

        return learning_insights

    # ========================================================================
    # HELPER METHODS FOR SMART ORCHESTRATION
    # ========================================================================

    def _assess_domain_activity(self, _domain: str, data_snapshot: dict[str, Any]) -> float:
        """Assess current activity level in a domain."""
        activity_indicators = data_snapshot.get("activity_indicators", {})
        recent_items = activity_indicators.get("recent_items_count", 0)
        last_update = activity_indicators.get("days_since_last_update", 30)

        # Simple activity scoring
        activity_score = min(1.0, recent_items / 10.0)  # Normalize to 0-1
        recency_factor = max(0.1, 1.0 - (last_update / 30.0))  # Recent activity bonus

        return activity_score * recency_factor

    def _assess_goal_alignment(
        self, _domain: str, data_snapshot: dict[str, Any], user_context: dict[str, Any]
    ) -> float:
        """Assess how well domain activity aligns with user goals."""
        domain_focus = data_snapshot.get("primary_focus_areas", [])
        user_goals = user_context.get("active_goals", [])

        # Simple alignment calculation
        alignment_count = 0
        for goal in user_goals:
            for focus_area in domain_focus:
                if any(keyword in focus_area.lower() for keyword in goal.lower().split()):
                    alignment_count += 1
                    break

        return alignment_count / max(len(user_goals), 1)

    def _identify_optimization_opportunities(
        self, _domain: str, data_snapshot: dict[str, Any]
    ) -> list[str]:
        """Identify optimization opportunities within a domain."""
        opportunities = []

        # Check for common optimization patterns
        completion_rate = data_snapshot.get("completion_rate", 0.8)
        if completion_rate < 0.7:
            opportunities.append("improve_completion_strategies")

        consistency_score = data_snapshot.get("consistency_score", 0.8)
        if consistency_score < 0.6:
            opportunities.append("enhance_consistency_patterns")

        efficiency_score = data_snapshot.get("efficiency_score", 0.8)
        if efficiency_score < 0.7:
            opportunities.append("optimize_efficiency_workflows")

        return opportunities

    def _detect_domain_conflicts(
        self, domain: str, data_snapshot: dict[str, Any], all_domains: dict[str, dict[str, Any]]
    ) -> list[str]:
        """Detect conflicts between this domain and others."""
        conflicts = []

        domain_priorities = data_snapshot.get("priority_focus", [])
        domain_time_allocation = data_snapshot.get("time_allocation_percentage", 0)

        for other_domain, other_data in all_domains.items():
            if other_domain != domain:
                other_priorities = other_data.get("priority_focus", [])
                other_time_allocation = other_data.get("time_allocation_percentage", 0)

                # Check for priority conflicts
                if any(priority in other_priorities for priority in domain_priorities):
                    conflicts.append(f"priority_conflict_with_{other_domain}")

                # Check for time allocation conflicts
                if domain_time_allocation + other_time_allocation > 0.8:  # Over-allocation
                    conflicts.append(f"time_conflict_with_{other_domain}")

        return conflicts

    def _analyze_temporal_effectiveness(
        self, domain: str, current_context: dict[str, Any]
    ) -> TemporalEffectiveness:
        """Analyze temporal patterns of domain effectiveness."""
        current_time_context = current_context.get("time_context", {})
        time_of_day = current_time_context.get("time_of_day", "unknown")
        day_of_week = current_time_context.get("day_of_week", "unknown")

        temporal_key = f"{time_of_day}_{day_of_week}"
        domain_temporal_patterns = self.temporal_pattern_analysis.get(domain, {})

        return {
            "current_effectiveness": domain_temporal_patterns.get(temporal_key, 0.5),
            "optimal_timing": max(
                domain_temporal_patterns.items(), key=itemgetter(1), default=("unknown", 0.5)
            )[0]
            if domain_temporal_patterns
            else "unknown",
            "timing_optimization_potential": max(domain_temporal_patterns.values(), default=0.5)
            - domain_temporal_patterns.get(temporal_key, 0.5),
        }

    def _determine_user_lifecycle_stage(
        self, user_context: dict[str, Any], _recent_patterns: list[dict[str, Any]]
    ) -> str:
        """Determine user's current lifecycle stage for targeted guidance."""
        # Simple lifecycle determination based on context and patterns
        experience_level = user_context.get("experience_level", "intermediate")
        goal_complexity = user_context.get("goal_complexity", "moderate")
        engagement_level = user_context.get("engagement_level", "moderate")

        if experience_level == "beginner" and engagement_level == "high":
            return "onboarding_active"
        elif experience_level == "intermediate" and goal_complexity == "high":
            return "scaling_up"
        elif engagement_level == "low":
            return "needs_motivation"
        else:
            return "steady_optimization"

    def _identify_relevant_domains_for_guidance(self, guidance_type: str) -> list[str]:
        """Identify which domains are relevant for specific guidance."""
        guidance_domain_mapping = {
            "goal_alignment": ["goals", "habits", "tasks"],
            "productivity_optimization": ["tasks", "events", "habits"],
            "learning_acceleration": ["knowledge", "learning", "goals"],
            "decision_enhancement": ["choices", "principles", "knowledge"],
            "motivation_boost": ["goals", "principles", "habits"],
        }
        return guidance_domain_mapping.get(guidance_type, ["goals", "tasks"])

    def _optimize_guidance_timing(self, _guidance_type: str, user_context: dict[str, Any]) -> str:
        """Determine optimal timing for delivering guidance."""
        urgency_level = user_context.get("urgency_level", "moderate")
        user_availability = user_context.get("availability", "moderate")

        if urgency_level == "high":
            return "immediate"
        elif user_availability == "high":
            return "next_interaction"
        else:
            return "when_convenient"

    def _calculate_guidance_confidence(
        self, guidance_type: str, recent_patterns: list[dict[str, Any]]
    ) -> float:
        """Calculate confidence in guidance recommendation."""
        base_confidence = 0.6

        # Boost confidence based on pattern consistency
        pattern_consistency = self._assess_pattern_consistency(guidance_type, recent_patterns)
        confidence_boost = pattern_consistency * 0.3

        return min(1.0, base_confidence + confidence_boost)

    def _detect_cross_domain_conflicts(
        self, domain_states: dict[str, dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Detect conflicts across multiple domains."""
        conflicts = []

        # Check for resource allocation conflicts
        total_time_allocation = sum(
            state.get("time_allocation_percentage", 0) for state in domain_states.values()
        )
        if total_time_allocation > 1.0:
            conflicts.append(
                {
                    "type": "resource_overallocation",
                    "description": "Total time allocation exceeds 100%",
                    "severity": 0.8,
                    "affected_domains": list(domain_states.keys()),
                }
            )

        # Check for priority conflicts
        all_priorities = []
        priority_domains = {}
        for domain, state in domain_states.items():
            priorities = state.get("priority_focus", [])
            for priority in priorities:
                if priority in all_priorities:
                    conflicts.append(
                        {
                            "type": "priority_conflict",
                            "description": f"Competing priorities for {priority}",
                            "severity": 0.6,
                            "affected_domains": [domain, priority_domains[priority]],
                        }
                    )
                else:
                    all_priorities.append(priority)
                    priority_domains[priority] = domain

        return conflicts

    def _assess_change_significance(
        self, attribute: str, _previous_value: Any, _current_value: Any
    ) -> float:
        """Assess significance of a context change."""
        # Simple significance assessment
        if attribute in ["life_stage", "primary_goals", "work_situation"]:
            return 0.9  # High significance
        elif attribute in ["energy_level", "motivation", "focus_areas"]:
            return 0.7  # Moderate significance
        else:
            return 0.3  # Low significance

    def _determine_adaptation_needs(self, attribute: str, _new_value: Any) -> list[str]:
        """Determine what adaptations are needed for context changes."""
        adaptation_mapping = {
            "life_stage": ["update_goal_priorities", "adjust_time_allocation"],
            "work_situation": ["revise_productivity_patterns", "update_schedule_preferences"],
            "energy_level": ["optimize_task_timing", "adjust_complexity_preferences"],
        }
        return adaptation_mapping.get(attribute, ["general_recalibration"])

    def _update_context_memory(self, current_context: dict[str, Any]) -> list[str]:
        """Update context awareness memory with current information."""
        memory_updates = []

        for key, value in current_context.items():
            if (
                key not in self.context_awareness_memory
                or self.context_awareness_memory[key] != value
            ):
                memory_updates.append(
                    f"Updated {key}: {self.context_awareness_memory.get(key)} -> {value}"
                )
                # In actual implementation, would update the memory (handling immutable constraints)

        return memory_updates

    def _generate_adaptation_recommendations(self, change: dict[str, Any]) -> list[dict[str, Any]]:
        """Generate specific adaptation recommendations for context changes."""
        return [
            {
                "type": "context_adaptation",
                "action": adaptation,
                "priority": "high" if change["significance"] > 0.8 else "moderate",
                "affected_attribute": change["attribute"],
            }
            for adaptation in change["adaptation_needed"]
        ]

    def _calculate_domain_effectiveness_for_outcome(
        self, domain: str, target_outcome: str
    ) -> float:
        """Calculate how effective a domain is for achieving a specific outcome."""
        # Simple outcome-domain effectiveness mapping
        outcome_domain_effectiveness = {
            "skill_development": {"learning": 0.9, "knowledge": 0.8, "goals": 0.7, "habits": 0.6},
            "productivity_improvement": {"tasks": 0.9, "habits": 0.8, "events": 0.7, "goals": 0.6},
            "decision_making": {"choices": 0.9, "principles": 0.8, "knowledge": 0.7, "goals": 0.5},
            "life_balance": {"principles": 0.8, "goals": 0.7, "habits": 0.7, "events": 0.6},
        }

        return outcome_domain_effectiveness.get(target_outcome, {}).get(domain, 0.5)

    def _identify_synergy_opportunities(
        self, primary_domain: str, other_domains: list[str]
    ) -> list[dict[str, Any]]:
        """Identify synergy opportunities between domains."""
        synergies = []

        for other_domain in other_domains:
            pair_key = f"{primary_domain}_{other_domain}"
            synergy_score = self.domain_interaction_patterns.get(pair_key, 0.5)

            if synergy_score > 0.7:  # High synergy threshold
                synergies.append(
                    {
                        "domain": other_domain,
                        "synergy_score": synergy_score,
                        "synergy_type": self._classify_synergy_type(primary_domain, other_domain),
                    }
                )

        return synergies

    def _identify_parallel_opportunities(
        self, domains: list[str], constraints: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Identify opportunities for parallel domain processing."""
        parallel_opportunities = []

        resource_availability = constraints.get("resource_availability", 1.0)
        time_availability = constraints.get("time_availability", 1.0)

        if resource_availability > 0.7 and time_availability > 0.6:
            # Can handle multiple domains in parallel
            for i in range(0, len(domains), 2):  # Process in pairs
                if i + 1 < len(domains):
                    domain1, domain2 = domains[i], domains[i + 1]
                    synergy_score = self.domain_interaction_patterns.get(
                        f"{domain1}_{domain2}", 0.5
                    )

                    parallel_opportunities.append(
                        {
                            "domains": [domain1, domain2],
                            "synergy_potential": synergy_score,
                            "resource_requirement": 0.6,  # Estimated resource need
                        }
                    )

        return parallel_opportunities

    def _calculate_synergy_bonus(self, domains: list[str]) -> float:
        """Calculate synergy bonus for domain combination."""
        if len(domains) < 2:
            return 0.0

        total_synergy = 0.0
        pair_count = 0

        for i, domain1 in enumerate(domains):
            for domain2 in domains[i + 1 :]:
                pair_key = f"{domain1}_{domain2}"
                synergy = self.domain_interaction_patterns.get(pair_key, 0.5)
                total_synergy += synergy
                pair_count += 1

        avg_synergy = total_synergy / pair_count if pair_count > 0 else 0.5
        return max(0.0, avg_synergy - 0.5) * 0.2  # Bonus for above-average synergy

    def _assess_constraint_impact(self, constraints: dict[str, Any]) -> float:
        """Assess negative impact of constraints on coordination success."""
        impact = 0.0

        time_constraint = 1.0 - constraints.get("time_availability", 1.0)
        resource_constraint = 1.0 - constraints.get("resource_availability", 1.0)
        complexity_constraint = constraints.get("complexity_penalty", 0.0)

        impact = (time_constraint + resource_constraint + complexity_constraint) / 3
        return impact * 0.3  # Constraint penalty factor

    def _calculate_actual_success_score(self, outcomes: dict[str, Any]) -> float:
        """Calculate actual success score from orchestration outcomes."""
        user_satisfaction = outcomes.get("user_satisfaction", 3) / 5.0  # Convert 1-5 to 0-1
        goal_progress = outcomes.get("goal_progress", 0.5)
        efficiency_score = outcomes.get("efficiency_score", 0.5)

        return (user_satisfaction + goal_progress + efficiency_score) / 3

    def _assess_pattern_consistency(
        self, guidance_type: str, recent_patterns: list[dict[str, Any]]
    ) -> float:
        """Assess consistency of recent patterns for guidance confidence."""
        if not recent_patterns:
            return 0.5

        relevant_patterns = [p for p in recent_patterns if p.get("type") == guidance_type]
        if not relevant_patterns:
            return 0.3

        # Simple consistency measure
        success_rates = [p.get("success_rate", 0.5) for p in relevant_patterns]
        variance = sum(
            (x - sum(success_rates) / len(success_rates)) ** 2 for x in success_rates
        ) / len(success_rates)
        return max(0.0, 1.0 - variance)  # Lower variance = higher consistency

    def _classify_synergy_type(self, domain1: str, domain2: str) -> str:
        """Classify the type of synergy between two domains."""
        synergy_types = {
            ("goals", "habits"): "reinforcement_synergy",
            ("knowledge", "learning"): "information_flow_synergy",
            ("tasks", "events"): "scheduling_synergy",
            ("principles", "choices"): "values_alignment_synergy",
            ("learning", "goals"): "progression_synergy",
        }

        pair = tuple(sorted([domain1, domain2]))
        return synergy_types.get(pair, "general_synergy")


@dataclass(frozen=True)
class AskesisApplicationIntelligence:
    """
    Persistent Askesis Application Intelligence Entity.

    Tracks specific conversations, domain integrations, and learning
    generated from cross-domain orchestration experiences.

    Essential conversation tracking and basic outcome analysis.
    """

    uid: str
    conversation_uid: str  # The conversation this tracks
    user_uid: str
    application_context: str

    # Conversation Details
    user_query: str
    query_complexity: QueryComplexity = QueryComplexity.SIMPLE
    conversation_style_used: ConversationStyle = ConversationStyle.DIRECT
    domains_involved: list[str] = field(default_factory=list)

    # Integration Analysis
    integration_approach: str = "direct_domain_lookup"
    predicted_integration_success: float = 0.5
    actual_integration_success: IntegrationSuccess | None = None

    # Response Quality
    response_satisfaction: int = 3  # 1-5 scale,
    response_helpfulness: int = 3  # 1-5 scale,
    response_clarity: int = 3  # 1-5 scale

    # Outcome Tracking
    user_action_taken: bool = False

    followup_questions: list[str] = (field(default_factory=list),)
    learning_generated: list[str] = (field(default_factory=list),)
    integration_insights: list[str] = field(default_factory=list)

    # Cross-Domain Effects
    domains_accessed: list[str] = (field(default_factory=list),)
    domain_data_retrieved: dict[str, Any] = (field(default_factory=dict),)
    cross_domain_patterns_identified: list[str] = field(default_factory=list)

    # Meta-Analysis
    conversation_effectiveness: float = 0.5  # 0-1 scale,
    domain_coordination_quality: float = 0.5  # How well domains were coordinated,
    synthesis_quality: float = 0.5  # How well information was synthesized,
    user_engagement_level: float = 0.5  # User engagement during conversation

    # Timing and Processing
    conversation_timestamp: datetime = (field(default_factory=datetime.now),)
    response_generation_time_seconds: float = 2.0
    domains_processing_time: dict[str, float] = field(default_factory=dict)

    def get_conversation_effectiveness_score(self) -> float:
        """Calculate overall effectiveness of this conversation."""
        satisfaction_score = self.response_satisfaction / 5.0
        helpfulness_score = self.response_helpfulness / 5.0
        clarity_score = self.response_clarity / 5.0

        return (
            satisfaction_score * 0.3
            + helpfulness_score * 0.4
            + clarity_score * 0.2
            + self.user_engagement_level * 0.1
        )

    def generated_cross_domain_insights(self) -> bool:
        """Check if conversation generated cross-domain insights."""
        return len(self.integration_insights) > 0

    def had_successful_domain_coordination(self) -> bool:
        """Check if domain coordination was successful."""
        return self.domain_coordination_quality > 0.6

    def extract_learning_patterns(self) -> dict[str, float]:
        """Extract patterns for Askesis learning algorithms."""
        return {
            "conversation_effectiveness": self.get_conversation_effectiveness_score(),
            "domain_coordination_success": self.domain_coordination_quality,
            "synthesis_quality": self.synthesis_quality,
            "user_engagement": self.user_engagement_level,
            "integration_prediction_accuracy": self._calculate_prediction_accuracy(),
            "complexity_handling": self._assess_complexity_handling(),
            "style_appropriateness": self._assess_style_appropriateness(),
        }

    def _calculate_prediction_accuracy(self) -> float:
        """Calculate accuracy of integration success prediction."""
        if self.actual_integration_success is None:
            return 0.5  # No actual outcome to compare

        actual_score = {
            IntegrationSuccess.EXCELLENT: 1.0,
            IntegrationSuccess.GOOD: 0.8,
            IntegrationSuccess.ACCEPTABLE: 0.6,
            IntegrationSuccess.POOR: 0.4,
            IntegrationSuccess.FAILED: 0.2,
        }.get(self.actual_integration_success, 0.5)

        return 1.0 - abs(self.predicted_integration_success - actual_score)

    def _assess_complexity_handling(self) -> float:
        """Assess how well the complexity was handled."""
        complexity_factor = {
            QueryComplexity.SIMPLE: 1.0,
            QueryComplexity.MODERATE: 0.8,
            QueryComplexity.COMPLEX: 0.6,
            QueryComplexity.SYSTEMIC: 0.4,
        }.get(self.query_complexity, 0.5)

        return self.conversation_effectiveness * complexity_factor

    def _assess_style_appropriateness(self) -> float:
        """Assess appropriateness of conversation style used."""
        # Simple assessment - could be enhanced with user feedback
        return self.response_satisfaction / 5.0


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================


def create_askesis_intelligence(
    user_uid: str, initial_patterns: dict[str, Any] | None = None
) -> AskesisIntelligence:
    """Factory function for creating AskesisIntelligence entities."""
    uid = f"ai_{user_uid}_{datetime.now().isoformat()}"

    # Initialize with basic domain interaction patterns
    default_patterns = {
        "knowledge_learning": 0.9,
        "goals_habits": 0.8,
        "principles_choices": 0.85,
        "tasks_events": 0.7,
        "learning_goals": 0.8,
    }

    return AskesisIntelligence(
        uid=uid,
        user_uid=user_uid,
        domain_interaction_patterns=initial_patterns.get("domain_interactions", default_patterns)
        if initial_patterns
        else default_patterns,
        domain_query_mapping={
            frozenset(["learn", "study", "knowledge"]): {"knowledge", "learning"},
            frozenset(["goal", "achieve", "target"]): {"goals", "habits", "tasks"},
            frozenset(["decide", "choose", "option"]): {"choices", "principles"},
            frozenset(["schedule", "time", "calendar"]): {"events", "tasks", "habits"},
        },
    )


def create_askesis_application_intelligence(
    conversation_uid: str,
    user_uid: str,
    user_query: str,
    domains_involved: list[str],
    conversation_style: ConversationStyle = ConversationStyle.DIRECT,
) -> AskesisApplicationIntelligence:
    """Factory function for creating AskesisApplicationIntelligence entities."""
    uid = f"aai_{conversation_uid}_{datetime.now().isoformat()}"

    return AskesisApplicationIntelligence(
        uid=uid,
        conversation_uid=conversation_uid,
        user_uid=user_uid,
        application_context=f"askesis_conversation_{conversation_uid}",
        user_query=user_query,
        conversation_style_used=conversation_style,
        domains_involved=domains_involved,
    )
