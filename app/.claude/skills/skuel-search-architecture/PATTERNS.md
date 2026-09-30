# SKUEL Search Architecture - Common Patterns

> **Real implementation patterns used in SKUEL's search layer**

---

## Pattern 1: Simple Text Search via SearchRouter

**Problem**: Search a single domain by keyword from a route.

**Solution**:
```python
from core.orchestrator.search_router import SearchRouter
from core.models.enums.entity_enums import EntityType

# OWNER_ONLY domain: user_uid is REQUIRED — the router refuses an unscoped call
result = await search_router.search(EntityType.TASK, "urgent deadline", limit=20, user_uid=user_uid)
if result.is_error:
    return error_response(result)

tasks = result.value  # list[Task]
```

**Cross-domain**:
```python
# search_domains returns a bare UnifiedSearchResult — not a Result, no .value
results = await search_router.search_domains(
    [EntityType.TASK, EntityType.GOAL, EntityType.KU],
    "machine learning",
    limit_per_domain=20,
    user_uid=user_uid,      # every OWNER_ONLY domain is refused (contributes nothing) without it
)
for entity_type, items in results.results_by_domain.items():
    ...  # items: list[SearchResultItem]

# Open-ended NL cross-domain discovery — Result[UnifiedSearchResult]
all_results = await search_router.intelligent_search("health fitness", user_uid=user_uid)
top_10 = all_results.value.top_results  # sorted by combined_score = relevance × 0.6 + priority × 0.4
```

`priority_score` is 0.0 unless the caller passes `user_context` (no route does — SKILL.md § Priority scoring), so `top_results` is a relevance order in practice.

**Trade-offs**:
- Use `search()` when you know the domain upfront
- Use `search_domains()` for curated multi-domain results
- Use `intelligent_search()` for open-ended cross-domain discovery (there is no `unified_search()` method)

**Real-world usage**: `search_routes.py` `/api/search/intelligent` → `intelligent_search()`; `/search/results` → `faceted_search()` (Pattern 2)

---

## Pattern 2: Faceted Search with SearchRequest

**Problem**: Search with filters (status, priority, type, nous, learning level) plus graph patterns.

**Context**: The `/search` page — a filter bar (off-canvas drawer on mobile); every control carries `hx-get="/search/results"` and re-fires with all current filters.

**Solution**:
```python
from core.models.search_request import SearchRequest

# Build from HTML form parameters — from_form_params() owns every coercion AND
# the renames: query → query_text, entity_type (one string) → entity_types (a
# one-element list), tags (CSV) → tags_contain, frequency/event_type/urgency/
# strength → extended_facets. Add a filter by extending it, never by adding a
# SearchRequest field named after the control.
search_request = SearchRequest.from_form_params(
    query=query,
    user_uid=user_uid,
    entity_type=entity_type,       # raw string, parsed to EntityType
    status=status,                 # raw string, parsed to EntityStatus
    priority=priority,             # raw string, parsed to Priority
    ready_to_learn=ready_to_learn, # checkbox "true"/"" → bool
    supports_goals=supports_goals,
    limit=20,
    offset=0,
)

result = await search_router.faceted_search(search_request, user_uid)   # Result[SearchResponse]

# For programmatic use, construct directly with typed values:
search_request = SearchRequest(
    query_text=query,
    entity_types=[EntityType.KU],
    status=EntityStatus.ACTIVE,
    user_uid=user_uid,
    limit=20,
)
```

**Strategy selection** (`SearchRequest.get_search_strategy()`, checked in this order):
| Strategy | Triggered by |
|----------|-------------|
| `semantic` | `has_semantic_boost()` — `enable_semantic_boost` AND `context_uids` |
| `learning` | `has_learning_aware()` |
| `graph` | `connected_to_uid` set |
| `tags` | `tags_contain` set |
| `faceted` | any boolean relationship flag set |
| `text` | default |

**Trade-offs**:
- Facets are first-class `SearchRequest` fields (not buried in dicts) — type-safe
- `to_property_filters()` converts enum values to strings for Cypher
- `to_relationship_filters()` captures the active relationship flags as a frozen `RelationshipFilters` intent — the EXISTS subqueries are authored **below the boundary** (ADR-044), not in the request model (SKUEL021)
- `/search/results` answers a prompt, not a query, when `has_any_criteria()` is false — a filter-only search (no text) is valid end to end

**Real-world usage**: `search_routes.py` → `SearchRouter.faceted_search()`; `explore_ui.py` (own `entity_types`)

---

## Pattern 3: Graph-Aware Search (8 Relationship Patterns)

**Problem**: Filter search results by relationship conditions — "only show knowledge I'm ready to learn", "tasks connected to my active goals".

**Context**: The relationship checkboxes on `/search`. Each runs as a Cypher EXISTS fragment inside `faceted_search_raw`.

**Solution**:
```python
# Ready to learn — all prerequisites mastered
request = SearchRequest(query_text="self-awareness", ready_to_learn=True, user_uid=user_uid)

# Multiple graph patterns combined (AND semantics)
request = SearchRequest(
    query_text="habits",
    ready_to_learn=True,
    supports_goals=True,
    user_uid=user_uid,
)
```

**The 8 graph patterns** (`SearchRequest` bool fields; authoritative Cypher in `adapters/persistence/neo4j/query/cypher/relationship_filter_fragments.py` — every edge is a registered `RelationshipName` with a real write path, guarded by `tests/unit/adapters/test_relationship_filter_vocabulary.py`):
| Field | Meaning |
|-------|---------|
| `ready_to_learn` | no unmastered `REQUIRES_KNOWLEDGE` prerequisite |
| `builds_on_mastered` | a mastered neighbour reaches this via `ENABLES_KNOWLEDGE` / `RELATED_TO` |
| `in_active_path` | in a path the user is `ENROLLED_IN` (not completed) |
| `supports_goals` | required by one of the user's active goals |
| `builds_on_habits` | reinforced by one of the user's active habits |
| `applied_in_tasks` | applied by a recent task (30-day window) |
| `aligned_with_principles` | grounds one of the user's active principles |
| `next_logical_step` | enabled by mastered knowledge, prerequisites met, not yet mastered |

**Pedagogical patterns** (content state): `not_yet_viewed`, `viewed_not_mastered`, `ready_to_review`.

Read the fragment file for the exact pattern; the table names the intent only.

**Real-world usage**: `search_routes.py` checkboxes → `SearchRequest` bool fields → `to_relationship_filters()` → (below the boundary) `build_relationship_filter_fragments()` → EXISTS subqueries in `faceted_search_raw`

---

## Pattern 4: Relationship Traversal Search

**Problem**: Find entities connected to a specific entity via a graph relationship.

**Solution**:
```python
from core.models.relationship_names import RelationshipName

request = SearchRequest(
    query_text="",  # optional — can traverse without a text filter
    entity_types=[EntityType.KU],
    connected_to_uid="ku.python.basics",
    connected_relationship=RelationshipName.ENABLES_KNOWLEDGE,
    connected_direction="outgoing",  # "incoming", "outgoing", "both"
    limit=20,
    user_uid=user_uid,
)
result = await search_router.advanced_search(request)
```

The JSON door is **`POST /api/search/unified`** (CSRF-protected; `@csrf_protected` — a `TestClient` needs the cookie + `X-CSRF-Token` pair): form/query params `query`, `entity_types` (CSV), `relationship`, `connected_to`, `direction`, `tags` (CSV), `tags_match_all`, `limit`. The handler builds the `SearchRequest` with the authenticated uid; `advanced_search` derives its per-domain budget from `request.limit` and the eligible domains (the handler's `limit_per_domain` parameter is accepted and never read — an inert knob, not a control).

**Trade-offs**:
- `connected_direction="both"` matches either direction — use when the relationship is symmetric
- Combine with `query_text` to further filter traversal results
- `build_relationship_traversal_query` composes `build_search_visibility_clause` like every other strategy (ADR-085 G3)

---

## Pattern 5: Tag / Array Search

**Problem**: Find entities by tags with AND or OR semantics.

**Solution**:
```python
# OR semantics — any of these tags (default)
request = SearchRequest(query_text="", tags_contain=["python", "ml", "data"], tags_match_all=False, user_uid=user_uid)

# AND semantics — must have all tags
request = SearchRequest(query_text="habits", tags_contain=["mindfulness", "morning"], tags_match_all=True, user_uid=user_uid)

result = await search_router.advanced_search(request)
```

**Cypher shape** (`build_array_any_match_query`, `crud_queries.py` — behind `SearchOperationsMixin.search_by_tags` → `backend.array_any_match_raw`). The two semantics match **differently**:
```cypher
// OR: any value, case-insensitive SUBSTRING match on each stored tag
WHERE ANY(v IN $values WHERE ANY(item IN n.tags WHERE toLower(item) CONTAINS toLower(v)))

// AND: every value, case-insensitive EQUALITY on some stored tag
WHERE ALL(v IN $values WHERE ANY(item IN n.tags WHERE toLower(item) = toLower(v)))
```
plus the visibility clause; the builder never accepts a field name outside the model's fields.

**Trade-offs**:
- Tags are arrays on Entity nodes — no separate tag nodes
- OR finds `"ml"` inside `"html"`; AND does not — say which semantics a caller gets
- The tag *vocabulary* (`tag_frequencies`) is scoped per domain by the router, not by this query (SKILL.md gotcha 6)

---

## Pattern 6: DomainConfig — Configuring a Search Service

**Problem**: A new domain service needs search capability.

**Solution**:
```python
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config, create_curriculum_domain_config

# Activity domain (user-owned — OWNER_ONLY)
class TasksSearchService(BaseService["TasksOperations", Task]):
    _config = create_activity_domain_config(
        dto_class=TaskDTO,
        model_class=Task,
        domain_name="tasks",
        date_field="due_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
    )

# Curriculum domain (shared — PUBLIC, no ownership filter)
class PsSearchService(BaseService["PsOperations", PathStep]):
    _config = create_curriculum_domain_config(
        dto_class=PathStepDTO,
        model_class=PathStep,
        domain_name="ps",
        search_fields=("title", "intent", "description"),
        category_field="nous",
    )
```

**Key `DomainConfig` fields** (`core/services/domain_config.py` — read the dataclass for the rest):
| Field | Default | Purpose |
|-------|---------|---------|
| `dto_class`, `model_class`, `domain_name` | required | DTO / frozen domain model / logging + routing name |
| `search_fields` | `("title", "description")` | Fields for text search |
| `search_order_by` | `"created_at"` | Default sort field |
| `category_field` | `"category"` | `get_by_category` / `list_*_categories` |
| `date_field` | `"created_at"` | Temporal queries |
| `user_ownership_relationship` | `RelationshipName.OWNS` | `None` for shared curriculum — derives `PUBLIC` |
| `search_visibility` / `read_visibility` | `None` → derived | Explicit for `SCOPE_AWARE` (Exercise) / `OWNER_OR_AUDIENCE` (UserEntry read) |
| `ownership_property` | `"user_uid"` | The property the OWNER_ONLY clause filters on (Group declares `owner_uid`) |
| `completed_statuses` | `()` | Excluded from `get_active` |

**Trade-offs**:
- `create_activity_domain_config()` keeps the OWNS ownership → `OWNER_ONLY`
- `create_curriculum_domain_config()` sets ownership to `None` → `PUBLIC`
- An `OWNER_ONLY` domain must declare the property it actually writes — a declaration pointing at a field the domain does not store is a null predicate and its search silently returns nothing (`TestOwnerOnlyDomainsCarryTheScopingProperty`)

**Real-world usage**: all 12 searchable domain services

---

## Pattern 7: Intelligent Search with Query Parsing

**Problem**: A natural-language query with implicit filters ("urgent tasks in progress").

**Solution**: `SearchRouter.intelligent_search()` — the single cross-domain NL entry point. `SearchQueryParser` (`core/models/search/query_parser.py`) extracts priority/status/domain signals; each target domain then runs through `faceted_search` so ownership applies in the query.

```python
result = await search_router.intelligent_search("urgent overdue tasks", user_uid=user_uid, limit=20)
```

**Real-world usage**: `GET /api/search/intelligent?q=…` → `SearchRouter.intelligent_search()`. There are no per-domain `intelligent_search()` methods.

---

## Pattern Comparison

| Pattern | Use Case | SearchRouter Method | Returns |
|---------|----------|---------------------|---------|
| Text Search | Simple keyword lookup | `search()` | `Result[list[model]]` |
| Cross-Domain | Compare across domains | `search_domains()` | `UnifiedSearchResult` (bare) |
| Faceted Search | Status/priority/type/nous filters | `faceted_search()` | `Result[SearchResponse]` |
| Graph-Aware | Relationship-condition filters | `faceted_search()` | `Result[SearchResponse]` |
| Traversal | Find connected entities | `advanced_search()` | `Result[UnifiedSearchResult]` |
| Tag Search | Array/tag filtering | `advanced_search()` | `Result[UnifiedSearchResult]` |
| Intelligent | Natural-language query | `intelligent_search()` | `Result[UnifiedSearchResult]` |

---

## Common Gotchas

1. **Always use SearchRouter** — never call `domain_service.search.search()` directly from a route
2. **MOC is not searchable** — emergent identity on Entity nodes, not a domain
3. **Curriculum search has no user filter** — `user_ownership_relationship=None` → `SearchVisibility.PUBLIC`; drafts are withheld by `build_publication_clause` on the vector/fulltext doors and on facet vocabularies, not by ownership
4. **`faceted_search()` vs `advanced_search()`** — both take `SearchRequest`; `faceted_search()` also takes `user_uid` and selects a strategy; `advanced_search()` is the cross-domain door with traversal and the hybrid rung
5. **Graph-pattern filters require `user_uid`** — `ready_to_learn`, `supports_goals`, … bind `(user:User {uid: $user_uid})` themselves
6. **`/api/search/unified` is POST + CSRF**, not GET

**See Also**: [SKILL.md](SKILL.md) for the SearchRouter API reference and architecture overview.
