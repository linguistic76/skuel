---
name: skuel-search-architecture
description: Explains SKUEL's unified search architecture, SearchRouter orchestration, graph-aware search, and BaseService pattern. Use when implementing search features, optimizing search queries, understanding SearchRouter, working with domain search services, or discussing unified search across all domains.
---

# SKUEL Search Architecture (January 2026 - Unified)

## Core Principle

> "SearchRouter is THE single path for all external search access"

**One Path Forward:** Never call domain search services directly from routes. Always use SearchRouter.

**Unified Architecture (ADR-023):** All 14 domains are peers - no Activity/Curriculum distinction. All search services extend `BaseService[Backend, Model]`.

## Architecture Overview

```
External Callers (One Path Forward):
├── /search routes      → SearchRouter.faceted_search()
├── /api/search/unified → SearchRouter.advanced_search()
└── GraphQL queries     → SearchRouter.faceted_search()

SearchRouter (THE Orchestrator):
├── Graph-Aware Domains → domain.search.graph_aware_faceted_search()
│   └── ALL 10 searchable domains (January 2026 - Unified)
└── Cross-domain        → self.search_domains() (aggregation)
```

## Key Files

| Component | File | Purpose |
|-----------|------|---------|
| **Orchestrator** | `/core/models/search/search_router.py` | THE single path |
| **Models** | `/core/models/search_request.py` | SearchRequest/SearchResponse |
| **Routes** | `/adapters/inbound/search_routes.py` | HTTP handling |
| **Domain Services** | `/core/services/{domain}/{domain}_search_service.py` | Domain logic |
| **Backends** | `/adapters/persistence/neo4j/{ls,lp,moc}_backend.py` | Protocol implementations |

## Searchable Domains (January 2026 - All Unified)

| Domain | Entities | Search Mode | Pattern |
|--------|----------|-------------|---------|
| **All 10 Domains** | Task, Goal, Habit, Event, Choice, Principle, KU, LS, LP, MOC | Graph-Aware | BaseService |

**Note:** The Activity/Curriculum distinction has been eliminated. All domains are peers.

## Unified BaseService Pattern (ADR-023)

All search services extend `BaseService[Backend, Model]`:

```python
class LsSearchService(BaseService["LsUniversalBackend", Ls]):
    # Required - DTO and model classes
    _dto_class = LearningStepDTO
    _model_class = Ls

    # Search configuration
    _search_fields: ClassVar[list[str]] = ["title", "intent", "description"]
    _search_order_by: str = "updated_at"

    # Curriculum features (opt-in via configuration)
    _content_field: str = "description"
    _supports_user_progress: bool = True  # Enable mastery tracking
    _prerequisite_relationships: ClassVar[list[str]] = ["REQUIRES_STEP"]
    _enables_relationships: ClassVar[list[str]] = ["ENABLES_STEP"]

    # Ownership (None = shared content, no user filter)
    _user_ownership_relationship: ClassVar[str | None] = None

    # Graph enrichment for faceted search
    _graph_enrichment_patterns: ClassVar[list[tuple[str, str, str, str]]] = [
        ("CONTAINS_KNOWLEDGE", "Ku", "knowledge_units", "outgoing"),
    ]
```

**All methods inherited from BaseService:**
- `search(query, limit)` - Text search on `_search_fields`
- `graph_aware_faceted_search(request)` - Unified filter interface
- `get_by_domain()`, `get_by_status()`, `get_by_category()`
- `get_with_content()`, `get_with_context()`
- `get_prerequisites()`, `get_enables()`, `get_hierarchy()`
- `get_user_progress()`, `update_user_mastery()`

## Common Implementation Patterns

### Text Search + Property Filters

```python
# Unified via SearchRequest - frontend uses one model for all domains
request = SearchRequest(
    query="python",
    domains=[Domain.TECH],
    status="active",
)
response = await search_router.faceted_search(request, user_uid)
```

### Graph-Aware Search (All Domains)

```python
# Graph patterns applied to ALL 10 searchable domains
request = SearchRequest(
    query="python",
    ready_to_learn=True,      # Graph pattern: prerequisites met
    supports_goals=True,       # Graph pattern: linked to user goals
)
response = await search_router.faceted_search(request, user_uid)
# Results include _graph_context with relationship summaries
```

### Cross-Domain Search

```python
# SearchRouter aggregates from multiple domains
request = SearchRequest(
    query="machine learning",
    entity_types=[EntityType.TASK, EntityType.KU, EntityType.LP],
)
response = await search_router.faceted_search(request, user_uid)
```

### Domain-Specific Methods

```python
# LS-specific
await ls_service.search.get_for_learning_path("lp:python-mastery")
await ls_service.search.get_standalone_steps()

# LP-specific
await lp_service.search.get_by_path_type(LpType.ADAPTIVE)
await lp_service.search.get_aligned_with_goal("goal:learn-python")

# MOC-specific
await moc_service.search.get_templates(domain=Domain.TECH)
await moc_service.search.get_related_mocs(moc_uid)
```

## Graph-Aware Domains Configuration

```python
# January 2026 - All 10 searchable domains are graph-aware
_GRAPH_AWARE_DOMAINS: frozenset[str] = frozenset(
    {"tasks", "goals", "habits", "events", "choices", "principles", "ku", "ls", "lp", "moc"}
)
```

| Aspect | Value |
|--------|-------|
| **Domains** | All 10 searchable domains |
| **User Ownership** | Activity domains use OWNS; Curriculum uses None (shared) |
| **Graph Patterns** | ready_to_learn, supports_goals, etc. |
| **Result Context** | `_graph_context` with relationships |
| **Method** | `graph_aware_faceted_search()` |

## Common Gotchas

1. **Always use SearchRouter** for external access - never call domain services directly from routes
2. **Curriculum content is shared** - `_user_ownership_relationship = None` (no OWNS filter)
3. **Use SearchRequest unified filters** - custom filter classes were removed in ADR-023
4. **All domains use graph-aware search** - the Activity/Curriculum distinction no longer exists

## Related Skills

- **[neo4j-cypher-patterns](../neo4j-cypher-patterns/SKILL.md)** - Cypher queries used in search services
- **[python](../python/SKILL.md)** - BaseService pattern for search services

## Foundation

- **[neo4j-cypher-patterns](../neo4j-cypher-patterns/SKILL.md)** - Understanding graph queries

## See Also

- `/docs/architecture/SEARCH_ARCHITECTURE.md` - Complete architecture reference
- `/docs/decisions/ADR-023-curriculum-baseservice-migration.md` - Unified BaseService decision
- `/docs/patterns/search_service_pattern.md` - Service pattern guide
- `/docs/patterns/query_architecture.md` - Query builders and patterns
