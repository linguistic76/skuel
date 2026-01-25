"""
Relationship Configuration - Domain-Specific Configuration for Generic Relationship Service
============================================================================================

Defines the configuration dataclass that captures ALL domain-specific aspects of
relationship services, enabling a single generic service to handle all 14 domains.

**The Problem:**
14 relationship service files with ~11,000 lines of largely duplicated patterns.
Each service has identical structure but different:
- Relationship types
- Cross-domain context mapping
- Semantic types
- Scoring weights

**The Solution:**
One configuration dataclass per domain + one generic service = ~90% code reduction.

Version: 1.0.0
Date: 2025-12-03
"""

from dataclasses import dataclass, field
from typing import Any

from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
from core.models.query import QueryIntent
from core.models.relationship_names import RelationshipName
from core.models.shared_enums import Domain


@dataclass(frozen=True)
class RelationshipSpec:
    """
    Specification for a single relationship type.

    Captures the relationship name, direction, filtering criteria, ordering,
    and edge metadata configuration.

    **Curriculum Domain Support (January 2026):**
    Extended to support ordered relationships (HAS_STEP with sequence) and
    edge metadata retrieval for curriculum domains (LP, LS, KU, MOC).

    Example with ordering:
        RelationshipSpec(
            relationship=RelationshipName.HAS_STEP,
            direction="outgoing",
            order_by_property="sequence",
            order_direction="ASC",
            include_edge_properties=("sequence", "completed"),
        )
    """

    relationship: RelationshipName
    direction: str = "outgoing"  # "outgoing", "incoming", or "both"
    filter_property: str | None = None  # Optional property filter (e.g., "essentiality")
    filter_value: str | None = None  # Value to filter on

    # =========================================================================
    # ORDERING SUPPORT (January 2026 - Curriculum Domains)
    # =========================================================================
    # Enables ordered relationship queries (e.g., HAS_STEP ordered by sequence)

    order_by_property: str | None = None  # Edge property to order by (e.g., "sequence")
    order_direction: str = "ASC"  # "ASC" or "DESC"

    # =========================================================================
    # EDGE METADATA (January 2026 - Curriculum Domains)
    # =========================================================================
    # Specifies which edge properties to return with get_related_with_metadata()

    include_edge_properties: tuple[str, ...] = ()  # Properties to return from edge


@dataclass(frozen=True)
class CrossDomainMapping:
    """
    Mapping for cross-domain context categorization.

    Defines how to categorize entities found via relationship traversal
    into domain-specific groups (e.g., tasks, goals, knowledge).
    """

    category_name: str  # e.g., "prerequisites", "supporting_habits"
    target_label: str  # Neo4j node label (e.g., "Task", "Ku", "Goal")
    via_relationships: list[RelationshipName]  # Relationships that lead to this category
    use_directional_markers: bool = False  # Whether to use ->REL / <-REL markers


@dataclass
class RelationshipConfig:
    """
    Complete configuration for a domain's relationship service.

    This single configuration object captures ALL domain-specific aspects,
    enabling the UnifiedRelationshipService to handle any domain generically.

    **Configuration Sections:**

    1. **Identity** - Domain, labels, classes
    2. **Backend** - How to access the backend
    3. **Relationships** - Which relationships this domain uses
    4. **Cross-Domain Context** - How to categorize related entities
    5. **Semantic** - Semantic relationship types
    6. **Scoring** - Weights for relevance calculations
    7. **Graph Intelligence** - Intent-based query configuration

    **Usage:**
    ```python
    TASK_CONFIG = RelationshipConfig(
        domain=Domain.TASKS,
        entity_label="Task",
        dto_class=TaskDTO,
        model_class=Task,
        backend_get_method="get_task",
        ownership_relationship=RelationshipName.HAS_TASK,
        ...
    )

    tasks_relationship_service = UnifiedRelationshipService(
        backend=tasks_backend,
        graph_intel=graph_intel,
        config=TASK_CONFIG,
    )
    ```
    """

    # =========================================================================
    # IDENTITY - What domain is this?
    # =========================================================================
    domain: Domain
    entity_label: str  # Neo4j node label (e.g., "Task", "Goal", "Habit")
    dto_class: type  # DTO class for conversion (e.g., TaskDTO)
    model_class: type  # Domain model class (e.g., Task)

    # =========================================================================
    # BACKEND - How to access the backend
    # =========================================================================
    backend_get_method: str = "get"  # Method name to get single entity
    use_semantic_helper: bool = True  # Whether to initialize SemanticRelationshipHelper

    # =========================================================================
    # RELATIONSHIPS - Which relationships does this domain use?
    # =========================================================================

    # User ownership relationship (e.g., HAS_TASK, HAS_GOAL)
    ownership_relationship: RelationshipName | None = None

    # Outgoing relationships: entity → other
    # Maps method suffix to relationship (e.g., "knowledge" → APPLIES_KNOWLEDGE)
    outgoing_relationships: dict[str, RelationshipSpec] = field(default_factory=dict)

    # Incoming relationships: other → entity
    incoming_relationships: dict[str, RelationshipSpec] = field(default_factory=dict)

    # Bidirectional relationships that work both ways
    bidirectional_relationships: list[RelationshipName] = field(default_factory=list)

    # =========================================================================
    # CROSS-DOMAIN CONTEXT - How to categorize related entities
    # =========================================================================

    # Relationship types to query for cross-domain context
    cross_domain_relationship_types: list[str] = field(default_factory=list)

    # How to map raw context to domain-specific categories
    cross_domain_mappings: list[CrossDomainMapping] = field(default_factory=list)

    # =========================================================================
    # SEMANTIC - Semantic relationship types for this domain
    # =========================================================================

    # Semantic types used for get_with_semantic_context()
    semantic_types: list[SemanticRelationshipType] = field(default_factory=list)

    # =========================================================================
    # SCORING - Weights for relevance calculations
    # =========================================================================

    # Scoring weights for relevance calculations
    # Keys: "urgency", "dependencies", "knowledge", "alignment", etc.
    scoring_weights: dict[str, float] = field(default_factory=dict)

    # =========================================================================
    # GRAPH INTELLIGENCE - Intent-based query configuration
    # =========================================================================

    # Default QueryIntent for get_entity_with_context()
    default_context_intent: QueryIntent = QueryIntent.HIERARCHICAL

    # Intent mappings for specific operations
    # Maps operation name to QueryIntent
    intent_mappings: dict[str, QueryIntent] = field(default_factory=dict)

    # =========================================================================
    # RELATIONSHIP CREATION - Batch creation configuration
    # =========================================================================

    # Maps parameter name to (RelationshipName, direction, optional_properties)
    # Used by create_entity_relationships() for batch edge creation
    relationship_creation_map: dict[str, tuple[RelationshipName, str, dict[str, Any] | None]] = (
        field(default_factory=dict)
    )

    def get_relationship_by_method(self, method_suffix: str) -> RelationshipSpec | None:
        """
        Get relationship spec by method suffix.

        Args:
            method_suffix: The suffix after get_{entity}_ (e.g., "knowledge", "principles")

        Returns:
            RelationshipSpec or None if not found
        """
        if method_suffix in self.outgoing_relationships:
            return self.outgoing_relationships[method_suffix]
        if method_suffix in self.incoming_relationships:
            return self.incoming_relationships[method_suffix]
        return None

    def get_all_relationship_methods(self) -> list[str]:
        """
        Get all method suffixes that should be generated.

        Returns list of suffixes like ["knowledge", "principles", "subtasks"]
        that will become get_entity_knowledge(), get_entity_principles(), etc.
        """
        return list(self.outgoing_relationships.keys()) + list(self.incoming_relationships.keys())

    def get_intent_for_operation(self, operation: str) -> QueryIntent:
        """
        Get the QueryIntent for a specific operation.

        Args:
            operation: Operation name (e.g., "context", "dependencies", "impact")

        Returns:
            QueryIntent for the operation, or default_context_intent if not mapped
        """
        return self.intent_mappings.get(operation, self.default_context_intent)
