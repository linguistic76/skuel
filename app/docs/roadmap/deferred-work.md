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
revisit semantic pool expansion (see [`SEMANTIC_ANALYSIS_ROADMAP.md`](SEMANTIC_ANALYSIS_ROADMAP.md)).

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

## Secrets Follow-ups — Shred the `secrets.env` Residue; KeyringBackend Tests

Extracted 2026-08-07 from [`done/secrets-out-of-worktree.md`](done/secrets-out-of-worktree.md)
("What's left" — stages 1–3 shipped; both items small and optional, previously tracked
nowhere live):

1. **Move docker-compose's `NEO4J_AUTH`/`NEO4J_PASSWORD` interpolation onto the
   `with-secrets` wrapper** so the two-line `secrets.env` residue can be shredded entirely —
   today `${VAR}` substitution in `app/docker-compose.yml` + `infrastructure/docker-compose.yml`
   still reads it.
2. **Dedicated `KeyringBackend` round-trip unit test** — currently covered by integration
   tests + the Stage-3a inline smoke test; cheap insurance, not strictly needed.

**Enable when**: next touch of the compose/secrets surface (item 1 rides along); item 2 any
time a test-writing pass visits `core/config/credential_store.py`.

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

## `:OWNS` Writers That Skip `user_uid` (the staged attendee/gravity surface)

Surfaced 2026-08-16 while closing the CRUD-door half of the `user_uid property == :OWNS owner`
invariant. **Not a live bug — a tripwire for whoever wires the staged surface.**

`UnifiedRelationshipService.create_user_relationship` writes the domain's
`ownership_relationship` (`:OWNS` for every OWNER_ONLY domain) and **never touches the
`user_uid` property**. Five methods call it, and all five are registered in `PLANNED_METHODS`
(`scripts/detect_bloat.py`) — zero production callers today:

| Method | File |
|---|---|
| `add_attendee` | `core/services/events/_orchestration_mixin.py` |
| `create_user_event_relationship` | `core/services/events/_orchestration_mixin.py` |
| `create_user_goal_relationship` | `core/services/goals_service.py` |
| `create_user_habit_relationship` | `core/services/habits/_orchestration_mixin.py` |
| `create_user_principle_relationship` | `core/services/principles/_gravity_mixin.py` |

`add_attendee` is the sharp one: it would give an attendee an `:OWNS` edge onto an Event whose
`user_uid` is the *organiser*. Faceted search anchors on the edge, so the attendee would see
another user's Event; the property-scoped strategies would not. That is an ownership edge doing
a *participation* job — `:OWNS` is the wrong relationship for "attends", and the fix when this
surface is wired is most likely a distinct edge (`ATTENDS`/`PARTICIPATES_IN`), not a second
ownership writer.

**Enable when**: the attendee surface or any of the four gravity-link methods is wired. Whoever
does it must decide the relationship *before* the first write — a wrong edge in the graph
outlives the PR that wrote it.

**Check it is still latent**: each of the five must still have no production caller.
```bash
git grep -n "add_attendee\|create_user_goal_relationship\|create_user_habit_relationship\|create_user_principle_relationship\|create_user_event_relationship" -- '*.py' | grep -v '^tests/\|^scripts/'
```

---

## `User.uid` Has No Index or Constraint

Surfaced 2026-08-16 by the same investigation, measured against the live AuraDB.

`:User` carries exactly two indexes — `User_email_unique` (uniqueness on `email`) and
`User_pairing_code_hash_idx`. **There is no index or constraint on `User(uid)`**, and
`neo4j_schema_manager.py`'s auth-index sync never creates one. Meanwhile **290 unique lines** of
`adapters/persistence/` Cypher do `MATCH (…:User {uid: $…})` — every one a label scan over
`:User`.

Invisible at 6 users. It is also *why* an `EXPLAIN` of the edge-anchored ownership plan
(`MATCH (user:User {uid:$uid})-[:OWNS]->(entity)`) shows `NodeByLabelScan user:User` where the
property-scoped plan gets a `NodeIndexSeek` — so this is a live input to any future ruling that
would move ownership reads onto the edge.

**Open question, not a mechanical add:** index or *uniqueness constraint*? `uid` reads as an
identity key (`user_<name>`), so a constraint is likely right and doubles as the index — but it
will fail to build if any duplicate `uid` exists, and that is a data question to check first.

**Enable when**: user count grows past a handful, or any ruling moves ownership reads onto the
`:OWNS` edge — whichever comes first. Cheap and independent either way.

```bash
# check for duplicates before choosing a constraint
# MATCH (u:User) WITH u.uid AS uid, count(*) AS c WHERE c > 1 RETURN uid, c
```

⚠️ **Counting trap** if you re-measure the call sites: the f-string spelling (`User {{uid:`) and
the plain spelling (`User {uid:`) are disjoint substrings. Grepping one undercounts by ~2×.

---

## `GroupService` Declares `OWNER_ONLY` But `Group` Has No `user_uid`

Surfaced 2026-08-16 by Codex on PR #1079 (the faceted-search convergence). **Not a live bug — a
design decision owed before Group is ever wired into search.** Left as a guarded trap rather
than folded into an access-control PR.

`GroupService._config` sets `user_ownership_relationship=RelationshipName.OWNS`
(`core/services/groups/group_service.py:54`), and `DomainConfig.get_search_visibility()` derives
`OWNER_ONLY` from any non-None ownership relationship. But `build_search_visibility_clause`
renders `OWNER_ONLY` as a **property** predicate — `entity.user_uid = $user_uid` — and `Group`
stores its owner in `owner_uid` with no `user_uid` field at all (`core/models/group/group.py`;
`GroupService.verify_ownership` overrides the base precisely because "Group uses `owner_uid`
instead of `Entity.user_uid`"). The predicate would be null for every row, so a Group search
would silently return nothing.

**Why it is inaccurate today, independent of that arc:** the declaration has always claimed a
scoping mechanism Group's model cannot support. It was merely *survivable* while faceted search
anchored on `(User)-[:OWNS]->(entity)`, because Group does carry that edge. #1079 removed the
anchor, so the mismatch now has no path that tolerates it.

**Why it is harmless:** Group is not a searchable domain. It is absent from
`_SEARCHABLE_DOMAINS` (12 `EntityType` members — `NonKuDomain.GROUP` cannot be one),
`_SERVICE_REGISTRY`, and `_GRAPH_AWARE_DOMAINS`; `GROUPS_CONFIG` wires CRUD only; and the sole
production callers of `graph_aware_faceted_search` are inside `SearchRouter`, which resolves
services from `_SERVICE_REGISTRY`. Group routes call `get_for_user`, `get_user_groups`,
`get_members`, `add_member`, `remove_member` — never search.

**The ruling needed** (either, not both):
1. Give `DomainConfig` a **configurable ownership property** so `OWNER_ONLY` can scope on
   `owner_uid` — the general fix, and it would also let Exercise's `owner_uid` half stop being a
   `SCOPE_AWARE` special case.
2. Give Group a **real visibility declaration** of its own. There is no correct value today:
   `SCOPE_AWARE` is Exercise-shaped (`scope` + `owner_uid` + group membership) and Group has no
   `scope` field, so this route means designing a Group visibility, not picking one.

Option 1 is the smaller change if a second `owner_uid`-keyed domain ever wants search; option 2
is smaller if Group stays the only one. Do not "fix" it by adding a `user_uid` to `Group` — that
would give the same claim two names, which is the divergence class #1078 spent a PR closing.

**Enable when**: anyone wires Group into search, or a second `owner_uid`-keyed domain wants
search. The guard fires first either way —
`tests/unit/models/test_search_router_registry.py::TestOwnerOnlyDomainsCarryTheScopingProperty`
holds both halves (`test_every_searchable_owner_only_domain_has_user_uid` for the class,
`test_group_is_not_a_searchable_domain` for Group specifically). Fix the declaration; do not
delete the test. Recorded also in `docs/architecture/SEARCH_ARCHITECTURE.md` § Ownership Scoping.

**Check it is still latent**: Group must still be in no search registry.
```bash
uv run python -c "
from core.orchestrator.search_router import SearchRouter as R
print('in _SERVICE_REGISTRY:', 'groups' in set(R._SERVICE_REGISTRY.values()))
print('in _GRAPH_AWARE_DOMAINS:', 'groups' in R._GRAPH_AWARE_DOMAINS)"
```

⚠️ The exemption list in that test guards **one** domain (Exercise, verified `SCOPE_AWARE`) and
asserts its own length. Adding Group to it instead of fixing the declaration converts a tripwire
into a silently-broken search.

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

## Backend-Typing Follow-on — the Active Queue (3 items)

These three outlived the backend-typing arc (#1090–#1102, closed 2026-08-20)
because none of them is a retype — each is a decision or a chain. They are
**active backlog, not trigger-gated deferral**: the standing ruling
(Mike, 2026-08-20) is that a fresh context takes **ONE** of them, not the set.
Registered here so the repo carries the list; a fourth sibling — the LP
recommendation backend methods — was ruled *build, not now* and has its own
section above.

### A. The `DomainConfig` string chain

`generate_prerequisite_relationships` **has** the `RelationshipName` enums and
discards them to strings — `[rel.value for rel in
config.prerequisite_relationship_names]` (`core/models/relationship_registry.py:2519`).
**Four** sites hold the downgraded `list[str]` form (Codex on PR #1105 caught
the fourth after this register first said three — the enumerate-every-site
lesson, live): the generator's return type (`relationship_registry.py:2505`),
`_prerequisite_relationships: ClassVar[list[str]]` on `BaseService`
(`core/services/base_service.py:570`), the context mixin's declaration
(`core/services/mixins/context_operations_mixin.py:69`), and the relationship
mixin's declaration (`core/services/mixins/relationship_operations_mixin.py:75`)
— the last also holds PR #1102's conversion chokepoint,
`RelationshipName(self._prerequisite_relationships[0])` (~`:319`), which a
chain conversion would retire. The chain's *sources* are `DomainConfig`'s
string tuples (`core/services/domain_config.py:385`, `:449`–`:471`).
PR #1102 made `add_relationship` enum-only and localized the conversion to the
ONE place a config value becomes an edge type; converting the whole chain is
the remaining cleanup — bounded, but it touches `domain_config.py` and both
mixins' query paths, so **measure before scoping, and re-run this census at
scoping time rather than trusting it**.
⚠️ `generate_enables_relationships` (`relationship_registry.py:2536`) is the
same shape and was never examined — enumerate both before fixing either.

### B. The `PsOperations` layering contradiction

Blocks the last untyped factory param: `create_ps_sub_services(backend=)`
(`core/services/curriculum_domain_config.py:135`, param `backend: Any` at
`:154`; Mike ruled "type not annotate"). It cannot be typed until this is
settled: `PsOperations` is documented as the **service-facing** protocol
(`core/ports/curriculum_protocols.py:874`), yet 5 sub-services type
`self.backend` against it — and, measured 2026-08-20,
`x: PsOperations = PsBackend(...)` probes **clean** while
`x: PsOperations = PsService(...)` **fails**: the protocol carrying the
service's shapes is satisfied by the backend and not by the service. Mike's
leaning (2026-08-20): "PsOperations is the backend protocol" — stated as a
hypothesis needing investigation, **not** a ruling. The two protocols the
factory would need are provably un-composable (mypy rejects the
multiple-inheritance). ⚠️ Same-root-word/two-layer trap — one prior "fix" of
this divergence had to be reverted; PR #1101 fixed the 5 row-type conflicts
but deliberately left the layering question open.

### C. The lying `ku_backend` fixture

`tests/integration/test_event_ku_practice_flow.py:61` — a fixture **named**
`ku_backend` that constructs a `PsBackend` (`NeoLabel.PATH_STEP`, `PathStep`).
**Ruled: bundle with whatever touches that file next; do not spend a PR on it.**

---

## Review Schedule

Review this document at the **September 2026 quarterly review**. Checklist:

| Item | Trigger | Check |
|------|---------|-------|
| Semantic Analysis residue (ZPD semantic pool expansion; 3-item remainder SHIPPED #598–#600) | Engagement edges exist (entry-enrichment arc) | Ku engagement edge count > 0 |
| Discovery Analytics Phases 2+ (logging shipped 2026-07-10) | Search events ≥ 1,000 | `MATCH (e:SearchEvent) RETURN count(e)` |
| Real-time Intelligence | DAU ≥ 10 for 2+ weeks | Grafana `skuel_daily_active_users` |
| Per-user intelligence tier | Billing model defined | Business decision |
| KnowledgeConfig validation | Config fields added | `grep embedding_model core/config/unified_config.py` |
| `filter_property` extension | A consumer wants non-GOALS edge tier buckets | Product need (not a data threshold) |
| Knowledge Ku↔Ku prerequisites (Option B) | A consumer reads prereq/dependent Ku buckets | Product need (not a data threshold) |
| Task `dependent_task_uids` | A consumer reads a task's dependents | Product need (not a data threshold) |
| Secrets follow-ups (shred `secrets.env` residue; KeyringBackend test) | Next touch of the compose/secrets surface | Ride-along, not standalone |
| Principles `_validate_update` reform or deletion | Next substantive touch of the Principles update path | Ruling needed — see the section's landmine note |
| EntryReport / ActivityReport search | A teacher workflow wants direct report-content search | Product need (not a data threshold) |
| Domain-level fulltext-first text search (D1(b)) | A consumer wants relevance-ranked text search beyond `/api/search/unified` curriculum (incl. the `/search` page) | Product need (not a data threshold) |
| ZPD snapshot history & trend analysis | A ZPD-over-time consumer exists | Product need + `MATCH (h:ZPDHistory) RETURN count(h)` for accrual |
| Habit rows in the weekly-note panel | Lived weekly-review use wants the backward look | Product need (not a data threshold) |
| Non-positive-duration follow-ups (habit `0m` on `/today` / proposes `15`) | Next touch of either surface | Ride-along, not standalone |
| Monthly-template vault cleanup | Founder vault pass | Founder-owned, non-repo |
| Monthly-note panel parity | Lived monthly-note use wants the weekly panel | Product need (not a data threshold) |
| Tasks/Events edge-clear on edit (`""` → None) | Next touch of the Tasks/Events edit forms | Ride-along; re-verify the bug still reproduces first |
| Skill↔doc backlink reconciliation | Docs-taxonomy pass — ruling needed per warning, not a rote edit | `uv run python scripts/validate_cross_references.py --verbose` |
| Drifted `## Related Skills` body sections (3 of 35) | Next `docs/patterns` sweep already touching these files | `uv run python scripts/sync_cross_references.py --all --dry-run` |
| `:OWNS` writers that skip `user_uid` (staged attendee/gravity surface) | Wiring `add_attendee` or any of the 4 gravity-link methods | Ruling needed on the edge type first — see the section |
| `User.uid` unindexed | User count past a handful, or a ruling moving ownership reads onto the `:OWNS` edge | `SHOW INDEXES` — no `User(uid)` entry today |
| `GroupService` OWNER_ONLY vs `Group.owner_uid` | Wiring Group into search, or a 2nd `owner_uid`-keyed domain wanting search | Ruling needed (configurable ownership property **or** a Group visibility) — see the section; guarded by `TestOwnerOnlyDomainsCarryTheScopingProperty` |
| LP recommendation backend methods (ruled *build, not now* 2026-08-20) | Mike schedules it — full feature: backend methods + frozen contract + consumer surface | Case file `lp-backend-recommendation-methods.md`; the 3 `Any` handles + their comments are the in-code markers |
| `DomainConfig` string chain (backend-typing queue A) | Next backlog session — active queue, ONE item per context | `git grep 'rel.value for rel in'` still shows the discard at `relationship_registry.py:2519`; ⚠️ enumerate the enables twin too |
| `PsOperations` layering contradiction (backend-typing queue B) | Next backlog session — investigation, not a retype | `create_ps_sub_services(backend=)` still `Any`; probe `x: PsOperations = PsBackend(...)` vs `= PsService(...)` before believing any doc |
| Lying `ku_backend` fixture (backend-typing queue C) | Next touch of `test_event_ku_practice_flow.py` | Ride-along, not standalone — ruled: do not spend a PR |

**The document is the checklist, the table is a convenience:** a section added to this file
without a matching row here is still in review scope — walk every `##` section, then the table.

Items that hit their trigger condition before the next review should be unblocked immediately —
don't wait for the review.
