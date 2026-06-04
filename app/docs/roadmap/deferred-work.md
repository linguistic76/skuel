# Deferred Work

**Context**: Items here are real, valuable improvements that are intentionally on hold. They are
not rejected — they are waiting for usage data, business decisions, or production prerequisites
that do not yet exist. Each item has an explicit trigger condition.

**Related**: `/docs/roadmap/security-hardening-deferred.md` — 5 deferred security items
(dependency pinning, rate limiting, secret scanning, session rotation, CI CVE scanning).

---

## Shelved Intelligence Features

The following three features have dedicated design documents in `/docs/intelligence/`. They are
not premature ideas — they are fully designed but correctly deferred until enough data exists
to make them meaningful.

**See**: `/docs/intelligence/INTELLIGENCE_ROADMAP.md` — master overview of the intelligence layer.

---

### 1. Semantic Analysis

**Why deferred**: Semantic analysis computes cross-KU similarity, concept clustering, and
prerequisite inference from content. With fewer than 50 KUs, the signal-to-noise ratio is too
low to produce useful clusters — the algorithm would find spurious patterns in thin data.

**The problem**: Users cannot currently discover related KUs they haven't explicitly linked.
Semantic similarity would surface "you studied X — here's Y which uses the same core concept"
recommendations, and would feed Askesis's gap-detection logic.

**What to do**:

1. Verify KU count: `MATCH (k:Curriculum) RETURN count(k)` — proceed when ≥ 50 with rich `content` fields.
2. Enable the `SemanticAnalysisService` in `services_bootstrap.py` (currently stubbed out).
3. Run the embedding pipeline against existing KUs: `POST /api/ingest/domain/ku` triggers
   embedding generation for all KUs missing embeddings.
4. Wire `SearchRouter.semantic_search()` to the `/search` UI — it already accepts vector queries
   but the UI toggle is disabled.
5. See `/docs/intelligence/SEMANTIC_ANALYSIS_ROADMAP.md` for full implementation steps.

**Enable when**: KU count ≥ 50, majority with non-empty `content` fields.

---

### 2. Discovery Analytics

**Why deferred**: Discovery analytics learns from search behavior — what users search for,
what they click, what they ignore. With fewer than 1,000 logged search queries, the behavioral
signal is too sparse to distinguish signal from noise.

**The problem**: SKUEL's search is currently keyword + embedding similarity. It does not learn
from usage. If 80% of users search "meditation" and click the same three KUs, those KUs should
rank higher. Discovery analytics closes this loop.

**What to do**:

1. Verify search query log count: `MATCH (e:SearchEvent) RETURN count(e)` — proceed when ≥ 1,000.
2. Enable search event logging in `SearchRouter` (event publishing is wired but disabled behind
   `INTELLIGENCE_TIER=full` and a feature flag).
3. Implement click-through rate weighting in `SearchRankingService` using logged events.
4. See `/docs/intelligence/DISCOVERY_ANALYTICS_ROADMAP.md` for full implementation steps.

**Enable when**: 1,000+ search queries logged in Neo4j.

---

### 3. Real-time Intelligence

**Why deferred**: Real-time intelligence (live activity feeds, push-based recommendations,
session-aware context updates) requires concurrent users to be meaningful. With a single
developer testing the system, "real-time" is indistinguishable from "refresh the page."

**The problem**: `UserContextIntelligence.get_ready_to_work_on_today()` currently rebuilds
context on every request. For 10+ daily active users, incremental updates (only recompute what
changed) would meaningfully reduce Neo4j load. Real-time also enables "your colleague just
completed the same KU" social signals.

**What to do**:

1. Verify daily active users: instrument `skuel_daily_active_users` Prometheus gauge — proceed
   when consistently ≥ 10.
2. Add WebSocket session tracking to `SessionBackend` (groundwork exists in `core/auth/`).
3. Replace full `build_rich()` calls with incremental delta queries for unchanged domains.
4. See `/docs/intelligence/REALTIME_INTELLIGENCE_ROADMAP.md` for full implementation steps.

**Enable when**: 10+ daily active users sustained over 2+ weeks.

---

## Decision Points

These items are blocked on business decisions, not engineering complexity. The code stubs exist;
they need a decision to wire up.

---

### 4. Per-user Intelligence Tier

**Why deferred**: The system-wide `INTELLIGENCE_TIER` env var toggle (CORE vs FULL) works
correctly. Per-user tier control requires a billing model — specifically, which features are
free vs paid — and that model has not been defined.

**The problem**: `core/services/intelligence_tier_service.py` implements `get_user_intelligence_tier(user_uid)`
and returns per-user tier based on role. It is not wired to route middleware. Currently all users
get the same tier controlled by the env var.

**What to do**:

1. Define the billing model: which `UserRole` levels get FULL tier? (e.g., MEMBER and above?)
2. In `services_bootstrap.py`, wire `intelligence_tier_service` into the route dependency chain.
3. Replace the env-var gating in the three bootstrap gating points with
   `await intelligence_tier_service.get_user_intelligence_tier(user_uid)`.
4. Update route middleware to pass `user_uid` to the tier check (requires auth context at
   service-selection time, not just inside route handlers).

**Enable when**: Billing model defined — specifically, which subscription tier gets AI features.

---

### 5. KnowledgeConfig Validation

**Why deferred**: `config/validation.py` has a `validate_knowledge_config()` function that
returns an empty list (stub). The fields it would validate — `embedding_model` and
`embedding_dimension` — do not yet exist on `KnowledgeConfig`. This is a 30-minute task once
those fields are added.

**The problem**: If someone deploys SKUEL with a mismatched `embedding_model` / `embedding_dimension`
pair (e.g., `text-embedding-3-large` with dimension 1536 instead of 3072), Neo4j vector index
operations will silently produce incorrect similarity scores. The validation stub exists but
does not catch this.

**What to do**:

1. Add `embedding_model: str` and `embedding_dimension: int` to `KnowledgeConfig` in
   `core/config/unified_config.py`.
2. In `config/validation.py`, implement `validate_knowledge_config()`:
   ```python
   VALID_EMBEDDING_DIMENSIONS = {
       "text-embedding-3-small": [512, 1536],
       "text-embedding-3-large": [256, 1024, 3072],
       "text-embedding-ada-002": [1536],
   }
   if config.embedding_model in VALID_EMBEDDING_DIMENSIONS:
       if config.embedding_dimension not in VALID_EMBEDDING_DIMENSIONS[config.embedding_model]:
           errors.append(f"embedding_dimension {config.embedding_dimension} invalid for {config.embedding_model}")
   ```
3. Add a test in `tests/unit/test_config_validation.py`.

**Enable when**: `embedding_model` and `embedding_dimension` fields are added to `KnowledgeConfig`.

---

## Mechanisms Awaiting a Consumer

These are complete, generic mechanisms that are correctly used in exactly one place today. They
are NOT to be extended speculatively — SKUEL's defer-until-consumer rule means infrastructure does
not get built ahead of a reader. The trigger is a product need, not a data threshold.

---

### 6. `filter_property` edge-filtering beyond GOALS essentiality

**Why deferred**: PR #216 made the `filter_property`/`filter_value` mechanism on a
`UnifiedRelationshipDefinition` work end-to-end — WRITE auto-stamps the edge property
(`_orient_edge`), and all three read paths auto-filter (`get_related_uids`/`count_related`,
`get_cross_domain_context` categorization, `get_with_context`). It lets one relationship type fan
out into separate typed tier buckets (e.g. a goal's `essential_habits` / `critical_habits` /
`optional_habits` off `(:Habit)-[:SUPPORTS_GOAL {essentiality}]->(:Goal)`). An audit (2026-06-04)
asked whether any *other* domain should use it. **Conclusion: none currently qualifies, so nothing
was shipped — a generic mechanism does not mean it must be used.**

A relationship qualifies only when **all four** links are live at once:

1. **Categorical edge property** — mutually-exclusive exact-match tier values, not a continuous
   number (`strength`, `confidence`) and not a single constant.
2. **Writer stamps varied values** — and is actually *called* with more than the default.
3. **Live data carries it** — real edges have the property set to differing values.
4. **A consumer partitions on it** — some service/UI/intelligence reads the *separate* buckets
   (not just their union) and does something different per tier.

Audit evidence (live Docker Neo4j, full-graph scan; full table in memory
`project_filter_property_extension_audit.md`):

| Candidate prop | Relationship | Writer | Consumer | Verdict |
|---|---|---|---|---|
| `dependency_type` | `DEPENDS_ON` | `create_task_dependency` stamps single default `"blocks"` | none | reject — single value, uncalled in prod, no live edge carries it |
| `contribution_type` | — | none (renamed → `essentiality` in #216) | n/a | reject — dead |
| `support_type` | — | none (TypedDict-only) | n/a | reject — dead |
| `strength` | edges | continuous confidence proxy only | n/a | reject — numeric threshold, not categorical |

A direct probe returned **zero edges** across the whole graph:

```cypher
MATCH ()-[r]->()
WHERE r.essentiality IS NOT NULL
   OR r.dependency_type IS NOT NULL
   OR r.contribution_type IS NOT NULL
   OR r.support_type IS NOT NULL
RETURN type(r), r.essentiality, r.dependency_type, r.contribution_type, r.support_type, count(*)
```

Even GOALS essentiality — the sole consumer — has no live data yet (the 8 live `SUPPORTS_GOAL`
edges are property-less; the ingestion path doesn't stamp `essentiality`, only the
`link_goal_to_habit` create path does).

**The problem**: The missing ingredient is never the mechanism — it is a consumer with a reason to
distinguish tiers. Until a product question needs, say, *blocking* vs *informational* task
dependencies shown separately, or *critical* supporting habits weighted higher in ZPD, the buckets
are infrastructure no one reads.

**What to do** (when a consumer emerges — `DEPENDS_ON` is the nearest miss, already 1.5 links in):

1. Pin down the product need that wants the tiers treated *differently* (link 4's reason to exist).
2. Make the edge property categorical and teach the writer's callers to stamp the varied values
   (`create_task_dependency` today only ever passes `"blocks"`); backfill existing edges so live
   data carries it.
3. Add catch-all + per-value filtered `UnifiedRelationshipDefinition` mappings (mirror
   GOALS `essential_habits` etc.). The three read paths then auto-filter — no read-side code change.
4. Add a real-Neo4j round-trip test across all three read paths + write-stamp + catch-all control
   (mirror `tests/integration/test_goal_habit_essentiality.py`).

**Enable when**: A consumer needs a non-GOALS relationship's edges partitioned into separate typed
tier buckets (and does something different per tier).

---

### 7. Knowledge cross-domain context: surface Ku↔Ku `PREREQUISITE_FOR` ("Option B")

**Why deferred**: The family-A `KnowledgeCrossContext` (`core/services/intelligence/cross_domain_contexts.py`)
anchors to `KU_CONFIG`. PR #215 realigned it to the one bucket that can populate today —
`path_step_uids` (`used_by_steps ∪ trained_by_steps`) — and dropped four fields. Two of those
(`applying_task_uids`, `supported_goal_uids`) are genuinely sourceless: a live-graph probe found
**zero Ku→Activity edges** (every `APPLIES_KNOWLEDGE` / `REQUIRES_KNOWLEDGE` / `REINFORCES_KNOWLEDGE`
/ `INFORMED_BY_KNOWLEDGE` edge targets a `:PathStep`, never a `:Ku` — application and goal-support
live at the PathStep layer). The other two (`prerequisite_knowledge_uids`, `dependent_knowledge_uids`)
are real-but-unsurfaced: live Ku↔Ku `PREREQUISITE_FOR` edges exist (3 in the graph, oriented
`(prereq)-[:PREREQUISITE_FOR]->(dependent)`) but `KU_CONFIG.cross_domain_relationship_types` only
traverses `{USES_KU, TRAINS_KU}`, so they never reach the context. **"Option B" = add the
`PREREQUISITE_FOR` mappings.** It was rejected for #215 to keep scope to keys-only and to avoid a
side effect: `KU_CONFIG.cross_domain_relationship_types` also feeds Ku-search graph-enrichment, so
widening it changes more than this one context.

**The problem**: There is no reader, at two layers. (a) The family-A `KnowledgeCrossContext` type is
itself currently **unconsumed** — the #214/#215 realign campaign fixed its keys but deliberately
deferred wiring it to any route/metrics consumer. (b) Even once wired, nothing yet asks "what are
this Ku's prerequisite / dependent Kus?" as separate buckets. Building Option B now adds fields
nothing reads, into a type nothing reads — and reverses a deliberate #215 scope decision for zero
functional gain.

**What to do** (when a consumer wants prerequisite/dependent Kus surfaced):

1. Add `PREREQUISITE_FOR` (both directions) to `KU_CONFIG.cross_domain_relationship_types` —
   incoming → `prerequisite_knowledge` (the prereqs of this Ku), outgoing → `dependent_knowledge`
   (the Kus that depend on this one), per the `(prereq)-[:PREREQUISITE_FOR]->(dependent)` orientation.
2. Re-add `prerequisite_knowledge_uids` / `dependent_knowledge_uids` to `KnowledgeCrossContext.from_dict`
   via `_uids()` (every bucket is a list of `{uid, title, distance, ...}` dicts — `_uids()` extraction
   is required, not optional).
3. Audit the Ku-search graph-enrichment path for the widened `cross_domain_relationship_types` —
   confirm surfacing prerequisite edges in search results is intended, not an accidental side effect.
4. Add a real-Neo4j round-trip + negative control (seed `PREREQUISITE_FOR`, assert both buckets
   populate with correct orientation; CI runs no pytest — verify on local Docker Neo4j).

**Enable when**: A consumer reads a Ku's prerequisite/dependent Kus as *separate* buckets — and the
family-A `KnowledgeCrossContext` type is itself wired to a route/metrics reader.

---

### 8. Task cross-domain context: restore `dependent_task_uids` via incoming-`DEPENDS_ON`

**Why deferred**: PR #215 dropped `dependent_task_uids` from the family-A `TaskCrossContext` because
its only source bucket — `dependents`, fed by `BLOCKED_BY`-incoming — is structurally dead. The
canonical writer `create_task_dependency` (`_relationship_mixin.py`) writes
`(dependent)-[:DEPENDS_ON]->(blocks)`; the live graph has `DEPENDS_ON` task edges and **zero
`BLOCKED_BY`** edges. A task's real dependents are its *incoming* `DEPENDS_ON` edges, and no
`TASKS_CONFIG` bucket surfaces those today. A guard test seeds the canonical edge and asserts the
`dependents` bucket stays empty — it will trip the moment an incoming-`DEPENDS_ON` mapping is added,
which is the signal to update it.

**The problem**: Same two-layer "no reader" as item 7 — the family-A `TaskCrossContext` type is itself
unconsumed (wiring deferred by the #214/#215 campaign), and nothing yet asks "which tasks depend on
this one?" as a separate bucket. The outgoing direction `prerequisite_task_uids` (outgoing
`DEPENDS_ON`) already populates; the inverse is the missing half, waiting on a reason to read it.

**What to do** (when a consumer wants a task's dependents):

1. Add an incoming-`DEPENDS_ON` mapping to `TASKS_CONFIG.cross_domain_relationship_types` → a
   `dependents` (or `dependent_tasks`) bucket.
2. Re-add `dependent_task_uids` to `TaskCrossContext.from_dict` via `_uids()`, plus the matching
   `dependent_count` metric (mirror the existing `prerequisite`/`*_count` pair).
3. Update the guard test (currently asserts the `dependents` bucket stays empty) to assert it now
   populates from incoming `DEPENDS_ON`.

**Enable when**: A consumer reads a task's dependents (incoming `DEPENDS_ON`) as a *separate* bucket —
and the family-A `TaskCrossContext` type is itself wired to a route/metrics reader.

---

## Review Schedule

Review this document at the **September 2026 quarterly review**. Checklist:

| Item | Trigger | Check |
|------|---------|-------|
| Semantic Analysis | KU count ≥ 50 | `MATCH (k:Curriculum) RETURN count(k)` |
| Discovery Analytics | Search queries ≥ 1,000 | `MATCH (e:SearchEvent) RETURN count(e)` |
| Real-time Intelligence | DAU ≥ 10 for 2+ weeks | Grafana `skuel_daily_active_users` |
| Per-user intelligence tier | Billing model defined | Business decision |
| KnowledgeConfig validation | Config fields added | `grep embedding_model core/config/unified_config.py` |
| `filter_property` extension | A consumer wants non-GOALS edge tier buckets | Product need (not a data threshold) |
| Knowledge Ku↔Ku prerequisites (Option B) | A consumer reads prereq/dependent Ku buckets | Product need (not a data threshold) |
| Task `dependent_task_uids` | A consumer reads a task's dependents | Product need (not a data threshold) |

Items that hit their trigger condition before the next review should be unblocked immediately —
don't wait for the review.
