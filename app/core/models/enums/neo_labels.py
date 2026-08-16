"""
Neo4j Node Labels - Single Source of Truth
==========================================

This module defines all valid Neo4j node labels used in SKUEL.

Core Principle: "The codebase knows itself"

Just as RelationshipName provides a single source of truth for relationship types,
NeoLabel provides a single source of truth for node labels. This enables:

1. Compile-time typo detection (MyPy catches invalid labels)
2. EntityType/NonKuDomain -> Label mapping (consistent translation)
3. Self-documentation (all valid labels in one place)
4. Backend validation (UniversalNeo4jBackend can validate labels)

Usage:
    from core.models.enums import NeoLabel

    # Domain-specific label — each entity type has its own label
    backend = UniversalNeo4jBackend[Task](driver, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY)

    # Get label from EntityType
    label = NeoLabel.from_entity_type(EntityType.TASK)  # Returns NeoLabel.TASK

    # Validate a label string
    if NeoLabel.is_valid("Task"):  # Returns True
        ...

See Also:
    - EntityType: Domain type enum (entity_enums.py)
    - NonKuDomain: Non-Ku domain enum (entity_enums.py)
    - RelationshipName: Relationship type enum (relationship_names.py)
    - UniversalNeo4jBackend: Generic persistence layer
"""

from __future__ import annotations

from enum import StrEnum

from core.models.enums.entity_enums import EntityType, NonKuDomain


class NeoLabel(StrEnum):
    """
    All valid Neo4j node labels in SKUEL.

    Domain entities use multi-label architecture:
    - :Entity (universal base label for all domain entities)
    - :Task, :Goal, :Habit, etc. (domain-specific label for indexed queries)

    The label value is the exact string used in Neo4j MATCH/CREATE patterns.
    """

    # =========================================================================
    # Universal Base Label — ALL domain entities
    # =========================================================================
    ENTITY = "Entity"  # Universal label for cross-domain queries

    # =========================================================================
    # Domain-Specific Labels — one per EntityType
    # =========================================================================

    # Activity Domains (6) — user-owned
    TASK = "Task"
    GOAL = "Goal"
    HABIT = "Habit"
    EVENT = "Event"
    CHOICE = "Choice"
    PRINCIPLE = "Principle"

    # Activity Templates (6) — PS-owned, spawn Activity instances on engagement
    TASK_TEMPLATE = "TaskTemplate"
    GOAL_TEMPLATE = "GoalTemplate"
    HABIT_TEMPLATE = "HabitTemplate"
    EVENT_TEMPLATE = "EventTemplate"
    CHOICE_TEMPLATE = "ChoiceTemplate"
    PRINCIPLE_TEMPLATE = "PrincipleTemplate"

    # Curriculum Domains (4) — shared content
    KU = "Ku"
    RESOURCE = "Resource"
    PATH_STEP = "PathStep"
    LEARNING_PATH = "LearningPath"

    # Content Processing — user submissions and reports
    SUBMISSION = "Submission"  # Base label for multi-label queries
    ACTIVITY_REPORT = "ActivityReport"
    ENTRY_REPORT = "EntryReport"

    # Unified user-authored content (ADR-054)
    USER_ENTRY = "UserEntry"

    # Instruction Templates (2)
    EXERCISE = "Exercise"  # Domain label for :Entity nodes with entity_type="exercise"
    REVISED_EXERCISE = "RevisedExercise"  # Targeted revision instructions after feedback

    # General-Purpose Forms (2)
    FORM_TEMPLATE = "FormTemplate"  # Admin-created form definitions
    FORM_SUBMISSION = "FormSubmission"  # User responses to form templates

    # Interaction audit (1) — User Interaction Contract
    INTERACTION = "Interaction"

    # Destination (1)
    LIFE_PATH = "LifePath"

    # =========================================================================
    # Activity Infrastructure (sub-entity nodes)
    # =========================================================================
    HABIT_COMPLETION = "HabitCompletion"
    PRINCIPLE_REFLECTION = "PrincipleReflection"

    # =========================================================================
    # Finance Domain (non-Entity)
    # EXPENSE removed (ADR-052 Phase 5) — native expense module demolished;
    # only invoices survive.
    # =========================================================================
    INVOICE = "Invoice"

    # =========================================================================
    # Organizational (non-Entity)
    # =========================================================================
    GROUP = "Group"  # Teacher-student class management (ADR-040)
    REVIEW_REQUEST = "ReviewRequest"  # Teacher review queue rows — not an Entity subclass

    # =========================================================================
    # Content/Processing Infrastructure
    # =========================================================================
    CONTENT = "Content"  # Body-content root: (Entity)-[:HAS_CONTENT]->(Content)-[:HAS_CHUNK]->(ContentChunk)
    CONTENT_CHUNK = "ContentChunk"  # RAG chunks for semantic retrieval
    REFERENCE_CHUNK = "ReferenceChunk"  # Canon reference-book chunks (own vector index, invisible to SearchRouter)
    REPORT_PROJECT = "ReportProject"  # Legacy — pre-Exercise report project nodes
    REPORT_SCHEDULE = "ReportSchedule"
    TRANSCRIPTION = "Transcription"
    CHANGE_LOG = "ChangeLog"  # Jupyter sync change audit rows

    # =========================================================================
    # Ingestion Audit Trail
    # =========================================================================
    INGESTION_HISTORY = "IngestionHistory"  # One row per ingestion run
    INGESTION_ERROR = "IngestionError"  # (IngestionHistory)-[:HAD_ERROR]->(IngestionError)
    INGESTION_METADATA = "IngestionMetadata"  # Per-file ingestion watermark (file_path keyed)

    # =========================================================================
    # Intelligence Snapshots (non-Entity aggregate nodes)
    # =========================================================================
    # "Analytics aggregate, they don't create" holds for DOMAIN data — these are
    # counters/snapshots keyed by user_uid, not domain entities.
    INSIGHT = "Insight"  # Persisted intelligence output (ABOUT_ENTITY → subject)
    ZPD_HISTORY = "ZPDHistory"  # Periodic ZPD assessment snapshots
    LEARNING_VELOCITY = "LearningVelocity"  # Per-user learning-rate counters
    PRODUCTIVITY_ANALYTICS = "ProductivityAnalytics"  # Per-user task-completion counters
    HABIT_ANALYTICS = "HabitAnalytics"  # Per-user habit-completion counters
    ACHIEVEMENT = "Achievement"  # Badge nodes unlocked by habit streaks

    # =========================================================================
    # Notifications
    # =========================================================================
    NOTIFICATION = "Notification"  # In-app notification nodes

    # =========================================================================
    # Authentication Infrastructure
    # =========================================================================
    SESSION = "Session"  # User session nodes for auth
    AUTH_EVENT = "AuthEvent"  # Audit trail nodes for security events
    DEVICE = "Device"  # Enrolled vault-agent devices (ADR-075) — auth infra, not an Entity
    PASSWORD_RESET_TOKEN = "PasswordResetToken"  # (user)-[:HAS_RESET_TOKEN]->(PasswordResetToken)

    # =========================================================================
    # Conversation Persistence (ADR-078) — discussion sessions, owner-private
    # =========================================================================
    # NeoLabels ONLY — deliberately NOT EntityType members. That non-membership
    # IS the understanding wall: keyed off EntityType, embeddings / SearchRouter /
    # context-builder are all structurally blind to these nodes (ADR-078 §2/§6).
    CONVERSATION_SESSION = "ConversationSession"  # Companion-neutral discussion session
    CONVERSATION_TURN = "ConversationTurn"  # One message within a session
    # Pre-ADR-078 Askesis transcript node, written on every query turn via
    # (user)-[:HAS_MESSAGE]->(ConversationMessage). A second, older conversation
    # store running in parallel with the pair above — outside the understanding
    # wall, and not yet reconciled with it (SKUEL030 backlog).
    CONVERSATION_MESSAGE = "ConversationMessage"

    # =========================================================================
    # Cross-Cutting Systems
    # =========================================================================
    USER = "User"
    USER_PROGRESS = "UserProgress"
    EMBEDDING_VECTOR = "EmbeddingVector"
    ASKESIS = "Askesis"
    SEARCH_EVENT = "SearchEvent"  # Search behavioral log (discovery analytics)

    # =========================================================================
    # Class Methods
    # =========================================================================

    @classmethod
    def from_entity_type(cls, entity_type: EntityType) -> NeoLabel:
        """
        Get the domain-specific Neo4j label for a EntityType.

        Each EntityType maps to its own domain label for indexed queries.

        Args:
            entity_type: The EntityType enum value

        Returns:
            Domain-specific NeoLabel

        Example:
            label = NeoLabel.from_entity_type(EntityType.TASK)  # Returns NeoLabel.TASK
            label = NeoLabel.from_entity_type(EntityType.KU)  # Returns NeoLabel.KU
        """
        return _ENTITY_TYPE_TO_LABEL[entity_type]

    @classmethod
    def from_domain(cls, domain: EntityType | NonKuDomain) -> NeoLabel | None:
        """
        Get Neo4j label for any domain identifier.

        Args:
            domain: EntityType or NonKuDomain value

        Returns:
            NeoLabel if mapping exists, None for domains without Neo4j nodes

        Example:
            NeoLabel.from_domain(EntityType.TASK)  # Returns NeoLabel.TASK
            NeoLabel.from_domain(NonKuDomain.FINANCE)  # Returns NeoLabel.INVOICE
            NeoLabel.from_domain(NonKuDomain.CALENDAR)  # Returns None
        """
        if isinstance(domain, EntityType):
            return cls.from_entity_type(domain)

        _non_ku_mapping: dict[NonKuDomain, NeoLabel] = {
            NonKuDomain.FINANCE: cls.INVOICE,
            NonKuDomain.GROUP: cls.GROUP,
        }
        return _non_ku_mapping.get(domain)  # CALENDAR/LEARNING have no Neo4j label

    @classmethod
    def is_valid(cls, label: str) -> bool:
        """
        Check if a string is a valid Neo4j label.

        Args:
            label: The label string to validate

        Returns:
            True if label is valid, False otherwise

        Example:
            NeoLabel.is_valid("Task")  # True
            NeoLabel.is_valid("Taks")  # False (typo)
        """
        return label in cls._value2member_map_

    @classmethod
    def fulltext_index_name(cls, label: NeoLabel | str) -> str:
        """
        Derive the fulltext index name for a label.

        THE single naming rule shared by index creation (schema manager) and
        index querying (vector search) — the two sides cannot drift. Snake-cases
        multi-word labels via the enum member name, which flat `label.lower()`
        gets wrong (`PathStep` → `pathstep`, not `path_step`).

        Note: vector index names deliberately use a different flat convention —
        this rule covers fulltext indexes only.

        Args:
            label: NeoLabel member or its label string (e.g. "PathStep")

        Returns:
            The fulltext index name (e.g. "path_step_fulltext_idx")

        Example:
            NeoLabel.fulltext_index_name(NeoLabel.PATH_STEP)  # "path_step_fulltext_idx"
            NeoLabel.fulltext_index_name("Task")  # "task_fulltext_idx"
        """
        return f"{cls(label).name.lower()}_fulltext_idx"

    @classmethod
    def all_labels(cls) -> frozenset[str]:
        """
        Get all valid label strings.

        Returns:
            Frozen set of all valid label values

        Example:
            labels = NeoLabel.all_labels()
            # frozenset({'Entity', 'Task', 'Goal', 'Invoice', ...})
        """
        return frozenset(label.value for label in cls)

    def __str__(self) -> str:
        """Return the label value for use in Cypher queries."""
        return self.value


# =============================================================================
# EntityType -> NeoLabel mapping (module-level for performance)
# =============================================================================

_ENTITY_TYPE_TO_LABEL: dict[EntityType, NeoLabel] = {
    EntityType.TASK: NeoLabel.TASK,
    EntityType.GOAL: NeoLabel.GOAL,
    EntityType.HABIT: NeoLabel.HABIT,
    EntityType.EVENT: NeoLabel.EVENT,
    EntityType.CHOICE: NeoLabel.CHOICE,
    EntityType.PRINCIPLE: NeoLabel.PRINCIPLE,
    EntityType.KU: NeoLabel.KU,
    EntityType.RESOURCE: NeoLabel.RESOURCE,
    EntityType.PATH_STEP: NeoLabel.PATH_STEP,
    EntityType.LEARNING_PATH: NeoLabel.LEARNING_PATH,
    EntityType.EXERCISE: NeoLabel.EXERCISE,
    EntityType.REVISED_EXERCISE: NeoLabel.REVISED_EXERCISE,
    EntityType.FORM_TEMPLATE: NeoLabel.FORM_TEMPLATE,
    EntityType.FORM_SUBMISSION: NeoLabel.FORM_SUBMISSION,
    EntityType.ACTIVITY_REPORT: NeoLabel.ACTIVITY_REPORT,
    EntityType.ENTRY_REPORT: NeoLabel.ENTRY_REPORT,
    EntityType.INTERACTION: NeoLabel.INTERACTION,
    EntityType.LIFE_PATH: NeoLabel.LIFE_PATH,
    EntityType.USER_ENTRY: NeoLabel.USER_ENTRY,  # ADR-054
    EntityType.TASK_TEMPLATE: NeoLabel.TASK_TEMPLATE,
    EntityType.GOAL_TEMPLATE: NeoLabel.GOAL_TEMPLATE,
    EntityType.HABIT_TEMPLATE: NeoLabel.HABIT_TEMPLATE,
    EntityType.EVENT_TEMPLATE: NeoLabel.EVENT_TEMPLATE,
    EntityType.CHOICE_TEMPLATE: NeoLabel.CHOICE_TEMPLATE,
    EntityType.PRINCIPLE_TEMPLATE: NeoLabel.PRINCIPLE_TEMPLATE,
}
