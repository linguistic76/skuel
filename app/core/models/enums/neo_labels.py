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

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.enums.entity_enums import EntityType, NonKuDomain


class NeoLabel(str, Enum):
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

    # Curriculum Domains (4) — shared content
    KU = "Ku"
    RESOURCE = "Resource"
    LEARNING_STEP = "LearningStep"
    LEARNING_PATH = "LearningPath"

    # Content Processing (4) — user submissions and reports
    SUBMISSION = "Submission"
    JOURNAL = "Journal"
    AI_FEEDBACK = "AiFeedback"
    FEEDBACK = "Feedback"

    # Instruction Templates (1)
    EXERCISE = "Exercise"  # Domain label for :Entity nodes with ku_type="exercise"

    # Destination (1)
    LIFE_PATH = "LifePath"

    # =========================================================================
    # Activity Infrastructure (sub-entity nodes)
    # =========================================================================
    HABIT_COMPLETION = "HabitCompletion"
    PRINCIPLE_REFLECTION = "PrincipleReflection"

    # =========================================================================
    # Finance Domain (non-Entity)
    # =========================================================================
    EXPENSE = "Expense"
    INVOICE = "Invoice"

    # =========================================================================
    # Organizational (non-Entity)
    # =========================================================================
    GROUP = "Group"  # Teacher-student class management (ADR-040)

    # =========================================================================
    # Content/Processing Infrastructure
    # =========================================================================
    ASSIGNMENT = "Assignment"  # Legacy — ReportProject/Assignment nodes
    KU_SCHEDULE = "KuSchedule"
    TRANSCRIPTION = "Transcription"

    # =========================================================================
    # Notifications
    # =========================================================================
    NOTIFICATION = "Notification"  # In-app notification nodes

    # =========================================================================
    # Cross-Cutting Systems
    # =========================================================================
    USER = "User"
    USER_PROGRESS = "UserProgress"
    EMBEDDING_VECTOR = "EmbeddingVector"
    ASKESIS = "Askesis"

    # =========================================================================
    # Class Methods
    # =========================================================================

    @classmethod
    def from_entity_type(cls, ku_type: EntityType) -> NeoLabel:
        """
        Get the domain-specific Neo4j label for a EntityType.

        Each EntityType maps to its own domain label for indexed queries.

        Args:
            ku_type: The EntityType enum value

        Returns:
            Domain-specific NeoLabel

        Example:
            label = NeoLabel.from_entity_type(EntityType.TASK)  # Returns NeoLabel.TASK
            label = NeoLabel.from_entity_type(EntityType.KU)  # Returns NeoLabel.KU
        """
        _ensure_mapping()
        return _ENTITY_TYPE_TO_LABEL[ku_type]

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
            NeoLabel.from_domain(NonKuDomain.FINANCE)  # Returns NeoLabel.EXPENSE
            NeoLabel.from_domain(NonKuDomain.CALENDAR)  # Returns None
        """
        from core.models.enums.entity_enums import EntityType, NonKuDomain

        if isinstance(domain, EntityType):
            return cls.from_entity_type(domain)

        _non_ku_mapping: dict[NonKuDomain, NeoLabel] = {
            NonKuDomain.FINANCE: cls.EXPENSE,
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
    def all_labels(cls) -> frozenset[str]:
        """
        Get all valid label strings.

        Returns:
            Frozen set of all valid label values

        Example:
            labels = NeoLabel.all_labels()
            # frozenset({'Entity', 'Task', 'Goal', 'Expense', ...})
        """
        return frozenset(label.value for label in cls)

    def __str__(self) -> str:
        """Return the label value for use in Cypher queries."""
        return self.value


# =============================================================================
# EntityType -> NeoLabel mapping (module-level for performance)
# =============================================================================
# Lazy-initialized to avoid circular imports (EntityType imports happen at runtime)

_ENTITY_TYPE_TO_LABEL: dict[EntityType, NeoLabel] = {}


def _init_ku_type_mapping() -> None:
    """Initialize the EntityType -> NeoLabel mapping. Called on first use."""
    from core.models.enums.entity_enums import EntityType

    _ENTITY_TYPE_TO_LABEL.update(
        {
            EntityType.TASK: NeoLabel.TASK,
            EntityType.GOAL: NeoLabel.GOAL,
            EntityType.HABIT: NeoLabel.HABIT,
            EntityType.EVENT: NeoLabel.EVENT,
            EntityType.CHOICE: NeoLabel.CHOICE,
            EntityType.PRINCIPLE: NeoLabel.PRINCIPLE,
            EntityType.KU: NeoLabel.KU,
            EntityType.RESOURCE: NeoLabel.RESOURCE,
            EntityType.LEARNING_STEP: NeoLabel.LEARNING_STEP,
            EntityType.LEARNING_PATH: NeoLabel.LEARNING_PATH,
            EntityType.EXERCISE: NeoLabel.EXERCISE,
            EntityType.SUBMISSION: NeoLabel.SUBMISSION,
            EntityType.JOURNAL: NeoLabel.JOURNAL,
            EntityType.AI_FEEDBACK: NeoLabel.AI_FEEDBACK,
            EntityType.FEEDBACK_REPORT: NeoLabel.FEEDBACK,
            EntityType.LIFE_PATH: NeoLabel.LIFE_PATH,
        }
    )


def _ensure_mapping() -> None:
    """Ensure the mapping is initialized."""
    if not _ENTITY_TYPE_TO_LABEL:
        _init_ku_type_mapping()
