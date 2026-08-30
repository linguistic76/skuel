# SKUEL Search Architecture - Quick Reference

> **Fast lookup** for SearchRouter methods and search wiring

---

## SearchRouter Methods (`core/orchestrator/search_router.py`)

```python
# Single domain — type-safe dispatch by EntityType
result = await search_router.search(EntityType.TASK, "urgent deadline", limit=20)

# Multi-domain aggregation
results = await search_router.search_domains(
    [EntityType.TASK, EntityType.GOAL, EntityType.KU], "machine learning"
)

# Natural-language cross-domain (semantic filter extraction)
result = await search_router.intelligent_search("urgent overdue tasks", user_uid=user_uid)

# Filters + graph patterns + tags
result = await search_router.advanced_search(SearchRequest(...))

# THE UI entry point (/search) — strategy selection + visibility scoping
result = await search_router.faceted_search(search_request, user_uid)

# Scoped ContentChunk retrieval (RAG, FULL tier) — user_uid is the AUDIENCE:
# published curriculum passages + this user's own notes, never another user's
result = await search_router.retrieve_scoped_chunks(search_request, user_uid=user_uid)
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

Single Cypher composition point: `build_search_visibility_clause()`.

---

## SearchRequest Strategy Selection (`get_search_strategy()`)

| Strategy | Trigger |
|----------|---------|
| `semantic` | `enable_semantic_boost=True` |
| `learning` | `enable_learning_aware=True` |
| `graph` | `connected_to_uid` set |
| `tags` | `tags_contain` set |
| `faceted` | boolean graph-pattern flags set |
| `text` | default |

Build from HTML forms with `SearchRequest.from_form_params(...)` (handles empty-string→None, checkbox→bool, string→enum coercion).

---

## Common Pitfalls

| Problem | Solution |
|---------|----------|
| Calling `domain_service.search.search()` from a route | Always go through SearchRouter |
| `unified_search()` | Doesn't exist — `search_domains()` / `intelligent_search()` |
| Any OWNER_ONLY search without `user_uid` | Refused by `SearchRouter.search()` (the clause emits no ownership predicate without a user). UserEntry additionally excluded from cross-domain sweeps |
| Per-strategy ownership filter | Never — visibility scoping is centralized in `build_search_visibility_clause()` |
| `_user_ownership_relationship` ClassVar | Removed — use DomainConfig `user_ownership_relationship` |
| Graph-pattern filters without `user_uid` | `ready_to_learn`, `supports_goals`, etc. need the user's mastery/ownership |
| Empty query on /search/results | Route short-circuits — no backend call |

---

## Index Foundation

| Index | Tier | Coverage |
|-------|------|----------|
| Full-text (Lucene) | Always | 14 domains (`sync_fulltext_indexes()`) — read by the hybrid rung (Ku/PS/LP, FULL tier, `advanced_search`/`/api/search/unified` only); `/search` and every other text path is `CONTAINS` |
| Vector (1024-dim cosine) | FULL only | Entity, ContentChunk, ReferenceChunk, Ku, PathStep, LearningPath (bootstrap) + Goal, Task (script) |

---

**See Also**: [SKILL.md](SKILL.md) for architecture and method reference
**See Also**: [PATTERNS.md](PATTERNS.md) for faceted/graph-aware/tag search patterns
