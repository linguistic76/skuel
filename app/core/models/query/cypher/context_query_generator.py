"""
Context Query Generator - Registry-Driven Graph Context Queries
================================================================

Generates graph context queries from RelationshipRegistry,
eliminating domain-specific build_*_with_context() functions.

**January 2026 Consolidation:**

Previously, each domain had its own `build_*_with_context()` function:
- build_task_with_context()
- build_goal_with_context()
- build_ku_with_context()
- ... (7 total, ~590 lines)

This module replaces ALL of them with a single function that reads
relationship definitions from RelationshipRegistry.

**Shared-Neighbor Patterns (January 2026):**

The generator now supports shared-neighbor patterns for finding related
entities through shared connections. For example, finding related tasks
that share the same knowledge or goals:

```cypher
OPTIONAL MATCH (entity)-[:APPLIES_KNOWLEDGE|FULFILLS_GOAL]->(shared)
              <-[:APPLIES_KNOWLEDGE|FULFILLS_GOAL]-(related:Task)
WHERE related <> entity
WITH entity, ...,
     collect(DISTINCT {uid: related.uid, ...})[0..5] as related_tasks
```

**Usage:**
```python
from core.models.query.cypher.context_query_generator import generate_context_query

# Generate Task context query
query, params = generate_context_query("Task")

# Generate with filtered relationships
query, params = generate_context_query(
    "Task",
    include_relationships=["applied_knowledge", "goal_context"],
)
```

**See Also:**
    - /core/models/relationship_registry.py - THE single source
    - /core/models/query/cypher/domain_queries.py - build_entity_with_context() engine
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .domain_queries import build_entity_with_context

if TYPE_CHECKING:
    from collections.abc import Sequence

    from core.models.relationship_registry import (
        DomainRelationshipConfig,
        UnifiedRelationshipDefinition,
    )


def _get_registry() -> dict[str, DomainRelationshipConfig]:
    """Lazy import to avoid circular dependency."""
    from core.models.relationship_registry import LABEL_CONFIGS

    return LABEL_CONFIGS


def generate_context_query(
    entity_label: str,
    include_relationships: Sequence[str] | None = None,
    exclude_relationships: Sequence[str] | None = None,
    default_confidence: float = 0.7,
) -> tuple[str, dict[str, Any]]:
    """
    Generate a context query from the RelationshipRegistry.

    This is THE function that replaces all domain-specific build_*_with_context()
    functions. It reads relationship definitions from the registry and generates
    Cypher queries using the generic build_entity_with_context() engine.

    Args:
        entity_label: Neo4j label (e.g., "Task", "Goal", "Ku")
        include_relationships: Only include these relationship context_field_names
                              (None = all relationships)
        exclude_relationships: Exclude these relationship context_field_names
                              (None = exclude none)
        default_confidence: Default confidence threshold for relationships
                           with use_confidence=True

    Returns:
        Tuple of (cypher_query, parameters)

    Raises:
        ValueError: If entity_label not found in registry

    Example:
        # Generate full Task context query
        query, params = generate_context_query("Task")

        # Generate partial query with only knowledge relationships
        query, params = generate_context_query(
            "Task",
            include_relationships=["applied_knowledge", "required_knowledge"],
        )

        # Generate query excluding certain relationships
        query, params = generate_context_query(
            "Goal",
            exclude_relationships=["essential_habits", "critical_habits", "optional_habits"],
        )
    """
    config = _get_registry().get(entity_label)
    if not config:
        raise ValueError(
            f"No registry config for label: {entity_label}. "
            f"Valid labels: {list(_get_registry().keys())}"
        )

    return _generate_from_config(
        config=config,
        include_relationships=include_relationships,
        exclude_relationships=exclude_relationships,
        default_confidence=default_confidence,
    )


def _build_shared_neighbor_clause(
    rel_def: UnifiedRelationshipDefinition,
    clause_index: int,
    with_vars: list[str],
) -> tuple[str, str]:
    """
    Build a shared-neighbor Cypher clause for finding related entities.

    The pattern finds entities of the same type that share common connections
    through specified relationship types. Uses proper aggregation to count
    shared connections before collecting.

    Args:
        rel_def: The relationship definition with shared_neighbor_config
        clause_index: Index for unique variable naming
        with_vars: Current WITH variables to carry forward

    Returns:
        Tuple of (cypher_clause, alias) where:
        - cypher_clause: The OPTIONAL MATCH...WITH clause(s)
        - alias: The result alias to add to RETURN
    """
    config = rel_def.shared_neighbor_config
    if not config:
        return "", ""

    # Build the relationship pattern (e.g., "APPLIES_KNOWLEDGE|FULFILLS_GOAL")
    rel_pattern = config.get_relationship_pattern()

    # Check if shared_count is requested
    has_shared_count = "shared_count" in config.result_fields

    # Build field collection for the result (excluding shared_count initially)
    field_parts = []
    for field in config.result_fields:
        if field == "shared_count":
            # Will be added after aggregation
            field_parts.append("shared_count: shared_count")
        else:
            field_parts.append(f"{field}: related{clause_index}.{field}")

    fields_str = ", ".join(field_parts)

    # Build the clause
    # Pattern: (entity)-[:REL1|REL2]->(shared)<-[:REL1|REL2]-(related:TargetLabel)
    prev_vars = ", ".join(with_vars)
    alias = config.result_alias

    clause_parts = [
        f"OPTIONAL MATCH (entity)-[:{rel_pattern}]->(shared{clause_index})"
        f"<-[:{rel_pattern}]-(related{clause_index}:{config.target_label})",
        f"WHERE related{clause_index} <> entity",
    ]

    if has_shared_count:
        # Two-step aggregation: first count shared per related, then collect
        # Step 1: Group by related entity and count shared connections
        clause_parts.append(
            f"WITH {prev_vars}, related{clause_index}, count(DISTINCT shared{clause_index}) as shared_count"
        )
        # Step 2: Collect the results with shared_count
        collect_expr = f"collect(DISTINCT {{{fields_str}}})[0..{config.limit}] as {alias}"
        clause_parts.append(f"WITH {prev_vars}, {collect_expr}")
    else:
        # Simple collect without shared_count
        collect_expr = f"collect(DISTINCT {{{fields_str}}})[0..{config.limit}] as {alias}"
        clause_parts.append(f"WITH {prev_vars}, {collect_expr}")

    return "\n".join(clause_parts), alias


def _generate_from_config(
    config: DomainRelationshipConfig,
    include_relationships: Sequence[str] | None = None,
    exclude_relationships: Sequence[str] | None = None,
    default_confidence: float = 0.7,
) -> tuple[str, dict[str, Any]]:
    """
    Generate context query from a DomainRelationshipConfig.

    Internal helper that handles relationship filtering and spec generation.
    Supports both standard relationships and shared-neighbor patterns.
    """
    # Start with all relationships
    relationships = list(config.relationships)

    # Apply include filter
    if include_relationships is not None:
        relationships = [r for r in relationships if r.context_field_name in include_relationships]

    # Apply exclude filter
    if exclude_relationships is not None:
        relationships = [
            r for r in relationships if r.context_field_name not in exclude_relationships
        ]

    # Separate regular relationships from shared-neighbor patterns
    regular_relationships = [r for r in relationships if r.shared_neighbor_config is None]
    shared_neighbor_relationships = [
        r for r in relationships if r.shared_neighbor_config is not None
    ]

    # Convert regular relationships to RelationshipSpec list
    specs = [r.to_relationship_spec() for r in regular_relationships]

    # Generate base query using the generic engine
    base_query, parameters = build_entity_with_context(
        entity_label=config.entity_label,
        relationships=specs,
        default_confidence=default_confidence,
    )

    # If no shared-neighbor patterns, return the base query
    if not shared_neighbor_relationships:
        return base_query, parameters

    # Extract current WITH variables from the base query
    # The base query ends with "RETURN entity, alias1, alias2, ..."
    # We need to insert shared-neighbor clauses before RETURN
    lines = base_query.strip().split("\n")
    return_line = lines[-1]  # Last line is RETURN

    # Parse the RETURN line to get current aliases
    # Format: "RETURN entity, alias1, alias2, ..."
    return_vars = [v.strip() for v in return_line.replace("RETURN ", "").split(",")]

    # Build shared-neighbor clauses
    shared_clauses = []
    shared_aliases = []

    for i, rel_def in enumerate(shared_neighbor_relationships):
        clause, alias = _build_shared_neighbor_clause(rel_def, i, return_vars)
        if clause:
            shared_clauses.append(clause)
            shared_aliases.append(alias)
            return_vars.append(alias)

    # Combine: base query (without RETURN) + shared-neighbor clauses + new RETURN
    query_without_return = "\n".join(lines[:-1])
    shared_neighbor_section = "\n".join(shared_clauses)
    new_return = f"RETURN {', '.join(return_vars)}"

    final_query = f"{query_without_return}\n{shared_neighbor_section}\n{new_return}"

    return final_query, parameters


def get_available_relationships(entity_label: str) -> list[str]:
    """
    Get available relationship context_field_names for an entity type.

    Useful for understanding what relationships can be included/excluded
    when calling generate_context_query().

    Args:
        entity_label: Neo4j label (e.g., "Task", "Goal")

    Returns:
        List of context_field_names (e.g., ["applied_knowledge", "goal_context", ...])
    """
    config = _get_registry().get(entity_label)
    if not config:
        return []

    return [r.context_field_name for r in config.relationships]


def get_relationship_details(entity_label: str) -> dict[str, dict[str, Any]]:
    """
    Get detailed relationship info for an entity type.

    Returns a dict mapping context_field_name to relationship details,
    useful for understanding what each relationship provides.

    Args:
        entity_label: Neo4j label (e.g., "Task", "Goal")

    Returns:
        Dict mapping context_field_name to details dict with:
        - relationship_type: The Neo4j relationship type
        - target_label: Target node label
        - direction: "outgoing", "incoming", or "both"
        - fields: Fields returned from target nodes
        - single: Whether it returns a single object or list
        - use_confidence: Whether confidence filtering is applied
        - limit: Maximum number of results (if set)
        - is_shared_neighbor: Whether this is a shared-neighbor pattern
        - shared_neighbor_relationships: The intermediate relationships (if shared-neighbor)
    """
    config = _get_registry().get(entity_label)
    if not config:
        return {}

    result = {}
    for r in config.relationships:
        details: dict[str, Any] = {
            "relationship_type": r.relationship.value,
            "target_label": r.target_label,
            "direction": r.direction,
            "fields": r.fields,
            "single": r.single,
            "use_confidence": r.use_confidence,
            "limit": r.limit,
            "is_shared_neighbor": r.shared_neighbor_config is not None,
        }
        if r.shared_neighbor_config:
            details["shared_neighbor_relationships"] = (
                r.shared_neighbor_config.get_relationship_pattern()
            )
            details["shared_neighbor_result_fields"] = r.shared_neighbor_config.result_fields
        result[r.context_field_name] = details
    return result
