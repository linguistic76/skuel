---
name: skuel-search-architecture
description: Explains SKUEL's unified search architecture, SearchRouter orchestration, graph-aware search, and BaseService pattern. Use when implementing search features, optimizing search queries, understanding SearchRouter, working with domain search services, or discussing unified search across all domains.
---

# SKUEL Search Architecture (February 2026 - EntityType-Driven)

## Core Principle

> "SearchRouter is THE single path for all external search access"

**One Path Forward:** Never call domain search services directly from routes. Always use SearchRouter.

**Unified Architecture (ADR-023, v3.0.0 Feb 2026):** SearchRouter dispatches by `EntityType`/`NonKuDomain` enum — type-safe, no stringly-typed domain checks. All search services extend `BaseService[Backend, Model]`.

## Architecture Overview

```
External Callers (One Path Forward):
├── /search routes      → SearchRouter.search() or search_domains()
├── /api/search/unified → SearchRouter.advanced_search(SearchRequest)
└── Cross-domain        → SearchRouter.unified_search()

SearchRouter (THE Orchestrator):
├── EntityType/NonKuDomain → domain search service (type-safe dispatch)
│   └── ALL 9 searchable domains
└── Cross-domain           → self.search_domains() (aggregation)
```

## Key Files

| Component | File | Purpose |
|-----------|------|---------|
| **Orchestrator** | `/core/models/search/search_router.py` | THE single path |
| **Models** | `/core/models/search_request.py` | SearchRequest/SearchResponse |
| **Routes** | `/adapters/inbound/search_routes.py` | HTTP handling |
| **Domain Services** | `/core/services/{domain}/{domain}_search_service.py` | Domain logic |
| **Domain Backends** | `/adapters/persistence/neo4j/domain_backends.py` | Domain-specific relationship Cypher |
| **Universal Backend** | `/adapters/persistence/neo4j/universal_backend.py` | Shell (~527 lines); methods in 6 mixin files |
| **Backend Mixins** | `_crud_mixin.py`, `_search_mixin.py`, `_relationship_query_mixin.py`, `_relationship_crud_mixin.py`, `_user_entity_mixin.py`, `_traversal_mixin.py` | One file per protocol group |

**Backend structure (March 2026):** `universal_backend.py` is a shell; all persistence operations live in 6 focused mixin files. `_relationship_mixin.py` was split into `_relationship_query_mixin.py` (graph-native queries, `relate()` fluent API, edge metadata) and `_relationship_crud_mixin.py` (create/delete/validate, `has_relationship`, batch ops). Public API unchanged.

## Searchable Domains (9 — No MOC)

| Domain | Entities | Search Mode | Pattern |
|--------|----------|-------------|---------|
| **All 9 Domains** | Task, Goal, Habit, Event, Choice, Principle, KU, LS, LP | Graph-Aware | BaseService |

**Note:** MOC is NOT a searchable domain — it is emergent identity (any Ku with ORGANIZES relationships). The Activity/Curriculum distinction has been eliminated; all 9 domains are peers.

## Unified BaseService Pattern (ADR-023, January 2026 DomainConfig)

All search services extend `BaseService[Backend, Model]` using **DomainConfig** — the single source of truth for configuration. Direct class-attribute style (`_dto_class`, `_model_class`, etc.) was migrated to DomainConfig in January 2026.

```python
# Curriculum domain example (shared content, admin creates, all users read)
class LsSearchService(BaseService["BackendOperations[LearningStep]", LearningStep]):
    _config = create_curriculum_domain_config(
        dto_class=LearningStepDTO,
        model_class=LearningStep,
        domain_name="ls",
        search_fields=("title", "intent", "description"),
        category_field="domain",
    )
    # _user_ownership_relationship = None by default for curriculum

# Activity domain example (user-owned content)
class TasksSearchService(BaseService[TasksOperations, Task]):
    _config = create_activity_domain_config(
        dto_class=TaskDTO,
        model_class=Task,
        domain_name="tasks",
        date_field="due_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
    )
```

**All methods inherited from BaseService:**
- `search(query, limit)` - Text search on configured `search_fields`
- `get_by_status()`, `get_by_category()`, `list_categories()`
- `get_prerequisites()`, `get_enables()`
- `verify_ownership()` — Activity domains only (OWNS relationship)

## Common Implementation Patterns

### Single Domain Search

```python
# Route by EntityType - type-safe dispatch
result = await search_router.search(EntityType.TASK, "urgent deadline")
result = await search_router.search(EntityType.KU, "python basics")
```

### Cross-Domain Search

```python
# SearchRouter aggregates from multiple domains
results = await search_router.search_domains(
    [EntityType.TASK, EntityType.KU, EntityType.LP],
    "machine learning"
)
```

### Unified Search (All 9 Domains)

```python
# Search across everything
result = await search_router.unified_search("health fitness")
# Returns UnifiedSearchResult with results_by_domain + top_results
```

### Advanced Search with Graph Filters

```python
# Advanced search with graph and tag filters via SearchRequest
request = SearchRequest(
    query_text="machine learning",
    entity_types=[EntityType.KU],
    connected_to_uid="ku.python-basics",
    connected_relationship=RelationshipName.ENABLES_KNOWLEDGE,
    tags_contain=["python"],
)
result = await search_router.advanced_search(request)
```

### Domain-Specific Methods

```python
# LS-specific (call on service directly, not via SearchRouter)
await ls_service.search.get_for_learning_path("lp:python-mastery")

# LP-specific
await lp_service.search.get_aligned_with_goal("goal:learn-python")
```

## SearchRouter Method Reference (v3.0.0)

| Method | Use Case |
|--------|----------|
| `search(entity_type, query)` | Single-domain text search |
| `search_domains(entity_types, query)` | Multi-domain aggregation |
| `unified_search(query)` | All 9 domains |
| `advanced_search(SearchRequest)` | Filters, graph patterns, tags |
| `faceted_search(request, user_uid)` | Legacy; prefer `advanced_search` |

| Aspect | Value |
|--------|-------|
| **Domains** | 9 (Task, Goal, Habit, Event, Choice, Principle, KU, LS, LP) |
| **User Ownership** | Activity domains use OWNS; Curriculum uses None (shared) |
| **Result Type** | `UnifiedSearchResult` with `results_by_domain` + `top_results` |
| **Dispatch** | EntityType/NonKuDomain enum (type-safe, no string checks) |

## Common Gotchas

1. **Always use SearchRouter** for external access — never call domain services directly from routes
2. **Curriculum content is shared** — `_user_ownership_relationship = None` (no OWNS filter)
3. **MOC is not a searchable domain** — it's emergent identity via ORGANIZES relationships on Ku nodes
4. **9 searchable domains, not 10** — there is no MOC EntityType

## UserContext and Search

SearchRouter and BaseService search services are independent of UserContext. They run their own domain queries and do not consume MEGA_QUERY or CONSOLIDATED_QUERY output. If you need to personalize or enrich search results with user state, the right approach is:

```python
# Get user state (standard context is sufficient for most search personalization)
context = await builder.build(user_uid)    # UIDs + ActivityReport — fast (~50-100ms)

# If intelligence-based ranking is needed alongside search
context = await builder.build_rich(user_uid)  # Full entity + graph — slower (~150-200ms)

# Run search independently — SearchRouter does NOT accept UserContext
results = await search_router.search(EntityType.TASK, query)
```

**Key distinction:** `MEGA_QUERY` (via `build()` and `build_rich(window=...)`) builds the user's *current state*. SearchRouter queries are *content searches* across entity properties. They solve different problems and compose independently.

**See:** `@user-context-intelligence` skill for MEGA_QUERY vs CONSOLIDATED_QUERY details.

## Related Skills

- **[neo4j-cypher-patterns](../neo4j-cypher-patterns/SKILL.md)** - Cypher queries used in search services
- **[python](../python/SKILL.md)** - BaseService pattern for search services
- **[user-context-intelligence](../user-context-intelligence/SKILL.md)** - Build paths when enriching search with user state

## Foundation

- **[neo4j-cypher-patterns](../neo4j-cypher-patterns/SKILL.md)** - Understanding graph queries

## See Also

- `/docs/architecture/SEARCH_ARCHITECTURE.md` - Complete architecture reference
- `/docs/decisions/ADR-023-curriculum-baseservice-migration.md` - Unified BaseService decision
- `/docs/patterns/search_service_pattern.md` - Service pattern guide
- `/docs/patterns/query_architecture.md` - Query builders and patterns
