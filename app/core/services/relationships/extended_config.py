"""
Extended Relationship Configuration - Full Domain-Specific Specifications
==========================================================================

Extends RelationshipConfig with complete specifications for:
1. Query specs for relationship fetching (TaskRelationships pattern)
2. Cross-domain context type mappings
3. UserContext planning method specs
"""

from dataclasses import dataclass, field
from typing import Any

from core.models.enums import Domain
from core.models.relationship_names import RelationshipName
from core.models.relationship_registry import DomainRelationshipConfig


@dataclass(frozen=True)
class QuerySpec:
    """
    Specification for a relationship query.

    Maps a field name to a service method and relationship type.
    Used by domain relationships containers (TaskRelationships, etc.)
    """

    field_name: str  # e.g., "subtask_uids"
    method_suffix: str  # e.g., "subtasks" → get_task_subtasks
    relationship: RelationshipName  # e.g., HAS_CHILD
    direction: str = "outgoing"


@dataclass(frozen=True)
class PathAwareTypeSpec:
    """
    Specification for a path-aware entity type.

    Maps a domain to its path-aware type class and core fields.
    """

    domain: Domain
    type_name: str  # e.g., "PathAwareTask"
    core_fields: list[tuple[str, str]]  # [(field_name, field_type), ...]


@dataclass(frozen=True)
class CrossContextSpec:
    """
    Specification for a cross-domain context type.

    Defines the structure of domain-specific context containers
    like TaskCrossContext, GoalCrossContext, etc.
    """

    context_type_name: str  # e.g., "TaskCrossContext"
    uid_field: str  # e.g., "task_uid"
    # Field specifications: (field_name, path_aware_type, is_list, relationship_types)
    fields: list[tuple[str, str, bool, list[RelationshipName]]] = field(default_factory=list)


@dataclass(frozen=True)
class PlanningMethodSpec:
    """
    Specification for a UserContext-aware planning method.

    Defines methods like get_actionable_tasks_for_user() that
    leverage UserContext (~240 fields) for filtering and ranking.
    """

    method_name: str  # e.g., "get_actionable_for_user"
    description: str
    # Context fields used from UserContext
    context_fields_used: list[str] = field(default_factory=list)
    # Additional parameters: (name, type, default_value or None)
    parameters: list[tuple[str, type, Any | None]] = field(default_factory=list)


@dataclass(frozen=True)
class ExtendedRelationshipConfig(DomainRelationshipConfig):
    """
    Extended configuration with full domain-specific specifications.

    Adds to base RelationshipConfig:
    - query_specs: For domain relationships container fetching
    - path_aware_spec: For path-aware entity type
    - cross_context_spec: For cross-domain context type
    - planning_method_specs: For UserContext-aware methods
    """

    # Query specs for domain relationships container (TaskRelationships pattern)
    query_specs: list[QuerySpec] = field(default_factory=list)

    # Path-aware type specification
    path_aware_spec: PathAwareTypeSpec | None = None

    # Cross-domain context type specification
    cross_context_spec: CrossContextSpec | None = None

    # UserContext planning method specifications
    planning_method_specs: list[PlanningMethodSpec] = field(default_factory=list)
