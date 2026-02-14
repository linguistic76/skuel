"""
Neo4j Node Labels - Single Source of Truth
==========================================

This module defines all valid Neo4j node labels used in SKUEL.

Core Principle: "The codebase knows itself"

Just as RelationshipName provides a single source of truth for relationship types,
NeoLabel provides a single source of truth for node labels. This enables:

1. Compile-time typo detection (MyPy catches invalid labels)
2. KuType/NonKuDomain -> Label mapping (consistent translation)
3. Self-documentation (all valid labels in one place)
4. Backend validation (UniversalNeo4jBackend can validate labels)

Usage:
    from core.models.enums import NeoLabel

    # Direct usage — all domain entities are :Ku nodes
    backend = UniversalNeo4jBackend[Ku](driver, NeoLabel.KU, Ku)

    # Get label from KuType (always returns KU)
    label = NeoLabel.from_ku_type(KuType.TASK)  # Returns NeoLabel.KU

    # Validate a label string
    if NeoLabel.is_valid("Ku"):  # Returns True
        ...

See Also:
    - KuType: Domain type enum (ku_enums.py)
    - NonKuDomain: Non-Ku domain enum (entity_enums.py)
    - RelationshipName: Relationship type enum (relationship_names.py)
    - UniversalNeo4jBackend: Generic persistence layer
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.enums.entity_enums import NonKuDomain
    from core.models.enums.ku_enums import KuType


class NeoLabel(str, Enum):
    """
    All valid Neo4j node labels in SKUEL.

    After the unified Ku migration, all domain entities (tasks, goals, habits,
    events, choices, principles, KU, LS, LP, reports, life path) are :Ku nodes
    with a ku_type discriminator. Only non-Ku infrastructure nodes retain
    separate labels.

    The label value is the exact string used in Neo4j MATCH/CREATE patterns.
    """

    # =========================================================================
    # Unified Domain Label — ALL domain entities
    # =========================================================================
    KU = "Ku"  # Tasks, Goals, Habits, Events, Choices, Principles, KU, LS, LP, Reports, LifePath

    # =========================================================================
    # Activity Infrastructure (sub-entity nodes)
    # =========================================================================
    HABIT_COMPLETION = "HabitCompletion"
    PRINCIPLE_REFLECTION = "PrincipleReflection"

    # =========================================================================
    # Finance Domain (non-Ku)
    # =========================================================================
    EXPENSE = "Expense"
    INVOICE = "Invoice"

    # =========================================================================
    # Organizational (non-Ku)
    # =========================================================================
    GROUP = "Group"  # Teacher-student class management (ADR-040)

    # =========================================================================
    # Content/Processing Infrastructure
    # =========================================================================
    KU_PROJECT = "KuProject"
    KU_SCHEDULE = "KuSchedule"
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
    def from_ku_type(cls, ku_type: KuType) -> NeoLabel:
        """
        Get the Neo4j label for a KuType.

        All KuTypes map to NeoLabel.KU (unified Ku model).

        Args:
            ku_type: The KuType enum value

        Returns:
            NeoLabel.KU (always)

        Example:
            label = NeoLabel.from_ku_type(KuType.TASK)  # Returns NeoLabel.KU
            label = NeoLabel.from_ku_type(KuType.CURRICULUM)  # Returns NeoLabel.KU
        """
        return cls.KU

    @classmethod
    def from_domain(cls, domain: KuType | NonKuDomain) -> NeoLabel | None:
        """
        Get Neo4j label for any domain identifier.

        Args:
            domain: KuType or NonKuDomain value

        Returns:
            NeoLabel if mapping exists, None for domains without Neo4j nodes

        Example:
            NeoLabel.from_domain(KuType.TASK)  # Returns NeoLabel.KU
            NeoLabel.from_domain(NonKuDomain.FINANCE)  # Returns NeoLabel.EXPENSE
            NeoLabel.from_domain(NonKuDomain.CALENDAR)  # Returns None
        """
        from core.models.enums.entity_enums import NonKuDomain
        from core.models.enums.ku_enums import KuType

        if isinstance(domain, KuType):
            return cls.KU

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
            NeoLabel.is_valid("Ku")  # True
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
            # frozenset({'Ku', 'HabitCompletion', 'Expense', ...})
        """
        return frozenset(label.value for label in cls)

    def __str__(self) -> str:
        """Return the label value for use in Cypher queries."""
        return self.value
