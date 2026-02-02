---
title: Relationship Infrastructure Pattern
updated: 2026-01-17
category: patterns
related_skills:
- neo4j-cypher-patterns
related_docs:
- /docs/patterns/DOMAIN_RELATIONSHIPS_PATTERN.md
- /docs/patterns/RELATIONSHIPS_ARCHITECTURE.md
- /docs/decisions/ADR-026
---

# Relationship Infrastructure Pattern

**Last Updated:** 2026-01-17
**Status:** Active
**Location:** `/core/infrastructure/relationships/`

## Overview

The relationships infrastructure provides the foundational building blocks for entity-level relationship storage, validation, and semantic enrichment. This is the "relationship kernel" of SKUEL - a consistent way to store relationships on entities, validate them, and optionally upgrade them into richer semantic relationships.

**Key Distinction:** This infrastructure is the *foundation layer* - it defines HOW relationships are stored and validated. The service layer (`UnifiedRelationshipService`, domain-specific relationship services) builds ON TOP of this foundation to provide runtime relationship queries.

## Three-Layer Architecture

```
+-----------------------------------------------+
|  Layer 3: Semantic Layer                      |
|  (semantic_relationships.py)                  |
|  - 80+ semantically precise relationship types |
|  - RDF-inspired triples with metadata         |
|  - Namespace-organized (learn:, task:, etc.)  |
+------------------------+----------------------+
                         |
                         v
+-----------------------------------------------+
|  Layer 2: Storage/Mixin Layer                 |
|  (relationship_base.py)                       |
|  - Lists of UIDs organized by type            |
|  - Hierarchical relationships                 |
|  - Learning-specific relationships            |
|  - Aliasing maps multiple enum -> same list   |
+------------------------+----------------------+
                         |
                         v
+-----------------------------------------------+
|  Layer 1: Validation/Unified Layer            |
|  (relationship_validation.py +                |
|   unified_relationships.py)                   |
|  - Centralized validation rules               |
|  - Circular dependency detection              |
|  - Graph traversal & analysis                 |
|  - Cross-entity relationships                 |
+-----------------------------------------------+
```

## File Structure

```
/core/infrastructure/relationships/
├── __init__.py                      # Public API exports
├── relationship_base.py             # Core mixins (RelationshipMixin, Hierarchical, Learning)
├── relationship_validation.py       # Validation logic (RelationshipValidator, Sanitizer)
├── semantic_relationships.py        # RDF-inspired semantic relationship system
├── relationships.py                 # Simple graph models (Relationship, GraphPath)
├── relationship_graph_native.py     # Graph-native extensions (KnowledgeRelationship, etc.)
└── unified_relationships.py         # Cross-entity unified relationship system
```

## Layer 1: Storage Mixins (relationship_base.py)

### RelationshipMixin

Base mixin for entities with relationships. Provides common relationship fields and helper methods.

**Fields (Three-Level Organization):**

| Relationship Type | Field | Purpose |
|-------------------|-------|---------|
| **Learning Flow** | `prerequisite_uids`, `enables_uids`, `builds_on_uids` | Knowledge prerequisites and progression |
| **Lateral** | `related_uids`, `see_also_uids` | Non-hierarchical connections |
| **Application** | `applies_to_uids`, `used_by_uids` | Cross-domain usage |
| **Domain** | `domain_uids` | Domain categorization |

**Key Methods:**

```python
# Check if entity has dependencies
entity.has_prerequisites  # bool
entity.has_dependencies   # bool

# Get all related UIDs (for graph traversal)
all_uids = entity.all_relationship_uids  # set[str]

# Get UIDs for specific relationship type
uids = entity.get_relationships_by_type(RelationshipType.REQUIRES)

# Modify relationships
entity.add_relationship(RelationshipType.ENABLES, target_uid)
entity.remove_relationship(RelationshipType.REQUIRES, target_uid)
```

### Aliasing Design (Intentional)

The `get_relationships_by_type()` method maps multiple `RelationshipType` enum values to the same underlying UID list. This is **intentional design**, not technical debt.

**Aliasing Mappings:**
- `REQUIRES`, `PREREQUISITE`, `PREREQUISITE_FOR` -> `prerequisite_uids`
- `RELATED_TO`, `RELATED` -> `related_uids`

**Rationale:**
1. Provides flexibility at the mixin level for domain-appropriate terminology
2. Callers can use semantically meaningful enum values
3. Mixin maintains simplified internal structure
4. Semantic layer (KuSemanticService) uses `SemanticRelationshipType` directly without aliasing

**Current Usage:** Internal only (`remove_relationship` method calls `get_relationships_by_type`).

**Future Consideration:** If aliasing becomes problematic when the mixin is adopted more widely, consider:
- Splitting lists by meaning, or
- Storing typed edges (uid + relationship type + optional metadata) and generating lists as views

### HierarchicalRelationshipMixin

Extends `RelationshipMixin` with parent-child hierarchy support.

**Fields:**
- `parent_uid: str | None = None` - Single parent reference
- `child_uids: list[str]` - Multiple children

**Properties:**
- `is_root` - True if `parent_uid is None`
- `is_leaf` - True if `child_uids` is empty

**Methods:**
- `add_child(child_uid)` - Add a child relationship
- `remove_child(child_uid)` - Remove a child relationship

**Note:** The `all_relationship_uids` property is overridden to include hierarchical relationships.

### LearningRelationshipMixin

Extends `RelationshipMixin` with learning-specific relationships.

**Categories:**
- **Learning Path Integration:** `learning_path_uids`, `learning_step_uids`
- **Resources:** `resource_uids`, `exercise_uids`, `assessment_uids`
- **Alternatives:** `alternative_explanation_uids`, `simplified_version_uid`, `advanced_version_uid`
- **Grouping:** `concept_group_uid`, `skill_cluster_uid`

**Properties:**
- `has_learning_paths` - Part of any learning paths
- `has_resources` - Has associated resources
- `has_alternatives` - Has alternative versions

### FullRelationshipMixin

Combines `HierarchicalRelationshipMixin` + `LearningRelationshipMixin` for entities needing ALL relationship types (e.g., KnowledgeUnit).

## Layer 2: Validation (relationship_validation.py)

Centralized validation rules - the "single source of truth" for relationship constraints.

### Five Validation Categories

| Validator | Purpose |
|-----------|---------|
| `validate_no_self_reference()` | Prevent self-loops |
| `validate_relationship_consistency()` | Check conflicting relationships |
| `validate_hierarchy()` | Parent-child integrity |
| `validate_prerequisites()` | Circular dependency detection |
| `validate_progress_requirements()` | Progress threshold validation |

### Helper Classes

- **RelationshipSanitizer** - Remove duplicates, clean relationships
- **RelationshipAnalyzer** - Find orphans, hubs, calculate density

### Helper Functions

```python
from core.infrastructure.relationships.relationship_base import (
    validate_no_self_references,
    find_circular_dependencies,
)

# Validate no self-reference
validate_no_self_references(entity_uid, relationship_uids)  # Raises ValueError

# Detect circular dependencies
cycle = find_circular_dependencies(start_uid, relationships_map)
# Returns list of UIDs forming cycle, or None
```

## Layer 3: Semantic Relationships (semantic_relationships.py)

RDF-inspired semantic relationship system with precise type definitions.

### SemanticRelationshipType

80+ semantically precise relationship types organized by namespace:

| Namespace | Count | Examples |
|-----------|-------|----------|
| `learn:*` | 12 | `REQUIRES_THEORETICAL_UNDERSTANDING`, `BUILDS_MENTAL_MODEL` |
| `task:*` | 7 | `BLOCKS_UNTIL_COMPLETE`, `CONTRIBUTES_TO_GOAL` |
| `habit:*` | 5 | `REINFORCES_THROUGH_REPETITION`, `CHAINS_WITH` |
| `cross:*` | 6 | `IMPLEMENTS_VIA_TASK`, `DISCOVERED_THROUGH` |
| `skill:*` | 4 | `DEVELOPS_SKILL`, `PRACTICES_TECHNIQUE` |
| `concept:*` | 7 | `GENERALIZES`, `SPECIALIZES`, `HAS_NARROWER_CONCEPT` |
| `time:*` | 5 | `OCCURS_BEFORE`, `DEADLINE_FOR` |
| `moc:*` | 8 | `ORGANIZED_IN_MOC`, `BRIDGES_DOMAINS` |

### RelationshipMetadata

Rich metadata for relationships:

```python
RelationshipMetadata(
    confidence=0.95,      # How sure (0-1)
    strength=0.8,         # How strong (0-1)
    source="expert",      # Where this came from
    valid_from=datetime,  # Validity window
    valid_until=datetime,
    evidence=["..."],     # Supporting evidence
    notes="...",          # Additional notes
    properties={}         # Custom properties
)
```

### Progressive Enhancement

The semantic layer provides an upgrade path from generic relationships:

```python
# Generic -> Semantic upgrade
semantic_type = SemanticRelationshipType.to_semantic(RelationshipType.REQUIRES)
# Returns: SemanticRelationshipType.REQUIRES_CONCEPTUAL_FOUNDATION
```

### SemanticTriple

RDF-style triple representation:

```python
triple = SemanticTriple(
    subject_uid="ku.machine-learning",
    predicate=SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING,
    object_uid="ku.linear-algebra",
    metadata=RelationshipMetadata(confidence=0.95)
)
```

## Boundary Guidelines

### Layer Separation

| Layer | Responsibility | Should NOT |
|-------|----------------|------------|
| **Mixins** | UID list storage + simple helpers | Reach into persistence or validation |
| **Validation** | Constraint checking | Store state or reach into persistence |
| **Semantic** | Rich type definitions + metadata | Leak into entity storage (unless migrating) |

### When to Use Each Layer

| Need | Layer | Example |
|------|-------|---------|
| Store relationship UIDs on entity | Mixins | `entity.prerequisite_uids.append(uid)` |
| Validate relationship graph | Validation | `find_circular_dependencies(...)` |
| Express precise relationship meaning | Semantic | `SemanticRelationshipType.BUILDS_MENTAL_MODEL` |
| Query relationships at runtime | Services | `UnifiedRelationshipService.get_related_uids(...)` |

## Testing

The infrastructure layer has unit tests in `tests/unit/test_relationship_base.py`:

```bash
poetry run pytest tests/unit/test_relationship_base.py -v
```

Test coverage includes:
- `is_root` property (regression test for parent_uid default bug)
- `is_leaf` property
- Child management
- Relationship type aliasing
- Validation helpers (self-references, circular dependencies)

## Bug Fixes

### January 2026: parent_uid Tuple Default Bug

**Bug:** `parent_uid: str | None = (None,)` - tuple default instead of `None`

**Impact:** `is_root` property always returned `False` for root nodes

**Fix:** Changed to `parent_uid: str | None = None`

**Regression Test:** `test_default_parent_uid_is_none_not_tuple` in `tests/unit/test_relationship_base.py`

## Related Documentation

- **Service Layer:** [DOMAIN_RELATIONSHIPS_PATTERN.md](DOMAIN_RELATIONSHIPS_PATTERN.md)
- **Architecture:** [RELATIONSHIPS_ARCHITECTURE.md](../architecture/RELATIONSHIPS_ARCHITECTURE.md)
- **Unified Service:** [UNIFIED_RELATIONSHIP_SERVICE.md](UNIFIED_RELATIONSHIP_SERVICE.md)
- **ADR-026:** Unified Relationship Registry

## Summary

The relationships infrastructure provides:

1. **Clean separation** between storage (mixins), validation (rules), and meaning (semantic)
2. **Intentional aliasing** at the mixin level for flexibility
3. **Progressive enhancement** path from generic to semantic relationships
4. **Centralized validation** rules as single source of truth
5. **Unit tests** to prevent regression of fixed bugs
