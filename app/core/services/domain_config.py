"""
Domain Configuration Dataclass
==============================

Centralized configuration for BaseService behavior.

This module consolidates the 18 class attributes previously scattered
across individual service classes into a single, type-safe dataclass.

**ONE PATH FORWARD (January 2026):**
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
- ✅ All services migrated to DomainConfig (19 core + 6 search = 25 services)
- ✅ Class attribute fallback removed from _get_config_value()

See Also:
    - /core/services/base_service.py - Uses DomainConfig exclusively
    - /core/models/relationship_registry.py - THE single source of truth for relationships
    - /docs/migrations/BASESERVICE_IMPROVEMENTS_2026-01-29.md - Migration guide
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from core.models.enums import SearchVisibility
from core.models.protocols.domain_model_protocol import (
    DomainModelProtocol,
    DTOProtocol,
)
from core.models.relationship_names import RelationshipName
from core.models.type_hints import FilterParams


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
        entity_label: Neo4j base-label for Cypher matching (e.g., "Entity", "Ku").
            Auto-inferred from ``model_class.__name__`` as a last resort.
        config_lookup_label: LABEL_CONFIGS registry key (e.g., "Task", "PathStep").
            Defaults to ``model_class.__name__``. Distinct from ``entity_label``:
            the registry key identifies the domain, the Neo4j label identifies
            how to match in Cypher.
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
    dto_class: type[DTOProtocol]
    model_class: type[DomainModelProtocol]

    # Entity Identity
    entity_label: str | None = (
        None  # Neo4j base-label for multi-label Cypher matching (e.g., "Entity" or "Ku")
    )
    config_lookup_label: str | None = None  # LABEL_CONFIGS registry key (e.g., "Task", "PathStep")
    service_name: str | None = None  # Logger name prefix

    # Date Range Queries
    date_field: str = "created_at"
    completed_statuses: tuple[str, ...] = ()

    # get_for_user_filtered vocabulary: filter-name -> extra find_by kwargs.
    # "all" or any unconfigured name applies no status constraint. Per-domain
    # semantics are preserved exactly here (e.g. Tasks' "active" means NOT
    # completed via status__not_in; Goals' "active" means status == "active").
    status_filters: Mapping[str, FilterParams] = field(default_factory=dict)

    # Text Search
    search_fields: tuple[str, ...] = ("title", "description")
    search_order_by: str = "created_at"
    category_field: str = "category"

    # Graph-Aware Search
    graph_enrichment_patterns: tuple[tuple[str, str, str, str], ...] = ()
    user_ownership_relationship: RelationshipName | None = (
        RelationshipName.OWNS
    )  # None for shared content (KU)

    # Search-result visibility (THE scoping declaration for every search
    # strategy — text, tags, graph traversal, faceted). None derives from
    # user_ownership_relationship via get_search_visibility(); set explicitly
    # only when the derivation is wrong (Exercise: SCOPE_AWARE).
    search_visibility: SearchVisibility | None = None

    # Temporal queries (get_upcoming / get_overdue / get_active)
    temporal_exclude_statuses: tuple[str, ...] = (
        "completed",
        "failed",
        "cancelled",
        "archived",
    )
    temporal_secondary_sort: str | None = None

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

        # Validate: "all" is reserved in status_filters (always means no constraint)
        if "all" in self.status_filters:
            raise ValueError(
                f"DomainConfig for {self.get_entity_label()}: 'all' is reserved in "
                f"status_filters (it always means no status constraint)."
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
        # This is VALID for curriculum domains (KU, PS, LP) where progress is tracked via
        # relationships: (User)-[HAS_MASTERY {score}]->(KU), not entity properties.

    def get_search_visibility(self) -> SearchVisibility:
        """
        Resolve who this domain's entities are visible to in search.

        Explicit ``search_visibility`` wins; otherwise derive from the
        ownership declaration: an ownership relationship means user-owned
        content (OWNER_ONLY), none means shared content (PUBLIC). The
        derivation keeps the two declarations from silently disagreeing —
        only genuinely instance-scoped domains (Exercise) set it explicitly.
        """
        if self.search_visibility is not None:
            return self.search_visibility
        if self.user_ownership_relationship is not None:
            return SearchVisibility.OWNER_ONLY
        return SearchVisibility.PUBLIC

    def get_entity_label(self) -> str:
        """
        Get Neo4j base-label for Cypher matching.

        Returns:
            Neo4j label (e.g., "Entity", "Ku")
        """
        if self.entity_label:
            return self.entity_label
        if self.model_class:
            return self.model_class.__name__
        return "Entity"

    def get_entity_type_value(self) -> str:
        """
        Resolve THE EntityType value this domain configures, from model_class.

        THE canonical vocabulary for search-result ``_domain`` stamping: every
        SearchRouter producer path stamps ``EntityType.value`` so consumers see
        one spelling — not the lowered-label / Services-attr / domain-name
        variants that #536 had to normalize at the render boundary.

        Derived from ``model_class`` via ENTITY_TYPE_CLASS_MAP (the canonical
        EntityType→class map) — never string-munged from a label, and never
        conflated with ``config_lookup_label`` (see memory entity-label-overload:
        the lookup label has two jobs already; do not add a third).

        Returns:
            The EntityType value (e.g., "task", "path_step", "ku").

        Raises:
            ValueError: If ``model_class`` has no EntityType in the map.
        """
        from core.models.entity_types import ENTITY_TYPE_CLASS_MAP

        for entity_type, model_cls in ENTITY_TYPE_CLASS_MAP.items():
            if model_cls is self.model_class:
                return entity_type.value
        raise ValueError(
            f"DomainConfig model_class {self.model_class.__name__!r} has no "
            f"EntityType in ENTITY_TYPE_CLASS_MAP — cannot stamp search _domain."
        )


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
    status_filters: Mapping[str, FilterParams] | None = None,
    category_field: str = "category",
    search_fields: tuple[str, ...] | None = None,
    search_order_by: str | None = None,
    entity_label: str | None = None,
    config_lookup_label: str | None = None,
    temporal_secondary_sort: str | None = None,
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
        status_filters: get_for_user_filtered vocabulary (filter-name -> extra
            find_by kwargs); "all"/unknown names mean no status constraint
        category_field: Field for category filtering
        search_fields: Fields for text search (default: ["title", "description"])
        search_order_by: Default sort field (default: "created_at")
        entity_label: Neo4j base-label for multi-label Cypher matching. Defaults to
            ``"Entity"`` for the unified :Entity scheme.
        config_lookup_label: LABEL_CONFIGS registry key. Defaults to ``model_class.__name__``
            (e.g., ``"Task"``). This is the domain-specific key — distinct from ``entity_label``,
            which is the Neo4j base-label.
        temporal_secondary_sort: Secondary sort field for get_upcoming/get_overdue
            (e.g., "start_time" for Events)

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

    entity_label = entity_label or "Entity"
    config_lookup_label = config_lookup_label or model_class.__name__

    # FAIL-FAST: Validate lookup key exists in unified registry
    if config_lookup_label not in LABEL_CONFIGS:
        raise ValueError(
            f"Entity '{config_lookup_label}' not found in LABEL_CONFIGS. "
            f"Add to /core/models/relationship_registry.py before creating DomainConfig."
        )

    return DomainConfig(
        dto_class=dto_class,
        model_class=model_class,
        entity_label=entity_label,
        config_lookup_label=config_lookup_label,
        service_name=f"{domain_name}.search",
        date_field=date_field,
        completed_statuses=completed_statuses,
        status_filters=status_filters or {},
        category_field=category_field,
        search_fields=search_fields or ("title", "description"),
        search_order_by=search_order_by or "created_at",
        graph_enrichment_patterns=tuple(generate_graph_enrichment(config_lookup_label)),
        prerequisite_relationships=tuple(generate_prerequisite_relationships(config_lookup_label)),
        enables_relationships=tuple(generate_enables_relationships(config_lookup_label)),
        user_ownership_relationship=RelationshipName.OWNS,
        supports_user_progress=True,
        temporal_secondary_sort=temporal_secondary_sort,
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
    user_ownership_relationship: RelationshipName | None = None,
    prerequisite_relationships: tuple[str, ...] | None = None,
    enables_relationships: tuple[str, ...] | None = None,
    entity_label: str | None = None,
    config_lookup_label: str | None = None,
) -> DomainConfig:
    """
    Factory for creating Curriculum Domain configurations.

    Curriculum domains (KU, PS, LP, MOC) are shared content without user ownership.

    **FAIL-FAST (2026-01-31):** Validates entity exists in registries when using defaults.

    Args:
        dto_class: The DTO class
        model_class: The domain model class
        domain_name: Domain name (e.g., "ku", "ps", "lp")
        search_fields: Fields for text search (default: ["title", "description"])
        search_order_by: Default sort field (default: "updated_at" for curriculum)
        category_field: Field for category filtering (default: "domain")
        content_field: Field containing main content (default: "content")
        supports_user_progress: Whether domain supports mastery tracking (default: True)
        user_ownership_relationship: Ownership relationship type (default: None for shared)
        prerequisite_relationships: Override relationship types for prerequisites (default: from registry)
        enables_relationships: Override relationship types for enables (default: from registry)
        entity_label: Neo4j base-label for Cypher matching (defaults to ``"Entity"``,
            or ``"Ku"`` for Ku which has its own Neo4j label).
        config_lookup_label: LABEL_CONFIGS registry key. Defaults to ``model_class.__name__``
            (e.g., ``"PathStep"``, ``"LearningPath"``, ``"Ku"``).

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

    entity_label = entity_label or "Entity"
    config_lookup_label = config_lookup_label or model_class.__name__

    # FAIL-FAST: Validate lookup key exists in unified registry
    if config_lookup_label not in LABEL_CONFIGS:
        raise ValueError(
            f"Entity '{config_lookup_label}' not found in LABEL_CONFIGS. "
            f"Add to /core/models/relationship_registry.py before creating DomainConfig."
        )

    # Use provided relationships or fall back to unified registry
    final_prerequisite_relationships = (
        prerequisite_relationships
        if prerequisite_relationships is not None
        else tuple(generate_prerequisite_relationships(config_lookup_label))
    )
    final_enables_relationships = (
        enables_relationships
        if enables_relationships is not None
        else tuple(generate_enables_relationships(config_lookup_label))
    )

    return DomainConfig(
        dto_class=dto_class,
        model_class=model_class,
        entity_label=entity_label,
        config_lookup_label=config_lookup_label,
        service_name=f"{domain_name}.search",
        search_fields=search_fields or ("title", "description"),
        search_order_by=search_order_by,
        category_field=category_field,
        content_field=content_field,
        graph_enrichment_patterns=tuple(generate_graph_enrichment(config_lookup_label)),
        prerequisite_relationships=final_prerequisite_relationships,
        enables_relationships=final_enables_relationships,
        user_ownership_relationship=user_ownership_relationship,
        supports_user_progress=supports_user_progress,
    )
