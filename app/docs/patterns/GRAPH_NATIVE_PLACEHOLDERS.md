---
title: Graph-Native Placeholder Pattern
updated: '2026-07-30'
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

Name the **edge** the data lives on and the **service method** that reads it — not the query. These placeholders sit in `core/models/`, which [SERVICE_DOCSTRING_STYLE.md](SERVICE_DOCSTRING_STYLE.md) § Where this applies answers **No** for on docstring Cypher, and SKUEL033 enforces.

```python
def prerequisite_tasks(self) -> tuple[str, ...]:
    """
    Get prerequisite tasks for this task.

    GRAPH-NATIVE: always returns empty — prerequisites live on the
    ``REQUIRES_TASK`` edge, so the model cannot answer this without the graph.

    Service: backend.get_related_uids(
        uid, RelationshipName.REQUIRES_TASK, "outgoing")
    """
    return ()
```

> **Two layers share this method name.** The `core/ports` form above takes
> `(uid, relationship_type: RelationshipName, direction)`; the service-layer
> `UnifiedRelationshipService.get_related_uids` takes `(relationship_key: str,
> entity_uid)`. Name the layer you mean — a pointer with the wrong argument
> order is the same rot as a stale query.

**An earlier version of this example prescribed a `Query: MATCH ... RETURN ...` line**, and `core/models/user/user.py` followed it. That line is exactly the drift the style guide warns about — the one in `user.py` had lost the `{uid: $user_uid}` scoping, so a reader who copied it would have queried **every** user's pins. A pointer to the service method cannot rot that way: it either resolves or it doesn't.

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
| PS | 6 | 2 | 8 |
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

- `/docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md` - Complete relationship service documentation
- `/docs/architecture/../patterns/query_architecture.md` - Graph-native architecture overview
- `CLAUDE.md` § "Graph-Native Comment Standard" - Quick reference
