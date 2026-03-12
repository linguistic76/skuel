---
title: ADR-037 - Embedding Infrastructure Separation from Domain Models
date: 2026-02-01
status: accepted
category: architecture
tags:
  - embeddings
  - dtos
  - three-tier
  - infrastructure
related:
  - three_tier_type_system.md
  - EMBEDDING_ARCHITECTURE.md
---

# ADR-037: Embedding Infrastructure Separation from Domain Models

**Date:** 2026-02-01
**Status:** Accepted
**Context:** All Activity domains (Task, Goal, Habit, Event, Choice, Principle) store embeddings in Neo4j for semantic search

## Problem

Neo4j nodes contain infrastructure fields (`embedding`, `embedding_version`, `embedding_model`, `embedding_updated_at`) that are returned when querying entities. When converting Neo4j data to DTOs, these fields cause `TypeError: __init__() got an unexpected keyword argument 'embedding'` because DTOs don't define these fields.

**Error encountered:**
```
TaskDTO.__init__() got an unexpected keyword argument 'embedding'
GoalDTO.__init__() got an unexpected keyword argument 'embedding'
```

## Decision

**Embeddings are infrastructure, not domain data. They are automatically filtered out from DTOs.**

### Rationale

1. **Embeddings are search infrastructure** - like database indexes
   - 1024-dimensional vectors used for semantic search
   - Generated asynchronously by background worker
   - Not part of business logic or domain model

2. **Application code doesn't need raw embeddings**
   - Users interact with search results, not vectors
   - Embeddings are consumed by Neo4j vector search, not application
   - Loading 1024 floats into memory is wasteful when not needed

3. **Consistent with Three-Tier Type System**
   - **External (Pydantic):** API validation/serialization
   - **Transfer (DTO):** Domain data movement
   - **Core (Domain):** Business logic
   - Infrastructure fields don't belong in any tier

4. **ChoiceDTO already implemented this pattern**
   - Manually filtered unknown fields including embeddings
   - Proven pattern working in production

## Implementation

### Generic Filtering in `dto_from_dict`

```python
# /core/models/dto_helpers.py (line 591)

if is_dataclass(cls):
    valid_field_names = {f.name for f in dataclass_fields(cls)}
    filtered_data = {k: v for k, v in data.items() if k in valid_field_names}
    return cls(**filtered_data)
```

**Automatically filters:**
- `embedding` - 1024-dimensional vector (BAAI/bge-large-en-v1.5)
- `embedding_version` - Model version (e.g., "v2")
- `embedding_model` - Model name
- `embedding_updated_at` - Generation timestamp
- Any other Neo4j-specific infrastructure fields

### Affected Domains

All 6 Activity domains benefit from this filtering:
1. **Tasks** - `TaskDTO.from_dict()`
2. **Goals** - `GoalDTO.from_dict()`
3. **Habits** - `HabitDTO.from_dict()`
4. **Events** - `EventDTO.from_dict()`
5. **Choices** - `ChoiceDTO.from_dict()` (migrated from manual filtering)
6. **Principles** - `PrincipleDTO.from_dict()`

**Plus Curriculum domains:**
7. **KU** - `CurriculumDTO.from_dict()` *(was KuDTO, deleted 2026-02-23)*
8. **LS** - `LsDTO.from_dict()`
9. **LP** - `LpDTO.from_dict()`

## Consequences

### Positive

✅ **Unified architecture** - All DTOs handle infrastructure fields consistently
✅ **No manual filtering** - Generic solution replaces 60+ lines of manual filtering
✅ **Type safety** - Only dataclass-defined fields passed to `__init__`
✅ **Future-proof** - New infrastructure fields automatically filtered
✅ **Clear separation** - Domain data vs infrastructure clearly delineated

### Negative

⚠️ **Embedding metadata not accessible** - Cannot display embedding status in UI without separate query
⚠️ **Silent filtering** - Unknown fields are dropped without warning (by design)

### Monitoring

If embedding status is needed (e.g., "Which entities have embeddings?"), query Neo4j directly:

```cypher
MATCH (n:Task)
RETURN n.uid,
       n.embedding IS NOT NULL as has_embedding,
       n.embedding_updated_at as last_updated
```

## Migration Notes

### Before (ChoiceDTO - Manual Filtering)

```python
# Filter to only known fields
known_fields = {
    "uid", "title", "description", ...  # 30+ fields listed
}
filtered_data = {k: v for k, v in data.items() if k in known_fields}
return cls(**filtered_data)
```

### After (All DTOs - Generic Filtering)

```python
return dto_from_dict(
    cls,
    data,
    enum_fields={...},
    date_fields=[...],
    # Automatic field filtering - no manual list needed
)
```

**Result:** Reduced from 60+ lines (manual filtering) to automatic filtering in `dto_from_dict`.

## Alternatives Considered

### Alternative 1: Add `embedding` field to all DTOs

**Rejected because:**
- Embeddings are infrastructure, not domain data
- 1024 floats wasteful to load when not needed
- Would expose implementation details to application layer

### Alternative 2: Remove embeddings from Neo4j

**Rejected because:**
- Embeddings required for semantic search
- Background worker architecture depends on Neo4j storage
- Vector indexes built on these properties

### Alternative 3: Separate embedding storage

**Rejected because:**
- Adds complexity (separate database/table)
- Neo4j vector search expects embeddings as node properties
- No clear benefit over filtering

## References

- **Three-Tier Type System:** `/docs/patterns/three_tier_type_system.md`
- **Embedding Architecture:** `/docs/patterns/EMBEDDING_ARCHITECTURE.md` (if exists)
- **DTO Helpers:** `/core/models/dto_helpers.py`
- **Background Worker:** `/core/services/background/embedding_worker.py`

## Related ADRs

- ADR-035: Tier Selection Guidelines (Three-Tier Type System)
- ADR-022: Graph-Native Authentication (Neo4j-first architecture)

## Status History

- **2026-02-01:** Accepted - Generic filtering implemented in `dto_from_dict`
- **2024-10:** Implicit - ChoiceDTO manually filtered unknown fields
