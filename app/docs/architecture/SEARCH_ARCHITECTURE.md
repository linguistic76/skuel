---
title: Search Architecture - Unified Search System
updated: 2026-01-05
status: current
category: architecture
tags: [architecture, search, mega-query, graph-aware, unified-domains, pedagogical, nous]
related: [QUERY_PATTERNS.md, UNIFIED_USER_ARCHITECTURE.md, ADR-023-curriculum-baseservice-migration.md]
---

# Search Architecture - Unified Search System

*Last updated: 2026-01-05*

## Overview

SKUEL's search architecture consists of **three complementary systems** that work together to provide both fast property-based search and rich graph-aware exploration:

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
│           │                                │                   │
│           ▼                                ▼                   │
│  ┌─────────────────────┐         ┌────────────────────────┐   │
│  │ Graph-Aware Search  │◄───────►│   UserContext          │   │
│  │ (Relationship-based)│         │   (~240 fields)        │   │
│  └─────────────────────┘         └────────────────────────┘   │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

## Core Principle

> "Property filters for speed, graph patterns for depth, user context for personalization, pedagogical tracking for learning"

## What's New (January 2026)

The search architecture has been enhanced with **complete curriculum search coverage** and **pedagogical tracking**:

| Feature | Purpose | Implementation |
|---------|---------|----------------|
| **LS/LP Search Services** | Complete 9-entity search coverage | `LsSearchService`, `LpSearchService` |
| **Interaction Tracking** | Track what users have viewed/are learning | `KuInteractionService` + VIEWED/IN_PROGRESS relationships |
| **Nous Filters** | Filter by Worldview section and content source | `nous_section`, `source` facets |
| **Learning Progress Filters** | Find content by learning state | `not_yet_viewed`, `viewed_not_mastered`, `ready_to_review` |
| **Learning State Badges** | Show progress in search results | Mastered/Learning/Viewed badges in `_graph_context` |

### Complete Entity Type Coverage (January 2026 - Unified)

| Entity Type | Search Mode | Service |
|-------------|-------------|---------|
| Tasks, Goals, Habits, Events, Choices, Principles | Graph-Aware | `{Domain}SearchService` |
| KU, LS, LP, MOC | Graph-Aware | `{Domain}SearchService` |

**Note:** All 10 searchable domains now use `graph_aware_faceted_search()`. The Activity/Curriculum distinction has been eliminated per ADR-023.

## The Three Systems

### 1. Simple Search (Property-Based)

**Purpose:** Fast faceted search using property filters

**When Used:** Fallback when no relationship filters are specified

> **Note (January 2026 - Unified Architecture):** All 10 searchable domains now use Graph-Aware Search by default. Simple search is a fallback for text-only queries.

**Implementation:** `SearchRouter.faceted_search()` → domain service `.search()`

**How it Works:**
1. SearchRouter receives SearchRequest
2. Routes to domain search service (e.g., `LsSearchService.search()`, `LpSearchService.search()`, `MocSearchService.search()`)
3. Domain service builds Cypher via raw Cypher queries
4. Executes fulltext or filtered search
5. Returns results with relevance scoring

**UI Mapping:** "Properties" sidebar section
- Domain dropdown
- SEL Category dropdown
- Learning Level dropdown
- Content Type dropdown
- Educational Level dropdown

```python
# Simple search example (via SearchRouter)
request = SearchRequest(
    query_text="meditation",
    domain=Domain.KNOWLEDGE,
    sel_category=SELCategory.SELF_AWARENESS,
)
response = await search_router.faceted_search(request, user_uid)
```

### 2. Graph-Aware Search (Relationship-Based)

**Purpose:** Rich relationship context leveraging Neo4j's graph structure

**When Used:** All 10 searchable domains (January 2026 - Unified Architecture):
- **All domains:** Tasks, Goals, Habits, Events, Choices, Principles, KU, LS, LP, MOC

**Implementation:** `SearchRouter.faceted_search()` → domain service `.graph_aware_faceted_search()`

**How it Works:**
1. SearchRouter routes to graph-aware domain service (checks `_GRAPH_AWARE_DOMAINS`)
2. Domain service executes `graph_aware_faceted_search(request, user_uid, driver)`
3. Builds Cypher with:
   - OWNS relationship for Activity Domains (user ownership)
   - NO ownership filter for KU (shared content)
   - Property filters from SearchRequest
   - **SearchRequest graph patterns** (`ready_to_learn`, `supports_goals`, etc.)
4. Enriches results with `_graph_context` containing:
   - Domain-specific relationships
   - Goal/habit support relationships
   - Knowledge application relationships
   - Task dependencies
   - For KU: prerequisites, enables_learning, applied_in_tasks, supports_goals

**UI Mapping:** "Graph Relationships" sidebar section
- Ready to Learn (prerequisites met)
- Builds on Mastered
- In Active Path
- Supports Goals
- Builds on Habits
- Applied Recently
- Aligned with Principles
- Next Logical Step

```python
# Graph-aware search for activity domains
request = SearchRequest(
    query_text="python",
    domain=Domain.TASKS,
    ready_to_learn=True,
)
response = await search_router.faceted_search(request, user_uid)
# Results include _graph_context with relationship summaries

# Graph-aware search for KU (January 2026 - now uses graph patterns!)
request = SearchRequest(
    query_text="python",
    ready_to_learn=True,     # NOW APPLIED to KU search!
    supports_goals=True,     # NOW APPLIED to KU search!
)
response = await search_router.faceted_search(request, user_uid)
# KU results include _graph_context with prerequisites, enables_learning, etc.
```

### 3. MEGA-QUERY (Context-Based)

**Purpose:** Build complete user state for personalization and ranking

**When Used:** Building `UserContext` for intelligence features

**Implementation:** `/core/services/user/user_context_queries.py`

**How it Works:**
1. Single comprehensive Cypher query
2. Fetches ~240 fields of user state
3. Includes all domains with graph neighborhoods
4. Powers capacity warnings, ranking personalization

**Relationship to Search:**
- NOT directly used for search queries
- Provides user context for result ranking
- Powers capacity warnings in search response
- Enables personalized facet suggestions

```python
# MEGA-QUERY feeds UserContext, which feeds search personalization
user_context = await context_builder.build(user_uid)
# Search uses subset of context for ranking
user_context_dict = _build_user_context_for_ranking(user_uid)
ranked_results = intelligence.rank_results(results, user_context_dict)
```

## How They Work Together

### Request Flow

```
User types search → HTMX triggers /search/results
       │
       ▼
SearchRequest built (14 filter parameters)
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
  │         │   (_graph_aware_search_knowledge, etc.)
  │         │
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

### No Duplication (One Path Forward)

Each system has a distinct role:

- **SearchRouter** is THE single path for all external search (One Path Forward, January 2026)
- **Domain Search Services** handle domain-specific search logic
- **MEGA-QUERY** handles comprehensive state (not search)

The routing logic in `SearchRouter.faceted_search()` ensures the right domain is used:

```python
# From SearchRouter.faceted_search() - THE entry point
# January 2026: ALL 10 searchable domains use graph-aware search
if domain_str in self._GRAPH_AWARE_DOMAINS and user_uid:
    result = await self._graph_aware_domain_search(request, user_uid, domain_str)

# Cross-domain → aggregate from multiple domains
result = await self._cross_domain_search(request)
```

**Graph-Aware Domains (January 2026 - Unified):**
```python
_GRAPH_AWARE_DOMAINS: frozenset[str] = frozenset(
    {"tasks", "goals", "habits", "events", "choices", "principles", "ku", "ls", "lp", "moc"}
)
```

## Pedagogical Tracking System

### Learning State Progression

Users progress through knowledge content via Neo4j relationships:

```
NONE → VIEWED → IN_PROGRESS → MASTERED
  │       │          │            │
  │       │          │            └── User has acquired knowledge
  │       │          └── User is actively learning
  │       └── User has seen/read the content
  └── No interaction yet
```

### Relationship Types

| Relationship | Direction | Purpose |
|--------------|-----------|---------|
| `VIEWED` | `(User)-[:VIEWED]->(KU)` | User has seen this content |
| `IN_PROGRESS` | `(User)-[:IN_PROGRESS]->(KU)` | User is actively learning |
| `MASTERED` | `(User)-[:MASTERED]->(KU)` | User has acquired knowledge |

### KuInteractionService

Tracks user-KU interactions for pedagogical search:

```python
from core.services.ku.ku_interaction_service import KuInteractionService, LearningState

# Record a view (called automatically from /nous routes)
await interaction_service.record_view(user_uid, ku_uid, time_spent_seconds=120)

# Mark as actively learning
await interaction_service.mark_in_progress(user_uid, ku_uid)

# Get current learning state
progress = await interaction_service.get_learning_state(user_uid, ku_uid)
# Returns: UserKuProgress(state=LearningState.VIEWED, view_count=3, ...)

# Batch lookup for search results
states = await interaction_service.get_learning_states_batch(user_uid, ku_uids)
# Returns: {"ku.python-basics": LearningState.MASTERED, ...}
```

### Automatic View Tracking

When users visit `/nous/{section}/{topic}`, views are automatically recorded:

```python
# In nous_routes.py - transparent to users
user_uid = get_current_user(request)
if user_uid and ku_content:
    await services.ku.interaction.record_view(user_uid, ku_uid)
```

## Nous Worldview Integration

### Unified Search for Nous Content

Nous content (the Worldview MOC) is stored as KU nodes in Neo4j with special properties:

| Property | Values | Purpose |
|----------|--------|---------|
| `source` | `"nous"`, `"obsidian"`, `"manual"` | Content origin |
| `nous_section` | `"stories"`, `"environment"`, `"intelligence"`, etc. | Worldview section |

### Filtering by Nous Section

```python
# Search only Stories section content
request = SearchRequest(
    query_text="creativity",
    nous_section="stories",
    source="nous",
)
```

### Available Nous Sections

| Section Slug | Description |
|--------------|-------------|
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

## Unified Search Services (January 2026 - ADR-023)

**Architecture (January 2026):** All search services now extend `BaseService[Backend, Model]`, providing unified search across all 14 domains. The Activity/Curriculum distinction has been eliminated - all domains are peers. See [ADR-023](../decisions/ADR-023-curriculum-baseservice-migration.md).

### Architecture Pattern

```python
class LsSearchService(BaseService["LsUniversalBackend", Ls]):
    _dto_class = LearningStepDTO
    _model_class = Ls
    _search_fields: ClassVar[list[str]] = ["title", "intent", "description"]
    _supports_user_progress: bool = True  # Curriculum feature opt-in
    _user_ownership_relationship: ClassVar[str | None] = None  # Shared content

    # All methods inherited from BaseService:
    # - search(query, limit)
    # - graph_aware_faceted_search(request)
    # - get_by_domain(), get_by_status(), get_by_category()
    # - get_with_content(), get_with_context()
    # - get_prerequisites(), get_enables(), get_hierarchy()
    # - get_user_progress(), update_user_mastery()
```

### LsSearchService - Learning Steps Search

**Location:** `/core/services/ls/ls_search_service.py`

**Backend:** `adapters/persistence/neo4j/ls_backend.py` (LsUniversalBackend)

**Searchable Fields:**
- **Text:** `title`, `intent`, `description`
- **Filters:** Via unified `SearchRequest` model

**Key Methods:**
```python
# Text search (inherited from BaseService)
await ls_service.search.search("python basics", limit=50)

# Unified filter search (inherited from BaseService)
request = SearchRequest(query="python", domains=[Domain.TECH])
await ls_service.search.graph_aware_faceted_search(request)

# Domain-specific (inherited from BaseService)
await ls_service.search.get_by_domain(Domain.TECH)
await ls_service.search.get_by_status(StepStatus.IN_PROGRESS)

# LS-specific methods
await ls_service.search.get_for_learning_path("lp:python-mastery")
await ls_service.search.get_standalone_steps()
await ls_service.search.intelligent_search("tech beginner python")
```

### LpSearchService - Learning Paths Search

**Location:** `/core/services/lp/lp_search_service.py`

**Backend:** `adapters/persistence/neo4j/lp_backend.py` (LpUniversalBackend)

**Searchable Fields:**
- **Text:** `name`, `goal`
- **Filters:** Via unified `SearchRequest` model

**Key Methods:**
```python
# Text search (inherited from BaseService)
await lp_service.search.search("machine learning", limit=50)

# Unified filter search (inherited from BaseService)
request = SearchRequest(query="ml", domains=[Domain.TECH])
await lp_service.search.graph_aware_faceted_search(request)

# LP-specific methods
await lp_service.search.get_by_path_type(LpType.ADAPTIVE)
await lp_service.search.get_for_user(user_uid)
await lp_service.search.get_aligned_with_goal("goal:learn-python")
await lp_service.search.intelligent_search("structured tech beginner")
```

### MocSearchService - Maps of Content Search

**Location:** `/core/services/moc/moc_search_service.py`

**Backend:** `adapters/persistence/neo4j/moc_backend.py` (MocUniversalBackend)

**Searchable Fields:**
- **Text:** `title`, `description`
- **Filters:** Via unified `SearchRequest` model

**Key Methods:**
```python
# Text search (inherited from BaseService)
await moc_service.search.search("python ecosystem", limit=50)

# MOC-specific methods
await moc_service.search.get_templates(domain=Domain.TECH)
await moc_service.search.get_for_user(user_uid)
await moc_service.search.get_related_mocs(moc_uid)
await moc_service.search.intelligent_search("public template tech")
```

### SearchRouter Integration

All 10 domains are registered in `_SEARCHABLE_DOMAINS` (January 2026 - Unified):

```python
_SEARCHABLE_DOMAINS: frozenset[EntityType] = frozenset({
    # All domains are peers - no Activity/Curriculum distinction
    EntityType.TASK, EntityType.GOAL, EntityType.HABIT,
    EntityType.EVENT, EntityType.CHOICE, EntityType.PRINCIPLE,
    EntityType.KU, EntityType.LS, EntityType.LP, EntityType.MOC,
})
```

## Learning Progress Filters

### Pedagogical Search Filters

Three new filters help users find content based on their learning state:

| Filter | Field | Purpose |
|--------|-------|---------|
| **Not Yet Viewed** | `not_yet_viewed` | Content user hasn't seen |
| **In Progress** | `viewed_not_mastered` | Content being learned |
| **Ready to Review** | `ready_to_review` | Mastered content due for review |

### Graph Patterns

These filters generate Cypher patterns using `NOT EXISTS` / `EXISTS`:

```python
# not_yet_viewed=True generates:
"""
NOT EXISTS {
    MATCH (user:User {uid: $user_uid})-[:VIEWED|IN_PROGRESS|MASTERED]->(ku)
}
"""

# viewed_not_mastered=True generates:
"""
EXISTS { MATCH (user:User {uid: $user_uid})-[:VIEWED|IN_PROGRESS]->(ku) }
AND NOT EXISTS { MATCH (user:User {uid: $user_uid})-[:MASTERED]->(ku) }
"""
```

### Combined with Nous Filters

```python
# Find unread Stories content
request = SearchRequest(
    nous_section="stories",
    not_yet_viewed=True,
)

# Find in-progress Intelligence content
request = SearchRequest(
    nous_section="intelligence",
    viewed_not_mastered=True,
)
```

## Learning State in Search Results

### Graph Context Enhancement

Graph-aware search returns learning state in `_graph_context`:

```python
{
    "_graph_context": {
        # Existing fields...
        "prerequisites": [...],
        "enables": [...],

        # NEW: Learning state fields
        "learning_state": "mastered",  # or "in_progress", "viewed", "not_started"
        "has_viewed": True,
        "has_in_progress": False,
        "has_mastered": True,
        "view_count": 5,
    }
}
```

### UI Badges

Search results display learning state badges:

| State | Badge | CSS Class |
|-------|-------|-----------|
| Mastered | ✅ Mastered | `badge-success` |
| In Progress | 📖 Learning | `badge-info` |
| Viewed | 👁️ Viewed (Nx) | `badge-warning` |
| Not Started | *(no badge)* | - |

## Key Files

| Component | File | Purpose |
|-----------|------|---------|
| **Routes** | `/adapters/inbound/search_routes.py` | HTTP handling, SearchRouter injection |
| **SearchRouter** | `/core/models/search/search_router.py` | THE search orchestrator (One Path Forward) |
| **Request Model** | `/core/models/search_request.py` | `SearchRequest`, `SearchResponse` |
| **Domain Search Services** | `/core/services/{domain}/{domain}_search_service.py` | Domain-specific search logic |
| **LS Search** | `/core/services/ls/ls_search_service.py` | Learning Steps search (January 2026) |
| **LP Search** | `/core/services/lp/lp_search_service.py` | Learning Paths search (January 2026) |
| **UI Components** | `/components/search_components.py` | Sidebar, results, learning badges |
| **Intelligence** | `/core/services/search/search_intelligence_service.py` | Ranking, suggestions |
| **MEGA-QUERY** | `/core/services/user/user_context_queries.py` | User state query |
| **Context Builder** | `/core/services/user/user_context_builder.py` | Orchestrates MEGA-QUERY |
| **Interaction Tracking** | `/core/services/ku/ku_interaction_service.py` | VIEWED/IN_PROGRESS tracking |
| **Nous Routes** | `/adapters/inbound/nous_routes.py` | View tracking on topic access |
| **Relationship Names** | `/core/models/relationship_names.py` | VIEWED, IN_PROGRESS, MASTERED |

## SearchRequest Model

**For complete model documentation, see:** [SEARCH_MODELS.md](../reference/models/SEARCH_MODELS.md)

The `SearchRequest` model unifies all filter types with these key features:

- **Query text is OPTIONAL** - Can do filter-only search
- **Core facets** - domain, sel_category, learning_level, content_type, educational_level
- **Domain-specific facets** - status, priority
- **Nous-specific facets** - nous_section, source (filter by Worldview section or content origin)
- **Relationship filters** - ready_to_learn, builds_on_mastered, in_active_path, supports_goals, etc.
- **Pedagogical filters** - not_yet_viewed, viewed_not_mastered, ready_to_review
- **Pagination** - limit, offset

**Key methods:**
- `to_neo4j_filters()` - Property → WHERE clauses (includes nous_section, source)
- `to_graph_patterns()` - Relationship → Cypher patterns (includes pedagogical filters)
- `has_relationship_filters()` - Mode routing (Simple vs Graph-Aware, includes pedagogical filters)

## Domain-Specific Graph Search

Graph-aware search has handlers for each domain:

| Domain | Handler | Graph Context |
|--------|---------|---------------|
| Knowledge | `_graph_aware_search_knowledge()` | prerequisites, enables, supporting_goals |
| Tasks | `_graph_aware_search_tasks()` | applied_knowledge, fulfills_goals, blocked_by |
| Goals | `_graph_aware_search_goals()` | required_knowledge, contributing_tasks, sub_goals |
| Habits | `_graph_aware_search_habits()` | reinforced_knowledge, supporting_goals |
| Events | `_graph_aware_search_events()` | applied_knowledge, linked_goals |
| Choices | `_graph_aware_search_choices()` | informed_by_knowledge, guided_by_principles |
| Principles | `_graph_aware_search_principles()` | grounded_knowledge, guided_goals |

## Personalization Pipeline

Search results are personalized through:

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
   # Includes: workload, energy, time, habits_at_risk, goal_context
   ```

4. **Facet Suggestions**:
   ```python
   suggestions = intelligence.suggest_facets(query, current_facets, user_context)
   ```

## UI Integration

The search page sidebar maps directly to `SearchRequest`:

```
Sidebar Section          →  SearchRequest Field     →  Search Mode
─────────────────────────────────────────────────────────────────
Properties:
  Domain dropdown        →  domain                  →  Simple
  SEL Category           →  sel_category            →  Simple
  Learning Level         →  learning_level          →  Simple
  Content Type           →  content_type            →  Simple
  Educational Level      →  educational_level       →  Simple

Nous Worldview:
  Section dropdown       →  nous_section            →  Simple
  Source dropdown        →  source                  →  Simple

Learning Progress:
  Not Yet Viewed         →  not_yet_viewed          →  Graph-Aware
  In Progress            →  viewed_not_mastered     →  Graph-Aware
  Ready to Review        →  ready_to_review         →  Graph-Aware

Graph Relationships:
  Ready to Learn         →  ready_to_learn          →  Graph-Aware
  Builds on Mastered     →  builds_on_mastered      →  Graph-Aware
  In Active Path         →  in_active_path          →  Graph-Aware
  Supports Goals         →  supports_goals          →  Graph-Aware
  Builds on Habits       →  builds_on_habits        →  Graph-Aware
  Applied Recently       →  applied_in_tasks        →  Graph-Aware
  Aligned with Principles→  aligned_with_principles →  Graph-Aware
  Next Logical Step      →  next_logical_step       →  Graph-Aware
```

## Best Practices

### When to Use Each Mode

| Scenario | Mode | Why |
|----------|------|-----|
| Quick text search | Simple | Fast, property-indexed |
| Filter by category | Simple | Direct property match |
| Filter by Nous section | Simple | Property filter on `nous_section` |
| Find content by source | Simple | Property filter on `source` |
| Find prerequisites | Graph-Aware | Relationship traversal |
| Goal-aligned content | Graph-Aware | Cross-domain relationships |
| Learning path content | Graph-Aware | Path membership |
| Find unread content | Graph-Aware | Requires `NOT EXISTS` on VIEWED |
| Continue learning | Graph-Aware | Requires `EXISTS` on IN_PROGRESS |
| Review mastered content | Graph-Aware | Requires MASTERED relationship check |

### Performance Considerations

- **Simple Search**: Use for high-volume, property-based queries
- **Graph-Aware**: Use when relationship context adds value
- **MEGA-QUERY**: Runs once per session/request, cached in UserContext

### Extending Search

To add a new filter:

1. **Property filter**: Add to `SearchRequest`, update `to_neo4j_filters()`
2. **Relationship filter**: Add bool field, update `has_relationship_filters()` and `to_graph_patterns()`
3. **New domain**: Add handler `_graph_aware_search_{domain}()` in backend

## See Also

### Search Documentation

| Document | Purpose | When to Use |
|----------|---------|-------------|
| **[SEARCH_SERVICE_METHODS.md](../reference/SEARCH_SERVICE_METHODS.md)** | **Method catalog** | Complete method reference for all 10 search services |
| **[SEARCH_MODELS.md](../reference/models/SEARCH_MODELS.md)** | **Model reference** | Complete SearchRequest/SearchResponse documentation |
| [search_service_pattern.md](../patterns/search_service_pattern.md) | Service pattern | How to implement domain search services |
| [search-one-path-forward.md](~/.claude/plans/search-one-path-forward.md) | Architecture plan | One Path Forward consolidation (January 2026) |

### Related Architecture

- [UNIFIED_USER_ARCHITECTURE.md](UNIFIED_USER_ARCHITECTURE.md) - UserContext and MEGA-QUERY
- [query_architecture.md](../patterns/query_architecture.md) - Query builders and patterns
