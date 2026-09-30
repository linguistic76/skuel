---
name: skuel-search-architecture
description: Explains SKUEL's unified search architecture, SearchRouter orchestration, graph-aware search, and BaseService pattern. Use when implementing search features, optimizing search queries, understanding SearchRouter, working with domain search services, or discussing unified search across all domains.
---

# SKUEL Search Architecture

## Core Principle

> "SearchRouter is THE single path for all external search access"

**One Path Forward:** Never call domain search services directly from routes. Always use SearchRouter.

`SearchRouter` (`core/orchestrator/search_router.py`) dispatches by `EntityType` / `NonKuDomain` enum — type-safe, no stringly-typed domain checks. Every domain search service extends `BaseService[Backend, Model]` and is configured by its `DomainConfig` (ADR-023).

## Architecture Overview

```
External callers (One Path Forward) — every one goes through the router:
├── /search, /search/results, /search/subtopics   → faceted_search() / list_tags() / list_nous_subtopics() / nous_subtopic_map()
├── /explore, /explore/library (explore_ui.py)     → faceted_search() / tag_frequencies() / nous_subtopic_map()
├── POST /api/search/unified (CSRF-protected)      → advanced_search(SearchRequest)
├── /api/search/intelligent                        → intelligent_search(q, user_uid=...)
└── Askesis ContextRetriever (RAG)                 → retrieve_scoped_chunks(request, user_uid=...)

SearchRouter (THE orchestrator):
├── EntityType/NonKuDomain → domain search service (`_SERVICE_REGISTRY`)
│   └── the `_SEARCHABLE_DOMAINS` frozenset — 12 EntityTypes
└── Cross-domain → search_domains() / _cross_domain_search() (aggregation)
```

`git grep "search_router\."` under `adapters/inbound/` is the live caller list; the routes above are what it printed when this was reviewed.

## Key Files

| Component | File | Purpose |
|-----------|------|---------|
| **Orchestrator** | `core/orchestrator/search_router.py` | THE single path (`SearchRouter`, `SearchResultItem`, `UnifiedSearchResult`) |
| **Request/response models** | `core/models/search_request.py` | `SearchRequest` (+ `from_form_params`), `SearchResponse`, `BodyFoldReport`, `build_facet_counts` |
| **Routes** | `adapters/inbound/search_routes.py` | `/search*` pages + the two JSON endpoints; `SEARCH_PAGE_ENTITY_TYPES` / `scope_to_search_page` |
| **Domain search services** | `core/services/{domain}/{domain}_search_service.py` | Per-domain `DomainConfig` + domain-specific reads |
| **Service search mixin** | `core/services/mixins/search_operations_mixin.py` | `SearchOperationsMixin` — the inherited `search()`, `search_by_tags()`, `graph_aware_faceted_search()`, `tag_frequencies()`, … |
| **Universal backend** | `adapters/persistence/neo4j/universal_backend.py` | A shell composed of the `_*Mixin` files beside it — read the class bases for the list |
| **Search Cypher** | `adapters/persistence/neo4j/_search_raw_mixin.py`, `query/cypher/crud_queries.py`, `query/cypher/relationship_filter_fragments.py` | `faceted_search_raw`, `text_search_raw`; `build_text_search_query`, `build_search_visibility_clause`; the EXISTS fragments |
| **Vector / fulltext** | `core/services/neo4j_vector_search_service.py`, `adapters/persistence/neo4j/vector_search_backend.py` | FULL tier: `find_similar_by_text`, `hybrid_search_with_metrics`, `query_vector_index` / `query_fulltext_index` (both publication-gated) |

**The backend has no `search` method.** `EntitySearchOperations` (`core/ports/base_protocols.py`) declares `find_by`, `count`, `find_by_date_range`, `get_user_entities` and the `*_raw` primitives (`text_search_raw`, `faceted_search_raw`, `graph_aware_search_raw`, `array_any_match_raw`, …) — census it with `inspect.getmembers`, never quote a count. The one `search` is the service-layer `SearchOperationsMixin.search(query, limit=50, user_uid=None)` → `backend.text_search_raw` (case-insensitive `CONTAINS`).

## Searchable Domains (12 — no MOC)

| Group | Entities | `SearchVisibility` |
|-------|----------|--------------------|
| **Activity (6)** | Task, Goal, Habit, Event, Choice, Principle | `OWNER_ONLY` |
| **Curriculum (3)** | Ku, PathStep, LearningPath | `PUBLIC` |
| **Learning Loop (3)** | Exercise, RevisedExercise, UserEntry | Exercise `SCOPE_AWARE`; RevisedExercise, UserEntry `OWNER_ONLY` |

- MOC is NOT a searchable domain — emergent identity (any Entity with `ORGANIZES` edges). Group and Finance are not in `_SEARCHABLE_DOMAINS`.
- Ku, PS and LP expose the sub-service as `.search`; the Learning Loop services implement `SupportsGraphAwareSearch` / `SupportsTextSearch` directly (no `.search` attribute) — `SearchRouter._get_search_service` resolves both shapes.
- Registry completeness (registry key → constructor parameter → `Services` field) is held by `tests/unit/models/test_search_router_registry.py`.

**Owner-scope gate:** `SearchRouter.search()` REQUIRES `user_uid` for **every** `OWNER_ONLY` domain and refuses without it (`_admits_anonymous_search`) — `build_search_visibility_clause` emits no ownership predicate when there is no user, so an unscoped call would return every user's rows. Only `PUBLIC` and `SCOPE_AWARE` may be searched anonymously; a service that declares nothing is refused too (default-deny). Every aggregate caller treats a refused domain as "contributes nothing".

**UserEntry aggregation rules:** excluded from the default "All Types" sweep and from `advanced_search` aggregation; it participates only when explicitly requested AND user-scoped. `faceted_search` keeps a by-name `user_entry` refusal at the entry point.

**A surface's result scope is NOT `_SEARCHABLE_DOMAINS`:** the `/search` page searches the **6 Activity Domains + Ku** — `SEARCH_PAGE_ENTITY_TYPES` / `scope_to_search_page` in `search_routes.py` narrow the REQUEST. PathStep, LearningPath, Exercise, RevisedExercise and UserEntry are off that page; the Type dropdown offers the 6 Activity Domains and Ku is reached through the **Nous** facet. Scoping a surface means moving all three vocabulary sites together — the scope tuple, `_ENTITY_TYPE_OPTIONS` (`ui/search/components.py`), `entityTypeFilters` (`static/js/skuel.js`); `tests/unit/test_search_page_scope.py` derives them from each other. Declare a surface's scope at its own entry point; never edit the router's shared sweep default — `/explore` and `/explore/library` ride the same `faceted_search` with their own `entity_types`. Type and Nous are mutually exclusive by construction (`nous` is a property only curriculum nodes carry), so the markup disables the unused control. **See:** `docs/architecture/SEARCH_ARCHITECTURE.md`.

## Unified BaseService Pattern (DomainConfig)

Every search service extends `BaseService[Backend, Model]` with a `DomainConfig` — the single source of truth for `search_fields`, `search_order_by`, `category_field`, `date_field`, `search_visibility` / `read_visibility`, `ownership_property`, temporal exclusions.

```python
# Curriculum domain (shared content — PUBLIC, no ownership filter)
class PsSearchService(BaseService["PsOperations", PathStep]):
    _config = create_curriculum_domain_config(
        dto_class=PathStepDTO,
        model_class=PathStep,
        domain_name="ps",
        search_fields=("title", "intent", "description"),
        category_field="nous",  # NOUS topic membership (array — `has` semantics)
    )

# Activity domain (user-owned — OWNER_ONLY)
class TasksSearchService(BaseService["TasksOperations", Task]):
    _config = create_activity_domain_config(
        dto_class=TaskDTO,
        model_class=Task,
        domain_name="tasks",
        date_field="due_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
    )
```

**Inherited reads, with their default caps** (batch-5 lesson: a read described as complete may carry one):

| Mixin | Method | Default |
|-------|--------|---------|
| `SearchOperationsMixin` | `search(query, limit=50, user_uid=None)`, `search_by_tags(tags, match_all=False, limit=50, user_uid=None)` | 50 |
| | `graph_aware_faceted_search(request, user_uid)` | `request.limit` (SearchRequest default 20, max 200) |
| | `get_by_status(status, limit=100, user_uid=None)`, `get_by_category(category, user_uid=None, limit=100)` | 100 |
| | `get_for_user_filtered(user_uid, status_filter="all")` → `backend.find_by(**filters)` | 100 (`find_by`'s default — the daily plan's domain stats read through it; a silent cap, not a feature) |
| | `list_user_categories(user_uid)`, `list_all_categories()`, `tag_frequencies(user_uid=None)`, `count(**filters)` | — |
| `RelationshipOperationsMixin` | `get_prerequisites(uid, depth=3)`, `get_enables(uid, depth=3)` | depth 3 |
| `TimeQueryMixin` | `get_upcoming(days_ahead=7, user_uid=None, limit=100)`, `get_overdue(user_uid=None, limit=100)`, `get_active(user_uid, limit=100)` | 100 |
| `CrudOperationsMixin` | `verify_ownership(uid, user_uid)`, `get_for_user(uid, user_uid)` | — |

Read the mixin for the full signature; there is no `list_categories()`.

## Common Implementation Patterns

### Single-domain search

```python
# OWNER_ONLY domain — user_uid is REQUIRED (refused without it)
result = await search_router.search(EntityType.TASK, "urgent deadline", user_uid=user_uid)

# PUBLIC domain — may be searched anonymously
result = await search_router.search(EntityType.KU, "python basics")
# result: Result[list[<domain model>]]
```

### Cross-domain search

```python
# Returns a bare UnifiedSearchResult (NOT a Result) — no .value
results = await search_router.search_domains(
    [EntityType.TASK, EntityType.PATH_STEP, EntityType.LEARNING_PATH],
    "machine learning",
    user_uid=user_uid,   # without it every OWNER_ONLY domain contributes nothing
)
for entity_type, items in results.results_by_domain.items():
    ...  # items: list[SearchResultItem]
```

### Intelligent search (cross-domain, NL query)

```python
result = await search_router.intelligent_search("health fitness", user_uid=user_uid)
# Result[UnifiedSearchResult] — .value.results_by_domain + .value.top_results
```

### Advanced search with graph filters

```python
# request.user_uid scopes every strategy (text/tags/graph) per each domain's
# SearchVisibility; without it, user-owned domains are skipped fail-closed.
request = SearchRequest(
    query_text="machine learning",
    entity_types=[EntityType.KU],
    connected_to_uid="ku.python.basics",
    connected_relationship=RelationshipName.ENABLES_KNOWLEDGE,
    tags_contain=["python"],
    user_uid=user_uid,
)
result = await search_router.advanced_search(request)   # Result[UnifiedSearchResult]
```

## SearchRouter Method Reference

| Method | Returns | Use case |
|--------|---------|----------|
| `search(entity_type, query, limit=50, user_uid=None)` | `Result[list[model]]` | Single-domain text search (OWNER_ONLY requires `user_uid`) |
| `search_domains(entity_types, query, limit_per_domain=20, user_uid=None)` | `UnifiedSearchResult` (bare) | Multi-domain aggregation |
| `intelligent_search(query, user_uid=None, user_context=None, limit=50)` | `Result[UnifiedSearchResult]` | NL cross-domain with semantic filter extraction |
| `advanced_search(request, user_context=None)` | `Result[UnifiedSearchResult]` | Text + graph traversal + tags; `request.user_uid` scopes all strategies |
| `faceted_search(request, user_uid=None, *, log_event=True, entry_point="faceted")` | `Result[SearchResponse]` | THE entry point for UI-driven search |
| `retrieve_scoped_chunks(request, *, chunk_types=None, min_score=None, user_uid=None)` | `Result[list[SemanticSearchChunkResult]]` | Facet- AND audience-scoped `:ContentChunk` retrieval (FULL tier): published curriculum + the user's own UserEntry notes; `user_uid=None` reads curriculum only (ADR-085 G8) |
| `list_tags(scope, user_uid)`, `tag_frequencies(…)`, `list_nous_subtopics(scope)`, `nous_subtopic_map(scope)` | `Result[…]` | Facet vocabularies — see § Measuring a Facet Vocabulary |

**Search-event logging:** `faceted_search`, `intelligent_search` and `advanced_search` publish `search.executed` → `:SearchEvent` — one event per external search (`intelligent_search`'s internal faceted fan-out passes `log_event=False`; empty queries never logged; fail-soft; tier-independent). `search()`, `search_domains()` and `retrieve_scoped_chunks()` publish nothing. See SEARCH_ARCHITECTURE § Search-Event Logging.

| Aspect | Value |
|--------|-------|
| **Visibility** | `DomainConfig.search_visibility` (table above). By-UID reads follow `read_visibility` (default: the search declaration; UserEntry `OWNER_OR_AUDIENCE` — opens for its share links' recipients, searches owner-only; ADR-088 §5) |
| **Result types** | `UnifiedSearchResult` with `results_by_domain` + `top_results` (top 10 by `combined_score` = relevance × 0.6 + priority × 0.4); `SearchResponse` for faceted |
| **Dispatch** | `EntityType` / `NonKuDomain` enum (type-safe, no string checks) |

## Priority scoring exists; nothing on a route runs it

`core/models/search/scoring.py` holds `score_task` … `score_principle` (each a weighted sum of shared `ComponentScore` helpers → `PriorityScore`). They are reached two ways, and neither has a production caller:

- `SearchRouter._score_results(items, user_context)` runs inside `intelligent_search` / `advanced_search` **only when the caller passes `user_context`** — `/api/search/intelligent` and `/api/search/unified` pass none.
- `get_prioritized(user_context, limit=10)` on the six Activity search services (PS/LP take `(user_uid, context, limit=20)`); `TasksService.get_prioritized` is the only facade delegation and has no caller. The Activity implementations read `backend.get_user_entities(user_uid)` with its default `limit=100`.

Do not describe `/search` results as priority-ranked: `faceted_search` builds no `UserContext` and runs no ranking pass, and on the two routes that return `SearchResultItem`s the `priority_score` stays at its 0.0 default.

**Config-driven temporal queries** (live): `TimeQueryMixin.get_upcoming()` / `get_overdue()` / `get_active()` read `DomainConfig.date_field`, `temporal_exclude_statuses` (default: the `EntityStatus.is_terminal()` values), `temporal_secondary_sort`, `completed_statuses`. Habits and Principles override all three (frequency windows / review threshold); the other four Activity domains use the base.

## Search Index Foundation (Bootstrap)

At startup `services_bootstrap/compose.py` calls `Neo4jSchemaManager`:

| Index type | Method | Tier | What it powers |
|-----------|--------|------|---------------|
| **Full-text** | `sync_fulltext_indexes()` | Always | Lucene — one index per label in `FULLTEXT_INDEX_DEFINITIONS` (`neo4j_schema_manager.py`), named by `NeoLabel.fulltext_index_name()` |
| **Vector** | `sync_vector_indexes(entity_labels=list(EmbeddingGeometry.INDEX_LABELS), …)` | FULL only | `{label.lower()}_embedding_idx`, `EmbeddingGeometry.DIMENSION` dims, cosine — **every** label in `INDEX_LABELS` (`core/constants.py`) is created at boot; `scripts/create_vector_indexes.py` reads the same constant |

Who reads the fulltext indexes is narrower than "always created" suggests:

- **The hybrid rung** is the one production reader — Ku/PathStep/LearningPath, FULL tier, `hybrid_search_with_metrics` (Lucene RRF-merged with vector similarity). It sits in `_execute_advanced_search`, so it serves **`advanced_search()` / `POST /api/search/unified`** only; the `/search` page runs `faceted_search` and is on `CONTAINS`. See SEARCH_ARCHITECTURE § Hybrid Fulltext + Vector Rung.
- **Every other text search is `CONTAINS`**, and it is **case-INSENSITIVE** (`faceted_search_raw` and `build_text_search_query` both `toLower` each side). Fulltext buys relevance ranking and vector recall, not case-insensitivity; it does not stem (`standard-no-stop-words`) and, being token-based, loses substring hits (`photosyn` misses "Photosynthesis"). The rung therefore short-circuits `CONTAINS` only on a full page and otherwise merges via `_backfill_with_contains`. Copy that shape on any new fulltext path.
- Case-SENSITIVE `CONTAINS` survives in the `find_by(field__contains=)` filter operator (`crud_queries.py`) — a field filter, not a search surface.
- Making domain-level search fulltext-first is the **D1(b)** follow-on in `docs/roadmap/deferred-work.md`.

Derive index names from `NeoLabel.fulltext_index_name()` (`PathStep` → `path_step_fulltext_idx`), never flat `label.lower()`. Vector indexes exist only at `INTELLIGENCE_TIER=full`; the semantic layers fail soft to keyword results without them.

## The AI tier and search (FULL tier)

Curriculum similarity is `rank_similar_curriculum` (`core/services/curriculum_similarity.py`) → `Neo4jVectorSearchService.find_similar_by_vector` / `find_similar_by_text` → `VectorSearchBackend.query_vector_index`, which composes `build_publication_clause` (drafts withheld). `PsAIService.search_by_semantic_query(query_text, limit=20, min_score=0.5)` = `find_similar_by_text` + `get_many`, with **no keyword fallback**. Index scores are `(1 + cos) / 2` on `[0, 1]` — the same scale `normalized_cosine_similarity` uses for stored vectors. The AI routes (`/api/*/ai/*`) are POST-only, CSRF-protected and resolved at boot; their residuals live in `docs/roadmap/ai-tier-consumer.md`.

## Common Gotchas

1. **Always use SearchRouter** for external access — never call domain services directly from routes.
2. **Curriculum content is shared** — `create_curriculum_domain_config()` sets `user_ownership_relationship=None`, which derives `SearchVisibility.PUBLIC`.
3. **MOC is not a searchable domain** — emergent identity via `ORGANIZES` edges.
4. **Every OWNER_ONLY search requires `user_uid`** — refused unscoped; UserEntry is additionally excluded from cross-domain sweeps.
5. **Every strategy is visibility-scoped** — `build_search_visibility_clause()` is THE single Cypher composition point; never add a per-strategy ownership filter. Every clause-composing builder passes `has_user=True` unconditionally (a null uid yields a null predicate matching nothing — fail-closed). See SEARCH_ARCHITECTURE § Ownership Scoping.
6. **A facet's VOCABULARY is scoped by the same declaration through a different builder** — `tag_frequencies` returns distinct strings via `build_distinct_values_query`, and the router applies each domain's `SearchVisibility` itself: PUBLIC counted corpus-wide, OWNER_ONLY counted for the caller alone and **skipped without a `user_uid`**, SCOPE_AWARE skipped. Same declaration, closed failure direction, not a second mechanism.
7. **`search_domains` returns a bare `UnifiedSearchResult`**; `search`, `intelligent_search`, `advanced_search`, `faceted_search` return `Result`.

## Measuring a Facet Vocabulary

⚠️ **Measure a facet by DRIVING the method that builds it — never with hand-written Cypher.** A facet's options are not a raw node scan: `build_distinct_values_query` composes `build_publication_clause`, so a draft PathStep's tags are never offered. A raw query omits every predicate the production path composes, and the error is **silent** because the raw number looks plausible — and agreement with a raw query on one row is not evidence for the next.

**How:** compose services in a scratch script and call the real method with the same scope the surface passes. ⚠️ The local MCP Cypher tool points at the **stopped** Docker sandbox, not AuraDB.

```python
os.environ["INTELLIGENCE_TIER"] = "core"          # pure analytics, no API keys
adapter = Neo4jAdapter(); await adapter.connect()
composed = await compose_services(adapter, InMemoryEventBus())
tags = await composed.value.search_router.list_tags(SEARCH_PAGE_ENTITY_TYPES, user_uid)
```

A per-vocabulary count is not a per-facet count (a sub-topic *word* may appear on some Ku while a *pairing* is PathStep-only) — count the thing the control offers, and treat any published figure as a dated snapshot: re-measure, never re-quote.

## UserContext and Search

SearchRouter and the BaseService search services are independent of `UserContext`: `faceted_search` builds none and consumes no MEGA-QUERY output. Search gets its per-user awareness inside the Cypher (`$user_uid` in the ownership predicate, the relationship-filter fragments, `_graph_context` enrichment). The one `UserContext` touch is `_peek_capacity_warnings` → `UserService.peek_cached_context` (cache-hit-only, never builds).

```python
context = await builder.build(user_uid)          # the user's current state (UserContextBuilder)
results = await search_router.search(EntityType.TASK, query, user_uid=user_uid)  # independent
```

**See:** `@user-context-intelligence` for the MEGA-QUERY.

## Related Skills

- **[neo4j-cypher-patterns](../neo4j-cypher-patterns/SKILL.md)** — Cypher the search backends compose
- **[python](../python/SKILL.md)** — BaseService pattern
- **[user-context-intelligence](../user-context-intelligence/SKILL.md)** — enriching results with user state

## See Also

- `/docs/architecture/SEARCH_ARCHITECTURE.md` — complete architecture reference (§ One Search, End to End)
- `/docs/decisions/ADR-023-curriculum-baseservice-migration.md` — unified BaseService decision
- `/docs/decisions/ADR-085-ownership-read-enforcement-contract.md`, `/docs/decisions/ADR-088-submit-and-share.md`
- `/docs/patterns/search_service_pattern.md`, `/docs/reference/SEARCH_SERVICE_METHODS.md`
- `/docs/patterns/query_architecture.md` — the query builders (NOT the search path)
