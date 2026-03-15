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

# Or search everything
all_results = await search_router.unified_search("health fitness")
top_10 = all_results.value.top_results  # Combined score: relevance 60% + priority 40%
```

**Trade-offs**:
- Use `search()` when you know the domain upfront
- Use `search_domains()` for curated multi-domain results
- Use `unified_search()` for open-ended cross-domain discovery

**Real-world usage**: `search_routes.py` GET `/search/results`

---

## Pattern 2: Faceted Search with SearchRequest

**Problem**: Search with filters (status, priority, domain, learning level) plus graph patterns.

**Context**: The search page with sidebar filters. User combines text query with enum-typed facets.

**Solution**:
```python
from core.models.search_request import SearchRequest
from core.models.enums import EntityStatus, Priority

# Build from route query parameters
search_request = SearchRequest(
    query_text=query,
    entity_types=[EntityType.KU] if entity_type else [],
    status=EntityStatus(status) if status else None,
    priority=Priority(priority) if priority else None,
    learning_level=LearningLevel(learning_level) if learning_level else None,
    sel_category=SELCategory(sel_category) if sel_category else None,
    user_uid=user_uid,
    limit=20,
    offset=0,
)

result = await search_router.faceted_search(search_request, user_uid)
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
- `to_graph_patterns()` generates EXISTS subqueries for graph pattern filters

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

**All 8 graph patterns** (in `SearchRequest`):
| Field | Cypher Pattern | Meaning |
|-------|---------------|---------|
| `ready_to_learn` | All REQUIRES_KNOWLEDGE targets are MASTERED | No blocked prerequisites |
| `builds_on_mastered` | EXISTS MASTERED neighbor ENABLES_LEARNING this | Extends existing knowledge |
| `in_active_path` | EXISTS user FOLLOWING lp CONTAINS this | Part of followed learning path |
| `supports_goals` | EXISTS user OWNS goal REQUIRES_KNOWLEDGE this | Linked to active goals |
| `builds_on_habits` | EXISTS user OWNS habit REINFORCES_KNOWLEDGE this | Reinforces active habits |
| `applied_in_tasks` | EXISTS user OWNS task APPLIES_KNOWLEDGE this | Used in recent tasks |
| `aligned_with_principles` | EXISTS user OWNS principle GROUNDED_IN_KNOWLEDGE this | Aligns with principles |
| `next_logical_step` | Built from mastery graph traversal | Natural progression |

**Pedagogical patterns** (content state):
| Field | Meaning |
|-------|---------|
| `not_yet_viewed` | User hasn't VIEWED this content |
| `viewed_not_mastered` | User has VIEWED but not MASTERED |
| `ready_to_review` | MASTERED but due for review |

**Real-world usage**: `search_routes.py` checkboxes → `SearchRequest.to_graph_patterns()`

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

class LessonSearchService(BaseService[LessonOperations, Entity]):
    _config = create_curriculum_domain_config(
        dto_class=CurriculumDTO,
        model_class=Entity,
        domain_name="article",
        search_fields=("title", "summary", "tags"),
        search_order_by="updated_at",
    )
    # _user_ownership_relationship = None → no OWNS filter applied
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

**Context**: Activity domain search services with `intelligent_search()`.

**Solution**:
```python
# Service-level intelligent search (extracts filters from query text)
result, parsed_query = await tasks_service.search.intelligent_search(
    "urgent overdue tasks in progress",
    user_uid=user_uid,
    limit=20,
)
# parsed_query.priorities → [Priority.HIGH, Priority.CRITICAL]
# parsed_query.statuses → [EntityStatus.ACTIVE]
# parsed_query.text_query → "overdue tasks"  # Remaining text after filter extraction

# The service auto-builds filters from parsed semantic terms:
# priority="critical", status="in_progress"
# Then falls back to text search on remaining query
```

**Trade-offs**:
- Only available on Activity domain search services (not KU/LS/LP)
- Parser handles common natural language terms for priority, status, domain
- Falls back to plain text search if no semantic terms found

**Real-world usage**: `TasksSearchService.intelligent_search()`, `GoalsSearchService.intelligent_search()`

---

## Pattern Comparison

| Pattern | Use Case | Complexity | SearchRouter Method |
|---------|----------|------------|---------------------|
| Text Search | Simple keyword lookup | Low | `search()` |
| Cross-Domain | Compare across domains | Low | `search_domains()`, `unified_search()` |
| Faceted Search | Status/priority filters | Medium | `faceted_search()` |
| Graph-Aware | Relationship condition filters | High | `faceted_search()` |
| Traversal | Find connected entities | Medium | `advanced_search()` |
| Tag Search | Array/tag filtering | Low | `advanced_search()` |
| Intelligent | Natural language query | Medium | Service `intelligent_search()` |

---

## Common Gotchas

1. **Always use SearchRouter** — never call `domain_service.search.search()` directly from routes
2. **MOC is not searchable** — it's emergent identity on Ku nodes, not a separate domain
3. **Curriculum search has no user filter** — `_user_ownership_relationship = None`, results are shared for all users
4. **`faceted_search()` vs `advanced_search()`** — both take `SearchRequest`; `faceted_search()` also takes `user_uid` and selects a strategy; `advanced_search()` is for cross-domain with traversal
5. **Graph pattern filters require `user_uid`** — `ready_to_learn`, `supports_goals`, etc. need the user to check their mastery/ownership

**See Also**: [SKILL.md](SKILL.md) for SearchRouter API reference and architecture overview.
