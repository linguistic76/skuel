---
updated: 2026-09-01
---

# Deferred Work

**Context**: Items here are real, valuable improvements that are intentionally on hold. They are not rejected — they are waiting for usage data, business decisions, or production prerequisites that do not yet exist. Each item has an explicit trigger condition.

**Related**: `/docs/roadmap/security-hardening-deferred.md` — the security hardening backlog
(see its Priority Order table for current status).

---

## Shelved Intelligence Features

The three features below are shelved — not premature ideas, but fully scoped and correctly deferred until enough data exists to make them meaningful. Semantic Analysis and Discovery Analytics have dedicated roadmap documents in `/docs/roadmap/`; Real-time Intelligence's roadmap was retired, so its trigger-gated note lives inline below.

**See**: `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md` — the authoritative index of the intelligence layer.

---

### 1. Semantic Analysis

**Search-wiring portion — ✅ SHIPPED (body-chunk layer).** The KU-count trigger
(≥ 50) is met — the graph has 121 Kus (120 nous-assigned), 14 PathSteps, and their
lesson **bodies** are chunked + embedded on `:ContentChunk` (~305 Ku + 244 PS chunks,
100% coverage via ADR-074's event-driven path). `/search` now reaches that body prose:
with the `enable_semantic_boost` checkbox on, `SearchRouter.faceted_search` folds
lesson-BODY semantic hits into the results, surfacing the **parent** Ku/PS card
(deduped, best-chunk score) for a query that matches only body text. Digital-layer
enhancement (ADR-043) — fails soft on the CORE tier (no vector service → analog
frontmatter/graph search stands alone). See `SEARCH_ARCHITECTURE.md` § "Body-Chunk
Semantic Layer".

Stale prior steps this replaced: there is no stubbed `SemanticAnalysisService` to
enable, and no `POST /api/ingest/domain/ku` embedding trigger — embeddings are
post-persist events (ADR-074), not an ingestion side effect.

**Remainder — ✅ ALL THREE SHIPPED 2026-07-10** (the old TextAnalysisService/readability
recipe was buried outright, One Path Forward ruling, same date):

1. **Concept clustering** — #598: "Related concepts" chips on Ku + PS detail pages
   (on-demand `find_similar_to_node`, `ku_similar_min_score=0.72` full-corpus-derived;
   read-time lens, no persistence, no auto-created edges).
2. **Prerequisite inference** — #599: mid-band candidates → LLM judge →
   `/admin/prereq-suggestions` queue → approve writes one Edge YAML into the content
   vault's `edges/` (authored edges stay canonical; suggestions never auto-write).
3. **Askesis/ZPD gap feed** — #600 (shipped-as-scoped): ONE UserContextBuilder (the
   capstone now reaches the daily-plan path), ENABLES-proximal (both enabler
   vocabularies + the PS-enabler bridge; enablers never gate), "Related to your next
   step" chips. **Deferred residue**: semantic expansion of the recommendation pool
   itself waits on engagement data (`APPLIES_KNOWLEDGE`/`REINFORCES_KNOWLEDGE` edges —
   the entry-enrichment capability is the fuel arc).

**Enable when** (residue): entry-enrichment ships and engagement edges exist — then
revisit semantic pool expansion (see [`SEMANTIC_ANALYSIS_ROADMAP.md`](done/SEMANTIC_ANALYSIS_ROADMAP.md)).

---

### 2. Discovery Analytics

**Logging portion — ✅ SHIPPED 2026-07-10 (Phase 1).** Every external search now
lands a `:SearchEvent` node: `SearchRouter` publishes `search.executed` from all
three entry points (faceted/intelligent/advanced) →
`SearchEventRecorder` → `SearchEventBackend`. Tier-independent (a plain graph
write, active on CORE and FULL — the prior claim here that publishing was
"wired but disabled behind a feature flag" was never true; nothing existed
before this ship). One event per external search (internal fan-out suppressed),
empty/filter-only queries skipped, fail-soft twice over (publish helper + event
bus isolation). The zero/low-result **content-gap aggregation**
(`get_search_gaps`) is useful immediately as a content-authoring queue — no
data threshold needed; its `/admin/analytics` surface is live ("Search Gaps
(content authoring queue)" section: gap table + running event total).

**Still deferred (Phases 2+)**: behavioral aggregates need volume. With fewer
than 1,000 logged searches, clustering and usage-weighted ranking are noise.

**What to do**:

1. Verify search event count: `MATCH (e:SearchEvent) RETURN count(e)` — proceed when ≥ 1,000
   (the running total is surfaced on `/admin/analytics`, Search Gaps section).
2. Query clustering + temporal patterns over the logged events.
3. Usage-aware ranking — requires click-tracking (not collected in Phase 1) and a ranking
   integration design pass (no `SearchRankingService` exists; scoring lives in SearchRouter).
4. See `/docs/roadmap/DISCOVERY_ANALYTICS_ROADMAP.md`.

**Enable when**: 1,000+ search events logged in Neo4j.

---

### 3. Real-time Intelligence

**Why deferred**: Real-time intelligence (live activity feeds, push-based recommendations,
session-aware context updates) requires concurrent users to be meaningful. With a single
developer testing the system, "real-time" is indistinguishable from "refresh the page."

**The problem**: `UserContextIntelligence.get_ready_to_work_on_today()` currently rebuilds context on every request. For 10+ daily active users, incremental updates (only recompute what changed) would meaningfully reduce Neo4j load. Real-time also enables "your colleague just completed the same KU" social signals.

**What to do**:

1. Verify daily active users: instrument `skuel_daily_active_users` Prometheus gauge — proceed when consistently ≥ 10.
2. Add WebSocket session tracking to `SessionBackend` (groundwork exists in `core/auth/`).
3. Replace full `build_rich()` calls with incremental delta queries for unchanged domains.

**Enable when**: 10+ daily active users sustained over 2+ weeks.

---

## Decision Points

These items are blocked on business decisions, not engineering complexity. The code stubs exist; they need a decision to wire up.

---

### 4. Per-user Intelligence Tier

**Why deferred**: The system-wide `INTELLIGENCE_TIER` env var toggle (CORE vs FULL) works correctly. Per-user tier control requires a billing model — specifically, which features are free vs paid — and that model has not been defined.

**The problem**: `core/services/intelligence_tier_service.py` implements the pure function `get_user_intelligence_tier(system_tier, user_role)` — system tier is the ceiling, REGISTERED gets CORE, MEMBER+ get the system tier.
It is not wired anywhere (registered in the bloat detector's PLANNED tier). Currently all users get the same tier controlled by the env var.

**What to do**:

1. Define the billing model: which `UserRole` levels get FULL tier? (e.g., MEMBER and above?)
2. Wire the tier resolution into the AI-gating points below `services_bootstrap/` — replace the
   env-var-only check with `get_user_intelligence_tier(system_tier, user.user_role)`.
3. Update route middleware to resolve the user's role at service-selection time (requires auth
   context before route handlers run).

**Enable when**: Billing model defined — specifically, which subscription tier gets AI features.

---



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

Audit evidence (live Docker Neo4j, full-graph scan):

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

**Why deferred**: The Ku cross-domain context anchors to `KU_CONFIG`. PR #215 realigned it to the
one bucket that can populate today — `path_step_uids` (`used_by_steps ∪ trained_by_steps`) — and
dropped four candidate fields. Two of those (`applying_task_uids`, `supported_goal_uids`) are
genuinely sourceless: a live-graph probe found **zero Ku→Activity edges** (every `APPLIES_KNOWLEDGE`
/ `REQUIRES_KNOWLEDGE` / `REINFORCES_KNOWLEDGE` / `INFORMED_BY_KNOWLEDGE` edge targets a `:PathStep`,
never a `:Ku` — application and goal-support live at the PathStep layer). The other two
(`prerequisite_knowledge`, `dependent_knowledge`) are real-but-unsurfaced: live Ku↔Ku
`PREREQUISITE_FOR` edges exist (3 in the graph, oriented `(prereq)-[:PREREQUISITE_FOR]->(dependent)`)
but `KU_CONFIG.cross_domain_relationship_types` only traverses `{USES_KU, TRAINS_KU}`, so they never
reach the context. **"Option B" = add the `PREREQUISITE_FOR` mappings.** It was rejected for #215 to
keep scope to keys-only and to avoid a side effect: `KU_CONFIG.cross_domain_relationship_types` also
feeds Ku-search graph-enrichment, so widening it changes more than this one context.

**The problem**: Nothing yet asks "what are this Ku's prerequisite / dependent Kus?" as separate
buckets. Knowledge has no path-aware `*CrossContext` analyzer wired (the 6 activity domains do;
Ku does not), so building Option B now adds fields no consumer reads, for zero functional gain.

**What to do** (when a consumer wants prerequisite/dependent Kus surfaced):

1. Add `PREREQUISITE_FOR` (both directions) to `KU_CONFIG.cross_domain_relationship_types` —
   incoming → `prerequisite_knowledge` (the prereqs of this Ku), outgoing → `dependent_knowledge`
   (the Kus that depend on this one), per the `(prereq)-[:PREREQUISITE_FOR]->(dependent)` orientation.
2. Surface the new buckets through the canonical path-aware reader (a Ku `*CrossContext` +
   `from_categorized` seam in `core/models/graph/path_aware_types.py`, fed by
   `get_cross_domain_context_typed`).
3. Audit the Ku-search graph-enrichment path for the widened `cross_domain_relationship_types` —
   confirm surfacing prerequisite edges in search results is intended, not an accidental side effect.
4. Add a real-Neo4j round-trip + negative control (seed `PREREQUISITE_FOR`, assert both buckets
   populate with correct orientation — verify on local Docker Neo4j).

**Enable when**: A consumer reads a Ku's prerequisite/dependent Kus as *separate* buckets.

---

### 8. Task cross-domain context: restore `dependent_task_uids` via incoming-`DEPENDS_ON`

**Why deferred**: PR #215 dropped `dependent_task_uids` from the task cross-domain context because
its only candidate source bucket — `dependents`, fed by `BLOCKED_BY`-incoming — is structurally dead.
The canonical writer `create_task_dependency` (`tasks_service.py`) writes
`(dependent)-[:DEPENDS_ON]->(blocks)`; the live graph has `DEPENDS_ON` task edges and **zero
`BLOCKED_BY`** edges. A task's real dependents are its *incoming* `DEPENDS_ON` edges, and no
`TASKS_CONFIG` bucket surfaces those today.

**The problem**: Nothing yet asks "which tasks depend on this one?" as a separate bucket. The
task cross-domain context is same-domain-scoped to knowledge + goals (task→task dependencies live in
the lateral-relationships system, not here), so the inverse dependency direction has no consumer.

**What to do** (when a consumer wants a task's dependents):

1. Add an incoming-`DEPENDS_ON` mapping to `TASKS_CONFIG.cross_domain_relationship_types` → a
   `dependents` (or `dependent_tasks`) bucket.
2. Surface it through the canonical path-aware reader (extend the path-aware `TaskCrossContext` +
   `from_categorized` seam in `core/models/graph/path_aware_types.py`), plus the matching
   `dependent_count` metric in `calculate_task_cross_domain_metrics`.

**Enable when**: A consumer reads a task's dependents (incoming `DEPENDS_ON`) as a *separate* bucket.

---

## Habit-Rhythm Arc Follow-ups

Extracted 2026-08-07 from the completed arc when it moved to
[`done/habit-rhythm-arc.md`](done/habit-rhythm-arc.md) (M1–M7 all shipped, #927/#933/#934):
the arc is finished, these follow-ups are not. Each was left open by design, gated on lived
use rather than on work — the archive is the record, this register is the tracker.

### Habit rows in the weekly-note panel

A5's backward-review half: the weekly-note panel does not yet show habit rows, per the arc's
Non-goals.

**Enable when**: lived weekly-review use wants the backward look — product need, not a data
threshold.

### Non-positive-duration follow-ups (arc PR 2)

The same habit renders `0m` on `/today` while `habits_scheduling_service` proposes `15` —
two surfaces disagreeing about a non-positive `duration_minutes`.

**Enable when**: next touch of either surface; small enough to ride along.

### Monthly-template vault cleanup (founder's, non-repo)

The monthly template in the personal vault still carries the retired markwhen block and lacks
`type: user_entry`/`pipeline` frontmatter. No repo PR — no personal vault content enters this
repo; the item lives here so the arc's archive can stay closed.

**Owner**: founder, on a vault pass.

---

## EntryReport / ActivityReport Search

Extracted 2026-08-07 from
[`done/learning-loop-cross-domain-search.md`](done/learning-loop-cross-domain-search.md)
(levels 1–3b complete) — its "Future" section, previously tracked nowhere live. Both report
entities lack BaseService-based search: `EntryReportService` is an LLM generator, not a
BaseService (would need an `EntryReportSearchService`); `ActivityReportService` is standalone
(would need search methods or a BaseService wrapper). Lower priority by design: teachers
search by Exercise or Submission and navigate to feedback via relationships.

**Enable when**: a teacher workflow wants to search report *content* directly rather than
navigate to it — product need, not a data threshold.

**The embedding half rides this want** (2026-08-30): `EMBEDDING_FIELD_MAPS` carries hollow
`ENTRY_REPORT` and `ACTIVITY_REPORT` maps — no event class, nothing builds text — registered
in `PLANNED_EMBEDDING_MAPS` (`scripts/detect_bloat.py`) with `blocked_by` pointing here.
Completing them is ADR-074's quartet (event class, label, post-persist publish in the
writer, worker subscription), scheduled by the same trigger. Never rename this heading
without moving the two pointers — the detector fails `--check` on a dangling one.

---

## Domain-level fulltext-first text search (D1(b) follow-on)

Deferred 2026-08-16 from the fulltext/hybrid wiring arc (D1 ruling: SearchRouter rung now,
domain-level later). The rung gave Ku/PathStep/LearningPath relevance-ranked hybrid search on
`/api/search/unified` (FULL tier) — and **only** there. Every other text-search caller,
including the `/search` browser page, still runs `CONTAINS`.

**What the rung actually buys — corrected 2026-08-16, verified against Neo4j 2026.06.0.**
PR #1074 claimed the paths it did not reach run *case-sensitive* `CONTAINS`. They do not.
Both production `CONTAINS` predicates lower-case both sides — `faceted_search_raw`
(`toLower(entity.{field}) CONTAINS $query_text`, param pre-lowered) and
`build_text_search_query` behind `text_search_raw`
(`toLower(n.{field}) CONTAINS toLower($query)`). The single case-SENSITIVE predicate in the
persistence layer is `_SearchMixin.search` (`_search_mixin.py:224-227`), whose only
production caller is `PsAiService.search_by_semantic_query`'s embedding-failure fallback —
it is on neither `/search` nor `/api/search/unified`. So the honest value of moving a
surface to fulltext is **relevance ranking and vector recall**, NOT case-insensitivity,
which every surface already has. Two further measured facts bound the case:

- **No stemming.** The 14 shipped indexes carry Neo4j's default `standard-no-stop-words`
  analyzer (`_create_fulltext_index` emits no `OPTIONS`), so `run` does not match
  "Running". An `english` analyzer stems, but `CREATE ... IF NOT EXISTS` matches on
  *schema* as well as name and silently skips an existing index — changing an analyzer
  needs an explicit DROP + recreate + reindex, not a config edit.
- **Lucene loses substring matching.** It matches whole tokens: `photosyn` and `synthesis`
  both return nothing for a "Photosynthesis explained" title that `CONTAINS` matches. Any
  fulltext-first path must therefore keep a `CONTAINS` fallback that fires on **thin**
  results, not only empty ones — the shipped rung originally short-circuited on any hybrid
  hit and lost those matches; fixed by `_backfill_with_contains` (2026-08-16), which tops a
  short rung page up and is the shape any new path should copy.

The follow-on, in rough order of value:

- **The `/search` HTML page.** The shipped rung sits in `_execute_advanced_search`, reached
  only from `advanced_search()` — the `/api/search/unified` JSON endpoint. The browser page
  runs `faceted_search`, a separate path still on `CONTAINS`, so the highest-traffic search
  surface has not changed. Reaching it means either routing the faceted path through the
  same rung or giving `faceted_search` its own; decide which when a consumer asks.
- **`_search_mixin.search` goes fulltext-first with CONTAINS fallback** — makes every caller
  of domain search index-backed and the "Cypher-first search foundation" claim true. Requires
  threading each domain's `SearchVisibility` into the fulltext Cypher (OWNER_ONLY domains need
  `user_uid` scoping the current label-wide fulltext path does not have — the reason this half
  was split off). The gating helpers (`NeoLabel.fulltext_index_name`, `escape_lucene_query`,
  the publication-gated `query_fulltext_index`) already exist.
- **CORE-tier text story** — fulltext needs no embeddings, so a fulltext-only rung (skip the
  vector half) would give CORE-tier relevance-ranked search too. Decide whether that lives in
  the mixin (above) or as a CORE branch of the SearchRouter rung.
- **Exercise** — SCOPE_AWARE visibility (curriculum scope public, owned scopes via
  OWNS/SHARES_WITH/group membership) needs the same user_uid threading, plus Exercise has no
  vector index (add it alongside, or run fulltext-only).

**Enable when**: a consumer wants relevance-ranked text search beyond the curriculum
domains on `/api/search/unified` — the `/search` page included. Product need, not a
data threshold.

### Ruled DEFERRED twice — read this before scoping it a third time

**Ruling 1 (2026-08-16, in the arc that wrote this section).** The trigger was tested
against the value case and did NOT fire: there is no named consumer, and the corrected
value case above (ordering gain, recall regression, no stemming without an analyzer
migration) does not clear "product need" on a surface that already works. The only
recognized work that investigation produced was the partial-result fallback regression on
the already-shipped rung, which shipped as `_backfill_with_contains` (#1077). The five
decision points (`/search` reach · service-layer mixin · CORE tier · Exercise · UserEntry)
were scoped with recommendations but deliberately left undecided — they are the inherited
shape for whenever the trigger fires, not a backlog.

**Ruling 2 (2026-08-25) — the usage census, which was never taken before.** Every
`:SearchEvent` in the live graph, read whole (the population is small enough to enumerate,
so this is a census and not a sample):

| Measure | Value |
|---|---|
| Total events since logging shipped 2026-07-10 | **41** |
| Entry point `faceted` (the `/search` page + `/explore` catalog) | **41** |
| Entry point `advanced` (`/api/search/unified`) | **0** |
| Genuine human queries (rest are July test probes `a`, `x`, `zzz_no_such_thing_xyz`) | **~8** — `breath` ×6, `body` ×2 |
| Most recent search of any kind | **2026-07-22** |

⚠️ **`faceted` is TWO surfaces, and the telemetry cannot separate them.** Both
`search_routes.py` (`/search`) and `explore_ui.py` (`/explore` + `/explore/library`) call
`faceted_search()` without overriding `entry_point="faceted"`, so every row above is one
or the other. The `domains` stamp does not discriminate either: it is populated only when
`_resolve_single_domain` finds a SINGLE domain, and the library always sends
`[KU, PATH_STEP]` (two) while `/search` defaults to All Types — so both emit `domains=[]`.
All 8 genuine queries carry `domains=[]`, `filters=None`, i.e. an unfiltered text box on
one of the two. **Do not attribute the 8 to `/search` specifically.** A distinct
`entry_point` for the library calls is a one-argument fix if surface-level attribution
ever matters — and it would have to land BEFORE any post-redesign usage comparison,
since it cannot be backfilled. (Raised by Codex on #1153.)

So **the surface the shipped rung serves has never been used in production**, and the two
faceted surfaces together have had ~8 real queries. Corpus at the same date:
121 Ku · 25 PathStep · 2 LearningPath · 14 Exercise · 77 Task · 62 UserEntry. Relevance
ordering over ≤20 `CONTAINS` hits drawn from a 121-node Ku corpus is a marginal
difference, not a fix.

**The valuable half has INVERTED — do not scope from the bullet list above.** The
`/search` facet redesign ([`done/search-facet-redesign.md`](done/search-facet-redesign.md))
removed PathStep and LearningPath from that surface entirely; it shipped 2026-08-26 in
#1155–#1160. The shipped rung covers
exactly Ku/PathStep/LearningPath — two of the three are now gone from the page — while the
six Activity Domains promoted to the primary facet are all `OWNER_ONLY`, i.e. the half this
section split off as harder: it needs `user_uid` threaded into the fulltext Cypher.
Anything built for curriculum relevance would now rank two domains the page no longer
returns.

⚠️ **The OWNER_ONLY half is CHEAPER than the 2026-08-16 investigation assumed — its
blocking finding is stale.** That investigation recorded a symmetric difference between
two ownership mechanisms (`faceted_search_raw` anchoring `MATCH (:User)-[:OWNS]->(entity)`
vs `build_search_visibility_clause` matching the `user_uid` property) and called
reconciling them a required ruling. **The ownership-bundle work closed it**:
`faceted_search_raw` no longer reads the `:OWNS` edge — it passes `visibility` to
`build_search_visibility_clause` like every other strategy, and
`test_search_visibility_scoping.py::test_owner_only_emits_the_property_predicate_not_an_owns_match`
pins that the anchor MATCH is gone (`":User" not in query`). One mechanism, one
composition point. Do **not** re-open that ruling — it was already made. (Caught by Codex
on #1153, where this section first restated the stale fact.)

### The "Relevance" label is this section's lever — a known fiction, left standing

Inherited from the `/search` facet redesign, which deliberately did NOT repair it
([`done/search-facet-redesign.md`](done/search-facet-redesign.md)) and left it with the
section that would make it true. `/search`'s sort dropdown offers **"Relevance"**, it is
the DEFAULT, and no path behind it ranks by text relevance. What it actually does depends
on the request shape — three behaviours under one label, none of them BM25:

| Request shape | What "Relevance" does |
|---|---|
| **Single domain** (a Type choice, or a facet resolving to one domain) | `RELEVANCE.get_sort_field()` returns `None` → the backend falls back to the domain's `search_order_by DESC`. Here it IS "Recently Updated" for Ku/PS/LP, "Newest First" for the Activity Domains, event-date for Events — two dropdown entries, one behaviour. |
| **Cross-domain, pure text, no facets** (the default landing shape) | `wants_faceted` is False → `search_domains` (`max(5, limit//6)` per domain — **5** at the default page size of 20, not 3), then a sort by `combined_score` — which is **0.0 for every row**: `_wrap_results` sets neither `relevance_score` nor `priority_score`, and both default to `0.0`. The sort is stable, so it is a **no-op** that preserves domain-iteration order, each domain's block still internally `search_order_by DESC`. It is called "the scored sweep" in the code comments; nothing scores it on this path. |
| **Cross-domain with any facet/tag/relationship filter** | `_faceted_sweep`, then `zip_longest` **round-robin interleave** across domains — not ordering by anything. |

⚠️ Do not restate this as a flat "Relevance means recency" — that is true only of the
single-domain row, and #1153 shipped that overstatement before Codex corrected it. The
defect is that one label covers three behaviours and advertises a fourth.
`ui/explore/cards.py` already excludes RELEVANCE from the library's
sorts *deliberately*, for a different reason (it bypasses the pageable sweep), so `/search`
is the inconsistent surface. This is the same class the July 2026 pass deleted ("no fake
options") — but it is **left in place on purpose**: Mike's intent is to make the label
true — that is the work below, scoped to the domains that remain — rather than to relabel
it away. Do not "tidy" it in a passing PR; that would spend the one lever that makes the
ranking work visible.

**Enable when** (unchanged in kind, sharpened in target): a consumer wants relevance-ranked
text search for the domains that remain on `/search` after the facet redesign — **the six
Activity Domains and Ku**, which since #1155 is the whole surface: UserEntry, Exercise and
RevisedExercise were ruled off it (see `done/search-facet-redesign.md` ruling 2). The
rule, not the list, is the contract: every domain visible on `/search` is either in D1(b)'s
scope or has Relevance disabled for it — so a domain re-added to the page re-opens this,
and the same rule applies to whatever profile-side surface those three land on. Product
need, not a data threshold.

---

## Profile-Side Search for UserEntry, Exercise and RevisedExercise (REGISTERED 2026-08-26)

The one obligation the `/search` facet redesign created. Closure record for the arc itself:
[`done/search-facet-redesign.md`](done/search-facet-redesign.md) (#1155–#1160) — read it
before scoping this; do not re-derive its rulings.

That arc took **UserEntry, Exercise AND RevisedExercise** off `/search` — from the results,
not just the dropdown — on the ground that entries and exercises are lived *output*, and
are searched where they live: the profile hub (`/profile`: Activities · Curriculum ·
Submissions · Reports). Mike sequenced it **strip first, build after**, so the gap is
accepted rather than overlooked. This section is the build half.

⚠️ **All THREE domains, not two.** RevisedExercise is a distinct searchable domain and the
arc sent it to the profile hub alongside Exercise; a build scoped to two would leave
revision artifacts with no browser search at all. (Codex caught the two-name version of
this very row on #1160.)

⚠️ **That search does not exist yet, in any form.** The Submissions tab is four link
buttons, `/submissions/history` renders an unfiltered list, and the Reports tab is
collapsible card sections. `user_entry_ui.py`, `user_entry_routes.py` and
`user_entry_api.py` contain zero search references, and the journals sidebar's search is
conversation sessions, not entries. Exercise search happened ONLY through the old
unfiltered `/search` sweep. Accepted cost while the gap stands: 62 entries, ~8 genuine
searches ever across both `faceted` surfaces.

**The ranking question travels with the entries — it is answered here, not in D1(b).**
UserEntry would have inherited `/search`'s fake Relevance label (its `search_order_by` is
`created_at`). The 2026-08-16 investigation's D5 recommended *excluding* UserEntry from any
fulltext path on the merits: recall matters more than ordering when searching your own
writing, and Lucene's substring loss bites hardest there ("that entry where I mentioned
photosyn…"), on top of it being a privacy line. That pulls against wanting relevance at
all, and the tension is real — **either UserEntry joins D1(b)'s scope, or Relevance is
disabled for it specifically.** D1(b)'s contract is a rule and not a list precisely so this
answers itself: every domain visible on a surface is either in that scope or has Relevance
disabled for it, and that applies to whatever this build puts on `/profile`. (Raised by
Codex on #1153.)

**Enable when**: Mike schedules it — the strip already landed, so the trigger is the build
half: a product decision, not a data threshold. When Reports gains a search box, the
**EntryReport / ActivityReport Search** section above has had its trigger fired and is
scoped with it.

---

## ZPD Snapshot History & Trend Analysis

Extracted 2026-08-07 from [`done/zpd-service-architecture.md`](done/zpd-service-architecture.md)
(implemented) — the deliberately-MVP corner: a single `:ZPDHistory` node per user stores only
the LATEST snapshot (`adapters/persistence/neo4j/zpd_snapshot_backend.py` — "full snapshot
history (timeline arrays, trend analysis) is deferred post-MVP"). Snapshots are written on
pedagogically significant events, so the trigger stream already exists; what is deferred is
keeping the timeline and reading trends from it.

**Enable when**: a consumer wants ZPD-over-time (student progress trends, teacher dashboards) —
and enough snapshot-writing events have accrued for a timeline to say anything.

---

## Calendar Periodic-Notes Arc Follow-up — Monthly-Note Panel Parity

Extracted 2026-08-07 from [`done/calendar-periodic-notes-arc.md`](done/calendar-periodic-notes-arc.md)
(all four PRs shipped 2026-08-03): the weekly note got its read-only planning panel; the
monthly note deliberately did not — "monthly-note panel parity is a follow-up, not in-scope,"
gated on lived use. This register is that tracking; it previously existed only in the archive.

**Enable when**: lived monthly-note use wants the same panel the weekly note has — product
need, not a data threshold.

---

## Secrets Follow-ups — DISPOSITION (2026-08-21)

The two items formerly registered here (shred the `secrets.env` residue by moving compose's
`NEO4J_AUTH`/`NEO4J_PASSWORD` interpolation onto the `with-secrets` wrapper; a dedicated
`KeyringBackend` round-trip unit test) were **taken into Mike's personal queue** and removed
from the live tracked register. Both were small and optional. Full text preserved in this
doc's git history (extracted 2026-08-07 from
[`done/secrets-out-of-worktree.md`](done/secrets-out-of-worktree.md)).

---

## Content Linting — the two survivors (registered 2026-08-21)

Extracted from the deleted `CONTENT_LINTING.md` (premise largely absorbed by
`core/services/ingestion/validator.py`, which already validates UID shape, edge-block
completeness, relationship types, and required fields pre-persist). Two ideas remain
genuinely uncovered:

1. **NOUS vocabulary check** — nous section names are free-typed; a typo passes silently
   (verified 2026-08-21: no `NousSection` vocabulary exists in `core/` or `scripts/`).
2. **Orphan detection** — flag authored content nothing links to, at lint time rather than
   via the knowledge-health gauge's after-the-fact orphan count.

**Enable when**: content authoring volume makes silent nous typos or orphan drift a lived
problem — likely alongside a vault-audit pass, as a ride-along on `validator.py`.

---

## Principles `_validate_update` Reform (or Deletion)

Extracted 2026-08-07 from [`done/update-intents.md`](done/update-intents.md) Phase-7 notes
("Reforming these rules onto the intent is tracked separately") — this register is that
tracking; it previously existed only in code docstrings and the archive.

`PrinciplesCoreService._validate_update` is stale in three of its four rules (keys on
`label` not `title`; the strength rule's casing never matches; the well-established rule
demands a `modification_reason` field that exists nowhere — **unsatisfiable**), yet it is
still live on the base `update` contract. `update_principle` deliberately bypasses it
backend-direct, because routing through `super().update` would activate the unsatisfiable
gate and block CORE/STRONG description edits. Resolution is a ruling, not just work: reform
the rules onto the intent (making both paths validate identically), or delete the hook per
the create-rules precedent in the same file (#963 — length bounds belong to the request
model). Either way the two-path behavioral split ends.

**Same class, found 2026-08-24 (ADR-087 PR-3), in Events**: `EventsCoreService._validate_update`
Rule 2 keys on `duration_minutes`, and two of the three fields its past-event exception allows
(`notes`, `quality_score`) are likewise absent from `EventUpdateIntent` — so this door cannot
reach them at all. Rule 1 and the `tags` exception ARE live and are now pinned by tests. Smaller
than the Principles case (nothing here is *unsatisfiable*, just unreachable), and the same
ruling settles both: reform the rules onto the intent, or delete what the intent cannot carry.

**Enable when**: next substantive touch of the Principles update path — do not let a new
caller reach the base `update` contract before this is resolved.

---

## Tasks/Events Edge-Clear on Edit (`""` → None)

Extracted 2026-08-07 from [`done/update-intents.md`](done/update-intents.md) Phase 7 notes,
where it was scoped out as "a deferred UX bug, not One-Path teardown; track separately" —
this register is that separate tracking (it previously existed nowhere live).

Clearing an edge picker in the Tasks/Events edit forms submits `""`, which does not map to
`None`, so a linked edge cannot be cleared from the edit UI. Recorded 2026-06-05 during the
ADR-066 migration; **re-verify against the current edit routes on pickup** — two months of
form work have landed since.

**Enable when**: next touch of the Tasks/Events edit forms — a bug this small rides along.

---

## Skill↔Doc Backlink Reconciliation (post-canonicalization)

`validate_cross_references.py` used to read prose `@skill` mentions out of doc bodies while
the repo declared its doc→skill links in `related_skills:` frontmatter. Making the validator
read the canonical field (#1023, 2026-08-11) cleared 65 false warnings and **surfaced 28 real ones
that the prose reader had been hiding** — an ADR could satisfy the backlink contract merely by
containing the string `@python` somewhere in its body while its frontmatter named no skill at
all. The instrument is fixed; the data it now sees honestly is not.

Two follow-ons, both deliberately left alone because each needs a judgment call rather than a
mechanical edit:

**1. Reconcile the surfaced backlinks.** Each warning has two legitimate resolutions and only
a human picks: add `related_skills: [python]` to `ADR-022`, *or* drop `ADR-022` from the
`python` skill's `related_adrs` because a curated teaching set shouldn't include it. Doing this
by rote in either direction would corrupt the taxonomy — the point of `primary_docs` is that it
is curated, not exhaustive.

Regenerate the list rather than trusting a count copied into this file:

```bash
uv run python scripts/validate_cross_references.py --verbose
```

`scripts/add_skill_backlinks.py` mechanises the safe subset (doc gets the backlink), but it
walks only `primary_docs` — not `patterns` or `related_adrs` — so it resolved 1 of 28 at the
time of writing. It is the surviving sibling of the deleted `fix_missing_reverse_links.py`,
and unlike that one-shot it now writes a field the validator actually reads.

**2. Resync the drifted body sections.** `sync_cross_references.py` generates `## Related
Skills` blocks *from* frontmatter; 35 docs carry one and **3 had already drifted from the field
they were generated from** (e.g. `PWA_ARCHITECTURE.md`: frontmatter `[fasthtml, pwa]`, rendered
section `[fasthtml]`). These are now cosmetic — the validator no longer reads them — but they
are visibly wrong to a human reader. `--all` is not a surgical fix for those 3: it walks 211
docs across `patterns/`, `architecture/`, `decisions/`, `intelligence/` and would rewrite 47 of
them, adding sections to docs that have frontmatter but no rendered block yet. That breadth is
why it wasn't bundled into a validator fix; run it as its own reviewable change.

```bash
uv run python scripts/sync_cross_references.py --all --dry-run
```

**Enable when**: either a docs-taxonomy pass (item 1) or the next `docs/patterns` sweep that is
already touching these files (item 2). Neither blocks anything — every one of them is a warning,
and `--errors-only`, the pre-commit gate, exits 0.

**Watch for:** the report's orphaned/skills-without-docs listings are truncated. Read the
counts in the statistics block, not the length of the printed list — the info listing caps at
20 while the real orphan count is ~321.

---

## Event Attendance Wiring (`ATTENDS`) — Staged Build (REGISTERED 2026-08-26)

Carried out of the ownership bundle when its closure record was archived — the bundle
itself is done: `docs/roadmap/done/ownership-bundle.md`.

#1119 retargeted the attendee triple (`add_attendee` / `remove_attendee` /
`get_event_attendees`) onto the designed
`(User)-[:ATTENDS {joined_at, role, added_by, status}]->(Event)` shape, with an
invite→accept consent state machine whose actor is always a service parameter from the auth
layer, never the request body. It is **staged, not abandoned**: registered in
`PLANNED_METHODS` (`scripts/detect_bloat.py`). ⚠️ Since #1119 the service methods call
same-named backend methods, so the detector's name-collision mask reports `add_attendee` /
`remove_attendee` as *stale* markings (measured 2026-08-29). What `./dev bloat` says about the
triple is ruled in § Catalog Copies in Code (item 2) — do not restate it here.

**The wiring obligations are recorded once, in ADR-086 § 3 and § Follow-ups** — self-add
eligibility gate, `OWNER_OR_ATTENDEE` visibility, creator auto-attend, ghost filter,
`max_attendees`, role enum. Read them there; do not re-summarise them here (a second copy
is a second thing to keep true).

⚠️ The eligibility gate is a **read-contract** obligation, not a nicety: unconditional
self-add plus `OWNER_OR_ATTENDEE` would let any authenticated user who obtains an event UID
join it and then read a private event — a direct bypass of ADR-085.

**Trigger:** Mike schedules it — a future arc on his explicit decision (ADR-086
§ Follow-ups). The surface stays staged until then.

---

## LP Recommendation Backend Methods — Ruled *Build, Not Now* (2026-08-20)

**Mike's ruling, made twice and confirmed after investigation:** build the
state-keyed LP recommendation feature eventually; do not build it now. Recorded
2026-08-20, re-affirmed the same day after the ZPD-absorption investigation
(PR #1103) with its evidence on the table — including the investigator's
on-record recommendation to delete. The ruling is **build wins**.

**What it is:** `find_paths_for_user` and `get_user_progress_summary` — two
backend methods called by LP intelligence and defined nowhere, whose absence
makes `LpIntelligenceService.recommend_learning_paths` always return `[]`.
The capability they would power — ranking whole LearningPaths by *learning
state* (readiness/mastery) — is done by nothing today: ZPD deliberately stays
Ku-grain and the live vision-keyed recommender
(`LifePathVisionService.recommend_learning_paths`) answers path choice by a
different key.

**The case file is authoritative:**
[`lp-backend-recommendation-methods.md`](lp-backend-recommendation-methods.md) —
verdict, evidence, the sharpened build spec (frozen contract, ports, and the
**consumer requirement**: the current chain terminates in an event with zero
subscribers, so an honest build includes a UI surface or a real subscriber).
Until then the three `Any | None` handles in `core/services/lp_intelligence/`
+ `lp/lp_intelligence_service.py` stay as the in-code markers, each commented —
do not retype them and do not delete the call branches.

**Enable when**: Mike schedules it — product decision, not a data threshold.
The build is a full feature (backend methods + frozen contract + consumer
surface), so it waits out the stabilize-and-content phase.

---

## ContextRetriever's Three Write-Only Fields (REGISTERED 2026-08-20 · Case B part-ruled 2026-08-21)

**Active queue.** Surfaced by the AST sweep in PR #1108 and deliberately left
there — they are not that PR's case (write-only *deps copies*, all superseded).
Registered rather than left in an untracked scratch file, for the same reason the
arc below was: an open question nothing in the repo records is one nobody can
find. Case file: `docs/roadmap/context-retriever-write-only-fields.md`.

`ContextRetriever` assigns three `self.*` fields that nothing reads —
`graph_intel` (`:185`), `events_service` (`:199`), `principles_service` (`:200`).
**Two cases, probably two verdicts; do not batch them.**

**A. `graph_intel`** — zero reads in-class and repo-wide, yet the constructor
takes it (`:148`), the Args docstring describes it (`:174`), and the class
docstring asserts *"Requires GraphIntelligenceService for graph queries."*
Hypothesis (**unconfirmed**): superseded when `ku_backend`/`ps_backend` were
injected *"migrated from inline Cypher"*. Date it with `git log -S` before
deleting. ⚠️ `ASKESIS_ARCHITECTURE.md:537` is a **decoy** — that
`self.graph_intel` is `ContextRelevanceEngine`'s own live field.

**B. `events_service` + `principles_service`** — **staged, not dead**;
`load_ps_bundle` says so in code (`events: list[Any] = []  # Event templates not
yet in graph_context`). `PsBundle.principles`/`.events` exist and are permanently
empty. The blocker is upstream and is a **query change, not a wiring job**: the
MEGA-QUERY `graph_context` projection (`user_context_queries.py:889`) emits
`practice_habits` and `practice_tasks` and no equivalent for the other two.
⚠️ `total_practice_opportunities` is `size(ps_habits) + size(ps_tasks)` — adding
channels without updating it makes it silently undercount.

**Both halves already have their building blocks** — a first draft of this entry
said principles had none, which Codex refuted on #1110. The edges are
`SCHEDULES_EVENT` (key `practice_events`) and `GUIDED_BY_PRINCIPLE` (key
`principles`), and `PsIntelligenceBackend.fetch_practice_counts`
(`ps_intelligence_backend.py:135`) **already traverses all six channels**. What
is missing is only the `graph_context` projection plus a fetch in
`load_ps_bundle`. Searching for `practice_principles` finds nothing because that
is not the key name — a naming miss, not an absence.

⚠️ **"Only a projection and a fetch are missing" is TOO STRONG — there are two
authoring paths.** Direct edges (`BUILDS_HABIT`/`SCHEDULES_EVENT`/
`GUIDED_BY_PRINCIPLE`, written from Edge-YAML via `yaml_field_path`) are what the
MEGA-QUERY projects. The current model is **templates**: `(PS)-[:HAS_EVENT_TEMPLATE]->`
+ `_SpawnOrchestrator` writing `SPAWNED_FROM` / `source_path_step_uid` on
learner-owned instances — **not projected at all**. A `SCHEDULES_EVENT`
projection populates only directly-authored PathSteps; template-based ones stay
empty. Any plan must add the student-scoped spawned-instance traversal or state
that its payoff covers legacy content only.

### ✅ PROBED 2026-08-21 (AuraDB `d2d160c4`) — was content-gated; **now resolved, see below**

At probe time both authoring paths were **completely unused**:

| | count |
|---|---|
| `(:PathStep)-[:BUILDS_HABIT\|ASSIGNS_TASK\|SCHEDULES_EVENT\|GUIDED_BY_PRINCIPLE\|…]->()` | **0** |
| `(:PathStep)-[:HAS_*_TEMPLATE]->()` | **0** |
| `SPAWNED_FROM` edges | **0** |
| PathSteps / Kus | 25 / 124 |
| Tasks / Choices / Events / Habits / Goals / Principles that exist | 91 / 10 / 6 / 5 / 3 / 2 |

And **no vault file has ever declared** `habit_uids`, `task_uids`,
`event_template_uids`, `principle_uids`, `goal_uids` or `choice_uids`. So this is
**never authored**, not a broken pipeline — the activities exist, nothing has
ever been linked to a PathStep either way.

**Consequences for the verdict:**

1. The **"events has a learner-visible consumer, principles does not" asymmetry
   is illusory.** The Socratic practice list is empty for *everyone* today —
   `bundle.habits` and `bundle.tasks` are as empty as `bundle.events`. An earlier
   draft of this entry leaned on that asymmetry; it does not hold.
2. Options A and B both build machinery that **stays empty until content exists**.
3. **One Path Forward does not force a choice here** — neither path superseded
   the other, because neither has ever been used.

### ✅ THE TEST HAS BEEN RUN, 2026-08-21 — **Way 1 works. Option A is the answer.**

The entry above prescribed authoring one `habit_uids:` line and syncing. Done, on
Mike's instruction. Authored on meaning, not convenience — *"Managing Your
Reactions"* ↔ *"Pause and Name One Reaction"*:

```yaml
# 0vault/Ps/Ps_dev/ps_managing-your-reactions.md
habit_uids:
  - habit.pause-and-name
```

Ingested through the **single-file** door (`ingest_file`), deliberately not
`ingest_directory` — a directory run propagates deletions, which is not a risk
worth taking on the live graph for a one-file test.

| step | outcome |
|---|---|
| ingest | `success: True`, `relationships_created: 1` |
| edge in graph | `(ps.self-management.managing-your-reactions)-[:BUILDS_HABIT]->(habit.pause-and-name)` ✅ |
| MEGA-QUERY projection (`user_context_queries.py:829` pattern, run verbatim) | `practice_habits: [{uid: habit.pause-and-name, title: "Pause and Name One Reaction"}]` ✅ |

**So the vault → ingestion → graph → `graph_context` path is intact and
unbroken.** It had simply never been used. The counts above become
`BUILDS_HABIT` **1**, everything else still 0.

⚠️ **Precisely what is proven, and what is not.** Proven by direct observation:
the edge exists and the MEGA-QUERY's own `practice_habits` pattern returns it.
**Not** run: a live Askesis session end-to-end — `load_ps_bundle` is user-scoped
(it walks `active_path_steps_rich`), so seeing it in the tutor needs that
PathStep active for a user. That is user state, not plumbing, and nothing in the
plumbing is now in doubt.

### ✅ P1 — RESOLVED BY THE OWNERSHIP BUNDLE (ADR-085, PR-3, 2026-08-21); was: OPTION A BLOCKED ON AN OWNERSHIP RULING

> Status: the cross-user disclosure mechanism described below is CLOSED — see
> the un-suspended verdict at the end of this entry. The findings below are the
> 2026-08-21 investigation record (file:lines as of that date); the open
> remainder is the templates-vs-activities authoring question and the
> events/principles projection completion (Askesis arc).

**A shared PathStep pointing at a user-owned activity crosses an ownership
boundary, unscoped end to end.** Verified: `Habit`/`Event` are `UserOwnedEntity`
(OWNER_ONLY); the vault-authored `habit.pause-and-name` and
`event.evening-check-in` both carry `user_uid=user_admin` **and** a
`(user_admin)-[:OWNS]->` edge; the MEGA-QUERY projection has **no owner
predicate** (`user_context_queries.py:829`); `_fetch_entities_by_uid` calls
`service.get(uid)` → `CrudOperationsMixin.get` (`:135`), which takes **no
`user_uid` and performs no ownership check**; and the value is rendered into the
Socratic prompt by `response_generator._build_guided_practice`.

So with that PathStep active for **any learner but the vault owner**, the owner's
user-owned habit lands in that learner's bundle and prompt. ⚠️ **This arc's own
authoring test created the first instance** (low sensitivity — a
curriculum-flavoured title owned by `user_admin` — but the mechanism is the
point, and the events projection would multiply it).

⚠️ **It reframes Way 1 vs Way 2.** Template + spawn exists to give each learner
*their own* instance — exactly the boundary a direct edge violates. Way 2 may be
architecturally right rather than dead.

**✅ RULED (Mike, 2026-08-21) — the vault ROOT decides ownership:**

| vault | meaning |
|---|---|
| `/home/mike/0bsidian/0vault` (`INGESTION_PATH`) | **shared curriculum** |
| `/home/mike/0bsidian/skuel` (`VAULT_ROOT`) | **user-owned** |

So content-vault activities are shared curriculum, and **the `user_uid=user_admin`
+ `:OWNS` stamp on them IS the bug** — not the direct-edge model. Way 2
(templates) is **not** forced; Option A is architecturally sound after all.

⚠️ **Cause — a first draft of this entry got it WRONG, and the wrong version
would have sent the follow-up at an ineffective fix** (Codex, #1112). It blamed
`default_user_uid` falling back to `DEFAULT_USER_UID`. **That is not what decides
the owner in production.** `compose.py:1433-1455` installs a `VaultRegistry`, and
`_resolve_owner` (`unified_ingestion_service.py:351-371`) resolves content-vault
paths to the **content descriptor's acts-as owner** before preparation. The two
vault doors are *already* distinguished; changing `DEFAULT_USER_UID` would change
nothing.

**The ingestion layer already does the right thing.** `_resolve_owner`'s docstring:
*"Only `requires_user_uid` entity types actually persist this owner; **SHARED
curriculum drops it**."* Measured:

| type | `requires_user_uid` |
|---|---|
| `HABIT` / `EVENT` / `PRINCIPLE` | **True** |
| `HABIT_TEMPLATE` / `EVENT_TEMPLATE` / `PATH_STEP` | **False** |

So the owner is persisted **because the entity type demands it** — not because a
default leaked. **The actionable cause is the type choice: a USER_CREATED
activity type is being authored where a curriculum template is required.** Which
is exactly the finding below, arrived at from the other direction.

That makes the P1 a **known-cause bug rather than an open design question** —
tractable, and squarely in the ownership group below.

### 🔑 But the type system already answers this, and its answer is TEMPLATES

Measured 2026-08-21 via `EntityType.<T>.content_origin()`:

| entity | `content_origin` |
|---|---|
| `Habit` / `Event` / `Principle` | **`user_created`** |
| `HabitTemplate` / `EventTemplate` / `PrincipleTemplate` | **`curriculum`** |

So **"a shared curriculum Habit" is not representable — by design.** The
curriculum-side representation of an activity *is* the Template (CLAUDE.md's
tier B). Combined with Mike's ruling that `0vault` is shared curriculum, it
follows that **content-vault activity files are authoring the wrong entity
type**: they should be `HabitTemplate` / `EventTemplate` / `PrincipleTemplate`,
not `Habit` / `Event` / `Principle`.

Which reframes the P1's root cause once more: the direct-edge channels point
**curriculum at user-owned instances** — that is the boundary violation — while
the template channels (`HAS_HABIT_TEMPLATE` → `HabitTemplate`) point curriculum
at curriculum and violate nothing. ⚠️ **Way 2 may be right after all**, for a
type-system reason rather than the ownership one.

⚠️ **And here is the actual gap: neither path is currently usable.**

- The **correct** entity type (Template) is **not vault-ingestible** — no
  reference to any `*Template` class exists under `core/services/ingestion/`
  (verified). It can only be created through the PathStep template routes in the
  app.
- The **authorable** entity type (Activity, via `habit_uids` etc.) is
  user-created and crosses the ownership boundary.

So a content author cannot currently express "this lesson has this practice" in
the vault without authoring a user-owned entity. **That is the design question
for the fresh context** — bigger than the four ownership entries, and upstream of
them.

**The question, in plain terms** (the first framing was too abstract to answer —
Mike said so, fairly). *When you write a lesson in the vault and want to say
"practise this by doing X", what should X be?*

| | X is a **Template** | X is an **Activity** (today's fields) |
|---|---|---|
| what it means | a curriculum-owned *pattern* — "a 2-min evening check-in". On engagement the app spawns **the learner's own copy** | the lesson points at **one real Habit/Event** that belongs to somebody |
| ownership | shared → shared; no boundary crossed | shared → user-owned; **every learner sees the author's item** (the P1) |
| type system | `*Template` is `content_origin=curriculum`, `requires_user_uid=False` ✅ | activities are `user_created`, `requires_user_uid=True` ✗ |
| works today? | **no** — templates are not vault-ingestible at all | yes, and that is how the P1 arose |

**Mike's leaning (2026-08-21): make Templates vault-ingestible** — *"Templates are
a basic part of this app and must be easy to use and understand."* ⚠️ Recorded as
a **leaning, not a ruling**: Mike said the question as first put to him was
unclear, so the fresh context should re-put it using the table above and confirm
before building. The leaning is well-aligned — templates are already the app's
stated model (CLAUDE.md: *"Activity Templates — PS-owned, spawn instances on
engagement"*) — but it implies real work: a new vault ingestion path for six
template types.

**✅ Ruled firmly (Mike, 2026-08-21): HOLD the `event_template_uids` → `event_uids`
rename** until this is settled. That rename was ruled on the framing "the
behaviour is right, the label lies". If the answer is Templates, the label was
right and the **target** is wrong — the option that ruling rejected. Do not
rename toward a model we may be leaving.

⚠️ Not established, and worth checking before acting: whether the direct-edge
channels were *intended* for something else (a teacher linking a PathStep to a
real personal habit as an exemplar), which would make them correct-but-misused
rather than wrong.

⚠️ **This is the read-side facet of a question three other entries in this file
already circle** (Mike, 2026-08-21). The root: **ownership is declared in three
places — the `user_uid` property, the `(User)-[:OWNS]->` edge, and DomainConfig's
`SearchVisibility` — and enforced in one**, `build_search_visibility_clause`,
"the one Cypher composition point" (CLAUDE.md § Ownership Scoping). The Askesis
bundle never reaches it: `context_retriever.py` references neither
`SearchVisibility` nor that clause, and reads entities directly through
`service.get()`, bypassing SearchRouter.

The other three facets were entries in this file until their closure record was archived
to `docs/roadmap/done/ownership-bundle.md`; the table below now cites that record.

| facet | where it landed |
|---|---|
| write-side (`:OWNS` writers that skipped `user_uid`) | ✅ RESOLVED — ADR-086 + bundle PR-2 residue collapse: paper channel deleted, attendee triple retargeted onto consent-carrying `ATTENDS`. See `done/ownership-bundle.md` § 1 |
| declaration-side (`GroupService` declared `OWNER_ONLY` on a model with no `user_uid`) | ✅ RESOLVED — bundle PR-4: `DomainConfig.ownership_property`, Group declares `owner_uid`, guard test tightened to the declaration. See `done/ownership-bundle.md` § 3 |
| index-side (`User.uid` had no index or constraint) | ✅ RESOLVED — bundle PR-4: `User_uid_unique` uniqueness constraint via startup DDL, applied live + `NodeUniqueIndexSeek` confirmed. See `done/ownership-bundle.md` § 2 |
| **this P1** | **read-side** — ✅ RESOLVED (ADR-085 G1+G2, bundle PR-3: `_fetch_entities_by_uid` reads through `get_visible_to_user`, and the MEGA-QUERY habit/task projections carry `user_uid = user.uid`) |

**Ruled 2026-08-21 (Mike): this is significant cross-cutting work and belongs to
a fresh context, taken with the other three facets together rather than as four
separate fixes** — which is how the ownership bundle was in fact taken. Whoever
takes it should settle the general question — *what enforces ownership on a read
that does not go through SearchRouter?* — before touching any single site.
⚠️ `CrudOperationsMixin.get` (`:135`) is used by every domain; changing its
signature is a repo-wide change, not a local one.

**✅ That ruling landed — ADR-085 (the read-enforcement contract, bundle PR-1),
and the mechanism is CLOSED (bundle PR-3, 2026-08-21):** two chokepoints, one
floor; `get_visible_to_user` promoted to THE audience-aware by-UID read (now a
`BaseService` method); bare `get()` stays unscoped with §3 legality rules —
`CrudOperationsMixin.get`'s signature was indeed left alone. This entry's two
disclosure paths are both shut: `_fetch_entities_by_uid` threads `user_uid` and
reads through `get_visible_to_user` (G1), and the MEGA-QUERY `practice_habits`/
`practice_tasks` projections re-tie to the anchored user (G2) — the vault-stamped
`user_admin` habit no longer reaches another learner's bundle OR their rich
context. The verdict below is therefore UN-SUSPENDED.

**Verdict — Option A in shape.** Way 2 stays unused; the fix shape is
a `graph_context` projection + a `_fetch_entities_by_uid` call per channel + the
`total_practice_opportunities` fix. ⚠️ `get_practice_events` is a phantom —
populate through the projection, never by giving it a caller. The
events/principles projection completion (the code-gated halves below) stays with
the **Askesis arc**, not the ownership bundle — new channels inherit the G1/G2
scoping by construction (the fetch helper requires `user_uid`; a new projection
copies the owner-predicate shape).

⚠️ **The test does NOT generalize to events — `habit_uids` is the most permissive
of the six channels.** Target labels in the PathStep activity block differ:
`habit_uids`/`choice_uids` → `:Entity` (matches anything — the bar the test
cleared); `task_uids` → `:Task`; `goal_uids` → `:Goal`; `principle_uids` →
`:Principle`; **`event_template_uids` → `:Event`**.

**✅ Event test run 2026-08-21 — the strict target works.** `event_template_uids:
[event.evening-check-in]` on `ps.self-reflection.noticing-patterns` →
`SCHEDULES_EVENT` edge landed, and a `practice_events` projection returns it. So
the mechanism is sound for **both** permissive (`:Entity`) and strict (`:Event`)
targets. Graph now: `BUILDS_HABIT` 1, `SCHEDULES_EVENT` 1.

⚠️ **The hazard survives as a pure NAMING hazard.** `event_template_uids` needs an
**Event instance** uid; an author following the field name to an `EventTemplate`
matches nothing (and `_template_loader.py:64-70` uses a different edge,
`HAS_EVENT_TEMPLATE`). Currently *impossible to hit* — zero `:EventTemplate`
nodes exist — but live the moment one is created via the PathStep template
routes. **Decide before then:** rename the field to `event_uids` (matches
behaviour) or retarget the edge at `EventTemplate` (matches the name, changes
semantics). **⏸️ Mike first ruled *rename to `event_uids`*, then HELD it** once the
type-system finding landed (if the answer is Templates, the label was right and
the target is wrong). See the hold and its resume condition above.

**✅ Principles is TESTED** — `principle_uids` → `GUIDED_BY_PRINCIPLE` landed
against the strict `:Principle` target (2026-08-21). All three target classes are
proven **for the correct-type case**: `:Entity` (habits), `:Event`, `:Principle`.

⚠️ **The WRONG-type case is open, and habits is the one channel exposed to it.**
`BUILDS_HABIT` declares target **`:Entity`** (accepts anything) while the reader
requires **`:Habit`** (`user_context_queries.py:829`) — the only writer/reader
disagreement of the four. So `habit_uids: [task.something]` creates an edge that
the projection **silently ignores**, and the pre-ingestion validator cannot catch
it because it validates against `:Entity`. SKUEL030 class. That makes the
permissive channel the **riskiest to author**, not the safest. Fix option: declare
`BUILDS_HABIT`'s target as `Habit` — but check first whether permissive was
deliberate.

⚠️ **The two halves are gated on DIFFERENT things — do not lump them as
"content-gated."** Per `PsBundle` channel, after both tests:

| channel | content | projection | bundle fetch | tutor sees it? |
|---|---|---|---|---|
| **habits** | ✅ 1 edge | ✅ exists | ✅ | **yes, end-to-end today** |
| **tasks** | none | ✅ exists | ✅ | needs content only |
| **events** | ✅ 1 edge | ❌ missing | ❌ hardcoded `[]` (`:505`) | **CODE-GATED — build first** |
| **principles** | ✅ 1 edge | ❌ missing | ❌ hardcoded `[]` (`:506`) | **CODE-GATED — same as events** |

**Events is code-gated, not content-gated** — the edge exists and is queryable.
⚠️ But it takes **both** halves: `load_ps_bundle` hardcodes `events = []`
(`context_retriever.py:505`), so the `practice_events` projection *alone* still
yields an empty bundle. Projection + `_fetch_entities_by_uid` are one change;
only together do they make the ENCOURAGING prompt name *"Evening Check-In —
2 min"*. ⚠️ **Principles is now code-gated too** — the principle test authored `GUIDED_BY_PRINCIPLE`, so
it needs the same projection + fetch. Both channels are in the same state; neither waits on content.

⚠️ Snapshot, not a constant. Re-run before acting if much time has passed.

⚠️ **`get_practice_events` is a PHANTOM — do not plan to "give it a caller."**
It, `get_practice_habits` and `get_practice_tasks` are declared on `PsOperations`
and **implemented nowhere**; a protocol-routed call falls through
`UniversalNeo4jBackend.__getattr__` (CRUD aliases only) and raises
`AttributeError`. ⚠️ That `__getattr__` returns `Any`, so mypy sees every
attribute as present — **a clean `x: PsOperations = PsBackend(...)` probe is a
direction check, never an implementation check.**

**Verdict 2026-08-21 — Option A in shape; events half NOT yet closed** (projection +
`_fetch_entities_by_uid` per channel + the `total_*` fix; never a `get_practice_*`
caller). "Delete both halves" is refuted — the path demonstrably works, see the
test below. ⚠️ No PLANNED tier exists for *fields* (`./dev bloat` covers
events/methods/templates), which is why an AST sweep found this and the tooling
did not.

---

## KnowledgePracticed Subscriber (REGISTERED 2026-08-21 — ruled "earns a subscriber")

**Trigger-gated deferral, Mike's ruling.** Offered delete-vs-keep on the
zero-subscriber `KnowledgePracticed` event (published at
`ps_practice_service.py`, path 1), Mike ruled a third way: **it should earn a
subscriber**. Per that ruling this section names the consumer; nothing is
built now.

**The named consumer: review scheduling (spaced repetition).** The staged
`Curriculum` model methods (`needs_review`, `days_until_review_needed` — see
the next section) are the repo's only designed consumer of practice recency,
and the event carries exactly what a scheduler needs (`knowledge_uid`,
`user_uid`, `times_practiced`, `occurred_at`, `practice_context`). When a
review-scheduling surface is built, `KnowledgePracticed` is its live signal —
subscribe there, then delete this section.

**Named cost of deferral:** until then the event is published to nobody — and
today not even published, since path 1 (`CalendarEventCompleted` →
`APPLIES_KNOWLEDGE` edges) has zero live traffic. Zero runtime cost, nonzero
map cost: `./dev bloat` will keep reporting it at the informational tier, and
this section is the recorded judgment call it asks for. ⚠️ `PLANNED_EVENTS` is
NOT the vehicle — it flags *published* classes as `planned-marking-stale`.

| Trigger | Check |
|---------|-------|
| A review-scheduling / spaced-repetition surface is scheduled | `git grep -l "subscribe(KnowledgePracticed"` — empty until wired |

---

## Per-Node Substance Counters — the Unread Arm (REGISTERED 2026-08-21 — ruled "keep staged")

**Registered finding, kept staged by Mike's ruling.** The substance-write-grain
census established: the per-node counter arm (`times_*` ×5 + last-date ×5 on
`Curriculum`) has **zero production readers**. All 8 counter-derived model
methods (`substance_score`, `is_theoretical_only`, `is_well_practiced`,
`needs_more_practice`, `get_substantiation_gaps`, `needs_review`,
`days_until_review_needed`, `get_substantiation_summary` —
`core/models/curriculum.py`) have no production caller; no code reads the
counter fields directly. Every live substance read is the OTHER arm — per-user
channel maps (`calculate_user_substance`, `zpd_backend`, analytics — #1033
switched the last reader deliberately: "the corpus-global figure this metric
deliberately no longer reads").

`git log -S` classification: the methods are **never-wired staged vision**
(present since the initial commit; `knowledge_substance_philosophy.md` is the
spec) — with `substance_score` orphaned from its one production caller by
#1033. Per the discriminator (never-wired → ask), Mike ruled **keep staged**:
the writers keep accruing (37 Kus + 10 PathSteps bear reflected counters; 464
total reflection credits vs 28 surviving edges — entries deleted by vault
reconciliation keep their credits) for the day a UI reads them. ⚠️ `./dev
bloat` does NOT cover model methods — this section is the visibility.

**Also parked here, same arm:** retroactive credit. A Ku composed into a
PathStep *after* accruing counters never back-credits the new composer (19
orphaned Kus currently hold counters nothing can read — the `Ku` model drops
the fields). Any future reader of the counter arm must decide whether stranded
orphan-Ku substance back-fills on composition or starts at zero.

| Trigger | Check |
|---------|-------|
| A substantiation UI/surface is scheduled (gaps, needs-review, well-practiced badges) | `git grep -n "get_substantiation_gaps\|is_well_practiced" -- "ui/" "adapters/inbound/"` — empty until wired |

---

## R4 Vault Inbound Propagation — Parked Build (REGISTERED 2026-08-24, ruled 2026-08-23)

**Never-wired verdict, then a parking ruling.** The `git log --all -S` discriminator ran with
multiple probes: the reconciler's inbound half has been `ingest_directory`-only since its first
commit (`b7a1bb3fe`); the only deleted artifact (`find_line_by_vault_id`) was same-day
scaffolding; the CLAUDE.md "completions propagate back" claim landed two days AFTER the
outbound-only code (`5cb1eec12`). The prose was vision, not history. Mike ruled (2026-08-23,
cascade-residue disposition): make the docs honest now — done 2026-08-24 (CLAUDE.md § Obsidian
VaultBridge, ADR-070 status annotation, both user guides) — and park the build here.

**Design sketch, for the day it is scheduled:**

- The `vault_id → entity` lookup the build needs already EXISTS: Guard 2b (#1143) builds
  `existing_vault_ids` per entry in `UserEntryProcessingService` from the same `EXTRACTED_FROM`
  provenance read that feeds Guards 2/3 (`ExtractedByVaultId` in
  `core/services/dsl/activity_extractor.py` carries `entity_uid` + the stored line hash).
- The build is a **status-reconciliation branch beside the extraction guards**: when a 🆔
  line is skipped as already-extracted, compare the PARSED LINE against the ENTITY'S STATE and
  reconcile — covering check (`[x]` + `✅` → complete the task), uncheck (`[ ]` → reopen), and
  edits (title/date changes). ADR-070 Decision 3's LWW-on-`✅` policy is the written conflict
  rule; it has never had a mechanism.
- ⭐ **The change signal must be parsed-line vs entity STATE, never a hash inequality.** The
  hash cannot say WHAT changed — and Guard 2b deliberately REFRESHES the edge hash on every
  moved 🆔 line, so hash inequality is transient by design. This was Codex round-5 P1 on
  #1143, rejected as exactly this parked feature
  (<https://github.com/linguistic76/skuel/pull/1143#issuecomment-5390505718>); the refresh
  forecloses nothing.
- The two historical guard-miss shapes the branch must not regress: Guard 2 misses when the
  hash moved (that miss becomes the reconciliation trigger), and Guard 4 filters to ACTIVE
  twins by design, so it can never catch a completed task.

**Trigger:** Mike schedules it — product decision, not a data threshold.
**Named cost while parked:** vault-side checks, unchecks, and edits of 🆔 lines silently do
not propagate — an edited 🆔 line is skipped + rehashed (#1143's deliberate behaviour: no
duplicate, no update). Tracked tasks must be completed and edited in SKUEL.

---

## Vault Task Door Publishes No Task Events (REGISTERED 2026-08-24)

The direct `type: task` frontmatter ingestion path persists through
`UnifiedIngestionService` → `BulkUpsertBackend.upsert_with_relationships`
(`adapters/persistence/neo4j/bulk_upsert_backend.py`) — no event bus anywhere in that chain. A
task that arrives completed (or is completed by a later re-ingest of its file) through that door
publishes no `TaskCompleted`, so nothing event-driven runs for it — concretely, the
`ProductivityAnalytics.first/last_completion_at` stamps never move: this is the residual root of
the `last_completion_at` staleness that survives #1142 (which derives the COUNT at read but kept
the stamps stored). Don't overstate the gap: checkbox/DSL **extraction**-created tasks go through
the activity services and DO cascade — only the frontmatter bulk-upsert door is silent.

**Trigger:** the R4 build (its reconciliation branch needs the same event honesty) or the next
vault-door touch.
**Named cost:** completion stamps drift stale for vault-frontmatter-authored completions; any
reader of first/last completion stamps under-reports that door's activity.

---

## Line Deletions Leave `EXTRACTED_FROM` Edges (REGISTERED 2026-08-24)

Deletion propagation is FILE-level (entity file deleted → entity deleted). Deleting a task LINE
from a note that still exists leaves the `EXTRACTED_FROM` edge (and its hash) behind. Observed
live in the #1143 read-only census (2026-08-23): 5 🆔-bearing edges point into
`Weekly/2026-W28.md`, whose file holds no checkbox line at all; edge ids in that PR's thread.
(The same census's other 43 hash-orphan edges are bridge/DSL prose entities that never had a
physical line — expected, and any fix must leave those alone.)

**Candidate fix:** retire the edge (or blank its hash) when a sync finds the line gone from its
file — scoped to edges that ever had a physical line (`vault_id`-bearing).
**Trigger:** the R4 build (a reconciliation branch needs honest provenance) or the next
reconciler touch.
**Named cost:** dead provenance rows feed the extraction guards' read on every future sync of
the entry, forever.

---

## `UserLearningIntelligence` Write-Only Fields (REGISTERED 2026-08-28 — ruling needed)

`core/models/user/user_intelligence.py` lost its uid-sniffing "by domain" grouping and the
dead `EnhancedUserContext` that consumed it (never-sniff, ADR-013). What survives is read in
exactly two places: `PsAdaptiveService` reads `current_masteries` and calls
`get_dominant_learning_velocity()`. Every other field the loader
(`PsAdaptiveService._load_user_intelligence` / `_create_default_intelligence`) fills —
`active_learning_paths`, `completed_learning_paths`, `learning_preferences`,
`knowledge_recommendations`, `recent_search_queries`, `search_interests`,
`search_intent_patterns`, the three transfer lists, `intelligence_sources`,
`last_intelligence_update`, `intelligence_confidence` (and the `IntelligenceSource` enum that
only feeds one of them) — is written and never read. Their sources are gone (the search
archive and the `:LearningPreference` node were deleted earlier; the loader hard-codes
empties), so this is hollow shape, not staged foundation.

**Named work:** trim the dataclass to `user_uid` + `current_masteries` + the velocity reading;
drop the two LP queries the loader runs only to fill the unread path fields
(`_query_active_learning_paths` / `_query_completed_learning_paths` — check for other callers
first) and the `IntelligenceSource` enum; adjust the test factory. Or name a consumer.
**Trigger:** the owner's ruling, or the next touch of `PsAdaptiveService`.
**Named cost while parked:** two graph queries per adaptive-path call whose results nothing
reads; a dataclass that advertises intelligence it does not hold.

---

## Habit Streak Counters — Lost-Update Race + Future-Day Credit (REGISTERED 2026-08-24)

Two named defects in the same write family, deliberately scoped OUT of the conditional-write arc
(numeric counters, not status transitions — a different bug class):

1. **Lost update.** Both streak writers are read-then-write: the inline CALCULATE STREAK block
   in `habits_progress_service.py` (`complete_habit_with_quality`) and `_calculate_new_streak`
   in `habits_completion_service.py` read `current_streak`/`last_completed`, compute in Python,
   and write back (`total_completions` rides the same shape). Two concurrent completions can
   drop an increment.
2. **Future-day credit — ruling needed on semantics.** Completing a FUTURE habit occurrence is
   legitimate by ruling (2026-08-23): the write doors carry no upper bound and must not gain
   one. But both writers advance `last_completed` to the completed day and increment on
   `days_since == 1`, so completing tomorrow, then the day after — in one sitting — grows
   `current_streak` without bound and freezes the inflation into `best_streak` permanently (for
   a daily habit with no recurrence end, every future day is an occurrence day). Not a
   mechanical fix: it is a question of what `current_streak` MEANS. Candidate: consecutive
   completed days ending at *today*, with future completions stored and shown but not advancing
   the streak until their day arrives. The provenance-bearing
   `HabitStreakBroken`/`HabitStreakMilestone` events publish whatever number the writer
   computed, so milestones inherit the inflation.

**Trigger:** next substantive touch of the streak write path, or a lived wrong-streak report.
**Named cost:** inflated or lost streaks and milestones; `best_streak` never heals.

---

## Unwired `HabitCompletion` Model Methods — Wrong the Day They're Wired (REGISTERED 2026-08-24)

Four methods on `core/models/habit/completion.py` have ZERO production consumers —
`was_completed_today`, `days_since_completion`, `is_streak_eligible`,
`contributes_to_consistency`. `git grep` finds only `tests/unit/models/test_habit_completion.py`
(the `days_since_completion` hit in `habit_event_handler_service.py` is an unrelated same-named
parameter). Under the future-completion ruling (2026-08-23) each would be wrong the day anyone
wires it: `days_since_completion` returns a NEGATIVE for a future completion;
`is_streak_eligible`'s recency gate (`days_since_completion() > 1`) never fires for a future
completion (negative days), so it OVER-accepts — the completion passes straight to the
quality/duplicate-day checks; `was_completed_today` is false for it; `contributes_to_consistency("weekly")`'s
`week_start <= d <= today` excludes a future day inside the current week.

⚠️ **Wiring caveat:** a never-called method's edge cases were never tested — wiring one CHANGES
its meaning from staged prose to live rule. Wiring is a semantics decision (what a
not-yet-happened completion means for that reader), not a hookup; audit each against the ruling
first. `./dev bloat` does not cover model methods — this section is the visibility.

**Trigger:** a consumer wants one of these, or the next Habits model touch (then: wire
corrected, or delete — never-wired → ask, per the docs-hold-vision discriminator).
**Named cost:** dormant wrong logic that looks ready-made.

---

## `find_by` Datetime String-Binding — Three Habit Sites (REGISTERED 2026-08-24 — one PR)

#1140 established the bug class (Pattern 10b / Key Rule 18b in
`.claude/skills/neo4j-cypher-patterns/PATTERNS.md`): `find_by(field__gte/__lte=<datetime>)` is a
Cypher range predicate whose bound is stringified by `convert_value_for_neo4j`, so a
natively-typed stored value falls outside every range — silently. #1140 fixed only the
consistency score's own fetch; three pre-existing sites remain, all in
`core/services/habits/habits_completion_service.py` and each ⚠-marked in the
`get_completions_for_habit` docstring:

- `get_completions_for_habit(start_date/end_date)` — feeds the streak backfill
  (`_completed_days_window`) and the calendar day read;
- `get_today_completions` via `_all_completions` (`completed_at__gte/__lte`);
- `export_completion_history` (CSV/JSON export, same range).

**Fix as ONE PR:** a normalized range query on a backend method —
`date(left(toString(x), 10)) >= date($iso)` on both sides (Codex's original suggestion on
#1140), replacing all three `find_by` reads.
**Trigger:** next touch of any of the three reads, or a second `completed_at` writer shape
appears (today's single writer persists ISO strings, so the hazard is latent, not live).
**Named cost:** a natively-typed `completed_at` row vanishes from streak backfill, calendar day
reads, today view, and exports — a confident wrong answer, not an error.

---

## Habit-Completion Persistence Bundle — Orphans, UID Collisions, Non-Atomic Day Uniqueness (REGISTERED 2026-08-28)

Codex's "future care session" on #915 (calendar act-from arc PR 3 —
[`done/calendar-act-from-arc.md`](done/calendar-act-from-arc.md)): five findings accepted as real
and deferred there because each belongs to the `HabitCompletion` **persistence layer**
(`core/services/habits/habits_completion_service.py` + the plain
`UniversalNeo4jBackend[HabitCompletion]` in `services_bootstrap/_backends.py`), not to the
calendar surface that PR was building. Until this section they lived only in that PR's body and
two consideration notes. Re-verified against the code and the live graph 2026-08-28; a sixth
(untrack) surfaced in this section's own review (#1172).

1. **A habit delete orphans its completions.** Both production delete doors are `DETACH DELETE`:
   the API route (`CRUDRouteFactory`'s `delete`, wired for every Activity Domain by
   `create_activity_domain_route_config`) calls `delete_for_user(uid, user_uid, cascade=True)`,
   which goes straight to `backend.delete(cascade=True)`; the vault reconciler
   (`IngestionTracker._execute_deletion_plan` → `IngestionBackend.delete_entities_with_metadata`,
   `DETACH DELETE` leaf-first) has no non-cascading variant at all. (`HabitsCoreService.delete` defaults
   to `cascade=False` and no production caller passes `True` — irrelevant, because neither door
   goes through it, and a plain `DELETE` could not succeed anyway: every habit carries its `:OWNS`
   edge.) A completion is tied
   to its habit by the `habit_uid` *property* only — its one edge is
   `(User)-[:OWNS]->(:HabitCompletion)` (`_create_node`, per the model's field docstring). But the
   edge is not the point: `DETACH DELETE` removes the habit and its relationships and never touches
   a neighbouring node, so an edge would not help either. **Requirement:** both delete doors
   explicitly `MATCH` and delete the habit's `HabitCompletion` nodes in the same deletion statement
   (the habit-specific backend delete and `delete_entities_with_metadata`'s Habit shape) — a
   bundle closed without that still orphans. Today the rows stay: unreachable from any habit read, still counted by every
   user-scoped `OWNS` aggregate (`activity_backends.py:413` high-quality count,
   `cross_domain_backend.py`'s consistency window). Both writers orphan identically; #915's own
   acceptance run swept its residue by hand.
2. **The completion uid is second-granularity and unconstrained.**
   `hc.{user_uid}.{habit_uid}.{int(now.timestamp())}` (`record_completion`, `:133`); the bulk door
   keys on the request's `completed_at` (`:265`), which defaults to `datetime.now()` per request
   and which its one production caller (`habits_api.py`, the bulk route) never passes — so bulk
   collides on the same second exactly as the single door does — and deterministically in one case
   reachable today: `BulkCompleteHabitsRequest.habit_uids` (`min_length=1`, no uniqueness check)
   accepts the same habit twice and the loop shares one `now`, so `["habit.x", "habit.x"]` mints
   one uid twice and increments the habit twice. The repair rejects a duplicated list at the
   boundary. Nothing enforces uniqueness:
   the model declares no `field(metadata={"index": ...})`; of the five startup sync routines in
   `services_bootstrap/compose.py` (`sync_auth_indexes` / `sync_vector_indexes` /
   `sync_domain_indexes` / `sync_fulltext_indexes` / `sync_conversation_indexes`) none names the
   label, and the `:Entity` uid uniqueness constraint `sync_domain_indexes` creates cannot reach it
   because its backend is built without `base_label=NeoLabel.ENTITY`; live AuraDB
   `SHOW CONSTRAINTS` (2026-08-28) lists 7 constraints, **none on `HabitCompletion`** (no index
   either). The eventual constraint belongs in `sync_domain_indexes`, alongside the per-label uid
   indexes it already owns — **behind a preflight**: Neo4j refuses to create a uniqueness
   constraint over a label that already violates it, and this work is triggered by lived use, i.e.
   after today's writers may have minted duplicates; a dedupe/migration (or an explicit
   duplicate-count preflight that fails the repair, not the boot) has to run before the constraint
   is enabled, or the repaired build cannot bootstrap. #915 live-verified three same-second
   writes → three nodes sharing one uid. The `hc.` spelling is registered nowhere else (no prefix validation knows it);
   the ratified separator grammar spells generated UIDs with `_` — settle the spelling when the key
   is redesigned, not before.
3. **Day idempotency is a read-before-write guard, not an invariant.** `record_habit_occurrence`
   (`calendar_service.py:1219-1224`) reads that day's completions and returns the existing one; two
   concurrent requests (two tabs) both pass the read and each create a node and increment the
   stats. The habits-surface door (`/api/habits/track` → `record_completion`) has **no** day guard
   at all. The `(habit_uid, day)` invariant has to live in persistence — the same redesign as
   defect 2 (a day-keyed uid + uniqueness constraint + upsert-on-create makes the double-tap a
   database-level no-op — **for the whole statement, not just the node**: the habit patch and every
   completion side effect must sit on the `ON CREATE` path, and the match path returns the
   already-recorded completion without incrementing or publishing anything; a `MERGE` that no-ops
   the node and still patches the counters double-counts the exact double-tap this exists to
   stop). ⚠ **Ruling needed first:** is one completion per habit-day the contract?
   Only the calendar door enforces it today; `record_completion` never said; and the streak readers
   are NOT evidence either way — `_completed_days_window` deliberately collapses rows to a set of
   days, so several completions on one day stay valid records that contribute one streak day.
   The ruling is a product decision, not an inference from the code. A multi-per-day habit would
   want a different key.
4. **A transient stats-write failure strands the node behind a later "success".** Write order is
   compute → `completions_backend.create` → `habits_backend.update` (`:162`). If the update fails
   after the create landed, the node exists with `total_completions` / streaks / `last_completed`
   stale, and a calendar retry is intercepted by defect 3's existing-day return — reported success,
   no repair (the `record_completion` docstring names this "the residual window"). The bulk door
   is worse: `_record_completion_no_event` (`:311`) **discards** the stats update's `Result`, so
   `/api/habits/bulk-complete` counts the completion and publishes `HabitCompletionBulk` on the
   spot even when the stats write failed — no retry is even attempted. And the bulk loop appends
   only `is_ok` results and always returns `Result.ok`, so `/api/habits/bulk-complete` answers 201
   on partial failure: atomicity alone does not close this writer — per-item failures must
   propagate or be reported. ⚠ The one-line
   "propagate the error" is NOT the fix there: the node is already stored, so propagating drops an
   existing completion from the response and the event — the same strand in a different coat.
   Only the atomicity work below closes either writer. Fix shapes: one
   Cypher statement that creates the node and patches the habit — the primary shape. It closes the
   streak lost-update race above **only if the statement derives the counters from the node's
   state after taking the write lock** (ADR-087's shape: lock, read prior, patch in the same
   statement); a Python-computed absolute `N+1` serialized twice is still `N+1`. Derivation is an
   alternative only if it covers
   **every** field the patch writes — `total_completions`, `current_streak`, `best_streak`,
   `last_completed`, `identity_votes_cast` — plus the milestone events keyed off them; deriving the
   tally alone (the direction `cross_domain_backend.py`'s consistency window took because the bulk
   door's nodes are invisible to the tally) heals one field of five and leaves the rest of this
   defect open.
5. **The streak backfill wants a DISTINCT-day query.** `_completed_days_window` (`:372-390`)
   fetches raw rows (`limit=max(1000, days*2)`) and dedupes to days in Python; ≥3 same-day
   duplicates sustained across a >1000-row window starve it and `best_streak` under-reports;
   `current_streak` is protected by the `max(run, habit.current_streak)` guard only down to the
   *cached* value — a backfill that extends the current run at its oldest end under the same
   starvation reads N instead of N+1. Both directions are conservative (never over-report); the
   repair's test must cover both. Fix: a backend operation
   returning **distinct `date(completed_at)`** in a range, for the streak reads only. It is NOT the
   `find_by` row's replacement — those three reads (`get_completions_for_habit`,
   `get_today_completions`, `export_completion_history`) need whole `HabitCompletion` records and
   deliberately keep same-day duplicates. What the two share is the **normalized range
   predicate** (`date(left(toString(x), 10))` on both sides): two operations, one predicate, one
   PR.
6. **Untrack cannot delete, says it did, and would not recompute if it could.** `untrack_habit`
   (`_completion_mixin.py:88`, `POST /api/habits/untrack`) deletes each of the day's completions
   with `completions_backend.delete(uid)` — default `cascade=False`, the plain `DELETE` the mixin
   documents as "will fail if entity has any relationships" — and every completion has carried its
   `(User)-[:OWNS]->` edge since #1100, so the delete has been refused on every call since then;
   the loop **discards** each `Result`, so the route answers `{"removed": true}` regardless. No
   test covers the door. Had it deleted, nothing recomputes `total_completions` / `current_streak`
   / `best_streak` / `last_completed` / `identity_votes_cast` / `success_rate` (an untrack inside
   the trailing consistency window changes its numerator) — cached stats diverge from the node set
   exactly as in defect 4, in the other direction. Requirement: one atomic
   delete-and-recompute (the inverse of defect 4's create-and-patch, the same single-statement
   shape), `cascade=True`, errors propagated — **and an inverse event with explicit subscriber
   semantics** (name it at build time; a new `core/events` module must be imported in
   `core/events/__init__.py`): the user-context cache must invalidate, linked-goal progress that
   `GoalsProgressService.handle_habit_completed` advanced must recompute, and once the shared
   writer emits `HabitCompleted` its analytics / timing-learning subscribers must be told the
   completion is gone, or every one of them keeps the removed completion. Two node writes are not
   the whole inverse. Found by Codex on #1172, not on #915.

⚠ **A third writer creates no node at all.** `POST /api/context/habit/complete` →
`UserContextService.complete_habit_with_context` →
`HabitsProgressService.complete_habit_with_quality` increments `total_completions`, advances
`current_streak` / `best_streak` / `last_completed` via `backend.update_habit`, is the ONLY
completion path that recalculates and persists **`success_rate`** (the consistency value habit
enrichment, AI, pattern and scheduling readers consume — `record_completion` never touches it),
and publishes `HabitCompleted` — without ever creating a `HabitCompletion`. Every node-derived
shape above
(derived stats, untrack's recompute, the `(habit_uid, day)` invariant) would erase or bypass that
door's contribution. The redesign migrates it onto the completion-node path — **one shared,
lock-derived persistence operation behind all four production doors**: `/api/habits/track`
(`record_completion`), the calendar (`record_habit_occurrence` → the same), `/api/habits/bulk-complete`
(`_record_completion_no_event`, with explicit bulk response/event semantics — today it has UID
collisions, discarded update failures, partial success and non-canonical events of its own), and
`/api/context/habit/complete` — carrying `success_rate` into the shared operation, **derived and
persisted inside the same locked statement** (or derived at read time), never as post-commit
work: a recalculation that runs after the node commits recreates defect 4's stranded window and
lets concurrent completions overwrite each other's rate; the same holds for untrack's inverse —
or deletes the door; a ruling taken at build time, not a default.
A redesign that leaves bulk on its own helper closes the bundle with a defective path still
open. **And routing future calls is not enough:** every contextual completion made before the
migration exists only in `Habit.total_completions`, the streak fields and already-published
events — a node-derived `success_rate` or untrack recompute would erase that history, and the
tally-vs-node trigger below only *detects* the condition. The bundle carries a historical
baseline/reconciliation step before any node-derived write is enabled (seed the pre-migration
tally as a baseline, or backfill it as nodes — a ruling), unless it lands before the first
contextual completion. (Its own
read-then-write streak block is already the *Habit Streak Counters* row's first item.)

⚠ **And the event asymmetry runs the other way.** That node-less door is today the ONLY
publisher of `HabitCompleted` (`habits_progress_service.py:298` — the only `HabitCompleted(`
left in the tree since the `core/events/habit_events.py` usage-example fiction, which cited a
`log_completion` that never existed, was deleted 2026-08-28). `record_completion` publishes
`HabitStreakMilestone` only, so the two
node-writing doors (`/api/habits/track`, calendar) reach none of the four wired subscribers —
`GoalsProgressService.handle_habit_completed` (goal progress),
`CrossDomainAnalyticsService.handle_habit_completed`,
`HabitEventHandlerService.handle_habit_completed`, and `MetricsEventHandler._on_habit_completed`
(the Prometheus `entities_completed{entity_type="habit"}` counter — completion telemetry is blind
to them too) — nor the user-context cache invalidation keyed on it. The same holds for `HabitStreakBroken`: `_calculate_new_streak` resets the streak after a
gap, but `record_completion` publishes only `HabitStreakMilestone` (`_check_streak_milestones`), so
the wired `HabitEventHandlerService` subscription never hears a tracked or calendar break —
`complete_habit_with_quality` (`:309`) is again the only real publisher — the second
constructor was in that same deleted example block. A live gap on the node doors now, not only
a consolidation
hazard: the shared committed writer must carry the canonical `HabitCompleted` and
`HabitStreakBroken` and the contextual side effects with it, or the merge silently disconnects
goal progress and streak recovery from every completion. **With explicit completion-time
semantics:** `BaseEvent.occurred_at` defaults to `datetime.now()`, and two subscribers read it
directly — `CrossDomainAnalyticsService.handle_habit_completed` persists it,
`HabitEventHandlerService.handle_habit_completed` learns the completion hour from it — so a
canonical event published as-is stamps a backfilled or future occurrence as completed *now* and
trains scheduling on the request hour (and setting `occurred_at` to the date-only midnight trains
an artificial hour instead). The shared writer's event carries the occurrence's own
`completed_at`, and a date-only backfill is excluded from the **whole timing sample** — not the
hour histogram alone: `HabitCompleted.completed_on_time` defaults to `True` and the same handler
feeds it into `learned_on_time_rate`, so an unknown-time completion left on the default is
counted as known-on-time and inflates the EMA and its sample count — defined, not defaulted.
And a **future-dated** completion (legitimate by the 2026-08-23 ruling — see the *Habit Streak
Counters* row) is stored but must not feed behaviour that has not happened yet into downstream
state: published as-is, `CrossDomainAnalyticsService.handle_habit_completed` would pass the
future timestamp into `_upsert_counter_analytics` (a permanently future `first_completion_at`)
and the handler would learn its hour and on-time sample. Its side effects are deferred or
excluded until its occurrence day arrives — the same decision as that row's `current_streak`
semantics, taken once.

**Not covered by the three Habit rows above, deliberately:** *Habit Streak Counters* is the HABIT
node's counters (read-then-write; what `current_streak` means); *Unwired `HabitCompletion` Model
Methods* is dormant model code; *`find_by` Datetime String-Binding* is the read-side range
predicate. This bundle is the completion node's **identity and lifecycle** and the atomicity
between the two backends. The overlaps are fix-sharing, not scope-sharing: a single-statement
lock-derived create+patch (4) closes the streak lost-update too; the DISTINCT-day operation (5)
rides the same normalized range predicate as the `find_by` row's fix.

**Trigger:** lived habit-completion use — live graph 2026-08-28: **0 `HabitCompletion` nodes**
across 5 habits, and the node-less door's footprint is zero too (`sum(h.total_completions)` 0, no
`last_completed`, `max(current_streak)` 0); the machinery has never been exercised outside #915's
swept acceptance run. ⚠ The node count alone cannot see the `/api/context` door — a habit tally
above the node count is that door's signature (`get_habit_analytics` already counts nodes only),
so the check reads both. Or
the next touch of the completion write path (`record_completion` / `_record_completion_no_event` /
`record_habit_occurrence` / `untrack_habit` / `complete_habit_with_quality`). Defect 5 is built in
the `find_by` row's PR (same predicate, distinct operations) but has its own trigger: duplicate
volume — ≥3 same-day rows sustained across a >1000-row window — which defect 3's `(habit_uid, day)`
invariant makes impossible once it lands; one natively-typed row fires the `find_by` row and says
nothing about this one. Defect 3's ruling is
Mike's, taken at build time, not in passing.
**Named cost:** orphaned completion rows after a habit delete (invisible to habit reads, counted
by user aggregates); a same-second double-tap on either door — or one bulk request naming a
habit twice — mints nodes sharing one uid; a two-tab double-complete double-counts stats; a transient stats-write failure
leaves totals permanently stale behind a "success"; a dup-heavy history under-reports
`best_streak`; an untrack answers `removed: true` having removed nothing; a tracked or calendar
completion advances no goal progress, invalidates no context cache, and reports no broken streak
(no `HabitCompleted`, no `HabitStreakBroken`).
Today every one of these costs nothing, because nothing has been written.

---

## `TaskUpdateRequest` Future `completion_date` — Create/Update Asymmetry (REGISTERED 2026-08-24 — ruling needed)

`TaskCreateRequest` refuses a future `completion_date` ("semantically impossible and would pin
itself atop completion-date-ordered reads" — `core/models/task/task_request.py`,
`default_completion_date_when_completed`); `TaskUpdateRequest.to_intent()` passes one straight
through as a patch. The 2026-08-23 future-completion ruling was about HABITS — future habit
occurrences are legitimate — and does not extend to Tasks; the create-vs-update asymmetry inside
Tasks is UNRULED. The decision (Mike's): refuse future on update too (symmetry with create), or
allow on both and bound the readers (the habits precedent). The two windowed readers are already
bounded either way (#1139/#1142).

**Trigger:** ruling — take it to Mike on the next touch of `task_request.py`'s validators; do
not rule it in passing.
**Named cost:** until ruled, an update can plant the future-dated stamp the create door exists
to refuse, pinning itself atop completion-date-ordered reads.

---

## "Vault Has Un-Synced Changes" Signal (REGISTERED 2026-08-24 — Mike schedules it)

The honest version of the dirty flag the reopen arc once proposed. A reopen now reaches the vault
on the next sync, but *the user is not told a sync is worth running*. The naive fix — light a flag
when a task is reopened — **tells a half-truth**: a completion, a minted 🆔 and a newly-extracted
task all leave the vault equally out of date, and a flag lit only by reopens would advertise the
rarest of the four while staying dark for the common ones. Whatever is built must cover all of
them, or it is worse than nothing.

**What exists to build on:**

- **No last-sync state is persisted anywhere today.** `/submissions/sync` is stateless on load
  (`adapters/inbound/vault_routes.py`) — the page cannot say "last synced 3 days ago" because
  nothing records it. That is the first thing any signal needs, and it does not exist yet.
- `UserPreferences.vault_write_consent` (`core/models/user/user.py`) is the **shape precedent**
  for a durable per-user vault flag.
- `:Notification` nodes (`core/services/notifications/notification_service.py`) are the existing
  durable per-user channel, already driven by four subscribers in
  `services_bootstrap/_event_wiring.py` — the one place a "your vault is behind" signal could live
  without inventing a mechanism.

**⚠️ The trap this replaces:** *"`TaskReopened` requests a sync"* was under-specified, and
investigating "what does the subscriber concretely DO?" is what dissolved it. Do not build a
signal without naming its verb and its actor first.

**Trigger:** Mike schedules it — a product decision about what the user should be told, not a
data threshold.
**Named cost until built:** the vault silently drifts from the graph between human-initiated
syncs, and nothing on any surface says so.


---

## Per-Domain Chunking Knobs + Chunk-Type-Aware Retrieval (REGISTERED 2026-08-28 · re-measured + fragment fix DONE 2026-08-30 · intent filter measured INERT + RULED 2026-08-30 · baseline RATIFIED 2026-08-30)

The chunking-params foundation shipped in #560 (2026-07-08): `ChunkingParams` on
`EntityIngestionConfig` (`core/services/ingestion/config.py`), every domain on
`DEFAULT_CHUNKING_PARAMS` (min 50 / max 500 words / context 100), `REFERENCE_CHUNKING_PARAMS`
(100/1000/150) for canon books, per-domain re-chunk via `regenerate_chunks(force=False)`
(`core/services/chunks/batch_chunking_service.py:101`). Two forward threads were recorded only in
memory: (1) **tune the knobs — "measure first"** (Mike's ruling), with the measurement never named;
(2) **chunk-type-aware retrieval** — chunks carry `chunk_type` (`ContentChunkType`, nine members:
definition / explanation / example / exercise / code / summary / section / introduction /
conclusion) but `_augment_with_body_chunks`
(`core/orchestrator/search_router.py:1120`) is type-blind. The sketch: a `chunk_type_weights`
table on `VectorSearchConfig` (`core/config/unified_config.py:142`, beside
`body_chunk_search_min_score = 0.68`), score = `vector_score × type_weight`, flat table first,
query-intent-conditioned later (ADR-034 Phase 2). `git grep chunk_type_weights` → 0 hits.

**Measured 2026-08-28 (AuraDB `d2d160c4`); re-measured 2026-08-30 unchanged, then acted on (Named work 1):** 998 `:ContentChunk`, all `chunking_version = 'v1'`,
all under `(:Content)-[:HAS_CHUNK]->`. By type: explanation **788**, exercise 142, definition 62,
example 3, summary 3; `code`, `section`, `introduction`, `conclusion` — 0 today. **By parent: path_step 386 chunks (21 parents), ku 309 (30),
user_entry 303 (15)** — the index is 30% personal-vault knowledge notes (canon P3), not
curriculum alone. In WORDS — the
unit the knobs are in, read from the persisted whitespace-aware count (`ContentChunk.word_count`
= `len(text.split())`, stored as `c.end_index` by `neo4j_content_adapter.py:193` — the name is
the adapter's, not a span): median **27**, p25 13, p90 75, max 496. **753 of 998 (75%) sit
below the configured `min_chunk_size` of 50** — the floor is
inert, never enforced (`core/services/ingestion/reference_ingestion.py:127` says so; #560
recorded 0 strategy references), and its default is above the corpus median. **83 chunks were
under 5 words — 75 of them `user_entry`** (`---` rules, bare `-` markers, link-only and
label-only lines; 72 typed `explanation`; 32 under 20 characters), 6 path_step (one was
`**5-4-3-2-1:**`), 2 ku; none exceeded the 500-word `max_chunk_size` (max 496 — the naive `split` had counted 2 over by counting empty tokens). 41 `:SearchEvent` in total, flat since 2026-07-22.

**What the numbers say (revised 2026-08-30).**
- **The type split is a classifier artifact, not a corpus fact.** `_detect_chunk_type`
  (`core/models/ps_content/content_chunks.py`) is a keyword heuristic whose FALLBACK is
  `EXPLANATION` — 79% means "no keyword matched" (and its `startswith(("a ", "an ", …))` →
  DEFINITION rule is over-broad). The distribution will NOT flatten from content growth; only a
  classifier that types by content changes it. A weight table built on it would re-rank a
  fallback label and look like it worked.
- **Chunk-type-aware retrieval exists on the Askesis path as a HARD filter — and has NEVER RUN.**
  `_INTENT_CHUNK_TYPES` (`core/services/askesis/context_retriever.py`) →
  `retrieve_scoped_chunks(chunk_types=)` → `chunk.chunk_type IN $chunk_types`. Re-measured on the
  925-chunk v2 corpus (2026-08-30): EXPLORATORY **66 of 925** (7.1%) — of which `introduction`,
  one of its three named types, matches **zero rows**; PRACTICE 137 (14.8%); the other mapped
  intents 786 (85.0%). The v2 re-chunk moved none of it (was 65/145/850 of 998), as predicted.
  ⚠ **EXPLORATORY's mapping may be answering the wrong question entirely.** Its
  `INTENT_EXEMPLARS` describe *catalog browsing* ("Show me what's available", "Browse available
  knowledge"), while `INTRODUCTION`/`SUMMARY`/`DEFINITION` chunks answer *topic orientation*
  ("introduce me to stoicism") — two intents under one name. PR-1 of
  [askesis-intent-classification-activation.md](askesis-intent-classification-activation.md)
  decides which it is; if it lands on browsing, this mapping is wrong on its own terms and the
  7.1% is beside the point.
  **But those are counterfactuals.** Driving the production path (`./dev eval-askesis-draw`)
  showed all 23 queries classify to **SPECIFIC**, which is unmapped → `chunk_types=None` → no
  filter. The cause was one layer up and was not a tuning miss: classification needed
  `IntelligenceThreshold.INTENT_CLASSIFICATION` = **0.65** *average* cosine similarity across an
  intent's **8** exemplars. Averaging over 8 diverse short sentences is a far stricter gate than
  it reads: the 23 eval queries scored **0.078–0.291**, and a query that IS one of the exemplars,
  verbatim, still only reached **0.43–0.56** against its own intent (practice 0.562,
  hierarchical 0.561, relationship 0.561, aggregation 0.482, prerequisite 0.480, exploratory
  0.429). Nothing could clear it, so `classify_intent` could only ever return SPECIFIC — the
  starvation was real arithmetic with zero production effect.
  ⚠ **STATE CHANGE (PR-2, 2026-08-31): the gate is 0.35 and queries DO classify to mapped
  intents — the filter stays off by a DIFFERENT mechanism.** `retrieve_relevant_context` now
  hard-wires `chunk_types=None` at the call site instead of deriving it from the intent: the
  map is explicitly disconnected (greppable), no longer shadowed by an unreachable gate. See
  Named work 4, now a RULING.
- **The fragments were an ingestion-hygiene defect, 90% in vault notes** — `/search` never showed
  them (`_aggregate_body_chunk_parents` drops non-Ku/PS parents); they only crowded the vector
  candidate pool and Askesis draws. "Enforce `min_chunk_size`" as configured would have folded
  three-quarters of the corpus — that IS the blind tuning Mike ruled against, so the floor's
  VALUE stays with the measured thread below.
- **Ride-along, found by this re-measure:** Askesis chunk retrieval was owner-UNSCOPED over that
  30% vault-note share — closed the same day as ADR-085 **G8** (#1195).

**Named work:**
1. ✅ **Sub-sentence fragments — DONE 2026-08-30 (#1196 + live re-chunk).** Chunking algorithm
   **v2**: `FRAGMENT_FLOOR_WORDS = 5` (`content_chunks.py`), re-based from the corpus median,
   deliberately NOT the 50-word knob. Thematic breaks and bare list markers are dropped; any
   other sub-5-word prose fragment folds into a prose neighbour (never into a code fence; a
   merged chunk re-types from its final text; a section made only of fragments joins into ONE
   chunk — the designed residual). Live run: `regenerate_chunks(force=False)` 66/66 parents,
   998 → **925** chunks all `v2`, fragments 83 → **7** (every survivor a link-only MOC-style
   note with nothing to fold into — a content property, not a splitter defect), embedding
   `NULL` = 0 after the worker drain, median 27 → 30 words.
2. **Knob tuning — instrument SHIPPED 2026-08-30 (eval arc PR-1), baseline RATIFIED
   2026-08-30:** `scripts/eval_chunk_retrieval.py` (`./dev eval-chunk-retrieval`) scores
   hit@5 over the reviewable query set `scripts/eval_chunk_retrieval_queries.yaml`
   (23 queries with expected Ku/PathStep hits) through the SEARCH path that retrieves
   chunks — `SearchRouter.faceted_search` with semantic boost, the sole caller of
   `_augment_with_body_chunks` (`log_event=False`, so eval runs never write
   :SearchEvent telemetry); `advanced_search`
   searches parent entities and never touches a `ContentChunk`, so a baseline run through it
   would be blind to every knob here (Askesis reaches chunks separately via
   `retrieve_scoped_chunks` — the knobs move that too, and it is audience-scoped since ADR-085 G8 (#1195) — but the eval targets search). Mike ratifies the query→expected-hit pairs
   (the set's `ratified:` field carries the date); the first RATIFIED run IS the baseline.
   **BASELINE (v2, ratified 2026-08-30, AuraDB `d2d160c4`, 925-chunk v2 corpus): hit@5 =
   23/23 = 1.00, 18 via the body fold, 0 errors; best_rank 1×19 / 2×3 / 3×1, mean 1.22.**
   ⚠ **The headline metric is SATURATED and can only detect regression, not improvement.**
   It reads 1.00 because the v2 widening admitted the Kus the two `real_usage` rows were
   already returning — not because retrieval changed (the 21/23 draft ran on the same
   corpus and the same code). A knob change that improves ordering cannot show up in
   hit@5, so **tuning is judged on `best_rank` and `expected_missing`**, which are in the
   `--json` rows and are NOT saturated. The one live residual: for the bare query `body`
   the fold contributes **0 chunk candidates** (nothing clears
   `body_chunk_search_min_score = 0.68`; corpus best 0.651) and both expected PathSteps
   stay absent — yet `ps.self-awareness.understanding-your-emotions` is reached at rank 1
   via the fold by "noticing feelings in my body before I react", so the gap is that
   query's specificity against the score floor, not that PathStep's retrievability. Only a measured
   miss traced to chunk
   grain earns a `chunking_params` change on one `EntityIngestionConfig` + a domain-scoped
   re-chunk. This is also where `min_chunk_size`'s default is re-based: 50 words is above the
   corpus median, so enforcing it is a tuning decision, not a defect fix. (The two older
   scripts still measure something else: `analyze_search_metrics.py` is latency/score
   from logs; `benchmark_hybrid_queries.py` is query-pattern latency.)
   **PR-2 (2026-08-30):** set widened to **v2** on Mike's ratification review — both
   `real_usage` rows had been too narrow, and both notes now carry the measurement that
   settled them. **Body-fold status shipped:** `SearchResponse.body_fold`
   (`BodyFoldReport` + `BodyFoldStatus`, ruled 2026-08-30) reports whether the fold ran,
   how many passages cleared the floor and how many parent cards it added — the fold fails
   SOFT, so without it a chunk-blind response is indistinguishable from a chunk-aware one
   that matched nothing. It REPLACED the eval's out-of-band probe, which proved only that a
   SIBLING call succeeded while the scored response's own fold ran afterwards and could fail
   independently.
   **Append-never-promote (measured, not a defect claim).** `_augment_with_body_chunks`
   ends `merged = list(response.results) + body_results`, and a parent already present from
   frontmatter is deduped OUT of the body list. So the fold can append but never re-rank:
   for `breath`, chunk retrieval scores `ps.mindfulness.breath-awareness-basics` the **#1
   parent at 0.755** while it sits at merged rank **6**, below five title-CONTAINS Kus. Mike
   ruled 2026-08-30 that those five are genuinely relevant, so this is recorded as a
   structural fact, not scheduled work; it is what a future ordering change would have to
   contend with.
3. **`chunk_type_weights`:** only when (a) the eval set exists and (b) a content-typing
   classifier has replaced the keyword fallback AND its distribution has flattened enough for
   weights to change an ordering (explanation < 50%) — (b) is a classifier decision, not a
   threshold the corpus crosses by growing (first bullet above).
   The table must carry all nine `ContentChunkType` members — a type with 0 chunks today
   (`code`, `section`, `introduction`, `conclusion`) weights 1.0 until it is measured, never
   "absent"; the distribution check below groups by whatever types exist.
4. **Askesis intent filter — MEASURED INERT 2026-08-30; now a RULING, not a build.**
   The thin-draw comparison shipped as `scripts/eval_askesis_chunk_draw.py`
   (`./dev eval-askesis-draw [--user <uid>]`): three arms — `filtered` (production),
   `thin_draw` (keep every filtered hit, BACKFILL from an unfiltered draw up to k — never
   loses an intent-appropriate passage the way "use the unfiltered draw when thin" can) and
   `unfiltered` (control) — over the same reviewable query set, reproducing the production
   draw (`limit=5`, `min_score=0.6` — NOT /search's 0.68 — and `user_uid` as the ADR-085
   audience). Recall is scored at the **prompt window of 3**, not the draw limit:
   `retrieve_relevant_context` keeps `relevant_chunks[:3]` and that is what `llm_service`
   inlines, so a parent reached only at draw rank 4 is retrieved and thrown away.
   Starvation is measured against the same 3 for the mirror reason. **Result: all three
   arms identical (recall@3 22/23, 0 starved), run both curriculum-only and with the
   audience, because 0 of 23 queries reached a filtered intent.** The script printed that
   as a loud banner, with the measured margin (`max_intent_score` 0.29 against the then-0.65
   gate) so the zero read as "unreachable gate", not "unusual queries" (banner re-worded at
   PR-2: the gate is reachable now, so an all-unmapped run reads as "these queries score
   low") —
   `filtered_intent_queries: 0` means the arms are an identity, not a finding. It classifies
   through `IntentClassifier.classify_intent_scored` (added here), NOT the fail-soft
   `classify_intent`: that one converts an embedding outage into `Result.ok(SPECIFIC)`, which
   is byte-identical to a real low-confidence verdict, so an outage could have manufactured
   this very finding with `errors: 0`. The scored variant fails loudly and a failed
   classification invalidates its row. It also reports `unlabelled_in_windows` PER ARM (1 in each of the three on the
   `--user` run, 0 curriculum-only), because a viewer's own notes compete for the prompt
   window while the set labels only published Ku/PathStep. Per arm, not per run: once
   the filter is live the three arms hold different windows, and a note sitting in only
   one of them would depress that arm alone and make the delta look like filtering.
   **So the thin-draw fallback would change nothing today**, and shipping it alone would be
   dead code guarding dead code.
   **RULED 2026-08-30 (Mike): NOT (a) — do not delete. The shape is (b); the present state
   is (c).** **REFINED the same day, once the dormant surface was measured: the classifier fix
   is SCHEDULED and the chunk filter is NOT part of it** — see
   [askesis-intent-classification-activation.md](askesis-intent-classification-activation.md).
   The classifier gates SIX Askesis branches across its two callers, and this filter is the
   weakest of them; the other five (graph context, suggested actions, citations — which had
   consequently never attached to any Askesis answer until PR-2 — plus the context-query
   API's own prose and actions branches) need no chunk types at all. So activation happened there first with `chunk_types` hard-wired off
   (LANDED 2026-08-31, PR-2 — `retrieve_relevant_context` no longer calls
   `_intent_to_chunk_types`; the map's disconnection is stated at the call site), and
   "fix and fallback ship together" narrows to its true scope: it binds whoever switches the
   FILTER on, not whoever fixes the classifier. This entry keeps the filter half.
   The plumbing stays because the intent is to *connect* it, not to retire it:
   `_INTENT_CHUNK_TYPES` + `chunk_types=` are a staged surface awaiting a reason to fire, so
   they are **PLANNED, not dead** — the One Path Forward carve-out for deliberately
   staged-but-unwired work. **Switching this filter on is ONE change with the thin-draw
   fallback**: activation is never neutral, and a live filter without the fallback imposes
   the 66-of-925 EXPLORATORY starvation on draws that today see all 925. The fallback is the
   prerequisite for ACTIVATING THE FILTER — not for fixing the classifier, which the arc doc
   does with the filter left off. Until then (3)'s weight table is arguing about a path that
   does not execute.
   ⚠ **The EXPLORATORY mapping is now wrong ON ITS OWN TERMS (PR-1 of the arc, 2026-08-31).**
   PR-1 settled `EXPLORATORY` as **catalog browsing** — *"what is there to learn here?"* — and
   NOT topic orientation (*"introduce me to stoicism"*, which is a content question and stays
   `SPECIFIC`). `INTRODUCTION`/`SUMMARY`/`DEFINITION` types an orientation answer, so this row
   maps an intent to the chunk types of a DIFFERENT intent. That is independent of the 7.1%
   eligibility measured above: even with a perfect content-typing classifier and a rich
   `introduction` population, the mapping would be answering a question EXPLORATORY no longer
   asks. Whoever builds (3)'s weight table or switches this filter on re-derives that row
   first — the arc doc's ruling 3 carries the reasoning.
   **Named cost while inert — SHRUNK by PR-2 (2026-08-31):** until then every reader of
   `context_retriever.py` — and, until #1198, four docs — saw an intent→chunk-type filter that
   appeared operative and was not, legible only through this entry plus the
   `./dev eval-askesis-draw` banner. The call site now states the disconnection itself
   (`chunk_types=None`, hard-wired, with the reason), and `_intent_to_chunk_types` is
   registered in `PLANNED_METHODS`.
   ⚠ **"Fix the classifier" DOES now mean "move the gate" — this reversed on the ratified
   baseline (2026-08-31), and the earlier reading here was wrong.** It said the fix must not be
   assumed to be a lower threshold, because a verbatim exemplar's 0.43–0.56 self-similarity
   implicates the *averaging over 8 diverse exemplars*, and because all three aggregations were
   thought to rank identically. Measured on 45 labelled queries, both halves fail: the
   aggregations do NOT rank identically (mean 30/31, max 29/31, top-3 29/31), and the production
   `mean` **dominates at the exact zero-wrong-activation frontier** — it activates 21 of 45 at
   0.3329 (78% accuracy), against max 17/45 at 0.5353 (69%) and top-3 15/45 at 0.4911 (64%).
   ⚠ Exact, not ladder-rounded: the frontier is pinned by one query and a 0.05 grid rounds it up,
   which understated all three arms (#1206). The averaging is not the defect; it is the
   best-behaved of the three. So the indicated fix is the one the old reading warned against:
   keep the mean, move the gate — **0.35, deliberately not the frontier itself**, which is an
   observed score and drifts between runs. **SHIPPED 2026-08-31 (PR-2)**: the gate is 0.35;
   the `AGGREGATION` carve-out PR-2 introduced was lifted the same day by the tool-selection
   first slice ([askesis-tool-selection-queries.md](askesis-tool-selection-queries.md)) in the
   same commit that added the aggregation tool; the arc doc's PR-2 section records the
   post-change measurement. Note what flipping queries off SPECIFIC does and does not touch: with `chunk_types`
   held off it re-routes the two answer-shaping branches and NOT the chunk draw, which is
   exactly why the arc proceeded without the fallback.
   **Both halves of that are RUNNABLE, not just prose**
   (`tests/unit/test_askesis_intent_filter_activation_guard.py`): mapping `SPECIFIC` fails —
   it is the verdict `classify_intent` returns on an embeddings OUTAGE, so a mapping would let
   a provider failure silently answer from a type-filtered slice, and that holds after the fix
   too; and switching the score from a mean to a max fails — originally because the averaging
   was the mechanism the "not just lower 0.65" reading rested on, and now for a better reason
   that outlived it: the mean is MEASURED to mis-route least. Neither asserts the filter is inert —
   that is live-corpus state and stays with `./dev eval-askesis-draw`.

**Trigger:** (1) ✅ done; (2) ✅ instrument + body-fold status shipped (PR-2), set ratified at
v2 and the baseline recorded on #1197 — the thread is now open only for a measured miss traced to
chunk grain (judged on `best_rank`, not the saturated hit@5); (4) ✅ measured and RULED — and the
ruling SPLIT it in two, so read both halves before starting: the **classifier fix is scheduled
separately** and does NOT touch this filter
([askesis-intent-classification-activation.md](askesis-intent-classification-activation.md)),
while **switching this filter on** stays here, gated on (3)'s content-typing classifier and
carrying the thin-draw fallback in the same change. Inert with the cost named until then;
(3) needs that classifier regardless, and gates the filter half of (4) — not the classifier arc,
which does not depend on it.
**Check** (one statement per block — paste each on its own; words, not characters, because the
knobs are word counts; `c.end_index` is the persisted whitespace-aware `word_count`, so a chunk
with line breaks or doubled spaces is counted the way ingestion counted it — a naive
`split(text, ' ')` disagrees on 4 of 998 chunks and inflates the max to 599):
```cypher
MATCH (c:ContentChunk) WITH c.chunk_type AS t, c.end_index AS words
RETURN t, count(*) AS n, percentileCont(words, 0.5) AS p50_words,
       sum(CASE WHEN words < 5 THEN 1 ELSE 0 END) AS fragments,
       sum(CASE WHEN words < 50 THEN 1 ELSE 0 END) AS under_min_chunk_size
ORDER BY n DESC
```
```cypher
MATCH (c:ContentChunk) WHERE c.end_index < 5 RETURN count(*) AS fragments   // 83 pre-v2 → 7 after the 2026-08-30 re-chunk (all link-only notes); a rise = new fragment-shaped ingestion
```
plus `git grep -n chunk_type_weights -- core/` (empty until built).
The intent filter's disconnection IS greppable since PR-2 (2026-08-31): the one production
call site hard-wires `chunk_types=None` with the reason stated
(`retrieve_relevant_context`, `core/services/askesis/context_retriever.py`) — before that the
code was wired and reachable and only the unreachable 0.65 gate kept it inert.
`./dev eval-askesis-draw --json` → `filtered_intent_queries` now counts queries whose
CLASSIFIED intent has a mapping — a counterfactual input to the filter arms, not "production
filtered here"; non-zero is EXPECTED at the 0.35 gate, and the arms measure what the filter
WOULD do for PR-3.
**Named cost while parked:** a type table built today would be tuned against a fallback-dominated
corpus (78% one label on the v2 corpus), and EXPLORATORY's eligible slice stays 66-of-925 — a
counterfactual while the filter cannot fire, and the number to beat the moment it can.

---

## DSL-Bridge Grounding Pair — Goal-Link Persistence + Principles/Recent-Topics (REGISTERED 2026-08-28)

#474 (2026-07-04) grounded BOTH `LLMDSLBridgeService.transform_with_context` callers in the
user's active goals through one builder (`core/services/dsl/grounding.py`: `active_goal_titles`,
`goals_as_context`), riding a non-extractable `{user_context}` prompt slot. Two follow-ups were
deferred in that PR's thread and lived only in memory:

1. **Goal-LINK persistence.** Grounding passes TITLES, so nothing resolves to an edge:
   `ActivityDSLParser.get_linked_goals` (`core/services/dsl/activity_dsl_parser.py:352`) builds
   `FULFILLS_GOAL` only from an explicit `@link(goal:<uid>)`; `@goal(...)` is a dropped attribute.
   Wiring it = UID-aware grounding + the model emitting `@link(goal:<uid>)` through the
   suggestion path + cache key — and a **keyed LLM test**, because a hallucinated UID on the
   entity-creating `EXTRACT_ACTIVITIES` path writes a WRONG edge. Measured 2026-08-28:
   **56 extracted tasks (`EXTRACTED_FROM`), 0 with any edge to a Goal, 0 `fulfills_goal_uid`;
   2 active goals** — the 2 live `FULFILLS_GOAL` edges in the graph are hand-authored.
2. **`user_principles` / `recent_topics` grounding.** `transform_with_context` accepts both
   (`core/services/dsl/llm_dsl_bridge.py:301`); neither caller passes them
   (`core/services/journal/journal_service.py:286`,
   `core/services/user_entry/user_entry_processing_service.py:478`). Deliberately symmetric:
   adding either to ONE path re-introduces the asymmetry #474 closed — **add to BOTH together**.

**The prerequisite both share:** the keyed LLM A/B that #474 could not run (no key then; the
Anthropic key has been in dev since 2026-07-23) — does goal grounding actually lift recognition?
Until that is measured, extending grounding is adding inputs to an unverified effect.

**Named work:** (0) run the A/B on the two prompt-capture fixtures with a real key and record the
recognition delta here; (2) if it lifts, thread `user_principles` / `recent_topics` through BOTH
callers in one PR (principle titles via `UserContext.core_principle_uids`; recent topics from
the entry's own recent tags); (1) only on Mike's product ruling that AI-inferred goal edges are
wanted — an edge the user did not author is a different kind of write.
**Trigger:** (0) next touch of the bridge, or Mike schedules it; (1) Mike's ruling; (2) the A/B.
**Check:** per argument — each must appear in BOTH callers or in NEITHER (neither today; a single
grep for either name would pass with one argument in each file):
`git grep -c "user_principles=" -- core/services/journal/journal_service.py core/services/user_entry/user_entry_processing_service.py`
`git grep -c "recent_topics=" -- core/services/journal/journal_service.py core/services/user_entry/user_entry_processing_service.py`;
`MATCH (t:Task)-[:EXTRACTED_FROM]->() OPTIONAL MATCH (t)-[:FULFILLS_GOAL]->(g:Goal) RETURN count(DISTINCT t) AS extracted, count(DISTINCT CASE WHEN g IS NOT NULL THEN t END) AS linked_tasks`
→ 56 / 0 on 2026-08-28.
**Named cost while parked:** every extracted task is goal-less however obviously it serves an
active goal; the recognition-quality claim behind #474 stays unmeasured.

---

## `HabitMissed` — Publisher-less Chain (REGISTERED 2026-08-28 — ruled keep-staged)

`HabitMissed` (`core/events/habit_events.py:131`) is subscribed
(`services_bootstrap/_event_wiring.py:532` → `HabitEventHandlerService.handle_habit_missed`,
`core/services/habits/habit_event_handler_service.py:447`) and has **no publisher in any
commit** — `git log -S'HabitMissed('` finds only the initial commit's usage fiction, deleted in
#1173. The handler is real: structured miss/difficulty logging, and at ≥3 consecutive misses a
persisted `InsightType.DIFFICULTY_PATTERN` through `InsightStore` — a live store (11 `:Insight`
nodes on 2026-08-28: 8 `completion_pattern`, 3 `learning_progress`, **0 `difficulty_pattern`**).

**Ruling 2026-08-28 (Mike):** the three same-shaped PLANNED entries were ruled in one sitting —
`SchemaChangeDetector.add_change_handler` and `UserContext.get_recommended_next_action`
DELETED 2026-08-29 (the PR after #1179 — with `SchemaChangeEvent`, whose only reader was the
fan-out); this chain KEPT staged. It differs from the two: its consumer is a persisted insight in
a store other events already feed, not a fan-out with no reader.

**What the publisher must be:** a detector that finds occurrence days with no completion. Tier
does not constrain its shape: CORE's guarantee is **AI-scoped** ("no AI background workers" —
`GRACEFUL_DEGRADATION_ARCHITECTURE.md` § Why This Matters; the hourly `ProgressReportWorker` IS a
CORE-tier Analog worker, and `done/reopen-vault-surface.md` records "CORE runs no background
workers" as a falsified premise). So a **scheduled Analog detector** on the `ProgressReportWorker`
pattern, a **read-time** scan (compute misses since the last observation when the habit list or
`/today` loads, publish, record the watermark) and a **one-shot** (`./dev habit-miss-scan`, like
telemetry retention) are all legitimate; the constraints are no LLM, no API cost, and the day
model. Its day maths must honour the future-completion ruling (a future completion is not a
miss) and the `current_streak` semantics question in § Habit Streak Counters — the same "what
does a day mean" ruling. Do not build the detector before that ruling.
**Trigger:** a lived want for difficulty insights, or the streak-semantics ruling (they share the
day model — rule it once).
**Check:** `git grep -n "HabitMissed(" -- core/ adapters/ scripts/ services_bootstrap/ ui/ ':!core/events/'`
— empty until a publisher exists in either accepted shape (`scripts/` covers the one-shot;
`core/events/` is excluded because it holds the class definition; the subscriber in
`_event_wiring.py` is the deliberate staging);
`MATCH (i:Insight {insight_type: 'difficulty_pattern'}) RETURN count(i)` → 0.
**Named cost while staged:** `./dev bloat` carries it as PLANNED; the difficulty assessment is
code that has never run outside its unit tests.

---

## Quarterly / Yearly Periodic Notes — Founder Vault Pass First (REGISTERED 2026-08-28)

The periodic-notes arc (`done/calendar-periodic-notes-arc.md`) unified daily + weekly + monthly:
the ingestion door derives `ue:daily:{user}:{date}`, `ue:weekly:{user}:{week_of}` and
`ue:monthly:{user}:{month}` (`core/services/ingestion/user_entry_ingestion.py:397-410`). The
founder vault also holds `templates/t_quarterly.md` (0 bytes) and `t_yearly.md` (2 bytes) and
the empty folders `periodic_notes/Quarterly/` and `periodic_notes/yearly/` (2026-08-28: Daily 13
files, Weekly 3, Monthly 0, Quarterly 0, yearly 0) — stubs with no UID derivation and no
calendar door.

**Ruling 2026-08-28 (Mike):** founder vault pass first — the templates get authored when a
quarterly/yearly rhythm actually starts; app support follows the first real note, not the stub.
**Named work (then):** `ue:quarterly:{user}:{YYYY-Qn}` / `ue:yearly:{user}:{YYYY}` derivation +
frontmatter date parsing beside the monthly branch; the calendar panel question
(§ Monthly-Note Panel Parity) inherits the same answer.
**Trigger:** the first file in either folder —
`find ~/0bsidian/skuel/periodic_notes/Quarterly ~/0bsidian/skuel/periodic_notes/yearly -type f | wc -l` > 0
(founder-owned check, non-repo — `find -type f`, not `ls`: with two directory operands `ls` prints
headings, so two EMPTY folders already count 3).
**Named cost while parked:** none in the app; two empty template files in the vault.

---

## PathStep → Ku Wiring Backlog — Ku-less PathSteps, PathStep-less Kus (REGISTERED 2026-08-28)

Askesis grounds a PathStep through its COMPOSITION edges — `USES_KU`, `TRAINS_KU`,
`CONTAINS_KNOWLEDGE` — (`PsBundle.kus`, filled by `ContextRetriever._fetch_kus`,
`core/services/askesis/context_retriever.py:693`); a step with none renders `kus=0` and the
companion has no atomic knowledge to cite for it. Measured 2026-08-28 (AuraDB, all three edges:
`USES_KU` 73, `TRAINS_KU` 5, `CONTAINS_KNOWLEDGE` 0): **1 of 25 PathSteps has no composition
edge — `ps.meditation.basics`** (`0vault/Ps/Ps_dev/`, also in the seed set of
`scripts/seed_search_test_data.py`) — and **67 of 121 Kus are composed by no PathStep**.
⚠️ A `USES_KU`-only census says 5 steps, not 1: the four mindfulness/self-reflection steps
declare `trains_ku_uids:` in their frontmatter and Askesis grounds them correctly — test all three
edges or the backlog is overstated five-fold (Codex, #1179). `./dev knowledge-health` reports
neither count: its orphan count is degree-0 Kus (no edge of any kind), a different question.

**Ruling 2026-08-28 (Mike):** a content backlog, registered with the two counts as the check.
**Named work:** compose `ps.meditation.basics` (`uses_kus:` or `trains_ku_uids:` — a
`Ps_dev` content session); decide which of the 67 unused Kus deserve a PathStep — or an
`ORGANIZES` parent, the other path to knowledge (MOC); the third query below shows how many have
neither. Optional, not built: a `path_steps_without_ku` / `kus_unused_by_path_step` pair in
`KnowledgeHealthService` (ADR-080 H1 authoring gauge) so the check becomes
`./dev knowledge-health` — over the same three-edge alternation, never `USES_KU` alone.
**Trigger:** Mike's next content session on `Ps_dev`.
**Check** (one statement per block; the alternation is the same set `_fetch_kus` composes over):
```cypher
MATCH (p:PathStep) WHERE NOT (p)-[:USES_KU|TRAINS_KU|CONTAINS_KNOWLEDGE]->(:Ku)
RETURN count(p)     // 1 on 2026-08-28
```
```cypher
MATCH (k:Ku) WHERE NOT (:PathStep)-[:USES_KU|TRAINS_KU|CONTAINS_KNOWLEDGE]->(k)
RETURN count(k)     // 67 on 2026-08-28
```
```cypher
MATCH (k:Ku) WHERE NOT (:PathStep)-[:USES_KU|TRAINS_KU|CONTAINS_KNOWLEDGE]->(k)
  AND NOT ()-[:ORGANIZES]->(k)
RETURN count(k)     // 67 on 2026-08-28 — every PathStep-less Ku also lacks a MOC parent
```
**Named cost while open:** one step Askesis cannot ground in Kus; 67 Kus (55%) are composed by
no PathStep — and, by the third query, organised by no MOC either today, so they are reachable
only by search. The PathStep count alone cannot support that claim; keep the third query in
the check.

---

## py314 Annotation Sweeps — UP037 Schedulable, TC002/TC003 Never (REGISTERED 2026-08-28)

**Home: ADR-067 § "Deferred: TC/UP037 annotation-modernization sweep"** — the rationale, the two
dispositions, the runtime-evaluation hazard and the measured baseline live there; this section
holds only the trigger and the check, so the review walk sees it. For today's size, run the
check — the counts move with every commit, so no number is written down here.
**Trigger:** UP037 — a churn window Mike picks (one mechanical PR, boot-verified per the ADR);
TC002/TC003 — never as a sweep (permanent ignore; re-open only if ruff can name a local
decorator as runtime-evaluated).
**Check:** `uv run ruff check --select UP037 --statistics . | tail -3` — no UP037 row after the
sweep; `grep -n '"TC002"\|"TC003"' pyproject.toml` still in the ignore list, comment says
*permanent*.

---

## Parked Features — Memory-Only Until Now (REGISTERED 2026-08-28)

Four feature-shaped threads Mike ruled *build later, from a stated design* — parked under the
2026-08 stabilize directive, and until this section recorded nowhere the repo could see. Each
row: what it is, the constraint already ruled, and a check that it is still absent. **Trigger
for all four: Mike schedules it** — none is a data threshold, and none may be self-scoped.

### Activity ledger (ruled 2026-06-11)
A cross-domain, event-grained, chronological feed ("Completed habit: Exercise · 2h ago") with
two consumers: a profile sibling to the recent-reports section, and the evidence input
`ActivityReport` generation synthesizes from. **Constraint:** design from the LIVE stores and
`{domain}.{action}` events (`dual_track_checkins`, habit completions, choice records) across all
6 Activity Domains at once; never restore the #286-deleted `get_recent_activity` (single-track,
proxy timestamps).
**Check:** `git grep -n -i "activity_ledger\|ActivityLedger" -- core/ ui/ adapters/` → empty.

### Interest signal + adoption/gravity — ONE thread (ruled 2026-06-11, unified 2026-08-22)
An interest-aware recommendation signal derived from live stores — `VIEWED` edge
recency/frequency, tags of engaged entities, or an embedding centroid of touched content —
feeding LP/content ranking. The ownership bundle deleted the four `HAS_*` "gravity" writers
(ADR-086 § 2); Mike ruled adoption/engagement is the SAME signal. **Constraint:** one engagement
signal, never two edges; never resurrect the #288 facet-affinity code (session-local by design)
or the retired gravity edges `HAS_TASK` / `HAS_GOAL` / `HAS_HABIT` / `HAS_EVENT` / `HAS_CHOICE` /
`HAS_PRINCIPLE` / `HAS_KU` (the live `HAS_*_TEMPLATE` family is a different edge and stays).
**Check** — two greps, both empty today: the new signal is absent, and no retired gravity edge is
a `RelationshipName` member (SKUEL030 makes that enum the only door to a Cypher edge, so the
member is the thing to watch, not free-text mentions — two comments still name the edges
historically):
`git grep -n -i "interest_signal\|engagement_signal\|facet_affinit" -- core/ ui/ adapters/`
`git grep -n -E '^\s+HAS_(TASK|GOAL|HABIT|EVENT|CHOICE|PRINCIPLE|KU)\s*=' -- core/models/relationship_names.py`
The same idea also survived as two reader-less members of the lowercase semantic vocabulary
(`RelationshipType.HAS_GOAL` / `.HAS_HABIT`, `core/models/enums/metadata_enums.py`) — deleted in
#1179; `git grep -n -E '^\s+HAS_(GOAL|HABIT)\s*=' -- core/models/enums/metadata_enums.py` → empty.

### Icon provider swap (ruled 2026-06-29)
`Icon()` (`ui/components/icon.py`) is a real chokepoint but its port leaks lucide's vocabulary —
126 `Icon("<lucide-name>")` literals on 2026-08-28, one `ICON_PATHS` registry, no provider
concept. **Design when wanted:** a semantic `IconName` StrEnum port; one generated registry per
provider with a `SEMANTIC_MAP`; `ICON_PROVIDER=lucide|heroicons` selected at startup like
`INTELLIGENCE_TIER`; the build assertion becomes "every adapter is total". **Constraint:** no
swap machinery before a second provider is actually wanted (One Path Forward); the silent-
fallback validation already shipped (#454/#455, `gen_icons.py::icon_name_literals`).
**Check:** `git grep -n "IconName\|ICON_PROVIDER" -- ui/ core/` → empty.

### Activity-templates re-homing (ruled 2026-07-06, shape undecided)
The 6 Activity Templates are PS-owned, TEACHER-gated, spawn instances on engagement, and are
invisible to search (not in `SearchRouter._SEARCHABLE_DOMAINS`,
`core/orchestrator/search_router.py:335`; absent from the `/search` Types facet). Mike ruled they
should be modelled/surfaced *somewhere of their own* and explicitly did not want a shape forced
yet. **Constraint:** a separate arc (not folded into search/nous work); entities stay orthogonal —
no coupling edges to make templates "belong". The adjacent question — should the Types facet do
content-discovery-by-domain? — is distinct and unruled.
**Check:** `git grep -n "_TEMPLATE" -- core/orchestrator/search_router.py` → empty (still
unsearchable); no templates hub under `ui/`.


---

## Docs `updated:` Frontmatter — Auto-Stamp (✅ SHIPPED 2026-09-01 — ruled 2026-08-29, guard fork ruled 2026-09-01)

**Built.** The field is now written by machine and checked by machine. Three pieces,
one shared module (`scripts/docs_updated_field.py`) so none is a catalog copy of the
others:

| Piece | Where | Runs |
|---|---|---|
| Stamper | `scripts/stamp_docs_updated.py` | pre-commit check 0 (`SKUEL_SKIP_DOC_STAMP=1` bypasses) |
| Backfill | `scripts/backfill_docs_updated.py` | once, 2026-09-01 |
| Guard | `scripts/health/docs_updated.py` | `./dev health-updated`, `./dev health`, weekly janitor |

**Result:** 412 of 412 green, in 2.6s. Before the backfill, 373 were wrong — 193 with
no `updated:` at all, 180 lagging their last substantive commit by over a week (33 by
over six months). The design and its reasoning live in
[`docs/tools/HEALTH_CHECKS.md` § 7](../tools/HEALTH_CHECKS.md) and the scripts'
docstrings; **this section deliberately does not restate them** — the sixteen traps
registered here were found by ten review rounds of *this prose*, four of them being
this document contradicting itself, and a stamp that is mechanically written is the
only form that cannot rot into a paraphrase. What follows is only what a future
session must not re-decide.

**Forks, as settled:**

- **Guard comparison = rot threshold, 7 days** (option (a), Mike 2026-09-01). Not
  merge-side stamping (b). ~~(c) drop the date comparison~~ **stays rejected**: on a
  doc stamped once whose hook then stops running, the old value remains present,
  unique, parseable and non-future forever — so the four structural checks pass on
  exactly the rot the guard exists to catch. Recorded rather than deleted so it is not
  re-proposed as "the simple option".
- **Backfill preserved pre-stamp history** (option (i)). Each file got its own last
  *substantive* commit date; the fall-back to a uniform backfill date was not needed.
- **Scope is `app/docs/**/*.md`.** Skills excluded — `SKILL.md` already carries
  `last_updated` and the cross-reference validator reads a human-set `last_reviewed`; a
  third date key would be a duplicated fact, and auto-stamping a *review* date destroys
  its meaning. Root `AGENTS.md`/`CLAUDE.md` excluded — always-loaded instruction files
  read in full, not sampled for freshness. `roadmap/done/` and pinned archives are
  **not** exempt: an unedited doc's stamp already matches its last substantive commit,
  so the guard is free on them and an exemption would only open a hole. **Machine-generated
  docs ARE excluded** — detected by their own `AUTO-GENERATED` banner, not a path list —
  because a generator's drift test is a stronger freshness guarantee than a date and a
  stamp breaks its byte-comparison.

**Permanent rules the guard carries:**

- **Stamp-only commits are excluded from "last substantive commit"** — stated as a rule,
  never a hardcoded SHA, so any future stamp-only commit gets the same treatment. A
  commit qualifies only if it actually changes an `updated:` line; fences and the blank
  separator are permitted alongside it because *creating* a block emits them, but on
  their own they are not a stamp change (a commit deleting two blank lines qualified
  under the looser rule and dated three docs from the wrong commit).
- ⛔ **Never cite `updated:` as staleness evidence outside the guard.** After shipping it
  is evidence *only within the 7-day rot window, and only because the guard runs*. It is
  never evidence of whether a doc's content is correct.
- ⛔ **No same-file contradictory-prose detector** — measured unmechanizable, 4/4 false
  positives. See the sub-finding below.

**Traps that survived into the build.** None was visible to a fixture; each was found by
running against the real corpus, by the full test suite, or by review, and each looks like
a simplification. **This is not the whole list** — Codex found twelve defects across ten
review rounds of the *implementation*, on top of the sixteen it found in ten rounds of the
registration, and every one of them is recorded in a docstring beside the code it
constrains, which is where a constraint cannot rot into a paraphrase. Carried here are the
ones a future session would most plausibly reintroduce while scoping:

- **Never `yaml.safe_load` the frontmatter to read this field.** 35 of 412 docs carry an
  unquoted `title: ADR-013: KU UID Flat Identity Design`, whose colon-space is a YAML
  syntax error — while their `updated:` line is perfectly well-formed. A YAML-parsing
  guard sits red on all 35 for a `title:` defect it does not own. (`validate_cross_references.py`
  *does* YAML-parse, so those 35 docs' `related_skills:` are invisible to it — none
  declares any today, so nothing is currently lost; quoting the 35 titles is a separate,
  unscheduled fix.)
- **Do not attribute `git show` hunks to files by parsing `+++ b/<path>`.** Git appends a
  TAB to that header for paths containing spaces, and three docs under
  `design-principles/` have them. Pass the path as a pathspec instead.
- ⚠️ **Never compute a file line number by adding an offset to a position inside the
  parsed frontmatter.** `split_frontmatter`'s opening fence is `^---\s*\n`, and `\s*`
  swallows a blank line after the `---` — so the raw block can begin on file line 2 while
  "raw index + 1" assumes line 1. Stamping then overwrote `title:` and left the real
  `updated:` below it: metadata deleted, duplicate key created, silently. Scan the file's
  own lines between the fences; `split_frontmatter` decides *whether* there is a block,
  not *where* its lines are. (Codex P1 on #1212 — the most destructive defect in the arc.)
- **Diff text cannot decide "touches only the stamp" — normalise the blobs instead.** Two
  formulations failed in sequence. *"Every changed line is a fence or a blank"* classified
  a commit that merely deleted two blank lines as stamp-only, dating three pattern docs
  from the commit before it. Adding *"and at least one changed line is `^updated:`"* still
  could not tell **where** that line sat — and two docs carry a documentation *example* of
  an `updated:` line in their body, so a commit editing only that example counted as
  stamp-only and the real edit stayed invisible to the guard indefinitely (Codex P2 on
  #1212). Stamping both blobs to the same date and comparing is positional by
  construction, because `apply_stamp` writes only the leading block.
- **A generated doc must not be stamped.** A date written into generated content
  describes nothing — the next regeneration overwrites it and the guard then reports a
  correctly regenerated file as missing its key — and where the artifact is drift-tested a
  frontmatter block reds that test immediately. ⚠️ The exemption does **not** assert that
  every excluded artifact is drift-tested — the argument for excluding it stands either
  way. (`CROSS_REFERENCE_INDEX.md` had no such test when this was recorded; closed by
  `tests/unit/scripts/test_generate_cross_reference_index.py`.) Detected by the file's own
  declaration — *"this file is auto-generated"*, matched as a self-assertion rather than
  the bare phrase, header-scoped — never a list of generated paths. The loose form has to
  be avoided in that exact direction: a hand-maintained doc wrongly matched is dropped
  from the guard permanently and *silently*, whereas a generated doc missing its banner
  fails loudly on its own drift test. The excluded paths are named on every run.
- **A writer must not treat malformed frontmatter as absent frontmatter.**
  `split_frontmatter` reports "no frontmatter" for a `---` fence that never closes — the
  right answer for a reader, a dangerous one for a writer: stamping prepends a second,
  valid block and the author's `title:`/`status:`/`related_skills:` become body text,
  present in the file and invisible to every parser. The stamper refuses and names the
  file; the guard reports `malformed` as its own verdict. Nothing in the corpus is
  malformed today; one mistyped fence is all it takes. (Codex P2 on #1212.)
- **A history-reading check must refuse a shallow clone, not measure it.**
  `actions/checkout` fetches one commit by default, and the weekly janitor's checkout had
  no `fetch-depth` — the guard reported 343 of 410 docs stale in a depth-1 clone, and at a
  HEAD touching no docs it would have reported a clean green having checked nothing. Fixed
  at the site (`fetch-depth: 0`) *and* in the check, which now exits 2 rather than publish
  either number — an audit that could not measure must never read as a passing week, the
  rule the janitor already applies to its bloat report. (Codex P2 on #1212.)
- **Creating a frontmatter block shifts every line number below it**, which invalidates
  any registry anchored by `(file, line)`. `stale_names.ALLOWED_OCCURRENCES` is exactly
  that, and the backfill left 72 of its anchors hitting nothing — so the exemptions
  stopped exempting and `./dev health-names` reported 72 phantom stale references. Found
  by the full unit suite, not by the backfill's own verification, which checked its
  writes but not what downstream depended on their line numbers. **Any future bulk edit
  that inserts at the top of docs must re-anchor that dict** (re-anchor by the file's
  measured line-count delta, not by a guessed constant — the delta here was 4, 1 or 0
  depending on whether the block was created, a key was inserted, or the key was
  rewritten in place).


### Sub-finding: same-file contradictory ruling prose is NOT mechanizable

Registered so it is not attempted again. The three sites cleaned up in #1182/#1183 shared a
shape — a ruling PR corrected one mention and left a contradicting one **in the same file**
(`search_request.py` 816 fixed / 895 stale; `SEARCH_MODELS.md` prose fixed / code block
stale; #1169's frontmatter vs its own body). The obvious detector does not work: scanning
for one `#NNN` cited twice in a file with both defer-family and settled-family words nearby
yields 28 pairs across 18 files, and **4 of 4 spot-checks were false positives** —
`INDEX.md` #978 (two correct rows), `deferred-work.md` #215 ("PR #215 dropped X" inside a
*different* item's "Why deferred"), `ingestion_tracker.py` #618 (Codex round citations),
and the deliberate "was deferred, now dropped" history in
`feedback-loop-staged-directions.md` § 4. History sections legitimately carry both
dispositions, so the check would flag correct prose as loudly as real drift.

Stays a **process discipline**, already recorded twice as a lesson: enumerate every site
before fixing any, and treat every summary as a duplicated fact. The one narrowing worth
carrying: when a ruling changes a fact, **re-grep the file you just edited** — in all three
cases the stale twin was in the same file as the fix. The post-commit docs hook covers the
*other* direction (docs referencing a changed module) and demonstrably works: it caught two
of the four sites unprompted during #1183.

---

## Catalog Copies in Code — the duplicated-fact defect, measured (registered 2026-08-29)

The documentation lesson recorded across #1153, #1176 and #1184 — every summary line is a
duplicated fact, stale copies are paraphrases `git grep` cannot find, and re-syncing a copy is
not a fix — has an exact analogue in code. This section names the class, records what was
measured on `8030f8899`, and registers the remedies. **The mechanical items are not built**
(phase directive): the inventory is the deliverable, Mike schedules the rest. Done in this
registration: CLAUDE.md's four enumerations became pointers or rules, and two docs lost a
pairing the code never had.

**The class — a catalog copy.** A hand-maintained enumeration (map keys, a `subscribe()`
block, a runner's script list, a count or member list in prose) of a membership fact whose
truth is decided elsewhere in the tree. It is a duplicate by construction and rots when the
source changes in a diff the copy is not part of. **Rule for new code:** a second list of the
same members is the defect unless it is (a) derived from the first — `for x in SOURCE` — or
(b) covered by a drift test that *discovers* copies rather than naming them, or (c) marked
"not the full set — see SOURCE" where it sits. SKUEL's remedies, strongest first, each with a
live exemplar: derive the catalog (`EVENT_REGISTRY` in `core/events/__init__.py`), generate the
doc (`scripts/generate_graph_contract.py` → `docs/reference/GRAPH_CONTRACT.yaml`), drift-test
the copies (`tests/unit/test_metric_reference_drift.py`, `tests/unit/test_package_exports.py`,
`tests/unit/docs/test_content_origin_docs.py` — which discovers every tier table instead of
naming two), pin two literals to each other (`AuraDBCaps` ↔ `monitoring/prometheus/alerts.yml`).
A discipline a human must remember ("touch both files") is the weakest remedy, and it is what
most of the instances below rely on today.

**Measured instances** — each: the copies · what makes it drift · whether anything notices:

1. **The `./dev health` check set.** Copies: `dev` § `health)` and `dev`'s help line; five
   sites in `.github/workflows/weekly-janitor.yml` (the `for check in` loop, two `for name in`
   loops, the "All checks passed" prose, the "Reproduce locally" prose); the janitor row of
   `.github/workflows/README.md`; `docs/tools/HEALTH_CHECKS.md` § Overview and its
   § File Structure tree; and the `docs-skills-evolution` skill (SKILL.md's file-locations row
   and reference.md's table). Drifts when a check is added — **and it did, on 2026-09-01**:
   `docs_updated.py` landed and every copy above had to be edited by hand, which is the
   instance measuring itself. Three of them (the janitor row of `.github/workflows/README.md`,
   the skill's two) were NOT in the `updated:` section's "update all three" warning and would
   have been missed by anyone scoping from it; they were found by
   `git grep -l duplicate_headings`, which is the honest way to enumerate a copy set. Those
   three became pointers rather than lists in the same change — the rest still enumerate.
   Noticed by nothing:
   `tests/unit/scripts/test_quality_ci_parity.py` pins `run_quality_checks.py` ↔ `ci.yml` and
   is the exact precedent, but no test reads `dev` or the janitor. **Remedy — one source.**
   The janitor consumes a list `dev` prints (a `--list` mode; one bash array shared by the
   janitor's five sites is the fallback), and a parity test asserts every runnable
   `scripts/health/*.py` (has a `__main__` guard) is in that list or in a declared-exclusion
   dict with a reason (`mypy_suppressions.py` — its own weekly workflow). Delete the prose
   enumerations: "reproduce locally with `./dev health`" needs no member list.
   ⚠️ `scripts/health/markdown_fences.py` is a library with no `__main__`; a directory glob
   without that discriminator would demand it be run. ⚠️ `scripts/validate_cross_references.py`
   lives outside `scripts/health/` — the family is not a directory.
2. **`PLANNED_EVENTS` / `PLANNED_METHODS` / `PLANNED_TEMPLATES` in `scripts/detect_bloat.py`.**
   The registry is itself the copy of "staged and unwired". The detector already emits
   `planned-marking-stale` when a subject vanishes, gets wired, or is masked by a same-named
   backend method — but at INFO, and `--check` fails on WARNING only while the janitor body
   prints WARNING findings and PLANNED aging only, so **no automated reader ever sees a stale
   marking**. Measured: **2 stale on 2026-08-29** — `add_attendee` and `remove_attendee`,
   masked since #1119 introduced `self.backend.add_attendee(...)` on 2026-08-21, eight days
   unseen — and the Event-attendance section of this file said so too (both copies now point
   here instead). ✅ **BUILT (ruled + shipped 2026-08-29):** a stale marking is a `WARNING` and
   fails `--check`; the janitor prints both tiers. The masked case was measured to be **2 of the
   2** findings and is NOT staleness — see the ruling below.
   ✅ **BUILT (2026-08-29, readiness arc PR-3):** the registry now *points* at this file instead
   of restating it — `PlannedEntry.blocked_by` names the `##`/`###` heading (core text) whose
   section holds an entry's blocker; the detector reads this file on every run and a pointer at
   nothing is `planned-blocker-missing`, `WARNING`, fails `--check`, with a live sentinel test
   that fails on a heading rename before CI does. `HabitMissed` lost its restated constraints
   (one copy, here). The sibling-registry-key pointer form was NOT built — zero populators.
3. **Embeddable entity types.** Copies: `EMBEDDING_EVENT_TYPES` (13), `EMBEDDING_NODE_LABELS`
   (13), `EmbeddingWorker.subscribe()` (13 hand-written lines plus the two chunk events),
   `ENTITY_CONFIGS[…].embeddable` (11), `EMBEDDING_SCAN_LABELS` (derived ✓),
   `EMBEDDING_FIELD_MAPS` (16), and CLAUDE.md's "16 content-bearing". Mostly guarded by
   `tests/unit/services/ingestion/test_post_persist_embedding.py` — except that
   `test_event_map_mirrors_worker_subscriptions` pins the map to a **literal set inside the
   test**, never to the worker, so the worker is an unguarded fourth copy and the test literal
   a fifth. **Remedy (derive):** the worker subscribes `for cls in
   EMBEDDING_EVENT_TYPES.values()`; `EMBEDDING_NODE_LABELS` becomes
   `{t: NeoLabel.from_entity_type(t).value for t in EMBEDDING_EVENT_TYPES}` — two copies and
   two tests deleted. **Hollow entries:** `ENTRY_REPORT`, `FORM_TEMPLATE`, `FORM_SUBMISSION`
   carry field maps (since `9175bb708`) but no event, no label and no ingestion flag; the only
   other caller of `build_embedding_text` is `_rank_similar_entities` on the eight AI-bearing
   facades, so nothing ever builds text for them and the "16" faithfully restates a count three
   of which are dead. `./dev bloat` cannot see map entries. Deletion protocol: unwired → ask.
   ✅ **RULED + BUILT (2026-08-29 / 2026-08-30, readiness arc PR-4):** asked, ruled keep — the
   three hollow maps are registered in `PLANNED_EMBEDDING_MAPS`, joined by a new
   `ACTIVITY_REPORT` map (four declared-hollow, zero undeclared). `./dev bloat` now *derives*
   the hollow set (`set(EMBEDDING_FIELD_MAPS) - set(EMBEDDING_EVENT_TYPES)`, both dict literals
   read by AST) and the registry annotates it: an unregistered hollow map is
   `embedding-map-unregistered`, `WARNING`, fails `--check`; a registered key that gained an
   event class is masked, never stale. The advisory phantom-field check drove two map fixes
   on the day it landed — `ENTRY_REPORT` (`content`/`summary` exist, inherited, but both
   writers populate `processed_content`) and `HABIT` (`name` is no field). CLAUDE.md's "16" is
   a rule now (the map's keys are the list); the three other doc copies followed. The two
   derivations (worker `subscribe`, `EMBEDDING_NODE_LABELS`) remain unbuilt.
4. **Suppressible lint rules.** `SkuelLinter.SUPPRESSIBLE_RULES` has 21 members; the
   "Supported" lists in CLAUDE.md and `docs/patterns/linter_rules.md` both had 20 — **SKUEL033
   missing since it became suppressible on 2026-07-29 (#868)**, a month unseen.
   `linter_rules.md` called the set "drift-guarded by `TestSuppressibleRulesDrift`" — true of
   the set (code ↔ checker call sites), false of the doc's copy of it: **"drift-guarded" in
   prose names the guard's subject; check which two things it pins before trusting a doc's
   claim about itself.** Fixed here: CLAUDE.md's copy is a pointer, `linter_rules.md` re-synced
   once. **Remedy:** a docs drift test in the `test_content_origin_docs.py` shape that finds
   every "Supported rules" list and pins it to the set. Same family: CLAUDE.md's rule table
   carries 25 of the 32 live rules in `RULE_DOCS` (SKUEL002, 005, 006, 008, 009, 010, 018
   absent) — now labelled partial rather than pinned.
5. **Lateral relationship types.** `_LATERAL_TYPES` (17) and the generated
   `GRAPH_CONTRACT.yaml` `lateral` trait (17, drift-tested ✓) versus CLAUDE.md's "6 …
   `PREREQUISITE_FOR/DEPENDS_ON`" and `docs/architecture/RELATIONSHIPS_ARCHITECTURE.md`'s
   relationship-category table and "Phase 5 deployed types" line. `DEPENDS_ON` has never been
   in `_LATERAL_TYPES`: the inverse has been `REQUIRES_PREREQUISITE` since the lateral
   implementation landed (2026-01-31), and `LATERAL_RELATIONSHIPS_VISUALIZATION.md` calls
   `DEPENDS_ON` a deliberately separate scheduling edge — so both docs asserted a pairing the
   code never had. Fixed here (pairing corrected; CLAUDE.md's line replaced by the rule). The
   category table is a hand copy of the contract's traits whose **count column disagrees with
   its own row's name list** — count the backticked names per row against the number beside
   them: 8 of 14 rows disagreed on 2026-08-29 (Lateral said 13 and named 8) — two copies
   inside one row. Unmeasured against the enum row by row; do not correct one cell and call it
   done — the remedy is a pointer to the generated contract or a generated table.
6. **Vector-index label set.** `services_bootstrap/compose.py` creates six (`Entity`,
   `ContentChunk`, `ReferenceChunk`, `Ku`, `PathStep`, `LearningPath`);
   `scripts/create_vector_indexes.py` `PRIORITY_ENTITIES` names eight (adds `Task`, `Goal`);
   CLAUDE.md said eight. Three copies, two values; which the live graph holds is unverified
   (the local MCP tool reaches the stopped sandbox, not Aura — `SHOW VECTOR INDEXES` there
   settles it). Index *names* are safe: creation and query both compute
   `{label.lower()}_embedding_idx`. **Remedy:** one constant both importers read; CLAUDE.md's
   enumeration is deleted here.
7. **`EntityType → label`.** `_ENTITY_TYPE_TO_LABEL` in `core/models/enums/neo_labels.py`
   (25, the accessor's source), `ENTITY_TYPE_TO_LABEL` in `core/models/relationship_registry.py`
   (25 strings, one consumer: ingestion config), plus `EMBEDDING_NODE_LABELS` above. All agree
   today; nothing pins the two full maps to each other or to completeness (a missing key is a
   `KeyError` at first use, not at import). **Remedy:** derive both string maps from
   `NeoLabel.from_entity_type`.
8. **Vendored-asset versions.** `ui/theme.py` `HTMX_VERSION` / `ALPINE_VERSION` ↔
   `static/service-worker.js` `PRECACHE_URLS` ↔ the files under `static/vendor/`. In sync
   today (fourteen precache entries, all present); protected only by CLAUDE.md's "touches two
   files" warning — a discipline. A miss breaks `cache.addAll()` and service-worker install for
   every PWA client. **Remedy:** a pin test in the `AuraDBCaps` style — every `/static/`
   precache entry exists on disk, each `*_VERSION` appears in the precache list.
9. **Counts in prose — guarded, true, or now removed.** 25 EntityTypes, 14 statuses, 12
   searchable domains, 14 alert rules, 4 dashboards, 15 ingestion configs: measured true, and
   **none is pinned to the prose that states it** (no test asserts `len(EntityType) == 25`; the
   content-origin table is the only CLAUDE.md membership claim a test reads). "25" recurs
   across many docs; a 26th EntityType makes every copy stale — the cheap pin, if ever wanted,
   is `test_content_origin_docs.py`'s group-phrase pattern (assert the number in the phrase
   against the enum). Ruled leave. Alpine "22 shared / 26 total" was true but unpinned
   (`tests/unit/docs/test_alpine_docs_registry.py` derives the registry and pins the two
   complete-registry docs, not CLAUDE.md) and had drifted once before — replaced by the rule.
   CLAUDE.md's content-origin table stays: it is pinned. ⚠️ Measuring is itself a copy-reading
   act: the census regex for "Supported:" over-captured into the next sentence and reported a
   false extra rule — print the numbers, then check one by hand.
10. **Leave, by ruling** — the duplication is cheaper than any fix: `dev` help text vs its case
    labels (one drift today: `typecheck-strict` has no help line; one file, low harm);
    `HEALTH_CHECKS.md`'s file-structure tree (an `ls`; delete on next touch); root `AGENTS.md`
    (declares `app/CLAUDE.md` authoritative).

**RULED 2026-08-29 (Mike): yes — a stale PLANNED marking fails `--check`.** "If it renders as
stale it registers as a fail; we don't stale xyz." SKUEL026 parity: a registration that
registers nothing is a failure.

The objection that had recommended *advisory* — that the name-collision mask would force a
still-staged method out of the tier — was **not a reason to weaken the ruling; it was a
detector bug**, and measuring settled it: `planned-marking-stale` fired exactly twice, both on
the attendee pair, and both markings were **true** (the methods are still unwired; the only
production calls are the mixin's own `self.backend.add_attendee(...)`). So the fix was to make
"stale" mean stale, then gate on it:

- **Stale means exactly one thing: the subject is GONE** — the only fact the detector
  establishes without inference. It is a `WARNING` in all three tiers.
- **"Looks wired now" never gates.** Three Codex rounds on #1188 found the same defect in each
  tier in turn: a definition-site count catches only the def-side collision
  (`VultureScan.used_names` is global by attribute name, so one `x.name` load masks a single-def
  method); `_collect_rendered_template_ids` is receiver-blind, so `settings.get("<template_id>")`
  fabricates a became-live report; and publish resolution uses a file-scoped variable index plus
  class registries, so a sibling's publish resolves for every class in the registry. The pattern
  is not three bugs but one: **every liveness engine here over-approximates by design**, because
  the module's rule permits over-approximation only to SUPPRESS an accusation. Gating any
  became-live signal inverts it. All three now report `planned-marking-masked` (INFO) — printed
  in their own report block and by the janitor, never demanded.
- All seven `planned-marking-stale` emissions are `WARNING`, so `--check` (`./dev quality`
  check 7 + the CI lint job) fails on them, and the janitor's existing WARNING block prints
  them for free. A masked block was added beside it, because an INFO finding no reader prints
  is the defect this whole section is about.
- The gate landed **green**: true stale count is 0, masked count is 2.

**Build order if scheduled** — each is small; item 2 is DONE (above), the rest unscheduled:
~~the janitor floor for stale markings~~ → the health-check single source + parity test (the `updated:` guard's "update all three"
collapses to one edit) → the precache pin test → the three derivations (worker subscribe,
`EMBEDDING_NODE_LABELS`, `ENTITY_TYPE_TO_LABEL`; each deletes more than it adds) → the
suppressible-rules docs test → one vector-index constant. Do not build a same-file
contradictory-prose detector (sub-finding above) or a free-prose count checker: the count
claims that matter are pinned or gone, and "N things" in running text has no reliable anchor.

---

## Dead-Doc-Links Instrument — Rulings + Scheduled Work (REGISTERED 2026-09-01)

`scripts/health/dead_doc_links.py` (in `./dev health` + the weekly janitor; not a CI gate)
has sat red at **871 findings / 531 distinct missing targets** (measured 2026-09-01,
re-measured same day on `eb6aad6af`, and confirmed again by the classification pass on
`e2e5b7f4a` — identical). An always-on check reporting 871
findings is one nobody reads. The findings decompose into classes (re-derive by driving
`check_file()` over `get_md_files()` — never trust these counts as current; the
route-shaped row overlaps the live-docs row and the freeform-file counts overlap the
parser row, so rows no longer sum to 871 — the authoritative recount is B1's exit
measurement):

| Class | Findings | Disposition (Mike, 2026-09-01) |
|---|---|---|
| Parser false positives (subscript-as-link ×30, globs in the bare pass ×7, ` + ` joins ×10, un-decoded `%20` ×1-real) | 47 | **APPROVED** — PR B1 |
| Route-shaped targets — application-URL links read as filesystem paths: 18 extension-less absolute link targets + 15 backticked PWA URLs (offline.html, manifest.json, service-worker.js served at root — registered in `adapters/inbound/pwa_routes.py`) | ~33 | **PR B1 investigation** (Codex on #1214, both rounds) — the class is defined by MATCHING a live route registration, never by shape alone: ⚠️ 5 of the 18 are genuinely dead (`/journals/browse` ×3 — registered nowhere, and a stale docstring in `adapters/inbound/user_entry_ui.py` claims it lives in `journals_routes.py`; `/yaml_templates/_schemas/` ×2 — neither route nor directory). Matched targets are not rot and a sweep must not rewrite them; UNMATCHED ones stay red and join the post-B1 sweep queue |
| The two freeform design-principles files (`direction w structuring.md` 20, `dp - emergence, patience, non-attachment.md` 16 — links point into the Obsidian vault, unvalidatable by construction) + `.claude/skills/_templates/` (placeholder paths) | 36 + 14 | **APPROVED** — PR B1 carve-outs; ⚠️ scoped to the two MEASURED files, NOT the directory (Codex on #1214): `design-principles/` also holds maintained specs with genuine rot — `HUB_PAGES.md` cites a teaching-hub view module that no longer exists — which must stay visible |
| Generated `CROSS_REFERENCE_INDEX.md` (slug-less ADR links) | 30 | **RULED** — PR B2, glob-with-loud-failure |
| History dirs (`migrations/` 206, `roadmap/done/` 12, `Reviews/`+`investigations/` 16 → 226 after parser dedup) | 226 | **RULED 2026-09-01** — silent dir carve-out; directory membership IS the classification (PR B3) |
| ADRs (`docs/decisions/`, 50 files; mixed faithful history and standing contracts) | 156 | **RULED 2026-09-01** — per-citation historical marker, option (d); measured split 81 standing / 70 narrative / 3 ambiguous of 154 (PR B3 mechanism + PR B4 sweep) |
| Live docs — real rot | 367 | **RULED** — sweep queue below |

**PR B1 (scheduled, fresh context):** the four parser narrowings — each targets a measured
shape, is measured against the live tree, and is pinned by a case in
`tests/unit/scripts/test_dead_doc_links.py` (the module's own PLACEHOLDER discipline) —
plus the carve-outs with per-entry reasons and the skip count printed in every run
(`duplicate_headings.py` shape): the TWO measured freeform files in `design-principles/`
(never the whole directory — its maintained specs carry genuine rot that must stay
visible) and the `_templates/` directory. Plus the route-shaped investigation: decide
in-PR how link targets that are registered application routes (extension-less absolutes,
the backticked PWA URLs) are recognized — classify against the live route registrations,
never a hand list of URLs.
⚠️ No blanket space-rejection in `_looks_like_local_path`: quoted fence spans deliberately
keep the real `docs/design-principles/direction w structuring.md` whole so a DEAD
space-bearing path stays detectable (Codex, PR #872). Expected roughly 871 → 745–780
depending on the route mechanism; the exit measurement is the authority.

**PR B2 (scheduled, fresh context):** the generator links ADRs as bare `ADR-NNN.md` under
`docs/decisions/` but real ADRs carry slugs — 12 of its 13 distinct ADR link targets are dead. Ruling:
resolve bare numbers by glob, **fail loudly naming every candidate on zero or ≥2 hits —
never pick silently**; a ref already ending `.md` is a full filename (verify it exists).
The loud failure forces the collision unblock in the same PR: the metadata's three
colliding refs get full filenames, promoting intent already recorded in YAML comments
(vis-network + neo4j-cypher-patterns `ADR-037` → `…lateral-relationships-visualization-phase5.md`;
user-context-intelligence `ADR-030` → `…usercontext-file-consolidation.md`).
⚠️ `validate_cross_references.py` must move in the same PR — its `adr_map` is
last-wins-silent on duplicate numbers, and both scripts share a `.md.md` hazard on
full-filename refs; they are the only two `related_adrs` consumers (verified 2026-09-01).
⚠️ So must the generator's sort key (Codex on #1214): `_parse_adr_number` does
`int(adr_id.replace("ADR-", ""))`, which raises `ValueError` on a full-filename ref —
extract the leading number instead of assuming the whole remainder is numeric.
Add the honesty guard that would have caught this at birth: every rendered
`/docs/decisions/` link target exists. Expected −30.

**PR B3 (scheduled, fresh context; after B1 — it edits the same scanner):** the ruled
history-line mechanism. (i) **Silent dir carve-out** for `docs/migrations/` +
`docs/roadmap/done/` + `docs/Reviews/` + `docs/investigations/` — directory membership
IS the classification (de-fiction: dated logs = LEAVE); these dirs carry no tripwire,
silence is sanctioned. (ii) **Per-citation historical marker** for `docs/decisions/`:
the scanner skips a marked citation ONLY when its target is dead; **marked-but-alive is
itself a finding** (the SKUEL026 inversion); the per-run output prints the
skipped-marker count (`duplicate_headings.py` shape). Marker syntax is decided in-PR,
measured against the live tree and pinned by cases in
`tests/unit/scripts/test_dead_doc_links.py`. Steady state: red inside `decisions/`
means rot in the authority tier — observability is inherent, no report-only section
needed. (iii) Decide in-PR whether `docs/decisions/ADR-TEMPLATE.md` joins the template
carve-out (same species as `.claude/skills/_templates/` — its example paths are
fictional by design; 1 finding).

**PR B4 (scheduled, fresh context; after B3 — the marker must exist to apply):** the
ADR content sweep, working from the classification pass's verified worksheet (scratch
tier — the B4 arc prompt carries the pointer). Fix the **81 standing-contract
findings**: ≈40 have a verified unique successor (e.g. `user_context_queries.py` →
`adapters/persistence/neo4j/`, `domain_configs.py` → `core/models/relationship_registry.py`,
`core/auth/{roles,session}.py` → `adapters/inbound/auth/`, `ku_enums.py` →
`entity_enums.py`, `learning_ui.py` → the ku/path_steps/pathways trio); ≈17 cite
deleted-no-successor targets (prose edit or supersession note — ADR-027 gets the
supersession note: its entire subject, the KnowledgeCarrier protocol, was deleted as
unused); ≈15 were never tracked in this repo (the early query-ADRs' "Tests: N/N
passing" lines — de-fiction the claim, don't invent a path). Apply the marker to the
~70 narrative citations. Execute the content rulings recorded below (delete ADR-010;
delete never-to-be-done planned citations; ADR-003 chain-completion + repoint;
create the UserEntry domain doc — `user_entry.md` under `docs/domains/`, spelled
indirectly here so the plan itself is not a scanner finding before B4 creates it)
**with their catalog ripple** (Codex on #1216):
deleting ADR-010 must also drop its `docs/INDEX.md` row (line 248 today), and the new
`user_entry.md` joins the domain catalogs — `docs/domains/README.md`'s Submissions row
still links the deleted `submissions.md` and becomes the UserEntry row; add an
INDEX.md entry if the domains are cataloged there. Splitting by cluster into more
than one PR is sanctioned if the diff is unwieldy. Exit: `docs/decisions/` findings
= 0 AND the full scanner run shows no NEW findings introduced by the sweep's own
deletions/creations (a `decisions/`-only check would miss an orphaned INDEX.md row),
marker skips printed.

**RULED — the history line (226 + 156) (Mike, 2026-09-01, on the classification pass's
report):** C takes **(a)** — the silent dir carve-out (no tripwire to un-observe). D
takes **(d)** — the per-citation historical marker, the option whose steady state makes
red mean rot inside the authority tier. The measured split decided it: of 154
classifiable `decisions/` findings (167 raw − 11 parser-class − 2 route-matched PWA),
**81 (53%) are standing-contract rot across 31 Accepted/Implemented ADRs, 70 are
narrative, 3 ambiguous** — the cheap arm (report-separately-don't-red) was conditioned
on ~all-narrative with "first observed standing-contract rot in an Accepted ADR" as its
reopening tripwire, a condition this measurement shows already fired 81 times over.
Content rulings from the same sitting: **(1)** planned-work citations advertising work
that must never be done are DELETED, not marked — unchecked "[ ] Create X" checklist
items and "(if exists)" hedges included (ADR-027:221 is the precedent). **(2)**
ADR-003:379's historical note gets its chain completed (Journal → Reports → UserEntry),
its `See` repointed at ADR-054, **and** a `user_entry.md` created under
`docs/domains/` — the
domains set documents 12 domains and is missing its busiest. **(3)**
`ADR-010-moc-core-service-query.md` is an unfilled template shell (its Decision section
is ADR-TEMPLATE's instructions + example block verbatim) — DELETE it; the number stays
retired (numbering already has gaps and duplicates). **The 3 ambiguous findings each
resolve under these rulings — B4 needs no further decision:** ADR-003:379 → (2);
ADR-037-embedding-infrastructure-separation:173 (the "(if exists)" hedge) → (1), delete
the line or repoint at ADR-068/ADR-074; ADR-027:221 → (1), delete the checklist item
alongside the supersession note. ⚠️ Standing constraints survive
the ruling: ADR findings stay OBSERVED (a silent `decisions/` carve-out remains off the
menu — Codex on #1215), and status-scoping stays FALSIFIED (2 of 89 Superseded; the
mixing is INTRA-file — reconfirmed by the pass: ADR-011/012 hold exemplary narrative
corrections lines above standing rot). Do not resurrect either.

**ADR classification pass (EXECUTED 2026-09-01):** full read, no sampling — all 154
findings classified from their surrounding paragraphs, every standing-contract case
verified against git history (`git log --follow` / `git ls-files` / `git grep`) before
classification; a citation was called "never tracked" only on empty `git log` since the
consolidation initial commit. Scanner residue landed entirely inside B1's approved
classes (11 parser-class + 2 PWA URLs matching `adapters/inbound/pwa_routes.py`) —
nothing new for B1. The worksheet (per-finding anchors, verified successors, quoted
ambiguous cases) is the pass's report in the scratch tier; PR B4's arc prompt carries
the pointer — this doc deliberately does not. Graduating it into `docs/` was considered
and rejected (Codex on #1216): a document consisting of ~150 intentionally-dead paths
would itself become ~150 scanner findings — the noise this section exists to remove.
**Fallback if the worksheet is unavailable** (fresh clone/worktree — scratch is
machine-local): B4 re-derives it by the recorded procedure — drive `check_file()` over
`docs/decisions/`, classify each finding by its surrounding paragraph
(narrative/standing/ambiguous), verify every standing case against git history — with
the split recorded above as the expected shape; re-derivation is mandatory for the
counts anyway, never guessed.

**Live-docs sweep queue (RULED: register + burn down via doc sweeps):** ~367 findings in
live docs — patterns 103 · skills 48 · intelligence 41 · architecture 35 · domains 32 ·
guides 30 · roadmap-live 14 · reference 13 · ui 11 · misc ~40 (2026-09-01) — ⚠️ **counts
contaminated by the route-shaped class above** (Codex on #1214: `VOICE_JOURNALING_AND_OBSIDIAN_GUIDE.md`'s
13 findings are ALL valid route links; `PWA_ARCHITECTURE.md` is 9 valid PWA URLs + 1 real).
**The queue is not actionable until PR B1 lands and the residue is recounted** — a sweep
run today would rewrite valid user-facing links. The tail shape survives the caveat: of
231 distinct targets only 36 have a unique same-basename relocation candidate; most are
genuinely deleted files, so the usual fix is editing the citing PROSE, not swapping a
path — a rename map cannot carry this queue. **Protocol (post-B1):** any sweep or PR
touching a listed doc fixes its dead links as a ride-along after checking route-shaped
targets against live route registrations; confirmed real heavy hitters
(`UI_COMPONENT_PATTERNS.md` 12 · `COMPONENT_CATALOG.md` 11 — deleted `ui/*.py` citations)
can be dedicated small sweeps. A bulk correction script, if one ever emerges, re-derives
its premise at run time and aborts on surprise — a heuristic proposes, never rewrites.

**Noted, unscheduled — duplicate ADR numbers:** ADR-030 exists three times
(`curriculum-domain-unification`, `dual-track-assessment-pattern`,
`usercontext-file-consolidation`) and ADR-037 twice (`embedding-infrastructure-separation`,
`lateral-relationships-visualization-phase5`). PR B2's metadata unblock routes around the
collisions; it does not remove them. Renumbering is a citation-update campaign — Mike
decides if/when; nothing schedules it.

## Review Schedule

Review this document at the **September 2026 quarterly review**. Checklist:

| Item | Trigger | Check |
|------|---------|-------|
| Semantic Analysis residue (ZPD semantic pool expansion; 3-item remainder SHIPPED #598–#600) | Engagement edges exist (entry-enrichment arc) | Ku engagement edge count > 0 |
| Discovery Analytics Phases 2+ (logging shipped 2026-07-10) | Search events ≥ 1,000 — ⚠️ **measured 41 on 2026-08-25**, of which ~8 are genuine queries, flat since 2026-07-22. At the observed rate the gate cannot fire; **re-base the number or retire the row** rather than re-checking it | `MATCH (e:SearchEvent) RETURN count(e)` |
| Real-time Intelligence | DAU ≥ 10 for 2+ weeks | Grafana `skuel_daily_active_users` |
| Per-user intelligence tier | Billing model defined | Business decision |
| KnowledgeConfig validation | Config fields added | `grep embedding_model core/config/unified_config.py` |
| `filter_property` extension | A consumer wants non-GOALS edge tier buckets | Product need (not a data threshold) |
| Knowledge Ku↔Ku prerequisites (Option B) | A consumer reads prereq/dependent Ku buckets | Product need (not a data threshold) |
| Task `dependent_task_uids` | A consumer reads a task's dependents | Product need (not a data threshold) |
| Content-linting survivors (NOUS vocabulary check; orphan detection at lint time) | Authoring volume makes silent nous typos / orphan drift a lived problem | Ride-along on `ingestion/validator.py` |
| Principles `_validate_update` reform or deletion | Next substantive touch of the Principles update path | Ruling needed — see the section's landmine note |
| EntryReport / ActivityReport search | A teacher workflow wants direct report-content search | Product need (not a data threshold) |
| Domain-level fulltext-first text search (D1(b)) — ruled DEFERRED **twice** (2026-08-16, 2026-08-25) | A consumer wants relevance ranking for the domains remaining on `/search` after the facet redesign (shipped #1155–#1160) — the 6 Activity Domains + Ku, which is now the whole surface | ⚠️ scope INVERTED, do not scope from the bullet list; the OWNER_ONLY edge-vs-property "ruling needed" is STALE — already closed, do not re-open. Product need (not a data threshold); read the section's two rulings first. It also now OWNS the "Relevance" fiction — do not tidy that label away |
| Profile-side search for UserEntry, Exercise **and RevisedExercise** (the `/search` facet redesign's one open obligation) | Mike schedules it — the strip landed first by his sequencing (#1155), so the trigger is the build half, not a data threshold | ⚠️ all THREE domains, not two: a two-domain build leaves revision artifacts unsearchable. Read the section, then `done/search-facet-redesign.md` for the arc's rulings. When Reports gains a search box, the EntryReport / ActivityReport row above has fired too |
| ZPD snapshot history & trend analysis | A ZPD-over-time consumer exists | Product need + `MATCH (h:ZPDHistory) RETURN count(h)` for accrual |
| Habit rows in the weekly-note panel | Lived weekly-review use wants the backward look | Product need (not a data threshold) |
| Non-positive-duration follow-ups (habit `0m` on `/today` / proposes `15`) | Next touch of either surface | Ride-along, not standalone |
| Monthly-template vault cleanup | Founder vault pass | Founder-owned, non-repo |
| Monthly-note panel parity | Lived monthly-note use wants the weekly panel | Product need (not a data threshold) |
| Tasks/Events edge-clear on edit (`""` → None) | Next touch of the Tasks/Events edit forms | Ride-along; re-verify the bug still reproduces first |
| Skill↔doc backlink reconciliation | Docs-taxonomy pass — ruling needed per warning, not a rote edit | `uv run python scripts/validate_cross_references.py --verbose` |
| Drifted `## Related Skills` body sections (3 of 35) | Next `docs/patterns` sweep already touching these files | `uv run python scripts/sync_cross_references.py --all --dry-run` |
| Event attendance wiring (`ATTENDS`) — staged since the ownership bundle | Mike schedules it — a future arc on his explicit decision (ADR-086 § Follow-ups) | See the section; the obligations live in ADR-086 § 3 + § Follow-ups, not in a second copy here; what `./dev bloat` says about the triple is ruled in § Catalog Copies in Code |
| LP recommendation backend methods (ruled *build, not now* 2026-08-20) | Mike schedules it — full feature: backend methods + frozen contract + consumer surface | Case file `lp-backend-recommendation-methods.md`; the 3 `Any` handles + their comments are the in-code markers |
| `KnowledgePracticed` subscriber (ruled "earns a subscriber" 2026-08-21) | A review-scheduling / spaced-repetition surface is scheduled | `git grep -l "subscribe(KnowledgePracticed"` — empty until wired; see the section |
| Per-node substance counters — the unread arm (ruled "keep staged" 2026-08-21) | A substantiation UI/surface is scheduled | `git grep -n "get_substantiation_gaps\|is_well_practiced" -- "ui/" "adapters/inbound/"` — empty until wired; see the section (incl. the retroactive-credit question) |
| R4 vault inbound propagation — parked build | Mike schedules it (product decision) | See the section — sketch + the #1143 r5 rejection; parsed-line vs entity state, never hash |
| Vault task door publishes no task events | R4 build or next vault-door touch | `git grep -n "event_bus" adapters/persistence/neo4j/bulk_upsert_backend.py` — empty until wired |
| Line deletions leave `EXTRACTED_FROM` edges | R4 build or next reconciler touch | Census shape in the section; re-probe the W28 edges before building |
| `UserLearningIntelligence` write-only fields (hollow since their sources were deleted) | Owner's ruling, or next touch of `PsAdaptiveService` | `git grep -n "intelligence\." core/services/ps/ps_adaptive_service.py` — assignments with no matching read |
| Habit streak counters (lost-update + future-day credit) | Next touch of the streak write path, or a lived wrong-streak report | Ruling needed on `current_streak` semantics — see the section |
| Unwired `HabitCompletion` model methods | A consumer wants one, or next Habits model touch | `git grep -n "is_streak_eligible\|was_completed_today" -- core/services/ adapters/ ui/` — empty until wired |
| "Vault has un-synced changes" signal | Mike schedules it — product decision (what the user is told), not a data threshold | See the section; ⚠️ must cover completions + 🆔 injections + new tasks, NOT reopens alone — no last-sync state is persisted today |
| `find_by` datetime string-binding (3 habit sites) | Next touch of any of the three reads, or a second `completed_at` writer | One PR: normalized range on a backend method (Pattern 10b / Key Rule 18b) |
| Habit-completion persistence bundle (#915 Codex "future care session": delete orphans / uid collision / non-atomic day uniqueness / stranded stats / DISTINCT-day query; + untrack refused-and-reported-success since #1100 and node doors publishing no `HabitCompleted`, both found on #1172) | Lived habit-completion use, or next touch of the completion write path | `MATCH (hc:HabitCompletion) RETURN count(hc)` **and** `MATCH (h:Habit) RETURN sum(h.total_completions), max(h.last_completed)` — nodes 0 / tally 0 / null on 2026-08-28 (tally > nodes = the node-less `/api/context` door was used); `SHOW CONSTRAINTS` lists none on the label. Built WITH the `find_by` row (one shared range predicate, two operations) but triggered by duplicate volume, moot once defect 3 lands; defect 3 needs Mike's one-per-day ruling first |
| `TaskUpdateRequest` future `completion_date` asymmetry | Next touch of `task_request.py` validators | Ruling needed — see the section; don't rule in passing |
| Per-domain chunking knobs + `chunk_type_weights` (fragment fix ✅ v2, 2026-08-30) | Tuning + Askesis intent-filter loosening: Mike schedules the eval set; type weights additionally need a content-typing classifier (79% `explanation` is the keyword FALLBACK, not the corpus) | `MATCH (c:ContentChunk) WHERE c.end_index < 5 RETURN count(*)` — **7** after the v2 re-chunk (all link-only MOC-style notes; a rise = new fragment-shaped ingestion; `end_index` = the persisted whitespace-aware `word_count`; pre-v2, 753 of 998 sat under the 50-word `min_chunk_size` — its value is the tuning question, not the defect); `git grep -n chunk_type_weights -- core/` empty until built |
| DSL-bridge grounding pair (goal-LINK persistence; `user_principles`/`recent_topics` to BOTH paths) | Keyed A/B on the next bridge touch; goal edges need Mike's ruling on AI-inferred writes | `git grep -c "user_principles="` and `git grep -c "recent_topics="` over `journal_service.py` + `user_entry_processing_service.py` — EACH argument in both files or neither (neither today); extracted tasks / tasks with a `FULFILLS_GOAL` edge = 56 / 0 on 2026-08-28 (count TASKS linked, not goals reached — ten tasks on one goal must read 10) |
| `HabitMissed` publisher-less chain (ruled keep-staged 2026-08-28) | A lived want for difficulty insights, or the streak-semantics ruling — rule the day model once | `git grep -n "HabitMissed(" -- core/ adapters/ scripts/ services_bootstrap/ ui/ ':!core/events/'` empty (scripts/ included — a one-shot publisher counts); `MATCH (i:Insight {insight_type: 'difficulty_pattern'}) RETURN count(i)` → 0 |
| Quarterly / yearly periodic notes (founder vault pass first) | The first real note in either vault folder | `find ~/0bsidian/skuel/periodic_notes/Quarterly ~/0bsidian/skuel/periodic_notes/yearly -type f \| wc -l` > 0 (files, not `ls` headings) — founder-owned, non-repo |
| PathStep → Ku wiring backlog (1 Ku-less step; 67 Kus composed by no step) | Mike's next `Ps_dev` content session | The three counts in the section, over all three composition edges (`USES_KU\|TRAINS_KU\|CONTAINS_KNOWLEDGE`, never `USES_KU` alone) — 1 / 67 / 67 on 2026-08-28 |
| py314 annotation sweeps — UP037 schedulable, TC002/TC003 never (home: ADR-067 § Deferred) | UP037: a churn window Mike picks; TC002/TC003: never | `uv run ruff check --select UP037 --statistics .`; baseline in the ADR |
| Parked features (activity ledger · interest/gravity · icon provider · templates re-homing) | Mike schedules each — feature work, never self-scoped | The four `git grep` checks in the section, all empty on 2026-08-28 |
| READY PLANNED entries over 90 days → wire-or-delete ruling (the `planned-ready-aging` finding, INFO, never gates) | Any READY entry in `scripts/detect_bloat.py` older than `READY_AGING_DAYS` — first fires 2026-09-10 on the three 2026-06-11 entries; by this review all seven READY are over it, which is the intended signal | `./dev bloat --ready` — every row listed is wire-or-delete; a DELAYED entry aging is expected and is NOT this row |
| Catalog copies in code — the duplicated-fact class (measured 2026-08-29) | Mike schedules the mechanical items; until then a ride-along: any PR that adds a health check, an embeddable type, a vector-index label, or a suppressible rule touches every copy the section names | ⛔ Do not scope from this cell — the section holds the inventory and the ruling. Re-measure: `uv run python scripts/detect_bloat.py --json` → count of `planned-marking-stale` findings (2 on 2026-08-29, seen by neither CI nor the janitor); the scripts named in `dev` § `health)` and in the janitor's `for check in` loop must be the same set (6 on 2026-09-01, up from 5 — `docs_updated.py` was added by hand to every copy) |
| Hollow embedding field maps — `PLANNED_EMBEDDING_MAPS` (4 DELAYED on 2026-08-30: `ENTRY_REPORT`, `ACTIVITY_REPORT`, `FORM_TEMPLATE`, `FORM_SUBMISSION`) | The EntryReport / ActivityReport search row above fires (the two report maps point at it), or a consumer wants form content in semantic search (the two form maps — no section, the registry reason is the one copy) | `./dev bloat` § Embedding field maps — every row is hollow by ruling; an unregistered hollow map already fails `--check` on its own. Wiring one = ADR-074's quartet, then delete its entry (the stale gate demands it) |
| Dead-doc-links PR B1 (parser fixes + route-shaped investigation + file-scoped freeform carve-outs) + PR B2 (ADR glob-with-loud-failure) — both APPROVED/RULED 2026-09-01 | Fresh-context sessions, one per PR — approved work, not waiting on data | `uv run python scripts/health/dead_doc_links.py` — B1's exit measurement is the authority (~745–780 expected, then −30 for B2); re-measure, never trust the snapshot. See the section |
| Dead-doc-links history line — **RULED 2026-09-01** (classification pass executed: 81 standing / 70 narrative / 3 ambiguous): ADRs = per-citation marker, 4 history dirs = silent carve-out; PR B3 (mechanism, after B1) + PR B4 (ADR sweep, after B3) | Fresh-context sessions, one per PR — ruled work, not waiting on data | The check stays red on `decisions/` + history dirs by design until B3/B4 land; rulings + content rulings in the section (status-scoping stays falsified — 2/89 Superseded) |
| Live-docs dead-link sweep queue (~367 pre-recount — ⚠️ NOT actionable until PR B1 lands: counts contaminated by valid route links, a sweep today would rewrite them) | Post-B1 recount, then ride-along on every doc sweep or PR touching a listed area; confirmed heavy hitters may get dedicated small sweeps | Re-derive per doc by running the scanner and filtering to the file; check route-shaped targets against live route registrations; fix the citing prose (most targets are deleted, not moved) |

**The document is the checklist, the table is a convenience:** a section added to this file
without a matching row here is still in review scope — walk every `##` section, then the table.

Items that hit their trigger condition before the next review should be unblocked immediately —
don't wait for the review.
