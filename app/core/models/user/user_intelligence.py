"""
User Intelligence Integration - Revolutionary Enhancement
=======================================================

Enhanced UserContext with persistent intelligence integration that leverages
the revolutionary Knowledge/Learning/Search intelligence patterns.

This transforms UserContext from a static aggregator to an adaptive,
learning-aware context that improves through persistent intelligence entities.

Key Revolutionary Features:
1. Persistent Learning Intelligence - KnowledgeMastery, LearningPreference integration
2. Search Intelligence Patterns - SearchQuery patterns inform user interests
3. Relationship-Based Recommendations - Neo4j patterns drive insights
4. Cross-Domain Transfer Learning - Knowledge↔Learning↔Search intelligence flows
5. Adaptive Context Evolution - Context learns and improves over time
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from operator import itemgetter
from typing import Any

from core.models.enums import Domain
from core.models.ku.ku_intelligence import (
    ContentPreference,
    LearningPreference,
    LearningVelocity,
    MasteryLevel,
)
from core.models.ku.ku_intelligence import KuMastery as KnowledgeMastery
from core.models.ku.ku_intelligence import KuRecommendation as KnowledgeRecommendation
from core.models.ku.ku import Ku
from core.services.user import UserContext

# NOTE: SearchIntent and SearchQuery removed - deprecated search_archive dependency
# Search intelligence now uses simple dict structures for flexibility


class IntelligenceSource(str, Enum):
    """Sources of intelligence for UserContext enhancement."""

    KNOWLEDGE_MASTERY = "knowledge_mastery"
    LEARNING_PREFERENCE = "learning_preference"
    SEARCH_PATTERNS = "search_patterns"
    RELATIONSHIP_ANALYSIS = "relationship_analysis"
    CROSS_DOMAIN_TRANSFER = "cross_domain_transfer"


@dataclass
class UserLearningIntelligence:
    """
    Persistent Learning Intelligence for UserContext.

    Aggregates learning intelligence from Knowledge/Learning/Search domains
    to provide adaptive, context-aware user understanding.
    """

    user_uid: str

    # Knowledge Intelligence
    current_masteries: dict[str, KnowledgeMastery] = (field(default_factory=dict),)
    learning_preferences: LearningPreference | None = (None,)
    knowledge_recommendations: list[KnowledgeRecommendation] = field(default_factory=list)

    # Learning Path Intelligence
    active_learning_paths: list[Ku] = (field(default_factory=list),)
    completed_learning_paths: list[str] = (field(default_factory=list),)
    learning_velocity_by_domain: dict[Domain, LearningVelocity] = field(default_factory=dict)

    # Search Intelligence (simplified - no longer using deprecated SearchQuery/SearchIntent)
    recent_search_queries: list[dict[str, Any]] = field(
        default_factory=list
    )  # Simple search history,
    search_interests: dict[str, float] = field(default_factory=dict)  # topic -> interest_score,
    search_intent_patterns: dict[str, int] = field(default_factory=dict)  # intent_name -> count

    # Cross-Domain Intelligence
    knowledge_to_learning_transfers: list[tuple[str, str]] = field(
        default_factory=list
    )  # knowledge_uid -> path_uid,
    learning_to_search_patterns: list[tuple[str, str]] = field(
        default_factory=list
    )  # path_uid -> search_pattern,
    search_to_knowledge_discoveries: list[tuple[str, str]] = field(
        default_factory=list
    )  # search_uid -> knowledge_uid

    # Intelligence Evolution
    intelligence_sources: list[IntelligenceSource] = (field(default_factory=list),)
    last_intelligence_update: datetime = (field(default_factory=datetime.now),)
    intelligence_confidence: float = 0.5  # How confident are we in our intelligence

    def get_dominant_learning_velocity(self) -> LearningVelocity:
        """Get the user's dominant learning velocity across domains."""
        if not self.learning_velocity_by_domain:
            return LearningVelocity.MODERATE

        # Count velocity occurrences
        velocity_counts: dict[LearningVelocity, int] = {}
        for velocity in self.learning_velocity_by_domain.values():
            velocity_counts[velocity] = velocity_counts.get(velocity, 0) + 1

        return max(velocity_counts.keys(), key=velocity_counts.get)

    def get_dominant_content_preferences(self) -> list[ContentPreference]:
        """Get user's dominant content preferences from learning intelligence."""
        if not self.learning_preferences:
            return [ContentPreference.PRACTICAL, ContentPreference.TEXTUAL]

        return self.learning_preferences.preferred_content_types

    def get_learning_efficiency_by_domain(self) -> dict[Domain, float]:
        """Calculate learning efficiency by domain from mastery patterns."""
        efficiency = {}

        for domain in Domain:
            domain_masteries = [
                m
                for m in self.current_masteries.values()
                if self._get_knowledge_domain(m.knowledge_uid) == domain
            ]

            if domain_masteries:
                # Calculate efficiency from mastery strength and learning velocity
                avg_mastery = sum(m.get_mastery_strength() for m in domain_masteries) / len(
                    domain_masteries
                )
                fast_learners = sum(
                    1
                    for m in domain_masteries
                    if m.learning_velocity in [LearningVelocity.FAST, LearningVelocity.VERY_FAST]
                )
                velocity_bonus = fast_learners / len(domain_masteries)

                efficiency[domain] = min(1.0, avg_mastery + (velocity_bonus * 0.2))
            else:
                efficiency[domain] = 0.5  # Default for unknown domains

        return efficiency

    def get_search_driven_interests(self) -> dict[str, float]:
        """Extract learning interests from search patterns."""
        interests: dict[str, float] = {}

        # Analyze recent search queries for interest patterns (using simplified dict structure)
        for query in self.recent_search_queries[-20:]:  # Last 20 searches
            # Extract interest signals from query text
            query_text = query.get("query_text", "") or query.get("text", "")
            if not query_text:
                continue

            query_words = query_text.lower().split()
            for word in query_words:
                if len(word) > 3:  # Filter short words
                    # Simple scoring (deprecated SearchIntent removed)
                    base_score = 0.5

                    # Boost based on any intent hint in the query dict
                    intent = query.get("intent", "unknown")
                    if intent in ["learn", "study", "understand"]:
                        base_score = 1.0
                    elif intent in ["practice", "exercise"]:
                        base_score = 0.8

                    current_score = interests.get(word, 0)
                    interests[word] = min(1.0, current_score + (base_score * 0.1))

        # Sort by interest score
        return dict(sorted(interests.items(), key=itemgetter(1), reverse=True)[:20])

    def get_adaptive_recommendations(self) -> list[dict[str, Any]]:
        """Generate adaptive recommendations using all intelligence sources."""
        recommendations = []

        # Knowledge-driven recommendations
        recommendations.extend(
            [
                {
                    "type": "knowledge",
                    "target_uid": rec.knowledge_uid,
                    "score": rec.recommendation_score,
                    "reason": rec.reasoning,
                    "source": IntelligenceSource.KNOWLEDGE_MASTERY,
                    "urgency": rec.urgency_score,
                }
                for rec in self.knowledge_recommendations
                if rec.is_high_value_recommendation()
            ]
        )

        # Learning path recommendations based on mastery gaps
        recommendations.extend(
            [
                {
                    "type": "learning_progress",
                    "target_uid": path.uid,
                    "score": 0.8,  # High priority for active paths
                    "reason": f"Continue learning path: {path.name}",
                    "source": IntelligenceSource.RELATIONSHIP_ANALYSIS,
                    "urgency": 0.7,
                }
                for path in self.active_learning_paths
            ]
        )

        # Search-driven recommendations
        interests = self.get_search_driven_interests()
        for topic, score in list(interests.items())[:3]:  # Top 3 interests
            if score > 0.6:  # High interest threshold
                recommendations.append(
                    {
                        "type": "search_interest",
                        "target_topic": topic,
                        "score": score,
                        "reason": f"High search interest in {topic}",
                        "source": IntelligenceSource.SEARCH_PATTERNS,
                        "urgency": score * 0.8,
                    }
                )

        # Sort by combined score and urgency
        def _recommendation_priority(r) -> Any:
            return r["score"] * r["urgency"]

        recommendations.sort(key=_recommendation_priority, reverse=True)
        return recommendations[:10]  # Top 10 recommendations

    def update_intelligence(
        self,
        new_masteries: list[KnowledgeMastery] | None = None,
        new_preferences: LearningPreference = None,
        new_searches: list[dict[str, Any]] | None = None,
        new_paths: list[Ku] | None = None,
    ) -> None:
        """Update intelligence with new data from persistent entities."""
        sources_updated = []

        if new_masteries:
            for mastery in new_masteries:
                self.current_masteries[mastery.knowledge_uid] = mastery
            sources_updated.append(IntelligenceSource.KNOWLEDGE_MASTERY)

        if new_preferences:
            self.learning_preferences = new_preferences
            sources_updated.append(IntelligenceSource.LEARNING_PREFERENCE)

        if new_searches:
            # Keep only recent searches (last 50)
            self.recent_search_queries.extend(new_searches)
            self.recent_search_queries = self.recent_search_queries[-50:]

            # Update search interest patterns
            self.search_interests = self.get_search_driven_interests()
            sources_updated.append(IntelligenceSource.SEARCH_PATTERNS)

        if new_paths:
            self.active_learning_paths = new_paths
            sources_updated.append(IntelligenceSource.RELATIONSHIP_ANALYSIS)

        # Update metadata
        self.intelligence_sources.extend(sources_updated)
        self.last_intelligence_update = datetime.now()

        # Increase confidence with more data sources
        unique_sources = set(self.intelligence_sources[-10:])  # Recent sources
        self.intelligence_confidence = min(1.0, len(unique_sources) * 0.2)

    def _get_knowledge_domain(self, knowledge_uid: str) -> Domain:
        """Helper to extract domain from knowledge UID (simplified)."""
        # This would integrate with actual knowledge metadata
        if "tech" in knowledge_uid.lower() or "python" in knowledge_uid.lower():
            return Domain.TECH
        elif "finance" in knowledge_uid.lower():
            return Domain.FINANCE
        else:
            return Domain.KNOWLEDGE  # Default


@dataclass
class EnhancedUserContext(UserContext):
    """
    Revolutionary Enhanced UserContext with persistent intelligence integration.

    Extends the base UserContext with adaptive learning intelligence
    from Knowledge/Learning/Search domains, enabling context that learns
    and improves over time through relationship-based patterns.
    """

    # Intelligence Integration
    learning_intelligence: UserLearningIntelligence | None = None

    # Intelligence-Driven Features
    adaptive_recommendations: list[dict[str, Any]] = (field(default_factory=list),)
    intelligence_confidence: float = 0.5
    cross_domain_insights: dict[str, Any] = field(default_factory=dict)

    # Enhanced Learning Context
    predicted_learning_velocity: LearningVelocity | None = (None,)

    optimal_content_types: list[ContentPreference] = (field(default_factory=list),)
    learning_efficiency_by_domain: dict[Domain, float] = field(default_factory=dict)

    # Enhanced Search Context
    search_interest_profile: dict[str, float] = (field(default_factory=dict),)
    search_intent_preferences: dict[str, float] = field(
        default_factory=dict
    )  # intent_name -> preference_score

    def get_intelligence_driven_recommendations(self) -> list[dict[str, Any]]:
        """Get recommendations driven by persistent intelligence."""
        if not self.learning_intelligence:
            return [self.get_recommended_next_action()]  # Fallback to base implementation

        return self.learning_intelligence.get_adaptive_recommendations()

    def get_personalized_learning_path(self) -> str | None:
        """Get next recommended learning path based on intelligence."""
        if not self.learning_intelligence:
            return None

        # Use mastery patterns and preferences to suggest optimal path
        efficiency_by_domain = self.learning_intelligence.get_learning_efficiency_by_domain()
        best_domain = max(efficiency_by_domain.keys(), key=efficiency_by_domain.get)

        # Find learning paths in the user's most efficient domain
        for path in self.learning_intelligence.active_learning_paths:
            if path.domain == best_domain:
                return path.uid

        return None

    def get_knowledge_readiness_score(self, knowledge_uid: str) -> float:
        """Calculate how ready user is to learn specific knowledge."""
        if not self.learning_intelligence:
            return 0.5

        # Check mastery of prerequisites
        mastery = self.learning_intelligence.current_masteries.get(knowledge_uid)
        if mastery:
            return mastery.get_mastery_strength()

        # Check if prerequisites are met through persistent intelligence
        # This would integrate with knowledge relationships
        return 0.7  # Default readiness for unknown knowledge

    def get_optimal_learning_session(self) -> dict[str, Any]:
        """Get optimal learning session based on intelligence patterns."""
        if not self.learning_intelligence or not self.learning_intelligence.learning_preferences:
            return {
                "duration_minutes": self.available_minutes_daily,
                "content_types": [ContentPreference.PRACTICAL],
                "difficulty": "medium",
            }

        prefs = self.learning_intelligence.learning_preferences
        dominant_velocity = self.learning_intelligence.get_dominant_learning_velocity()

        # Adapt session based on learning velocity and preferences
        session_duration = prefs.preferred_session_duration_minutes
        if dominant_velocity == LearningVelocity.VERY_FAST:
            session_duration = int(session_duration * 1.3)  # Longer sessions for fast learners
        elif dominant_velocity == LearningVelocity.SLOW:
            session_duration = int(session_duration * 0.7)  # Shorter sessions for slower learners

        return {
            "duration_minutes": min(session_duration, self.available_minutes_daily),
            "content_types": prefs.preferred_content_types,
            "difficulty": prefs.preferred_difficulty_progression,
            "use_spaced_repetition": prefs.should_use_spaced_repetition(),
            "optimal_review_intervals": {
                level.value: prefs.get_optimal_review_interval(level) for level in MasteryLevel
            },
        }

    def get_cross_domain_transfer_opportunities(self) -> list[dict[str, Any]]:
        """Identify opportunities to transfer learning across domains."""
        if not self.learning_intelligence:
            return []

        opportunities = []
        masteries = self.learning_intelligence.current_masteries

        # Find mastery patterns that suggest transfer potential
        high_mastery_domains: dict[Domain, list[KnowledgeMastery]] = {}
        for knowledge_uid, mastery in masteries.items():
            domain = self.learning_intelligence._get_knowledge_domain(knowledge_uid)
            if domain not in high_mastery_domains:
                high_mastery_domains[domain] = []

            if mastery.get_mastery_strength() >= 0.7:
                high_mastery_domains[domain].append(mastery)

        # Suggest transfers from high-mastery domains to others
        for strong_domain, strong_masteries in high_mastery_domains.items():
            if len(strong_masteries) >= 3:  # Good mastery in domain
                opportunities.extend(
                    [
                        {
                            "from_domain": strong_domain,
                            "to_domain": weak_domain,
                            "transfer_potential": len(strong_masteries) * 0.2,
                            "suggested_starting_knowledge": f"ku_{weak_domain.value.lower()}_basics",
                            "reasoning": f"Strong mastery in {strong_domain.value} suggests potential in {weak_domain.value}",
                        }
                        for weak_domain in Domain
                        if weak_domain != strong_domain and weak_domain not in high_mastery_domains
                    ]
                )

        return opportunities[:5]  # Top 5 opportunities

    def update_with_intelligence(
        self,
        masteries: list[KnowledgeMastery] | None = None,
        preferences: LearningPreference = None,
        searches: list[dict[str, Any]] | None = None,
        paths: list[Ku] | None = None,
    ) -> None:
        """Update context with new intelligence data."""
        if not self.learning_intelligence:
            self.learning_intelligence = UserLearningIntelligence(user_uid=self.user_uid)

        # Update learning intelligence
        self.learning_intelligence.update_intelligence(
            new_masteries=masteries,
            new_preferences=preferences,
            new_searches=searches,
            new_paths=paths,
        )

        # Update context fields based on intelligence
        if self.learning_intelligence.learning_preferences:
            prefs = self.learning_intelligence.learning_preferences
            self.optimal_content_types = prefs.preferred_content_types
            self.predicted_learning_velocity = (
                self.learning_intelligence.get_dominant_learning_velocity()
            )

        self.learning_efficiency_by_domain = (
            self.learning_intelligence.get_learning_efficiency_by_domain()
        )
        self.search_interest_profile = self.learning_intelligence.get_search_driven_interests()
        self.adaptive_recommendations = self.learning_intelligence.get_adaptive_recommendations()
        self.intelligence_confidence = self.learning_intelligence.intelligence_confidence

        # Generate cross-domain insights
        self.cross_domain_insights = {
            "transfer_opportunities": self.get_cross_domain_transfer_opportunities(),
            "optimal_learning_session": self.get_optimal_learning_session(),
            "personalized_path": self.get_personalized_learning_path(),
        }

        # Update last refresh
        self.last_refresh = datetime.now()
