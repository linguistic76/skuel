# Query Infrastructure - Neo4j Query Builders

**Neo4j-specific query infrastructure for all domains in SKUEL.**

Located at `/adapters/persistence/neo4j/query/` — the adapter layer.
Core-layer types (`QueryIntent`, `IndexStrategy`) live in `/core/models/query_types.py`.
Search boundary models live in `/core/models/search_models.py`.

## Purpose

Provides Neo4j-first, pure Cypher query capabilities to all domains:
- Tasks, Events, Habits, Goals, Choices, Principles
- Finance
- KU, LS, LP, MOC (Curriculum)
- Search

## Key Components

### Query Intent & Strategy
```python
from core.models.query_types import QueryIntent, IndexStrategy

# Semantic query understanding
intent = QueryIntent.HIERARCHICAL  # or PREREQUISITE, PRACTICE, etc.

# Neo4j index optimization
strategy = IndexStrategy.UNIQUE_LOOKUP  # or FULLTEXT_SEARCH, VECTOR_SEARCH
```

### `cypher/` build_* functions (Pure Cypher)

Module-level functions, not a class — there is no `CypherGenerator` type to import.

Both take the domain model class first — the Cypher label is derived from it (pass
`label=` only to override).

```python
from adapters.persistence.neo4j.query.cypher import (
    build_graph_aware_search_query,
    build_text_search_query,
)
from core.models.ku.ku import Ku
from core.models.task.task import Task

# Text search, scoped to chosen fields
query, params = build_text_search_query(
    Ku,
    query="algebra",
    search_fields=["title", "description"],
    limit=25,
)

# Graph-aware search: text search anchored to a related node
query, params = build_graph_aware_search_query(
    Task,
    query="python api testing",
    source_uid="goal.ship-v1",
    relationship_type="FULFILLS_GOAL",
    search_fields=["title", "description"],
    direction="incoming",
)
```

### UnifiedQueryBuilder (Application Layer)
```python
from adapters.persistence.neo4j.query import UnifiedQueryBuilder

# Fluent API for query construction
builder = UnifiedQueryBuilder()
query = (
    builder.for_model(Task)
    .with_filters({"priority": "high"})
    .build()
)
```

### Query Build Request
```python
from adapters.persistence.neo4j.query import QueryBuildRequest, create_search_request

# Declarative query construction
request = QueryBuildRequest(
    labels={"Task"},
    search_text="python api testing",
    query_intent=QueryIntent.SPECIFIC,
    limit=25
)

# Helper for common search patterns
search_req = create_search_request(
    labels=["Ku"],
    search_text="algebra fundamentals",
    intent=QueryIntent.EXPLORATORY,
    limit=20
)
```

### Query Validation
```python
from adapters.persistence.neo4j.query import ValidationResult, QueryElements

# Schema-aware validation
validation_result = validator.validate_query(cypher, schema_context)

if not validation_result.is_valid:
    print(validation_result.get_error_summary())
    for suggestion in validation_result.get_suggestions():
        print(f"  - {suggestion}")
```

## Design Principles

1. **Infrastructure-Level** - Not tied to any single domain
2. **Neo4j-First** - Leverages indexes and graph traversal
3. **Pure Cypher** - No external dependencies (APOC removed October 2025)
4. **Intent-Based** - Semantic query understanding (not just keyword matching)
5. **Schema-Aware** - Validates queries against live Neo4j schema

## Files

- `_query_models.py` - Query building models (imports enums from `core.models.query_types`)
- `cypher/` - pure Cypher query builder functions (`build_*`, module-level)
- `cypher_template.py` - Query optimization strategies

## Query Architecture Layers

| Layer | Component | Purpose |
|-------|-----------|---------|
| Application | UnifiedQueryBuilder | Fluent API, default for new code |
| Service | QueryBuilder | Optimization, templates |
| Infrastructure | `cypher/` build_* functions | Pure Cypher generation |

See `/docs/patterns/query_architecture.md` for full documentation.
