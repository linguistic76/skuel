"""
Conversation Models
===================

Models for managing conversations, sessions, and chat interactions.
These models support the Askesis service and any other conversational interfaces.

The conversation layer provides:
- Turn-based conversation tracking
- Session management with context
- Integration points for search results
- Pedagogical guidance tracking
"""

__version__ = "1.0"


from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from core.infrastructure.utils.factory_functions import create_current_timestamp, create_turn_id
from core.models.enums import ConversationState, GuidanceMode, MessageRole, SystemConstants

# NOTE: FacetExtraction removed - was deprecated search_archive dependency
# Extraction field in ConversationTurn is now optional dict for flexibility


def _utc_now() -> Any:
    """Factory function for UTC timestamp."""
    return datetime.now(UTC)


# ============================================================================
# SEARCH TRACE VALUE OBJECT
# ============================================================================


@dataclass(frozen=True, slots=True)
class SearchTrace:
    """
    Cohesive value object for search operation traceability.
    Replaces scattered search fields with a single, extensible structure.
    """

    performed: bool = False
    query: str | None = (None,)
    results_count: int = 0
    summary: str | None = (None,)
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "performed": self.performed,
            "query": self.query,
            "results_count": self.results_count,
            "summary": self.summary,
            "elapsed_ms": self.elapsed_ms,
        }


# ============================================================================
# CONVERSATION TURN
# ============================================================================


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    """
    A single turn in a conversation.
    Immutable record of an exchange between user and assistant.
    """

    # Core message
    role: MessageRole
    content: str
    timestamp: datetime = (field(default_factory=create_current_timestamp),)
    turn_id: str = field(default_factory=create_turn_id)

    # Extraction and understanding (flexible dict for any extraction data)
    extraction: dict[str, Any] | None = None

    # Search integration
    search: SearchTrace = field(default_factory=SearchTrace)

    # Turn metadata
    turn_number: int = 0

    response_time_ms: float = 0.0
    tokens_used: int = 0

    # User feedback (if any)
    user_rating: float | None = None  # 1-5 rating,
    user_feedback: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "search": self.search.to_dict(),
            "turn_number": self.turn_number,
        }

    def get_summary(self, max_length: int = 100) -> str:
        """Get summary of the turn"""
        content_preview = self.content[:max_length]
        if len(self.content) > max_length:
            content_preview += "..."
        return f"[{self.role.value}] {content_preview}"


# ============================================================================
# CONVERSATION SESSION
# ============================================================================


@dataclass(slots=True)
class ConversationSession:
    """
    Active conversation session with full context.
    Mutable to allow efficient updates during conversation.
    """

    # Session identity
    session_id: str
    user_uid: str
    started_at: datetime = (field(default_factory=_utc_now),)
    last_activity: datetime = field(default_factory=_utc_now)

    # Conversation history
    turns: list[ConversationTurn] = (field(default_factory=list),)
    turn_count: int = 0

    # Pedagogical state
    guidance_mode: GuidanceMode = GuidanceMode.BALANCED
    current_topic: str | None = (None,)
    topics_discussed: list[str] = (field(default_factory=list),)
    learning_objectives: list[str] = field(default_factory=list)

    # Conversation state
    state: ConversationState = ConversationState.IDLE
    awaiting_response_to: str | None = None  # What we're waiting for user to answer

    # Context accumulation
    entities_mentioned: list[str] = (field(default_factory=list),)
    concepts_explored: list[str] = (field(default_factory=list),)
    questions_asked: list[str] = field(default_factory=list)

    # Search context
    search_queries_performed: list[str] = (field(default_factory=list),)
    search_results_shown: dict[str, int] = field(default_factory=dict)  # query -> count

    # Session metadata
    session_type: str = "chat"  # chat, learning, practice, exploration,
    session_goals: list[str] = (field(default_factory=list),)
    session_achievements: list[str] = field(default_factory=list)

    # Performance metrics
    total_searches: int = 0
    total_tokens: int = 0
    average_response_time_ms: float = 0.0

    def add_turn(
        self,
        role: MessageRole,
        content: str,
        extraction: dict[str, Any] | None = None,
        search: SearchTrace | None = None,
    ) -> ConversationTurn:
        """Add a turn to the conversation"""
        self.turn_count += 1
        turn = ConversationTurn(
            role=role,
            content=content,
            extraction=extraction,
            search=search or SearchTrace(),
            turn_number=self.turn_count,
        )

        self.turns.append(turn)
        self.last_activity = datetime.now(UTC)

        # Update metrics
        if search and search.performed:
            self.total_searches += 1

        # Keep conversation size manageable
        if len(self.turns) > SystemConstants.MAX_CONVERSATION_TURNS:
            self.turns = self.turns[-SystemConstants.MAX_CONVERSATION_TURNS :]

        return turn

    def get_context_window(
        self, max_turns: int = 10, include_system: bool = False
    ) -> list[ConversationTurn]:
        """Get recent turns for context"""
        turns = self.turns[-max_turns:] if self.turns else []

        if not include_system:
            turns = [t for t in turns if t.role != MessageRole.SYSTEM]

        return turns

    def get_conversation_summary(self) -> str:
        """Generate a summary of the conversation"""
        summary_parts = []

        if self.current_topic:
            summary_parts.append(f"Topic: {self.current_topic}")

        if self.topics_discussed:
            topics = ", ".join(self.topics_discussed[:5])
            summary_parts.append(f"Discussed: {topics}")

        if self.learning_objectives:
            objectives = ", ".join(self.learning_objectives[:3])
            summary_parts.append(f"Learning: {objectives}")

        summary_parts.append(f"Turns: {self.turn_count}")
        summary_parts.append(f"Searches: {self.total_searches}")

        return " | ".join(summary_parts)

    def update_topic(self, topic: str):
        """Update current topic and track it"""
        self.current_topic = topic
        if topic not in self.topics_discussed:
            self.topics_discussed.append(topic)
        # Keep topics list manageable
        if len(self.topics_discussed) > 20:
            self.topics_discussed = self.topics_discussed[-20:]

    def add_entity(self, entity: str):
        """Track an entity mentioned in conversation"""
        if entity not in self.entities_mentioned:
            self.entities_mentioned.append(entity)

    def add_concept(self, concept: str):
        """Track a concept explored in conversation"""
        if concept not in self.concepts_explored:
            self.concepts_explored.append(concept)

    def get_session_duration(self) -> float:
        """Get session duration in minutes"""
        duration = (self.last_activity - self.started_at).total_seconds() / 60
        return round(duration, 1)

    def is_active(self, timeout_minutes: int = SystemConstants.SESSION_TIMEOUT_MINUTES) -> bool:
        """Check if session is still active"""
        time_since_activity = (datetime.now(UTC) - self.last_activity).total_seconds() / 60
        return time_since_activity < timeout_minutes

    def should_summarize(self) -> bool:
        """Check if conversation is long enough to need summarization"""
        return self.turn_count > 20 or self.get_session_duration() > 30

    def to_llm_messages(
        self, max_tokens: int = 4000, include_system: bool = False
    ) -> list[dict[str, str]]:
        """
        Return trimmed [{'role','content'}] respecting token/window limits.

        Starts from most recent turns and walks backwards until max_tokens reached.
        Uses content length as proxy for token count until proper tokenizer available.

        Args:
            max_tokens: Maximum token budget for the message window,
            include_system: Whether to include system messages

        Returns:
            List of message dicts in correct chronological order for LLM
        """
        turns = self.get_context_window(
            max_turns=SystemConstants.MAX_CONVERSATION_TURNS, include_system=include_system
        )

        msgs: list[dict[str, str]] = []
        running_tokens = 0

        # Walk backwards from most recent
        for turn in reversed(turns):
            # Use content length as token proxy (rough estimate: ~4 chars per token)
            estimated_tokens = len(turn.content) // 4

            if running_tokens + estimated_tokens > max_tokens:
                break

            msgs.append({"role": turn.role.value, "content": turn.content})
            running_tokens += estimated_tokens

        # Return in chronological order (reverse the reversed list)
        return list(reversed(msgs))

    def get_analytics(self) -> dict[str, Any]:
        """Get compact analytics for dashboards"""
        return {
            "turns": self.turn_count,
            "searches": self.total_searches,
            "duration_min": self.get_session_duration(),
            "topics": self.topics_discussed[-5:] if self.topics_discussed else [],
            "session_id": self.session_id,
            "user_uid": self.user_uid,
            "is_active": self.is_active(),
        }


# ============================================================================
# CONVERSATION CONTEXT (For Service State)
# ============================================================================


@dataclass(slots=True)
class ConversationContext:
    """
    Extended conversation context for service-level state management.
    Includes session management and cross-session tracking.
    """

    # Active sessions
    active_sessions: dict[str, ConversationSession] = field(default_factory=dict)

    # User's conversation history (across sessions)
    user_sessions: dict[str, list[str]] = field(default_factory=dict)  # user_uid -> session_ids

    # Conversation memory (for continuity)
    user_memory: dict[str, dict[str, Any]] = field(default_factory=dict)  # user_uid -> memory

    # Global conversation metrics
    total_sessions_created: int = 0

    total_turns_processed: int = 0

    def get_or_create_session(self, session_id: str, user_uid: str) -> ConversationSession:
        """Get existing session or create new one"""
        if session_id not in self.active_sessions:
            session = ConversationSession(session_id=session_id, user_uid=user_uid)
            self.active_sessions[session_id] = session
            self.total_sessions_created += 1

            # Track session for user
            if user_uid not in self.user_sessions:
                self.user_sessions[user_uid] = []
            self.user_sessions[user_uid].append(session_id)

        return self.active_sessions[session_id]

    def get_user_context(self, user_uid: str) -> dict[str, Any]:
        """Get accumulated context for a user across sessions"""
        # Type-safe lists for context aggregation
        recent_topics: list[str] = []
        frequent_concepts: list[str] = []

        # Aggregate from recent sessions
        recent_sessions = self.user_sessions.get(user_uid, [])[-5:]
        for session_id in recent_sessions:
            if session_id in self.active_sessions:
                session = self.active_sessions[session_id]
                recent_topics.extend(session.topics_discussed)
                frequent_concepts.extend(session.concepts_explored)

        return {
            "session_count": len(self.user_sessions.get(user_uid, [])),
            "memory": self.user_memory.get(user_uid, {}),
            "recent_topics": recent_topics,
            "frequent_concepts": frequent_concepts,
        }

    def update_user_memory(self, user_uid: str, key: str, value: Any):
        """Update user's conversation memory"""
        if user_uid not in self.user_memory:
            self.user_memory[user_uid] = {}
        self.user_memory[user_uid][key] = value

    def cleanup_inactive_sessions(
        self, timeout_minutes: int = SystemConstants.SESSION_TIMEOUT_MINUTES
    ):
        """Remove inactive sessions to manage memory"""
        inactive_sessions = []
        for session_id, session in self.active_sessions.items():
            if not session.is_active(timeout_minutes):
                inactive_sessions.append(session_id)

        for session_id in inactive_sessions:
            del self.active_sessions[session_id]

        return len(inactive_sessions)

    def get_active_session_count(self) -> int:
        """Get count of active sessions"""
        return len(self.active_sessions)

    def get_user_session_count(self, user_uid: str) -> int:
        """Get count of sessions for a user"""
        return len(self.user_sessions.get(user_uid, []))


# ============================================================================
# PEDAGOGICAL CONTEXT
# ============================================================================


@dataclass(frozen=True, slots=True)
class PedagogicalContext:
    """
    Context for pedagogical decisions in conversations.
    Helps determine how to guide the learning conversation.
    """

    # Current learning state
    current_understanding_level: float = 0.5  # 0.0 to 1.0,
    confidence_in_topic: float = 0.5
    engagement_level: float = 0.7

    # Learning patterns observed
    prefers_examples: bool = True
    prefers_theory: bool = False
    prefers_practice: bool = True
    asks_many_questions: bool = False

    # Recommended approach
    recommended_guidance: GuidanceMode = GuidanceMode.BALANCED
    recommended_difficulty: str = "intermediate"
    recommended_pace: str = "moderate"  # slow, moderate, fast

    # Intervention triggers
    needs_encouragement: bool = False
    needs_clarification: bool = False
    needs_challenge: bool = False
    needs_break: bool = False

    # Teaching strategies
    use_analogies: bool = True
    use_scaffolding: bool = True
    use_socratic_method: bool = False
    provide_hints: bool = True

    def get_teaching_approach(self) -> str:
        """Get recommended teaching approach as string"""
        if self.confidence_in_topic < 0.3:
            return "Start with basics and build confidence"
        elif self.engagement_level < 0.5:
            return "Use engaging examples and interactive elements"
        elif self.current_understanding_level > 0.8:
            return "Challenge with advanced concepts"
        else:
            return "Continue with guided exploration"
