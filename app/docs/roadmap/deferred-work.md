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

So **the surface the shipped rung serves has never been used in production**, and the
surface that is used has had ~8 real queries in its lifetime. Corpus at the same date:
121 Ku · 25 PathStep · 2 LearningPath · 14 Exercise · 77 Task · 62 UserEntry. Relevance
ordering over ≤20 `CONTAINS` hits drawn from 121 nodes is a marginal difference, not a
fix.

**The valuable half has since INVERTED — do not scope from the bullet list above.** The
`/search` facet redesign ruled 2026-08-25 (its own section below) removes PathStep and
LearningPath from that surface entirely. The shipped rung covers exactly
Ku/PathStep/LearningPath — two of the three are leaving — while the six Activity Domains
being promoted to the primary facet are all `OWNER_ONLY`, i.e. the half this section
split off as harder: it needs `user_uid` threaded into the fulltext Cypher. Anything
built for curriculum relevance before the facet redesign lands would rank domains that
are leaving the page.

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

**Enable when** (unchanged in kind, sharpened in target): a consumer wants relevance-ranked
text search for the domains that remain on `/search` after the facet redesign — the six
Activity Domains and Ku. Product need, not a data threshold.

---

## `/search` Facet Redesign — Ruled *Build, Not Now* (2026-08-25)

Mike's design, ruled in full on 2026-08-25 after a code trace of both search surfaces.
**Nothing is built.** The shape below is the contract for whenever it is scheduled; it is
recorded now because it changes what the D1(b) section above is worth (see that section's
"the valuable half has since INVERTED").

**The design.** `/search` becomes one surface with one job — *your lived activity, plus the
knowledge behind it*:

| Control | Today | Ruled |
|---|---|---|
| Primary scope facet | "Type" — 10 entity types, curriculum and activity mixed flat | **Activity Domains** — Task, Goal, Habit, Event, Choice, Principle |
| Knowledge facet | "Nous" + dependent sub-topic column | **unchanged, keeps the name "Nous"** |
| Ku | a "Knowledge Units" row in the Type dropdown | reached through the Nous facet |
| PathStep, LearningPath | Type dropdown rows | **removed — from the dropdown AND from the results** |
| "My Entries" (UserEntry) | a Type dropdown row | **stays** |

**Why removing curriculum costs nothing: it is a duplicate surface, not a capability.**
`/explore/library` is billed as "Explore all knowledge units and path steps", runs the same
`SearchRouter.faceted_search` path, and carries the richer facet set (tags, NOUS,
sub-topic, learning level) plus Load-more pagination that actually works. The curriculum
half of `/search` is a second, worse copy of it. This item is therefore directive item 2
(remove the unnecessary), not feature building — with one genuine addition, below.

**Ride-along that is NOT optional: LearningPath must join the library catalog.**
`_library_search_request` (`adapters/inbound/explore_ui.py`) scopes the catalog to
`[EntityType.KU, EntityType.PATH_STEP]`. Remove LP from `/search` without adding it there
and LP becomes findable by text **nowhere**. It is part of the same change — the library
page's own subtitle already promises more than the catalog delivers once LP has no other
home.

⚠️ **It is NOT "one list literal" — the card renderer must move too.** `_library_cards`
(`ui/explore/cards.py`) branches on `is_ku` and sends **everything else** to a hard-coded
"Path Step" pill and `/explore/ps/{uid}`. Add LPs to the catalog without touching it and
every LearningPath renders as a mislabeled Path Step card with a dead detail link
(LPs live at `/lp/{uid}`). The fix is available rather than new: `entity_detail_href`
(`ui/patterns/entity_links.py`) already maps `learning_path` → `/lp`, so adopt the shared
helper instead of extending the two-way branch to three. Card pill likewise needs a real
per-type value. (Caught by Codex on #1153.)

**Rulings that were decisions, not defaults** — each was posed and answered:

1. **Removal is from the results, not just the filter.** A filter-only removal would leave
   an unfiltered search still returning PathSteps the user can no longer filter to.
2. **"My Entries" stays.** It is the ONLY UserEntry text search in the application —
   `user_entry_ui.py`, `user_entry_routes.py` and `user_entry_api.py` contain zero search
   references, and the journals sidebar's search is conversation sessions, not entries.
   Removing the row would delete the capability outright for 62 live entries. It also fits
   the new framing: entries are lived output, not curriculum.
3. **The Nous facet keeps its name.** "Nous → Ku" was considered and rejected: NOUS is the
   official *grouping* of Kus (the magazine metaphor; `Heading: H3` anchors), a vault-derived
   vocabulary — not an entity-type label, which is what the rename would make it. ⚠️ The
   rename would ALSO have been false while PathStep remained: `nous` is a property on **both**
   Ku and PathStep (112 Ku vault files carry it; 14 of 28 Ps files do), so the facet returns
   PS rows today. The two halves of the original proposal were load-bearing on each other.

**Known fiction this redesign does NOT repair — deliberately left standing.** `/search`'s
sort dropdown offers **"Relevance"**, it is the DEFAULT, and no path behind it ranks by
text relevance. What it actually does depends on the request shape — three behaviours
under one label, none of them BM25:

| Request shape | What "Relevance" does |
|---|---|
| **Single domain** (a Type choice, or a facet resolving to one domain) | `RELEVANCE.get_sort_field()` returns `None` → the backend falls back to the domain's `search_order_by DESC`. Here it IS "Recently Updated" for Ku/PS/LP, "Newest First" for the Activity Domains, event-date for Events — two dropdown entries, one behaviour. |
| **Cross-domain, pure text, no facets** (the default landing shape) | `wants_faceted` is False → `search_domains`, the scored sweep, capped at `limit//6` per domain. A real distinct behaviour — a *score*, just not a text-relevance score. |
| **Cross-domain with any facet/tag/relationship filter** | `_faceted_sweep`, then `zip_longest` **round-robin interleave** across domains — not ordering by anything. |

⚠️ Do not restate this as a flat "Relevance means recency" — that is true only of the
single-domain row, and #1153 shipped that overstatement before Codex corrected it. The
defect is that one label covers three behaviours and advertises a fourth.
`ui/explore/cards.py` already excludes RELEVANCE from the library's
sorts *deliberately*, for a different reason (it bypasses the pageable sweep), so `/search`
is the inconsistent surface. This is the same class the July 2026 pass deleted ("no fake
options") — but it is **left in place on purpose**: Mike's intent is to make the label
true (D1(b), scoped to the domains that remain) rather than to relabel it away. Do not
"tidy" it in a passing PR; that would spend the one lever that makes the ranking work
visible.

**Dependency order** (the reason this is ruled but not built):

1. This facet redesign — decides which domains `/search` must rank at all.
2. Then D1(b), re-scoped to the six Activity Domains + Ku, which requires the OWNER_ONLY
   ownership ruling (edge vs property) called out in that section.

Building (2) first ranks domains that are leaving the page.

**Enable when**: Mike schedules it — product decision (what `/search` is *for*), not a data
threshold. The usage census in the D1(b) section is the honest backdrop: ~8 genuine
queries in the surface's lifetime, most recent 2026-07-22.

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

## `:OWNS` Writers That Skip `user_uid` — ✅ RESOLVED (ownership bundle PR-2, 2026-08-21)

The write-side facet of the ownership bundle, closed by ADR-086 + the residue collapse
(arc contract PR-2). Deleted outright: the registry `ownership_relationship` field and its
paper `HAS_*`/`MADE_REFLECTION` enum family (zero such edges ever existed in the graph),
`UnifiedRelationshipService.create_user_relationship`/`delete_user_relationship`, the
backend generic pair in `_user_entity_mixin.py` (the one interpolation that could write a
`HAS_*` edge), and the four gravity writers
(`create_user_goal/habit/principle/event_relationship`). `is_ownership_relationship()` now
traits `OWNS` alone, and the regenerated `GRAPH_CONTRACT.yaml` stopped documenting
never-written edges as "ownership".

The attendee triple (`add_attendee`/`remove_attendee`/`get_event_attendees`) survived,
retargeted onto the designed `(User)-[:ATTENDS {joined_at, role, added_by, status}]->(Event)`
shape with the invite→accept consent state machine (actor always a service parameter from
the auth layer, never the request body) — still STAGED in `PLANNED_METHODS`; the wiring
obligations (self-add eligibility gate, `OWNER_OR_ATTENDEE` visibility, creator
auto-attend, ghost filter, `max_attendees`, role enum) are recorded in ADR-086.

**Correction recorded while retiring:** the original section claimed faceted search
"hard-anchors `(User)-[:OWNS]->`" — stale since #1079: `faceted_search_raw` is
property-scoped and fail-closed (`has_user=True`). Today's `:OWNS` readers are the
MEGA-QUERY/CONSOLIDATED anchors (`user_context_queries.py`), `get_user_entities`, the GDPR
cascade, and one SCOPE_AWARE disjunct.

**Deferred design note — adoption/gravity (recorded, unscheduled):** the deleted gravity
writers expressed "this user has pulled this entity into their orbit" (adoption,
engagement) — a semantic that is *not* ownership. If SKUEL wants it later, it returns as
its own named edge with its own design, never by resurrecting the `HAS_*` family
(ADR-086 § 2).

### Completion stamping — ✅ RESOLVED (completion-stamping arc, 2026-08-22)

The residue: `get_recent_activities` read `coalesce(completion_date[, achieved_date],
updated_at)` (#1116), and `updated_at` is a *mutable* proxy — editing a long-completed task
re-dated its "completion" and bounced it to the top. Only the explicit complete paths
stamped anything (measured 5/85 on the live graph).

Closed by a four-PR arc: canonical fields per domain (#1122), the shared transition helper
wired at all six `update_<domain>` chokepoints plus `EntityType.valid_statuses()`
enforcement (#1123), Goals reopen alignment (#1124), and the read + vault + backfill pass
(this PR). What the fix is, in one line: **every transition into COMPLETED stamps the
domain's canonical field, every transition out clears it, and nothing downstream reads
`updated_at` as a completion any more.**

- **Read** (`cross_domain_backend.get_recent_activities`): the stamp alone — Task
  `completion_date`, Goal `achieved_date`. The legacy Goal `completion_date` leg died with
  it. A completed row carrying no stamp is **excluded, not approximated** (truth over
  coverage — an absent row is honest, a wrong date is not).
- **Vault outbound** (`vault_reconciler`): the Obsidian `✅ date` comes from
  `task.completion_date`, falling back to today only for pre-stamp history. It used to come
  from `updated_at`, which rewrote the user's own file every time a long-done task was edited.
- **History**, frozen once: `scripts/backfill_activity_completion_stamps.py` sets
  `field = updated_at` where a completed node has no stamp. **Applied to the live graph
  2026-08-22** (AuraDB `d2d160c4`, measured first): 85 completed Tasks, 5 already stamped,
  80 frozen, 0 unstampable; zero completed Goals/Habits/Events/Choices, so Task was the only
  label with anything to do. Verified post-apply — 85/85 stamped, all `STRING` (writers
  persist ISO strings via `to_neo4j_node`; a native Neo4j DATE would read back fine and still
  be the wrong shape). `migrate_activity_completion_aliases.py` reran to a clean no-op:
  zero legacy `completion_date` rows, as PR-1's rerun already found.
- **`complete_task_with_cascade`** now gates its own stamp on the same transition rule
  (surfaced by Codex on #1124). It writes through the *generic* CRUD update, so the
  chokepoint helper never sees it — the stamp was unconditional, and two live callers
  re-enter behind an ownership check only (`POST /today/tasks/{uid}/complete`,
  `UserContextService.complete_task_with_context`), so a retry re-dated the completion and
  would now propagate into the vault `✅`.

✅ **RESOLVED by the cascade-idempotency arc (#1126–#1136, 2026-08-23).** Ruled: **the cascade
genuinely re-runs**, and the subscribers were made safe to repeat — a repeat complete stays a
real complete, so the repair path is preserved.

Two things this entry got wrong, kept here because the corrections are the useful part:

- **Three of the four listed effects were not real.** "Goal progress bumped again, habit
  reinforced again, knowledge mastery +0.1 again" described `logger.debug("Would …")` **stubs**
  (`_update_goal_progress`, `_reinforce_habit`, `_update_knowledge_mastery`). The fourth,
  "dependent tasks re-triggered", **was real** — `_trigger_task` wrote `{"status": "scheduled"}`
  through the generic CRUD with no read first, so it could reopen an already-completed dependent
  while leaving its `completion_date` set. Latent only because the graph has 0
  `TRIGGERS_ON_COMPLETION` edges, and it fired on a **first** completion too, not just a repeat.
  Fixed in #1128. What else actually re-ran: the `ProductivityAnalytics` counter, a duplicate
  `PersistedInsight` (**two** append sites, not one), the Prometheus counter, and the
  duration-calibration EMA.
- **The "offline PWA queue replay" vector does not exist** — `static/service-worker.js` has no
  background-sync or POST queue. The real vector was three deterministic clicks: complete → Undo →
  complete, because Today's Undo un-hid the card client-side without posting anything.

The mechanism is one signal, `TaskCompleted.is_repeat`, with the contract on the event class:
handlers that **recompute** ignore it; handlers that **count or append** skip on a repeat. A later
refinement (#1134) sharpened it further — the flag gates what **accumulates** (appends, stamps),
never what **derives**. See `core/events/task_events.py` for the authoritative statement.

✅ **The successor arc is CLOSED too — ADR-087, the conditional-write primitive
(#1145 / #1147 / #1148 / #1149 + its final PR, 2026-08-24).** Codex flagged the underlying
read-then-write race five times across the cascade arc (#1127, #1128, #1131, #1133, #1136) and
each rejection was scoped, not dismissive — the window was the one the completion stamps
already carry (#1123), so closing it closed both. Every status-bearing write in `core/services/`
now goes through `backend.update_with_status_guard`, which takes the node's write-lock BEFORE
reading the prior and hands that prior back; `is_repeat` is exact by construction, and
`completion_transition_patch` (the read-then-write form) is deleted — there is no second path.
The five stamping domains plus seven raw status writers migrated; Principles is the one
deliberate exception (target-only legality, prior-independent, so no race) and calls
`validate_status_target` for that check alone. See ADR-087 § Consequences / § Scope, and
CLAUDE.md § Status-Guarded Writes.

The residue PRs that preceded the arc are merged: #1139/#1140 (habit windows bounded both
ends), #1142 (`tasks_completed` derived at read; the reconcile instrument retired — never
resurrect), #1143 (the 🆔 is identity at ingest — Guard 2b).

R4 — vault **inbound** `[x]`-completion propagation — is ✅ dispositioned (ruled 2026-08-23;
docs corrected 2026-08-24): the `git log -S` discriminator ran, verdict **never wired**, the docs
now state the outbound-only truth (CLAUDE.md § Obsidian VaultBridge, ADR-070 status annotation,
both user guides), and the build is parked with a trigger and design sketch — see § R4 Vault
Inbound Propagation — Parked Build.

---

## `User.uid` Has No Index or Constraint — ✅ RESOLVED (ownership bundle PR-4, 2026-08-21)

Closed by ADR-086 §4. The open question ("index or *uniqueness constraint*?") resolved to a
**uniqueness constraint** — `uid` is the identity key (`user_<name>`) and the constraint
doubles as the seek index. `sync_auth_indexes` (`neo4j_schema_manager.py`) now creates
`User_uid_unique` as startup DDL, idempotent per boot (`IF NOT EXISTS`).

**Applied to the live graph 2026-08-21** (re-measured first: 6 users, zero duplicate `uid`s,
zero null `uid`s — built cleanly) by running the real `sync_auth_indexes` path against AuraDB
`d2d160c4`. Verified post-apply: `EXPLAIN MATCH (u:User {uid:$uid})-[:OWNS]->(e:Entity)` now
plans `NodeUniqueIndexSeek [UNIQUE u:User(uid)]` where it was `NodeByLabelScan` — the ~290
`MATCH (:User {uid: $…})` adapter call sites all inherit the seek.

⚠️ **Counting trap** preserved for anyone re-measuring those call sites: the f-string spelling
(`User {{uid:`) and the plain spelling (`User {uid:`) are disjoint substrings. Grepping one
undercounts by ~2×.

---

## `GroupService` Declares `OWNER_ONLY` But `Group` Has No `user_uid` — ✅ RESOLVED (ownership bundle PR-4, 2026-08-21)

Surfaced 2026-08-16 by Codex on PR #1079; closed by the ruling's **option 1** (ADR-086, arc
contract ruling 7): `DomainConfig` gained a **configurable ownership property** —
`ownership_property` (default `"user_uid"`, identifier-validated at construction and again at
the composition point) — and the `OWNER_ONLY` branch of `build_search_visibility_clause` now
renders `n.{ownership_property} = $user_uid`. The declaration threads from DomainConfig through
the service search mixin and `get_visible_to_user` into every strategy builder, riding with
`search_visibility`. `GroupService._config` declares `ownership_property="owner_uid"` — the
scoping claim its model can finally render.

What did NOT change, deliberately: Group stays absent from every search registry (wiring it in
remains a product decision — `test_group_is_not_a_searchable_domain` still pins it); no
`user_uid` was added to `Group` (the two-names-for-one-claim divergence #1078 closed);
Exercise's `owner_uid` half stays inside `SCOPE_AWARE` (its exemption is still earned by that
declaration, and the exemption set still asserts its own length — do not add Group to it). The
guard was tightened per the contract:
`TestOwnerOnlyDomainsCarryTheScopingProperty::test_every_searchable_owner_only_domain_declares_a_real_property`
now asserts every searchable OWNER_ONLY domain's **declared** property exists on its model.
Doc truth-up rode along in `docs/architecture/SEARCH_ARCHITECTURE.md` § Ownership Scoping.

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

## Backend-Typing Follow-on — ✅ QUEUE EMPTY (all 3 closed)

These outlived the backend-typing arc (#1090–#1102, closed 2026-08-20)
because none of them was a retype — each was a decision or a chain. The
standing ruling (Mike, 2026-08-20) was that a fresh context takes **ONE** of
them, not the set — and that is how they closed: A and B on 2026-08-20, C on
2026-08-21 riding the substance-write-grain arc. A fourth sibling — the LP
recommendation backend methods — was ruled *build, not now* and has its own
section above. The closed records stay because each carries residue notes and
never-resurrect rulings.

### A. ✅ CLOSED — The `DomainConfig` string chain (2026-08-20)

Re-running the census (as this register demanded) **falsified the item's
premise**: the chain was not merely string-typed — it was **severed**. Commit
`76d64a0d1` (2026-01-31) deleted the per-class values (e.g. KU's
`_prerequisite_relationships = [RelationshipName.REQUIRES_KNOWLEDGE.value]`)
pointing at DomainConfig as successor, but `BaseService.__init__` synced only
`dto_class`/`model_class` — the relationship tuples were computed at every
factory call, validated in `__post_init__`, and read by nobody. Every service
saw the empty default; the mixin's `get_prerequisites`/`get_enables` silently
returned `[]`, `add_prerequisite` always refused, and PR #1102's conversion
chokepoint was unreachable. No live path was affected (PsService's caller
overrides with its graph service; the lateral routes hardcode their enums).
The enables half was deader still: `_enables_relationships` had zero readers,
and the ruled `get_enables` design (KEEP, 2026-07-25) walks prerequisite edges
inward — nothing staged consumed it.

**Mike's rulings (2026-08-20):** reconnect + type the prerequisite chain;
delete the service-side enables plumbing. Executed: `DomainConfig
.prerequisite_relationships` is `tuple[RelationshipName, ...]`,
`BaseService.__init__` syncs it onto the instance (like `_dto_class`), both
mixins and the `prerequisite_traversal` / `prerequisite_chain_with_distance`
port+adapter carry enums (`.value` happens once, in the adapter, where enums
become Cypher edge patterns), the #1102 chokepoint is retired, and
`generate_enables_relationships` + `DomainConfig.enables_relationships` +
`_enables_relationships` are deleted (registry-side
`enables_relationship_names` stays — the graph contract reads it).
A regression test now pins the `__init__` sync.
Known residue (Codex on the PR, measured): the mixin's typed
`get_prerequisites` matches the domain label, so a curriculum domain's
Ku-typed prerequisites are silently excluded from that read — heterogeneous
chains belong to `prerequisite_chain_with_distance` (base-label match,
projected rows), which is what PsService's live path uses. Whoever wires the
PLANNED mixin consumers must pick the read accordingly.

### B. ✅ CLOSED — The `PsOperations` layering contradiction (2026-08-20)

Mike's hypothesis ("PsOperations is the backend protocol") was **confirmed by
census**, and the dual-layer doctrine it contradicted turned out to be drifted
fiction with a single, datable origin.

**Measured.** `PsOperations` declares 142 public callables. `PsBackend`
satisfies it; `PsService` implements **8**, diverges on 15, and is **missing
119** — including `execute_query`, `find_by`, `create_step_node`,
`faceted_search_raw`. Consumer census found **7** annotation sites, not the 5
this register claimed: six are backend handles (the factory's five plus
`PsAIService`, built outside it), all satisfied. The seventh —
`EntityExtractor.knowledge_service`, the "facade holder" the whole doctrine
rested on — called exactly **one** method (`get`) and arrived via
`AskesisDeps.knowledge_service: Any`, so its 142-member claim had never been
type-checked. Its four sibling params (`TasksOperations`, `GoalsOperations`,
`HabitsOperations`, `EventsOperations`) failed the identical probe: the
constructor was a uniform five-site instance of the trap, not a PS quirk.

**Provenance.** `git log -S "service-facing"` returns one commit: `862dafea4`
(PR #826, 2026-07-26). Commit 2 of that PR made `PsOperations` inherit the
backend slice; commit 3 reverted it on a Codex P1 whose rationale was the
dual-layer story — while that same commit message's own verification line
records "`EntityExtractor` never calls the ORGANIZES methods at all". The
revert accepted a remedy its own measurement falsifies. Every downstream
statement (the seam comment, the module docstring, `PsProgressBackendOperations`'
docstring, `BACKEND_OPERATIONS_ISP.md`'s "live example") descends from it.

**The un-composability constraint was real but irrelevant.** Re-verified: the
multiple-inheritance probe is still rejected — by the extra optional `limit`
param, *not* the `entity_uid`/`parent_uid` rename (mypy does not enforce
protocol parameter names at all under this config, so that divergence guarded
nothing). Composition was never the tool: **inheritance has no conflict,
because there is only one definition.**

**Executed.** All five `EntityExtractor` params type against `EntityLookup`,
promoted from `context_retriever.py` into `core/services/askesis/types.py`
alongside `KuLookup` (deleting the duplicate private `_EntityLookup`).
`PsOperations` inherits `PsOrganizesBackendOperations` **and**
`PsProgressBackendOperations` (Mike's ruling: take the progress slice too), so
both sets of signatures have one source; its 8 duplicate declarations are
deleted. `create_ps_sub_services(backend=)` **and** `PsService.__init__(backend=)`
are typed `PsOperations`; the `# boundary: ps-two-layer-divergence` comment is
gone. Naming: Mike ruled **state the layer, don't rename** — `KuOperations` /
`PsOperations` / `LpOperations` are all backend protocols wearing the
route-facing suffix, and renaming only PS would invent a new asymmetry. The
trio-wide rename stays an open naming question, deliberately untaken.

⚠️ **Typing the laundered handle found a real hole:** the moment the param
stopped being `Any`, mypy surfaced `PsService.attach_step_to_path` calling
`self.repo.get_next_step_sequence(...)` — a method `PsBackend` has always
implemented and the port had never declared. Now declared (cf. #1094).

### C. ✅ CLOSED — The lying `ku_backend` fixture (2026-08-21, with its vehicle)

`tests/integration/test_event_ku_practice_flow.py:61` — a fixture **named**
`ku_backend` that constructed a `PsBackend`. Ruled a rider, not a PR; closed
riding the substance-write-grain arc, exactly as scheduled — and riding it
mattered for the reason predicted: the arc's ruling (grain-agnostic, rename to
`knowledge_uid`) decided what the fixture should say. Executed: the fixture is
`ps_backend` (named for what it constructs), the seeded PathSteps carry honest
`ps.`-form uids instead of `ku.`-spelled ones, and a real `KuBackend`-backed
fixture now exists in the same file for the new grain-contract tests — so
`ku_backend` there means a Ku backend again.

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

| entry | facet of the same root |
|---|---|
| § `:OWNS` Writers That Skip `user_uid` | **write-side** — ✅ RESOLVED (ADR-086 + PR-2 residue collapse: paper channel deleted, attendee triple retargeted onto consent-carrying `ATTENDS`) |
| § `GroupService` Declares `OWNER_ONLY`… | **declaration-side** — ✅ RESOLVED (bundle PR-4: `DomainConfig.ownership_property`, Group declares `owner_uid`, guard test tightened to the declaration) |
| § `User.uid` Has No Index or Constraint | **index-side** — ✅ RESOLVED (bundle PR-4: `User_uid_unique` uniqueness constraint via startup DDL, applied live + `NodeUniqueIndexSeek` confirmed) |
| **this P1** | **read-side** — ✅ RESOLVED (ADR-085 G1+G2, bundle PR-3: `_fetch_entities_by_uid` reads through `get_visible_to_user`, and the MEGA-QUERY habit/task projections carry `user_uid = user.uid`) |

**Ruled 2026-08-21 (Mike): this is significant cross-cutting work and belongs to
a fresh context, taken with those three entries together rather than as four
separate fixes.** Whoever takes it should settle the general question — *what
enforces ownership on a read that does not go through SearchRouter?* — before
touching any single site. ⚠️ `CrudOperationsMixin.get` (`:135`) is used by every
domain; changing its signature is a repo-wide change, not a local one.

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

## ✅ Substance-Write Grain — ARC CLOSED (2026-08-21)

Scheduled 2026-08-20, executed 2026-08-21 with item C riding as planned. Full
case file (investigation record, falsified premises, probe method):
`docs/roadmap/done/substance-write-grain.md`. What follows is the closure
record; the two questions the arc *opened* have their own sections below.

**The census was re-run** (code @ `d57b3bf96`, graph = AuraDB `d2d160c4`,
2026-08-21) and confirmed the register's numbers, adding three findings it had
asked for:

1. **Provenance of the 28 user_entry→ku edges:** ALL 28 carry `inferred: true`
   — every surviving edge came from `EntryGroundingService` (vector grounding,
   `:Ku`-label-constrained Cypher), zero from the `@ku()` extraction door. The
   dominant channel is Ku-grain **by construction**.
2. **The task channel shows a clean roll-up signature:** `ku.mindfulness.breath`
   = 10 with both composing PathSteps = 10 each (consistent-with, not proof).
3. **Path 1 is a dead channel today:** ZERO `(event)-[:APPLIES_KNOWLEDGE]->()`
   edges exist; `times_practiced_in_events` = 0 everywhere; the docstring's
   third edge writer (`create_study_session`) no longer exists. The
   **double-count is latent, never fired** — creation publishes without writing
   an edge, completion reads only edges; they overlap only if the same
   knowledge is named in both places. Ruled: documented in both writers'
   docstrings, no guard machinery for a dead channel.

**Mike's rulings (2026-08-21):**

1. **Grain-agnostic, rename** — the substance counter grain is *whatever the
   uid names* (Ku or PathStep; "I practised this lesson" is a real fact).
   Executed: `ku_uid`→`knowledge_uid` on `KuBackend.increment_substance` /
   `batch_increment_substance` + their `KuOperations` declarations,
   `PsService.increment_substance_metric` / `batch_increment_substance_metric`,
   `_AdaptiveMixin.increment_practice_count` + `find_kus_practiced_by_event`'s
   return alias, `KnowledgePracticed.knowledge_uid`, and the item-C fixture.
2. **`KnowledgePracticed` earns a subscriber** (not deleted, not blessed as
   fire-and-forget) — see § KnowledgePracticed Subscriber below.
3. **The unread counter arm stays staged, registered** — see § Per-Node
   Substance Counters below. The two phantom protocol declarations
   (`PsOperations.get_substance_score` / `get_substantiation_summary` — no
   implementation, no caller, laundered by `UniversalNeo4jBackend.__getattr__`)
   are DELETED with their `SubstantiationSummaryResult` TypedDict family.

**The Cypher fix (unconditional, shipped):** both writers now
`collect(DISTINCT ps)` + `FOREACH`, so the `RETURN` emits whenever the primary
write lands — the former `WHERE ps IS NOT NULL` row-filter reported `ok(0)`
for landed orphan-Ku and PathStep-targeted writes (the majority live case: 17
of 28 edges target orphan Kus). `ok(0)` now means exactly one thing: the uid
matched no node. Same restructure kills the dual-edge double-credit (a
PathStep composing one Ku via two edge types was credited twice) and the
duplicated `TRAINS_KU|TRAINS_KU` token. Pinned by
`TestIncrementSubstanceGrain` in the item-C test file (seed-and-match, per the
#586 precedent).

⚠️ Never-resurrect: the `WHERE ps IS NOT NULL` row-gating shape, and the
fictional subscribers (`LearningAnalyticsService`, `SpacedRepetitionService`)
that were de-fictioned out of `knowledge_substance_events.py` docstrings.

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

## Phantom-🆔 on a No-Op Injection — ✅ RESOLVED (reopen-vault-surface arc PR-1, 2026-08-24)

`VaultReconciler._process_entry_outbound` minted a `vault_id`, queued the line injection, and
after a **file-level** successful `write_task_updates` persisted EVERY minted pair via
`update_extracted_vault_id`. `WriteResult` carried only `success`/`new_sha256` —
`apply_task_updates` computed a per-update `changed` and discarded it into a file-level OR — so
file-level success was TAKEN AS proof that every queued injection landed, with nothing enforcing
it. No production trigger was ever known (corrected by the Codex review on #1144: both windows
once thought live are closed by the queue-time hash lookup and the whole-file SHA guard); the
registration was the structural fragility, and the arc that adds a third write operation
(`mark_undone`) is exactly the touch that would have inherited it.

Closed by the arc's PR-1: `apply_task_updates` **returns** its per-update outcomes instead of
OR-ing them away, `WriteResult.updates_applied` carries them positionally parallel to the batch
across BOTH transports and the `skuel-vault-agent`, and the reconciler persists each minted 🆔
only when THAT injection reports applied. `WriteResult.was_applied` reads fail-CLOSED — an
unreported outcome is "did not land" — and only a real JSON boolean counts as a confirmation
(`bool("false")` is `True`, so coercing the wire would have forged exactly the confirmation this
removes). A withheld persist leaves a warning on the sync rather than "complete".
`stats.ids_injected` moved with it: it counts injections that reached the file, not injections
that were queued.

**Withholding is recoverable only because the recovery arm now runs — guarded.** The arm that
adopts a 🆔 the file already carries (its stated purpose: heal a partial-write failure) sat
behind `if not updates: return`, so in its own defining case — the healing pass has nothing to
write — it never ran, and the divergence was permanent. That early return is now conditioned on
there being neither writes nor pending adoptions, and such a pass still goes through the write
door with an **empty batch**: both transports answer an empty batch with the SHA-256 stale-read
guard and no file mutation, so the adopted id is re-validated against the snapshot it was read
from instead of being persisted blind. Both pre-existing, found by the Codex review on the PR
that made them matter.

**Hash lookups are injective across an entry.** Two identical task lines in one note share a
`source_line_hash` (the digest is content-based and 🆔-blind by design), and `_find_line_by_hash`
returned the first match, so both of their entities got the SAME line: a recovery copied the
first line's 🆔 onto the second entity's edge, and that task's completion write-back would then
check the wrong line. A line whose 🆔 an edge in the entry already owns is now excluded before
the loop, and every line a lookup takes is excluded afterwards. Also pre-existing — reachable
before only through a mixed batch, and reachable on any recovery once the arm above started
running.

**Stated limitation, not a defect:** for byte-identical lines, WHICH of them an entity adopts is
arbitrary. No edge→line mapping is recorded and none exists to recover — the digest is
position-free and 🆔-blind by design, so two identical lines carry the same text and the same
state, and the choice is unobservable. A line that diverges from its twin also diverges in the
digest (the ✅ date is deliberately inside it) and stops matching, which is the discriminator
the design does have. What was fixed is the part that IS in the reconciler's control: the
backend read carries no `ORDER BY`, so the pass now sorts its rows and the outcome is at least
reproducible. Do not "fix" this further with a positional discriminator — line positions move
under exactly the edits the content-hash design exists to tolerate.

Wire-protocol change, so `PROTOCOL_VERSION` went **1 → 2** on both sides in one commit (parity
contract-tested in `tests/unit/test_vault_agent.py`; RED-checked by a one-sided bump). No agent
release was cut for it — PR-2 bumps to v3 and ONE release follows, so users pull once.

**Residue SETTLED in PR-2 (2026-08-24) — the whole outbound stat trio now counts what LANDED.**
`stats.tasks_marked_done` was counted at QUEUE time, so a repeat sync of an unchanged vault
reported every completed 🆔-bearing task as "marked done" again. When `tasks_marked_undone`
landed beside it the pair was settled together, in the direction `ids_injected` had already
moved in this section: each counter is gated on its own `WriteResult.updates_applied` slot.
"N tasks marked done in vault" now means "N lines this sync actually changed", and a repeat sync
of an unchanged vault reports zeros — which is the truth.

Fail-closed follows from `was_applied`: a transport reporting no outcomes under-counts rather
than guessing. That costs a display number and never durable state, which is why the same
fail-closed read that WITHHOLDS a 🆔 persist may simply under-report here. ⚠️ Fixtures that
mocked a bridge returning a bare `WriteResult(success=True)` were modelling a transport no real
adapter is — they now report outcomes (`tests/unit/services/vault/test_reconciler_done_date.py`).

⚠️ **Only the un-check warns on a `False` outcome.** A `mark_done` no-op is ORDINARY — `[x] ✅`
is the steady state of every completed task. A `mark_undone` no-op is not: its arm is gated on
running the mutation against the very snapshot the write is guarded by (`needs_mark_undone`), so
a successful write that changed nothing means the file moved underneath the batch.

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

## `TaskReopened` Has Zero Subscribers, and a Reopen Has No Vault Surface (RESOLVED 2026-08-24)

Two halves of one question — *what should a reopen actually do?* — carried unresolved through
three arcs (completion-stamping, cascade-idempotency, conditional-write). Mike ruled it
2026-08-24; **Half B by the build, Half A by ruling.** Kept as the case file because the ruling
is the interesting part, and because a future bloat sweep will meet `TaskReopened` again.

**Half B — RESOLVED BY BUILD.** A reopen now un-checks its Obsidian line and strips the `✅`
date (`apply_mark_undone`, `TaskLineUpdate.mark_undone`, the outbound `else` arm), byte-exact
reverse of the completion write. ADR-070's deliberate outbound-undone deferral was **amended,
not silently overridden** — three sites (field-authority row, the three-write-operations list,
Resolved Design Question 2 + a changelog row). Wire-protocol change: `PROTOCOL_VERSION` 2 → 3
on both sides in one commit.

**Half A — RESOLVED BY RULING: the event stays published and gets NO subscriber.**

⭐ **Why STATE is the authority, not the event.** `is_reopen` is only knowable *after*
`update_with_status_guard` returns the prior (ADR-087), so the graph write has already committed
before any consumer could run. A failed vault write has **no retry**: re-issuing the request
writes nothing, because the prior is now non-completed and it is no longer a transition. **A
reopen transition is a one-shot fact, consumed by the write that produced it.** So the vault
write is driven by a predicate — "this task is not completed AND its line is still marked done"
— which is re-evaluable at any time and idempotent. See
`feedback_one_shot_transition_needs_state_not_event`.

⭐ **And once state is the authority, the event has no verb left.** The outbound pass already
evaluates that predicate on every sync, so the un-check lands with zero event involvement. What
a subscriber would add is *only* lower latency — and **there is no latency asymmetry to correct**:
a task COMPLETION also only reaches the vault on the next human-initiated sync (`VaultReconciler.sync`
has exactly two callers — `vault_routes.py` and `scripts/vault_bridge_sync.py`). A subscriber
would make a reopen's vault write *more eager than the completion it reverses*, and add a second
live path to "the vault line matches the task's state" — the shape ADR-070 Decision 9 Ruling 1
rejects.

**Three premises that were investigated and FALSIFIED — do not re-derive them:**

- ❌ *"CORE tier runs no background workers."* The guarantee is **AI-scoped**.
  `GRACEFUL_DEGRADATION_ARCHITECTURE.md` says *"No **AI** background workers spin up"* and then
  documents one that does: the hourly `ProgressReportWorker` (graph analytics only) IS a CORE-tier
  Analog worker. ADR-043 makes no no-workers claim, and the bus plus all ~45 subscriptions in
  `services_bootstrap/_event_wiring.py` are wired unconditionally in CORE.
- ❌ *"A subscriber is a background write in all but name."* `publish_event` awaits
  `InMemoryEventBus.publish_async`, which awaits handlers through `asyncio.gather`. A subscriber
  is exactly as synchronous with the request as an inline call.
- ❌ *"A filesystem write from a subscriber would be unprecedented."*
  `AnalyticsService.handle_goal_achieved` → `_save_report` → `filepath.write_text(...)`.

**⚠️ `./dev bloat` reporting `i TaskReopened` (published, never subscribed) is the RULED END
STATE**, not a regression — INFO is not a `--check` failure. And `PLANNED_EVENTS` is **NOT** the
way to silence it: `analyze_events` branches on `publish_live` first, so a published class listed
there earns a SECOND INFO (`planned-marking-stale`) and the PLANNED tier below is never reached.
The ⚠ marker on the event's own docstring carries the decision, and it is what a sweep meets first.

⭐ **The transferable lesson:** an event-shaped *"prompt"* still needs a recipient that can act on
it. When the only actor able to act is the human, the event has no verb — and "what exactly does
the subscriber do?" is not a detail to fill in later, it is the design failing out loud.

**Still open, and separately registered:** the want behind "mark the owner's vault dirty" is real
but bigger than a reopen — see § "Vault Has Un-Synced Changes" Signal below. Inbound propagation
(a vault-side check/uncheck reaching SKUEL) stays parked in § R4.

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
| Domain-level fulltext-first text search (D1(b)) — ruled DEFERRED **twice** (2026-08-16, 2026-08-25) | A consumer wants relevance ranking for the domains remaining on `/search` after the facet redesign (6 Activity Domains + Ku) — ⚠️ scope INVERTED, do not scope from the bullet list; the OWNER_ONLY edge-vs-property "ruling needed" is STALE — already closed, do not re-open | Product need (not a data threshold); read the section's two rulings first |
| `/search` facet redesign (ruled *build, not now* 2026-08-25) | Mike schedules it — product decision (what `/search` is for) | See the section: Activity Domains facet, PS/LP out of results, LP joins the library catalog (not optional), Nous keeps its name, Relevance fiction left standing on purpose |
| ZPD snapshot history & trend analysis | A ZPD-over-time consumer exists | Product need + `MATCH (h:ZPDHistory) RETURN count(h)` for accrual |
| Habit rows in the weekly-note panel | Lived weekly-review use wants the backward look | Product need (not a data threshold) |
| Non-positive-duration follow-ups (habit `0m` on `/today` / proposes `15`) | Next touch of either surface | Ride-along, not standalone |
| Monthly-template vault cleanup | Founder vault pass | Founder-owned, non-repo |
| Monthly-note panel parity | Lived monthly-note use wants the weekly panel | Product need (not a data threshold) |
| Tasks/Events edge-clear on edit (`""` → None) | Next touch of the Tasks/Events edit forms | Ride-along; re-verify the bug still reproduces first |
| Skill↔doc backlink reconciliation | Docs-taxonomy pass — ruling needed per warning, not a rote edit | `uv run python scripts/validate_cross_references.py --verbose` |
| Drifted `## Related Skills` body sections (3 of 35) | Next `docs/patterns` sweep already touching these files | `uv run python scripts/sync_cross_references.py --all --dry-run` |
| Completion stamping at the status-transition chokepoint (truth-pass residue) | Next touch of the status-transition write path, or recent-activities ordering visibly lies | See § `:OWNS` Writers (RESOLVED) — residue subsection |
| LP recommendation backend methods (ruled *build, not now* 2026-08-20) | Mike schedules it — full feature: backend methods + frozen contract + consumer surface | Case file `lp-backend-recommendation-methods.md`; the 3 `Any` handles + their comments are the in-code markers |
| `KnowledgePracticed` subscriber (ruled "earns a subscriber" 2026-08-21) | A review-scheduling / spaced-repetition surface is scheduled | `git grep -l "subscribe(KnowledgePracticed"` — empty until wired; see the section |
| Per-node substance counters — the unread arm (ruled "keep staged" 2026-08-21) | A substantiation UI/surface is scheduled | `git grep -n "get_substantiation_gaps\|is_well_practiced" -- "ui/" "adapters/inbound/"` — empty until wired; see the section (incl. the retroactive-credit question) |
| R4 vault inbound propagation — parked build | Mike schedules it (product decision) | See the section — sketch + the #1143 r5 rejection; parsed-line vs entity state, never hash |
| Vault task door publishes no task events | R4 build or next vault-door touch | `git grep -n "event_bus" adapters/persistence/neo4j/bulk_upsert_backend.py` — empty until wired |
| Line deletions leave `EXTRACTED_FROM` edges | R4 build or next reconciler touch | Census shape in the section; re-probe the W28 edges before building |
| Habit streak counters (lost-update + future-day credit) | Next touch of the streak write path, or a lived wrong-streak report | Ruling needed on `current_streak` semantics — see the section |
| Unwired `HabitCompletion` model methods | A consumer wants one, or next Habits model touch | `git grep -n "is_streak_eligible\|was_completed_today" -- core/services/ adapters/ ui/` — empty until wired |
| "Vault has un-synced changes" signal | Mike schedules it — product decision (what the user is told), not a data threshold | See the section; ⚠️ must cover completions + 🆔 injections + new tasks, NOT reopens alone — no last-sync state is persisted today |
| `find_by` datetime string-binding (3 habit sites) | Next touch of any of the three reads, or a second `completed_at` writer | One PR: normalized range on a backend method (Pattern 10b / Key Rule 18b) |
| `TaskUpdateRequest` future `completion_date` asymmetry | Next touch of `task_request.py` validators | Ruling needed — see the section; don't rule in passing |

**The document is the checklist, the table is a convenience:** a section added to this file
without a matching row here is still in review scope — walk every `##` section, then the table.

Items that hit their trigger condition before the next review should be unblocked immediately —
don't wait for the review.
