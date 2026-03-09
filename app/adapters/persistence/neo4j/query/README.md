# Query Infrastructure - Universal Query Models

**Infrastructure-level query models for ALL domains in SKUEL.**

Located at `/core/models/query/` as part of the Query Infrastructure.

## Purpose

Provides Neo4j-first, pure Cypher query capabilities to all domains:
- Tasks, Events, Habits, Goals, Choices, Principles
- Finance
- KU, LS, LP, MOC (Curriculum)
- Search

## Key Components

### Query Intent & Strategy
```python
from core.models.query import QueryIntent, IndexStrategy

# Semantic query understanding
intent = QueryIntent.HIERARCHICAL  # or PREREQUISITE, PRACTICE, etc.

# Neo4j index optimization
strategy = IndexStrategy.UNIQUE_LOOKUP  # or FULLTEXT_SEARCH, VECTOR_SEARCH
```

### CypherGenerator (Pure Cypher)
```python
from core.models.query.cypher import CypherGenerator

# Build graph-aware search queries
query, params = CypherGenerator.build_graph_aware_search_query(
    label="Task",
    search_fields=["title", "description"],
    search_text="python api testing"
)

# Build text search queries
query, params = CypherGenerator.build_text_search_query(
    label="Ku",
    search_fields=["title", "content"],
    query="algebra"
)
```

### UnifiedQueryBuilder (Application Layer)
```python
from core.models.query import UnifiedQueryBuilder

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
from core.models.query import QueryBuildRequest, create_search_request

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
from core.models.query import ValidationResult, QueryElements

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

- `_query_models.py` - Core query building models
- `cypher/` - CypherGenerator and pure Cypher query builders
- `cypher_template.py` - Query optimization strategies

## Query Architecture Layers

| Layer | Component | Purpose |
|-------|-----------|---------|
| Application | UnifiedQueryBuilder | Fluent API, default for new code |
| Service | QueryBuilder | Optimization, templates |
| Infrastructure | CypherGenerator | Pure Cypher generation |

See `/docs/patterns/query_architecture.md` for full documentation.
