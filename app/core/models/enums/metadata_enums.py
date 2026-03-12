"""
Metadata Enums - Relationships, UI, Search, and System Configuration
=====================================================================

Enums for relationships, user interaction, search, caching, visibility,
and system-wide configuration.
"""

from enum import StrEnum

# ============================================================================
# USER & INTERACTION
# ============================================================================


class ResponseTone(StrEnum):
    """Tone for system responses"""

    NEUTRAL = "neutral"
    FRIENDLY = "friendly"
    PROFESSIONAL = "professional"
    ENCOURAGING = "encouraging"
    MOTIVATIONAL = "motivational"
    ANALYTICAL = "analytical"
    CONCISE = "concise"
    DETAILED = "detailed"


class Personality(StrEnum):
    """
    AI personality modes and user personality types.
    Shapes the overall character of responses and interactions.
    """

    # AI personality modes
    KNOWLEDGEABLE_FRIEND = "knowledgeable_friend"
    TUTOR = "tutor"
    COACH = "coach"
    PROFESSIONAL = "professional"
    CASUAL = "casual"
    SOCRATIC = "socratic"  # Asks guiding questions

    # User personality types for personalization
    ACHIEVER = "achiever"
    EXPLORER = "explorer"
    SOCIALIZER = "socializer"
    ANALYTICAL = "analytical"
    CREATIVE = "creative"
    METHODICAL = "methodical"


class GuidanceMode(StrEnum):
    """How Askesis responds — default register is DIRECT.

    DIRECT: Concise, informational responses using curriculum context.
    SOCRATIC: Probes understanding via questions, does not give answers.
    EXPLORATORY: Guided discovery through scaffolding and connections.
    ENCOURAGING: Warm, practice-focused, connects understanding to activity.
    """

    DIRECT = "direct"
    SOCRATIC = "socratic"
    EXPLORATORY = "exploratory"
    ENCOURAGING = "encouraging"


class LearningModality(StrEnum):
    """Preferred learning modalities"""

    VISUAL = "visual"
    AUDITORY = "auditory"
    READING = "reading"
    KINESTHETIC = "kinesthetic"
    INTERACTIVE = "interactive"
    VIDEO = "video"
    PRACTICE = "practice"


# ============================================================================
# RELATIONSHIPS & DEPENDENCIES
# ============================================================================


class RelationshipType(StrEnum):
    """
    Universal relationship types that can exist between any entities.

    Covers task dependencies, learning prerequisites, habit chains, and all
    cross-entity relationships in the system.
    """

    # Dependency relationships
    BLOCKS = "blocks"  # A blocks B (B can't start until A completes)
    REQUIRES = "requires"  # A requires B (A needs B to be available)
    ENABLES = "enables"  # A enables B (B becomes possible after A)

    # Hierarchical relationships
    PARENT_OF = "parent_of"  # A is parent of B
    CHILD_OF = "child_of"  # A is child of B
    SUBTASK_OF = "subtask_of"  # A is subtask of B (specific parent type)

    # Association relationships
    RELATED_TO = "related_to"  # General relation
    PART_OF = "part_of"  # A is part of B (e.g., event part of project)
    SUPPORTS = "supports"  # A supports B (non-blocking helper)
    SUGGESTS = "suggests"  # A suggests B
    CONFLICTS_WITH = "conflicts_with"  # A conflicts with B (scheduling conflict)
    DUPLICATES = "duplicates"  # A duplicates B
    CONTINUES = "continues"  # A continues B

    # Temporal relationships
    BEFORE = "before"  # A should happen before B
    AFTER = "after"  # A should happen after B
    DURING = "during"  # A happens during B
    OVERLAPS = "overlaps"  # A overlaps with B

    # Learning relationships
    PREREQUISITE_FOR = "prerequisite_for"  # A is prerequisite for B
    BUILDS_ON = "builds_on"  # A builds on knowledge from B
    PRACTICES = "practices"  # A practices skill from B
    APPLIES_TO = "applies_to"  # Knowledge applies to domain/situation
    USED_BY = "used_by"  # Knowledge/skill used by entity/person

    # Habit relationships
    TRIGGERS = "triggers"  # A triggers B (habit chain)
    REINFORCES = "reinforces"  # A reinforces B
    REPLACES = "replaces"  # A replaces B (habit substitution)

    # User-Knowledge relationships (for personalized learning graph)
    MASTERED = "mastered"  # User has mastered knowledge unit
    IN_PROGRESS = "in_progress"  # User is currently learning knowledge unit
    NEEDS_REVIEW = "needs_review"  # User needs to review knowledge unit
    STRUGGLING_WITH = "struggling_with"  # User is having difficulty

    # User-Task relationships
    ASSIGNED_TO = "assigned_to"  # Task assigned to user
    OWNS = "owns"  # User owns/created task
    COMPLETED_TASK = "completed_task"  # User completed task
    DELEGATED = "delegated"  # User delegated task

    # Task-Domain relationships
    REQUIRES_KNOWLEDGE = "requires_knowledge"  # Task requires knowledge unit
    CONTRIBUTES_TO_GOAL = "contributes_to_goal"  # Task contributes to goal
    DEPENDS_ON = "depends_on"  # Task depends on another task
    BLOCKED_BY = "blocked_by"  # Task blocked by another task

    # User-Event relationships
    ATTENDING = "attending"  # User attending event
    ORGANIZING = "organizing"  # User organizing event
    INVITED_TO = "invited_to"  # User invited to event
    PRESENTS_AT = "presents_at"  # User presenting at event

    # Event-Domain relationships
    COVERS_KNOWLEDGE = "covers_knowledge"  # Event covers knowledge topic
    ADVANCES_GOAL = "advances_goal"  # Event advances goal

    # Goal-Domain relationships
    HAS_GOAL = "has_goal"  # User has/owns goal
    SUPPORTED_BY = "supported_by"  # Goal supported by habit (with weight)
    GUIDED_BY = "guided_by"  # Goal guided by principle/value

    # Habit-Domain relationships
    HAS_HABIT = "has_habit"  # User has/practices habit
    DEVELOPS_SKILL = "develops_skill"  # Habit develops knowledge/skill
    EMBODIES = "embodies"  # Habit embodies principle/value

    # Principle-Domain relationships
    HOLDS_PRINCIPLE = "holds_principle"  # User holds/believes principle
    BASED_ON_KNOWLEDGE = "based_on_knowledge"  # Principle based on knowledge

    # Choice-Domain relationships
    SUPPORTS_GOAL = "supports_goal"  # Choice supports/undermines goal
    REINFORCES_HABIT = "reinforces_habit"  # Choice reinforces/weakens habit
    ALIGNS_WITH_PRINCIPLE = "aligns_with_principle"  # Choice aligns with principle
    INFORMED_BY_KNOWLEDGE = "informed_by_knowledge"  # Choice informed by knowledge

    # General cross-domain relationships
    INTERESTED_IN = "interested_in"  # User expressed interest
    BOOKMARKED = "bookmarked"  # User bookmarked knowledge unit
    COMPLETED = "completed"  # User completed learning path/course
    ENROLLED = "enrolled"  # User enrolled in learning path/course


# ============================================================================
# SEARCH & SYSTEM
# ============================================================================


class Intent(StrEnum):
    """User intent detected from queries and conversations."""

    # Core intents
    GENERAL = "general"
    LEARNING = "learning"
    SEARCH = "search"

    # Action intents
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"

    # Exploration intents
    EXPLORE = "explore"
    DISCOVER = "discover"
    PRACTICE = "practice"

    # Management intents
    TASK_MANAGEMENT = "task_management"
    HABIT_TRACKING = "habit_tracking"
    FINANCIAL = "financial"

    # Support intents
    HELP = "help"
    CLARIFY = "clarify"
    REVIEW = "review"
    REFLECT = "reflect"

    # Analysis intents
    EXPLAIN = "explain"
    SUMMARIZE = "summarize"
    ANALYZE = "analyze"
    SCHEDULE = "schedule"
    TRACK = "track"
    CONNECT = "connect"
    ORGANIZE = "organize"


class ExtractionMethod(StrEnum):
    """Method used for facet/intent extraction"""

    PATTERN = "pattern"  # Rule-based patterns
    EMBEDDING = "embedding"  # Semantic similarity
    LLM = "llm"  # Language model
    HYBRID = "hybrid"  # Combination of methods


class SearchScope(StrEnum):
    """Scope of search operations"""

    LOCAL = "local"  # Current domain only
    CROSS_DOMAIN = "cross_domain"  # Across all domains
    RELATED = "related"  # Include related items
    DEEP = "deep"  # Include prerequisites and dependencies


class FacetType(StrEnum):
    """Types of facets for filtering and categorization"""

    DOMAIN = "domain"
    TAG = "tag"
    CATEGORY = "category"
    STATUS = "status"
    PRIORITY = "priority"
    DATE_RANGE = "date_range"
    AUTHOR = "author"
    TYPE = "type"
    DIFFICULTY = "difficulty"
    MASTERY = "mastery"
    AGE = "age"
    LEVEL = "level"


class MessageRole(StrEnum):
    """Role of message sender"""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ConversationState(StrEnum):
    """State of a conversation session"""

    IDLE = "idle"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    EXTRACTING_FACETS = "extracting_facets"
    SEARCHING = "searching"
    GENERATING_RESPONSE = "generating_response"
    RESPONDING = "responding"
    ERROR = "error"


# ============================================================================
# ERROR & CACHE
# ============================================================================


class ErrorSeverity(StrEnum):
    """Severity of errors"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CacheStrategy(StrEnum):
    """Caching strategies"""

    NO_CACHE = "no_cache"
    SHORT = "short"  # 5 minutes
    MEDIUM = "medium"  # 1 hour
    LONG = "long"  # 24 hours
    PERSISTENT = "persistent"  # Until invalidated


# ============================================================================
# VISIBILITY
# ============================================================================


class Visibility(StrEnum):
    """Visibility settings for any entity."""

    PRIVATE = "private"  # Only visible to owner
    SHARED = "shared"  # Visible to specific users
    TEAM = "team"  # Visible to team members
    PUBLIC = "public"  # Visible to everyone

    def is_public(self) -> bool:
        """Check if publicly visible"""
        return self == Visibility.PUBLIC

    def is_restricted(self) -> bool:
        """Check if access is restricted"""
        return self in {Visibility.PRIVATE, Visibility.SHARED, Visibility.TEAM}


# ============================================================================
# UI PRESENTATION ENUMS
# ============================================================================


class TrendDirection(StrEnum):
    """Direction of trends in analytics and dashboards"""

    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"

    def get_color(self) -> str:
        """Get Tailwind CSS color class for trend direction"""
        colors = {
            TrendDirection.INCREASING: "text-green-600",
            TrendDirection.DECREASING: "text-red-600",
            TrendDirection.STABLE: "text-gray-600",
        }
        return colors.get(self, "text-gray-600")

    def get_icon(self) -> str:
        """Get emoji icon for trend direction"""
        icons = {
            TrendDirection.INCREASING: "📈",
            TrendDirection.DECREASING: "📉",
            TrendDirection.STABLE: "↔️",
        }
        return icons.get(self, "→")


class HealthStatus(StrEnum):
    """System health status levels"""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"

    def get_color(self) -> str:
        """Get color for health status (Tailwind base color name)"""
        colors = {
            HealthStatus.HEALTHY: "green",
            HealthStatus.WARNING: "yellow",
            HealthStatus.CRITICAL: "red",
            HealthStatus.UNKNOWN: "gray",
        }
        return colors.get(self, "gray")

    def get_icon(self) -> str:
        """Get emoji icon for health status"""
        icons = {
            HealthStatus.HEALTHY: "✅",
            HealthStatus.WARNING: "⚠️",
            HealthStatus.CRITICAL: "🔴",
            HealthStatus.UNKNOWN: "❔",
        }
        return icons.get(self, "❔")


class SeverityLevel(StrEnum):
    """Severity levels for issues, gaps, and alerts"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    def get_color(self) -> str:
        """Get color for severity level (Tailwind base color name)"""
        colors = {
            SeverityLevel.HIGH: "red",
            SeverityLevel.MEDIUM: "yellow",
            SeverityLevel.LOW: "blue",
        }
        return colors.get(self, "gray")

    def to_numeric(self) -> int:
        """Convert to numeric value for sorting (1-3, higher is more severe)"""
        mapping = {SeverityLevel.LOW: 1, SeverityLevel.MEDIUM: 2, SeverityLevel.HIGH: 3}
        return mapping.get(self, 2)


class BridgeType(StrEnum):
    """Types of knowledge bridges for cross-domain learning"""

    DIRECT = "direct"  # Direct transfer of concepts
    ANALOGICAL = "analogical"  # Learning by analogy
    METHODOLOGICAL = "methodological"  # Transfer of methods/approaches
    SKILL_TRANSFER = "skill_transfer"  # Transfer of skills

    def get_color(self) -> str:
        """Get color for bridge type (Tailwind base color name)"""
        colors = {
            BridgeType.DIRECT: "green",
            BridgeType.ANALOGICAL: "blue",
            BridgeType.METHODOLOGICAL: "purple",
            BridgeType.SKILL_TRANSFER: "orange",
        }
        return colors.get(self, "gray")


# ============================================================================
# SYSTEM CONFIGURATION CONSTANTS
# ============================================================================


class SystemConstants:
    """System-wide configuration constants and thresholds"""

    # Mastery thresholds
    MASTERY_THRESHOLD = 0.8  # 80% for concept to be considered mastered
    REVIEW_THRESHOLD = 0.6  # Below 60% needs review
    MIN_QUALITY_THRESHOLD = 0.7  # 70% minimum quality for content
    MIN_MASTERY_THRESHOLD = 0.5  # 50% minimum for basic understanding
    DEFAULT_CONFIDENCE_THRESHOLD = 0.8  # 80% confidence for relationships
    HIGH_CONFIDENCE = 0.9  # 90% for high confidence

    # Time constants
    REVIEW_DAYS = 7  # Days before review is needed
    SESSION_TIMEOUT_MINUTES = 30
    CACHE_TTL_SECONDS = 300  # 5 minutes default

    # Limits
    MAX_SEARCH_RESULTS = 100
    DEFAULT_SEARCH_LIMIT = 20
    MAX_CONVERSATION_TURNS = 50
    MAX_LEARNING_PATH_STEPS = 100

    # Batch sizes
    BATCH_SIZE_SMALL = 10
    BATCH_SIZE_MEDIUM = 50
    BATCH_SIZE_LARGE = 100

    # Scoring weights
    RELEVANCE_WEIGHT = 0.6
    RECENCY_WEIGHT = 0.2
    FREQUENCY_WEIGHT = 0.2

    # Default values
    DEFAULT_CONTEXT_WINDOW = 10
    DEFAULT_EMBEDDING_DIM = 768
