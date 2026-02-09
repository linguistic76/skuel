"""
Neo4j Node Labels - Single Source of Truth
==========================================

This module defines all valid Neo4j node labels used in SKUEL.

Core Principle: "The codebase knows itself"

Just as RelationshipName provides a single source of truth for relationship types,
NeoLabel provides a single source of truth for node labels. This enables:

1. Compile-time typo detection (MyPy catches invalid labels)
2. EntityType <-> Label mapping (consistent translation)
3. Self-documentation (all valid labels in one place)
4. Backend validation (UniversalNeo4jBackend can validate labels)

Usage:
    from core.models.enums import NeoLabel

    # Direct usage
    backend = UniversalNeo4jBackend[Task](driver, NeoLabel.TASK, Task)

    # Get label from EntityType
    label = NeoLabel.from_entity_type(EntityType.KU)  # Returns NeoLabel.KU

    # Validate a label string
    if NeoLabel.is_valid("Task"):  # Returns True
        ...

See Also:
    - EntityType: Domain type enum (entity_enums.py)
    - RelationshipName: Relationship type enum (relationship_names.py)
    - UniversalNeo4jBackend: Generic persistence layer
"""

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.enums.entity_enums import EntityType


class NeoLabel(str, Enum):
    """
    All valid Neo4j node labels in SKUEL.

    Organized by domain group to match the 14-domain architecture.

    The label value is the exact string used in Neo4j MATCH/CREATE patterns.
    """

    # =========================================================================
    # Activity Domains (7)
    # =========================================================================
    TASK = "Task"
    GOAL = "Goal"
    HABIT = "Habit"
    HABIT_COMPLETION = "HabitCompletion"
    EVENT = "Event"
    CHOICE = "Choice"
    PRINCIPLE = "Principle"
    PRINCIPLE_REFLECTION = "PrincipleReflection"

    # =========================================================================
    # Finance Domain (1)
    # =========================================================================
    EXPENSE = "Expense"
    INVOICE = "Invoice"

    # =========================================================================
    # Curriculum Domains (4)
    # =========================================================================
    KU = "Ku"  # Knowledge Unit
    LS = "Ls"  # Learning Step
    LP = "Lp"  # Learning Path
    MOC = "Moc"  # Map of Content (MOC is a KU with ORGANIZES relationships)

    # =========================================================================
    # Organizational
    # =========================================================================
    GROUP = "Group"  # Teacher-student class management (ADR-040)

    # =========================================================================
    # Content/Processing Domains
    # =========================================================================
    JOURNAL = "Journal"  # Legacy — migration target is Report
    JOURNAL_PROJECT = "JournalProject"  # Legacy — migration target is ReportProject
    REPORT = "Report"
    REPORT_PROJECT = "ReportProject"
    REPORT_SCHEDULE = "ReportSchedule"
    TRANSCRIPTION = "Transcription"

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
    def from_entity_type(cls, entity_type: "EntityType") -> "NeoLabel | None":
        """
        Get the Neo4j label for an EntityType.

        This is THE mapping between domain types and persistence labels.

        Args:
            entity_type: The EntityType enum value

        Returns:
            NeoLabel if mapping exists, None otherwise

        Example:
            label = NeoLabel.from_entity_type(EntityType.KU)  # Returns NeoLabel.KU
            label = NeoLabel.from_entity_type(EntityType.TASK)  # Returns NeoLabel.TASK
        """
        # Import here to avoid circular dependency
        from core.models.enums.entity_enums import EntityType

        # Use canonical form to handle aliases (KNOWLEDGE -> KU, etc.)
        canonical = entity_type.get_canonical()

        mapping: dict[EntityType, NeoLabel] = {
            # Activity Domains
            EntityType.TASK: cls.TASK,
            EntityType.GOAL: cls.GOAL,
            EntityType.HABIT: cls.HABIT,
            EntityType.EVENT: cls.EVENT,
            EntityType.CHOICE: cls.CHOICE,
            EntityType.PRINCIPLE: cls.PRINCIPLE,
            # Finance
            EntityType.FINANCE: cls.EXPENSE,
            # Curriculum Domains
            EntityType.KU: cls.KU,
            EntityType.LS: cls.LS,
            EntityType.LP: cls.LP,
            EntityType.MOC: cls.MOC,
            # Content Domains (JOURNAL canonicalizes to REPORT)
            EntityType.REPORT: cls.REPORT,
            # Organizational
            EntityType.GROUP: cls.GROUP,
        }

        return mapping.get(canonical)

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
            # frozenset({'Task', 'Goal', 'Habit', ...})
        """
        return frozenset(label.value for label in cls)

    def __str__(self) -> str:
        """Return the label value for use in Cypher queries."""
        return self.value
