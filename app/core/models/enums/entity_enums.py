"""
Entity Enums - Core Identity, Lifecycle, and Domain Classification
===================================================================

Core enums for entity type discrimination, processing lifecycle,
content origin, and domain classification.

Organized in 4 sections:
1. Core Identity: EntityType, ContentOrigin (4 tiers)
2. Processing Lifecycle: EntityStatus
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
    Type of Entity — 25 entity types in SKUEL.

    Discriminator for the `entity_type` field on Entity.

    Entity types (alphabetical):
        ACTIVITY_REPORT      → AI/human feedback about activity patterns
        CHOICE               → Knowledge about decisions you make
        CHOICE_TEMPLATE      → PS-owned template that spawns Choice instances on engagement
        ENTRY_REPORT         → Teacher or AI report on an exercise submission
        EVENT                → Knowledge about what you attend
        EVENT_TEMPLATE       → PS-owned template that spawns Event instances on engagement
        EXERCISE             → Instruction template for practicing curriculum
        FORM_SUBMISSION      → User response to a FormTemplate
        FORM_TEMPLATE        → General-purpose form definition (admin-created)
        GOAL                 → Knowledge about where you're heading
        GOAL_TEMPLATE        → PS-owned template that spawns Goal instances on engagement
        HABIT                → Knowledge about what you practice
        HABIT_TEMPLATE       → PS-owned template that spawns Habit instances on engagement
        INTERACTION          → Situated learning-loop event (User Interaction Contract)
        KU                   → Atomic knowledge unit (concept, state, principle)
        LEARNING_PATH        → Ordered sequence of path steps
        LIFE_PATH            → Knowledge about your life direction
        PATH_STEP            → THE curriculum content entity (composes Kus, sits in learning paths)
        PRINCIPLE            → Knowledge about what you believe
        PRINCIPLE_TEMPLATE   → PS-owned template that spawns Principle instances on engagement
        RESOURCE             → Books, talks, films, music (admin-only)
        REVISED_EXERCISE     → Targeted revision instructions after feedback
        TASK                 → Knowledge about what needs doing
        TASK_TEMPLATE        → PS-owned template that spawns Task instances on engagement
        USER_ENTRY           → Unified user-authored content (ADR-054)

    Any PathStep can organize other PathSteps via ORGANIZES relationships (emergent
    identity — no separate MOC type needed).

    Content origin tiers (A-D): `content_origin()`, backed by
    `_CONTENT_ORIGIN_BY_TYPE` in this file. That dict is the only membership list —
    it is tier-commented and read directly by `content_origin()`, so it cannot drift
    from what the method returns. `ContentOrigin` documents what the four tiers mean.
    The list that used to sit here was a hand-transcription of that dict and had
    drifted on two members; call the method instead of trusting prose.

    Ownership rules:
        Curriculum (KU, PS, LP, Exercise) + Activity Templates (6) + Resource +
            FormTemplate:      user_uid = None (shared content, admin/teacher-created)
        Content processing:    user_uid = student/teacher (user-owned)
        Activity (6):          user_uid = student (user-owned)
        Destination:           user_uid = student (user-owned)
        FormSubmission:        user_uid = student (user-owned)
        Interaction:           user_uid = student (user-owned, audit record)
    """

    # Curriculum (admin-created, shared)
    KU = "ku"
    PATH_STEP = "path_step"
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
    ACTIVITY_REPORT = "activity_report"
    ENTRY_REPORT = "entry_report"

    # Unified user-authored content (ADR-054) — collapses the former
    # EXERCISE_SUBMISSION, JE_INPUT, JE_OUTPUT into one type. Dispatch
    # driven by `Pipeline` field, not entity_type.
    USER_ENTRY = "user_entry"

    # Activity (user-owned)
    TASK = "task"
    GOAL = "goal"
    HABIT = "habit"
    EVENT = "event"
    CHOICE = "choice"
    PRINCIPLE = "principle"

    # Activity Templates (PS-owned, admin/teacher-authored, spawn Activity instances on engagement)
    TASK_TEMPLATE = "task_template"
    GOAL_TEMPLATE = "goal_template"
    HABIT_TEMPLATE = "habit_template"
    EVENT_TEMPLATE = "event_template"
    CHOICE_TEMPLATE = "choice_template"
    PRINCIPLE_TEMPLATE = "principle_template"

    # Interaction audit (user-owned, situated learning-loop event)
    INTERACTION = "interaction"

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
        """Check if this is curriculum knowledge content (PathStep or Ku)."""
        return self in _KNOWLEDGE_TYPES

    def is_applied_knowledge(self) -> bool:
        """True for instruction/revision templates — Exercise and RevisedExercise.

        Applied knowledge entities are subordinate to PathStep in the knowledge
        hierarchy: PathStep IS knowledge; Exercise and RevisedExercise are how
        that knowledge is practised and revised. This is the same structural
        relationship as Goal.fulfills_goal_uid (sub-goal under parent goal) —
        Exercise.path_step_uid is a hierarchy-membership property, not a
        scoring/enrichment field.
        """
        return self in _APPLIED_KNOWLEDGE_TYPES

    def is_curriculum_structure(self) -> bool:
        """Check if this is curriculum organisational structure (LearningPath only).

        Note: Exercise is NOT curriculum structure — it is applied knowledge
        subordinate to PathStep. Use is_applied_knowledge() for Exercise/RevisedExercise.
        """
        return self in _CURRICULUM_STRUCTURE_TYPES

    def is_activity(self) -> bool:
        """Check if this is a user activity domain."""
        return self in _ACTIVITY_TYPES

    def is_activity_template(self) -> bool:
        """Check if this is one of the 6 PS-owned Activity Template types."""
        return self in _ACTIVITY_TEMPLATE_TYPES

    def instance_type(self) -> "EntityType":
        """Return the Activity instance type spawned by this template.

        Only valid for the 6 Activity Template types; raises ValueError otherwise.
        """
        try:
            return _TEMPLATE_TO_INSTANCE[self]
        except KeyError:
            raise ValueError(f"{self!r} is not an Activity Template type") from None

    def template_type(self) -> "EntityType":
        """Return the Activity Template type that spawns this instance type.

        Only valid for the 6 Activity Domain instance types; raises ValueError otherwise.
        """
        try:
            return _INSTANCE_TO_TEMPLATE[self]
        except KeyError:
            raise ValueError(f"{self!r} is not an Activity Domain instance type") from None

    def is_destination(self) -> bool:
        """Check if this is the life path destination."""
        return self == EntityType.LIFE_PATH

    def is_content_processing(self) -> bool:
        """Check if this is in the content processing chain (submissions + reports)."""
        return self in _CONTENT_PROCESSING_TYPES

    def is_journal(self) -> bool:
        """Check if this is a journal-pipeline user entry."""
        return False

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
            EntityType.USER_ENTRY,
            EntityType.FORM_SUBMISSION,
            EntityType.ACTIVITY_REPORT,
            EntityType.ENTRY_REPORT,
            EntityType.REVISED_EXERCISE,
        }

    def is_processable(self) -> bool:
        """Check if this EntityType goes through a processing pipeline."""
        return self in {
            EntityType.USER_ENTRY,
            EntityType.ACTIVITY_REPORT,
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

        Canonical DSL shorthands: "ps" → PATH_STEP, "lp" → LEARNING_PATH,
        "ku" → KU, "book"/"film"/"talk" → RESOURCE, "step" → PATH_STEP.
        """
        normalized = text.strip().lower().replace("-", "_").replace(" ", "_")
        return _ENTITY_TYPE_ALIASES.get(normalized)


# EntityType lookup tables (module-level for performance)
_ENTITY_TYPE_DISPLAY_NAMES: dict[EntityType, str] = {
    EntityType.KU: "Knowledge Unit",
    EntityType.RESOURCE: "Resource",
    EntityType.PATH_STEP: "PathStep",
    EntityType.LEARNING_PATH: "Learning Path",
    EntityType.ACTIVITY_REPORT: "Activity Report",
    EntityType.ENTRY_REPORT: "Entry Report",
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
    EntityType.INTERACTION: "Interaction",
    EntityType.LIFE_PATH: "Life Path",
    EntityType.USER_ENTRY: "User Entry",
    EntityType.TASK_TEMPLATE: "Task Template",
    EntityType.GOAL_TEMPLATE: "Goal Template",
    EntityType.HABIT_TEMPLATE: "Habit Template",
    EntityType.EVENT_TEMPLATE: "Event Template",
    EntityType.CHOICE_TEMPLATE: "Choice Template",
    EntityType.PRINCIPLE_TEMPLATE: "Principle Template",
}

_KNOWLEDGE_TYPES = frozenset({EntityType.PATH_STEP, EntityType.KU})
_APPLIED_KNOWLEDGE_TYPES = frozenset({EntityType.EXERCISE, EntityType.REVISED_EXERCISE})
_CURRICULUM_STRUCTURE_TYPES = frozenset({EntityType.LEARNING_PATH})
_CONTENT_PROCESSING_TYPES = frozenset(
    {
        EntityType.USER_ENTRY,
        EntityType.ACTIVITY_REPORT,
        EntityType.ENTRY_REPORT,
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
_ACTIVITY_TEMPLATE_TYPES = frozenset(
    {
        EntityType.TASK_TEMPLATE,
        EntityType.GOAL_TEMPLATE,
        EntityType.HABIT_TEMPLATE,
        EntityType.EVENT_TEMPLATE,
        EntityType.CHOICE_TEMPLATE,
        EntityType.PRINCIPLE_TEMPLATE,
    }
)
_TEMPLATE_TO_INSTANCE: dict[EntityType, EntityType] = {
    EntityType.TASK_TEMPLATE: EntityType.TASK,
    EntityType.GOAL_TEMPLATE: EntityType.GOAL,
    EntityType.HABIT_TEMPLATE: EntityType.HABIT,
    EntityType.EVENT_TEMPLATE: EntityType.EVENT,
    EntityType.CHOICE_TEMPLATE: EntityType.CHOICE,
    EntityType.PRINCIPLE_TEMPLATE: EntityType.PRINCIPLE,
}
_INSTANCE_TO_TEMPLATE: dict[EntityType, EntityType] = {
    v: k for k, v in _TEMPLATE_TO_INSTANCE.items()
}
_SHARED_TYPES = frozenset(
    {
        EntityType.KU,
        EntityType.RESOURCE,
        EntityType.PATH_STEP,
        EntityType.LEARNING_PATH,
        EntityType.EXERCISE,
        EntityType.FORM_TEMPLATE,
        # Activity Templates (PS-owned curriculum content; spawn user-owned instances)
        EntityType.TASK_TEMPLATE,
        EntityType.GOAL_TEMPLATE,
        EntityType.HABIT_TEMPLATE,
        EntityType.EVENT_TEMPLATE,
        EntityType.CHOICE_TEMPLATE,
        EntityType.PRINCIPLE_TEMPLATE,
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
    EntityType.KU: ContentOrigin.CURRICULUM,
    EntityType.PATH_STEP: ContentOrigin.CURRICULUM,
    EntityType.LEARNING_PATH: ContentOrigin.CURRICULUM,
    EntityType.EXERCISE: ContentOrigin.CURRICULUM,
    EntityType.REVISED_EXERCISE: ContentOrigin.USER_CREATED,
    # Activity Templates — PS-owned curriculum content authored by admin/teacher
    EntityType.TASK_TEMPLATE: ContentOrigin.CURRICULUM,
    EntityType.GOAL_TEMPLATE: ContentOrigin.CURRICULUM,
    EntityType.HABIT_TEMPLATE: ContentOrigin.CURRICULUM,
    EntityType.EVENT_TEMPLATE: ContentOrigin.CURRICULUM,
    EntityType.CHOICE_TEMPLATE: ContentOrigin.CURRICULUM,
    EntityType.PRINCIPLE_TEMPLATE: ContentOrigin.CURRICULUM,
    # C — User-generated content
    EntityType.TASK: ContentOrigin.USER_CREATED,
    EntityType.GOAL: ContentOrigin.USER_CREATED,
    EntityType.HABIT: ContentOrigin.USER_CREATED,
    EntityType.EVENT: ContentOrigin.USER_CREATED,
    EntityType.CHOICE: ContentOrigin.USER_CREATED,
    EntityType.PRINCIPLE: ContentOrigin.USER_CREATED,
    EntityType.FORM_SUBMISSION: ContentOrigin.USER_CREATED,
    EntityType.INTERACTION: ContentOrigin.USER_CREATED,
    EntityType.LIFE_PATH: ContentOrigin.USER_CREATED,
    EntityType.USER_ENTRY: ContentOrigin.USER_CREATED,  # ADR-054
    # D — Reports that act on user content
    EntityType.ACTIVITY_REPORT: ContentOrigin.REPORT,
    EntityType.ENTRY_REPORT: ContentOrigin.REPORT,
}

_ENTITY_TYPE_ALIASES: dict[str, EntityType] = {
    # Canonical values
    "ku": EntityType.KU,
    "resource": EntityType.RESOURCE,
    "path_step": EntityType.PATH_STEP,
    "learning_path": EntityType.LEARNING_PATH,
    "activity_report": EntityType.ACTIVITY_REPORT,
    "entry_report": EntityType.ENTRY_REPORT,
    "task": EntityType.TASK,
    "goal": EntityType.GOAL,
    "habit": EntityType.HABIT,
    "event": EntityType.EVENT,
    "choice": EntityType.CHOICE,
    "principle": EntityType.PRINCIPLE,
    "life_path": EntityType.LIFE_PATH,
    # Shorthand aliases
    "book": EntityType.RESOURCE,
    "film": EntityType.RESOURCE,
    "talk": EntityType.RESOURCE,
    "ps": EntityType.PATH_STEP,
    "step": EntityType.PATH_STEP,
    "lp": EntityType.LEARNING_PATH,
    "path": EntityType.LEARNING_PATH,
    "exercise": EntityType.EXERCISE,
    "revised_exercise": EntityType.REVISED_EXERCISE,
    "form_template": EntityType.FORM_TEMPLATE,
    "form_submission": EntityType.FORM_SUBMISSION,
    "form": EntityType.FORM_TEMPLATE,
    "interaction": EntityType.INTERACTION,
    "ia": EntityType.INTERACTION,  # UID prefix alias
    "lifepath": EntityType.LIFE_PATH,
    # ADR-054 unified user-authored content — pre-collapse strings redirect to USER_ENTRY
    "user_entry": EntityType.USER_ENTRY,
    "ue": EntityType.USER_ENTRY,
    "exercise_submission": EntityType.USER_ENTRY,
    "je_input": EntityType.USER_ENTRY,
    "je_output": EntityType.USER_ENTRY,
    # Activity Templates
    "task_template": EntityType.TASK_TEMPLATE,
    "goal_template": EntityType.GOAL_TEMPLATE,
    "habit_template": EntityType.HABIT_TEMPLATE,
    "event_template": EntityType.EVENT_TEMPLATE,
    "choice_template": EntityType.CHOICE_TEMPLATE,
    "principle_template": EntityType.PRINCIPLE_TEMPLATE,
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

    def get_border_class(self) -> str:
        """Get Tailwind border-left class for status card borders."""
        return _ENTITY_STATUS_BORDER_CLASSES.get(self, "border-l-border")

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
    def from_string(cls, text: str) -> EntityStatus | None:
        """Parse EntityStatus from string (case-insensitive, alias-aware).

        Supports aliases for user-uploaded data where non-canonical values
        may appear (e.g., "pending" -> DRAFT).
        """
        normalized = text.strip().lower().replace("-", "_").replace(" ", "_")
        return _ENTITY_STATUS_ALIASES.get(normalized)

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

_ENTITY_STATUS_BORDER_CLASSES: dict[EntityStatus, str] = {
    EntityStatus.ACTIVE: "border-l-green-500",
    EntityStatus.COMPLETED: "border-l-green-500",
    EntityStatus.PAUSED: "border-l-yellow-500",
    EntityStatus.SCHEDULED: "border-l-blue-500",
    EntityStatus.BLOCKED: "border-l-red-500",
    EntityStatus.FAILED: "border-l-red-500",
    EntityStatus.CANCELLED: "border-l-red-500",
    EntityStatus.DRAFT: "border-l-gray-400",
    EntityStatus.SUBMITTED: "border-l-yellow-500",
    EntityStatus.QUEUED: "border-l-yellow-500",
    EntityStatus.PROCESSING: "border-l-blue-500",
    EntityStatus.POSTPONED: "border-l-yellow-500",
    EntityStatus.REVISION_REQUESTED: "border-l-yellow-500",
    EntityStatus.ARCHIVED: "border-l-gray-400",
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

_ENTITY_STATUS_ALIASES: dict[str, EntityStatus] = {
    # Canonical values
    **{status.value: status for status in EntityStatus},
    # Aliases from user-uploaded data
    "pending": EntityStatus.DRAFT,
    "ready": EntityStatus.SCHEDULED,
    "planned": EntityStatus.SCHEDULED,
    "in_progress": EntityStatus.ACTIVE,
    "in_process": EntityStatus.ACTIVE,
    "todo": EntityStatus.DRAFT,
    "done": EntityStatus.COMPLETED,
    "canceled": EntityStatus.CANCELLED,
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
        EntityStatus.SUBMITTED,  # reprocessing path
        EntityStatus.REVISION_REQUESTED,
        EntityStatus.ARCHIVED,
    },
    EntityStatus.FAILED: {
        EntityStatus.DRAFT,
        EntityStatus.SUBMITTED,  # reprocessing path
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
        EntityStatus.COMPLETED,  # teacher approves without student re-submitting
        EntityStatus.ARCHIVED,
    },
    EntityStatus.ARCHIVED: set(),
}

# Activity Templates share the same minimal authoring lifecycle.
_TEMPLATE_STATUSES: frozenset[EntityStatus] = frozenset(
    {
        EntityStatus.DRAFT,
        EntityStatus.ACTIVE,
        EntityStatus.ARCHIVED,
    }
)

# Valid statuses per EntityType (from plan specification)
_VALID_STATUSES_BY_TYPE: dict[EntityType, frozenset[EntityStatus]] = {
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
    EntityType.PATH_STEP: frozenset(
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
    # ActivityReport: generated artifact — written post-generation, always
    # complete. No draft/processing pipeline states exist for it (ruling
    # 2026-07-17: enum map matches the writer, not a speculative lifecycle).
    EntityType.ACTIVITY_REPORT: frozenset({EntityStatus.COMPLETED}),
    EntityType.ENTRY_REPORT: frozenset(
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
    # ADR-054: UserEntry covers the full content-processing lifecycle —
    # draft submission, queued/processing for pipeline work, teacher-review
    # revision loop, terminal completed/failed/archived.
    EntityType.USER_ENTRY: frozenset(
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
    # Interaction: immutable learning-loop event record — the outcome lives
    # on its own result_status field (InteractionResult), not EntityStatus.
    # Record-like lifecycle, same as LifePath: exists (ACTIVE) or archived.
    EntityType.INTERACTION: frozenset(
        {
            EntityStatus.ACTIVE,
            EntityStatus.ARCHIVED,
        }
    ),
    # Activity Templates: authoring lifecycle is publish-and-engage.
    # Templates are not "completed" — instances spawned from them are.
    EntityType.TASK_TEMPLATE: _TEMPLATE_STATUSES,
    EntityType.GOAL_TEMPLATE: _TEMPLATE_STATUSES,
    EntityType.HABIT_TEMPLATE: _TEMPLATE_STATUSES,
    EntityType.EVENT_TEMPLATE: _TEMPLATE_STATUSES,
    EntityType.CHOICE_TEMPLATE: _TEMPLATE_STATUSES,
    EntityType.PRINCIPLE_TEMPLATE: _TEMPLATE_STATUSES,
}

_DEFAULT_STATUS_BY_TYPE: dict[EntityType, EntityStatus] = {
    EntityType.KU: EntityStatus.COMPLETED,
    EntityType.RESOURCE: EntityStatus.COMPLETED,
    EntityType.PATH_STEP: EntityStatus.DRAFT,
    EntityType.LEARNING_PATH: EntityStatus.DRAFT,
    EntityType.EXERCISE: EntityStatus.DRAFT,
    EntityType.REVISED_EXERCISE: EntityStatus.DRAFT,
    EntityType.ACTIVITY_REPORT: EntityStatus.COMPLETED,
    EntityType.ENTRY_REPORT: EntityStatus.DRAFT,
    EntityType.TASK: EntityStatus.DRAFT,
    EntityType.GOAL: EntityStatus.DRAFT,
    EntityType.HABIT: EntityStatus.ACTIVE,
    EntityType.EVENT: EntityStatus.SCHEDULED,
    EntityType.CHOICE: EntityStatus.DRAFT,
    EntityType.PRINCIPLE: EntityStatus.ACTIVE,
    EntityType.FORM_TEMPLATE: EntityStatus.DRAFT,
    EntityType.FORM_SUBMISSION: EntityStatus.COMPLETED,
    EntityType.LIFE_PATH: EntityStatus.ACTIVE,
    EntityType.USER_ENTRY: EntityStatus.DRAFT,  # ADR-054
    EntityType.INTERACTION: EntityStatus.ACTIVE,
    EntityType.TASK_TEMPLATE: EntityStatus.DRAFT,
    EntityType.GOAL_TEMPLATE: EntityStatus.DRAFT,
    EntityType.HABIT_TEMPLATE: EntityStatus.DRAFT,
    EntityType.EVENT_TEMPLATE: EntityStatus.DRAFT,
    EntityType.CHOICE_TEMPLATE: EntityStatus.DRAFT,
    EntityType.PRINCIPLE_TEMPLATE: EntityStatus.DRAFT,
}


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
    TRANSCRIPTION = "transcription"  # Audio→text (Deepgram); valid search facet
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
    SPIRITUAL = "spiritual"
    META = "meta"
    CROSS_DOMAIN = "cross_domain"

    def get_search_synonyms(self) -> tuple[str, ...]:
        """Return search terms that match this domain"""
        synonyms = {
            Domain.KNOWLEDGE: ("knowledge", "learn", "study", "education", "info", "ku"),
            Domain.LEARNING: ("learning", "course", "path", "curriculum", "lp", "ps"),
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

    @classmethod
    def from_string(cls, value: str) -> Domain | None:
        """Parse a string to Domain, case-insensitive. Returns None on unknown.

        Mirrors NonKuDomain.from_string — the canonical enum-boundary parser
        for loosely-typed edge values (e.g. a request Literal that carries a
        value outside the Domain set).
        """
        normalized = value.strip().lower()
        try:
            return cls(normalized)
        except ValueError:
            return None


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
# EntityType covers all 25 entity types; NonKuDomain covers the 4 non-entity domains.
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
    CHOICES = "choices"
    PRINCIPLES = "principles"

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
            AnalyticsDomain.CHOICES: [
                "total_choices",
                "choices_by_domain",
                "decision_quality_avg",
                "choices_reviewed_count",
            ],
            AnalyticsDomain.PRINCIPLES: [
                "total_principles",
                "active_count",
                "embodied_count",
                "alignment_score_avg",
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
