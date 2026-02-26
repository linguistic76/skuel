---
title: Graph-Native Placeholder Pattern
updated: '2026-02-02'
category: patterns
related_skills: []
related_docs: []
---
# Graph-Native Placeholder Pattern

## Overview

SKUEL domain models follow a **graph-native architecture** where relationship data lives in Neo4j edges, not serialized as model fields. Some domain models include limited placeholder methods that document this pattern.

## The Pattern

**Intentional Limited Implementations:**
Methods that return empty collections or partial data to demonstrate the separation between domain models and graph relationships.

**Purpose:**
1. Document that full relationship data requires service layer queries
2. Provide basic functionality using in-memory data where applicable
3. Show the correct query pattern for complete data

## Comment Standard: "GRAPH-NATIVE:"

All placeholder methods use the `GRAPH-NATIVE:` prefix to indicate:
- This is an intentional architectural pattern (not deprecated code)
- The implementation is limited by design
- Complete data requires service layer queries

**Examples:**

### Field-Level Comments
```python
# GRAPH-NATIVE: subtask_uids removed - query via service.relationships.get_task_subtasks()
```

### Method-Level Comments
```python
def prerequisite_tasks(self) -> tuple[str, ...]:
    """
    Get prerequisite tasks for this task.

    GRAPH-NATIVE: Real implementation requires service layer query.
    Query: MATCH (task)-[:REQUIRES_TASK]->(prereq:Task) RETURN prereq.uid
    """
    return ()
```

### Limited Implementation Comments
```python
def is_connected(self) -> bool:
    """
    Check if this knowledge is connected to others.

    GRAPH-NATIVE: Limited implementation using semantic links only.
    For complete relationship checking across all graph edges, use:
    has_rels = await backend.get_related_uids(uid, relationship_type, "both")
    """
    return len(self.semantic_links) > 0
```

## Key Principles

1. **Not Deprecated** - These are intentional placeholders, not legacy code
2. **Architectural Separation** - Domain models are pure, relationships live in graph
3. **Documentation First** - Comments show the correct way to get complete data
4. **One Path Forward** - Service layer is THE way to query relationships

## Distribution Across Domains

| Domain | Field Comments | Method Comments | Total |
|--------|----------------|-----------------|-------|
| Task | 9 | 18+ | 27+ |
| Goal | 5 | 6+ | 11+ |
| Habit | 4 | 8+ | 12+ |
| Event | 3 | 8+ | 11+ |
| Choice | 2 | 8+ | 10+ |
| Principle | 2 | 6+ | 8+ |
| KU | 13 | 2 | 15 |
| LS | 6 | 2 | 8 |
| LP | 1 | 0 | 1 |
| MOC | 3 | 1 | 4 |
| User | 4 | 2 | 6 |
| Journal | 2 | 2 | 4 |
| **TOTAL** | **54** | **63** | **117+** |

## Migration Guide

If you see "DEPRECATED" in a placeholder method docstring:

### ❌ Don't Think
"This is legacy code that needs removal"

### ✅ Do Think
"This is an intentional limited implementation documenting the graph-native pattern"

### Action
Replace "DEPRECATED" with "GRAPH-NATIVE: Limited implementation..." to clarify intent.

## See Also

- `/docs/patterns/DOMAIN_RELATIONSHIPS_PATTERN.md` - Complete relationship pattern documentation
- `/docs/architecture/../patterns/query_architecture.md` - Graph-native architecture overview
- `CLAUDE.md` § "Graph-Native Comment Standard" - Quick reference
