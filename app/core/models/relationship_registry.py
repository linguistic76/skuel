"""
Centralized Relationship Registry
==================================

Single source of truth for domain relationship configurations.

**January 2026 Consolidation (ADR-026):**

Activity Domains (6) now use the UnifiedRelationshipRegistry as the single
source of truth. This file serves as a FACADE that generates patterns from
the unified registry for Activity domains, while maintaining existing
string-based patterns for Curriculum domains.

Usage:
    from core.models.relationship_registry import (
        GRAPH_ENRICHMENT_REGISTRY,
        PREREQUISITE_REGISTRY,
        ENABLES_REGISTRY,
    )

    class TasksSearchService(BaseService):
        _graph_enrichment_patterns = GRAPH_ENRICHMENT_REGISTRY["Task"]
        _prerequisite_relationships = PREREQUISITE_REGISTRY["Task"]
        _enables_relationships = ENABLES_REGISTRY["Task"]

Architecture:
    - Activity Domains: Generated from UnifiedRelationshipRegistry
    - Curriculum Domains: String-based patterns (until enum additions in Phase 2)

See Also:
    - /core/models/unified_relationship_registry.py - THE single source of truth
    - /core/services/base_service.py - Uses these configurations
    - /core/models/relationship_names.py - Relationship type enums
    - /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md - Domain relationships
"""

from core.models.unified_relationship_registry import (
    generate_enables_relationships as _gen_enables,
)
from core.models.unified_relationship_registry import (
    generate_graph_enrichment,
)
from core.models.unified_relationship_registry import (
    generate_prerequisite_relationships as _gen_prereq,
)

# Type alias for graph enrichment patterns
# Format: (relationship_type, target_label, context_field_name, direction)
# Direction is "outgoing" (default), "incoming", or "both"
GraphEnrichmentPattern = tuple[str, str, str, str]

# ============================================================================
# GRAPH ENRICHMENT REGISTRY
# ============================================================================
# Defines which relationships to include in search results for each domain.
# Used by BaseService.graph_aware_faceted_search() for _graph_context enrichment.
#
# Activity Domains: Generated from UnifiedRelationshipRegistry
# Curriculum Domains: String-based patterns (Phase 2 migration pending)

GRAPH_ENRICHMENT_REGISTRY: dict[str, list[GraphEnrichmentPattern]] = {
    # =========================================================================
    # ACTIVITY DOMAINS (6) - Generated from UnifiedRelationshipRegistry
    # =========================================================================
    "Task": generate_graph_enrichment("Task"),
    "Goal": generate_graph_enrichment("Goal"),
    "Habit": generate_graph_enrichment("Habit"),
    "Event": generate_graph_enrichment("Event"),
    "Choice": generate_graph_enrichment("Choice"),
    "Principle": generate_graph_enrichment("Principle"),
    # =========================================================================
    # CURRICULUM DOMAINS (3) - Generated from UnifiedRelationshipRegistry (Phase 2)
    # =========================================================================
    "Ku": generate_graph_enrichment("Ku"),
    "Ls": generate_graph_enrichment("Ls"),
    "Lp": generate_graph_enrichment("Lp"),
}

# ============================================================================
# PREREQUISITE REGISTRY
# ============================================================================
# Defines which relationship types represent prerequisites for each domain.
# Used by BaseService.get_prerequisites() and add_prerequisite().
#
# ALL domains now generated from UnifiedRelationshipRegistry (Phase 2 complete)

PREREQUISITE_REGISTRY: dict[str, list[str]] = {
    # Activity Domains (6)
    "Task": _gen_prereq("Task"),
    "Goal": _gen_prereq("Goal"),
    "Habit": _gen_prereq("Habit"),
    "Event": _gen_prereq("Event"),
    "Choice": _gen_prereq("Choice"),
    "Principle": _gen_prereq("Principle"),
    # Curriculum Domains (3)
    "Ku": _gen_prereq("Ku"),
    "Ls": _gen_prereq("Ls"),
    "Lp": _gen_prereq("Lp"),
}

# ============================================================================
# ENABLES REGISTRY
# ============================================================================
# Defines which relationship types represent what this entity enables.
# Used by BaseService.get_enables().
#
# ALL domains now generated from UnifiedRelationshipRegistry (Phase 2 complete)

ENABLES_REGISTRY: dict[str, list[str]] = {
    # Activity Domains (6)
    "Task": _gen_enables("Task"),
    "Goal": _gen_enables("Goal"),
    "Habit": _gen_enables("Habit"),
    "Event": _gen_enables("Event"),
    "Choice": _gen_enables("Choice"),
    "Principle": _gen_enables("Principle"),
    # Curriculum Domains (3)
    "Ku": _gen_enables("Ku"),
    "Ls": _gen_enables("Ls"),
    "Lp": _gen_enables("Lp"),
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def get_graph_enrichment(entity_label: str) -> list[GraphEnrichmentPattern]:
    """
    Get graph enrichment patterns for an entity type.

    Args:
        entity_label: The Neo4j label (e.g., "Task", "Goal", "Ku")

    Returns:
        List of enrichment patterns, empty list if not configured
    """
    return GRAPH_ENRICHMENT_REGISTRY.get(entity_label, [])


def get_prerequisite_relationships(entity_label: str) -> list[str]:
    """
    Get prerequisite relationship types for an entity type.

    Args:
        entity_label: The Neo4j label (e.g., "Task", "Goal", "Ku")

    Returns:
        List of relationship type strings, empty list if not configured
    """
    return PREREQUISITE_REGISTRY.get(entity_label, [])


def get_enables_relationships(entity_label: str) -> list[str]:
    """
    Get enables relationship types for an entity type.

    Args:
        entity_label: The Neo4j label (e.g., "Task", "Goal", "Ku")

    Returns:
        List of relationship type strings, empty list if not configured
    """
    return ENABLES_REGISTRY.get(entity_label, [])
