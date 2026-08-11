"""
Shared Types for Cypher Query Generation
=========================================

Common type definitions used across all cypher query modules.

Type Categories
---------------
1. **RelationshipSpec** - Graph traversal specifications
2. **CypherQueryParams** - Low-level Cypher parameters
3. **NodePropertySpec** - Node property definitions
4. **ReturnClauseSpec** - RETURN clause configuration

See Also
--------
    /core/ports/query_types.py - Higher-level service TypedDicts
    /docs/patterns/query_architecture.md - Query architecture documentation

Date Updated: January 2026 (Type Safety Improvements)
"""

from collections.abc import Sequence
from typing import Literal, TypedDict, TypeVar

from core.models.enums.neo_labels import NeoLabel
from core.models.type_hints import UserUID


class RelationshipSpec(TypedDict, total=False):
    """
    Type-safe specification for relationship traversal in graph context queries.

    Required fields:
        rel_types: Relationship type(s), pipe-separated (e.g., "BLOCKS|DEPENDS_ON")
        target_label: Target node label (e.g., "Task", "Entity")
        alias: Result alias (e.g., "dependencies", "applied_knowledge")

    Optional fields:
        direction: "incoming", "outgoing", or "both" (default "outgoing")
        fields: Fields to return (default: ["uid", "title"])
        use_confidence: Apply confidence filtering (default False)
        include_rel_type: Include relationship type in results (default False)
        single: Expect single result vs list (default False)
        limit: Max related results to collect (omit for unlimited)
        filter_property/filter_value: Restrict to edges whose property equals a value
            (e.g. SUPPORTS_GOAL with essentiality="essential"). Both must be set together;
            the value is parameterized, the property name is identifier-validated.
    """

    rel_types: str
    target_label: NeoLabel
    alias: str
    direction: str
    fields: Sequence[str]
    use_confidence: bool
    include_rel_type: bool
    single: bool
    limit: int
    filter_property: str
    filter_value: str


class CypherQueryParams(TypedDict, total=False):
    """
    Low-level Cypher query parameters for execute_query().

    These are the raw parameters passed to Neo4j driver's execute_query().
    For service-level type hints, use CypherParams from query_types.py.

    Common Parameters:
        uid: Entity UID
        user_uid: User UID
        label: Node label for MATCH
        limit: LIMIT value
        offset: SKIP value

    Filter Parameters:
        status: Status filter
        priority: Priority filter
        category: Category filter
        domain: Domain filter

    Date Parameters:
        start_date: Range start (ISO string)
        end_date: Range end (ISO string)
        created_after: Created date filter
        created_before: Created date filter

    Text Search:
        query_text: Text search query (lowercased)
        search_pattern: CONTAINS pattern
    """

    uid: str
    user_uid: UserUID
    label: NeoLabel
    limit: int
    offset: int
    status: str
    priority: str
    category: str
    domain: str
    start_date: str
    end_date: str
    created_after: str
    created_before: str
    query_text: str
    search_pattern: str


class NodePropertySpec(TypedDict, total=False):
    """
    Specification for node properties in CREATE/MERGE operations.

    Used by the cypher/ build_* functions for type-safe property setting.

    Identity:
        uid: Entity UID (required for most operations)
        user_uid: Owner user UID (for Activity domains)

    Common Properties:
        title: Entity title
        description: Entity description
        status: Current status
        created_at: ISO timestamp
        updated_at: ISO timestamp

    Domain-Specific (examples):
        priority: For Tasks
        due_date: For Tasks, Goals
        frequency: For Habits
    """

    uid: str
    user_uid: UserUID
    title: str
    description: str
    status: str
    created_at: str
    updated_at: str
    priority: str
    due_date: str
    frequency: str


class ReturnClauseSpec(TypedDict, total=False):
    """
    Specification for RETURN clause configuration.

    Used by query builders to configure what data to return.

    Fields:
        alias: Variable alias in query (e.g., "n", "entity")
        properties: List of properties to return (None = all)
        as_name: Rename in result (e.g., "entity" AS "task")
        include_labels: Include node labels in result
        include_id: Include internal Neo4j ID
    """

    alias: str
    properties: list[str] | None
    as_name: str
    include_labels: bool
    include_id: bool


class MatchClauseSpec(TypedDict, total=False):
    """
    Specification for MATCH clause configuration.

    Used by query builders to configure node matching.

    Node Specification:
        label: Node label (e.g., "Task")
        alias: Variable name in query (e.g., "n")
        properties: Properties to match on

    Relationship Specification:
        rel_type: Relationship type (e.g., "OWNS")
        rel_alias: Relationship variable name
        rel_direction: "outgoing", "incoming", or "both"
        target_label: Target node label
        target_alias: Target node variable name
    """

    label: NeoLabel
    alias: str
    properties: dict[str, str | int | float | bool]
    rel_type: str
    rel_alias: str
    rel_direction: Literal["outgoing", "incoming", "both"]
    target_label: NeoLabel
    target_alias: str


class OrderByClauseSpec(TypedDict, total=False):
    """
    Specification for ORDER BY clause.

    Fields:
        field: Property to sort by (e.g., "created_at")
        alias: Node alias if needed (e.g., "n.created_at")
        direction: "ASC" or "DESC" (default "ASC")
        nulls: NULL handling: "FIRST" or "LAST"
    """

    field: str
    alias: str
    direction: Literal["ASC", "DESC"]
    nulls: Literal["FIRST", "LAST"]


T = TypeVar("T")


# ============================================================================
# EXPLICIT EXPORTS
# ============================================================================

__all__ = [
    # Graph Traversal
    "RelationshipSpec",
    # Query Parameters
    "CypherQueryParams",
    # Node/Property Specs
    "NodePropertySpec",
    "ReturnClauseSpec",
    "MatchClauseSpec",
    "OrderByClauseSpec",
    # TypeVar
    "T",
]
