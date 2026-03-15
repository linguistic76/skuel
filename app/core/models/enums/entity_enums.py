"""
Entity Enums - Core Identity, Lifecycle, and Domain Classification
===================================================================

Core enums for entity type discrimination, processing lifecycle,
content origin, and domain classification.

Organized in 5 sections:
1. Core Identity: EntityType (21 values + 3 deprecated), ContentOrigin (4 tiers)
2. Processing Lifecycle: EntityStatus (14 values), ProcessorType (4 values)
3. Domain Classification: Domain, NonKuDomain, DomainIdentifier
4. Analytics: AnalyticsDomain
5. Access Control: ContentScope, Context
"""

from __future__ import annotations

from enum import StrEnum

# =============================================================================
# 1. CORE IDENTITY
# =============================================================================


class EntityType(StrEnum):
    """
    Type of Entity — 21 entity types in SKUEL.

    Discriminator for the `entity_type` field on Entity.

    Entity types (alphabetical):
        ACTIVITY_REPORT      → AI/human feedback about activity patterns
        CHOICE               → Knowledge about decisions you make
        EVENT                → Knowledge about what you attend
        EXERCISE             → Instruction template for practicing curriculum
        EXERCISE_REPORT      → Teacher or AI report on an exercise submission
        EXERCISE_SUBMISSION  → Student-uploaded work against an Exercise
        FORM_SUBMISSION      → User response to a FormTemplate
        FORM_TEMPLATE        → General-purpose form definition (admin-created)
        GOAL                 → Knowledge about where you're heading
        HABIT                → Knowledge about what you practice
        JOURNAL_REPORT       → AI-generated report on a journal submission
        JOURNAL_SUBMISSION   → Voice or text journal entry (user's own reflections)
        KU                   → Atomic knowledge unit (concept, state, principle)
        LEARNING_PATH        → Ordered sequence of steps
        LESSON               → A unit for learning
        LEARNING_STEP        → A collection of lessons
        LIFE_PATH            → Knowledge about your life direction
        PRINCIPLE            → Knowledge about what you believe
        RESOURCE             → Books, talks, films, music (admin-only)
        REVISED_EXERCISE     → Targeted revision instructions after feedback
        TASK                 → Knowledge about what needs doing

    Any Lesson can organize other Lessons via ORGANIZES relationships (emergent
    identity — no separate MOC type needed).

    Content origin tiers (see ContentOrigin):
        A  CURATED      → RESOURCE
        B  CURRICULUM   → LESSON, KU, LEARNING_STEP, LEARNING_PATH, EXERCISE, REVISED_EXERCISE
        C  USER_CREATED → Activities (6), EXERCISE_SUBMISSION, JOURNAL_SUBMISSION, LIFE_PATH,
                          FORM_SUBMISSION
        D  REPORT       → ACTIVITY_REPORT, EXERCISE_REPORT, JOURNAL_REPORT

    Ownership rules:
        Curriculum (Lesson, KU, LS, LP, Exercise) + Resource + FormTemplate: user_uid = None (shared content, admin-created)
        Content processing:    user_uid = student/teacher (user-owned)
        Activity (6):          user_uid = student (user-owned)
        Destination:           user_uid = student (user-owned)
        FormSubmission:        user_uid = student (user-owned)
    """

    # Curriculum (admin-created, shared)
    LESSON = "lesson"
    KU = "ku"
    LEARNING_STEP = "learning_step"
    LEARNING_PATH = "learning_path"
    EXERCISE = "exercise"

    # Revision cycle (teacher-owned, student-targeted)
    REVISED_EXERCISE = "revised_exercise"

    # General-purpose forms (admin-created template, user-owned submissions)
    FORM_TEMPLATE = "form_template"
    FORM_SUBMISSION = "form_submission"

    # Curated external content (admin-created, shared)
    RESOURCE = "resource"

    # Content processing (user-owned, derivation chain)
    EXERCISE_SUBMISSION = "exercise_submission"
    JOURNAL_SUBMISSION = "journal_submission"
    ACTIVITY_REPORT = "activity_report"
    EXERCISE_REPORT = "exercise_report"
    JOURNAL_REPORT = "journal_report"

    # Deprecated aliases — use EXERCISE_SUBMISSION, JOURNAL_SUBMISSION, EXERCISE_REPORT, LESSON
    SUBMISSION = "submission"  # deprecated: use EXERCISE_SUBMISSION
    JOURNAL = "journal"  # deprecated: use JOURNAL_SUBMISSION
    SUBMISSION_REPORT = "submission_report"  # deprecated: use EXERCISE_REPORT
    ARTICLE = "lesson"  # deprecated: use LESSON

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
        return _ENTITY_TYPE_DISPLAY_NAMES[self]

    # -------------------------------------------------------------------------
    # Group classification
    # -------------------------------------------------------------------------

    def is_knowledge(self) -> bool:
        """Check if this is curriculum knowledge content (Lesson or Ku)."""
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
            EntityType.EXERCISE_SUBMISSION,
            EntityType.JOURNAL_SUBMISSION,
            EntityType.FORM_SUBMISSION,
            EntityType.ACTIVITY_REPORT,
            EntityType.EXERCISE_REPORT,
            EntityType.JOURNAL_REPORT,
            EntityType.REVISED_EXERCISE,
            # Deprecated aliases
            EntityType.SUBMISSION,
            EntityType.JOURNAL,
            EntityType.SUBMISSION_REPORT,
        }

    def is_processable(self) -> bool:
        """Check if this EntityType goes through a processing pipeline."""
        return self in {
            EntityType.EXERCISE_SUBMISSION,
            EntityType.JOURNAL_SUBMISSION,
            EntityType.ACTIVITY_REPORT,
            # Deprecated aliases
            EntityType.SUBMISSION,
            EntityType.JOURNAL,
        }

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
            "ku" -> KU (canonical)
            "knowledge" -> LESSON
            "ls" -> LEARNING_STEP
            "lp" -> LEARNING_PATH
            "submission_report" -> EXERCISE_REPORT
        """
        normalized = text.strip().lower().replace("-", "_").replace(" ", "_")
        return _ENTITY_TYPE_ALIASES.get(normalized)


# EntityType lookup tables (module-level for performance)
_ENTITY_TYPE_DISPLAY_NAMES: dict[EntityType, str] = {
    EntityType.LESSON: "Lesson",
    EntityType.KU: "Knowledge Unit",
    EntityType.RESOURCE: "Resource",
    EntityType.LEARNING_STEP: "Learning Step",
    EntityType.LEARNING_PATH: "Learning Path",
    EntityType.EXERCISE_SUBMISSION: "Exercise Submission",
    EntityType.JOURNAL_SUBMISSION: "Journal",
    EntityType.ACTIVITY_REPORT: "Activity Report",
    EntityType.EXERCISE_REPORT: "Exercise Report",
    EntityType.JOURNAL_REPORT: "Journal Report",
    EntityType.TASK: "Task",
    EntityType.GOAL: "Goal",
    EntityType.HABIT: "Habit",
    EntityType.EVENT: "Event",
    EntityType.CHOICE: "Choice",
    EntityType.PRINCIPLE: "Principle",
    EntityType.EXERCISE: "Exercise",
    EntityType.REVISED_EXERCISE: "Revised Exercise",
    EntityType.FORM_TEMPLATE: "Form Template",
    EntityType.FORM_SUBMISSION: "Form Submission",
    EntityType.LIFE_PATH: "Life Path",
    # Deprecated aliases
    EntityType.SUBMISSION: "Submission",
    EntityType.JOURNAL: "Journal",
    EntityType.SUBMISSION_REPORT: "Submission Report",
}

_KNOWLEDGE_TYPES = frozenset({EntityType.LESSON, EntityType.KU})
_CURRICULUM_STRUCTURE_TYPES = frozenset(
    {EntityType.LEARNING_STEP, EntityType.LEARNING_PATH, EntityType.EXERCISE}
)
_CONTENT_PROCESSING_TYPES = frozenset(
    {
        EntityType.EXERCISE_SUBMISSION,
        EntityType.JOURNAL_SUBMISSION,
        EntityType.ACTIVITY_REPORT,
        EntityType.EXERCISE_REPORT,
        EntityType.JOURNAL_REPORT,
        # Deprecated aliases
        EntityType.SUBMISSION,
        EntityType.JOURNAL,
        EntityType.SUBMISSION_REPORT,
    }
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
        EntityType.LESSON,
        EntityType.KU,
        EntityType.RESOURCE,
        EntityType.LEARNING_STEP,
        EntityType.LEARNING_PATH,
        EntityType.EXERCISE,
        EntityType.FORM_TEMPLATE,
    }
)


class ContentOrigin(StrEnum):
    """
    Content origin tier — classifies KuTypes by where content comes from
    and what role it plays in the system.

    Four tiers:
        CURATED      (A) → Admin-curated resources, used by Askesis
        CURRICULUM   (B) → Curriculum structure and organization
        USER_CREATED (C) → User-generated content (activities, submissions, journals)
        REPORT       (D) → Reports/assessments that act on user content
    """

    CURATED = "curated"
    CURRICULUM = "curriculum"
    USER_CREATED = "user_created"
    REPORT = "report"


_CONTENT_ORIGIN_BY_TYPE: dict[EntityType, ContentOrigin] = {
    # A — Admin-curated resources
    EntityType.RESOURCE: ContentOrigin.CURATED,
    EntityType.FORM_TEMPLATE: ContentOrigin.CURATED,
    # B — Curriculum structure and organization
    EntityType.LESSON: ContentOrigin.CURRICULUM,
    EntityType.KU: ContentOrigin.CURRICULUM,
    EntityType.LEARNING_STEP: ContentOrigin.CURRICULUM,
    EntityType.LEARNING_PATH: ContentOrigin.CURRICULUM,
    EntityType.EXERCISE: ContentOrigin.CURRICULUM,
    EntityType.REVISED_EXERCISE: ContentOrigin.CURRICULUM,
    # C — User-generated content
    EntityType.TASK: ContentOrigin.USER_CREATED,
    EntityType.GOAL: ContentOrigin.USER_CREATED,
    EntityType.HABIT: ContentOrigin.USER_CREATED,
    EntityType.EVENT: ContentOrigin.USER_CREATED,
    EntityType.CHOICE: ContentOrigin.USER_CREATED,
    EntityType.PRINCIPLE: ContentOrigin.USER_CREATED,
    EntityType.EXERCISE_SUBMISSION: ContentOrigin.USER_CREATED,
    EntityType.JOURNAL_SUBMISSION: ContentOrigin.USER_CREATED,
    EntityType.FORM_SUBMISSION: ContentOrigin.USER_CREATED,
    EntityType.LIFE_PATH: ContentOrigin.USER_CREATED,
    # Deprecated aliases
    EntityType.SUBMISSION: ContentOrigin.USER_CREATED,
    EntityType.JOURNAL: ContentOrigin.USER_CREATED,
    # D — Reports that act on user content
    EntityType.ACTIVITY_REPORT: ContentOrigin.REPORT,
    EntityType.EXERCISE_REPORT: ContentOrigin.REPORT,
    EntityType.JOURNAL_REPORT: ContentOrigin.REPORT,
    # Deprecated alias
    EntityType.SUBMISSION_REPORT: ContentOrigin.REPORT,
}

_ENTITY_TYPE_ALIASES: dict[str, EntityType] = {
    # Canonical values
    "lesson": EntityType.LESSON,
    "ku": EntityType.KU,
    "resource": EntityType.RESOURCE,
    "learning_step": EntityType.LEARNING_STEP,
    "learning_path": EntityType.LEARNING_PATH,
    "exercise_submission": EntityType.EXERCISE_SUBMISSION,
    "journal_submission": EntityType.JOURNAL_SUBMISSION,
    "activity_report": EntityType.ACTIVITY_REPORT,
    "exercise_report": EntityType.EXERCISE_REPORT,
    "journal_report": EntityType.JOURNAL_REPORT,
    "task": EntityType.TASK,
    "goal": EntityType.GOAL,
    "habit": EntityType.HABIT,
    "event": EntityType.EVENT,
    "choice": EntityType.CHOICE,
    "principle": EntityType.PRINCIPLE,
    "life_path": EntityType.LIFE_PATH,
    # Backward-compat aliases (deprecated entity type values)
    "submission": EntityType.EXERCISE_SUBMISSION,
    "journal": EntityType.JOURNAL_SUBMISSION,
    "submission_report": EntityType.EXERCISE_REPORT,
    "submission_feedback": EntityType.EXERCISE_REPORT,  # pre-rename compat
    # Aliases
    "knowledge": EntityType.LESSON,
    "moc": EntityType.LESSON,
    "map_of_content": EntityType.LESSON,
    "book": EntityType.RESOURCE,
    "film": EntityType.RESOURCE,
    "talk": EntityType.RESOURCE,
    "ls": EntityType.LEARNING_STEP,
    "step": EntityType.LEARNING_STEP,
    "lp": EntityType.LEARNING_PATH,
    "path": EntityType.LEARNING_PATH,
    "exercise": EntityType.EXERCISE,
    "revised_exercise": EntityType.REVISED_EXERCISE,
    "form_template": EntityType.FORM_TEMPLATE,
    "form_submission": EntityType.FORM_SUBMISSION,
    "form": EntityType.FORM_TEMPLATE,
    "assignment": EntityType.EXERCISE,
    "feedback": EntityType.EXERCISE_REPORT,
    "revised_ex": EntityType.REVISED_EXERCISE,
    "lifepath": EntityType.LIFE_PATH,
}


# =============================================================================
# 2. PROCESSING LIFECYCLE
# =============================================================================


class EntityStatus(StrEnum):
    """
    Processing lifecycle status for an Entity.

    14 values covering all lifecycle patterns across all EntityTypes.

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

    Use `can_transition_to(target, entity_type)` for type-aware validation.
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

    def get_badge_class(self) -> str:
        """Get Tailwind badge classes for status display."""
        return _ENTITY_STATUS_BADGE_CLASSES.get(self, "bg-gray-100 text-gray-600 border-gray-200")

    def get_text_class(self) -> str:
        """Get Tailwind text color class for status display."""
        return _ENTITY_STATUS_TEXT_CLASSES.get(self, "text-muted-foreground")

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

    def can_transition_to(
        self, target: EntityStatus, entity_type: EntityType | None = None
    ) -> bool:
        """
        Check if transition to target status is valid.

        When entity_type is provided, validates both:
        1. Target is a valid status for that EntityType
        2. The transition itself is allowed

        When entity_type is None, only checks the general transition map.
        """
        if entity_type is not None:
            valid = entity_type.valid_statuses()
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

_ENTITY_STATUS_BADGE_CLASSES: dict[EntityStatus, str] = {
    EntityStatus.ACTIVE: "bg-green-100 text-green-800 border-green-200",
    EntityStatus.COMPLETED: "bg-green-100 text-green-800 border-green-200",
    EntityStatus.PAUSED: "bg-yellow-100 text-yellow-800 border-yellow-200",
    EntityStatus.SCHEDULED: "bg-blue-100 text-blue-800 border-blue-200",
    EntityStatus.BLOCKED: "bg-red-100 text-red-800 border-red-200",
    EntityStatus.CANCELLED: "bg-red-100 text-red-800 border-red-200",
    EntityStatus.FAILED: "bg-red-100 text-red-800 border-red-200",
    EntityStatus.ARCHIVED: "bg-gray-100 text-gray-600 border-gray-200",
    EntityStatus.DRAFT: "bg-gray-100 text-gray-600 border-gray-200",
    EntityStatus.POSTPONED: "bg-yellow-100 text-yellow-800 border-yellow-200",
    EntityStatus.SUBMITTED: "bg-yellow-100 text-yellow-800 border-yellow-200",
    EntityStatus.QUEUED: "bg-yellow-100 text-yellow-800 border-yellow-200",
    EntityStatus.PROCESSING: "bg-blue-100 text-blue-800 border-blue-200",
    EntityStatus.REVISION_REQUESTED: "bg-yellow-100 text-yellow-800 border-yellow-200",
}

_ENTITY_STATUS_TEXT_CLASSES: dict[EntityStatus, str] = {
    EntityStatus.COMPLETED: "text-green-600",
    EntityStatus.ACTIVE: "text-green-600",
    EntityStatus.PAUSED: "text-yellow-600",
    EntityStatus.BLOCKED: "text-red-600",
    EntityStatus.FAILED: "text-red-600",
    EntityStatus.SCHEDULED: "text-blue-600",
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
    EntityType.LESSON: frozenset(
        {
            EntityStatus.DRAFT,
            EntityStatus.COMPLETED,
            EntityStatus.ARCHIVED,
        }
    ),
    EntityType.KU: frozenset(
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
    EntityType.EXERCISE_SUBMISSION: frozenset(
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
    EntityType.JOURNAL_SUBMISSION: frozenset(
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
    EntityType.ACTIVITY_REPORT: frozenset(
        {
            EntityStatus.DRAFT,
            EntityStatus.PROCESSING,
            EntityStatus.COMPLETED,
            EntityStatus.FAILED,
            EntityStatus.ARCHIVED,
        }
    ),
    EntityType.EXERCISE_REPORT: frozenset(
        {
            EntityStatus.DRAFT,
            EntityStatus.COMPLETED,
            EntityStatus.ARCHIVED,
        }
    ),
    EntityType.JOURNAL_REPORT: frozenset(
        {
            EntityStatus.DRAFT,
            EntityStatus.COMPLETED,
            EntityStatus.ARCHIVED,
        }
    ),
    # Deprecated aliases
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
    EntityType.SUBMISSION_REPORT: frozenset(
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
    EntityType.REVISED_EXERCISE: frozenset(
        {
            EntityStatus.DRAFT,
            EntityStatus.ACTIVE,
            EntityStatus.COMPLETED,
            EntityStatus.ARCHIVED,
        }
    ),
    EntityType.FORM_TEMPLATE: frozenset(
        {
            EntityStatus.DRAFT,
            EntityStatus.ACTIVE,
            EntityStatus.COMPLETED,
            EntityStatus.ARCHIVED,
        }
    ),
    EntityType.FORM_SUBMISSION: frozenset(
        {
            EntityStatus.DRAFT,
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
    EntityType.LESSON: EntityStatus.COMPLETED,
    EntityType.KU: EntityStatus.COMPLETED,
    EntityType.RESOURCE: EntityStatus.COMPLETED,
    EntityType.LEARNING_STEP: EntityStatus.DRAFT,
    EntityType.LEARNING_PATH: EntityStatus.DRAFT,
    EntityType.EXERCISE: EntityStatus.DRAFT,
    EntityType.REVISED_EXERCISE: EntityStatus.DRAFT,
    EntityType.EXERCISE_SUBMISSION: EntityStatus.DRAFT,
    EntityType.JOURNAL_SUBMISSION: EntityStatus.DRAFT,
    EntityType.ACTIVITY_REPORT: EntityStatus.DRAFT,
    EntityType.EXERCISE_REPORT: EntityStatus.DRAFT,
    EntityType.JOURNAL_REPORT: EntityStatus.DRAFT,
    # Deprecated aliases
    EntityType.SUBMISSION: EntityStatus.DRAFT,
    EntityType.JOURNAL: EntityStatus.DRAFT,
    EntityType.SUBMISSION_REPORT: EntityStatus.DRAFT,
    EntityType.TASK: EntityStatus.DRAFT,
    EntityType.GOAL: EntityStatus.DRAFT,
    EntityType.HABIT: EntityStatus.ACTIVE,
    EntityType.EVENT: EntityStatus.SCHEDULED,
    EntityType.CHOICE: EntityStatus.DRAFT,
    EntityType.PRINCIPLE: EntityStatus.ACTIVE,
    EntityType.FORM_TEMPLATE: EntityStatus.DRAFT,
    EntityType.FORM_SUBMISSION: EntityStatus.COMPLETED,
    EntityType.LIFE_PATH: EntityStatus.ACTIVE,
}


class ProcessorType(StrEnum):
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


class Domain(StrEnum):
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


class NonKuDomain(StrEnum):
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
# EntityType covers all 18 entity types; NonKuDomain covers the 4 non-entity domains.
DomainIdentifier = EntityType | NonKuDomain


# =============================================================================
# 4. ANALYTICS
# =============================================================================


class AnalyticsDomain(StrEnum):
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


class ContentScope(StrEnum):
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


class Context(StrEnum):
    """Context where activity can be performed"""

    HOME = "home"
    WORK = "work"
    COMPUTER = "computer"
    PHONE = "phone"
    ERRANDS = "errands"
    ANYWHERE = "anywhere"
