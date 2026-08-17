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
├── /search routes      → SearchRouter.faceted_search() / search() / search_domains()
├── /api/search/unified → SearchRouter.advanced_search(SearchRequest)
└── Cross-domain NL     → SearchRouter.intelligent_search()

SearchRouter (THE Orchestrator):
├── EntityType/NonKuDomain → domain search service (type-safe dispatch)
│   └── ALL 12 searchable domains
└── Cross-domain           → self.search_domains() (aggregation)
```

## Key Files

| Component | File | Purpose |
|-----------|------|---------|
| **Orchestrator** | `/core/orchestrator/search_router.py` | THE single path |
| **Models** | `/core/models/search_request.py` | SearchRequest/SearchResponse |
| **Routes** | `/adapters/inbound/search_routes.py` | HTTP handling |
| **Domain Services** | `/core/services/{domain}/{domain}_search_service.py` | Domain logic |
| **Domain Backends** | `/adapters/persistence/neo4j/backends/` | Domain-specific relationship Cypher (9 cluster files) |
| **Universal Backend** | `/adapters/persistence/neo4j/universal_backend.py` | Shell; methods in 11 mixin files |
| **Backend Mixins** | `_crud_mixin.py`, `_search_mixin.py`, `_search_raw_mixin.py`, `_temporal_mixin.py`, `_prereq_progress_mixin.py`, `_context_query_mixin.py`, `_relationship_query_mixin.py`, `_relationship_ordered_mixin.py`, `_relationship_crud_mixin.py`, `_user_entity_mixin.py`, `_traversal_mixin.py` | One file per protocol group |

**Backend structure (April 2026):** `universal_backend.py` is a shell; all persistence operations live in 11 focused mixin files. The March split of `_relationship_mixin.py` into `_relationship_query_mixin.py` + `_relationship_crud_mixin.py` was followed by the April split of the oversized `_search_mixin.py` (~1,233 lines) along section markers: core `EntitySearchOperations[T]` stayed in `_search_mixin.py` (find_by, search, count, health_check, execute_query), while raw search primitives moved to `_search_raw_mixin.py`, temporal queries to `_temporal_mixin.py`, prerequisite/progress queries to `_prereq_progress_mixin.py`, and registry-driven context queries to `_context_query_mixin.py`. A further April pass extracted the ordered/hierarchical section of `_relationship_query_mixin.py` (~1,174 lines) into `_relationship_ordered_mixin.py`, leaving the core mixin at ~666 lines. Public API unchanged.

## Searchable Domains (12 — No MOC)

| Group | Entities | Search Mode | Pattern |
|-------|----------|-------------|---------|
| **Activity (6)** | Task, Goal, Habit, Event, Choice, Principle | Graph-Aware | BaseService |
| **Curriculum (3)** | Ku, PathStep, LearningPath | Graph-Aware | BaseService |
| **Learning Loop (3)** | Exercise, RevisedExercise, UserEntry | Graph-Aware | BaseService |

**Note:** MOC is NOT a searchable domain — it is emergent identity (any Ku with ORGANIZES relationships). Ku joined `_SEARCHABLE_DOMAINS` in July 2026 (content campaigns made Kus full lessons; `KuService` now exposes `.search` as the sub-service attribute, PS pattern). Learning Loop services implement `SupportsGraphAwareSearch` directly (no `.search` sub-service). SearchRouter detects this via `isinstance(domain_service, SupportsGraphAwareSearch)` fallback.

**UserEntry privacy line (July 2026):** `SearchRouter.search(USER_ENTRY, ...)` REQUIRES `user_uid` (refused unscoped). UserEntry is excluded from the default "All Types" sweep + `advanced_search` aggregation; it participates only when explicitly requested AND user-scoped — the `/search` "My Entries" filter routes through OWNS-scoped `graph_aware_faceted_search()`, and a multi-type `entity_types` filter sweeps it owner-scoped. Registry completeness is guarded by `tests/unit/models/test_search_router_registry.py`.

## Unified BaseService Pattern (ADR-023, January 2026 DomainConfig)

All search services extend `BaseService[Backend, Model]` using **DomainConfig** — the single source of truth for configuration. Direct class-attribute style (`_dto_class`, `_model_class`, etc.) was migrated to DomainConfig in January 2026.

```python
# Curriculum domain example (shared content, admin creates, all users read)
class PsSearchService(BaseService["PsOperations", PathStep]):
    _config = create_curriculum_domain_config(
        dto_class=PathStepDTO,
        model_class=PathStep,
        domain_name="ps",
        search_fields=("title", "intent", "description"),
        category_field="nous",  # NOUS topic membership (array — `has` semantics)
    )
    # user_ownership_relationship=None by default for curriculum (DomainConfig field)

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
    [EntityType.TASK, EntityType.PATH_STEP, EntityType.LEARNING_PATH],
    "machine learning"
)
```

### Intelligent Search (Cross-Domain, NL Query)

```python
# Natural-language cross-domain search (semantic filter extraction)
result = await search_router.intelligent_search("health fitness", user_uid=user_uid)
# Returns UnifiedSearchResult with results_by_domain + top_results
```

### Advanced Search with Graph Filters

```python
# Advanced search with graph and tag filters via SearchRequest.
# user_uid scopes every strategy (text/tags/graph) per each domain's
# SearchVisibility declaration; without it, user-owned domains are
# skipped fail-closed and only shared content returns.
request = SearchRequest(
    query_text="machine learning",
    entity_types=[EntityType.KU],
    connected_to_uid="ku.python-basics",
    connected_relationship=RelationshipName.ENABLES_KNOWLEDGE,
    tags_contain=["python"],
    user_uid=user_uid,
)
result = await search_router.advanced_search(request)
```

### Domain-Specific Methods

```python
# PS-specific (call on service directly, not via SearchRouter)
await ps_service.search.get_standalone_steps()

# LP-specific (staged, PLANNED — no live consumer yet)
await lp_service.search.get_aligned_with_goal("goal_learn-python_xyz")
```

## SearchRouter Method Reference (v3.0.0)

| Method | Use Case |
|--------|----------|
| `search(entity_type, query, user_uid=...)` | Single-domain text search (USER_ENTRY requires `user_uid`) |
| `search_domains(entity_types, query, user_uid=...)` | Multi-domain aggregation |
| `intelligent_search(query, user_uid)` | NL cross-domain with semantic filter extraction |
| `advanced_search(SearchRequest)` | Filters, graph patterns, tags (`request.user_uid` scopes all strategies) |
| `faceted_search(request, user_uid)` | THE entry point for UI-driven search (/search) |
| `retrieve_scoped_chunks(...)` | Scoped ContentChunk retrieval for semantic boost / RAG contexts (FULL tier) |

**Search-event logging (July 2026):** all three external entry points (faceted/intelligent/advanced) publish `search.executed` → `:SearchEvent` node — one event per external search (`intelligent_search`'s internal faceted fan-out passes `log_event=False`; empty queries never logged; fail-soft; tier-independent). See SEARCH_ARCHITECTURE.md § Search-Event Logging.

| Aspect | Value |
|--------|-------|
| **Domains** | 12 (Task, Goal, Habit, Event, Choice, Principle, Ku, PathStep, LearningPath, Exercise, RevisedExercise, UserEntry) |
| **User Ownership** | `DomainConfig.search_visibility`: Activities/UserEntry/RevisedExercise `OWNER_ONLY`, PS/LP/KU `PUBLIC`, Exercise `SCOPE_AWARE` (curriculum visible to all; owned scopes via OWNS/SHARES_WITH/group membership) |
| **Result Type** | `UnifiedSearchResult` with `results_by_domain` + `top_results` |
| **Dispatch** | EntityType/NonKuDomain enum (type-safe, no string checks) |

## Priority Scoring — Unified Across 6 Activity Domains

All 6 Activity Domain search services (`{tasks,goals,habits,events,choices,principles}_search_service.py`) implement `get_prioritized(user_context)` by delegating to a single `score_<domain>(entity, context) -> PriorityScore` function in `core/models/search/scoring.py`. The same scorers also back `SearchRouter._score_results()` for cross-domain ranking.

Each scorer composes shared `ComponentScore` helpers with domain-specific weights that sum to 1.0:

| Helper | Produces (normalized 0–1) | Reused by |
|--------|---------------------------|-----------|
| `score_deadline_proximity(target_date)` | Urgency from days-until | Task, Goal, Event, Choice |
| `score_priority_level(priority)` | CRITICAL/HIGH/MEDIUM/LOW → 1.0/0.8/0.5/0.25 | Task, Goal, Choice |
| `score_goal_alignment(goal_uid, active_goal_uids)` | 1.0 if linked to active goal | Task, Goal, Event, Habit |
| `score_streak_protection(habit_uid, streaks, active_habits)` | Protects long streaks | Task, Habit, Event |
| `score_progress_momentum(progress)` | Inverted-U — ~0.5 favored over stuck/done | Goal |

`PriorityScore.total` is the weighted sum; `.components` + `.explain()` expose per-component breakdown for debugging. Service-level canonical pattern:

```python
scored = [(e, score_<domain>(e, user_context).total) for e in entities]
scored.sort(key=get_result_score, reverse=True)
```

**Frequency Windows (Habits, separate concern):** `get_frequency_window_days()` in `timestamp_helpers.py` powers the Habits-specific `get_upcoming()`/`get_overdue()` overrides only — the *prioritization* scorer uses the unified pipeline above.

**Config-Driven Temporal Queries:** `TimeQueryMixin.get_upcoming()` / `get_overdue()` / `get_active()` use `DomainConfig` fields:
- `date_field` — column driving upcoming/overdue (e.g., `target_date`, `decision_deadline`)
- `temporal_exclude_statuses` — defaults to the 4 `EntityStatus.is_terminal()` values
- `temporal_secondary_sort` — optional secondary ORDER BY (Events use `"start_time"`)
- `completed_statuses` — excluded from `get_active` (Goals extend to `("completed", "cancelled")`)

Tasks, Goals, Events, and Choices use the base implementation. Only Habits and Principles override (fundamentally different semantics — frequency windows / 90-day review threshold).

**See:** `/docs/architecture/SEARCH_ARCHITECTURE.md` → "Priority Scoring — Unified Across 6 Activity Domains" for full weights and breakdown.

## Search Index Foundation (Bootstrap)

At startup, `Neo4jSchemaManager` creates all indexes needed for search:

| Index Type | Method | Tier | What It Powers |
|-----------|--------|------|---------------|
| **Full-text indexes** | `sync_fulltext_indexes()` | Always (CORE + FULL) | Lucene keyword search — 14 domains |
| **Vector indexes** | `sync_vector_indexes()` | FULL only | 1024-dim cosine — Entity, ContentChunk, ReferenceChunk, Ku, PathStep, LearningPath (bootstrap) + Goal, Task per-label (`scripts/create_vector_indexes.py`) |

Full-text indexes are the **Cypher-first search foundation**, created in both tiers. Who actually reads them is narrower than "always available" suggests, so be precise:

- **SearchRouter's hybrid rung** (August 2026) is the one production reader — Ku/PathStep/LearningPath, FULL tier, via `hybrid_search_with_metrics` (Lucene RRF-merged with vector similarity). It sits in `_execute_advanced_search`, so it serves **`advanced_search()` / `/api/search/unified`** — the `/search` HTML page runs `faceted_search` and is still on `CONTAINS`. See SEARCH_ARCHITECTURE § Hybrid Fulltext + Vector Rung.
- **Every other text search is `CONTAINS`**, including all of CORE tier and all OWNER_ONLY domains — and that `CONTAINS` is **case-INSENSITIVE** (`faceted_search_raw` and `build_text_search_query` both lower-case each side). Fulltext buys relevance ranking and vector recall, not case-insensitivity; it also does not stem (shipped analyzer is `standard-no-stop-words`) and, being token-based, loses the substring hits `CONTAINS` finds (`photosyn` misses "Photosynthesis").
- ⚠️ **Two `search` methods, two layers, one name.** The *backend* `_SearchMixin.search()` IS case-SENSITIVE `CONTAINS` — but its only production caller is `PsAiService.search_by_semantic_query`'s fallback, not `/search` or `/api/search/unified`. Those reach the *service-layer* `SearchOperationsMixin.search()` → `text_search_raw`, which is case-insensitive. Check the layer before reasoning about the predicate.
- Making domain-level search fulltext-first is the named **D1(b) follow-on** in `docs/roadmap/deferred-work.md`; until it lands, do not assume a fulltext index has a reader just because it exists.

Index names come from `NeoLabel.fulltext_index_name()` — THE rule shared by creation and lookup (`PathStep` → `path_step_fulltext_idx`; never flat `label.lower()`).

Vector indexes are only created when `INTELLIGENCE_TIER=full` (embeddings enabled). When absent, search gracefully falls back to keyword-only results.

**Key file:** `adapters/persistence/neo4j/neo4j_schema_manager.py`

## Common Gotchas

1. **Always use SearchRouter** for external access — never call domain services directly from routes
2. **Curriculum content is shared** — DomainConfig `user_ownership_relationship=None` derives `SearchVisibility.PUBLIC` (no ownership filter); the old `_user_ownership_relationship` ClassVar is gone (it bypassed DomainConfig and OWNS-scoped even shared domains)
3. **MOC is not a searchable domain** — it's emergent identity via ORGANIZES relationships on Ku nodes
4. **12 searchable domains** — 6 Activity + 3 Curriculum (Ku, PS, LP) + 3 Learning Loop; MOC is not an EntityType
5. **UserEntry search requires `user_uid`** — refused unscoped; excluded from cross-domain sweeps (privacy line)
6. **Every strategy is visibility-scoped** — `build_search_visibility_clause()` is THE single Cypher composition point (text/tags/graph/faceted); never add a per-strategy ownership filter. See SEARCH_ARCHITECTURE § Ownership Scoping
7. **Full-text indexes are always created** — regardless of INTELLIGENCE_TIER; vector indexes are FULL-only

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
