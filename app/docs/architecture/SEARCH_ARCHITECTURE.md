---
title: Search Architecture - Unified Search System
updated: 2026-03-03
status: current
category: architecture
tags:
- architecture
- search
- mega-query
- graph-aware
- unified-domains
- pedagogical
- semantic
related:
- QUERY_PATTERNS.md
- UNIFIED_USER_ARCHITECTURE.md
- ADR-023-curriculum-baseservice-migration.md
related_skills:
- skuel-search-architecture
---

# Search Architecture - Unified Search System

## Related Skills

For implementation guidance, see:
- [@skuel-search-architecture](../../.claude/skills/skuel-search-architecture/SKILL.md)

---

## Overview

SKUEL's search architecture consists of **three complementary systems** that work together to provide fast property-based search, rich graph-aware exploration, and context-personalized results:

```
┌────────────────────────────────────────────────────────────────┐
│                      SEARCH INFRASTRUCTURE                      │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌─────────────────────┐         ┌────────────────────────┐   │
│  │   Simple Search     │         │   MEGA-QUERY           │   │
│  │   (Property-based)  │         │   (Context-based)      │   │
│  └─────────────────────┘         └────────────────────────┘   │
│           │                                │                   │
│           ▼                                ▼                   │
│  ┌─────────────────────┐         ┌────────────────────────┐   │
│  │ Graph-Aware Search  │◄───────►│   UserContext          │   │
│  │ (Relationship-based)│         │   (~240 fields)        │   │
│  └─────────────────────┘         └────────────────────────┘   │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**Core Principle:** "Property filters for speed, graph patterns for depth, user context for personalization, semantic relationships for relevance"

## Searchable Domains (9 total)

All 9 domains use `graph_aware_faceted_search()` via `SearchRouter`. The Activity/Curriculum distinction has been eliminated — all domains are peers (ADR-023).

| Group | Domains | Ownership |
|-------|---------|-----------|
| Activity (6) | Tasks, Goals, Habits, Events, Choices, Principles | User-owned (`OWNS`) |
| Curriculum (3) | KU, LS, LP | Shared content (no ownership filter) |

**Note:** MOC is emergent identity (any entity with `ORGANIZES` relationships), not an `EntityType`, and is not a standalone searchable domain.

```python
_GRAPH_AWARE_DOMAINS: frozenset[str] = frozenset(
    {"tasks", "goals", "habits", "events", "choices", "principles", "ku", "ls", "lp"}
)

_SEARCHABLE_DOMAINS: frozenset[EntityType] = frozenset({
    EntityType.TASK, EntityType.GOAL, EntityType.HABIT,
    EntityType.EVENT, EntityType.CHOICE, EntityType.PRINCIPLE,
    EntityType.KU, EntityType.LEARNING_STEP, EntityType.LEARNING_PATH,
})
```

---

## The Three Systems

### 1. Simple Search (Property-Based)

**Purpose:** Fast faceted search using property filters

**When Used:** Fallback for text-only queries with no relationship filters

**Implementation:** `SearchRouter.faceted_search()` → domain service `.search()`

**How it Works:**
1. `SearchRouter` receives `SearchRequest`
2. Routes to domain search service (e.g., `KuSearchService.search()`)
3. Domain service builds Cypher via `UnifiedQueryBuilder`
4. Executes fulltext or filtered search
5. Returns results with relevance scoring

**UI Mapping:** "Properties" sidebar section — domain, SEL category, learning level, content type, educational level

```python
request = SearchRequest(
    query_text="meditation",
    domain=Domain.KNOWLEDGE,
    sel_category=SELCategory.SELF_AWARENESS,
)
response = await search_router.faceted_search(request, user_uid)
```

---

### 2. Graph-Aware Search (Relationship-Based)

**Purpose:** Rich relationship context leveraging Neo4j's graph structure

**When Used:** All 9 searchable domains when relationship filters are present, or always for graph-aware domains

**Implementation:** `SearchRouter.faceted_search()` → domain service `.graph_aware_faceted_search()`

**How it Works:**
1. `SearchRouter` routes to `_graph_aware_domain_search()` (checks `_GRAPH_AWARE_DOMAINS`)
2. Domain service executes `graph_aware_faceted_search(request, user_uid, driver)`
3. Builds Cypher with:
   - `OWNS` relationship filter for Activity Domains (user ownership)
   - No ownership filter for KU/LS/LP (shared content)
   - Property filters from `SearchRequest`
   - Graph pattern filters (`ready_to_learn`, `supports_goals`, etc.)
4. Enriches results with `_graph_context` (prerequisites, enables, relationships, learning state)

**UI Mapping:** "Graph Relationships" sidebar section — Ready to Learn, Builds on Mastered, In Active Path, Supports Goals, Builds on Habits, Applied Recently, Aligned with Principles, Next Logical Step

```python
# Graph-aware with relationship filters
request = SearchRequest(
    query_text="python",
    domain=Domain.TASKS,
    ready_to_learn=True,
    supports_goals=True,
)
response = await search_router.faceted_search(request, user_uid)
# Results include _graph_context with relationship summaries
```

---

### 3. MEGA-QUERY (Context-Based)

**Purpose:** Build complete user state for personalization and ranking

**When Used:** Building `UserContext` for intelligence features; search uses a subset for ranking

**Implementation:** `/core/services/user/user_context_queries.py`

**How it Works:**
1. Single comprehensive Cypher query
2. Fetches ~240 fields of user state across all 14 domains
3. Powers capacity warnings, result ranking, personalized facet suggestions

**Relationship to Search:**
- NOT directly used for search queries
- Provides user context for result ranking and capacity warnings
- `build_rich(user_uid, window="30d")` extends MEGA-QUERY with activity window data

```python
user_context = await context_builder.build(user_uid)
ranked_results = intelligence.rank_results(results, user_context)
```

---

## How They Work Together

### Request Flow

```
User types search → HTMX triggers /search/results
       │
       ▼
SearchRequest built (filter parameters)
       │
       ▼
has_relationship_filters()?
       │
  ┌────┴────┐
  │         │
  NO        YES
  │         │
  ▼         ▼
simple_    graph_aware_
search()   search()
  │         │
  │         ├─► Domain-specific handlers
  │         └─► Returns with _graph_context
  │
  ├─► SearchIntelligenceService.rank_results()
  │   (uses UserContext for personalization)
  │
  └─► SearchResponse with:
      - results (with graph context if applicable)
      - facet_counts (for sidebar badges)
      - capacity_warnings (from UserContext)
```

### Complementary Design

| System | Speed | Depth | Personalization |
|--------|-------|-------|-----------------|
| Simple Search | Fast | Property-only | Via ranking |
| Graph-Aware | Moderate | Rich relationships | Via ranking + context |
| MEGA-QUERY | N/A (background) | Complete state | Powers all personalization |

---

## Pedagogical Tracking

### Learning State Progression

Users progress through knowledge content via Neo4j relationships on KU nodes:

```
NONE → VIEWED → IN_PROGRESS → MASTERED
```

### Relationship Types

| Relationship | Direction | Purpose |
|--------------|-----------|---------|
| `VIEWED` | `(User)-[:VIEWED]->(KU)` | User has seen this content |
| `IN_PROGRESS` | `(User)-[:IN_PROGRESS]->(KU)` | User is actively learning |
| `MASTERED` | `(User)-[:MASTERED]->(KU)` | User has acquired knowledge |

### KuInteractionService

```python
from core.services.ku.ku_interaction_service import KuInteractionService, LearningState

await interaction_service.record_view(user_uid, ku_uid, time_spent_seconds=120)
await interaction_service.mark_in_progress(user_uid, ku_uid)

progress = await interaction_service.get_learning_state(user_uid, ku_uid)
# Returns: UserKuProgress(state=LearningState.VIEWED, view_count=3, ...)

# Batch lookup for search results
states = await interaction_service.get_learning_states_batch(user_uid, ku_uids)
# Returns: {"ku_python-basics_abc": LearningState.MASTERED, ...}
```

### Automatic View Tracking

When users visit `/nous/{section}/{topic}`, views are recorded automatically:

```python
# In nous_routes.py — transparent to users
user_uid = get_current_user(request)
if user_uid and ku_content:
    await services.ku.interaction.record_view(user_uid, ku_uid)
```

### Learning Progress Filters

Three filters in `SearchRequest` let users find content by learning state:

| Filter | Field | Cypher Pattern |
|--------|-------|----------------|
| Not Yet Viewed | `not_yet_viewed=True` | `NOT EXISTS { (user)-[:VIEWED\|IN_PROGRESS\|MASTERED]->(ku) }` |
| In Progress | `viewed_not_mastered=True` | `EXISTS { VIEWED\|IN_PROGRESS } AND NOT EXISTS { MASTERED }` |
| Ready to Review | `ready_to_review=True` | `EXISTS { MASTERED }` with spaced-repetition timing |

### Learning State in Results

Graph-aware search returns learning state in `_graph_context`:

```python
{
    "_graph_context": {
        "prerequisites": [...],
        "enables": [...],
        "learning_state": "mastered",     # "in_progress" | "viewed" | "not_started"
        "has_viewed": True,
        "has_mastered": True,
        "view_count": 5,
    }
}
```

### UI Badges

| State | Badge | CSS Class |
|-------|-------|-----------|
| Mastered | ✅ Mastered | `badge-success` |
| In Progress | 📖 Learning | `badge-info` |
| Viewed | 👁️ Viewed (Nx) | `badge-warning` |
| Not Started | *(no badge)* | — |

---

## Semantic Search

Semantic search integrates SKUEL's graph relationship infrastructure (60+ relationship types) with vector search for context-aware and personalized results.

### Two Modes

**1. Semantic-Enhanced Search** — boosts results based on semantic relationships

```python
request = SearchRequest(
    query_text="python programming",
    enable_semantic_boost=True,
    context_uids=["ku_python-basics_abc", "ku_functions_xyz"],
)
# SearchRouter calls: vector_search.semantic_enhanced_search(...)
```

**Algorithm:**
1. Initial vector search (fetch 2× limit for coverage)
2. For each result, query semantic relationships to `context_uids`
3. Calculate semantic boost: `boost = Σ(type_weight × confidence × strength) / count`
4. Combine: `final_score = vector_score × 0.7 + semantic_boost × 0.3`
5. Re-rank by enhanced score

**2. Learning-Aware Search** — personalizes based on user's learning progress

```python
request = SearchRequest(
    query_text="python programming",
    enable_learning_aware=True,
    user_uid="user_alice",
    prefer_unmastered=True,
)
# SearchRouter calls: vector_search.learning_aware_search(...)
```

**Boost strategy:**

| State | Multiplier | Rationale |
|-------|-----------|-----------|
| NOT_STARTED | +15% | Prioritize discovery |
| IN_PROGRESS | +10% | Currently learning — highly relevant |
| VIEWED | 0% | Seen but not active |
| MASTERED | −20% | Already known |

**Note:** Learning-aware search currently supports the KU label only (learning state relationships only exist for Knowledge Units).

### `SearchRequest` Semantic Fields

```python
enable_semantic_boost: bool = False     # Requires context_uids
context_uids: list[str] | None = None  # KU UIDs as context anchor
enable_learning_aware: bool = False     # Requires user_uid on request
prefer_unmastered: bool = True          # Set False for review mode
```

`has_semantic_boost()` returns True when `enable_semantic_boost=True` and `context_uids` is non-empty.
`has_learning_aware()` returns True when `enable_learning_aware=True`.

### Configuration (`VectorSearchConfig` in `unified_config.py`)

```python
semantic_boost_weight: float = 0.3        # 30% semantic, 70% vector
semantic_boost_enabled: bool = True

relationship_type_weights: dict[str, float] = {
    "REQUIRES_THEORETICAL_UNDERSTANDING": 1.0,
    "REQUIRES_PRACTICAL_APPLICATION": 0.9,
    "REQUIRES_CONCEPTUAL_FOUNDATION": 0.9,
    "BUILDS_MENTAL_MODEL": 0.8,
    "PROVIDES_FOUNDATION_FOR": 0.8,
    "BLOCKS_UNTIL_COMPLETE": 1.0,
    "ENABLES_START_OF": 0.9,
    "APPLIES_KNOWLEDGE_TO": 0.8,
    "RELATED_TO": 0.5,
    "ANALOGOUS_TO": 0.6,
}

learning_state_boost_mastered: float = -0.2       # -20%
learning_state_boost_in_progress: float = 0.1    # +10%
learning_state_boost_viewed: float = 0.0          # neutral
learning_state_boost_not_started: float = 0.15   # +15%
```

**Tuning guidance:**
- Raise `semantic_boost_weight` (0.4–0.5) if results feel too generic
- Lower (0.2) if results feel too narrow
- Disable (0.0) if semantic relationships aren't yet populated for a domain
- **Review mode:** set `prefer_unmastered=False` to invert learning state boosts

### Performance

| Operation | Baseline | Semantic Enhanced | Learning Aware |
|-----------|----------|------------------|----------------|
| Vector search | 100–150ms | 130–200ms (+30–50ms) | 120–180ms (+20–30ms) |
| Graph query | N/A | 20–30ms | 15–20ms |
| Re-ranking | <5ms | <5ms | <5ms |

### Graceful Degradation

- `semantic_boost_enabled=False` → standard vector search
- `context_uids` empty → standard vector search
- Relationship query fails → 0.0 boost, no crash
- Learning state query fails → unmodified scores returned
- Search always returns results even if enhancement features fail

---

## Nous Worldview Integration

Nous content (the Worldview MOC) is stored as KU nodes with special properties:

| Property | Values | Purpose |
|----------|--------|---------|
| `source` | `"nous"`, `"obsidian"`, `"manual"` | Content origin |
| `nous_section` | `"stories"`, `"environment"`, `"intelligence"`, etc. | Worldview section |

```python
# Search only Stories section, unread
request = SearchRequest(
    query_text="creativity",
    nous_section="stories",
    source="nous",
    not_yet_viewed=True,
)
```

### Available Nous Sections

| Slug | Description |
|------|-------------|
| `stories` | Narrative learning content |
| `environment` | Environmental topics |
| `intelligence` | Intelligence and cognition |
| `consciousness` | Consciousness studies |
| `identity` | Identity and self |
| `cosmos` | Cosmological topics |
| `society` | Social structures |
| `history` | Historical content |
| `tech` | Technology topics |
| `values` | Values and ethics |
| `practice` | Practical applications |

---

## Search Services Architecture

All search services extend `BaseService[Backend, Model]` with `DomainConfig`. Activity domains use `create_activity_domain_config()`; curriculum domains use `create_curriculum_domain_config()`.

```python
class LsSearchService(BaseService["BackendOperations[LearningStep]", LearningStep]):
    _config = create_curriculum_domain_config(
        dto_class=LearningStepDTO,
        model_class=LearningStep,
        domain_name="ls",
        search_fields=("title", "intent", "description"),
        category_field="domain",
    )
    # All methods inherited: search(), graph_aware_faceted_search(),
    # get_by_domain(), get_by_status(), get_prerequisites(), get_enables(), ...
```

**Key per-domain methods:**

```python
# LS (Learning Steps)
await ls_service.search.search("python basics", limit=50)
await ls_service.search.get_for_learning_path("lp_python-mastery_abc")
await ls_service.search.get_standalone_steps()

# LP (Learning Paths)
await lp_service.search.search("machine learning", limit=50)
await lp_service.search.get_by_path_type(LpType.ADAPTIVE)
await lp_service.search.get_aligned_with_goal("goal_learn-python_xyz")

# KU (Knowledge Units)
await ku_service.search.search("meditation", limit=50)
await ku_service.search.graph_aware_faceted_search(request, user_uid, driver)
```

---

## Route Wiring

Search routes use explicit parameter-based dependency injection:

```python
# adapters/inbound/search_routes.py
def create_search_routes(
    app: Any,
    rt: Any,
    services: "Services",
    search_router: SearchRouter,  # ← Explicit parameter (no globals)
) -> None:
    @app.get("/search/results")
    async def search_results(...):
        result = await search_router.faceted_search(search_request, user_uid)
        ...
```

Search is a meta-service (orchestrates domain search services), so it uses explicit injection rather than `DomainRouteConfig`, matching the same pattern used by other orchestration-level routes.

---

## SearchRequest Model

**For complete field documentation, see:** [SEARCH_MODELS.md](../reference/models/SEARCH_MODELS.md)

Key design: **query text is OPTIONAL** — filter-only search is valid.

| Field Group | Fields |
|-------------|--------|
| Core facets | `domain`, `sel_category`, `learning_level`, `content_type`, `educational_level` |
| Nous facets | `nous_section`, `source` |
| Status/priority | `status`, `priority` |
| Relationship filters | `ready_to_learn`, `builds_on_mastered`, `in_active_path`, `supports_goals`, `builds_on_habits`, `applied_in_tasks`, `aligned_with_principles`, `next_logical_step` |
| Pedagogical filters | `not_yet_viewed`, `viewed_not_mastered`, `ready_to_review` |
| Semantic fields | `enable_semantic_boost`, `context_uids`, `enable_learning_aware`, `prefer_unmastered` |
| Pagination | `limit`, `offset` |

**Key methods:**
- `to_neo4j_filters()` — property → WHERE clauses
- `to_graph_patterns()` — relationship → Cypher patterns
- `has_relationship_filters()` — mode routing (Simple vs Graph-Aware)
- `has_semantic_boost()` — semantic vector search routing
- `has_learning_aware()` — learning-aware vector search routing

---

## Domain-Specific Graph Search

`SearchRouter` has handlers for each domain that build the `_graph_context`:

| Domain | Handler | Graph Context Fields |
|--------|---------|---------------------|
| KU | `_graph_aware_search_knowledge()` | prerequisites, enables, supporting_goals |
| Tasks | `_graph_aware_search_tasks()` | applied_knowledge, fulfills_goals, blocked_by |
| Goals | `_graph_aware_search_goals()` | required_knowledge, contributing_tasks, sub_goals |
| Habits | `_graph_aware_search_habits()` | reinforced_knowledge, supporting_goals |
| Events | `_graph_aware_search_events()` | applied_knowledge, linked_goals |
| Choices | `_graph_aware_search_choices()` | informed_by_knowledge, guided_by_principles |
| Principles | `_graph_aware_search_principles()` | grounded_knowledge, guided_goals |

---

## Personalization Pipeline

1. **User Context Loading** (from MEGA-QUERY):
   ```python
   user_context = await _build_user_context_for_ranking(user_uid)
   ```

2. **Result Ranking**:
   ```python
   ranked = intelligence.rank_results(results, user_context)
   ```

3. **Capacity Warnings** (in response):
   ```python
   warnings = _build_capacity_warnings(user_context)
   # workload, energy, time, habits_at_risk, goal_context
   ```

4. **Facet Suggestions**:
   ```python
   suggestions = intelligence.suggest_facets(query, current_facets, user_context)
   ```

---

## UI Integration

The search sidebar maps directly to `SearchRequest`:

```
Sidebar Section          →  SearchRequest Field       →  Search Mode
─────────────────────────────────────────────────────────────────────
Properties:
  Domain dropdown        →  domain                    →  Simple
  SEL Category           →  sel_category              →  Simple
  Learning Level         →  learning_level            →  Simple
  Content Type           →  content_type              →  Simple

Nous Worldview:
  Section dropdown       →  nous_section              →  Simple
  Source dropdown        →  source                    →  Simple

Learning Progress:
  Not Yet Viewed         →  not_yet_viewed            →  Graph-Aware
  In Progress            →  viewed_not_mastered       →  Graph-Aware
  Ready to Review        →  ready_to_review           →  Graph-Aware

Graph Relationships:
  Ready to Learn         →  ready_to_learn            →  Graph-Aware
  Builds on Mastered     →  builds_on_mastered        →  Graph-Aware
  In Active Path         →  in_active_path            →  Graph-Aware
  Supports Goals         →  supports_goals            →  Graph-Aware
  Builds on Habits       →  builds_on_habits          →  Graph-Aware
  Applied Recently       →  applied_in_tasks          →  Graph-Aware
  Aligned with Principles→  aligned_with_principles   →  Graph-Aware
  Next Logical Step      →  next_logical_step         →  Graph-Aware
```

---

## Best Practices

### When to Use Each Mode

| Scenario | Mode | Why |
|----------|------|-----|
| Quick text search | Simple | Fast, property-indexed |
| Filter by category or Nous section | Simple | Direct property match |
| Find prerequisites | Graph-Aware | Relationship traversal |
| Goal-aligned content | Graph-Aware | Cross-domain relationships |
| Find unread content | Graph-Aware | `NOT EXISTS` on VIEWED |
| Continue learning | Graph-Aware | `EXISTS` on IN_PROGRESS |
| Context-aware recommendations | Semantic | Relationship boosting |
| "What should I learn next?" | Learning-Aware | Progress-based ranking |
| Background batch operations | Standard vector | No extra graph overhead |

### Performance Considerations

- **Simple Search**: Use for high-volume, property-based queries
- **Graph-Aware**: Use when relationship context adds value (+0ms to +50ms)
- **Semantic search**: +30–50ms overhead — acceptable for interactive search
- **Learning-aware**: +20–30ms overhead
- **MEGA-QUERY**: Runs once per session, cached in UserContext

### Extending Search

1. **New property filter**: Add field to `SearchRequest`, update `to_neo4j_filters()`
2. **New relationship filter**: Add bool field, update `has_relationship_filters()` and `to_graph_patterns()`
3. **New searchable domain**: Add to `_SEARCHABLE_DOMAINS`, add `_GRAPH_AWARE_DOMAINS` entry, add handler `_graph_aware_search_{domain}()`
4. **New semantic relationship type**: Add to `relationship_type_weights` in `VectorSearchConfig`

---

## Key Files

| Component | File | Purpose |
|-----------|------|---------|
| **SearchRouter** | `/core/models/search/search_router.py` | THE search orchestrator |
| **Routes** | `/adapters/inbound/search_routes.py` | HTTP handling with explicit DI |
| **Request Model** | `/core/models/search_request.py` | `SearchRequest`, `SearchResponse` |
| **Domain Search Services** | `/core/services/{domain}/{domain}_search_service.py` | Domain search logic |
| **Vector Search** | `/core/services/neo4j_vector_search_service.py` | `semantic_enhanced_search()`, `learning_aware_search()` |
| **Vector Config** | `/core/config/unified_config.py` | `VectorSearchConfig` |
| **UI Components** | `/ui/search/components.py` | Sidebar, results, learning badges |
| **Intelligence** | `/core/services/search/search_intelligence_service.py` | Ranking, suggestions |
| **MEGA-QUERY** | `/core/services/user/user_context_queries.py` | User state query |
| **Interaction Tracking** | `/core/services/ku/ku_interaction_service.py` | VIEWED/IN_PROGRESS tracking |
| **Relationship Names** | `/core/models/relationship_names.py` | VIEWED, IN_PROGRESS, MASTERED |

---

## See Also

- [SEARCH_SERVICE_METHODS.md](../reference/SEARCH_SERVICE_METHODS.md) — Method catalog for all 9 search services
- [SEARCH_MODELS.md](../reference/models/SEARCH_MODELS.md) — Complete `SearchRequest`/`SearchResponse` documentation
- [search_service_pattern.md](../patterns/search_service_pattern.md) — How to implement domain search services
- [UNIFIED_USER_ARCHITECTURE.md](UNIFIED_USER_ARCHITECTURE.md) — UserContext and MEGA-QUERY
- [query_architecture.md](../patterns/query_architecture.md) — Query builders and patterns
- [NEO4J_GENAI_ARCHITECTURE.md](NEO4J_GENAI_ARCHITECTURE.md) — Vector search and embeddings
