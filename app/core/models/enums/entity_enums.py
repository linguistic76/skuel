"""
Entity Enums - Core Identity, Lifecycle, and Domain Classification
===================================================================

Core enums for entity type discrimination, processing lifecycle,
content origin, and domain classification.

Organized in 5 sections:
1. Core Identity: EntityType (16 values), ContentOrigin (4 tiers)
2. Processing Lifecycle: EntityStatus (14 values), ProcessorType (4 values)
3. Domain Classification: Domain, NonKuDomain, DomainIdentifier
4. Analytics: AnalyticsDomain
5. Access Control: ContentScope, Context
"""

from __future__ import annotations

from enum import Enum

# =============================================================================
# 1. CORE IDENTITY
# =============================================================================


class EntityType(str, Enum):
    """
    Type of Knowledge Unit — 16 manifestations of knowledge in SKUEL.

    "Everything is a Ku" — a task is knowledge about what needs doing,
    a principle is knowledge about what you believe, a goal is knowledge
    about where you're heading.

    Five groups:
        Knowledge (shared curriculum):
            CURRICULUM      → Admin-created shared knowledge
            RESOURCE        → Books, talks, films, music (admin-only)
        Curriculum Structure:
            LEARNING_STEP   → Step in a learning path
            LEARNING_PATH   → Ordered sequence of steps
            EXERCISE        → Instruction template for practicing curriculum
        Content Processing:
            JOURNAL         → Raw student submission (voice/text, informal)
            SUBMISSION      → Student-uploaded work (file submissions)
            AI_REPORT       → AI-derived from submission/journal
            FEEDBACK_REPORT → Teacher feedback on submission
        Activity (user-owned):
            TASK            → Knowledge about what needs doing
            GOAL            → Knowledge about where you're heading
            HABIT           → Knowledge about what you practice
            EVENT           → Knowledge about what you attend
            CHOICE          → Knowledge about decisions you make
            PRINCIPLE       → Knowledge about what you believe
        Destination:
            LIFE_PATH       → Knowledge about your life direction

    Any Ku can organize other Kus via ORGANIZES relationships (emergent
    identity — no separate MOC type needed).

    Content origin tiers (see ContentOrigin):
        A  CURATED      → RESOURCE
        B  CURRICULUM   → CURRICULUM, LEARNING_STEP, LEARNING_PATH, EXERCISE
        C  USER_CREATED → Activities, SUBMISSION, JOURNAL, LIFE_PATH
        D  FEEDBACK     → AI_REPORT, FEEDBACK_REPORT

    Ownership rules:
        Knowledge group:     user_uid = None (shared content, admin-created)
        Curriculum structure: user_uid = None (shared structure)
        Content processing:  user_uid = student/teacher (user-owned)
        Activity group:      user_uid = student (user-owned)
        Destination:         user_uid = student (user-owned)
    """

    # Knowledge (shared curriculum)
    CURRICULUM = "curriculum"
    RESOURCE = "resource"

    # Curriculum structure
    LEARNING_STEP = "learning_step"
    LEARNING_PATH = "learning_path"

    # Content processing (derivation chain)
    JOURNAL = "journal"
    SUBMISSION = "submission"
    AI_REPORT = "ai_report"
    FEEDBACK_REPORT = "feedback_report"

    # Activity (user-owned)
    TASK = "task"
    GOAL = "goal"
    HABIT = "habit"
    EVENT = "event"
    CHOICE = "choice"
    PRINCIPLE = "principle"

    # Curriculum instruction templates
    EXERCISE = "exercise"

    # Destination
    LIFE_PATH = "life_path"

    # -------------------------------------------------------------------------
    # Display
    # -------------------------------------------------------------------------

    def get_display_name(self) -> str:
        """Get human-readable display name for UI."""
        return _ENTITY_TYPE_DISPLAY_NAMES[self]

    # -------------------------------------------------------------------------
    # Group classification
    # -------------------------------------------------------------------------

    def is_knowledge(self) -> bool:
        """Check if this is shared curriculum knowledge (admin-created)."""
        return self in _KNOWLEDGE_TYPES

    def is_curriculum_structure(self) -> bool:
        """Check if this is curriculum structure (LS or LP)."""
        return self in _CURRICULUM_STRUCTURE_TYPES

    def is_activity(self) -> bool:
        """Check if this is a user activity domain."""
        return self in _ACTIVITY_TYPES

    def is_destination(self) -> bool:
        """Check if this is the life path destination."""
        return self == EntityType.LIFE_PATH

    def is_content_processing(self) -> bool:
        """Check if this is in the content processing chain."""
        return self in _CONTENT_PROCESSING_TYPES

    def content_origin(self) -> ContentOrigin:
        """Return the content origin tier (A-D) for this EntityType."""
        return _CONTENT_ORIGIN_BY_TYPE[self]

    # -------------------------------------------------------------------------
    # Ownership
    # -------------------------------------------------------------------------

    def requires_user_uid(self) -> bool:
        """Check if this EntityType requires a user_uid (ownership)."""
        return self not in _SHARED_TYPES

    def is_user_owned(self) -> bool:
        """Check if this EntityType represents user-owned content."""
        return self not in _SHARED_TYPES

    # -------------------------------------------------------------------------
    # Derivation chain
    # -------------------------------------------------------------------------

    def is_derived(self) -> bool:
        """Check if this EntityType is derived from another Entity (has parent)."""
        return self in {
            EntityType.JOURNAL,
            EntityType.SUBMISSION,
            EntityType.AI_REPORT,
            EntityType.FEEDBACK_REPORT,
        }

    def is_processable(self) -> bool:
        """Check if this EntityType goes through a processing pipeline."""
        return self in {EntityType.JOURNAL, EntityType.SUBMISSION, EntityType.AI_REPORT}

    # -------------------------------------------------------------------------
    # Status validation
    # -------------------------------------------------------------------------

    def valid_statuses(self) -> frozenset[EntityStatus]:
        """Return the set of EntityStatus values valid for this EntityType."""
        return _VALID_STATUSES_BY_TYPE[self]

    def default_status(self) -> EntityStatus:
        """Return the default status for this EntityType."""
        return _DEFAULT_STATUS_BY_TYPE[self]

    # -------------------------------------------------------------------------
    # String parsing (for DSL and ingestion)
    # -------------------------------------------------------------------------

    @classmethod
    def from_string(cls, text: str) -> EntityType | None:
        """
        Parse EntityType from string (case-insensitive, alias-aware).

        Supports aliases for backward compatibility with DSL and ingestion:
            "knowledge" -> CURRICULUM
            "ku" -> CURRICULUM
            "ls" -> LEARNING_STEP
            "lp" -> LEARNING_PATH
            "report" -> AI_REPORT
        """
        normalized = text.strip().lower().replace("-", "_").replace(" ", "_")
        return _ENTITY_TYPE_ALIASES.get(normalized)


# EntityType lookup tables (module-level for performance)
_ENTITY_TYPE_DISPLAY_NAMES: dict[EntityType, str] = {
    EntityType.CURRICULUM: "Curriculum",
    EntityType.RESOURCE: "Resource",
    EntityType.LEARNING_STEP: "Learning Step",
    EntityType.LEARNING_PATH: "Learning Path",
    EntityType.JOURNAL: "Journal",
    EntityType.SUBMISSION: "Submission",
    EntityType.AI_REPORT: "AI Report",
    EntityType.FEEDBACK_REPORT: "Feedback Report",
    EntityType.TASK: "Task",
    EntityType.GOAL: "Goal",
    EntityType.HABIT: "Habit",
    EntityType.EVENT: "Event",
    EntityType.CHOICE: "Choice",
    EntityType.PRINCIPLE: "Principle",
    EntityType.EXERCISE: "Exercise",
    EntityType.LIFE_PATH: "Life Path",
}

_KNOWLEDGE_TYPES = frozenset({EntityType.CURRICULUM, EntityType.RESOURCE})
_CURRICULUM_STRUCTURE_TYPES = frozenset(
    {EntityType.LEARNING_STEP, EntityType.LEARNING_PATH, EntityType.EXERCISE}
)
_CONTENT_PROCESSING_TYPES = frozenset(
    {EntityType.JOURNAL, EntityType.SUBMISSION, EntityType.AI_REPORT, EntityType.FEEDBACK_REPORT}
)
_ACTIVITY_TYPES = frozenset(
    {
        EntityType.TASK,
        EntityType.GOAL,
        EntityType.HABIT,
        EntityType.EVENT,
        EntityType.CHOICE,
        EntityType.PRINCIPLE,
    }
)
_SHARED_TYPES = frozenset(
    {
        EntityType.CURRICULUM,
        EntityType.RESOURCE,
        EntityType.LEARNING_STEP,
        EntityType.LEARNING_PATH,
        EntityType.EXERCISE,
    }
)


class ContentOrigin(str, Enum):
    """
    Content origin tier — classifies KuTypes by where content comes from
    and what role it plays in the system.

    Four tiers:
        CURATED      (A) → Admin-curated resources, used by Askesis
        CURRICULUM   (B) → Curriculum structure and organization
        USER_CREATED (C) → User-generated content (activities, submissions, journals)
        FEEDBACK     (D) → Analysis/feedback that acts on user content
    """

    CURATED = "curated"
    CURRICULUM = "curriculum"
    USER_CREATED = "user_created"
    FEEDBACK = "feedback"


_CONTENT_ORIGIN_BY_TYPE: dict[EntityType, ContentOrigin] = {
    # A — Admin-curated resources
    EntityType.RESOURCE: ContentOrigin.CURATED,
    # B — Curriculum structure and organization
    EntityType.CURRICULUM: ContentOrigin.CURRICULUM,
    EntityType.LEARNING_STEP: ContentOrigin.CURRICULUM,
    EntityType.LEARNING_PATH: ContentOrigin.CURRICULUM,
    EntityType.EXERCISE: ContentOrigin.CURRICULUM,
    # C — User-generated content
    EntityType.TASK: ContentOrigin.USER_CREATED,
    EntityType.GOAL: ContentOrigin.USER_CREATED,
    EntityType.HABIT: ContentOrigin.USER_CREATED,
    EntityType.EVENT: ContentOrigin.USER_CREATED,
    EntityType.CHOICE: ContentOrigin.USER_CREATED,
    EntityType.PRINCIPLE: ContentOrigin.USER_CREATED,
    EntityType.SUBMISSION: ContentOrigin.USER_CREATED,
    EntityType.JOURNAL: ContentOrigin.USER_CREATED,
    EntityType.LIFE_PATH: ContentOrigin.USER_CREATED,
    # D — Feedback that acts on user content
    EntityType.AI_REPORT: ContentOrigin.FEEDBACK,
    EntityType.FEEDBACK_REPORT: ContentOrigin.FEEDBACK,
}

_ENTITY_TYPE_ALIASES: dict[str, EntityType] = {
    # Canonical values
    "curriculum": EntityType.CURRICULUM,
    "resource": EntityType.RESOURCE,
    "moc": EntityType.CURRICULUM,
    "learning_step": EntityType.LEARNING_STEP,
    "learning_path": EntityType.LEARNING_PATH,
    "journal": EntityType.JOURNAL,
    "submission": EntityType.SUBMISSION,
    "ai_report": EntityType.AI_REPORT,
    "feedback_report": EntityType.FEEDBACK_REPORT,
    "task": EntityType.TASK,
    "goal": EntityType.GOAL,
    "habit": EntityType.HABIT,
    "event": EntityType.EVENT,
    "choice": EntityType.CHOICE,
    "principle": EntityType.PRINCIPLE,
    "life_path": EntityType.LIFE_PATH,
    # Aliases
    "knowledge": EntityType.CURRICULUM,
    "ku": EntityType.CURRICULUM,
    "book": EntityType.RESOURCE,
    "film": EntityType.RESOURCE,
    "talk": EntityType.RESOURCE,
    "map_of_content": EntityType.CURRICULUM,
    "ls": EntityType.LEARNING_STEP,
    "step": EntityType.LEARNING_STEP,
    "lp": EntityType.LEARNING_PATH,
    "path": EntityType.LEARNING_PATH,
    "report": EntityType.AI_REPORT,
    "exercise": EntityType.EXERCISE,
    "assignment": EntityType.EXERCISE,
    "feedback": EntityType.FEEDBACK_REPORT,
    "lifepath": EntityType.LIFE_PATH,
}


# =============================================================================
# 2. PROCESSING LIFECYCLE
# =============================================================================


class EntityStatus(str, Enum):
    """
    Processing lifecycle status for a Knowledge Unit.

    14 values covering all lifecycle patterns across all KuTypes.

    Content processing lifecycle:
        DRAFT -> SUBMITTED -> QUEUED -> PROCESSING -> COMPLETED / FAILED
                                                        |
                                                 REVISION_REQUESTED -> resubmit

    Activity lifecycle:
        DRAFT -> SCHEDULED -> ACTIVE -> PAUSED -> COMPLETED
                    |           |         |
                    |           +-> BLOCKED -> ACTIVE
                    |           |
                    +-> POSTPONED   +-> CANCELLED / FAILED

    Terminal states: COMPLETED, FAILED, CANCELLED, ARCHIVED

    Use `can_transition_to(target, ku_type)` for type-aware validation.
    """

    DRAFT = "draft"
    SUBMITTED = "submitted"
    QUEUED = "queued"
    PROCESSING = "processing"
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    PAUSED = "paused"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    POSTPONED = "postponed"
    REVISION_REQUESTED = "revision_requested"
    ARCHIVED = "archived"

    def get_display_name(self) -> str:
        """Get human-readable display name for UI."""
        return _ENTITY_STATUS_DISPLAY_NAMES[self]

    def get_color(self) -> str:
        """Get hex color for UI rendering."""
        return _ENTITY_STATUS_COLORS[self]

    def get_search_synonyms(self) -> tuple[str, ...]:
        """Return search terms that match this status."""
        return _ENTITY_STATUS_SEARCH_SYNONYMS.get(self, ())

    def get_search_description(self) -> str:
        """Human-readable description for search UI."""
        return _ENTITY_STATUS_SEARCH_DESCRIPTIONS.get(self, "")

    @classmethod
    def from_search_text(cls, text: str) -> list[EntityStatus]:
        """Find matching statuses from search text."""
        text_lower = text.lower()
        return [
            status
            for status in cls
            if any(synonym in text_lower for synonym in status.get_search_synonyms())
        ]

    def is_terminal(self) -> bool:
        """Check if this is a terminal (non-progressing) status."""
        return self in _TERMINAL_STATUSES

    def is_active(self) -> bool:
        """Check if this status indicates active work/processing."""
        return self in _ACTIVE_STATUSES

    def is_pending(self) -> bool:
        """Check if this status indicates pending/waiting state."""
        return self in {
            EntityStatus.DRAFT,
            EntityStatus.SUBMITTED,
            EntityStatus.QUEUED,
            EntityStatus.SCHEDULED,
        }

    def can_transition_to(self, target: EntityStatus, ku_type: EntityType | None = None) -> bool:
        """
        Check if transition to target status is valid.

        When ku_type is provided, validates both:
        1. Target is a valid status for that EntityType
        2. The transition itself is allowed

        When ku_type is None, only checks the general transition map.
        """
        if ku_type is not None:
            valid = ku_type.valid_statuses()
            if self not in valid or target not in valid:
                return False
        return target in _VALID_TRANSITIONS.get(self, set())


_ENTITY_STATUS_DISPLAY_NAMES: dict[EntityStatus, str] = {
    EntityStatus.DRAFT: "Draft",
    EntityStatus.SUBMITTED: "Submitted",
    EntityStatus.QUEUED: "Queued",
    EntityStatus.PROCESSING: "Processing",
    EntityStatus.SCHEDULED: "Scheduled",
    EntityStatus.ACTIVE: "Active",
    EntityStatus.PAUSED: "Paused",
    EntityStatus.BLOCKED: "Blocked",
    EntityStatus.COMPLETED: "Completed",
    EntityStatus.FAILED: "Failed",
    EntityStatus.CANCELLED: "Cancelled",
    EntityStatus.POSTPONED: "Postponed",
    EntityStatus.REVISION_REQUESTED: "Revision Requested",
    EntityStatus.ARCHIVED: "Archived",
}

_TERMINAL_STATUSES = frozenset(
    {
        EntityStatus.COMPLETED,
        EntityStatus.FAILED,
        EntityStatus.CANCELLED,
        EntityStatus.ARCHIVED,
    }
)

_ACTIVE_STATUSES = frozenset(
    {
        EntityStatus.SUBMITTED,
        EntityStatus.QUEUED,
        EntityStatus.PROCESSING,
        EntityStatus.ACTIVE,
        EntityStatus.SCHEDULED,
    }
)

_ENTITY_STATUS_COLORS: dict[EntityStatus, str] = {
    EntityStatus.DRAFT: "#9CA3AF",  # Light gray
    EntityStatus.SUBMITTED: "#8B5CF6",  # Violet
    EntityStatus.QUEUED: "#A855F7",  # Purple
    EntityStatus.PROCESSING: "#F59E0B",  # Amber
    EntityStatus.SCHEDULED: "#3B82F6",  # Blue
    EntityStatus.ACTIVE: "#06B6D4",  # Cyan
    EntityStatus.PAUSED: "#F59E0B",  # Amber
    EntityStatus.BLOCKED: "#DC2626",  # Red
    EntityStatus.COMPLETED: "#10B981",  # Green
    EntityStatus.FAILED: "#EF4444",  # Red
    EntityStatus.CANCELLED: "#6B7280",  # Gray
    EntityStatus.POSTPONED: "#A855F7",  # Purple
    EntityStatus.REVISION_REQUESTED: "#F97316",  # Orange
    EntityStatus.ARCHIVED: "#9CA3AF",  # Gray
}

_ENTITY_STATUS_SEARCH_SYNONYMS: dict[EntityStatus, tuple[str, ...]] = {
    EntityStatus.DRAFT: ("draft", "new", "planning", "unconfirmed"),
    EntityStatus.SUBMITTED: ("submitted", "sent", "turned in"),
    EntityStatus.QUEUED: ("queued", "waiting", "in queue"),
    EntityStatus.PROCESSING: ("processing", "running", "analyzing"),
    EntityStatus.SCHEDULED: ("scheduled", "planned", "upcoming", "queued"),
    EntityStatus.ACTIVE: ("active", "in progress", "working", "current", "ongoing"),
    EntityStatus.PAUSED: ("paused", "on hold", "waiting", "suspended"),
    EntityStatus.BLOCKED: ("blocked", "stuck", "waiting on", "dependent"),
    EntityStatus.COMPLETED: ("completed", "done", "finished", "complete", "achieved"),
    EntityStatus.FAILED: ("failed", "unsuccessful", "not completed"),
    EntityStatus.CANCELLED: ("cancelled", "canceled", "abandoned", "dropped"),
    EntityStatus.POSTPONED: ("postponed", "delayed", "rescheduled", "deferred"),
    EntityStatus.REVISION_REQUESTED: ("revision", "revise", "redo", "resubmit"),
    EntityStatus.ARCHIVED: ("archived", "old", "historical", "past"),
}

_ENTITY_STATUS_SEARCH_DESCRIPTIONS: dict[EntityStatus, str] = {
    EntityStatus.DRAFT: "Not yet scheduled or confirmed",
    EntityStatus.SUBMITTED: "Submitted for processing",
    EntityStatus.QUEUED: "Waiting in processing queue",
    EntityStatus.PROCESSING: "Currently being processed",
    EntityStatus.SCHEDULED: "Scheduled but not started",
    EntityStatus.ACTIVE: "Currently being worked on",
    EntityStatus.PAUSED: "Temporarily paused",
    EntityStatus.BLOCKED: "Blocked by dependency",
    EntityStatus.COMPLETED: "Successfully completed",
    EntityStatus.FAILED: "Failed to complete",
    EntityStatus.CANCELLED: "Cancelled before completion",
    EntityStatus.POSTPONED: "Moved to future time",
    EntityStatus.REVISION_REQUESTED: "Revision requested",
    EntityStatus.ARCHIVED: "No longer active",
}

# General transition map — union of all valid transitions across all EntityTypes.
# Type-specific validation is handled by can_transition_to() + valid_statuses().
_VALID_TRANSITIONS: dict[EntityStatus, set[EntityStatus]] = {
    EntityStatus.DRAFT: {
        EntityStatus.SUBMITTED,
        EntityStatus.SCHEDULED,
        EntityStatus.ACTIVE,
        EntityStatus.COMPLETED,
        EntityStatus.CANCELLED,
        EntityStatus.ARCHIVED,
    },
    EntityStatus.SUBMITTED: {
        EntityStatus.QUEUED,
        EntityStatus.PROCESSING,
        EntityStatus.FAILED,
    },
    EntityStatus.QUEUED: {
        EntityStatus.PROCESSING,
        EntityStatus.FAILED,
    },
    EntityStatus.PROCESSING: {
        EntityStatus.COMPLETED,
        EntityStatus.FAILED,
    },
    EntityStatus.SCHEDULED: {
        EntityStatus.ACTIVE,
        EntityStatus.COMPLETED,
        EntityStatus.CANCELLED,
        EntityStatus.POSTPONED,
    },
    EntityStatus.ACTIVE: {
        EntityStatus.PAUSED,
        EntityStatus.BLOCKED,
        EntityStatus.COMPLETED,
        EntityStatus.CANCELLED,
        EntityStatus.FAILED,
        EntityStatus.ARCHIVED,
    },
    EntityStatus.PAUSED: {
        EntityStatus.ACTIVE,
        EntityStatus.CANCELLED,
        EntityStatus.ARCHIVED,
    },
    EntityStatus.BLOCKED: {
        EntityStatus.ACTIVE,
        EntityStatus.CANCELLED,
    },
    EntityStatus.COMPLETED: {
        EntityStatus.REVISION_REQUESTED,
        EntityStatus.ARCHIVED,
    },
    EntityStatus.FAILED: {
        EntityStatus.DRAFT,
        EntityStatus.CANCELLED,
        EntityStatus.ARCHIVED,
    },
    EntityStatus.CANCELLED: {
        EntityStatus.ARCHIVED,
    },
    EntityStatus.POSTPONED: {
        EntityStatus.DRAFT,
        EntityStatus.SCHEDULED,
        EntityStatus.CANCELLED,
    },
    EntityStatus.REVISION_REQUESTED: {
        EntityStatus.DRAFT,
        EntityStatus.ARCHIVED,
    },
    EntityStatus.ARCHIVED: set(),
}

# Valid statuses per EntityType (from plan specification)
_VALID_STATUSES_BY_TYPE: dict[EntityType, frozenset[EntityStatus]] = {
    EntityType.CURRICULUM: frozenset(
        {
            EntityStatus.DRAFT,
            EntityStatus.COMPLETED,
            EntityStatus.ARCHIVED,
        }
    ),
    EntityType.RESOURCE: frozenset(
        {
            EntityStatus.DRAFT,
            EntityStatus.COMPLETED,
            EntityStatus.ARCHIVED,
        }
    ),
    EntityType.LEARNING_STEP: frozenset(
        {
            EntityStatus.DRAFT,
            EntityStatus.ACTIVE,
            EntityStatus.COMPLETED,
            EntityStatus.ARCHIVED,
        }
    ),
    EntityType.LEARNING_PATH: frozenset(
        {
            EntityStatus.DRAFT,
            EntityStatus.ACTIVE,
            EntityStatus.COMPLETED,
            EntityStatus.ARCHIVED,
        }
    ),
    EntityType.JOURNAL: frozenset(
        {
            EntityStatus.DRAFT,
            EntityStatus.SUBMITTED,
            EntityStatus.QUEUED,
            EntityStatus.PROCESSING,
            EntityStatus.COMPLETED,
            EntityStatus.FAILED,
            EntityStatus.REVISION_REQUESTED,
            EntityStatus.ARCHIVED,
        }
    ),
    EntityType.SUBMISSION: frozenset(
        {
            EntityStatus.DRAFT,
            EntityStatus.SUBMITTED,
            EntityStatus.QUEUED,
            EntityStatus.PROCESSING,
            EntityStatus.COMPLETED,
            EntityStatus.FAILED,
            EntityStatus.REVISION_REQUESTED,
            EntityStatus.ARCHIVED,
        }
    ),
    EntityType.AI_REPORT: frozenset(
        {
            EntityStatus.DRAFT,
            EntityStatus.PROCESSING,
            EntityStatus.COMPLETED,
            EntityStatus.FAILED,
            EntityStatus.ARCHIVED,
        }
    ),
    EntityType.FEEDBACK_REPORT: frozenset(
        {
            EntityStatus.DRAFT,
            EntityStatus.COMPLETED,
            EntityStatus.ARCHIVED,
        }
    ),
    EntityType.TASK: frozenset(
        {
            EntityStatus.DRAFT,
            EntityStatus.SCHEDULED,
            EntityStatus.ACTIVE,
            EntityStatus.PAUSED,
            EntityStatus.BLOCKED,
            EntityStatus.COMPLETED,
            EntityStatus.CANCELLED,
            EntityStatus.POSTPONED,
            EntityStatus.FAILED,
        }
    ),
    EntityType.GOAL: frozenset(
        {
            EntityStatus.DRAFT,
            EntityStatus.ACTIVE,
            EntityStatus.PAUSED,
            EntityStatus.COMPLETED,
            EntityStatus.CANCELLED,
            EntityStatus.FAILED,
            EntityStatus.ARCHIVED,
        }
    ),
    EntityType.HABIT: frozenset(
        {
            EntityStatus.ACTIVE,
            EntityStatus.PAUSED,
            EntityStatus.COMPLETED,
            EntityStatus.CANCELLED,
            EntityStatus.ARCHIVED,
        }
    ),
    EntityType.EVENT: frozenset(
        {
            EntityStatus.SCHEDULED,
            EntityStatus.ACTIVE,
            EntityStatus.COMPLETED,
            EntityStatus.CANCELLED,
        }
    ),
    EntityType.CHOICE: frozenset(
        {
            EntityStatus.DRAFT,
            EntityStatus.ACTIVE,
            EntityStatus.COMPLETED,
            EntityStatus.ARCHIVED,
        }
    ),
    EntityType.PRINCIPLE: frozenset(
        {
            EntityStatus.ACTIVE,
            EntityStatus.PAUSED,
            EntityStatus.ARCHIVED,
        }
    ),
    EntityType.EXERCISE: frozenset(
        {
            EntityStatus.DRAFT,
            EntityStatus.ACTIVE,
            EntityStatus.COMPLETED,
            EntityStatus.ARCHIVED,
        }
    ),
    EntityType.LIFE_PATH: frozenset(
        {
            EntityStatus.ACTIVE,
            EntityStatus.ARCHIVED,
        }
    ),
}

_DEFAULT_STATUS_BY_TYPE: dict[EntityType, EntityStatus] = {
    EntityType.CURRICULUM: EntityStatus.COMPLETED,
    EntityType.RESOURCE: EntityStatus.COMPLETED,
    EntityType.LEARNING_STEP: EntityStatus.DRAFT,
    EntityType.LEARNING_PATH: EntityStatus.DRAFT,
    EntityType.EXERCISE: EntityStatus.DRAFT,
    EntityType.JOURNAL: EntityStatus.DRAFT,
    EntityType.SUBMISSION: EntityStatus.DRAFT,
    EntityType.AI_REPORT: EntityStatus.DRAFT,
    EntityType.FEEDBACK_REPORT: EntityStatus.DRAFT,
    EntityType.TASK: EntityStatus.DRAFT,
    EntityType.GOAL: EntityStatus.DRAFT,
    EntityType.HABIT: EntityStatus.ACTIVE,
    EntityType.EVENT: EntityStatus.SCHEDULED,
    EntityType.CHOICE: EntityStatus.DRAFT,
    EntityType.PRINCIPLE: EntityStatus.ACTIVE,
    EntityType.LIFE_PATH: EntityStatus.ACTIVE,
}


class ProcessorType(str, Enum):
    """
    Type of processor used for content processing.

    Determines the processing pipeline:
        LLM: AI/LLM processing (OpenAI, etc.)
        HUMAN: Manual human review (teacher feedback)
        HYBRID: LLM + human review
        AUTOMATIC: System-determined processor
    """

    LLM = "llm"
    HUMAN = "human"
    HYBRID = "hybrid"
    AUTOMATIC = "automatic"

    def get_display_name(self) -> str:
        """Get human-readable display name for UI."""
        return {
            ProcessorType.LLM: "AI Processing",
            ProcessorType.HUMAN: "Human Review",
            ProcessorType.HYBRID: "Hybrid (AI + Human)",
            ProcessorType.AUTOMATIC: "Automatic",
        }[self]


# =============================================================================
# 3. DOMAIN CLASSIFICATION
# =============================================================================


class Domain(str, Enum):
    """
    Core domains in the SKUEL system.
    Each domain represents a distinct area of functionality.
    """

    # Core system domains
    KNOWLEDGE = "knowledge"
    LEARNING = "learning"
    TASKS = "tasks"
    HABITS = "habits"
    FINANCE = "finance"
    EVENTS = "events"
    REPORTS = "reports"
    JOURNALS = "journals"  # Alias for REPORTS (migration aid)
    PRINCIPLES = "principles"
    GOALS = "goals"
    CHOICES = "choices"
    SYSTEM = "system"
    ALL = "all"  # Special case for cross-domain operations

    # Knowledge categorization domains
    TECH = "tech"
    BUSINESS = "business"
    PERSONAL = "personal"
    HEALTH = "health"
    EDUCATION = "education"
    CREATIVE = "creative"
    RESEARCH = "research"
    SOCIAL = "social"
    META = "meta"
    CROSS_DOMAIN = "cross_domain"

    def get_search_synonyms(self) -> tuple[str, ...]:
        """Return search terms that match this domain"""
        synonyms = {
            Domain.KNOWLEDGE: ("knowledge", "learn", "study", "education", "info", "ku"),
            Domain.LEARNING: ("learning", "course", "path", "curriculum", "lp", "ls"),
            Domain.TASKS: ("task", "todo", "work", "action"),
            Domain.HABITS: ("habit", "routine", "practice", "behavior", "pattern"),
            Domain.FINANCE: ("finance", "money", "budget", "expense", "income"),
            Domain.EVENTS: ("event", "calendar", "meeting", "appointment", "schedule"),
            Domain.REPORTS: ("report", "journal", "entry", "log", "diary", "reflection"),
            Domain.PRINCIPLES: ("principle", "value", "belief", "philosophy", "guideline"),
            Domain.GOALS: ("goal", "objective", "target", "aim", "milestone"),
            Domain.CHOICES: ("choice", "decision", "option", "selection"),
            Domain.TECH: ("tech", "technology", "programming", "software", "code"),
            Domain.BUSINESS: ("business", "work", "professional", "career"),
            Domain.PERSONAL: ("personal", "self", "life", "individual"),
            Domain.HEALTH: ("health", "fitness", "wellness", "medical"),
            Domain.EDUCATION: ("education", "academic", "school", "university"),
            Domain.CREATIVE: ("creative", "art", "design", "music"),
            Domain.RESEARCH: ("research", "study", "investigation", "analysis"),
            Domain.SOCIAL: ("social", "people", "relationship", "community"),
        }
        return synonyms.get(self, (self.value,))

    @classmethod
    def from_search_text(cls, text: str) -> list[Domain]:
        """Find matching domains from search text"""
        text_lower = text.lower()
        return [
            domain
            for domain in cls
            if any(synonym in text_lower for synonym in domain.get_search_synonyms())
        ]


class NonKuDomain(str, Enum):
    """
    Non-knowledge-unit domains outside the Entity model hierarchy.

    These 4 domains exist in SKUEL but are NOT represented as :Entity nodes:
    - FINANCE: Admin-only bookkeeping (:Expense nodes)
    - GROUP: Teacher-student class management (:Group nodes, ADR-040)
    - CALENDAR: Aggregation meta-service (no dedicated nodes)
    - LEARNING: DSL context modifier (not a domain entity)
    """

    FINANCE = "finance"
    GROUP = "group"
    CALENDAR = "calendar"
    LEARNING = "learning"  # DSL context modifier

    @classmethod
    def from_string(cls, value: str) -> NonKuDomain | None:
        """Parse a string to NonKuDomain, case-insensitive."""
        normalized = value.strip().lower()
        try:
            return cls(normalized)
        except ValueError:
            return None


# Union type for any domain identifier in SKUEL.
# EntityType covers all 16 entity manifestations; NonKuDomain covers the 4 non-entity domains.
DomainIdentifier = EntityType | NonKuDomain


# =============================================================================
# 4. ANALYTICS
# =============================================================================


class AnalyticsDomain(str, Enum):
    """
    Core system domains that can generate statistical analytics.

    Analytics provide quantitative assessment of user data within each domain.
    """

    TASKS = "tasks"
    HABITS = "habits"
    GOALS = "goals"
    EVENTS = "events"
    FINANCE = "finance"
    CHOICES = "choices"

    def get_metrics(self) -> list[str]:
        """Get available metrics for this analytics domain"""
        metrics = {
            AnalyticsDomain.TASKS: [
                "completion_rate",
                "total_count",
                "completed_count",
                "in_progress_count",
                "pending_count",
                "overdue_count",
                "priority_distribution",
                "avg_completion_time_days",
            ],
            AnalyticsDomain.HABITS: [
                "total_active",
                "completion_rate",
                "current_streaks",
                "best_streaks",
                "consistency_rate",
                "completion_by_day_of_week",
            ],
            AnalyticsDomain.GOALS: [
                "total_active",
                "total_completed",
                "on_track_count",
                "at_risk_count",
                "avg_progress_percentage",
                "completion_rate",
            ],
            AnalyticsDomain.EVENTS: [
                "total_count",
                "upcoming_count",
                "completed_count",
                "cancelled_count",
                "total_hours_scheduled",
                "events_by_type",
            ],
            AnalyticsDomain.FINANCE: [
                "total_expenses",
                "total_income",
                "net_balance",
                "expenses_by_category",
                "budget_adherence",
                "avg_daily_expense",
            ],
            AnalyticsDomain.CHOICES: [
                "total_choices",
                "choices_by_domain",
                "decision_quality_avg",
                "choices_reviewed_count",
            ],
        }
        return metrics.get(self, [])


# =============================================================================
# 5. ACCESS CONTROL
# =============================================================================


class ContentScope(str, Enum):
    """
    Defines content ownership/sharing model for domain entities.

    This enum makes the critical security contract explicit in code:
    - USER_OWNED: User-specific content with ownership verification
    - SHARED: Public reading, admin-only creation (curriculum domains)

    Combined with require_role=UserRole.ADMIN for write operations:
    - Read (get, list): Public, no authentication required
    - Write (create, update, delete): ADMIN role required

    Usage in route factories:
        CRUDRouteFactory(
            service=tasks_service,
            scope=ContentScope.USER_OWNED,  # Tasks are user-owned
        )

        CRUDRouteFactory(
            service=ku_service,
            scope=ContentScope.SHARED,       # Knowledge Units are shared
            require_role=UserRole.ADMIN,      # Admin-only writes
            user_service_getter=getter,
        )

    IMPORTANT: SHARED content means user_uid=None in list() requests for
    unauthenticated users. Services must handle this correctly:
    - user_uid=None → return shared/public content
    - user_uid=None does NOT mean "return everything"

    Access control summary:
    - Activity domains (USER_OWNED): Any user creates and owns their content
    - Curriculum domains (SHARED + ADMIN): Admin creates, everyone reads
    - Finance (ADMIN_ONLY via require_role): Admin creates and reads
    """

    USER_OWNED = "user_owned"  # User-specific with ownership checks
    SHARED = "shared"  # Public/shared, no ownership required


class Context(str, Enum):
    """Context where activity can be performed"""

    HOME = "home"
    WORK = "work"
    COMPUTER = "computer"
    PHONE = "phone"
    ERRANDS = "errands"
    ANYWHERE = "anywhere"
