"""
Ku Enums - Unified Knowledge Unit Identity and Processing
==========================================================

Enums for the unified Ku model where "Ku is the heartbeat of SKUEL."

Organized in 12 sections:
1. Core Identity: KuType (14 values — role and domain manifestation)
2. Processing Lifecycle: KuStatus (14 values — type-aware transitions), ProcessorType
3. Project/Assignment: ProjectScope (teacher assignment workflow)
4. Journal Processing: JournalType, JournalCategory, JournalMode
5. LLM Processing: FormattingStyle, AnalysisDepth, ContextEnrichmentLevel
6. Schedule: ScheduleType, ProgressDepth
7. Goal: GoalType, GoalTimeframe, MeasurementType
8. Habit: HabitPolarity, HabitCategory, HabitDifficulty
9. Choice: ChoiceType
10. Principle: PrincipleCategory, PrincipleSource, PrincipleStrength
11. Alignment: AlignmentLevel (unified — principles + life path)
12. Curriculum Structure: LpType, StepDifficulty

Per One Path Forward: These are THE canonical location for all Ku-related enums.
"""

from __future__ import annotations

from enum import Enum


# =============================================================================
# 1. CORE IDENTITY
# =============================================================================


class KuType(str, Enum):
    """
    Type of Knowledge Unit — 14 manifestations of knowledge in SKUEL.

    "Everything is a Ku" — a task is knowledge about what needs doing,
    a principle is knowledge about what you believe, a goal is knowledge
    about where you're heading.

    Four groups:
        Knowledge (shared curriculum):
            CURRICULUM      → Admin-created shared knowledge
            MOC             → Map of Content (KU organizing KUs)
        Curriculum Structure:
            LEARNING_STEP   → Step in a learning path
            LEARNING_PATH   → Ordered sequence of steps
        Content Processing:
            ASSIGNMENT      → Student submission (user-owned)
            AI_REPORT       → AI-derived from assignment
            FEEDBACK_REPORT → Teacher feedback on assignment
        Activity (user-owned):
            TASK            → Knowledge about what needs doing
            GOAL            → Knowledge about where you're heading
            HABIT           → Knowledge about what you practice
            EVENT           → Knowledge about what you attend
            CHOICE          → Knowledge about decisions you make
            PRINCIPLE       → Knowledge about what you believe
        Destination:
            LIFE_PATH       → Knowledge about your life direction

    Ownership rules:
        Knowledge group:     user_uid = None (shared content, admin-created)
        Curriculum structure: user_uid = None (shared structure)
        Content processing:  user_uid = student/teacher (user-owned)
        Activity group:      user_uid = student (user-owned)
        Destination:         user_uid = student (user-owned)
    """

    # Knowledge (shared curriculum)
    CURRICULUM = "curriculum"
    MOC = "moc"

    # Curriculum structure
    LEARNING_STEP = "learning_step"
    LEARNING_PATH = "learning_path"

    # Content processing (derivation chain)
    ASSIGNMENT = "assignment"
    AI_REPORT = "ai_report"
    FEEDBACK_REPORT = "feedback_report"

    # Activity (user-owned)
    TASK = "task"
    GOAL = "goal"
    HABIT = "habit"
    EVENT = "event"
    CHOICE = "choice"
    PRINCIPLE = "principle"

    # Destination
    LIFE_PATH = "life_path"

    # -------------------------------------------------------------------------
    # Display
    # -------------------------------------------------------------------------

    def get_display_name(self) -> str:
        """Get human-readable display name for UI."""
        return _KU_TYPE_DISPLAY_NAMES[self]

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
        return self == KuType.LIFE_PATH

    def is_content_processing(self) -> bool:
        """Check if this is in the content processing chain."""
        return self in _CONTENT_PROCESSING_TYPES

    # -------------------------------------------------------------------------
    # Ownership
    # -------------------------------------------------------------------------

    def requires_user_uid(self) -> bool:
        """Check if this KuType requires a user_uid (ownership)."""
        return self not in _SHARED_TYPES

    def is_user_owned(self) -> bool:
        """Check if this KuType represents user-owned content."""
        return self not in _SHARED_TYPES

    # -------------------------------------------------------------------------
    # Derivation chain
    # -------------------------------------------------------------------------

    def is_derived(self) -> bool:
        """Check if this KuType is derived from another Ku (has parent)."""
        return self in {KuType.ASSIGNMENT, KuType.AI_REPORT, KuType.FEEDBACK_REPORT}

    def is_processable(self) -> bool:
        """Check if this KuType goes through a processing pipeline."""
        return self in {KuType.ASSIGNMENT, KuType.AI_REPORT}

    # -------------------------------------------------------------------------
    # Status validation
    # -------------------------------------------------------------------------

    def valid_statuses(self) -> frozenset[KuStatus]:
        """Return the set of KuStatus values valid for this KuType."""
        return _VALID_STATUSES_BY_TYPE[self]

    def default_status(self) -> KuStatus:
        """Return the default status for this KuType."""
        return _DEFAULT_STATUS_BY_TYPE[self]

    # -------------------------------------------------------------------------
    # String parsing (for DSL and ingestion)
    # -------------------------------------------------------------------------

    @classmethod
    def from_string(cls, text: str) -> KuType | None:
        """
        Parse KuType from string (case-insensitive, alias-aware).

        Supports aliases for backward compatibility with DSL and ingestion:
            "knowledge" -> CURRICULUM
            "ku" -> CURRICULUM
            "ls" -> LEARNING_STEP
            "lp" -> LEARNING_PATH
            "report" -> ASSIGNMENT
        """
        normalized = text.strip().lower().replace("-", "_").replace(" ", "_")
        return _KU_TYPE_ALIASES.get(normalized)


# KuType lookup tables (module-level for performance)
_KU_TYPE_DISPLAY_NAMES: dict[KuType, str] = {
    KuType.CURRICULUM: "Curriculum",
    KuType.MOC: "Map of Content",
    KuType.LEARNING_STEP: "Learning Step",
    KuType.LEARNING_PATH: "Learning Path",
    KuType.ASSIGNMENT: "Assignment",
    KuType.AI_REPORT: "AI Report",
    KuType.FEEDBACK_REPORT: "Feedback Report",
    KuType.TASK: "Task",
    KuType.GOAL: "Goal",
    KuType.HABIT: "Habit",
    KuType.EVENT: "Event",
    KuType.CHOICE: "Choice",
    KuType.PRINCIPLE: "Principle",
    KuType.LIFE_PATH: "Life Path",
}

_KNOWLEDGE_TYPES = frozenset({KuType.CURRICULUM, KuType.MOC})
_CURRICULUM_STRUCTURE_TYPES = frozenset({KuType.LEARNING_STEP, KuType.LEARNING_PATH})
_CONTENT_PROCESSING_TYPES = frozenset({KuType.ASSIGNMENT, KuType.AI_REPORT, KuType.FEEDBACK_REPORT})
_ACTIVITY_TYPES = frozenset({
    KuType.TASK, KuType.GOAL, KuType.HABIT,
    KuType.EVENT, KuType.CHOICE, KuType.PRINCIPLE,
})
_SHARED_TYPES = frozenset({
    KuType.CURRICULUM, KuType.MOC,
    KuType.LEARNING_STEP, KuType.LEARNING_PATH,
})

_KU_TYPE_ALIASES: dict[str, KuType] = {
    # Canonical values
    "curriculum": KuType.CURRICULUM,
    "moc": KuType.MOC,
    "learning_step": KuType.LEARNING_STEP,
    "learning_path": KuType.LEARNING_PATH,
    "assignment": KuType.ASSIGNMENT,
    "ai_report": KuType.AI_REPORT,
    "feedback_report": KuType.FEEDBACK_REPORT,
    "task": KuType.TASK,
    "goal": KuType.GOAL,
    "habit": KuType.HABIT,
    "event": KuType.EVENT,
    "choice": KuType.CHOICE,
    "principle": KuType.PRINCIPLE,
    "life_path": KuType.LIFE_PATH,
    # Aliases
    "knowledge": KuType.CURRICULUM,
    "ku": KuType.CURRICULUM,
    "map_of_content": KuType.MOC,
    "ls": KuType.LEARNING_STEP,
    "step": KuType.LEARNING_STEP,
    "lp": KuType.LEARNING_PATH,
    "path": KuType.LEARNING_PATH,
    "report": KuType.ASSIGNMENT,
    "submission": KuType.ASSIGNMENT,
    "feedback": KuType.FEEDBACK_REPORT,
    "lifepath": KuType.LIFE_PATH,
}


# =============================================================================
# 2. PROCESSING LIFECYCLE
# =============================================================================


class KuStatus(str, Enum):
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
        return _KU_STATUS_DISPLAY_NAMES[self]

    def is_terminal(self) -> bool:
        """Check if this is a terminal (non-progressing) status."""
        return self in _TERMINAL_STATUSES

    def is_active(self) -> bool:
        """Check if this status indicates active work/processing."""
        return self in _ACTIVE_STATUSES

    def is_pending(self) -> bool:
        """Check if this status indicates pending/waiting state."""
        return self in {KuStatus.DRAFT, KuStatus.SUBMITTED, KuStatus.QUEUED, KuStatus.SCHEDULED}

    def can_transition_to(self, target: KuStatus, ku_type: KuType | None = None) -> bool:
        """
        Check if transition to target status is valid.

        When ku_type is provided, validates both:
        1. Target is a valid status for that KuType
        2. The transition itself is allowed

        When ku_type is None, only checks the general transition map.
        """
        if ku_type is not None:
            valid = ku_type.valid_statuses()
            if self not in valid or target not in valid:
                return False
        return target in _VALID_TRANSITIONS.get(self, set())


_KU_STATUS_DISPLAY_NAMES: dict[KuStatus, str] = {
    KuStatus.DRAFT: "Draft",
    KuStatus.SUBMITTED: "Submitted",
    KuStatus.QUEUED: "Queued",
    KuStatus.PROCESSING: "Processing",
    KuStatus.SCHEDULED: "Scheduled",
    KuStatus.ACTIVE: "Active",
    KuStatus.PAUSED: "Paused",
    KuStatus.BLOCKED: "Blocked",
    KuStatus.COMPLETED: "Completed",
    KuStatus.FAILED: "Failed",
    KuStatus.CANCELLED: "Cancelled",
    KuStatus.POSTPONED: "Postponed",
    KuStatus.REVISION_REQUESTED: "Revision Requested",
    KuStatus.ARCHIVED: "Archived",
}

_TERMINAL_STATUSES = frozenset({
    KuStatus.COMPLETED, KuStatus.FAILED,
    KuStatus.CANCELLED, KuStatus.ARCHIVED,
})

_ACTIVE_STATUSES = frozenset({
    KuStatus.SUBMITTED, KuStatus.QUEUED, KuStatus.PROCESSING,
    KuStatus.ACTIVE, KuStatus.SCHEDULED,
})

# General transition map — union of all valid transitions across all KuTypes.
# Type-specific validation is handled by can_transition_to() + valid_statuses().
_VALID_TRANSITIONS: dict[KuStatus, set[KuStatus]] = {
    KuStatus.DRAFT: {
        KuStatus.SUBMITTED, KuStatus.SCHEDULED, KuStatus.ACTIVE,
        KuStatus.COMPLETED, KuStatus.CANCELLED, KuStatus.ARCHIVED,
    },
    KuStatus.SUBMITTED: {
        KuStatus.QUEUED, KuStatus.PROCESSING, KuStatus.FAILED,
    },
    KuStatus.QUEUED: {
        KuStatus.PROCESSING, KuStatus.FAILED,
    },
    KuStatus.PROCESSING: {
        KuStatus.COMPLETED, KuStatus.FAILED,
    },
    KuStatus.SCHEDULED: {
        KuStatus.ACTIVE, KuStatus.COMPLETED,
        KuStatus.CANCELLED, KuStatus.POSTPONED,
    },
    KuStatus.ACTIVE: {
        KuStatus.PAUSED, KuStatus.BLOCKED, KuStatus.COMPLETED,
        KuStatus.CANCELLED, KuStatus.FAILED, KuStatus.ARCHIVED,
    },
    KuStatus.PAUSED: {
        KuStatus.ACTIVE, KuStatus.CANCELLED, KuStatus.ARCHIVED,
    },
    KuStatus.BLOCKED: {
        KuStatus.ACTIVE, KuStatus.CANCELLED,
    },
    KuStatus.COMPLETED: {
        KuStatus.REVISION_REQUESTED, KuStatus.ARCHIVED,
    },
    KuStatus.FAILED: {
        KuStatus.DRAFT, KuStatus.CANCELLED, KuStatus.ARCHIVED,
    },
    KuStatus.CANCELLED: {
        KuStatus.ARCHIVED,
    },
    KuStatus.POSTPONED: {
        KuStatus.DRAFT, KuStatus.SCHEDULED, KuStatus.CANCELLED,
    },
    KuStatus.REVISION_REQUESTED: {
        KuStatus.DRAFT, KuStatus.ARCHIVED,
    },
    KuStatus.ARCHIVED: set(),
}

# Valid statuses per KuType (from plan specification)
_VALID_STATUSES_BY_TYPE: dict[KuType, frozenset[KuStatus]] = {
    KuType.CURRICULUM: frozenset({
        KuStatus.DRAFT, KuStatus.COMPLETED, KuStatus.ARCHIVED,
    }),
    KuType.MOC: frozenset({
        KuStatus.DRAFT, KuStatus.COMPLETED, KuStatus.ARCHIVED,
    }),
    KuType.LEARNING_STEP: frozenset({
        KuStatus.DRAFT, KuStatus.ACTIVE, KuStatus.COMPLETED, KuStatus.ARCHIVED,
    }),
    KuType.LEARNING_PATH: frozenset({
        KuStatus.DRAFT, KuStatus.ACTIVE, KuStatus.COMPLETED, KuStatus.ARCHIVED,
    }),
    KuType.ASSIGNMENT: frozenset({
        KuStatus.DRAFT, KuStatus.SUBMITTED, KuStatus.QUEUED,
        KuStatus.PROCESSING, KuStatus.COMPLETED, KuStatus.FAILED,
        KuStatus.REVISION_REQUESTED, KuStatus.ARCHIVED,
    }),
    KuType.AI_REPORT: frozenset({
        KuStatus.DRAFT, KuStatus.PROCESSING, KuStatus.COMPLETED,
        KuStatus.FAILED, KuStatus.ARCHIVED,
    }),
    KuType.FEEDBACK_REPORT: frozenset({
        KuStatus.DRAFT, KuStatus.COMPLETED, KuStatus.ARCHIVED,
    }),
    KuType.TASK: frozenset({
        KuStatus.DRAFT, KuStatus.SCHEDULED, KuStatus.ACTIVE,
        KuStatus.PAUSED, KuStatus.BLOCKED, KuStatus.COMPLETED,
        KuStatus.CANCELLED, KuStatus.POSTPONED, KuStatus.FAILED,
    }),
    KuType.GOAL: frozenset({
        KuStatus.DRAFT, KuStatus.ACTIVE, KuStatus.PAUSED,
        KuStatus.COMPLETED, KuStatus.CANCELLED, KuStatus.FAILED,
        KuStatus.ARCHIVED,
    }),
    KuType.HABIT: frozenset({
        KuStatus.ACTIVE, KuStatus.PAUSED, KuStatus.COMPLETED,
        KuStatus.CANCELLED, KuStatus.ARCHIVED,
    }),
    KuType.EVENT: frozenset({
        KuStatus.SCHEDULED, KuStatus.ACTIVE, KuStatus.COMPLETED,
        KuStatus.CANCELLED,
    }),
    KuType.CHOICE: frozenset({
        KuStatus.DRAFT, KuStatus.ACTIVE, KuStatus.COMPLETED,
        KuStatus.ARCHIVED,
    }),
    KuType.PRINCIPLE: frozenset({
        KuStatus.ACTIVE, KuStatus.PAUSED, KuStatus.ARCHIVED,
    }),
    KuType.LIFE_PATH: frozenset({
        KuStatus.ACTIVE, KuStatus.ARCHIVED,
    }),
}

_DEFAULT_STATUS_BY_TYPE: dict[KuType, KuStatus] = {
    KuType.CURRICULUM: KuStatus.COMPLETED,
    KuType.MOC: KuStatus.COMPLETED,
    KuType.LEARNING_STEP: KuStatus.DRAFT,
    KuType.LEARNING_PATH: KuStatus.DRAFT,
    KuType.ASSIGNMENT: KuStatus.DRAFT,
    KuType.AI_REPORT: KuStatus.DRAFT,
    KuType.FEEDBACK_REPORT: KuStatus.DRAFT,
    KuType.TASK: KuStatus.DRAFT,
    KuType.GOAL: KuStatus.DRAFT,
    KuType.HABIT: KuStatus.ACTIVE,
    KuType.EVENT: KuStatus.SCHEDULED,
    KuType.CHOICE: KuStatus.DRAFT,
    KuType.PRINCIPLE: KuStatus.ACTIVE,
    KuType.LIFE_PATH: KuStatus.ACTIVE,
}


class ProcessorType(str, Enum):
    """
    Type of processor used for Ku content processing.

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
# 3. PROJECT / ASSIGNMENT
# =============================================================================


class ProjectScope(str, Enum):
    """
    Scope of a KuProject (instruction template).

    PERSONAL: User's own AI feedback template (default)
    ASSIGNED: Teacher-created, assigned to a group (ADR-040)
    """

    PERSONAL = "personal"
    ASSIGNED = "assigned"


# =============================================================================
# 4. JOURNAL PROCESSING
# =============================================================================


class JournalType(str, Enum):
    """
    Journal retention tiers.

    Two-tier journal system:
    - VOICE (PJ1): Ephemeral voice journals, max 3 stored, audio source
    - CURATED (PJ2): Permanent curated text/markdown journals
    """

    VOICE = "voice"
    CURATED = "curated"

    def is_ephemeral(self) -> bool:
        """Check if this type has auto-cleanup (max retention limit)."""
        return self == JournalType.VOICE

    def max_retention_count(self) -> int | None:
        """
        Return max retention count for ephemeral types, None for permanent.

        VOICE journals have FIFO cleanup - only most recent 3 are kept.
        CURATED journals are permanent (no limit).
        """
        if self == JournalType.VOICE:
            return 3
        return None

    def get_display_name(self) -> str:
        """Get human-readable display name."""
        return {
            JournalType.VOICE: "Voice Journal",
            JournalType.CURATED: "Curated Journal",
        }[self]


class JournalCategory(str, Enum):
    """Categories for journal entries."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    REFLECTION = "reflection"
    GRATITUDE = "gratitude"
    GOALS = "goals"
    IDEAS = "ideas"
    DREAMS = "dreams"
    HEALTH = "health"
    WORK = "work"
    PERSONAL = "personal"
    LEARNING = "learning"
    PROJECT = "project"
    OTHER = "other"


class JournalMode(str, Enum):
    """
    Journal processing modes — determines output formatting strategy.

    Typical journal: 80% one mode + 20% mixed.
    System infers weights via LLM, user can override.

    ACTIVITY_TRACKING: Focus on extracting actionable entities
    IDEA_ARTICULATION: Focus on preserving original thought
    CRITICAL_THINKING: Focus on question exploration
    """

    ACTIVITY_TRACKING = "activity_tracking"
    IDEA_ARTICULATION = "idea_articulation"
    CRITICAL_THINKING = "critical_thinking"

    def get_display_name(self) -> str:
        """Get human-readable display name."""
        return {
            JournalMode.ACTIVITY_TRACKING: "Activity Tracking",
            JournalMode.IDEA_ARTICULATION: "Idea Articulation",
            JournalMode.CRITICAL_THINKING: "Critical Thinking",
        }[self]

    def get_description(self) -> str:
        """Get mode description for UI/help text."""
        return {
            JournalMode.ACTIVITY_TRACKING: "Extract tasks, goals, habits from your reflections",
            JournalMode.IDEA_ARTICULATION: "Preserve your ideas with minimal processing",
            JournalMode.CRITICAL_THINKING: "Organize your thoughts around questions",
        }[self]


# =============================================================================
# 5. LLM PROCESSING
# =============================================================================


class FormattingStyle(str, Enum):
    """Style for formatting transcripts during LLM processing."""

    STRUCTURED = "structured"
    NARRATIVE = "narrative"
    BULLET_POINTS = "bullet_points"
    CONVERSATIONAL = "conversational"
    EXECUTIVE_SUMMARY = "executive_summary"


class AnalysisDepth(str, Enum):
    """Depth of analysis for transcript processing."""

    BASIC = "basic"
    DETAILED = "detailed"
    COMPREHENSIVE = "comprehensive"


class ContextEnrichmentLevel(str, Enum):
    """Level of SKUEL enterprise context integration."""

    NONE = "none"
    BASIC = "basic"
    STANDARD = "standard"
    DEEP = "deep"


# =============================================================================
# 6. SCHEDULE
# =============================================================================


class ScheduleType(str, Enum):
    """Frequency of progress Ku generation."""

    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"

    def get_display_name(self) -> str:
        """Get human-readable display name."""
        return {
            ScheduleType.WEEKLY: "Weekly",
            ScheduleType.BIWEEKLY: "Every 2 Weeks",
            ScheduleType.MONTHLY: "Monthly",
        }[self]


class ProgressDepth(str, Enum):
    """Level of detail in generated progress Ku."""

    SUMMARY = "summary"
    STANDARD = "standard"
    DETAILED = "detailed"

    def get_display_name(self) -> str:
        """Get human-readable display name."""
        return {
            ProgressDepth.SUMMARY: "Summary (counts only)",
            ProgressDepth.STANDARD: "Standard (counts + examples)",
            ProgressDepth.DETAILED: "Detailed (full breakdown)",
        }[self]


# =============================================================================
# 7. GOAL
# =============================================================================


class GoalType(str, Enum):
    """
    Classification of goal by nature.

    Determines measurement strategy and progress tracking approach.
    """

    OUTCOME = "outcome"
    PROCESS = "process"
    LEARNING = "learning"
    PROJECT = "project"
    MILESTONE = "milestone"
    MASTERY = "mastery"


class GoalTimeframe(str, Enum):
    """
    Expected duration/timeframe for goal achievement.

    Used for scheduling, priority calculation, and progress pacing.
    """

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    MULTI_YEAR = "multi_year"


class MeasurementType(str, Enum):
    """
    How goal progress is measured.

    Determines the progress tracking UI and calculation method.
    """

    BINARY = "binary"
    PERCENTAGE = "percentage"
    NUMERIC = "numeric"
    MILESTONE = "milestone"
    HABIT_BASED = "habit_based"
    KNOWLEDGE_BASED = "knowledge_based"
    TASK_BASED = "task_based"
    MIXED = "mixed"


class HabitEssentiality(str, Enum):
    """
    Classification of habit importance to goal achievement.

    Based on James Clear's Atomic Habits philosophy:
    "You do not rise to the level of your goals.
     You fall to the level of your systems."
    """

    ESSENTIAL = "essential"
    CRITICAL = "critical"
    SUPPORTING = "supporting"
    OPTIONAL = "optional"


# =============================================================================
# 8. HABIT
# =============================================================================


class HabitPolarity(str, Enum):
    """
    Direction of habit change.

    BUILD: Creating a new positive habit
    BREAK: Eliminating a negative habit
    NEUTRAL: Tracking without direction
    """

    BUILD = "build"
    BREAK = "break"
    NEUTRAL = "neutral"


class HabitCategory(str, Enum):
    """Category classification for habits."""

    HEALTH = "health"
    FITNESS = "fitness"
    MINDFULNESS = "mindfulness"
    LEARNING = "learning"
    PRODUCTIVITY = "productivity"
    CREATIVE = "creative"
    SOCIAL = "social"
    FINANCIAL = "financial"
    OTHER = "other"


class HabitDifficulty(str, Enum):
    """Difficulty level of maintaining a habit."""

    TRIVIAL = "trivial"
    EASY = "easy"
    MODERATE = "moderate"
    CHALLENGING = "challenging"
    HARD = "hard"


# =============================================================================
# 9. CHOICE
# =============================================================================


class ChoiceType(str, Enum):
    """
    Type of decision being made.

    Determines the decision framework and option evaluation approach.
    """

    BINARY = "binary"
    MULTIPLE = "multiple"
    RANKING = "ranking"
    ALLOCATION = "allocation"
    STRATEGIC = "strategic"
    OPERATIONAL = "operational"


# =============================================================================
# 10. PRINCIPLE
# =============================================================================


class PrincipleCategory(str, Enum):
    """Life domain classification for principles."""

    SPIRITUAL = "spiritual"
    ETHICAL = "ethical"
    RELATIONAL = "relational"
    PERSONAL = "personal"
    PROFESSIONAL = "professional"
    INTELLECTUAL = "intellectual"
    HEALTH = "health"
    CREATIVE = "creative"


class PrincipleSource(str, Enum):
    """Origin/tradition of a principle."""

    PHILOSOPHICAL = "philosophical"
    RELIGIOUS = "religious"
    CULTURAL = "cultural"
    PERSONAL = "personal"
    SCIENTIFIC = "scientific"
    MENTOR = "mentor"
    LITERATURE = "literature"


class PrincipleStrength(str, Enum):
    """How deeply held/practiced a principle is."""

    CORE = "core"
    STRONG = "strong"
    MODERATE = "moderate"
    DEVELOPING = "developing"
    EXPLORING = "exploring"


# =============================================================================
# 11. ALIGNMENT (unified — principles + life path)
# =============================================================================


class AlignmentLevel(str, Enum):
    """
    Alignment measurement for principles and life path.

    Unified spectrum from FLOURISHING (highest) to UNKNOWN (unassessed).

    Used by:
        Principles: current_alignment, alignment_history[].alignment_level
        Life Path: alignment_level (overall life direction alignment)
    """

    FLOURISHING = "flourishing"
    ALIGNED = "aligned"
    MOSTLY_ALIGNED = "mostly_aligned"
    EXPLORING = "exploring"
    PARTIAL = "partial"
    DRIFTING = "drifting"
    MISALIGNED = "misaligned"
    UNKNOWN = "unknown"

    def to_score(self) -> float:
        """Convert alignment level to numeric score (0.0-1.0)."""
        return _ALIGNMENT_SCORES[self]

    @classmethod
    def from_score(cls, score: float) -> AlignmentLevel:
        """Derive alignment level from numeric score."""
        if score >= 0.9:
            return cls.FLOURISHING
        if score >= 0.75:
            return cls.ALIGNED
        if score >= 0.6:
            return cls.MOSTLY_ALIGNED
        if score >= 0.45:
            return cls.EXPLORING
        if score >= 0.3:
            return cls.PARTIAL
        if score >= 0.15:
            return cls.DRIFTING
        if score >= 0.0:
            return cls.MISALIGNED
        return cls.UNKNOWN


_ALIGNMENT_SCORES: dict[AlignmentLevel, float] = {
    AlignmentLevel.FLOURISHING: 1.0,
    AlignmentLevel.ALIGNED: 0.85,
    AlignmentLevel.MOSTLY_ALIGNED: 0.7,
    AlignmentLevel.EXPLORING: 0.5,
    AlignmentLevel.PARTIAL: 0.35,
    AlignmentLevel.DRIFTING: 0.2,
    AlignmentLevel.MISALIGNED: 0.1,
    AlignmentLevel.UNKNOWN: 0.0,
}


# =============================================================================
# 12. CURRICULUM STRUCTURE
# =============================================================================


class LpType(str, Enum):
    """
    Type of Learning Path.

    Determines path behavior: adaptive vs. fixed, exploratory vs. directed.
    """

    STRUCTURED = "structured"
    ADAPTIVE = "adaptive"
    EXPLORATORY = "exploratory"
    REMEDIAL = "remedial"
    ACCELERATED = "accelerated"


class StepDifficulty(str, Enum):
    """Difficulty level of a learning step."""

    TRIVIAL = "trivial"
    EASY = "easy"
    MODERATE = "moderate"
    CHALLENGING = "challenging"
    ADVANCED = "advanced"
