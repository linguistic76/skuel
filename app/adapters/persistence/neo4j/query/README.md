# Query Infrastructure - Neo4j Query Builders

**Neo4j-specific query infrastructure for all domains in SKUEL.**

Located at `/adapters/persistence/neo4j/query/` — the adapter layer.
Core-layer types (`QueryIntent`, `IndexStrategy`) live in `/core/models/query_types.py`.
Search boundary models live in `/core/models/search_models.py`.

Two layers, not three: a fluent facade (`UnifiedQueryBuilder`) over a package of
Cypher-building functions (`cypher/`). Callers may use either — calling a
`build_*` function directly is the documented path for shapes the facade does
not cover, not a fallback.

## Purpose

Provides Neo4j-first, pure Cypher query capabilities to all domains:
- Tasks, Events, Habits, Goals, Choices, Principles
- Finance
- KU, LS, LP, MOC (Curriculum)
- Search

## Key Components

### Query Intent
```python
from core.models.query_types import QueryIntent

# Semantic query understanding
intent = QueryIntent.HIERARCHICAL  # or PREREQUISITE, PRACTICE, etc.
```

### `cypher/` build_* functions (Pure Cypher)

Module-level functions, not a class — there is no `CypherGenerator` type to import.

Both take the domain model class first — the Cypher label is derived from it (pass
`label=` only to override).

> ⚠ **`visibility` and `user_uid` are the ownership gate, and they default to `None`.**
> Omit them and the builder emits **no** `target.user_uid` predicate — for an `OWNER_ONLY`
> domain that is an IDOR. Pass the domain's `SearchVisibility` (from its `DomainConfig`)
> and the requesting user's UID on every user-facing search. `OWNER_ONLY` = Activities +
> UserEntry; `PUBLIC` = Ku/PS/LP; `SCOPE_AWARE` = Exercise.

```python
from adapters.persistence.neo4j.query.cypher import (
    build_graph_aware_search_query,
    build_text_search_query,
)
from core.models.enums.metadata_enums import SearchVisibility
from core.models.ku.ku import Ku
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task

# Text search over a PUBLIC domain — no owner predicate by design
query, params = build_text_search_query(
    Ku,
    query="algebra",
    search_fields=["title", "description"],
    visibility=SearchVisibility.PUBLIC,
    limit=25,
)

# Graph-aware search: text search anchored to a related node.
# Task is an Activity domain → OWNER_ONLY, so scope it or it leaks.
query, params = build_graph_aware_search_query(
    Task,
    query="python api testing",
    source_uid="goal.ship-v1",
    relationship_type=RelationshipName.FULFILLS_GOAL.value,
    search_fields=["title", "description"],
    direction="incoming",
    visibility=SearchVisibility.OWNER_ONLY,
    user_uid=requesting_user_uid,
)
# → WHERE (target.user_uid = $user_uid) AND (toLower(target.title) CONTAINS ...)
```

### UnifiedQueryBuilder (fluent facade)

Holds filter/limit/offset/order state and renders it through the `cypher/`
functions. `.build()` returns `(cypher, params)`; `.execute()` also needs an
executor. Live callers reach it via `UniversalNeo4jBackend.query_builder`.

```python
from adapters.persistence.neo4j.query import UnifiedQueryBuilder

cypher, params = (
    UnifiedQueryBuilder()
    .for_model(Task)
    .filter(priority="high", status="in_progress")
    .order_by("due_date", desc=True)
    .limit(50)
    .build()
)
```

> ⚠ `.for_model()` emits **no** ownership predicate — it is a raw shape builder.
> User-facing reads go through the domain service / `SearchRouter`, which apply
> the `SearchVisibility` gate. Do not put a user-facing search on it directly.

## Design Principles

1. **Infrastructure-Level** - Not tied to any single domain
2. **Neo4j-First** - Leverages indexes and graph traversal
3. **Pure Cypher** - No external dependencies (APOC removed October 2025)
4. **Intent-Based** - Semantic query understanding (not just keyword matching)
5. **Reviewed, not generated** - every query is authored and parameterized here;
   nothing composes Cypher from an LLM or validates it against a live schema at
   runtime (the schema-aware validator was deleted with `query_builders/`,
   2026-08-17)

## Files

- `unified_query_builder.py` - `UnifiedQueryBuilder` / `ModelQueryBuilder` fluent facade
- `cypher/` - pure Cypher query builder functions (`build_*`, module-level)
- `graph_traversal.py` - `build_graph_context_query` (variable-length patterns)
- `confidence_filter.py` - confidence-clause fragments
- `schema_ddl.py` - index/constraint DDL builders
- `cypher_template.py` - `QueryOptimizationStrategy` enum

## Query Architecture Layers

| Layer | Component | Purpose |
|-------|-----------|---------|
| Facade | UnifiedQueryBuilder | Fluent API over the builders below |
| Infrastructure | `cypher/` build_* functions | Pure Cypher generation |

See `/docs/patterns/query_architecture.md` for full documentation.
