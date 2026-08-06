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

from typing import TYPE_CHECKING, Any, Literal, Protocol, TypedDict, overload, runtime_checkable

from core.models.type_hints import EntityUID, Neo4jProperties, Neo4jValue, UserUID

if TYPE_CHECKING:
    import builtins
    import logging
    from datetime import date, datetime

    from core.models.enums import Priority, SearchVisibility
    from core.models.enums.neo_labels import NeoLabel
    from core.models.protocols.domain_model_protocol import DomainModelProtocol
    from core.models.relationship_filters import RelationshipFilters
    from core.models.relationship_names import RelationshipName
    from core.models.type_hints import FilterParams
    from core.ports.query_types import (
        PrerequisiteChainRow,
        RelationshipRow,
        TraversalNodeRow,
    )
    from core.utils.result_simplified import Result as ResultType
    # Note: the ``Result`` Protocol in this module is for duck-typing Result-like
    # objects; ``ResultType`` is the actual Result[T] class used in annotations.
    # (Was "defined at line 866" — already 420 lines stale before this change;
    # naming the symbol instead of a line number is what stops it re-rotting.)


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
    essentiality: str  # SUPPORTS_GOAL tier: essential / critical / supporting / optional


class HierarchyContextRaw(TypedDict):
    """
    Typed result from get_hierarchy_raw() — full parent-child hierarchy context.

    Always contains all three keys; each list holds raw Neo4j node property dicts.
    The service layer converts these to typed domain models.

    Keys:
        ancestors: Root-to-parent path (excludes the entity itself), ordered by depth DESC.
        siblings: Other children of the same parent.
        children: Immediate children of the entity.
    """

    ancestors: list[Neo4jProperties]
    siblings: list[Neo4jProperties]
    children: list[Neo4jProperties]


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
        - UnifiedRelationshipService for cross-domain context usage pattern
    """

    # Required graph traversal fields (present in all results)
    uid: str
    labels: list[str]
    distance: int
    path_strength: float
    via_relationships: list[str]

    # Incident-edge attribution (the last hop, the edge incident to this node).
    # Categorization buckets a node by the relationship + orientation of THIS edge,
    # so attribution stays correct at any distance (not just direct connections).
    incident_rel_type: str
    incident_into_related: bool  # True: edge points INTO this node (node is the object)
    # Properties of the incident edge — lets categorization route a node to a
    # property-filtered mapping (e.g. SUPPORTS_GOAL {essentiality} habit tiers).
    incident_rel_properties: Neo4jProperties

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

    def model_dump(self, *, exclude_none: bool = False) -> dict[str, Any]:
        """Dump model to dictionary.

        ``exclude_none`` is the whole keyword surface the two consumers use
        (``ConversionServiceV2.create_to_pure`` passes it; ``to_dict`` below
        calls it bare). A real ``pydantic.BaseModel`` still satisfies this —
        its extra keywords all have defaults.
        """
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
class EnumLike[V = str | int | float](Protocol):
    """Protocol for enum-like objects with a value attribute.

    ``value`` is a read-only property, not a mutable attribute: ``Enum.value``
    is a descriptor, so a settable-attribute protocol does not match an enum
    statically (it only ever matched at runtime, where ``runtime_checkable``
    just tests for the name). Parameterising it is what lets
    ``get_enum_value`` hand the member's value type back to its caller; the
    ``str | int | float`` default keeps bare ``EnumLike`` narrowing as before.
    """

    @property
    def value(self) -> V: ...


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
        properties: Neo4jProperties | None = None,
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
        properties: Neo4jProperties | None = None,
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

    async def create_relationship(
        self,
        from_uid: str,
        to_uid: str,
        relationship_type: RelationshipName,
        properties: Neo4jProperties | None = None,
    ) -> ResultType[bool]:
        """Attach a registry-validated edge between two entities, idempotently.

        Safe to retry: a repeat call updates the one edge of this type between
        this pair rather than adding a second, and merges ``properties`` into
        whatever the edge already carries — keys absent from this call survive,
        keys present win. Edge identity is (source, type, target) only, so
        properties never fork it.

        Both entities must ALREADY exist; this creates the edge, never the
        endpoints. Invalid pairs fail hard rather than silently no-op: the
        relationship type must be legal for the source's domain and the target's
        label must match the registry's spec for it.

        Args:
            from_uid: Source entity UID
            to_uid: Target entity UID
            relationship_type: Neo4j relationship type (validated against the registry)
            properties: Optional edge properties

        Returns:
            Result[bool] - True if created/updated
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

    async def update(self, uid: str, updates: Neo4jProperties) -> ResultType[T]:
        """Update an existing entity."""
        ...

    async def delete(self, uid: str, cascade: bool = False) -> ResultType[bool]:
        """Delete an entity."""
        ...

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
        filters: FilterParams | None = None,
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

    async def find_by(
        self, limit: int = 100, **filters: Neo4jValue
    ) -> ResultType[builtins.list[T]]:
        """Find entities matching dynamic filters.

        Filter values reach the driver as query parameters, so they are
        Neo4j scalars — ``Neo4jValue``, not ``FilterValue``: real call sites
        pass ``date``/``datetime`` (``due_date__gte=date.today()``).
        """
        ...

    async def count(self, **filters: Neo4jValue) -> ResultType[int]:
        """Count entities matching filters."""
        ...

    async def find_by_date_range(
        self,
        start_date: "date | str | None",
        end_date: "date | str | None",
        date_field: str = "occurred_at",
        additional_filters: "FilterParams | None" = None,
        limit: int = 100,
    ) -> ResultType[builtins.list[T]]:
        """Find entities whose ``date_field`` falls in [start_date, end_date].

        Distinct from ``find_by(field__gte=...)``, and not interchangeable with it:
        the stored value is coerced (``date(left(toString(n.field), 10))``) before
        comparing, so this matches a field held as an ISO string, an ISO datetime
        string, or a native temporal alike. A bare ``>=`` against a string bound
        evaluates to null on temporally-stored rows and silently drops them.
        Prefer this for any window over a mixed-representation field.
        """
        ...

    async def get_user_entities(
        self,
        user_uid: UserUID,
        relationship_type: RelationshipName | None = None,
        filters: FilterParams | None = None,
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

    # ========================================================================
    # Typed Search Operations (April 2026)
    # Backend methods that encapsulate Cypher construction + execution.
    # Service mixins call these instead of importing query builders directly.
    # ========================================================================

    async def text_search_raw(
        self,
        query_text: str,
        search_fields: tuple[str, ...],
        *,
        limit: int = 50,
        order_by: str = "created_at",
        order_desc: bool = True,
        user_uid: UserUID | None = None,
        visibility: SearchVisibility | None = None,
    ) -> ResultType[builtins.list[dict[str, Any]]]:
        """Text search across specified fields, returning raw dicts."""
        ...

    async def relationship_traversal_raw(
        self,
        source_uid: str,
        relationship_type: str,
        target_label: NeoLabel,
        direction: Direction = "outgoing",
    ) -> ResultType[builtins.list[dict[str, Any]]]:
        """Traverse a graph relationship and return raw target node dicts."""
        ...

    async def graph_aware_search_raw(
        self,
        query_text: str,
        source_uid: str,
        relationship_type: str,
        search_fields: tuple[str, ...],
        *,
        direction: Direction = "outgoing",
        limit: int = 50,
        order_by: str = "created_at",
        order_desc: bool = True,
        user_uid: UserUID | None = None,
        visibility: SearchVisibility | None = None,
    ) -> ResultType[builtins.list[dict[str, Any]]]:
        """Combined text search + relationship traversal in one query."""
        ...

    async def array_any_match_raw(
        self,
        field: str,
        values: builtins.list[str],
        *,
        match_all: bool = False,
        limit: int = 50,
        order_by: str = "created_at",
        order_desc: bool = True,
        user_uid: UserUID | None = None,
        visibility: SearchVisibility | None = None,
    ) -> ResultType[builtins.list[dict[str, Any]]]:
        """Search array field for ANY/ALL of the given values."""
        ...

    async def array_contains_raw(
        self,
        field: str,
        value: str,
        *,
        limit: int = 50,
        order_by: str = "created_at",
        order_desc: bool = True,
    ) -> ResultType[builtins.list[dict[str, Any]]]:
        """Search array field for a single value."""
        ...

    async def distinct_values_raw(
        self,
        field: str,
        user_uid: UserUID | None = None,
    ) -> ResultType[builtins.list[dict[str, Any]]]:
        """Get distinct values (with occurrence counts) for a field, optionally user-scoped."""
        ...

    async def faceted_search_raw(
        self,
        user_uid: UserUID | None,
        *,
        user_ownership_relationship: RelationshipName | None,
        search_fields: tuple[str, ...],
        search_order_by: str,
        graph_enrichment_patterns: tuple[tuple[str, ...], ...],
        property_filters: dict[str, Any],
        query_text: str | None = None,
        relationship_filters: RelationshipFilters | None = None,
        tags_contain: builtins.list[str] | None = None,
        tags_match_all: bool = False,
        order_by: str | None = None,
        order_desc: bool = True,
        limit: int = 50,
        offset: int = 0,
        visibility: SearchVisibility | None = None,
    ) -> ResultType[builtins.list[dict[str, Any]]]:
        """Graph-aware faceted search with ownership, filters, and enrichment.

        The Cypher for ``relationship_filters`` is authored below the boundary
        (ADR-044); callers pass only the active-flag intent. ``user_uid`` may
        be None for PUBLIC-visibility domains (anonymous browse); the service
        layer fails closed before reaching here for OWNER_ONLY domains.
        ``order_by``/``order_desc`` override the domain's ``search_order_by``
        DESC default (SearchSortOrder plumbing).
        """
        ...

    async def user_activity_range_raw(
        self,
        user_uid: UserUID,
        date_field: str | builtins.list[str],
        start_date: date,
        end_date: date,
        exclude_statuses: builtins.list[str] | None = None,
    ) -> ResultType[builtins.list[dict[str, Any]]]:
        """Query user entities within a date range.

        A list of date fields uses OR semantics: an entity matches when ANY
        of the fields falls inside the range.
        """
        ...

    async def upcoming_raw(
        self,
        date_field: str,
        days_ahead: int = 7,
        *,
        exclude_statuses: builtins.list[str] | None = None,
        user_uid: UserUID | None = None,
        limit: int = 100,
        secondary_sort_field: str | None = None,
    ) -> ResultType[builtins.list[dict[str, Any]]]:
        """Query entities upcoming within N days."""
        ...

    async def overdue_raw(
        self,
        date_field: str,
        *,
        exclude_statuses: builtins.list[str] | None = None,
        user_uid: UserUID | None = None,
        limit: int = 100,
        secondary_sort_field: str | None = None,
    ) -> ResultType[builtins.list[dict[str, Any]]]:
        """Query entities past their due date."""
        ...

    async def active_raw(
        self,
        user_uid: UserUID,
        *,
        exclude_statuses: builtins.list[str] | None = None,
        limit: int = 100,
    ) -> ResultType[builtins.list[dict[str, Any]]]:
        """Query user's active (non-terminal) entities."""
        ...

    async def prerequisite_traversal(
        self,
        uid: str,
        relationship_types: builtins.list[str],
        depth: int = 3,
        direction: Direction = "outgoing",
    ) -> ResultType[builtins.list[T]]:
        """Traverse prerequisite relationships and return typed domain models."""
        ...

    async def prerequisite_chain_with_distance(
        self,
        uid: str,
        relationship_types: builtins.list[str],
        depth: int = 3,
    ) -> ResultType[builtins.list[PrerequisiteChainRow]]:
        """Traverse the prerequisite chain, returning projected distance-annotated rows.

        Heterogeneous by design (Ku and PathStep), so rows are projected fields
        (uid/title/domain/entity_type/distance), not single-type domain models.
        """
        ...

    async def hierarchy_query_raw(
        self,
        uid: str,
    ) -> ResultType[builtins.list[dict[str, Any]]]:
        """Get hierarchical structure for an entity."""
        ...

    async def context_query_raw(
        self,
        uid: str,
        *,
        include_relationships: builtins.list[str] | None = None,
        exclude_relationships: builtins.list[str] | None = None,
        default_confidence: float = 0.7,
    ) -> ResultType[builtins.list[dict[str, Any]]]:
        """Registry-driven context query for entity with graph neighborhood."""
        ...

    async def basic_context_query_raw(
        self,
        uid: str,
        prereq_rels: str,
        min_confidence: float = 0.7,
    ) -> ResultType[builtins.list[dict[str, Any]]]:
        """Basic 3-relationship context query for unregistered entities."""
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
        properties: Neo4jProperties | None = None,
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
    ) -> ResultType[builtins.list[RelationshipRow]]:
        """Get relationships for an entity — raw edge rows, not domain models."""
        ...

    async def has_relationship(
        self, from_uid: str, to_uid: str, relationship_type: RelationshipName
    ) -> ResultType[bool]:
        """Check if a relationship exists between two entities."""
        ...

    async def create_relationships_batch(
        self, relationships: builtins.list[tuple[str, str, str, Neo4jProperties | None]]
    ) -> ResultType[int]:
        """Create multiple relationships in a single transaction."""
        ...

    async def get_owner_uids_batch(
        self, uids: builtins.list[str]
    ) -> ResultType[dict[str, builtins.list[str]]]:
        """Owners of each node, for many nodes in one query (uid -> owning user UIDs).

        Resolves all three spellings of ownership — ``user_uid`` (UserOwnedEntity),
        ``owner_uid`` (Exercise, Group) and the ``OWNS`` edge. Only owned nodes appear:
        shared content (Ku, PathStep, LearningPath) has none of the three and is absent.
        Callers turning request-supplied UIDs into edges use this to refuse cross-user
        endpoints, asking whether the caller is AMONG the owners.
        """
        ...

    async def create_extracted_from_links(
        self, entry_uid: str, links: builtins.list[tuple[str, str, str | None]]
    ) -> ResultType[int]:
        """Batch-write ``(created)-[:EXTRACTED_FROM]->(entry)`` provenance edges.

        ``links`` is ``(created_uid, source_line_hash, vault_id)`` triples (ADR-070).
        Backend: ``_RelationshipCrudMixin.create_extracted_from_links``.
        """
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
        properties: Neo4jProperties,
    ) -> ResultType[bool]:
        """Update specific properties on a relationship edge."""
        ...

    async def get_relationships_batch(
        self, relationships: builtins.list[tuple[str, str, str]]
    ) -> ResultType[builtins.list[RelationshipMetadata]]:
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
        properties: Neo4jProperties | None = None,
    ) -> ResultType[int]:
        """Count related entities via relationship pattern."""
        ...

    async def get_related_uids(
        self,
        uid: str,
        relationship_type: RelationshipName,
        direction: Direction = "outgoing",
        limit: int = 100,
        properties: Neo4jProperties | None = None,
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
    ) -> ResultType[builtins.list[TraversalNodeRow]]:
        """Traverse the graph following a relationship pattern.

        Returns the flat set of nodes reached — ``uid``/``labels``/``depth``
        (+ ``properties`` when ``include_properties``) — not paths.
        """
        ...

    async def get_domain_context_raw(
        self,
        entity_uid: EntityUID,
        entity_label: NeoLabel,
        relationship_types: builtins.list[str],
        depth: int = 2,
        min_confidence: float = 0.7,
        bidirectional: bool = False,
    ) -> ResultType[builtins.list[GraphContextNode]]:
        """Get raw graph context for cross-domain intelligence analysis."""
        ...

    async def find_uids_by_semantic_filter(
        self,
        pattern: str,
        target_uid: str,
        min_confidence: float,
        semantic_type_values: builtins.list[str] | None = None,
    ) -> ResultType[builtins.list[str]]:
        """Find entity UIDs matching a semantic relationship pattern."""
        ...

    async def get_batch_cross_domain_context(
        self,
        entity_label: NeoLabel,
        entity_uids: builtins.list[str],
    ) -> ResultType[builtins.list[dict[str, Any]]]:
        """Batch-retrieve cross-domain relationship context for entities."""
        ...

    async def get_goal_aligned_entities(
        self,
        user_uid: str,
        domain_name: str,
        entity_label: NeoLabel,
        goal_uid: str | None,
        limit: int,
    ) -> ResultType[builtins.list[dict[str, Any]]]:
        """Get entities aligned with user's goals via goal relationships."""
        ...

    async def get_citation_export(
        self,
        node_uid: str,
        node_label: NeoLabel,
        relationship_type: str,
        depth: int,
    ) -> ResultType[builtins.list[dict[str, Any]]]:
        """Execute a citation/provenance export query."""
        ...


@runtime_checkable
class QueryExecutor(Protocol):
    """
    Port for executing raw Cypher queries against the graph database.

    Use this for services that need direct query access without a typed
    BackendOperations[T] entity backend. Any BackendOperations[T] also
    satisfies this protocol (via LowLevelOperations).

    Implementations:
    - Neo4jQueryExecutor (adapters/persistence/neo4j/) - standalone executor
    - UniversalNeo4jBackend[T] (via LowLevelOperations) - entity backend

    See: /docs/patterns/protocol_architecture.md
    """

    async def execute_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> ResultType[builtins.list[dict[str, Any]]]:
        """Execute a Cypher query, returning records as dicts wrapped in Result."""
        ...


@runtime_checkable
class LowLevelOperations(QueryExecutor, Protocol):
    """
    Low-level infrastructure operations.

    Used by services that need direct database access or health monitoring.
    Use sparingly - prefer higher-level protocols.

    Inherits from QueryExecutor - any LowLevelOperations also satisfies QueryExecutor.
    """

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
# Hierarchy Operations Protocol (sub-entity parent-child relationships)
# ============================================================================


@runtime_checkable
class HierarchyOperations(Protocol):
    """Protocol for backends that support sub-entity hierarchy operations.

    Provides generic parent-child hierarchy management (get children, get parent,
    get full hierarchy, create/remove bidirectional relationships, cycle detection).

    Implemented by ``_HierarchyMixin`` on domain backends. All methods return raw
    dicts — the service layer converts to typed domain models.

    See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
    """

    async def get_children_raw(
        self, parent_uid: str, depth: int = 1
    ) -> ResultType[builtins.list[Neo4jProperties]]:
        """Get child nodes as raw Neo4j property dicts at the given traversal depth."""
        ...

    async def get_parent_raw(self, child_uid: str) -> ResultType[Neo4jProperties | None]:
        """Get immediate parent node as a raw Neo4j property dict, or None if root-level."""
        ...

    async def get_hierarchy_raw(self, entity_uid: EntityUID) -> ResultType[HierarchyContextRaw]:
        """Get full hierarchy context: ancestors, siblings, children as raw dicts."""
        ...

    async def create_hierarchy_relationship(
        self,
        parent_uid: str,
        child_uid: str,
        forward_props: Neo4jProperties | None = None,
    ) -> ResultType[bool]:
        """Create bidirectional parent-child relationship with cycle detection."""
        ...

    async def remove_hierarchy_relationship(
        self, parent_uid: str, child_uid: str
    ) -> ResultType[bool]:
        """Remove bidirectional parent-child relationship."""
        ...

    async def would_create_cycle(self, parent_uid: str, child_uid: str) -> ResultType[bool]:
        """Check if adding parent→child would create a cycle."""
        ...

    async def get_descendant_uids(self, uid: str) -> ResultType[builtins.set[str]]:
        """Get all descendant UIDs reachable via the forward relationship."""
        ...


@runtime_checkable
class HierarchicalBackendOperations[T: "DomainModelProtocol"](
    BackendOperations[T], HierarchyOperations, Protocol
):
    """``BackendOperations`` plus sub-entity ``HierarchyOperations``.

    The type bound for the shared typed-hierarchy service reads (``HierarchyReadMixin``):
    ``get_entity_hierarchy`` needs both ``get`` (CRUD) and ``get_*_raw`` (hierarchy). The
    6 activity domain protocols (TasksOperations, GoalsOperations, …) already compose
    exactly ``BackendOperations`` + ``HierarchyOperations``, so they satisfy this
    structurally; plain ``BackendOperations`` lacks ``get_*_raw`` and cannot be the bound.
    """


# ============================================================================
# Duck-typing Protocols
#
# The generic capability-check tier that once lived here (SupportsPathfinding,
# SupportsSearch, SupportsCount, SupportsHealthCheck, SupportsInsights,
# SupportsRelatedSearch, SupportsSearchWithFilters) plus Repository,
# EventHandler and Service were deleted: zero imports, zero annotations and
# zero isinstance checks anywhere in the tree. (``EventHandler`` now names the
# callable alias in core/ports/infrastructure_protocols.py — real handlers are
# plain functions, never classes with a ``.handle()`` method, which is why the
# protocol had no implementers.) The capability-protocol idiom
# itself is alive and correct — it is served by the domain-specific tier in
# core/ports/search_protocols.py (SupportsGraphAwareSearch,
# SupportsGraphTraversalSearch, SupportsTagSearch), which SearchRouter really
# does isinstance against. The generic tier was superseded, not needed.
# ============================================================================


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
# Utility Helper Functions — SECOND IMPLEMENTATION, not a re-export
# ============================================================================
#
# core/utils/type_converters.py carries its own copy of to_dict /
# get_enum_value / get_enum_attr_str, over its own private protocols
# (_PydanticModel, _EnumLike, ...). Neither file imports the other:
# type_converters would cycle back through this module's protocols, so the
# bodies are duplicated rather than shared. Both copies have live callers
# (~20 import from core.ports, 2 from core.utils.type_converters).
#
# Consequence for anyone editing here: a change to a body or a signature
# below does NOT propagate — mirror it in core/utils/type_converters.py, or
# the two copies drift.
# ============================================================================


def to_dict(obj: object) -> object:
    """
    Universal converter to dictionary format.

    Every branch is an isinstance narrow, so ``object`` accepts exactly what
    ``Any`` did while forbidding unchecked attribute access inside. The return
    is ``object`` because the arms genuinely differ — ``dict[str, Any]`` from
    the four protocol branches, a list from the sequence branch, and the input
    untouched otherwise.

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


@overload
def get_enum_value[V](obj: EnumLike[V]) -> V: ...
@overload
def get_enum_value[T](obj: T) -> T: ...
def get_enum_value(obj: object) -> object:
    """
    Get the value of an enum-like object.

    Two overloads rather than one signature: callers that pass an enum need
    the member's value type back (``GoalCreated.domain: str | None`` and
    ``GraphContext.query_intent: str`` are both fed from here), and callers
    that pass a plain value need it returned unchanged.

    Uses Protocol-based type checking instead of hasattr.
    See core.utils.type_converters.get_enum_value for full documentation.
    """
    if isinstance(obj, EnumLike):
        return obj.value
    return obj


def get_enum_attr_str(obj: object, attr: str, default: str = "") -> str:
    """Extract an attribute as a lowercase string, handling both enum and string values.

    See core.utils.type_converters.get_enum_attr_str for full documentation.
    """
    value = getattr(obj, attr, None)
    if value is None:
        return default
    if isinstance(value, EnumLike):
        return str(value.value).lower()
    return str(value).lower()


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
    # Pydantic Field Constraint Protocols (7)
    "GeConstraint",
    "GraphContextNode",
    # Graph Relationship Operations Protocol (1)
    "GraphRelationshipOperations",
    # Hierarchy Operations (1 TypedDict + 1 Protocol)
    "HierarchyContextRaw",
    "GraphTraversalOperations",  # Graph traversal
    "GtConstraint",
    # Timestamp Protocols (3)
    "HasCreatedAt",
    "HasDict",
    "HasLogger",
    "HasMetadata",
    # Priority/Sorting Protocols (3)
    "HasPriority",
    "HasRelevanceScore",
    # Score/Metrics Protocols (6)
    "HasScore",
    # Query/Optimizer Protocols (3)
    "HasSeverity",
    "HasStrategy",
    "HasSummary",
    "HasToDict",
    "HasToNumeric",
    # Entity Attribute Protocols - Core (6)
    "HasUID",
    "HasUpdated",
    "HasUpdatedAt",
    "HasUsage",
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
    "Result",
    "Serializable",
    "StreaksLike",
    # Backend Capability Protocols (7 - kept used ones)
    # Helper Functions (3)
    "get_enum_attr_str",
    "get_enum_value",
    "to_dict",
]
