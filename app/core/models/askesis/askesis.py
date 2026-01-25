"""
Askesis Application Models
==========================

Application layer models for the Askesis service.
These models define the interface for the AI tutor/assistant functionality,
building on top of the search and conversation models.

The Askesis layer provides:
- Request/response models for the service interface
- Integration of search, conversation, and learning
- Pedagogical enhancements for teaching

Phase 1-4 Integration (October 3, 2025):
- Phase 1: APOC query building for user context and learning paths
- Phase 3: GraphContext for personalized learning intelligence
- Phase 4: QueryIntent selection for conversation-specific patterns
"""

__version__ = "2.1"  # Updated for Phase 1-4 integration

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Import askesis-specific enums
from core.models.askesis.askesis_dto import AskesisDTO
from core.models.askesis.askesis_intelligence import (
    ConversationStyle,
    QueryComplexity,
)
from core.models.ku import KuDTO as KnowledgeUnitDTO
from core.models.query import QueryIntent
from core.models.query.graph_traversal import build_graph_context_query
from core.models.shared_enums import GuidanceMode, Intent, Personality, ResponseTone
from core.models.transcription.transcription_dto import (
    SearchResultDTO as CrossDomainSearchResultsSchema,
)
from core.models.transcription.transcription_request import FacetSetRequest as FacetSetSchema
from core.models.transcription.transcription_request import SearchQueryRequest as SearchQuerySchema
from core.models.user import User
from core.models.user.conversation import ConversationSession, PedagogicalContext


def _utcnow() -> Any:
    """Factory function for datetime.now(timezone.utc)"""
    return datetime.now(UTC)


# ============================================================================
# ASKESIS DOMAIN MODEL (Tier 3 - Frozen)
# ============================================================================


@dataclass(frozen=True)
class Askesis:
    """
    Immutable Askesis domain model - AI Learning Assistant instance.

    Represents a personalized AI assistant that learns user preferences,
    domain expertise, and provides intelligent guidance across domains.

    Following three-tier pattern:
    - Tier 1 (External): AskesisCreateRequest/AskesisUpdateRequest (Pydantic)
    - Tier 2 (Transfer): AskesisDTO (mutable dataclass)
    - Tier 3 (Core): Askesis (frozen dataclass) - THIS CLASS
    """

    # Identity
    uid: str
    user_uid: str
    name: str = "Askesis"  # Fixed: string value, not tuple
    version: str = "1.0"

    # Intelligence Metrics
    intelligence_confidence: float = 0.5  # 0.0 to 1.0
    total_conversations: int = 0  # Fixed: int value, not tuple
    total_domain_integrations: int = 0  # Fixed: int value, not tuple
    integration_success_rate: float = 0.0  # Fixed: float value, not tuple
    pattern_recognition_accuracy: float = 0.0  # Fixed: float value, not tuple
    proactive_guidance_success_rate: float = 0.0

    # User Preferences (learned)
    preferred_conversation_style: ConversationStyle = (
        ConversationStyle.DIRECT
    )  # Fixed: enum value, not tuple
    preferred_complexity_level: QueryComplexity = (
        QueryComplexity.MODERATE
    )  # Fixed: enum value, not tuple
    response_preferences: tuple[tuple[str, float], ...] = ()  # Immutable dict as tuple of tuples

    # Domain Knowledge (immutable collections)
    domain_expertise_levels: tuple[
        tuple[str, float], ...
    ] = ()  # Fixed: empty tuple, not nested ((),)
    domain_usage_patterns: tuple[
        tuple[str, float], ...
    ] = ()  # Fixed: empty tuple, not nested ((),)
    cross_domain_synergies: tuple[tuple[str, float], ...] = ()

    # Learning State (immutable lists as tuples)
    active_learning_areas: tuple[str, ...] = ()  # Fixed: empty tuple, not nested ((),)
    knowledge_gaps: tuple[str, ...] = ()  # Fixed: empty tuple, not nested ((),)
    optimization_opportunities: tuple[str, ...] = ()

    # Metadata
    created_at: datetime = field(default_factory=_utcnow)  # Fixed: field, not tuple-wrapped
    last_interaction: datetime | None = None  # type: ignore[assignment]
    last_intelligence_update: datetime | None = None  # type: ignore[assignment]

    # ========================================================================
    # BUSINESS LOGIC METHODS
    # ========================================================================

    def get_expertise_level(self, domain: str) -> float:
        """Get user's expertise level in a specific domain (0.0 to 1.0)."""
        expertise_dict = dict(self.domain_expertise_levels)
        return expertise_dict.get(domain, 0.0)

    def get_domain_synergy(self, domain_pair: str) -> float:
        """Get synergy score between two domains."""
        synergy_dict = dict(self.cross_domain_synergies)
        return synergy_dict.get(domain_pair, 0.0)

    def is_learning_area_active(self, area: str) -> bool:
        """Check if an area is currently being actively learned."""
        return area in self.active_learning_areas

    def has_knowledge_gap(self, gap: str) -> bool:
        """Check if a specific knowledge gap exists."""
        return gap in self.knowledge_gaps

    def get_overall_intelligence_score(self) -> float:
        """Calculate overall AI intelligence score (0.0 to 1.0)."""
        metrics = [
            self.intelligence_confidence,
            self.integration_success_rate,
            self.pattern_recognition_accuracy,
            self.proactive_guidance_success_rate,
        ]
        return sum(metrics) / len(metrics) if metrics else 0.0

    def needs_intelligence_update(self, hours_threshold: int = 24) -> bool:
        """Check if intelligence metrics need updating."""
        if not self.last_intelligence_update:
            return True

        hours_since_update = (
            datetime.now(UTC) - self.last_intelligence_update
        ).total_seconds() / 3600
        return hours_since_update >= hours_threshold

    @classmethod
    def from_dto(cls, dto: "AskesisDTO") -> "Askesis":
        """Convert from mutable DTO to immutable domain model."""

        return cls(
            uid=dto.uid,
            user_uid=dto.user_uid,
            name=dto.name,
            version=dto.version,
            intelligence_confidence=dto.intelligence_confidence,
            total_conversations=dto.total_conversations,
            total_domain_integrations=dto.total_domain_integrations,
            integration_success_rate=dto.integration_success_rate,
            pattern_recognition_accuracy=dto.pattern_recognition_accuracy,
            proactive_guidance_success_rate=dto.proactive_guidance_success_rate,
            preferred_conversation_style=(
                ConversationStyle(dto.preferred_conversation_style)
                if isinstance(dto.preferred_conversation_style, str)
                else dto.preferred_conversation_style
            ),
            preferred_complexity_level=(
                QueryComplexity(dto.preferred_complexity_level)
                if isinstance(dto.preferred_complexity_level, str)
                else dto.preferred_complexity_level
            ),
            response_preferences=tuple(dto.response_preferences.items())
            if dto.response_preferences
            else (),
            domain_expertise_levels=tuple(dto.domain_expertise_levels.items())
            if dto.domain_expertise_levels
            else (),
            domain_usage_patterns=tuple(dto.domain_usage_patterns.items())
            if dto.domain_usage_patterns
            else (),
            cross_domain_synergies=tuple(dto.cross_domain_synergies.items())
            if dto.cross_domain_synergies
            else (),
            active_learning_areas=tuple(dto.active_learning_areas)
            if dto.active_learning_areas
            else (),
            knowledge_gaps=tuple(dto.knowledge_gaps) if dto.knowledge_gaps else (),
            optimization_opportunities=tuple(dto.optimization_opportunities)
            if dto.optimization_opportunities
            else (),
            created_at=dto.created_at or datetime.now(UTC),
            last_interaction=dto.last_interaction,
            last_intelligence_update=dto.last_intelligence_update,
        )

    def to_dto(self) -> "AskesisDTO":
        """Convert from immutable domain model to mutable DTO."""
        return AskesisDTO(
            uid=self.uid,
            user_uid=self.user_uid,
            name=self.name,
            version=self.version,
            intelligence_confidence=self.intelligence_confidence,
            total_conversations=self.total_conversations,
            total_domain_integrations=self.total_domain_integrations,
            integration_success_rate=self.integration_success_rate,
            pattern_recognition_accuracy=self.pattern_recognition_accuracy,
            proactive_guidance_success_rate=self.proactive_guidance_success_rate,
            preferred_conversation_style=self.preferred_conversation_style.value,
            preferred_complexity_level=self.preferred_complexity_level.value,
            response_preferences=dict(self.response_preferences),
            domain_expertise_levels=dict(self.domain_expertise_levels),
            domain_usage_patterns=dict(self.domain_usage_patterns),
            cross_domain_synergies=dict(self.cross_domain_synergies),
            active_learning_areas=list(self.active_learning_areas),
            knowledge_gaps=list(self.knowledge_gaps),
            optimization_opportunities=list(self.optimization_opportunities),
            created_at=self.created_at,
            last_interaction=self.last_interaction,
            last_intelligence_update=self.last_intelligence_update,
        )


# ============================================================================
# ASKESIS REQUEST
# ============================================================================


@dataclass
class AskesisRequest:
    """
    Request to the Askesis service.
    This is the main entry point for conversational interactions.
    """

    # Core message
    message: str
    user: User

    # Session management
    session_id: str | None = (None,)

    create_new_session: bool = False

    # Conversation preferences (can override user defaults)
    personality: Personality | None = (None,)

    tone: ResponseTone | None = (None,)
    guidance_mode: GuidanceMode | None = None

    # Search configuration
    include_search: bool = True

    max_search_results: int = 5
    search_domains: list[str] | None = None

    # Response configuration
    include_examples: bool = True

    include_exercises: bool = False
    include_prerequisites: bool = True

    verbosity: str = "medium"  # low, medium, high

    # Context and metadata
    context: dict[str, Any] = (field(default_factory=dict),)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Request tracking
    request_id: str | None = (None,)

    timestamp: datetime = field(default_factory=_utcnow)

    def get_effective_personality(self) -> Personality:
        """Get personality to use (request override or user preference)"""
        # NOTE: Falls back to default if UserPreferences lacks preferred_personality
        if self.personality:
            return self.personality
        pref: Personality = getattr(
            self.user.preferences, "preferred_personality", Personality.KNOWLEDGEABLE_FRIEND
        )
        return pref

    def get_effective_tone(self) -> ResponseTone:
        """Get tone to use (request override or user preference)"""
        # NOTE: Falls back to default if UserPreferences lacks preferred_tone
        if self.tone:
            return self.tone
        pref_tone: ResponseTone = getattr(
            self.user.preferences, "preferred_tone", ResponseTone.FRIENDLY
        )
        return pref_tone

    def get_effective_guidance(self) -> GuidanceMode:
        """Get guidance mode to use"""
        # NOTE: Falls back to default if UserPreferences lacks preferred_guidance_mode
        if self.guidance_mode:
            return self.guidance_mode
        pref_guidance: GuidanceMode = getattr(
            self.user.preferences, "preferred_guidance_mode", GuidanceMode.BALANCED
        )
        return pref_guidance

    def should_search(self) -> bool:
        """Determine if search should be performed"""
        return self.include_search and len(self.message.strip()) > 0

    # ==========================================================================
    # PHASE 1-4 INTEGRATION: GRAPH INTELLIGENCE
    # ==========================================================================

    def build_user_context_query(self, depth: int = 2) -> str:
        """
        Build pure Cypher query for user's complete context

        Finds user's active learning, tasks, habits, and goals.

        Args:
            depth: Maximum context depth

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=self.user.uid, intent=QueryIntent.EXPLORATORY, depth=depth
        )

    def build_learning_path_query(self, topic_uid: str, depth: int = 3) -> str:
        """
        Build pure Cypher query for learning path recommendation

        Finds appropriate learning paths for topic and user level.

        Args:
            topic_uid: Learning topic UID
            depth: Maximum knowledge graph depth

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=topic_uid, intent=QueryIntent.HIERARCHICAL, depth=depth
        )

    def build_knowledge_search_query(self, search_uid: str, depth: int = 2) -> str:
        """
        Build pure Cypher query for knowledge search

        Finds relevant knowledge based on search context.

        Args:
            search_uid: Search context UID
            depth: Maximum knowledge graph depth

        Returns:
            Pure Cypher query string
        """
        return build_graph_context_query(
            node_uid=search_uid, intent=QueryIntent.RELATIONSHIP, depth=depth
        )

    def get_suggested_query_intent(self) -> QueryIntent:
        """
        Get suggested QueryIntent based on request characteristics.

        Business rules:
        - Question about "how" → EXPLORATORY (discover)
        - Question about "what is" → SPECIFIC (definition)
        - Question about "why" → RELATIONSHIP (understand connections)
        - Request for practice → PRACTICE (find opportunities)
        - Request for prerequisites → PREREQUISITE (understand foundation)
        - Default → EXPLORATORY (learning mode)

        Returns:
            Recommended QueryIntent for this request
        """
        message_lower = self.message.lower()

        if "how to" in message_lower or "how do" in message_lower:
            return QueryIntent.EXPLORATORY

        if "what is" in message_lower or "define" in message_lower:
            return QueryIntent.SPECIFIC

        if "why" in message_lower:
            return QueryIntent.RELATIONSHIP

        if "practice" in message_lower or "exercise" in message_lower:
            return QueryIntent.PRACTICE

        if "prerequisite" in message_lower or "need to know" in message_lower:
            return QueryIntent.PREREQUISITE

        return QueryIntent.EXPLORATORY


# ============================================================================
# NUDGING CONTEXT
# ============================================================================


@dataclass
class NudgeContext:
    """Context for intelligent nudging in learning conversations"""

    nudge_type: str  # encouragement, challenge, break, review, progress, celebration, gentle_push
    priority: int  # 1-10, higher is more urgent
    message: str
    trigger_reason: str


# ============================================================================
# ASKESIS RESPONSE
# ============================================================================


@dataclass
class AskesisResponse:
    """
    Rich response from the Askesis service.
    Contains the message, search results, suggestions, and metadata.
    """

    # Core response
    message: str
    session: ConversationSession

    # Search integration
    search_performed: bool = False

    search_query: SearchQuerySchema | None = (None,)
    search_results: CrossDomainSearchResultsSchema | None = None

    # Extraction and understanding
    extraction: FacetSetSchema | None = (None,)

    detected_intent: Intent | None = (None,)
    confidence: float = 0.8

    # Pedagogical enhancements
    pedagogical_context: PedagogicalContext | None = (None,)

    learning_insights: list[str] = field(default_factory=list)

    # Suggestions and follow-ups
    suggestions: list[str] = (field(default_factory=list),)
    follow_up_questions: list[str] = (field(default_factory=list),)
    recommended_resources: list[str] = (field(default_factory=list),)
    exercises: list[str] = field(default_factory=list)

    # Knowledge graph integration
    related_knowledge_units: list[KnowledgeUnitDTO] = (field(default_factory=list),)
    prerequisite_units: list[str] = field(default_factory=list)  # UIDs of prerequisites,
    next_units: list[str] = field(default_factory=list)  # UIDs of next learning steps

    # Nudging system
    nudges: list[NudgeContext] = field(default_factory=list)

    # Response metadata
    personality_used: Personality = Personality.KNOWLEDGEABLE_FRIEND
    tone_used: ResponseTone = ResponseTone.FRIENDLY
    guidance_used: GuidanceMode = GuidanceMode.BALANCED

    # Performance metrics
    response_time_ms: float = 0.0
    tokens_used: int = 0
    search_time_ms: float = 0.0

    # Context for next turn
    context_for_next: dict[str, Any] = (field(default_factory=dict),)
    awaiting_response: str | None = None  # What we're waiting for user to answer

    # Response tracking
    response_id: str | None = (None,)

    timestamp: datetime = field(default_factory=_utcnow)

    def has_learning_warnings(self) -> bool:
        """Check if there are learning warnings"""
        return bool(self.search_results and getattr(self.search_results, "mastery_warnings", None))

    def get_search_summary(self) -> str | None:
        """Get summary of search results"""
        if not self.search_results:
            return None
        # NOTE: Uses getattr for optional to_summary() on SearchResultDTO
        to_summary = getattr(self.search_results, "to_summary", None)
        if callable(to_summary):
            return to_summary()
        return f"Found {getattr(self.search_results, 'total_results', 0)} results"

    def should_show_prerequisites(self) -> bool:
        """Check if prerequisites should be shown"""
        if not self.search_results:
            return False

        # NOTE: Uses getattr for optional should_user_proceed() on SearchResultDTO
        should_proceed_fn = getattr(self.search_results, "should_user_proceed", None)
        if callable(should_proceed_fn):
            should_proceed, reason = should_proceed_fn()
            return not should_proceed
        return False  # Default: don't show prerequisites

    def to_display_dict(self) -> dict[str, Any]:
        """Convert to dictionary for display/API"""
        # NOTE: Uses getattr for optional primary_results field on SearchResultDTO
        search_count = 0
        if self.search_results:
            primary_results = getattr(self.search_results, "primary_results", [])
            search_count = len(primary_results) if primary_results else 0

        return {
            "message": self.message,
            "session_id": self.session.session_id,
            "suggestions": self.suggestions,
            "follow_up_questions": self.follow_up_questions,
            "confidence": self.confidence,
            "search_performed": self.search_performed,
            "search_results_count": search_count,
            "has_warnings": self.has_learning_warnings(),
            "response_time_ms": self.response_time_ms,
            "related_knowledge_count": len(self.related_knowledge_units),
            "has_prerequisites": len(self.prerequisite_units) > 0,
            "has_next_steps": len(self.next_units) > 0,
        }


# ============================================================================
# ASKESIS CONFIGURATION
# ============================================================================


@dataclass(frozen=True)
class AskesisConfig:
    """
    Configuration for Askesis service behavior.
    """

    # Search configuration
    always_search: bool = False
    search_on_questions: bool = True
    min_query_length_for_search: int = 3

    # Response configuration
    max_response_length: int = 1000
    include_sources: bool = True
    include_confidence: bool = True

    # Pedagogical configuration
    adaptive_difficulty: bool = True
    track_understanding: bool = True
    provide_scaffolding: bool = True
    use_socratic_method: bool = False

    # Conversation configuration
    maintain_context_turns: int = 10
    summarize_after_turns: int = 20

    # Performance configuration
    cache_responses: bool = True
    cache_ttl_seconds: int = 300
    max_search_time_ms: int = 3000

    # Graph configuration
    use_graph_knowledge: bool = True
    max_related_units: int = 5
    include_prerequisites: bool = True
    use_apoc_batch: bool = True  # Use APOC for 10x performance

    # Safety configuration
    filter_inappropriate: bool = True
    require_auth: bool = False
    log_conversations: bool = True


# ============================================================================
# ASKESIS ANALYTICS
# ============================================================================


@dataclass(frozen=True)
class AskesisAnalytics:
    """
    Analytics for Askesis interactions.
    Used for improving the service and understanding usage.
    """

    user_uid: str
    period: str  # "session", "day", "week", "month"

    # Interaction metrics
    total_messages: int = 0

    total_sessions: int = 0
    average_session_length: float = 0.0
    average_messages_per_session: float = 0.0

    # Search metrics
    searches_performed: int = 0

    search_success_rate: float = 0.0
    average_results_per_search: float = 0.0
    domains_searched: dict[str, int] = field(default_factory=dict)

    # Learning metrics
    concepts_explored: int = 0

    prerequisites_identified: int = 0
    learning_paths_suggested: int = 0

    exercises_completed: int = 0

    # Engagement metrics
    follow_ups_asked: int = 0

    suggestions_followed: int = 0
    average_confidence: float = 0.0
    user_satisfaction: float | None = None

    # Intent distribution
    intent_counts: dict[str, int] = field(default_factory=dict)

    # Topic analysis
    top_topics: list[str] = (field(default_factory=list),)
    topic_progression: list[str] = field(default_factory=list)

    def get_engagement_score(self) -> float:
        """Calculate overall engagement score"""
        if self.total_messages == 0:
            return 0.0

        factors = [
            self.average_messages_per_session / 10,  # Normalize to 0-1
            self.search_success_rate,
            self.suggestions_followed / max(self.total_messages, 1),
            self.average_confidence,
        ]

        return sum(factors) / len(factors)

    def get_learning_effectiveness(self) -> float:
        """Calculate learning effectiveness score"""
        if self.concepts_explored == 0:
            return 0.0

        return (
            (self.exercises_completed / max(self.concepts_explored, 1)) * 0.5
            + (self.learning_paths_suggested / max(self.concepts_explored, 1)) * 0.3
            + self.average_confidence * 0.2
        )


# ============================================================================
# ASKESIS ERROR HANDLING
# ============================================================================


@dataclass(frozen=True)
class AskesisError:
    """
    Error response from Askesis service.
    """

    error_type: str  # "search_failed", "extraction_failed", "response_generation_failed"
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    # Recovery suggestions
    suggestions: list[str] = (field(default_factory=list),)
    can_retry: bool = True

    # Error context
    request_id: str | None = (None,)
    timestamp: datetime = field(default_factory=_utcnow)

    def to_user_message(self) -> str:
        """Convert to user-friendly error message"""
        base_message = "I encountered an issue processing your request."

        if self.error_type == "search_failed":
            base_message = "I couldn't search for that information right now."
        elif self.error_type == "extraction_failed":
            base_message = "I had trouble understanding your question."

        if self.suggestions:
            base_message += f" Try: {self.suggestions[0]}"

        return base_message
