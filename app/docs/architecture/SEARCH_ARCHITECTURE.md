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

## Searchable Entity Types (12 total)

All 12 entity types resolve through `SearchRouter._SERVICE_REGISTRY` to an
explicit constructor dependency whose parameter name matches the `Services`
field compose reads it from — guarded by
`tests/unit/models/test_search_router_registry.py` (registry key → constructor
param → `Services` field, so `supports_search()` can't lie).

| Group | Entity Types | SearchVisibility | Search Mode |
|-------|---------|-----------|-------------|
| Activity (6) | Tasks, Goals, Habits, Events, Choices, Principles | `OWNER_ONLY` | Graph-Aware |
| Curriculum (3) | Ku, PS, LP | `PUBLIC` (shared, no filter) | Graph-Aware |
| Learning Loop (3) | Exercise (`SCOPE_AWARE`), RevisedExercise + UserEntry (`OWNER_ONLY`) | mixed | Graph-Aware |

**Ku inclusion (July 2026):** Ku joined `_SEARCHABLE_DOMAINS` once the content
campaigns made Kus full lessons (bodies + NOUS topic membership). The old
exclusion rationale ("divergent facade signature") was a facade-shape bug:
`KuService` exposed `search` as a delegation *method*; it now exposes the
sub-service as the `.search` *attribute* (same shape as `PsService`), which is
what `_get_search_service` resolves.

**Deliberate exclusions:**
- **FormTemplate / FormSubmission** — searchable via their own domain services, not routed through `SearchRouter`.
- **MOC** is emergent identity (any entity with `ORGANIZES` relationships), not an `EntityType`, and is not a standalone searchable domain.

**UserEntry privacy line (July 2026):** entries hold private user content (journal
periodic notes live in this store), so `SearchRouter.search(USER_ENTRY, ...)` REQUIRES
`user_uid` (refused otherwise). UserEntry is excluded from the default "All Types"
sweep and from `advanced_search` aggregation; it participates only when explicitly
requested AND user-scoped — the `/search` "My Entries" filter routes through the
OWNS-scoped `graph_aware_faceted_search()` path, and a multi-type `entity_types`
filter sweeps it owner-scoped (`search_domains` threads `user_uid`; each domain's
`SearchVisibility` declaration decides what the uid means — see next section).

```python
_SEARCHABLE_DOMAINS: frozenset[EntityType] = frozenset({
    # Activity (6)
    EntityType.TASK, EntityType.GOAL, EntityType.HABIT,
    EntityType.EVENT, EntityType.CHOICE, EntityType.PRINCIPLE,
    # Curriculum (3)
    EntityType.KU, EntityType.PATH_STEP, EntityType.LEARNING_PATH,
    # Learning Loop (3)
    EntityType.EXERCISE, EntityType.REVISED_EXERCISE, EntityType.USER_ENTRY,
})
```

---

## Ownership Scoping — SearchVisibility (July 2026 ruling)

**Core Principle:** "One scoping mechanism for every strategy — the domain declares
its visibility, the persistence layer composes the Cypher."

`DomainConfig.search_visibility` (`core/models/enums/metadata_enums.py`) is THE
scoping declaration for text, tags, graph-traversal, and faceted search alike.
`DomainConfig.get_search_visibility()` derives it when unset — an ownership
relationship implies `OWNER_ONLY`, its absence implies `PUBLIC` — so only
genuinely instance-scoped domains declare it explicitly.

| Value | Domains | Semantics |
|-------|---------|-----------|
| `PUBLIC` | PS, LP, KU | No filter — shared curriculum content |
| `OWNER_ONLY` | Activities, UserEntry, RevisedExercise | Property scope `n.user_uid = $user_uid` — **every** strategy, faceted included (see the convergence note below) |
| `SCOPE_AWARE` | Exercise | `scope = 'curriculum'` always visible; owned scopes (PERSONAL/ASSIGNED/ASSESSMENT) visible via `:OWNS`, `:SHARES_WITH`, or group membership (`:MEMBER_OF` + `:SHARED_WITH_GROUP`) — ADR-038/040 semantics. A student finds their group's assigned exercise by search; a stranger never sees someone's PERSONAL template |

**Composition point:** `build_search_visibility_clause()`
(`adapters/persistence/neo4j/query/cypher/crud_queries.py`) — the single
WHERE-fragment builder consumed by `build_text_search_query`,
`build_graph_aware_search_query`, `build_array_any_match_query`,
`build_knowledge_read_clause`, `_crud_mixin.get_visible_to_user`, and
`faceted_search_raw`. No strategy carries its own ad-hoc filter.

**Faceted search converged onto the clause (August 2026).** Until then the
faceted path expressed OWNER_ONLY as an anchor `MATCH (user:User {uid:
$user_uid})-[:OWNS]->(entity)` instead of composing the clause, making it the
only strategy that read the `:OWNS` **edge** rather than the denormalized
`user_uid` **property**. The two were held equal by the write-door invariant
`user_uid property == :OWNS owner`, so both answers agreed on a healthy graph —
but the split was real, and the edge is the half that actually went missing in
production: a 2026-07 ingest batch stamped `user_uid` with no edge and an
owner's own Principles vanished from `/search`. Converging on the property also
buys the only index-seek plan (`NodeIndexSeek RANGE INDEX entity:Task(user_uid)`
vs. a `:User` label scan + expand — every OWNER_ONLY label carries a `user_uid`
RANGE index; `User.uid` has none).

The invariant is unchanged and still enforced on both write doors — the `:OWNS`
edge remains the ownership signal for cascade deletes, sharing, and the adapter
Cypher that traverses it. What changed is that **search scoping no longer
depends on it.**

⚠️ **`faceted_search_raw` passes `has_user=True` unconditionally, on purpose.**
`build_search_visibility_clause(OWNER_ONLY, has_user=False)` emits **no
predicate at all**, so deriving `has_user` from `user_uid is not None` would
turn a null uid into an unscoped query over every user's rows. Passing True
always emits `entity.user_uid = $user_uid`, which on a null parameter is a null
predicate matching nothing — fail-closed. Guarded by
`test_search_visibility_scoping.py::test_faceted_null_user_fails_closed`.

**Fail-closed rules:**
- `advanced_search` without `request.user_uid` skips user-owned domains
  entirely and returns curriculum-only for `SCOPE_AWARE` — shared content is
  the unscoped floor. `/api/search/unified` always passes the authenticated uid.
- A raw-layer caller passing `user_uid` with no visibility declaration gets
  `OWNER_ONLY` scoping by default (scoping-by-default; PUBLIC must be declared).
- **`SearchRouter.search()` refuses an `OWNER_ONLY` domain with no user** —
  the text strategy's chokepoint. Only `PUBLIC` (shared curriculum) and
  `SCOPE_AWARE` (floors at CURRICULUM) may be searched anonymously; a service
  that declares nothing is refused too (default-deny). Every aggregate caller
  — `search_domains`, `_cross_domain_search`, `_simple_domain_search` — already
  treats a failed domain result as "contributes nothing", so refusing reads as
  a skip while keeping the fault visible to a direct caller. When present,
  `user_uid` is forwarded unconditionally; the config declaration decides what
  it means.

**Why that gate exists (August 2026).** `build_search_visibility_clause` emits
*no* ownership predicate for `OWNER_ONLY` without a user, and names external
surfaces as responsible for the skip. Only `user_entry` had one, by name, in
`faceted_search`. An anonymous single-domain faceted call for any *other*
OWNER_ONLY domain declined at `_graph_aware_domain_search` (correctly), fell
through to `_simple_domain_search`, and reached `search()` with no scope —
returning every user's rows. `/api/explore/search` resolves its raw `?type=`
param through `EntityType.from_string` with no catalog whitelist and serves
anonymous callers, so `?type=revised_exercise` reached it. `_simple_domain_search`
compounded it by taking no `user_uid` at all, dropping the scope for
authenticated callers too. Both are fixed; the by-name `user_entry` guard in
`faceted_search` stays as the loud refusal at the entry point.

Guarded by `tests/unit/test_search_visibility_scoping.py` (clause shapes,
parenthesization, derivation, faceted composition, router forwarding),
`tests/integration/test_advanced_search_scoping.py` (per-strategy cross-user
negatives incl. faceted + the exercise visibility matrix, revert-verified
against pre-fix main), and
`tests/integration/test_owner_only_ownership_invariant.py` (the write-door
invariant and the two read surfaces over it).

---

## The Three Systems

### 1. Simple Search (Property-Based)

**Purpose:** Fast faceted search using property filters

**When Used:** Fallback for text-only queries with no relationship filters

**Implementation:** `SearchRouter.faceted_search()` → `_simple_domain_search()` → domain service `.search()`

**How it Works:**
1. `SearchRouter` receives `SearchRequest`
2. Routes to the domain search service's `.search()` — inherited from
   `BaseService` (`SearchOperationsMixin`), never defined per domain and never
   called directly from routes
3. The backend builds Cypher via `build_text_search_query()`
   (`adapters/persistence/neo4j/query/cypher/crud_queries.py`): case-insensitive
   `CONTAINS` over the domain's configured `search_fields`, visibility-scoped
   by `build_search_visibility_clause()`
4. Returns results sorted by the domain's `search_order_by`

**UI Mapping:** the Type dropdown alone, or Type + the per-type context
filters (status, priority, SEL category, learning level, ...)

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

**When Used:** All 12 graph-aware domains when relationship filters are present, or always for graph-aware domains

**Implementation:** `SearchRouter.faceted_search()` → domain service `.graph_aware_faceted_search()`

**How it Works:**
1. `SearchRouter` routes to `_graph_aware_domain_search()` (checks `_GRAPH_AWARE_DOMAINS`)
2. Domain service executes `graph_aware_faceted_search(request, user_uid, driver)`
3. Builds Cypher with:
   - Visibility scoping per the domain's `SearchVisibility` declaration
     (`OWNER_ONLY`: ownership MATCH; `PUBLIC`: none for KU/PS/LP;
     `SCOPE_AWARE`: Exercise scope/sharing WHERE fragment)
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

**Purpose:** Build complete user state (`UserContext`) for the intelligence services

**When Used:** Daily planning, ZPD assessment, Askesis — NOT the search path

**Implementation:** `/core/services/user/user_context_queries.py`

**How it Works:**
1. Single comprehensive Cypher query
2. Fetches ~240 fields of user state across all entity types
3. Powers the intelligence services (daily plan, ZPD, alignment)

**Relationship to Search:**
- NOT part of any search query — `SearchRouter` never builds a `UserContext`,
  so searching stays fast and adds no MEGA-QUERY latency
- Search gets its per-user awareness a cheaper way: the graph-relationship
  filters and `_graph_context` enrichment reference `$user_uid` directly
  inside each domain's own Cypher (see the walkthrough below)
- `build_rich(user_uid, window="30d")` extends MEGA-QUERY with activity
  window data — again for intelligence features, not search

---

## How They Work Together

### Request Flow

The public entry point is always `SearchRouter.faceted_search()`. The names
below the router are private routing helpers (`_`-prefixed) — you never call
them directly; they show where a request goes inside the router.

```
User types in the search box, or changes any filter
       │  (every control carries hx-get="/search/results" — HTMX re-fires
       │   the search with ALL current filters via hx-include)
       ▼
/search/results route (adapters/inbound/search_routes.py)
       │  SearchRequest.from_form_params() — normalizes empty→None,
       │  checkbox→bool, parses enums; invalid values → friendly error
       ▼
SearchRouter.faceted_search(request, user_uid)      ← THE public entry point
       │
       ├─ single domain resolvable? (Type dropdown, or request.domain)
       │    ├─ YES + graph-aware domain + user
       │    │     → _graph_aware_domain_search()
       │    │       → BaseService.graph_aware_faceted_search()
       │    │         → backend.faceted_search_raw()   ← builds the Cypher
       │    │           (ownership MATCH + property filters + text search
       │    │            + relationship-filter fragments + enrichment)
       │    ├─ YES, otherwise → _simple_domain_search()  (text search)
       │    └─ NO → _cross_domain_search()  (sweeps eligible domains)
       │
       ├─ enable_semantic_boost checked? → _augment_with_body_chunks()
       │    (FULL tier: vector search over lesson-body ContentChunks folds
       │     body hits into their parent Ku/PathStep cards; fails soft)
       │
       └─► SearchResponse
             - results (each stamped with _domain; _graph_context on the
               graph-aware path)
             - total / limit / offset (pagination)
             - search_time_ms (shown in the results header)
```

### One Search, End to End (worked example)

What actually happens when you type **"python"**, set Type to **Tasks**, and
check **Ready to learn**. The Cypher below is assembled by
`faceted_search_raw` (`adapters/persistence/neo4j/_search_raw_mixin.py`) from
three sources — the ownership predicate (from `build_search_visibility_clause`,
per the domain's `SearchVisibility`), the text filter (from `search_fields`),
and the relationship-filter fragment (from
`adapters/persistence/neo4j/query/cypher/relationship_filter_fragments.py`,
quoted verbatim):

```cypher
// A plain label MATCH — no ownership pattern. Scoping is a WHERE predicate
// so that one clause builder serves every strategy and every visibility.
MATCH (entity:Task)

WHERE 1=1
  // 1. Ownership scoping: only YOUR tasks survive. $user_uid is a query
  //    parameter — user data is never spliced into the query text. Each
  //    relationship fragment below binds its OWN (user:User {uid: $user_uid});
  //    none depends on this predicate having bound one.
  AND (entity.user_uid = $user_uid)

  // 2. Text search over the domain's configured search_fields
  //    (title + description for Tasks). Case-insensitive substring match.
  AND (toLower(entity.title) CONTAINS $query_text
       OR toLower(entity.description) CONTAINS $query_text)

  // 3. "Ready to learn" = the task has NO prerequisite knowledge
  //    you haven't mastered yet. Double negative on purpose:
  //    "no prerequisite exists that is not mastered".
  AND NOT EXISTS {
      MATCH (entity)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity)
      WHERE NOT EXISTS {
          MATCH (user:User {uid: $user_uid})-[:MASTERED]->(prereq)
      }
  }

// 4. Graph enrichment: pull related nodes so the result card can show
//    "Graph Context" badges without extra round trips. One OPTIONAL MATCH
//    per pattern registered for the domain in relationship_registry.py
//    (Task has ~18 — one shown here).
OPTIONAL MATCH (entity)-[:APPLIES_KNOWLEDGE]->(applied_knowledge:Entity)

RETURN entity,
       collect(DISTINCT {applied_knowledge_uid: applied_knowledge.uid,
                         applied_knowledge_title: applied_knowledge.title}) as applied_knowledge_list
LIMIT $limit
```

Reading it as a founder: `MATCH` walks edges (the arrows ARE the
relationships), `EXISTS { ... }` asks "is there such a path?" without
returning it, and everything prefixed `$` is a parameter — the only way user
input ever reaches a query. Every relationship-filter checkbox on `/search`
maps to exactly one fragment like step 3; they are all in
`relationship_filter_fragments.py`, each a self-contained boolean anchored on
`(entity)`.

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

### Ku Learning State

Ku has native two-tier learning state on `KuBackend` (no PsService dependency):

```python
# Two-tier learning state (Ku-native, via KuService -> KuBackend)
await ku_service.mark_as_studying(user_uid, ku_uid)   # IN_PROGRESS
await ku_service.mark_as_understood(user_uid, ku_uid)  # MASTERED (self-reported, score=0.7)
state = await ku_service.get_ku_learning_state(user_uid, ku_uid)  # {is_studying, is_understood}
```

PathStep has richer learning state via `PsMasteryService` (VIEWED, IN_PROGRESS, MASTERED, BOOKMARKED, MARKED_AS_READ).

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
| Studying | 📖 Studying | `badge-warning` |
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

**Entry point:** both modes above run through `SearchRouter.advanced_search()` — the
`/api/search/unified` JSON endpoint — and `has_semantic_boost()` requires
`context_uids` (a relationship anchor the HTML `/search` form never supplies).

### Body-Chunk Semantic Layer (`/search` UI)

**What it reaches:** Ku/PS ENTITY vectors are frontmatter-only by design (ADR-074 —
title/summary/description); a lesson's **body prose** lives on `:ContentChunk` nodes
(the `chunks_body_content` ingestion configs, ~305 Ku + 244 PS chunks, 100% embedded).
Frontmatter text/faceted search cannot see that prose. The body-chunk layer is the one
`/search` path that does.

**How it works:** `SearchRouter.faceted_search` (THE `/search` HTML entry point) runs
its normal frontmatter/graph/faceted search, then — when the `enable_semantic_boost`
checkbox is on — folds in lesson-BODY hits:

1. Embed the query, search `:ContentChunk` via `find_similar_chunks_by_text`
   (`min_score = body_chunk_search_min_score`, default **0.68** — admits a matched
   passage inside a long chunk (~0.70) while the off-topic noise ceiling floors ~0.66,
   so the empty state still holds for gibberish). The search is **scoped to the active
   facets** — `parent_filters = request.to_property_filters()` applies the same
   nous/level/… membership to the chunk's owning Entity that the frontmatter path applies,
   so a filtered `/search` (e.g. `nous=body`) never leaks lesson bodies from other topics.
2. Map each chunk to its owning Ku/PS Entity, **dedupe to the best-scoring chunk per
   parent** (a lesson is as relevant as its single most on-point passage), and drop
   parents already in the base results or outside the in-scope curriculum type.
3. Append the **PARENT** as a normal result card (never a raw chunk) — the matched
   passage becomes the card description; `_domain` is the parent's EntityType value so
   the card links through `entity_detail_href`.

Gated on the **raw** `enable_semantic_boost` flag (not `has_semantic_boost()`, which
also requires `context_uids`). Scope: a single Ku/PS domain search adds that type's
bodies; a cross-domain (Type=All) search adds both.

**Tier discipline (ADR-043):** Digital-layer enhancement. `INTELLIGENCE_TIER=core` has
no vector service — the augmentation **fails soft** (skips silently, never raises), so
the Analog frontmatter/faceted search stands alone as a complete search, not a degraded
one. `find_similar_chunks_by_text` unavailable / erroring / empty all return the base
results unchanged.

**Code:** `SearchRouter._augment_with_body_chunks` /
`_aggregate_body_chunk_parents` (pure, DB-free dedup) /
`_chunk_hit_to_result` in `core/orchestrator/search_router.py`.

**Scoped Ask (RAG counterpart):** `SearchRouter.retrieve_scoped_chunks(request, …)`
is the chunk-level sibling of `faceted_search` — where the latter returns entity
cards, this returns the passages that ground an Askesis answer. Both take the same
`SearchRequest` and apply `to_property_filters()`, so **Ask and Find share one
facet→scope path**: a `nous` topic on the Askesis composer narrows the retrieved
passages exactly as it narrows `/search` cards. Askesis's `ContextRetriever` routes
`_find_similar_chunks` through this method (search_router post-wired in compose);
returns an `unavailable` error on the CORE tier (no vector service) so the caller
fails soft.

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

## Hybrid Fulltext + Vector Rung (curriculum text search, August 2026)

**What it is:** the text rung of `_execute_advanced_search`'s Strategy 3. Before it
runs the domain's `CONTAINS` search, an eligible domain gets
`Neo4jVectorSearchService.hybrid_search_with_metrics` — Lucene fulltext RRF-merged
with vector similarity. This is the first production reader of the 14
`*_fulltext_idx` indexes, which were synced every boot with no consumer until now
(rulings D1(c)/D2(i), 2026-08-16).

**Which surface it serves — read this before assuming:** `_execute_advanced_search`
is reached only from `SearchRouter.advanced_search()`, i.e. the **`/api/search/unified`
JSON endpoint**. The **`/search` HTML page runs `faceted_search`**, a different path
that still uses `CONTAINS`. So the rung is live in production, but the browser search
page is not yet one of its callers — extending it there is part of the D1(b)
follow-on.

**Why it matters — and what it does NOT buy** (corrected 2026-08-16; PR #1074 shipped an
overstated claim here). The rung buys **relevance ranking and vector recall**. It does
*not* buy case-insensitivity: Strategy 3's fallback is the service-layer
`SearchOperationsMixin.search` → `text_search_raw` → `build_text_search_query`, whose
predicate is `toLower(n.{field}) CONTAINS toLower($query)` — already case-insensitive, as
is `faceted_search_raw`'s. The one case-SENSITIVE predicate is the *backend* method
`_SearchMixin.search` (`_search_mixin.py:224-227`), reached in production only by
`PsAiService.search_by_semantic_query`'s embedding-failure fallback. The two `search`
methods share a name across the service and backend layers — the CLAUDE.md
"same root word at both layers" trap; check the layer before reasoning about the predicate.

Measured limits of the fulltext half (Neo4j 2026.06.0):

- **It does not stem.** `_create_fulltext_index` emits no `OPTIONS`, so all 14 indexes run
  Neo4j's default `standard-no-stop-words` analyzer: `run` does not match "Running". An
  `english` analyzer does stem, but `CREATE ... IF NOT EXISTS` matches on schema as well as
  name and silently skips an existing index, so switching analyzers needs an explicit
  DROP + recreate + reindex.
- **It matches whole tokens, so it loses substring hits.** `photosyn` and `synthesis` each
  return nothing against a "Photosynthesis explained" title that `CONTAINS` matches. The
  fallback below covers a fully empty hybrid result — but not a *partial* one: a query with
  any hybrid hit returns early and never sees the substring matches `CONTAINS` would find.

**Eligibility — all four, belt and braces:**

| Condition | Why |
|-----------|-----|
| `entity_type` in `{ku, path_step, learning_path}` | The explicit curriculum allowlist |
| `search_visibility is PUBLIC` (live read) | `hybrid_search` is **label-wide** — it composes no `user_uid`, so an OWNER_ONLY domain reaching it would return every user's nodes |
| `self._vector_search is not None` | FULL tier only — the vector half needs embeddings (D3) |
| non-empty `query_text` | Nothing to rank |

Both visibility halves are deliberate redundancy: the allowlist alone would not notice
a domain's `SearchVisibility` changing, and the live read alone would admit any PUBLIC
domain the arc never reviewed. **Exercise is deliberately excluded** — its
`SCOPE_AWARE` visibility needs `user_uid` threading, deferred to the D1(b) follow-on
in `docs/roadmap/deferred-work.md`.

**Publication gating:** `VectorSearchBackend.query_fulltext_index` composes
`build_publication_clause` exactly as its vector twin does — hybrid search reads both
doors, and an ungated fulltext half would resurface drafts the vector half withholds
(the Codex #1006 class). Registered in `scripts/publication_gate_registry.py` and
measured in both directions by `test_publication_gate_output_invariant.py`.

**Score normalization:** RRF emits 0.001–0.05 while every other rung emits ~0–1, and
`UnifiedSearchResult.get_top_results` compares combined scores ACROSS domains — so
hybrid scores are divided onto 0–1 at the mapping point. Without it, hybrid-ranked
domains sink below `CONTAINS` domains in a mixed sweep.

The divisor is `Neo4jVectorSearchService.max_rrf_score` = **1/(k+1)** — the theoretical
ceiling, *not* the batch's own maximum. A document ranked first by both halves scores
`vector_weight/(k+1) + text_weight/(k+1)`, and the weights always sum to 1, so the
ceiling is the same for every label. Using each batch's max instead would give every
domain's best hit exactly 1.0: Ku, PathStep and LearningPath would tie at the top, the
merged order would fall to iteration order, and the difference between "ranked first by
both halves" and "ranked first by one" — twice the raw score — would be erased.

**Fallback and backfill:** ineligible, empty, or failed → `[]`, and Strategy 3 runs the
domain's `CONTAINS` search unchanged.

A *short* rung result is topped up rather than trusted alone. Only a **full page**
(`len(items) >= limit_per_domain`) short-circuits `CONTAINS`; anything less also runs it
and merges via `_backfill_with_contains`. This is not belt-and-braces — the two match
**differently**, so neither is strictly better: Lucene matches whole tokens, so a partial
word finds nothing where a substring scan finds the entity (`photosyn` → "Photosynthesis";
`run` → "Running technique"). Returning early on *any* hybrid hit therefore dropped every
substring-only match the rung happened not to rank, which is the rung making a working
search worse — the one thing it promised never to do.

Merge order is load-bearing: hybrid hits keep their rank and their lead, `CONTAINS` hits
fill the remaining budget deduped by `uid` (the hybrid copy wins — it carries the real
score and a derived `match_reason`). Backfilled items keep `relevance_score` 0.0, exactly
what a `CONTAINS` result has always scored, so recall is recovered without a substring
match outranking a relevance-ranked one in the cross-domain merge.

**Match attribution is derived, never assumed.** `hybrid_search` returns
`HybridSearchHit` (`core/ports/query_types.py`), which reports `matched_vector` /
`matched_fulltext` per result; the rung turns those into the `match_reason`
("Keyword + semantic match" / "Semantic match" / "Keyword match").
Do not collapse this back to a constant: the vector half is empty whenever a label
has no index or no backfilled embeddings yet, and a fixed "semantic" label would
claim machine understanding for a hit Lucene found on its own.

**Per-domain thresholds** come from `VectorSearchConfig.get_min_score_for_entity()`,
keyed on canonical `NeoLabel` spellings *and* `EntityType` values. Curriculum labels
sit at 0.75 (calibrated for text→entity queries) against a 0.70 generic default — a
label missing from that mapping silently searches at the default, which is how Ku and
PathStep ran at 0.70 before this arc.

**One embed per request, not per domain:** an unfiltered sweep runs the rung for all
three curriculum domains, and `EmbeddingsService.create_embedding` is uncached — so
`advanced_search` embeds the query once (`_embed_query_for_hybrid_rung`) and passes the
vector to each `hybrid_search` call. Adding a domain to the allowlist costs no extra
embedding. It returns `None` when the rung cannot fire at all, so nothing is paid for a
rung that will not run.

**Index naming:** `NeoLabel.fulltext_index_name()` is THE rule, shared by the schema
manager (creation) and the query side (lookup) so the two cannot drift. It snake-cases
multi-word labels — `PathStep` → `path_step_fulltext_idx`, which flat `label.lower()`
got wrong, silently matching no index at all.

**Lucene escaping:** `core/utils/lucene.py::escape_lucene_query` neutralizes user input at
the boundary. Syntax reaches the parser through **two** doors and both must be closed:

1. **Special characters** (`+ - && || ! ( ) { } [ ] ^ " ~ * ? : \ /`) — backslash-escaped.
   Unescaped, `C++ (advanced)` is a parse error rather than a search.
2. **Reserved boolean keywords** (bare uppercase `AND`/`OR`/`NOT`) — quoted. Left bare, a
   lone `AND` raises `ParseException` (which `_fulltext_search` turns into an empty result,
   silently degrading hybrid to vector-only), and `peace NOT war` *excludes* documents the
   user never asked to exclude. Lowercase `and` and words merely containing a keyword
   (`NOTE`, `android`) are deliberately untouched; `TO` is reserved only inside a range,
   which cannot form because `[`/`]` are already escaped.

---

## Search-Event Logging (Discovery Analytics Phase 1, July 2026)

Every EXTERNAL search through SearchRouter publishes a `search.executed` event
(`core/events/search_events.py`), persisted by `SearchEventRecorder`
(`core/services/search_event_recorder.py`) → `SearchEventBackend`
(`adapters/persistence/neo4j/search_event_backend.py`) as a `:SearchEvent`
node — the behavioral log behind content-gap analysis and the deferred
discovery-analytics phases.

- **One event per external search.** All three entry points publish —
  `faceted_search` (entry_point `faceted`), `intelligent_search`
  (`intelligent`), `advanced_search` (`advanced`). `intelligent_search`'s
  internal per-domain `faceted_search` fan-out passes `log_event=False` and
  never publishes.
- **Empty/filter-only queries are never logged** — no query text, no gap signal.
- **Fail-soft twice over:** the router's `_publish_search_event` helper never
  raises, and the event bus isolates handler errors — logging can never break
  or fail a search. `retrieve_scoped_chunks` (Askesis RAG) is not logged.
- **Tier-independent** (ADR-043 untouched): a plain graph write, active on
  CORE and FULL; the subscriber is an in-process event-bus handler, not a
  background worker.

**See:** `/docs/roadmap/DISCOVERY_ANALYTICS_ROADMAP.md` (node schema,
gap aggregation, deferred phases).

---

## NOUS Topic Integration

NOUS is the official grouping of Kus — the "magazine sections" of SKUEL's
curriculum (ruled 2026-07-06). Membership is authored in vault YAML as a
`nous:` list on Ku and PathStep frontmatter and stored as an array property:

| Property | Shape | Purpose |
|----------|-------|---------|
| `nous` | array of topic slugs, e.g. `["body", "self-awareness"]` | NOUS topic membership (multi-topic; empty = deliberately unassigned per the rawness principle) |

```python
# Search "breath" within the Body topic
request = SearchRequest(
    query_text="breath",
    nous="body",
)
```

The topic vocabulary is **derived from the graph, never hardcoded**: the
/search dropdown calls `KuService.list_nous_topics()` →
`list_all_categories()` (distinct `nous` values, arrays UNWOUND per element).
Each of the 11 topics has an anchor Ku that self-assigns its own topic, so
the derived list is complete by construction. Current topics: stories,
environment, intelligence, investment, words, relationships, social, body,
exercises, self-management, self-awareness.

Filtering is membership-aware end-to-end: `to_property_filters()` emits the
real `nous` property; `faceted_search_raw` renders scalar params with a
`CASE WHEN entity.nous IS :: LIST<ANY> THEN $v IN entity.nous ELSE ... END`
clause; `get_by_category` uses the `has` operator (exact on scalar category
fields, element membership on array fields). The cross-domain sweep routes
through per-domain `graph_aware_faceted_search` whenever property facets are
present, so "topic only, Type = All" filters correctly.

---

## Search Services Architecture

All search services extend `BaseService[Backend, Model]` with `DomainConfig`. Activity domains use `create_activity_domain_config()`; curriculum domains use `create_curriculum_domain_config()`.

```python
class PsSearchService(BaseService["PsOperations", PathStep]):
    _config = create_curriculum_domain_config(
        dto_class=PathStepDTO,
        model_class=PathStep,
        domain_name="ps",
        search_fields=("title", "intent", "description"),
        category_field="nous",  # NOUS topic membership (array — `has` semantics)
    )
    # All methods inherited: search(), graph_aware_faceted_search(),
    # get_by_status(), get_prerequisites(), get_enables(), ...
```

**Key per-domain methods:**

```python
# PS (Path Steps)
await ps_service.search.search("python basics", limit=50)
await ps_service.search.get_standalone_steps()

# LP (Learning Paths)
await lp_service.search.search("machine learning", limit=50)
await lp_service.search.get_aligned_with_goal("goal_learn-python_xyz")  # staged, PLANNED

# KU (Knowledge Units)
await ku_service.search.search("meditation", limit=50)
await ku_service.search.graph_aware_faceted_search(request, user_uid, driver)
```

---

## Route Wiring

Search routes wire through `DomainRouteConfig` with the router as the primary
service:

```python
# adapters/inbound/search_routes.py
SEARCH_CONFIG = DomainRouteConfig(
    domain_name="search",
    primary_service_attr="search_router",
    api_factory=create_search_api_routes,   # search_router: "SearchRouter"
    api_related_services={"ku_service": "ku", ...},
)
```

The router itself is an application orchestrator
(`core/orchestrator/search_router.py`) built in compose with explicit typed
dependencies — one keyword parameter per routed domain plus
user/vector-search/event-bus, each read from the same-named `Services` field.

**Search HTTP endpoints (all in `search_routes.py`):**

| Route | Method | SearchRouter call |
|-------|--------|-------------------|
| `/search/results` | GET | `faceted_search(SearchRequest, user_uid)` |
| `/api/search/unified` | POST | `advanced_search(SearchRequest)` |
| `/api/search/intelligent` | GET | `intelligent_search(q, limit)` — NL query with semantic filter extraction |

---

## SearchRequest Model

**For complete field documentation, see:** [SEARCH_MODELS.md](../reference/models/SEARCH_MODELS.md)

Key design: **query text is OPTIONAL** — filter-only search is valid, end to end. A facet alone (NOUS topic, entity-type scope, priority, relationship flag, ...) runs a real search; `/search/results` shows the blank-state prompt only when there is neither a query nor any filter (`has_any_criteria()` is False). The underlying Cypher wraps its text match in `if query_text`, so it is well-formed without a query and orders by the DomainConfig default; no embeddings/chunk path is involved (semantic boost stays independently gated and no-ops without query text).

| Field Group | Fields |
|-------------|--------|
| Core facets | `domain`, `sel_category`, `learning_level`, `content_type`, `educational_level` |
| NOUS facet | `nous` (topic slug — array-membership match), `source` |
| Status/priority | `status`, `priority` |
| Relationship filters | `ready_to_learn`, `builds_on_mastered`, `in_active_path`, `supports_goals`, `builds_on_habits`, `applied_in_tasks`, `aligned_with_principles`, `next_logical_step` |
| Pedagogical filters | `not_yet_viewed`, `viewed_not_mastered`, `ready_to_review` |
| Semantic fields | `enable_semantic_boost`, `context_uids`, `enable_learning_aware`, `prefer_unmastered` |
| Pagination | `limit`, `offset` |

**Key methods:**
- `from_form_params()` — classmethod that builds a `SearchRequest` from raw HTML form strings (handles empty→None, checkbox→bool, entity type parsing, extended_facets assembly)
- `to_property_filters()` — property → WHERE clauses
- `to_relationship_filters()` — captures the active relationship-filter flags as a frozen `RelationshipFilters` intent. The flag→Cypher mapping is authored **below the boundary** (ADR-044) in `adapters/persistence/neo4j/query/cypher/relationship_filter_fragments.py::build_relationship_filter_fragments` — `core/` holds no Cypher (SKUEL021)
- `has_any_criteria()` — blank-state gate: True when the request carries query text OR any result-defining filter (property facets, relationship/pedagogical flags, domain/entity-type scope, tags, graph traversal); False for a truly blank request or a bare enhancement toggle. The route shows the prompt iff this is False.
- `has_relationship_filters()` — mode routing (Simple vs Graph-Aware)
- `has_semantic_boost()` — semantic vector search routing
- `has_learning_aware()` — learning-aware vector search routing

---

## Domain-Specific Graph Search

`SearchRouter` has handlers for each domain that build the `_graph_context`:

| Domain | Graph Context Fields |
|--------|---------------------|
| KU | prerequisites, enables, supporting_goals |
| Tasks | applied_knowledge, fulfills_goals, blocked_by |
| Goals | required_knowledge, contributing_tasks, sub_goals |
| Habits | reinforced_knowledge, supporting_goals |
| Events | applied_knowledge, linked_goals |
| Choices | informed_by_knowledge, guided_by_principles |
| Principles | grounded_knowledge, guided_goals |
| Exercise | required_knowledge, for_groups, submissions (incoming) |
| RevisedExercise | responds_to_feedback, revises_exercise, submissions (incoming) |
| Submission | fulfills_exercise, reports_received (incoming) |

---

## Personalization — What Actually Runs

Search personalization is **query-time, not ranking-time** on the `/search`
path: the per-user awareness lives inside the Cypher itself (ownership MATCH,
relationship-filter fragments referencing `$user_uid`, `_graph_context`
enrichment). `faceted_search()` builds no `UserContext` and runs no ranking
pass — that keeps the search box fast.

Context-based scoring exists on the API paths that already carry a
`UserContext`: `intelligent_search()` and `advanced_search()` call
`SearchRouter._score_results()`, which applies the unified per-domain scorers
(next section).

Two response fields are populated by `faceted_search()` itself, both
zero-extra-query by design (July 2026):

- **`facet_counts`** — `build_facet_counts()` (`core/models/search_request.py`)
  counts `entity_type` (the `_domain` stamp) and `nous` values across the
  RETURNED window. Window-scoped like `total` (#555), not a corpus count.
  The UI renders the entity-type breakdown as clickable chips in the results
  header (`_render_domain_breakdown`) when results span multiple types.
- **`capacity_warnings`** — `SearchRouter._peek_capacity_warnings()` reads
  the WARM `UserContext` cache only (`UserService.peek_cached_context` —
  cache-hit-only, never builds), then `UserContext.get_capacity_warnings()`
  produces at most `workload` (score ≥ 0.8) and `overdue_tasks` entries.
  A cold cache simply yields no warnings; pages that build the rich context
  (today, daily plan) warm it, and domain events invalidate it. The UI shows
  a slim advisory strip above the results (`_render_capacity_banner`).

---

## Priority Scoring — Unified Across 6 Activity Domains

All 6 Activity Domain search services implement `get_prioritized(user_context)` by delegating to a single `score_<domain>(entity, context) -> PriorityScore` function in `core/models/search/scoring.py`. Each scorer composes the same shared component helpers (deadline proximity, priority level, goal alignment, streak protection, knowledge alignment, progress momentum, etc.) with domain-specific weights that sum to 1.0.

The same scorers back `SearchRouter._score_results()` — cross-domain search and per-domain prioritization go through one code path.

### Canonical Service Shape

```python
from core.models.search.scoring import score_goal
from core.utils.sort_functions import get_result_score

@with_error_handling("get_prioritized", error_type="database")
async def get_prioritized(
    self, user_context: UserContext, limit: int = 10
) -> Result[list[Goal]]:
    result = await self.backend.find_by(user_uid=user_context.user_uid)
    if result.is_error:
        return Result.fail(result)

    entities = self._to_domain_models(result.value, GoalDTO, Goal)
    entities = [e for e in entities if <domain terminal filter>]

    scored = [(e, score_goal(e, user_context).total) for e in entities]
    scored.sort(key=get_result_score, reverse=True)
    return Result.ok([e for e, _ in scored[:limit]])
```

### Component Weights by Domain

Each `score_<domain>` combines `ComponentScore`s with weights summing to 1.0. `PriorityScore.total` is the weighted sum; `PriorityScore.explain()` and `.components` expose the breakdown for debugging.

| Domain | Primary components (weights) |
|--------|-----------------------------|
| **Task** | Deadline 0.25, Priority 0.15, Goal alignment 0.15, Streak protection 0.15, Knowledge alignment 0.10, Learning alignment 0.10, Context alignment 0.10 |
| **Goal** | Deadline 0.25, Priority 0.20, Progress momentum 0.25, Context alignment 0.15, Learning alignment 0.15 |
| **Habit** | Streak protection 0.30, Priority 0.15, Context alignment 0.20, Goal alignment 0.15, Learning alignment 0.20 |
| **Event** | Deadline 0.30, Goal alignment 0.20, Streak protection 0.20, Event-type bonus 0.15, Context alignment 0.15 |
| **Choice** | Deadline 0.30, Priority 0.25, High-stakes 0.20, Complexity 0.15, Context alignment 0.10 |
| **Principle** | Strength 0.30, Review need 0.25, Alignment health 0.20, Actionability 0.25 |

Actual weights live in `core/models/search/scoring.py` — check the source when tuning.

### Shared Component Helpers

Reused by multiple `score_<domain>` functions. Each returns a `ComponentScore` with normalized `[0.0, 1.0]` value + rationale string:

| Helper | Inputs | Used by |
|--------|--------|---------|
| `score_deadline_proximity(target_date)` | Target date, today, urgent/soon day thresholds | Task, Goal, Event, Choice |
| `score_priority_level(priority)` | `Priority` enum or raw string | Task, Goal, Choice |
| `score_goal_alignment(goal_uid, context.active_goal_uids)` | Foreign key + active set | Task, Goal, Event, Habit |
| `score_streak_protection(habit_uid, context.habit_streaks, context.active_habit_uids)` | Habit UID + streak map | Task, Habit, Event |
| `score_progress_momentum(progress)` | Progress percentage | Goal |

### Config-Driven Temporal Queries (get_upcoming / get_overdue / get_active)

`TimeQueryMixin` provides `get_upcoming()`, `get_overdue()`, and `get_active()` using `DomainConfig` fields:

| Config Field | Default | Purpose |
|-------------|---------|---------|
| `date_field` | `None` | Column driving `get_upcoming` / `get_overdue` (e.g., `target_date` for Goals, `decision_deadline` for Choices) |
| `temporal_exclude_statuses` | `("completed", "failed", "cancelled", "archived")` | The 4 `EntityStatus.is_terminal()` values — excludes finished entities |
| `temporal_secondary_sort` | `None` | Optional secondary ORDER BY (e.g., Events use `"start_time"`) |
| `completed_statuses` | `("completed",)` | Excluded from `get_active` — Goals extend this with `"cancelled"` |

**Domains using base TimeQueryMixin (no override):** Tasks, Goals, Events, Choices
**Domains with custom override:** Habits (frequency-based windows), Principles (90-day review threshold via `is_active` flag)

The base implementation delegates to `upcoming_raw()`, `overdue_raw()`, `active_raw()` on `UniversalNeo4jBackend._TemporalMixin`, which generate Cypher filtered by `temporal_exclude_statuses` and sorted by the domain's `date_field` (+ `temporal_secondary_sort` when set).

### Frequency Window Scoring (Habits)

Habits use **backwards-looking** logic — instead of "how close is the deadline?", they ask "how long since last completion relative to recurrence frequency?"

#### Shared Helper

`get_frequency_window_days()` from `core/utils/timestamp_helpers.py`, backed by `FREQUENCY_WINDOWS_DAYS`:

```python
from core.utils.timestamp_helpers import get_frequency_window_days, FREQUENCY_WINDOWS_DAYS

FREQUENCY_WINDOWS_DAYS: dict[str, int] = {
    "daily": 1,
    "weekly": 7,
    "monthly": 30,
}

get_frequency_window_days("weekly")  # 7
get_frequency_window_days(None)      # 1 (default)
```

**Due:** `days_since_last_completion >= window_days`
**Overdue:** `days_since_last_completion > window_days`
**Never completed:** always due

Used by `_is_habit_due_in_window()`, `_is_habit_overdue()`, and `get_user_due_today()` (plus the `get_upcoming()`/`get_overdue()` overrides in `HabitsSearchService`).

**See:** `/docs/domains/habits.md` → "Frequency Window Logic" for full details.

### Key Files

| File | Purpose |
|------|---------|
| `core/models/search/scoring.py` | Unified `score_<domain>` functions + shared `ComponentScore` helpers (`score_deadline_proximity`, `score_priority_level`, `score_goal_alignment`, `score_streak_protection`, `score_progress_momentum`) and the `PriorityScore` dataclass |
| `core/orchestrator/search_router.py` | `SearchRouter._score_results()` consumes the same scorers for cross-domain ranking |
| `core/utils/timestamp_helpers.py` | `get_frequency_window_days()`, `FREQUENCY_WINDOWS_DAYS`, `week_bounds()`, `month_bounds()`, `prev_month()`, `next_month()`, `week_label()` |
| `core/services/domain_config.py` | `date_field`, `temporal_exclude_statuses`, `temporal_secondary_sort`, `completed_statuses` config fields |
| `core/services/mixins/time_query_mixin.py` | `get_upcoming()`, `get_overdue()`, `get_active()` base implementations |
| `adapters/persistence/neo4j/universal_backend.py` | `upcoming_raw()`, `overdue_raw()`, `active_raw()` on the shared `_TemporalMixin` |
| `core/services/habits/habits_search_service.py` | Habit-specific frequency-window logic using `get_frequency_window_days()` |

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

NOUS Topics:
  Topic dropdown         →  nous                      →  Simple
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

1. **New property filter**: Add field to `SearchRequest`, update `to_property_filters()`
2. **New relationship filter**: Add a bool field + a `RelationshipFilters` field, update `has_relationship_filters()` and `to_relationship_filters()`, then add the Cypher fragment in `relationship_filter_fragments.py` (below the boundary)
3. **New searchable domain**: Add to `_SEARCHABLE_DOMAINS` and `_SERVICE_REGISTRY`, add a same-named constructor parameter on `SearchRouter` (wired in `compose.py` from the same-named `Services` field — the registry test enforces the chain), add `SearchFieldConfig` in `config.py`. For graph-aware search, also add a `_GRAPH_AWARE_DOMAINS` entry
4. **New semantic relationship type**: Add to `relationship_type_weights` in `VectorSearchConfig`

---

## Key Files

| Component | File | Purpose |
|-----------|------|---------|
| **SearchRouter** | `/core/orchestrator/search_router.py` | THE search orchestrator |
| **Routes** | `/adapters/inbound/search_routes.py` | HTTP handling with explicit DI |
| **Request Model** | `/core/models/search_request.py` | `SearchRequest`, `SearchResponse` |
| **Domain Search Services** | `/core/services/{domain}/{domain}_search_service.py` | Domain search logic |
| **Vector Search** | `/core/services/neo4j_vector_search_service.py` | `semantic_enhanced_search()`, `learning_aware_search()` (FULL tier only) |
| **Vector Config** | `/core/config/unified_config.py` | `VectorSearchConfig` |
| **Schema Manager** | `/adapters/persistence/neo4j/neo4j_schema_manager.py` | `sync_fulltext_indexes()` (always), `sync_vector_indexes()` (FULL tier only) |
| **UI Components** | `/ui/search/components.py` | Query box, filter bar (+ mobile drawer), result cards, pagination |
| **Query parsing & ranking** | `SearchQueryParser` (`/core/models/search/query_parser.py`) + `score_*` (`/core/models/search/scoring.py`) | Analog typed-filter (priority/status/domain) parse; `score_*` unified ranking applied by `SearchRouter._score_results` only when a caller supplies `user_context` (CORE tier) |
| **MEGA-QUERY** | `/core/services/user/user_context_queries.py` | User state query |
| **Ku Learning State** | `KuBackend` in `/adapters/persistence/neo4j/backends/curriculum_backends.py` | IN_PROGRESS, MASTERED (Ku-native two-tier: Studying + Understood) |
| **PathStep Learning State** | `/core/services/ps/ps_mastery_service.py` | VIEWED/IN_PROGRESS/MASTERED/BOOKMARKED/MARKED_AS_READ |
| **Relationship Names** | `/core/models/relationship_names.py` | VIEWED, IN_PROGRESS, MASTERED |

---

## See Also

- [SEARCH_SERVICE_METHODS.md](../reference/SEARCH_SERVICE_METHODS.md) — Method catalog for search services
- [SEARCH_MODELS.md](../reference/models/SEARCH_MODELS.md) — Complete `SearchRequest`/`SearchResponse` documentation
- [search_service_pattern.md](../patterns/search_service_pattern.md) — How to implement domain search services
- [UNIFIED_USER_ARCHITECTURE.md](UNIFIED_USER_ARCHITECTURE.md) — UserContext and MEGA-QUERY
- [query_architecture.md](../patterns/query_architecture.md) — Query builders and patterns
- [NEO4J_GENAI_ARCHITECTURE.md](NEO4J_GENAI_ARCHITECTURE.md) — Vector search and embeddings
