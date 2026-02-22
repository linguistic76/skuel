"""
Domain Configuration Dataclass
==============================

Centralized configuration for BaseService behavior.

This module consolidates the 18 class attributes previously scattered
across individual service classes into a single, type-safe dataclass.

**ONE PATH FORWARD (January 2026 - Phase 3 Complete):**
DomainConfig is THE ONLY configuration source for BaseService.

**Before (scattered class attributes):**
```python
class TasksSearchService(BaseService):
    _dto_class = TaskDTO
    _model_class = Task
    _search_fields = ["title", "description"]
    _date_field = "due_date"
    _completed_statuses = [EntityStatus.COMPLETED.value]
    # ... 13 more attributes scattered across the class
```

**After (single configuration object):**
```python
class TasksSearchService(BaseService):
    _config = create_activity_domain_config(
        dto_class=TaskDTO,
        model_class=Task,
        domain_name="tasks",
        date_field="due_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
    )
```

**Benefits:**
- ✅ Single source of truth for domain behavior (One Path Forward)
- ✅ Type-safe with IDE completion
- ✅ Easy to compare configurations across domains
- ✅ Centralized validation in DomainConfig.__post_init__
- ✅ Factory functions for Activity and Curriculum domains
- ✅ No dual configuration system - DomainConfig is THE path

**Migration Status (January 2026):**
- ✅ Phase 1: Created DomainConfig and factories
- ✅ Phase 2: Migrated search services to use DomainConfig
- ✅ Phase 3: Migrated ALL services to DomainConfig (19 core + 6 search = 25 services)
- ✅ Phase 3: Removed class attribute fallback from _get_config_value()

See Also:
    - /core/services/base_service.py - Uses DomainConfig exclusively
    - /core/models/relationship_registry.py - THE single source of truth for relationships
    - /docs/migrations/BASESERVICE_IMPROVEMENTS_2026-01-29.md - Migration guide
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.models.relationship_names import RelationshipName


@dataclass(frozen=True)
class DomainConfig:
    """
    Configuration for BaseService behavior.

    Consolidates 18 class attributes into a single, immutable configuration.

    Internal Consistency (enforced via __post_init__):
        - If supports_user_progress=False, mastery_threshold is ignored (warning)
        - prerequisite_relationships and enables_relationships should be tuples
        - search_fields should not be empty

    Required Fields:
        dto_class: The DTO class for this domain (e.g., TaskDTO)
        model_class: The domain model class (e.g., Task)

    Optional Fields (with sensible defaults):
        entity_label: Neo4j label (auto-inferred from model_class if None)
        service_name: Logger name prefix (e.g., "tasks.search")
        date_field: Field for date range queries (default: "created_at")
        completed_statuses: Status values indicating completion
        search_fields: Fields for text search (default: ["title", "description"])
        search_order_by: Default sort field (default: "created_at")
        category_field: Field for category filtering (default: "category")
        graph_enrichment_patterns: Relationship patterns for graph context
        user_ownership_relationship: Relationship type for ownership (None for shared)
        prerequisite_relationships: Relationship types for prerequisites
        enables_relationships: Relationship types for enables chain
        supports_user_progress: Whether domain supports mastery tracking

    Example:
        ```python
        from core.services.domain_config import DomainConfig
        from core.models.task.task import Task
        from core.models.task.task_dto import TaskDTO
        from core.models.relationship_registry import (
            generate_graph_enrichment,
            generate_prerequisite_relationships,
            generate_enables_relationships,
        )

        TASKS_CONFIG = DomainConfig(
            dto_class=TaskDTO,
            model_class=Task,
            service_name="tasks.search",
            date_field="due_date",
            completed_statuses=("completed",),
            graph_enrichment_patterns=tuple(generate_graph_enrichment("Task")),
            prerequisite_relationships=tuple(
                generate_prerequisite_relationships("Task")
            ),
            enables_relationships=tuple(generate_enables_relationships("Task")),
            supports_user_progress=True,
        )
        ```
    """

    # Required: DTO and Model classes
    dto_class: type[Any]  # type[DTOProtocol] - relaxed for compatibility
    model_class: type[Any]  # type[DomainModelProtocol] - relaxed for compatibility

    # Entity Identity
    entity_label: str | None = None  # Auto-inferred from model_class.__name__ if None
    service_name: str | None = None  # Logger name prefix

    # Date Range Queries
    date_field: str = "created_at"
    completed_statuses: tuple[str, ...] = ()

    # Text Search
    search_fields: tuple[str, ...] = ("title", "description")
    search_order_by: str = "created_at"
    category_field: str = "category"

    # Graph-Aware Search
    graph_enrichment_patterns: tuple[tuple[str, str, str, str], ...] = ()
    user_ownership_relationship: str | None = RelationshipName.OWNS  # None for shared content (KU)

    # Prerequisites & Curriculum
    prerequisite_relationships: tuple[str, ...] = ()
    enables_relationships: tuple[str, ...] = ()
    content_field: str = "content"
    mastery_threshold: float = 0.7
    supports_user_progress: bool = False

    def __post_init__(self) -> None:
        """
        Validate internal consistency of configuration.

        Makes DomainConfig a truth enforcer, not just a container.
        Catches logical contradictions at configuration time.
        """
        # Validate: search_fields should not be empty
        if not self.search_fields or len(self.search_fields) == 0:
            raise ValueError(
                f"DomainConfig for {self.get_entity_label()}: search_fields cannot be empty. "
                f"Provide at least one field for text search."
            )

        # Validate: mastery_threshold is meaningless without progress tracking
        if not self.supports_user_progress and self.mastery_threshold != 0.7:
            # Use object.__setattr__ because dataclass is frozen
            import warnings

            warnings.warn(
                f"DomainConfig for {self.get_entity_label()}: mastery_threshold={self.mastery_threshold} "
                f"is set but supports_user_progress=False. The threshold will be ignored.",
                UserWarning,
                stacklevel=2,
            )

        # Validate: relationship fields should be tuples (enforce immutability)
        if self.prerequisite_relationships and not isinstance(
            self.prerequisite_relationships, tuple
        ):
            raise TypeError(
                f"DomainConfig for {self.get_entity_label()}: prerequisite_relationships must be a tuple, "
                f"got {type(self.prerequisite_relationships).__name__}"
            )

        if self.enables_relationships and not isinstance(self.enables_relationships, tuple):
            raise TypeError(
                f"DomainConfig for {self.get_entity_label()}: enables_relationships must be a tuple, "
                f"got {type(self.enables_relationships).__name__}"
            )

        if self.graph_enrichment_patterns and not isinstance(self.graph_enrichment_patterns, tuple):
            raise TypeError(
                f"DomainConfig for {self.get_entity_label()}: graph_enrichment_patterns must be a tuple, "
                f"got {type(self.graph_enrichment_patterns).__name__}"
            )

        # NOTE: We do NOT validate user_ownership_relationship=None + supports_user_progress=True
        # This is VALID for curriculum domains (KU, LS, LP) where progress is tracked via
        # relationships: (User)-[HAS_MASTERY {score}]->(KU), not entity properties.

    def get_entity_label(self) -> str:
        """
        Get entity label, inferring from model_class if not set.

        Returns:
            Entity label string (e.g., "Task", "Goal")
        """
        if self.entity_label:
            return self.entity_label
        if self.model_class:
            return self.model_class.__name__
        return "Entity"

    def get_service_name(self) -> str:
        """
        Get service name for logging.

        Returns:
            Service name string (e.g., "tasks.search")
        """
        if self.service_name:
            return self.service_name
        # Infer from model class
        label = self.get_entity_label().lower()
        return f"{label}.service"


# ============================================================================
# PRE-DEFINED CONFIGURATIONS
# ============================================================================
# These can be imported by services instead of defining inline.
# Import relationship registries when defining these.


def create_activity_domain_config(
    dto_class: type[Any],
    model_class: type[Any],
    domain_name: str,
    date_field: str = "created_at",
    completed_statuses: tuple[str, ...] = (),
    category_field: str = "category",
    search_fields: tuple[str, ...] | None = None,
    search_order_by: str | None = None,
    entity_label: str | None = None,
) -> DomainConfig:
    """
    Factory for creating Activity Domain configurations.

    Uses centralized relationship registry for graph patterns.

    **FAIL-FAST (2026-01-31):** Validates entity exists in all registries at configuration time.

    Args:
        dto_class: The DTO class
        model_class: The domain model class
        domain_name: Domain name (e.g., "tasks", "goals")
        date_field: Field for date queries
        completed_statuses: Status values indicating completion
        category_field: Field for category filtering
        search_fields: Fields for text search (default: ["title", "description"])
        search_order_by: Default sort field (default: "created_at")
        entity_label: Neo4j node label override (default: model_class.__name__).
            Use when model_class is a domain subclass (e.g., Task) but the
            Neo4j label remains the base type (e.g., "Ku").

    Returns:
        Configured DomainConfig for the activity domain

    Raises:
        ValueError: If entity not found in required registries
    """
    # Import here to avoid circular imports
    from core.models.relationship_registry import (
        LABEL_CONFIGS,
        generate_enables_relationships,
        generate_graph_enrichment,
        generate_prerequisite_relationships,
    )

    entity_label = (
        entity_label or getattr(model_class, "_neo4j_label", None) or model_class.__name__
    )

    # FAIL-FAST: Validate entity exists in unified registry
    if entity_label not in LABEL_CONFIGS:
        raise ValueError(
            f"Entity '{entity_label}' not found in LABEL_CONFIGS. "
            f"Add to /core/models/relationship_registry.py before creating DomainConfig."
        )

    return DomainConfig(
        dto_class=dto_class,
        model_class=model_class,
        entity_label=entity_label,
        service_name=f"{domain_name}.search",
        date_field=date_field,
        completed_statuses=completed_statuses,
        category_field=category_field,
        search_fields=search_fields or ("title", "description"),
        search_order_by=search_order_by or "created_at",
        graph_enrichment_patterns=tuple(generate_graph_enrichment(entity_label)),
        prerequisite_relationships=tuple(generate_prerequisite_relationships(entity_label)),
        enables_relationships=tuple(generate_enables_relationships(entity_label)),
        user_ownership_relationship=RelationshipName.OWNS,
        supports_user_progress=True,
    )


def create_curriculum_domain_config(
    dto_class: type[Any],
    model_class: type[Any],
    domain_name: str,
    search_fields: tuple[str, ...] | None = None,
    search_order_by: str = "updated_at",
    category_field: str = "domain",
    content_field: str = "content",
    supports_user_progress: bool = True,
    user_ownership_relationship: str | None = None,
    prerequisite_relationships: tuple[str, ...] | None = None,
    enables_relationships: tuple[str, ...] | None = None,
    entity_label: str | None = None,
) -> DomainConfig:
    """
    Factory for creating Curriculum Domain configurations.

    Curriculum domains (KU, LS, LP, MOC) are shared content without user ownership.

    **FAIL-FAST (2026-01-31):** Validates entity exists in registries when using defaults.

    Args:
        dto_class: The DTO class
        model_class: The domain model class
        domain_name: Domain name (e.g., "ku", "ls", "lp")
        search_fields: Fields for text search (default: ["title", "description"])
        search_order_by: Default sort field (default: "updated_at" for curriculum)
        category_field: Field for category filtering (default: "domain")
        content_field: Field containing main content (default: "content")
        supports_user_progress: Whether domain supports mastery tracking (default: True)
        user_ownership_relationship: Ownership relationship type (default: None for shared)
        prerequisite_relationships: Override relationship types for prerequisites (default: from registry)
        enables_relationships: Override relationship types for enables (default: from registry)
        entity_label: Neo4j node label override (default: model_class.__name__).
            Use when model_class is a domain subclass but the Neo4j label
            remains the base type.

    Returns:
        Configured DomainConfig for the curriculum domain

    Raises:
        ValueError: If entity not found in registries when using defaults
    """
    from core.models.relationship_registry import (
        LABEL_CONFIGS,
        generate_enables_relationships,
        generate_graph_enrichment,
        generate_prerequisite_relationships,
    )

    entity_label = (
        entity_label or getattr(model_class, "_neo4j_label", None) or model_class.__name__
    )

    # FAIL-FAST: Validate entity exists in unified registry
    if entity_label not in LABEL_CONFIGS:
        raise ValueError(
            f"Entity '{entity_label}' not found in LABEL_CONFIGS. "
            f"Add to /core/models/relationship_registry.py before creating DomainConfig."
        )

    # Use provided relationships or fall back to unified registry
    final_prerequisite_relationships = (
        prerequisite_relationships
        if prerequisite_relationships is not None
        else tuple(generate_prerequisite_relationships(entity_label))
    )
    final_enables_relationships = (
        enables_relationships
        if enables_relationships is not None
        else tuple(generate_enables_relationships(entity_label))
    )

    return DomainConfig(
        dto_class=dto_class,
        model_class=model_class,
        entity_label=entity_label,
        service_name=f"{domain_name}.search",
        search_fields=search_fields or ("title", "description"),
        search_order_by=search_order_by,
        category_field=category_field,
        content_field=content_field,
        graph_enrichment_patterns=tuple(generate_graph_enrichment(entity_label)),
        prerequisite_relationships=final_prerequisite_relationships,
        enables_relationships=final_enables_relationships,
        user_ownership_relationship=user_ownership_relationship,
        supports_user_progress=supports_user_progress,
    )
