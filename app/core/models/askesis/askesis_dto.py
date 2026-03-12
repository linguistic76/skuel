"""
Askesis DTO Models (Tier 2 - Transfer)
=======================================

Mutable data transfer objects for Askesis domain.
Used for data movement between layers and API responses.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.models.enums import GuidanceMode, Priority
from core.models.enums.askesis_enums import QueryComplexity


@dataclass
class ConversationSessionDTO:
    """Mutable DTO for conversation sessions."""

    uid: str
    user_uid: str
    started_at: datetime
    ended_at: datetime | None = None

    # Session characteristics
    primary_intent: str | None = None
    domains_discussed: list[str] = field(default_factory=list)
    complexity_level: str = QueryComplexity.SIMPLE.value
    guidance_mode: str = GuidanceMode.DIRECT.value

    # Session outcomes
    user_satisfaction: int | None = None  # 1-5 scale,
    goals_achieved: bool = False
    integration_success: str | None = None

    # Learning metrics
    new_insights_generated: int = 0
    cross_domain_connections_made: int = 0
    actionable_recommendations: int = 0


@dataclass
class DomainInteractionDTO:
    """Mutable DTO for domain interactions."""

    uid: str
    domain_a: str
    domain_b: str
    interaction_type: str  # "synergy", "conflict", "dependency", "enhancement"
    synergy_score: float  # 0.0 to 1.0
    user_uid: str
    context: str | None = None

    observed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.observed_at is None:
            self.observed_at = datetime.now()


@dataclass
class GuidanceRecommendationDTO:
    """Mutable DTO for guidance recommendations."""

    uid: str
    user_uid: str
    guidance_type: str
    title: str
    description: str

    # Context
    trigger_context: dict[str, Any] = field(default_factory=dict)
    relevant_domains: list[str] = field(default_factory=list)
    confidence_score: float = 0.5  # 0.0 to 1.0

    # Implementation
    actionable_steps: list[str] = field(default_factory=list)
    expected_impact: str = ""
    estimated_effort: str = Priority.MEDIUM.value

    # Lifecycle
    created_at: datetime | None = None
    delivered_at: datetime | None = None
    user_response: str | None = None  # "accepted", "rejected", "deferred",
    effectiveness_rating: int | None = None  # 1-5 scale

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now()


@dataclass
class AskesisDTO:
    """Mutable DTO for Askesis instances."""

    uid: str
    user_uid: str
    name: str = "Askesis"
    version: str = "1.0"

    # Intelligence Metrics
    intelligence_confidence: float = 0.5  # 0.0 to 1.0,
    total_conversations: int = 0
    total_domain_integrations: int = 0

    integration_success_rate: float = 0.0
    pattern_recognition_accuracy: float = 0.0
    proactive_guidance_success_rate: float = 0.0

    # User Preferences (learned)
    preferred_guidance_mode: str = GuidanceMode.DIRECT.value
    preferred_complexity_level: str = QueryComplexity.MODERATE.value
    response_preferences: dict[str, float] = field(default_factory=dict)

    # Domain Knowledge
    domain_expertise_levels: dict[str, float] = field(default_factory=dict)
    domain_usage_patterns: dict[str, float] = field(default_factory=dict)
    cross_domain_synergies: dict[str, float] = field(default_factory=dict)

    # Learning State
    active_learning_areas: list[str] = field(default_factory=list)
    knowledge_gaps: list[str] = field(default_factory=list)
    optimization_opportunities: list[str] = field(default_factory=list)

    # Metadata
    created_at: datetime | None = None

    last_interaction: datetime | None = None

    last_intelligence_update: datetime | None = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now()


@dataclass
class AskesisCreateDTO:
    """DTO for creating new Askesis instances."""

    user_uid: str
    name: str = "Askesis"
    version: str = "1.0"
    preferred_guidance_mode: str = GuidanceMode.DIRECT.value
    preferred_complexity_level: str = QueryComplexity.MODERATE.value


@dataclass
class AskesisUpdateDTO:
    """DTO for updating Askesis instances."""

    uid: str

    # Optional updates
    name: str | None = None

    version: str | None = None
    intelligence_confidence: float | None = None

    preferred_guidance_mode: str | None = None
    preferred_complexity_level: str | None = None

    # Intelligence metrics updates
    total_conversations: int | None = None

    total_domain_integrations: int | None = None
    integration_success_rate: float | None = None

    pattern_recognition_accuracy: float | None = None
    proactive_guidance_success_rate: float | None = None

    # Learning state updates
    active_learning_areas: list[str] | None = None

    knowledge_gaps: list[str] | None = None

    optimization_opportunities: list[str] | None = None

    # Timestamp update
    last_interaction: datetime | None = None

    last_intelligence_update: datetime | None = None


@dataclass
class ConversationAnalyticsDTO:
    """DTO for conversation analytics."""

    user_uid: str
    total_sessions: int = 0
    average_session_duration: float = 0.0  # minutes,
    average_satisfaction: float = 0.0
    most_discussed_domains: list[str] = field(default_factory=list)
    preferred_guidance_mode: str = GuidanceMode.DIRECT.value
    integration_success_rate: float = 0.0
    total_insights_generated: int = 0


@dataclass
class DomainSynergiesAnalyticsDTO:
    """DTO for domain synergies analytics."""

    user_uid: str
    top_synergies: list[dict[str, Any]] = field(
        default_factory=list
    )  # [{domain_pair, synergy_score}],
    conflict_pairs: list[dict[str, Any]] = field(
        default_factory=list
    )  # [{domain_pair, conflict_score}],
    most_integrated_domains: list[str] = field(default_factory=list)
    integration_patterns: dict[str, float] = field(default_factory=dict)


@dataclass
class IntelligenceInsightsDTO:
    """DTO for Askesis intelligence insights."""

    user_uid: str
    overall_intelligence: float = 0.0
    conversation_readiness: bool = False
    needs_more_learning: bool = True
    top_domains: list[str] = field(default_factory=list)
    domain_coverage: int = 0
    average_domain_expertise: float = 0.0
    conversation_experience: float = 0.0
    proactive_guidance_ready: bool = False

    # Recommendations for improvement
    learning_recommendations: list[str] = field(default_factory=list)
    optimization_suggestions: list[str] = field(default_factory=list)


@dataclass
class DomainSuggestionDTO:
    """DTO for domain suggestions based on user query."""

    domain: str
    relevance_score: float
    integration_potential: float
    reasoning: str
    suggested_actions: list[str] = field(default_factory=list)


@dataclass
class CrossDomainInsightDTO:
    """DTO for cross-domain insights."""

    uid: str
    user_uid: str
    insight_type: str  # "pattern", "optimization", "conflict", "synergy"
    title: str
    description: str

    # Domains involved
    primary_domain: str
    secondary_domains: list[str] = field(default_factory=list)

    # Impact assessment
    confidence_score: float = 0.5
    potential_impact: str = Priority.MEDIUM.value
    actionability: float = 0.5  # How actionable this insight is

    # Context
    trigger_data: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)

    # Metadata
    created_at: datetime | None = None
    user_viewed: bool = False
    user_acted_on: bool = False

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now()


@dataclass
class AskesisConfigurationDTO:
    """DTO for Askesis configuration settings."""

    user_uid: str

    # Conversation preferences
    preferred_guidance_mode: str = GuidanceMode.DIRECT.value
    preferred_complexity_level: str = QueryComplexity.MODERATE.value
    proactive_guidance_enabled: bool = True

    auto_domain_suggestions: bool = True

    # Intelligence settings
    learning_mode: str = "adaptive"  # "conservative", "adaptive", "aggressive",
    pattern_recognition_sensitivity: float = 0.5
    cross_domain_analysis_depth: str = "medium"  # "shallow", "medium", "deep"

    # Notification preferences
    guidance_notifications: bool = True

    insight_notifications: bool = True
    pattern_alerts: bool = False

    # Privacy settings
    conversation_logging: bool = True

    pattern_sharing: bool = False  # Share anonymized patterns for research

    # Advanced settings
    experimental_features: bool = False

    debug_mode: bool = False

    # Metadata
    created_at: datetime | None = None

    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()
