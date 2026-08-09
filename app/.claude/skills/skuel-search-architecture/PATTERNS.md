# SKUEL Search Architecture - Common Patterns

> **Real implementation patterns used in SKUEL's search layer**

---

## Pattern 1: Simple Text Search via SearchRouter

**Problem**: Search a single domain by keyword from a route.

**Context**: Most common search — user types a query, route delegates to SearchRouter.

**Solution**:
```python
# In a route handler
from core.models.search.search_router import SearchRouter
from core.models.enums.entity_enums import EntityType

result = await search_router.search(EntityType.TASK, "urgent deadline", limit=20)
if result.is_error:
    return error_response(result)

tasks = result.value  # list[Task]
```

**Cross-domain**:
```python
# Search across multiple domains simultaneously
results = await search_router.search_domains(
    [EntityType.TASK, EntityType.GOAL, EntityType.KU],
    "machine learning",
    limit=50,
)
# results: UnifiedSearchResult with results_by_domain dict + top_results list
for entity_type, items in results.value.results_by_domain.items():
    ...  # items: list[SearchResultItem]

# Or open-ended NL cross-domain discovery
all_results = await search_router.intelligent_search("health fitness", user_uid=user_uid)
top_10 = all_results.value.top_results  # Combined score: relevance 60% + priority 40%
```

**Trade-offs**:
- Use `search()` when you know the domain upfront
- Use `search_domains()` for curated multi-domain results
- Use `intelligent_search()` for open-ended cross-domain discovery (there is no `unified_search()` method)

**Real-world usage**: `search_routes.py` GET `/search/results`

---

## Pattern 2: Faceted Search with SearchRequest

**Problem**: Search with filters (status, priority, domain, learning level) plus graph patterns.

**Context**: The search page with a horizontal filter bar (off-canvas drawer on mobile). User combines text query with enum-typed facets.

**Solution**:
```python
from core.models.search_request import SearchRequest

# Build from HTML form parameters — from_form_params() handles all coercion:
# empty string → None, checkbox "true" → bool, string → enum, extended_facets assembly
search_request = SearchRequest.from_form_params(
    query=query,
    user_uid=user_uid,
    entity_type=entity_type,       # raw string, parsed to EntityType enum
    status=status,                 # raw string, parsed to EntityStatus enum
    priority=priority,             # raw string, parsed to Priority enum
    ready_to_learn=ready_to_learn, # checkbox "true"/"" → bool
    supports_goals=supports_goals,
    limit=20,
    offset=0,
)

result = await search_router.faceted_search(search_request, user_uid)

# For programmatic/API use, construct directly with typed values:
search_request = SearchRequest(
    query_text=query,
    entity_types=[EntityType.KU],
    status=EntityStatus.ACTIVE,
    user_uid=user_uid,
    limit=20,
)
```

**SearchRequest strategy selection** (`get_search_strategy()`):
| Strategy | Triggered by | Path |
|----------|-------------|------|
| `semantic` | `enable_semantic_boost=True` | Vector/embedding search |
| `learning` | `enable_learning_aware=True` | Personalized by mastery state |
| `graph` | `connected_to_uid` set | Relationship traversal |
| `tags` | `tags_contain` set | Array/tag search |
| `faceted` | Boolean graph patterns set | Cypher EXISTS patterns |
| `text` | Default | Text search on configured fields |

**Trade-offs**:
- Facets are first-class `SearchRequest` fields (not buried in dicts) — type-safe
- `to_property_filters()` converts enum values to strings for Cypher
- `to_relationship_filters()` captures the active relationship flags as a frozen `RelationshipFilters` intent — the EXISTS subqueries are authored **below the boundary** (ADR-044), not in the request model (SKUEL021)

**Real-world usage**: `search_routes.py` → `SearchRouter.faceted_search()`

---

## Pattern 3: Graph-Aware Search (8 Relationship Patterns)

**Problem**: Filter search results by relationship conditions — "only show knowledge I'm ready to learn", "tasks connected to my active goals".

**Context**: The "Smart Filters" section on the search page. All 8 patterns run as Cypher EXISTS subqueries.

**Solution**:
```python
# Ready to learn — all prerequisites mastered
request = SearchRequest(
    query_text="self-awareness",
    ready_to_learn=True,
    user_uid=user_uid,
)

# Builds on what the user already knows
request = SearchRequest(
    query_text="meditation",
    builds_on_mastered=True,
    user_uid=user_uid,
)

# Multiple graph patterns combined (AND semantics)
request = SearchRequest(
    query_text="habits",
    ready_to_learn=True,
    supports_goals=True,
    user_uid=user_uid,
)
```

**All 8 graph patterns** (in `SearchRequest`; authoritative Cypher in `relationship_filter_fragments.py` — every edge is a registered `RelationshipName` with a real write path, guarded by `tests/unit/adapters/test_relationship_filter_vocabulary.py`):
| Field | Cypher Pattern (EXISTS fragment) | Meaning |
|-------|---------------|---------|
| `ready_to_learn` | NOT EXISTS an unmastered REQUIRES_KNOWLEDGE prereq | No blocked prerequisites |
| `builds_on_mastered` | user MASTERED neighbor —ENABLES_KNOWLEDGE\|RELATED_TO— this | Extends existing knowledge |
| `in_active_path` | user ENROLLED_IN (not completed) lp HAS_STEP ps USES_KU\|TRAINS_KU\|CONTAINS_KNOWLEDGE this | Part of followed learning path |
| `supports_goals` | user OWNS active goal REQUIRES_KNOWLEDGE this | Linked to active goals |
| `builds_on_habits` | user OWNS active habit REINFORCES_KNOWLEDGE this | Reinforces active habits |
| `applied_in_tasks` | user OWNS task APPLIES_KNOWLEDGE this (30-day window; `datetime()` coerces string `updated_at`) | Used in recent tasks |
| `aligned_with_principles` | user OWNS active principle GROUNDED_IN_KNOWLEDGE this | Aligns with principles |
| `next_logical_step` | MASTERED —ENABLES_KNOWLEDGE→ this, prereqs met, not yet mastered | Natural progression |

**Pedagogical patterns** (content state):
| Field | Meaning |
|-------|---------|
| `not_yet_viewed` | User hasn't VIEWED this content |
| `viewed_not_mastered` | User has VIEWED but not MASTERED |
| `ready_to_review` | MASTERED but due for review |

**Real-world usage**: `search_routes.py` checkboxes → `SearchRequest` bool fields → `to_relationship_filters()` → (below the boundary) `build_relationship_filter_fragments()` → Cypher EXISTS subqueries in `faceted_search_raw`

---

## Pattern 4: Relationship Traversal Search

**Problem**: Find entities connected to a specific entity via a graph relationship.

**Context**: "Show me all KUs that ENABLE this one", "find tasks that DEPENDS_ON this task".

**Solution**:
```python
from core.models.relationship_names import RelationshipName

# Advanced search with graph traversal
request = SearchRequest(
    query_text="",  # Optional — can traverse without text filter
    entity_types=[EntityType.KU],
    connected_to_uid="ku_python-basics_abc123",
    connected_relationship=RelationshipName.ENABLES_KNOWLEDGE,
    connected_direction="outgoing",  # "incoming", "outgoing", "both"
    limit=20,
)
result = await search_router.advanced_search(request)

# From /api/search/unified route:
# GET /api/search/unified?query=python&connected_to=ku_abc&relationship=ENABLES_KNOWLEDGE&direction=outgoing
```

**Trade-offs**:
- `connected_direction="both"` matches in either direction — use when relationship is symmetric
- Combine with `query_text` to further filter traversal results
- RelationshipName enum provides type-safe traversal (IDE autocomplete, MyPy verification)

**Real-world usage**: `search_routes.py` `/api/search/unified` endpoint

---

## Pattern 5: Tag / Array Search

**Problem**: Find entities by tags with AND or OR semantics.

**Context**: Tag-based filtering on the search page.

**Solution**:
```python
# OR semantics — any of these tags (default)
request = SearchRequest(
    query_text="",
    tags_contain=["python", "ml", "data"],
    tags_match_all=False,  # OR — match any tag
    limit=50,
)

# AND semantics — must have all tags
request = SearchRequest(
    query_text="habits",
    tags_contain=["mindfulness", "morning"],
    tags_match_all=True,  # AND — must have all tags
)

result = await search_router.advanced_search(request)
```

**Cypher pattern** (from `SupportsTagSearch.search_by_tags()`):
```cypher
// OR semantics
MATCH (e:Entity)
WHERE ANY(tag IN e.tags WHERE tag IN $tags)
RETURN e

// AND semantics
MATCH (e:Entity)
WHERE ALL(tag IN $tags WHERE tag IN e.tags)
RETURN e
```

**Trade-offs**:
- Tags are stored as arrays on Entity nodes — no separate tag nodes
- AND semantics (`tags_match_all=True`) can return very few results with long tag lists
- Combine with `query_text` for text + tag filtering

**Real-world usage**: `search_routes.py` `/api/search/unified` with `tags` and `tags_match_all` params

---

## Pattern 6: DomainConfig — Configuring a Search Service

**Problem**: New domain service needs search capability. How to wire it.

**Context**: Every Activity and Curriculum domain has a search service extending `BaseService`.

**Solution**:
```python
# Activity domain (user-owned content)
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config

class TasksSearchService(BaseService["TasksOperations", Task]):
    _config = create_activity_domain_config(
        dto_class=TaskDTO,
        model_class=Task,
        domain_name="tasks",
        date_field="due_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
    )
    # Inherits: search(), get_by_status(), get_by_category(), verify_ownership()

# Curriculum domain (shared content — no user ownership filter)
from core.services.domain_config import create_curriculum_domain_config

class PsSearchService(BaseService[PsOperations, PathStep]):
    _config = create_curriculum_domain_config(
        dto_class=PathStepDTO,
        model_class=PathStep,
        domain_name="path_step",
        search_fields=("title", "intent", "description"),
        search_order_by="updated_at",
    )
    # user_ownership_relationship=None (DomainConfig) → SearchVisibility.PUBLIC, no OWNS filter
```

**Key config fields**:
| Field | Default | Purpose |
|-------|---------|---------|
| `dto_class` | Required | DTO for Neo4j → Python conversion |
| `model_class` | Required | Domain model (frozen dataclass) |
| `domain_name` | Required | Used in logging/routing |
| `search_fields` | `("title", "description")` | Fields for text search |
| `search_order_by` | `"created_at"` | Default sort field |
| `user_ownership_relationship` | `"OWNS"` | None for shared curriculum content |
| `completed_statuses` | `()` | For activity completion tracking |

**Trade-offs**:
- `create_activity_domain_config()` adds OWNS filter automatically
- `create_curriculum_domain_config()` sets ownership to None (shared content)
- Direct class-attribute style (`_dto_class = ...`) was removed January 2026 — always use DomainConfig

**Real-world usage**: All 12 searchable domain services

---

## Pattern 7: Intelligent Search with Query Parsing

**Problem**: Natural language query that contains implicit filters ("urgent tasks in progress", "python habits").

**Solution**: Route through `SearchRouter.intelligent_search()` — the single cross-domain NL entry point.

```python
# Cross-domain NL search via SearchRouter (live)
result = await search_router.intelligent_search(query="urgent overdue tasks", limit=20)
```

**Real-world usage**: `GET /api/search/intelligent` → `SearchRouter.intelligent_search()`

Per-domain `intelligent_search()` methods were deleted in Theme F (June 2026) — they were parallel dead code with no callers; `SearchRouter` owns this surface.

---

## Pattern Comparison

| Pattern | Use Case | Complexity | SearchRouter Method |
|---------|----------|------------|---------------------|
| Text Search | Simple keyword lookup | Low | `search()` |
| Cross-Domain | Compare across domains | Low | `search_domains()` |
| Faceted Search | Status/priority filters | Medium | `faceted_search()` |
| Graph-Aware | Relationship condition filters | High | `faceted_search()` |
| Traversal | Find connected entities | Medium | `advanced_search()` |
| Tag Search | Array/tag filtering | Low | `advanced_search()` |
| Intelligent | Natural language query | Medium | `SearchRouter.intelligent_search()` → `GET /api/search/intelligent` (cross-domain only) |

---

## Common Gotchas

1. **Always use SearchRouter** — never call `domain_service.search.search()` directly from routes
2. **MOC is not searchable** — it's emergent identity on Ku nodes, not a separate domain
3. **Curriculum search has no user filter** — DomainConfig `user_ownership_relationship=None` → `SearchVisibility.PUBLIC`, results are shared for all users
4. **`faceted_search()` vs `advanced_search()`** — both take `SearchRequest`; `faceted_search()` also takes `user_uid` and selects a strategy; `advanced_search()` is for cross-domain with traversal
5. **Graph pattern filters require `user_uid`** — `ready_to_learn`, `supports_goals`, etc. need the user to check their mastery/ownership

**See Also**: [SKILL.md](SKILL.md) for SearchRouter API reference and architecture overview.
