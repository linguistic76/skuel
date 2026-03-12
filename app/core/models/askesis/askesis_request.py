"""
Askesis Request Models (Tier 1 - External)
===========================================

Pydantic models for API validation and external interfaces.
Handles input validation and serialization for Askesis domain.

Uses shared validators from validation_rules.py for DRY compliance.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.models.enums import GuidanceMode, Priority
from core.models.enums.askesis_enums import (
    IntegrationSuccess,
    QueryComplexity,
)
from core.models.validation_rules import validate_required_string


class AskesisCreateRequest(BaseModel):
    """Request model for creating Askesis instances."""

    name: str = Field("Askesis", min_length=1, max_length=100, description="Askesis instance name")
    version: str = Field("1.0", description="Version identifier")
    preferred_guidance_mode: GuidanceMode = Field(
        GuidanceMode.DIRECT, description="Preferred guidance mode"
    )
    preferred_complexity_level: QueryComplexity = Field(
        QueryComplexity.MODERATE, description="Preferred query complexity level"
    )

    model_config = ConfigDict(
        use_enum_values=True
        # Pydantic V2 serializes enums automatically
    )


class AskesisUpdateRequest(BaseModel):
    """Request model for updating Askesis instances."""

    name: str | None = Field(None, min_length=1, max_length=100)
    version: str | None = None
    preferred_guidance_mode: GuidanceMode | None = None
    preferred_complexity_level: QueryComplexity | None = None

    # Intelligence settings
    proactive_guidance_enabled: bool | None = None
    auto_domain_suggestions: bool | None = None
    learning_mode: str | None = Field(None, pattern="^(conservative|adaptive|aggressive)$")

    model_config = ConfigDict(use_enum_values=True)


class ConversationSessionCreateRequest(BaseModel):
    """Request model for starting conversation sessions."""

    primary_intent: str | None = Field(
        None, max_length=200, description="Main intent of conversation"
    )
    expected_complexity: QueryComplexity = Field(
        QueryComplexity.MODERATE, description="Expected complexity level"
    )
    preferred_guidance_mode: GuidanceMode = Field(
        GuidanceMode.DIRECT, description="Preferred guidance mode"
    )
    context: dict[str, Any] | None = Field(None, description="Additional context")

    model_config = ConfigDict(use_enum_values=True)


class ConversationSessionUpdateRequest(BaseModel):
    """Request model for updating conversation sessions."""

    session_uid: str = Field(..., description="Session UID")
    action: str = Field(..., description="Update action")

    # Session outcomes
    user_satisfaction: int | None = Field(None, ge=1, le=5, description="Satisfaction rating")
    goals_achieved: bool | None = None
    integration_success: IntegrationSuccess | None = None

    # Learning metrics
    new_insights_generated: int | None = Field(None, ge=0)
    cross_domain_connections_made: int | None = Field(None, ge=0)
    actionable_recommendations: int | None = Field(None, ge=0)

    # Additional data
    domains_discussed: list[str] | None = None
    notes: str | None = Field(None, max_length=1000)

    @field_validator("action")
    @classmethod
    def validate_action(cls, v) -> Any:
        valid_actions = ["add_domain", "update_metrics", "end_session", "rate_session"]
        if v not in valid_actions:
            raise ValueError(f"Action must be one of: {valid_actions}")
        return v

    model_config = ConfigDict(use_enum_values=True)


class DomainInteractionRequest(BaseModel):
    """Request model for recording domain interactions."""

    domain_a: str = Field(..., description="First domain")
    domain_b: str = Field(..., description="Second domain")
    interaction_type: str = Field(..., description="Type of interaction")
    synergy_score: float = Field(..., ge=0.0, le=1.0, description="Synergy score")
    context: str | None = Field(None, max_length=500, description="Interaction context")

    @field_validator("interaction_type")
    @classmethod
    def validate_interaction_type(cls, v) -> Any:
        valid_types = ["synergy", "conflict", "dependency", "enhancement", "neutral"]
        if v not in valid_types:
            raise ValueError(f"Interaction type must be one of: {valid_types}")
        return v

    @field_validator("domain_a", "domain_b")
    @classmethod
    def validate_domains(cls, v) -> Any:
        valid_domains = [
            "knowledge",
            "learning",
            "tasks",
            "events",
            "habits",
            "goals",
            "finance",
            "journal",
            "transcription",
            "choice",
            "search",
            "principle",
            "user",
            "askesis",
        ]
        if v not in valid_domains:
            raise ValueError(f"Domain must be one of: {valid_domains}")
        return v


class GuidanceRecommendationCreateRequest(BaseModel):
    """Request model for creating guidance recommendations."""

    guidance_type: str = Field(..., description="Type of guidance")
    title: str = Field(..., min_length=1, max_length=200, description="Guidance title")
    description: str = Field(..., min_length=1, max_length=1000, description="Detailed description")

    # Context
    trigger_context: dict[str, Any] = Field(
        default_factory=dict, description="Context that triggered guidance"
    )
    relevant_domains: list[str] = Field(default_factory=list, description="Relevant domains")
    confidence_score: float = Field(0.5, ge=0.0, le=1.0, description="Confidence in guidance")

    # Implementation details
    actionable_steps: list[str] = Field(default_factory=list, description="Specific action steps")
    expected_impact: str = Field("", max_length=500, description="Expected impact description")
    estimated_effort: Priority = Field(Priority.MEDIUM, description="Estimated effort level")

    @field_validator("relevant_domains")
    @classmethod
    def validate_relevant_domains(cls, v) -> Any:
        valid_domains = [
            "knowledge",
            "learning",
            "tasks",
            "events",
            "habits",
            "goals",
            "finance",
            "journal",
            "transcription",
            "choice",
            "search",
            "principle",
            "user",
            "askesis",
        ]
        for domain in v:
            if domain not in valid_domains:
                raise ValueError(f"Domain {domain} is not valid")
        return v

    model_config = ConfigDict(use_enum_values=True)


class GuidanceRecommendationResponseRequest(BaseModel):
    """Request model for responding to guidance recommendations."""

    recommendation_uid: str = Field(..., description="Recommendation UID")
    user_response: str = Field(..., description="User response")
    effectiveness_rating: int | None = Field(None, ge=1, le=5, description="Effectiveness rating")
    feedback: str | None = Field(None, max_length=1000, description="Additional feedback")

    @field_validator("user_response")
    @classmethod
    def validate_user_response(cls, v) -> Any:
        valid_responses = ["accepted", "rejected", "deferred", "modified"]
        if v not in valid_responses:
            raise ValueError(f"User response must be one of: {valid_responses}")
        return v


class DomainSuggestionRequest(BaseModel):
    """Request model for getting domain suggestions."""

    query_text: str = Field(..., min_length=1, max_length=500, description="User query")
    current_context: dict[str, Any] | None = Field(None, description="Current user context")
    active_domains: list[str] | None = Field(None, description="Currently active domains")
    max_suggestions: int = Field(5, ge=1, le=10, description="Maximum number of suggestions")

    # Shared validators
    _validate_query_text = validate_required_string("query_text")


class IntelligenceUpdateRequest(BaseModel):
    """Request model for updating Askesis intelligence."""

    update_type: str = Field(..., description="Type of intelligence update")

    # Conversation metrics
    conversation_feedback: dict[str, Any] | None = None
    domain_usage_data: dict[str, float] | None = None
    interaction_success_data: dict[str, Any] | None = None

    # Learning data
    pattern_recognition_results: dict[str, float] | None = None
    cross_domain_insights: list[dict[str, Any]] | None = None
    user_preference_updates: dict[str, Any] | None = None

    @field_validator("update_type")
    @classmethod
    def validate_update_type(cls, v) -> Any:
        valid_types = [
            "conversation_feedback",
            "domain_usage",
            "pattern_recognition",
            "user_preferences",
            "integration_success",
            "comprehensive_update",
        ]
        if v not in valid_types:
            raise ValueError(f"Update type must be one of: {valid_types}")
        return v


class AskesisAnalyticsRequest(BaseModel):
    """Request model for Askesis analytics."""

    analytics_type: str = Field("overview", description="Type of analytics")
    date_range: dict[str, str] | None = Field(None, description="Date range filter")
    include_patterns: bool = Field(True, description="Include pattern analysis")
    include_predictions: bool = Field(True, description="Include predictions")
    detail_level: str = Field("medium", description="Level of detail")

    @field_validator("analytics_type")
    @classmethod
    def validate_analytics_type(cls, v) -> Any:
        valid_types = [
            "overview",
            "conversation_patterns",
            "domain_synergies",
            "intelligence_insights",
            "learning_progress",
            "effectiveness",
        ]
        if v not in valid_types:
            raise ValueError(f"Analytics type must be one of: {valid_types}")
        return v

    @field_validator("detail_level")
    @classmethod
    def validate_detail_level(cls, v) -> Any:
        valid_levels = ["basic", "medium", "detailed", "comprehensive"]
        if v not in valid_levels:
            raise ValueError(f"Detail level must be one of: {valid_levels}")
        return v


# Response Models


class AskesisResponse(BaseModel):
    """Response model for Askesis data."""

    uid: str
    user_uid: str
    name: str
    version: str

    # Intelligence metrics
    intelligence_confidence: float
    total_conversations: int
    total_domain_integrations: int
    integration_success_rate: float
    pattern_recognition_accuracy: float
    proactive_guidance_success_rate: float

    # User preferences
    preferred_guidance_mode: str
    preferred_complexity_level: str

    # Learning state
    active_learning_areas: list[str]
    knowledge_gaps: list[str]
    optimization_opportunities: list[str]

    # Domain knowledge
    domain_expertise_levels: dict[str, float]
    top_domains: list[str]

    # Metadata
    created_at: datetime
    last_interaction: datetime | None
    last_intelligence_update: datetime | None

    # Computed fields
    is_conversation_ready: bool
    needs_learning: bool
    learning_progress_score: float

    model_config = ConfigDict(
        from_attributes=True
        # Pydantic V2 serializes datetimes automatically
    )


class ConversationSessionResponse(BaseModel):
    """Response model for conversation sessions."""

    uid: str
    user_uid: str
    started_at: datetime
    ended_at: datetime | None

    # Session characteristics
    primary_intent: str | None
    domains_discussed: list[str]
    complexity_level: str
    guidance_mode: str

    # Session outcomes
    user_satisfaction: int | None
    goals_achieved: bool
    integration_success: str | None

    # Learning metrics
    new_insights_generated: int
    cross_domain_connections_made: int
    actionable_recommendations: int

    # Computed fields
    duration_minutes: float | None
    is_active: bool

    model_config = ConfigDict(
        from_attributes=True
        # Pydantic V2 serializes datetimes automatically
    )


class GuidanceRecommendationResponse(BaseModel):
    """Response model for guidance recommendations."""

    uid: str
    user_uid: str
    guidance_type: str
    title: str
    description: str

    # Context
    relevant_domains: list[str]
    confidence_score: float

    # Implementation
    actionable_steps: list[str]
    expected_impact: str
    estimated_effort: str

    # Lifecycle
    created_at: datetime
    delivered_at: datetime | None
    user_response: str | None
    effectiveness_rating: int | None

    # Computed fields
    is_delivered: bool
    is_responded_to: bool
    was_effective: bool

    model_config = ConfigDict(
        from_attributes=True
        # Pydantic V2 serializes datetimes automatically
    )


class DomainSuggestionResponse(BaseModel):
    """Response model for domain suggestions."""

    domain: str
    relevance_score: float
    integration_potential: float
    reasoning: str
    suggested_actions: list[str]
    confidence_score: float

    model_config = ConfigDict(from_attributes=True)


class IntelligenceInsightsResponse(BaseModel):
    """Response model for intelligence insights."""

    user_uid: str
    overall_intelligence: float
    conversation_readiness: bool
    needs_more_learning: bool

    # Domain insights
    top_domains: list[str]
    domain_coverage: int
    average_domain_expertise: float

    # Progress insights
    conversation_experience: float
    proactive_guidance_ready: bool
    learning_progress_score: float

    # Recommendations
    learning_recommendations: list[str]
    optimization_suggestions: list[str]

    # Analytics
    conversation_patterns: dict[str, Any]
    domain_synergies: dict[str, float]

    model_config = ConfigDict(from_attributes=True)
