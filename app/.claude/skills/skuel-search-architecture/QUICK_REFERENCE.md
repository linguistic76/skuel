# SKUEL Search Architecture - Quick Reference

> **Fast lookup** for SearchRouter methods and search wiring

---

## SearchRouter Methods (`core/orchestrator/search_router.py`)

```python
# Single domain — type-safe dispatch by EntityType; OWNER_ONLY domains REQUIRE user_uid
result = await search_router.search(EntityType.TASK, "urgent deadline", limit=20, user_uid=user_uid)   # Result[list[Task]]

# Multi-domain aggregation — returns a BARE UnifiedSearchResult (no .value)
results = await search_router.search_domains(
    [EntityType.TASK, EntityType.GOAL, EntityType.KU], "machine learning", user_uid=user_uid
)

# Natural-language cross-domain (semantic filter extraction) — Result[UnifiedSearchResult]
result = await search_router.intelligent_search("urgent overdue tasks", user_uid=user_uid)

# Filters + graph traversal + tags (+ the hybrid fulltext/vector rung on FULL) — Result[UnifiedSearchResult]
result = await search_router.advanced_search(SearchRequest(..., user_uid=user_uid))

# THE UI entry point (/search, /explore) — strategy selection + visibility scoping — Result[SearchResponse]
result = await search_router.faceted_search(search_request, user_uid)

# Scoped ContentChunk retrieval (RAG, FULL tier) — user_uid is the AUDIENCE:
# published curriculum passages + this user's own notes, never another user's
result = await search_router.retrieve_scoped_chunks(search_request, user_uid=user_uid)

# Facet vocabularies — drive these, never a raw Cypher count
tags = await search_router.list_tags(SEARCH_PAGE_ENTITY_TYPES, user_uid)
```

There is **no `unified_search()`** — use `search_domains()` or `intelligent_search()`.

---

## The 12 Searchable Domains

Task, Goal, Habit, Event, Choice, Principle · Ku, PathStep, LearningPath · Exercise, RevisedExercise, UserEntry

| Visibility (`DomainConfig.search_visibility`) | Domains |
|--------|---------|
| `OWNER_ONLY` | 6 Activity + UserEntry + RevisedExercise |
| `PUBLIC` | Ku, PS, LP |
| `SCOPE_AWARE` | Exercise (curriculum visible to all; owned scopes via OWNS/SHARES_WITH/group) |
| `OWNER_OR_AUDIENCE` | UserEntry — as `read_visibility` only (the by-UID read opens for the share links' recipients; search stays `OWNER_ONLY`; ADR-088 §5) |

Single Cypher composition point: `build_search_visibility_clause()` (`query/cypher/crud_queries.py`); its audience arm is `build_audience_fragment()` (ADR-088 §3). Every composing builder passes `has_user=True` unconditionally — fail-closed on a null uid.

---

## SearchRequest Strategy Selection (`get_search_strategy()`)

| Strategy | Trigger (checked in this order) |
|----------|---------|
| `semantic` | `enable_semantic_boost` AND `context_uids` |
| `learning` | `enable_learning_aware` |
| `graph` | `connected_to_uid` set |
| `tags` | `tags_contain` set |
| `faceted` | any boolean relationship flag set |
| `text` | default |

Build from HTML forms with `SearchRequest.from_form_params(...)` — it owns the coercions (empty-string→None, checkbox→bool, string→enum) AND the renames (`query`→`query_text`, `entity_type`→`entity_types` one-element list, `tags` CSV→`tags_contain`, `frequency`/`event_type`/`urgency`/`strength`→`extended_facets`).

---

## Common Pitfalls

| Problem | Solution |
|---------|----------|
| Calling `domain_service.search.search()` from a route | Always go through SearchRouter |
| `unified_search()` | Doesn't exist — `search_domains()` / `intelligent_search()` |
| `search_domains(...).value` | It returns a bare `UnifiedSearchResult` — read `.results_by_domain` directly |
| Any OWNER_ONLY search without `user_uid` | Refused by `SearchRouter.search()` (the clause emits no ownership predicate without a user); in an aggregate the domain contributes nothing. UserEntry additionally excluded from cross-domain sweeps |
| Per-strategy ownership filter | Never — visibility scoping is centralized in `build_search_visibility_clause()` |
| `backend.search(...)` | No such method — the backend has `text_search_raw` and the other `*_raw` primitives; `search()` is the service mixin's |
| Graph-pattern filters without `user_uid` | `ready_to_learn`, `supports_goals`, … bind `$user_uid` themselves |
| Expecting priority-ranked results | No route passes `user_context`, so `_score_results` never runs; `priority_score` is 0.0 |
| `GET /api/search/unified` | It is `POST` + `@csrf_protected` (cookie + `X-CSRF-Token`) |
| A `/search/results` request with no criteria at all | The route renders the empty-search prompt — no backend call; a filter-only request (no text) does run |

---

## Index Foundation

| Index | Tier | Coverage |
|-------|------|----------|
| Full-text (Lucene) | Always | one per label in `FULLTEXT_INDEX_DEFINITIONS` (`neo4j_schema_manager.sync_fulltext_indexes()`), named by `NeoLabel.fulltext_index_name()` — read by the hybrid rung (Ku/PS/LP, FULL tier, `advanced_search` / `POST /api/search/unified` only); `/search` and every other text path is case-insensitive `CONTAINS` |
| Vector (`EmbeddingGeometry.DIMENSION` dims, cosine) | FULL only | every label in `EmbeddingGeometry.INDEX_LABELS` (`core/constants.py`), `{label.lower()}_embedding_idx` — synced at boot and by `scripts/create_vector_indexes.py` from the same constant |

---

**See Also**: [SKILL.md](SKILL.md) for architecture and method reference
**See Also**: [PATTERNS.md](PATTERNS.md) for faceted/graph-aware/tag search patterns
