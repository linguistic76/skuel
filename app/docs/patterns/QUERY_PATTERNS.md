---
title: Query Patterns
updated: '2026-02-02'
category: patterns
related_skills:
- neo4j-cypher-patterns
related_docs: []
---
# Query Patterns

*Last updated: 2025-12-07*

This document describes SKUEL's query architecture patterns and best practices.

**See also:** [Search Architecture](../architecture/SEARCH_ARCHITECTURE.md) for how search uses these patterns.
## Related Skills

For implementation guidance, see:
- [@neo4j-cypher-patterns](../../.claude/skills/neo4j-cypher-patterns/SKILL.md)


## Three-Tier Query Architecture

SKUEL uses a layered query architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                        │
│                  UnifiedQueryBuilder                        │
│        (Single entry point for routes/APIs)                 │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                     SERVICE LAYER                           │
│                     QueryBuilder                            │
│        (Optimization, templates, validation)                │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                  INFRASTRUCTURE LAYER                       │
│                   CypherGenerator                           │
│           (Pure Cypher query generation)                    │
└─────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

| Layer | Component | Purpose | Used By |
|-------|-----------|---------|---------|
| Application | `UnifiedQueryBuilder` | Single entry point, fluent API | Routes, APIs |
| Service | `QueryBuilder` | Templates, optimization | Services (advanced use) |
| Infrastructure | `CypherGenerator` | Pure Cypher generation | Backends, low-level services |

### When to Use Each Layer

- **Routes/APIs**: Always use `UnifiedQueryBuilder`
- **Domain Services**: Use `CypherGenerator` for graph-native queries
- **Complex Optimization**: Use `QueryBuilder` for template-based queries

## Confidence Filtering

Relationship queries often need to filter by confidence scores. SKUEL provides standardized helpers:

```python
from core.models.query import (
    build_confidence_clause,
    build_confidence_field,
    CONFIDENCE_DEFAULTS,
)
```

### Confidence Modes

| Mode | Default | Use Case |
|------|---------|----------|
| `strict` | 1.0 | Explicit user relationships only |
| `standard` | 0.8 | Most queries (default) |
| `lenient` | 0.5 | Include inferred relationships |
| `explicit` | 0.0 | Require explicit confidence value |

### Usage Examples

```python
# In WHERE clause
clause = build_confidence_clause("r", "min_confidence", mode="standard")
# Returns: "coalesce(r.confidence, 0.8) >= $min_confidence"

# In RETURN clause
field = build_confidence_field("r", alias="edge_confidence")
# Returns: "coalesce(r.confidence, 0.8) as edge_confidence"

# For paths
path_conf = build_path_confidence_aggregation("p")
# Returns: "[rel in relationships(p) | coalesce(rel.confidence, 0.8)] as confidences"
```

## Batch Query Patterns

Always prefer batch queries over N+1 patterns.

### Anti-Pattern: N+1 Queries

```python
# BAD: N+1 queries
all_knowledge_uids = set()
for habit in habits:
    result = await service.get_related_uids("knowledge", habit.uid)  # N queries!
    all_knowledge_uids.update(result.value)
```

### Correct Pattern: Batch Query

```python
# GOOD: Single batch query
habit_uids = [h.uid for h in habits]
result = await service.batch_get_related_uids("knowledge", habit_uids)  # 1 query!
for uids in result.value.values():
    all_knowledge_uids.update(uids)
```

### Available Batch Methods

| Method | Purpose |
|--------|---------|
| `batch_get_related_uids()` | Get related UIDs for multiple entities |
| `batch_count_related()` | Count relationships for multiple entities |
| `batch_has_relationship()` | Check relationship existence for multiple entities |

## N+1 Detection Checklist

Before committing code, check for these patterns:

1. **Loop + await** - Any `for` loop containing `await` calls to the same method
2. **Collect + iterate** - Collecting UIDs then iterating to fetch more data
3. **Missing batch alternative** - Check if a batch method exists

### Detection Example

```python
# SUSPICIOUS: Loop with await
for entity in entities:
    result = await backend.get_related_uids(entity.uid, relationship)  # N+1!
```

## MEGA-QUERY Pattern

For complex user context, SKUEL uses a single comprehensive query:

```python
# Location: /core/services/user/user_context_queries.py
# Purpose: Fetch complete user state in ONE query

# The MEGA-QUERY fetches:
# - User profile
# - Active tasks, goals, habits, events
# - Knowledge mastery
# - Principles alignment
# - Cross-domain relationships
```

### When to Use MEGA-QUERY vs Multiple Queries

| Scenario | Approach |
|----------|----------|
| User context for dashboard | MEGA-QUERY |
| Single entity with relationships | `get_with_context()` |
| Simple list fetch | Standard query |
| Paginated results | Standard query with SKIP/LIMIT |

## Search Integration

SKUEL's search system uses two complementary query approaches:

### Simple Search (Property-Based)

Uses `UniversalNeo4jBackend.search()` and `.find_by()` for fast property filtering:

```python
# Converts SearchRequest facets to WHERE clauses
filters = request.to_neo4j_filters()
# {"sel_category": "self_awareness", "learning_level": "beginner"}

results = await backend.find_by(**filters)
```

### Graph-Aware Search (Relationship-Based)

Uses custom Cypher queries for relationship traversal:

```python
# Converts relationship filters to Cypher patterns
patterns = request.to_graph_patterns()
# {"ready_to_learn": "EXISTS((ku)<-[:MASTERED]-(user:User {uid: $user_uid}))"}

# Builds domain-specific graph query
cypher = """
MATCH (ku:Curriculum)
WHERE {property_filters} AND {graph_patterns}
OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq:Curriculum)
...
"""
```

### Query Mode Selection

The search backend routes automatically based on filters:

```python
if search_request.has_relationship_filters():
    # Graph-aware: Custom Cypher with relationship context
    result = await backend.graph_aware_search(request, user_uid)
else:
    # Simple: UniversalNeo4jBackend property queries
    result = await backend.simple_search(request)
```

**See:** [Search Architecture](../architecture/SEARCH_ARCHITECTURE.md) for complete documentation.

## Performance Guidelines

### Query Optimization

1. **Index usage**: Ensure queries hit indexed properties (`uid`, `user_uid`)
2. **Limit early**: Use `LIMIT` as early as possible in query
3. **Selective MATCH**: Start with most selective node (usually User)
4. **OPTIONAL MATCH**: Use for data that may not exist

### Performance Thresholds

| Query Type | Target Latency | Action if Exceeded |
|------------|----------------|-------------------|
| Simple fetch | < 50ms | Investigate index |
| With relationships | < 100ms | Consider batch |
| MEGA-QUERY | < 500ms | Profile query plan |
| Complex traversal | < 1s | Split or cache |

## Related Documentation

- [Search Architecture](../architecture/SEARCH_ARCHITECTURE.md) - How search uses query patterns
- [ADR-015: MEGA-QUERY](../decisions/ADR-015-mega-query-rich-queries-completion.md) - MEGA-QUERY decision
- [Neo4j Database Architecture](../architecture/../patterns/query_architecture.md) - Database architecture
- [SearchService Pattern](search_service_pattern.md) - Domain search protocols
- `/adapters/persistence/neo4j/query/` - Query module implementation
