"""
Core Protocols for Type Safety
==============================

Protocol-based contracts for dependency injection and type conversion.
ISP-compliant architecture (refactored November 2025).

Protocol Hierarchy
------------------
BackendOperations[T] is THE full backend protocol, composed from 7 sub-protocols:

    BackendOperations[T]  ← UniversalNeo4jBackend implements this
        ├── CrudOperations[T]              (6 methods: create, get, get_many, update, delete, list)
        ├── EntitySearchOperations[T]      (3 methods: search, find_by, count)
        ├── RelationshipCrudOperations     (6 methods: add/delete relationships, batch ops)
        ├── RelationshipMetadataOperations (3 methods: get/update edge properties)
        ├── RelationshipQueryOperations    (3 methods: count_related, get_related_uids, batch)
        ├── GraphTraversalOperations       (2 methods: traverse, get_domain_context_raw)
        └── LowLevelOperations             (2 methods + driver: execute_query, health_check)

Usage
-----
    # Domain protocols inherit from BackendOperations
    class TasksOperations(BackendOperations["Task"], Protocol):
        async def create_task(self, data: Metadata) -> Result[EntityUID]: ...

    # For focused dependencies (ISP), use sub-protocols
    class SimpleReadService:
        def __init__(self, backend: CrudOperations[Task]) -> None:
            self.backend = backend  # Only needs CRUD

See Also
--------
    /docs/patterns/BACKEND_OPERATIONS_ISP.md - Full architecture documentation
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Protocol, TypedDict, runtime_checkable

if TYPE_CHECKING:
    import builtins
    import logging
    from datetime import datetime

    from core.models.protocols.domain_model_protocol import DomainModelProtocol
    from core.models.relationship_names import RelationshipName
    from core.models.shared_enums import Domain, Priority
    from core.utils.result_simplified import Result as ResultType
    # Note: Result protocol defined at line 866 is for duck-typing Result-like objects
    # ResultType is the actual Result[T] class used in type annotations


# ============================================================================
# Type Aliases for Protocol Signatures
# ============================================================================

# Direction for graph traversal operations
Direction = Literal["outgoing", "incoming", "both"]


class RelationshipMetadata(TypedDict, total=False):
    """
    Type-safe base for relationship edge properties.

    Provides type hints for ~80% of common relationship metadata fields.
    All fields are optional (total=False) since relationships have
    heterogeneous properties depending on type.

    Common patterns in SKUEL relationships:
    - Strength metrics: confidence, strength, *_strength, *_score
    - Timestamps: created_at, updated_at (ISO format strings)
    - Categorization: *_type fields (str)

    Usage:
        metadata: RelationshipMetadata = result.value
        confidence = metadata.get("confidence", 0.0)  # Type-safe access

    Note:
        Additional domain-specific properties (e.g., milestone_uid,
        funding_type) are still accessible via dict access but won't
        have IDE autocomplete. This is an intentional trade-off to
        avoid an explosion of domain-specific TypedDicts.
    """

    # Core confidence/strength metrics (most common)
    confidence: float
    strength: float

    # Timestamps (ISO 8601 format strings)
    created_at: str
    updated_at: str

    # Common domain-specific strength metrics
    alignment_score: float
    contribution_score: float
    enablement_strength: float
    grounding_strength: float
    guidance_strength: float
    influence_strength: float
    inspiration_strength: float
    reinforcement_strength: float
    support_strength: float

    # Common type categorizations
    contribution_type: str
    dependency_type: str
    support_type: str


class GraphContextNode(TypedDict, total=False):
    """
    Typed representation of graph traversal result from get_domain_context_raw().

    Provides ~90% type safety for cross-domain graph queries while preserving
    flexibility via the raw_properties escape hatch.

    The tension: Cross-domain queries inherently return heterogeneous data.
    Full typing would require a union of all 15 domain models (unwieldy).
    This structural type captures the common graph traversal fields that
    ALL entities share, while raw_properties holds domain-specific data.

    Required fields (total=False but always present in practice):
        uid: Entity UID (e.g., "task:123", "goal:456")
        labels: Neo4j node labels (e.g., ["Task", "Activity"])
        distance: Hops from source entity (1 = direct connection)
        path_strength: Confidence cascade (product of relationship confidences)
        via_relationships: Relationship path with direction markers

    Common optional fields:
        title: Entity title (most entities have this)
        entity_type: EntityType value if available

    Escape hatch:
        raw_properties: Domain-specific data not covered above

    Usage:
        result = await backend.get_domain_context_raw(...)
        for node in result.value:
            uid = node["uid"]  # Type-safe: str
            labels = node["labels"]  # Type-safe: list[str]
            # Domain-specific access still works but without autocomplete:
            domain_data = node.get("raw_properties", {})

    See Also:
        - core/models/graph/path_aware_types.py for domain-specific typed wrappers
        - TasksRelationshipService.get_task_cross_domain_context() for usage pattern
    """

    # Required graph traversal fields (present in all results)
    uid: str
    labels: list[str]
    distance: int
    path_strength: float
    via_relationships: list[str]

    # Common optional fields (present in most entities)
    title: str
    entity_type: str  # EntityType.value when available

    # Escape hatch for domain-specific properties
    raw_properties: dict[str, Any]


# ============================================================================
# Core Conversion Protocols (USED: adapters, services)
# ============================================================================


@runtime_checkable
class PydanticModel(Protocol):
    """Protocol for Pydantic models with model_dump method."""

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Dump model to dictionary."""
        ...


@runtime_checkable
class HasDict(Protocol):
    """Protocol for objects that can be converted to dict."""

    def dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        ...


@runtime_checkable
class HasToDict(Protocol):
    """Protocol for objects with to_dict method."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        ...


@runtime_checkable
class Serializable(Protocol):
    """Protocol for objects that can be serialized to dict."""

    def serialize(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        ...


@runtime_checkable
class EnumLike(Protocol):
    """Protocol for enum-like objects with a value attribute."""

    value: str | int | float


# ============================================================================
# Attribute Protocols (USED: type checking in services)
# ============================================================================


@runtime_checkable
class HasUID(Protocol):
    """Protocol for objects with a UID."""

    uid: str


@runtime_checkable
class HasMetadata(Protocol):
    """Protocol for objects with metadata."""

    metadata: dict[str, Any]


@runtime_checkable
class HasSummary(Protocol):
    """Protocol for objects with summary field."""

    summary: str | None


@runtime_checkable
class HasMetrics(Protocol):
    """Protocol for objects with metrics attribute."""

    metrics: Any


@runtime_checkable
class HasStreaks(Protocol):
    """Protocol for objects with streaks attribute."""

    streaks: Any


@runtime_checkable
class MetricsLike(Protocol):
    """Protocol for metrics objects with common attributes."""

    completion_percentage: float
    mastery_level: float
    practice_count: int
    time_spent_minutes: float
    quality_score: float


@runtime_checkable
class StreaksLike(Protocol):
    """Protocol for streak objects with success_rate."""

    success_rate: float


@runtime_checkable
class HasUpdated(Protocol):
    """Protocol for objects with updated field."""

    updated: datetime | str | None


@runtime_checkable
class HasUpdatedAt(Protocol):
    """Protocol for objects with updated_at timestamp."""

    updated_at: datetime | str | None


@runtime_checkable
class HasParentUID(Protocol):
    """Protocol for objects with parent UID."""

    parent_uid: str | None


@runtime_checkable
class HasBody(Protocol):
    """Protocol for response objects with body attribute."""

    body: bytes


@runtime_checkable
class HasScore(Protocol):
    """Protocol for objects with score attribute."""

    score: float


@runtime_checkable
class HasRelevanceScore(Protocol):
    """Protocol for objects with relevance_score attribute."""

    relevance_score: float


@runtime_checkable
class HasToNumeric(Protocol):
    """Protocol for enum-like objects with to_numeric method."""

    def to_numeric(self) -> int:
        """Convert to numeric representation."""
        ...


@runtime_checkable
class IsMockEndpoint(Protocol):
    """Protocol for functions decorated with @mock_endpoint."""

    _is_mock_endpoint: bool


@runtime_checkable
class IsStubEndpoint(Protocol):
    """Protocol for functions decorated with @stub_endpoint."""

    _is_stub_endpoint: bool


@runtime_checkable
class HasLogger(Protocol):
    """Protocol for objects with a logger attribute."""

    logger: logging.Logger


@runtime_checkable
class HasCreatedAt(Protocol):
    """Protocol for objects with created_at timestamp."""

    created_at: datetime | str | None


@runtime_checkable
class HasValidate(Protocol):
    """Protocol for objects with validate method."""

    def validate(self) -> Any:
        """Validate this object."""
        ...


@runtime_checkable
class HasStrategy(Protocol):
    """Protocol for objects with strategy attribute."""

    strategy: Any


@runtime_checkable
class HasSeverity(Protocol):
    """Protocol for objects with severity attribute."""

    severity: str


@runtime_checkable
class HasUsage(Protocol):
    """Protocol for objects with usage attribute."""

    usage: str


@runtime_checkable
class HasPriority(Protocol):
    """Protocol for objects with priority attribute."""

    priority: Priority | int | str


@runtime_checkable
class HasDomain(Protocol):
    """Protocol for objects with domain attribute."""

    domain: Domain | str


@runtime_checkable
class HasRelationships(Protocol):
    """Protocol for objects with relationships attribute."""

    relationships: Any


@runtime_checkable
class HasSemanticRelationships(Protocol):
    """Protocol for objects with semantic_relationships attribute."""

    semantic_relationships: Any


@runtime_checkable
class HasKnowledgeUnit(Protocol):
    """Protocol for objects with knowledge_unit attribute."""

    knowledge_unit: Any


@runtime_checkable
class HasKnowledgeMasteryCheck(Protocol):
    """Protocol for objects with knowledge_mastery_check attribute."""

    knowledge_mastery_check: Any


@runtime_checkable
class HasPrerequisiteKnowledgeUids(Protocol):
    """Protocol for objects with prerequisite_knowledge_uids attribute."""

    prerequisite_knowledge_uids: tuple[str, ...] | list[str]


@runtime_checkable
class HasAppliesKnowledgeUids(Protocol):
    """Protocol for objects with applies_knowledge_uids attribute."""

    applies_knowledge_uids: tuple[str, ...] | list[str]


# ============================================================================
# Streak & Consistency Protocols (USED: habits tracking)
# ============================================================================


@runtime_checkable
class HasConsistencyScore(Protocol):
    """Protocol for objects with consistency_score field."""

    consistency_score: float


@runtime_checkable
class HasStreakCount(Protocol):
    """Protocol for objects with streak_count field."""

    streak_count: int


@runtime_checkable
class HasStreak(Protocol):
    """Protocol for objects with streak attribute."""

    streak: int


# ============================================================================
# Graph Relationship Query Operations Protocol (DRY consolidation)
# ============================================================================


@runtime_checkable
class GraphRelationshipOperations(Protocol):
    """
    Protocol for graph relationship query operations.

    Consolidates the get_related_uids() and count_related() methods that were
    duplicated across 6 domain protocols (Tasks, Events, Habits, Goals, Choices,
    Principles).

    These methods query graph edges without retrieving full entity data - useful
    for relationship counting, UID collection, and lightweight graph traversal.

    Domain protocols that need these operations should inherit from this protocol:
        class TasksOperations(BackendOperations["Task"], GraphRelationshipOperations, Protocol):
            ...

    Date Added: November 29, 2025 (DRY consolidation)
    """

    async def get_related_uids(
        self,
        uid: str,
        relationship_type: RelationshipName,
        direction: Direction = "outgoing",
        limit: int = 100,
        properties: dict[str, Any] | None = None,
    ) -> ResultType[builtins.list[str]]:
        """Get UIDs of related entities via specific relationship type.

        Args:
            uid: Entity UID
            relationship_type: Neo4j relationship type (e.g., RelationshipName.APPLIES_KNOWLEDGE)
            direction: "outgoing", "incoming", or "both"
            limit: Max results to return (default 100)
            properties: Optional dict of relationship properties to filter by

        Returns:
            Result[list[str]] - List of related entity UIDs
        """
        ...

    async def count_related(
        self,
        uid: str,
        relationship_type: RelationshipName,
        direction: Direction = "outgoing",
        properties: dict[str, Any] | None = None,
    ) -> ResultType[int]:
        """Count related entities via specific relationship type.

        Args:
            uid: Entity UID
            relationship_type: Neo4j relationship type (e.g., RelationshipName.APPLIES_KNOWLEDGE)
            direction: "outgoing", "incoming", or "both"
            properties: Optional dict of relationship properties to filter by

        Returns:
            Result[int] - Count of related entities
        """
        ...


# ============================================================================
# Composable Backend Protocols (ISP-compliant decomposition)
# ============================================================================
#
# BackendOperations was a "god protocol" with 25+ methods. These smaller
# protocols follow the Interface Segregation Principle (ISP):
#
# 1. CrudOperations[T] - Basic CRUD (create, get, update, delete, list)
# 2. EntitySearchOperations[T] - Entity search (search, find_by, count)
# 3. RelationshipCrudOperations - Relationship CRUD (add, delete, batch)
# 4. RelationshipMetadataOperations - Edge properties (get/update metadata)
# 5. RelationshipQueryOperations - Relationship queries (count_related, get_related_uids)
# 6. GraphTraversalOperations - Graph traversal (traverse, get_domain_context_raw)
# 7. LowLevelOperations - Infrastructure (execute_query, health_check)
#
# BackendOperations composes all of these for backward compatibility.
# Services can depend on just the protocols they need for better testability.
# ============================================================================


@runtime_checkable
class CrudOperations[T: "DomainModelProtocol"](Protocol):
    """
    Core CRUD operations for domain entities.

    The fundamental operations every backend must support.
    This is the minimal protocol for entity persistence.

    Type Parameter:
        T: Domain model type (must implement DomainModelProtocol)
    """

    async def create(self, entity: T) -> ResultType[T]:
        """Create a new entity."""
        ...

    async def get(self, uid: str) -> ResultType[T | None]:
        """Get entity by UID."""
        ...

    async def get_many(self, uids: builtins.list[str]) -> ResultType[builtins.list[T | None]]:
        """Get multiple entities by UIDs in a single batched query."""
        ...

    async def update(self, uid: str, updates: dict[str, Any]) -> ResultType[T]:
        """Update an existing entity."""
        ...

    async def delete(self, uid: str, cascade: bool = False) -> ResultType[bool]:
        """Delete an entity."""
        ...

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
        sort_by: str | None = None,
        sort_order: str = "asc",
    ) -> ResultType[tuple[builtins.list[T], int]]:
        """List entities with pagination and filtering."""
        ...


@runtime_checkable
class EntitySearchOperations[T: "DomainModelProtocol"](Protocol):
    """
    Search and query operations for entities.

    Used by services that need to search/filter entities.
    """

    async def search(self, query: str, limit: int = 10) -> ResultType[builtins.list[T]]:
        """Search for entities by text query."""
        ...

    async def find_by(self, limit: int = 100, **filters: Any) -> ResultType[builtins.list[T]]:
        """Find entities matching dynamic filters."""
        ...

    async def count(self, **filters: Any) -> ResultType[int]:
        """Count entities matching filters."""
        ...

    async def get_user_entities(
        self,
        user_uid: str,
        relationship_type: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: str | None = None,
        sort_order: str = "desc",
    ) -> ResultType[tuple[builtins.list[T], int]]:
        """
        Get all entities for a user via relationship traversal.

        Args:
            user_uid: User UID
            relationship_type: Optional relationship type filter
            filters: Optional filters on entity properties
            limit: Max results
            offset: Pagination offset
            sort_by: Field to sort by
            sort_order: 'asc' or 'desc'

        Returns:
            Result[tuple[list[T], int]]: Tuple of (entities, total_count)
        """
        ...


@runtime_checkable
class RelationshipCrudOperations(Protocol):
    """
    CRUD operations for graph relationships (edges).

    Used by relationship services that create/delete edges.
    """

    async def add_relationship(
        self,
        from_uid: str,
        to_uid: str,
        relationship_type: RelationshipName,
        properties: dict[str, Any] | None = None,
    ) -> ResultType[bool]:
        """
        Add a relationship between two entities.

        Args:
            from_uid: Source entity UID
            to_uid: Target entity UID
            relationship_type: Type of relationship (from RelationshipName enum)
            properties: Optional relationship properties (e.g., confidence, strength)

        Returns:
            Result[bool]: True if relationship was created/updated
        """
        ...

    async def get_relationships(
        self, uid: str, rel_type: RelationshipName | None = None, direction: Direction = "both"
    ) -> Any:
        """Get relationships for an entity."""
        ...

    async def has_relationship(
        self, from_uid: str, to_uid: str, relationship_type: RelationshipName
    ) -> ResultType[bool]:
        """Check if a relationship exists between two entities."""
        ...

    async def create_relationships_batch(
        self, relationships: builtins.list[tuple[str, str, str, dict[str, Any] | None]]
    ) -> ResultType[int]:
        """Create multiple relationships in a single transaction."""
        ...

    async def delete_relationship(
        self, from_uid: str, to_uid: str, relationship_type: RelationshipName
    ) -> ResultType[bool]:
        """Delete a single relationship between two entities."""
        ...

    async def delete_relationships_batch(
        self, relationships: builtins.list[tuple[str, str, str]]
    ) -> ResultType[int]:
        """Delete multiple relationships in a single transaction."""
        ...


@runtime_checkable
class RelationshipMetadataOperations(Protocol):
    """
    Operations for relationship edge properties/metadata.

    Used by services that need to read/update relationship properties
    (confidence scores, timestamps, etc.).
    """

    async def get_relationship_metadata(
        self, from_uid: str, to_uid: str, relationship_type: RelationshipName
    ) -> ResultType[RelationshipMetadata | None]:
        """Get properties stored on a relationship edge."""
        ...

    async def update_relationship_properties(
        self,
        from_uid: str,
        to_uid: str,
        relationship_type: RelationshipName,
        properties: dict[str, Any],
    ) -> ResultType[bool]:
        """Update specific properties on a relationship edge."""
        ...

    async def get_relationships_batch(
        self, relationships: builtins.list[tuple[str, str, str]]
    ) -> ResultType[builtins.list[dict[str, Any]]]:
        """Get metadata for multiple relationships in a single query."""
        ...


@runtime_checkable
class RelationshipQueryOperations(Protocol):
    """
    Query operations for graph relationships.

    Used by services that need to count or list related entities
    without loading full entity data.
    """

    async def count_related(
        self,
        uid: str,
        relationship_type: RelationshipName,
        direction: Direction = "outgoing",
        properties: dict[str, Any] | None = None,
    ) -> ResultType[int]:
        """Count related entities via relationship pattern."""
        ...

    async def get_related_uids(
        self,
        uid: str,
        relationship_type: RelationshipName,
        direction: Direction = "outgoing",
        limit: int = 100,
        properties: dict[str, Any] | None = None,
    ) -> ResultType[builtins.list[str]]:
        """Get UIDs of related entities via graph edge traversal."""
        ...

    async def count_relationships_batch(
        self, requests: builtins.list[tuple[str, str, str | None]]
    ) -> ResultType[dict[tuple[str, str, str], int]]:
        """Count multiple relationship patterns in a single query."""
        ...


@runtime_checkable
class GraphTraversalOperations(Protocol):
    """
    Graph traversal operations for path finding and context queries.

    Used by intelligence services that need to traverse the graph
    to find related context across domains.
    """

    async def traverse(
        self, start_uid: str, rel_pattern: str, max_depth: int = 3, include_properties: bool = False
    ) -> Any:
        """Traverse the graph following a relationship pattern."""
        ...

    async def get_domain_context_raw(
        self,
        entity_uid: str,
        entity_label: str,
        relationship_types: builtins.list[str],
        depth: int = 2,
        min_confidence: float = 0.7,
        bidirectional: bool = False,
    ) -> ResultType[builtins.list[GraphContextNode]]:
        """Get raw graph context for cross-domain intelligence analysis."""
        ...


@runtime_checkable
class LowLevelOperations(Protocol):
    """
    Low-level infrastructure operations.

    Used by services that need direct database access or health monitoring.
    Use sparingly - prefer higher-level protocols.
    """

    driver: Any  # Neo4j AsyncDriver (implementation-specific)

    async def execute_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> ResultType[builtins.list[dict[str, Any]]]:
        """Execute a low-level Cypher query."""
        ...

    async def health_check(self) -> ResultType[bool]:
        """Check backend health."""
        ...


# ============================================================================
# BackendOperations - THE Full Backend Protocol
# ============================================================================


@runtime_checkable
class BackendOperations[T: "DomainModelProtocol"](
    CrudOperations[T],
    EntitySearchOperations[T],
    RelationshipCrudOperations,
    RelationshipMetadataOperations,
    RelationshipQueryOperations,
    GraphTraversalOperations,
    LowLevelOperations,
    Protocol,
):
    """
    Full backend operations protocol for SKUEL domain backends.

    This is THE protocol that UniversalNeo4jBackend implements.
    Domain protocols (TasksOperations, GoalsOperations, etc.) inherit from this.

    Composed from 7 focused sub-protocols (ISP-compliant):
    - CrudOperations[T]: create, get, get_many, update, delete, list
    - EntitySearchOperations[T]: search, find_by, count
    - RelationshipCrudOperations: add/delete relationships, batch ops
    - RelationshipMetadataOperations: edge properties
    - RelationshipQueryOperations: count_related, get_related_uids
    - GraphTraversalOperations: traverse, get_domain_context_raw
    - LowLevelOperations: execute_query, health_check, driver

    Usage:
        # Domain protocols inherit from BackendOperations
        class TasksOperations(BackendOperations["Task"], Protocol):
            async def create_task(self, data: Metadata) -> Result[EntityUID]: ...

        # Services use domain protocols or BackendOperations directly
        class TasksService(BaseService[BackendOperations[Task], Task]):
            pass

        # For focused dependencies, use sub-protocols directly
        class SimpleReadService:
            def __init__(self, backend: CrudOperations[Task]) -> None:
                self.backend = backend  # Only needs CRUD

    Type Parameter:
        T: Domain model type (must implement DomainModelProtocol)
    """

    # All methods inherited from composed protocols
    pass


# ============================================================================
# Capability Check Protocols (for runtime isinstance checks)
# These are @runtime_checkable for duck-typing capability detection
# ============================================================================


@runtime_checkable
class SupportsRelationships(Protocol):
    """Protocol for backends that support relationship operations."""

    async def add_relationship(
        self,
        from_uid: str,
        to_uid: str,
        relationship_type: RelationshipName,
        properties: dict[str, Any] | None = None,
    ) -> Any:
        """Add a relationship between entities."""
        ...

    async def get_relationships(self, uid: str, direction: Direction = "both") -> Any:
        """Get relationships for an entity."""
        ...


@runtime_checkable
class SupportsTraversal(Protocol):
    """Protocol for backends that support graph traversal."""

    async def traverse(
        self, start_uid: str, rel_pattern: str, max_depth: int = 3, include_properties: bool = False
    ) -> Any:
        """Traverse the graph from a starting point."""
        ...


@runtime_checkable
class SupportsPathfinding(Protocol):
    """Protocol for backends that support pathfinding."""

    async def find_path(
        self, from_uid: str, to_uid: str, rel_types: list[str], max_depth: int = 5
    ) -> Any:
        """Find a path between two entities."""
        ...


@runtime_checkable
class SupportsSearch(Protocol):
    """Protocol for backends that support search operations."""

    async def search(self, query: str, **filters: Any) -> Any:
        """Search for entities."""
        ...


@runtime_checkable
class SupportsCount(Protocol):
    """Protocol for backends that support counting."""

    async def count(self, **filters: Any) -> ResultType[int]:
        """Count entities matching filters."""
        ...


@runtime_checkable
class SupportsHealthCheck(Protocol):
    """Protocol for backends that support health checking."""

    async def health_check(self) -> ResultType[bool]:
        """Check backend health."""
        ...


@runtime_checkable
class SupportsFacets(Protocol):
    """Protocol for search backends that support faceted search."""

    async def get_facets(self, query: str, **filters: Any) -> Any:
        """Get facets for search results."""
        ...


@runtime_checkable
class SupportsInsights(Protocol):
    """Protocol for search backends that support insights generation."""

    async def get_insights(self, query: str, **filters: Any) -> Any:
        """Get insights for search results."""
        ...


@runtime_checkable
class SupportsRelatedSearch(Protocol):
    """Protocol for search backends that support related searches."""

    async def get_related(self, query: str, **filters: Any) -> Any:
        """Get related searches."""
        ...


@runtime_checkable
class SupportsSearchWithFilters(Protocol):
    """Protocol for search backends that support advanced filtering."""

    async def search_with_filters(self, query: str, filters: dict[str, Any], **options: Any) -> Any:
        """Search with advanced filters."""
        ...


# ============================================================================
# Base Service Protocols (USED: service architecture)
# ============================================================================


@runtime_checkable
class Repository(Protocol):
    """Protocol for repository objects."""

    def get(self, uid: str) -> Any:
        """Get entity by UID."""
        ...

    def save(self, entity: Any) -> Any:
        """Save entity."""
        ...


@runtime_checkable
class EventHandler(Protocol):
    """Protocol for event handlers."""

    async def handle(self, event: Any) -> None:
        """Handle an event."""
        ...


@runtime_checkable
class Service(Protocol):
    """Base protocol for services."""

    async def start(self) -> None:
        """Start the service."""
        ...

    async def stop(self) -> None:
        """Stop the service."""
        ...


@runtime_checkable
class Result(Protocol):
    """Protocol for Result-like objects (duck-typing for Result[T])."""

    is_ok: bool
    is_error: bool
    value: Any
    error: Any


# ============================================================================
# Pydantic Field Constraint Protocols (USED: validators)
# ============================================================================


@runtime_checkable
class PydanticFieldInfo(Protocol):
    """Protocol for Pydantic v2 FieldInfo with metadata list."""

    description: str | None
    metadata: list[Any]  # List of constraint objects (annotated_types)


@runtime_checkable
class MinLenConstraint(Protocol):
    """Protocol for Pydantic MinLen constraint."""

    min_length: int


@runtime_checkable
class MaxLenConstraint(Protocol):
    """Protocol for Pydantic MaxLen constraint."""

    max_length: int


@runtime_checkable
class GeConstraint(Protocol):
    """Protocol for Pydantic Ge (greater than or equal) constraint."""

    ge: float


@runtime_checkable
class LeConstraint(Protocol):
    """Protocol for Pydantic Le (less than or equal) constraint."""

    le: float


@runtime_checkable
class GtConstraint(Protocol):
    """Protocol for Pydantic Gt (greater than) constraint."""

    gt: float


@runtime_checkable
class LtConstraint(Protocol):
    """Protocol for Pydantic Lt (less than) constraint."""

    lt: float


@runtime_checkable
class MaxItemsConstraint(Protocol):
    """Protocol for Pydantic MaxItems constraint (array/list size limit)."""

    max_items: int


# ============================================================================
# Utility Helper Functions (re-exported from core.utils.type_converters)
# ============================================================================
#
# These functions are implemented in core/utils/type_converters.py and
# re-exported here for backward compatibility. New code should import from:
#
#     from core.utils.type_converters import to_dict, get_enum_value
#
# Why the separation:
# - Protocols define contracts (what an object CAN do)
# - Utilities implement behavior (HOW to convert objects)
# - This file should focus on Protocol definitions
#
# Note: We can't import from type_converters here due to circular imports
# (type_converters imports protocols from this file). Instead, we define
# the functions here and type_converters re-implements them.
# ============================================================================


def to_dict(obj: Any) -> Any:
    """
    Universal converter to dictionary format.

    Uses Protocol-based type checking instead of hasattr.
    See core.utils.type_converters.to_dict for full documentation.
    """
    if isinstance(obj, PydanticModel):
        return obj.model_dump()
    elif isinstance(obj, HasDict):
        return obj.dict()
    elif isinstance(obj, HasToDict):
        return obj.to_dict()
    elif isinstance(obj, Serializable):
        return obj.serialize()
    elif isinstance(obj, dict):
        return obj
    elif isinstance(obj, list | tuple):
        return [to_dict(item) for item in obj]
    else:
        return obj


def get_enum_value(obj: Any) -> Any:
    """
    Get the value of an enum-like object.

    Uses Protocol-based type checking instead of hasattr.
    See core.utils.type_converters.get_enum_value for full documentation.
    """
    if isinstance(obj, EnumLike):
        return obj.value
    return obj


# ============================================================================
# EXPLICIT EXPORTS - ISP-compliant protocols (streamlined Nov 2025)
# NOTE: Deepgram protocols moved to adapters/external/deepgram/
# NOTE: Helper functions also available from core.utils.type_converters
# ============================================================================

__all__ = [
    # ========== COMPOSED BACKEND PROTOCOL (1 - backward compatible) ==========
    "BackendOperations",  # Composes all 7 above
    # ========== COMPOSABLE BACKEND PROTOCOLS (7 - ISP-compliant) ==========
    "CrudOperations",  # Basic CRUD
    # Type Aliases (3)
    "Direction",
    "EntitySearchOperations",  # Search/filter
    # Core Conversion Protocols (5)
    "EnumLike",
    # Base Service Protocols (4)
    "EventHandler",
    # Pydantic Field Constraint Protocols (7)
    "GeConstraint",
    "GraphContextNode",
    # Graph Relationship Operations Protocol (1)
    "GraphRelationshipOperations",
    "GraphTraversalOperations",  # Graph traversal
    "GtConstraint",
    "HasAppliesKnowledgeUids",
    "HasBody",
    # Streak & Consistency Protocols (3)
    "HasConsistencyScore",
    # Timestamp Protocols (3)
    "HasCreatedAt",
    "HasDict",
    # Domain/Relationship Protocols (4)
    "HasDomain",
    # Knowledge Mastery Protocols (3)
    "HasKnowledgeMasteryCheck",
    "HasKnowledgeUnit",
    "HasLogger",
    "HasMetadata",
    "HasMetrics",
    "HasParentUID",
    "HasPrerequisiteKnowledgeUids",
    # Priority/Sorting Protocols (3)
    "HasPriority",
    "HasRelationships",
    "HasRelevanceScore",
    # Score/Metrics Protocols (6)
    "HasScore",
    "HasSemanticRelationships",
    # Query/Optimizer Protocols (3)
    "HasSeverity",
    "HasStrategy",
    "HasStreak",
    "HasStreakCount",
    "HasStreaks",
    "HasSummary",
    "HasToDict",
    "HasToNumeric",
    # Entity Attribute Protocols - Core (6)
    "HasUID",
    "HasUpdated",
    "HasUpdatedAt",
    "HasUsage",
    "HasValidate",
    # Mock/Stub Endpoint Protocols (2)
    "IsMockEndpoint",
    "IsStubEndpoint",
    "LeConstraint",
    "LowLevelOperations",  # Direct DB access
    "LtConstraint",
    "MaxLenConstraint",
    "MetricsLike",
    "MinLenConstraint",
    "PydanticFieldInfo",
    "PydanticModel",
    "RelationshipCrudOperations",  # Edge CRUD
    "RelationshipMetadata",
    "RelationshipMetadataOperations",  # Edge properties
    "RelationshipQueryOperations",  # Relationship queries
    "Repository",
    "Result",
    "Serializable",
    "Service",
    "StreaksLike",
    # Backend Capability Protocols (10)
    "SupportsCount",
    "SupportsFacets",
    "SupportsHealthCheck",
    "SupportsInsights",
    "SupportsPathfinding",
    "SupportsRelatedSearch",
    "SupportsRelationships",
    "SupportsSearch",
    "SupportsSearchWithFilters",
    "SupportsTraversal",
    # Helper Functions (2)
    "get_enum_value",
    "to_dict",
]
