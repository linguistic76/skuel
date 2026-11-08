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
updated: 2026-11-08
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
# /core/models/dto_helpers.py, dto_from_dict

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
8. **PS** - `LsDTO.from_dict()`
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

## Amendment (2026-11-07): the model keeps them, no JSON response carries them

`Entity` declares `embedding`, `embedding_model` and `embedding_updated_at`, and
`from_neo4j_node` fills them from the node, so the domain model holds the vector. It keeps it:
`BaseAIService._rank_similar_entities` reads `entity.embedding`. The JSON boundary is where the
fields stop. `jsonable_content` (`/adapters/inbound/boundary.py`) leaves the three keys out of
every `Entity` in a response, wherever it sits in the value, so an embedded entity answers with
the same keys as one that is not; they are absent, never null. Ruled by Mike 2026-11-07: fix it
at the JSON boundary, not in the mapper.

The strip is type-based: it reaches an `Entity`, so a door that turned one into a plain dict
first, or returned raw node properties, would carry the vector past it. Ruled by Mike the same
day: it stays type-based, and a census holds the invariant by behaviour.
`/tests/integration/routes/test_json_read_census.py` reads every GET route in the app's route
table over a signed-in user's seeded, embedded entities, and fails on a body carrying the
vector and on any 5xx.

## References

- **Three-Tier Type System:** `/docs/patterns/three_tier_type_system.md`
- **Embedding Architecture:** [ADR-074](ADR-074-post-persist-embedding-events.md)
  (post-persist embedding events) and [ADR-068](ADR-068-openai-embeddings-now-bge-later.md)
  (provider choice)
- **DTO Helpers:** `/core/models/dto_helpers.py`
- **Background Worker:** `/core/services/background/embedding_worker.py`

## Related ADRs

- ADR-035: Tier Selection Guidelines (Three-Tier Type System)
- ADR-022: Graph-Native Authentication (Neo4j-first architecture)

## Status History

- **2026-11-07:** Amended - the JSON boundary leaves the three `Entity` embedding fields out of every response
- **2026-02-01:** Accepted - Generic filtering implemented in `dto_from_dict`
- **2024-10:** Implicit - ChoiceDTO manually filtered unknown fields
