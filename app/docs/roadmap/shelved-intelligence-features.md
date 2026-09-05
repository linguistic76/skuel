---
title: "Shelved Intelligence Features — Semantic Analysis residue, Discovery Analytics Phases 2+, Real-time Intelligence"
updated: 2026-09-05
status: "shelved"
trigger: "engagement edges exist (Semantic residue); 1,000+ :SearchEvent (Discovery Phases 2+); DAU ≥ 10 for 2+ weeks (Real-time)"
check: "Ku engagement edge count > 0; MATCH (e:SearchEvent) RETURN count(e); Grafana skuel_daily_active_users"
---

# Shelved Intelligence Features

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

The three features below are shelved — not premature ideas, but fully scoped and correctly deferred until enough data exists to make them meaningful. Semantic Analysis and Discovery Analytics have dedicated roadmap documents in `/docs/roadmap/`; Real-time Intelligence's roadmap was retired, so its trigger-gated note lives inline below.

**See**: `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md` — the authoritative index of the intelligence layer.

---

## 1. Semantic Analysis

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

## 2. Discovery Analytics

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

**Enable when**: 1,000+ search events logged in Neo4j — ⚠️ measured 41 on 2026-08-25;
[`DISCOVERY_ANALYTICS_ROADMAP.md`](DISCOVERY_ANALYTICS_ROADMAP.md) § Phases 2+ says what to do
with a gate that cannot fire at the observed rate.

---

## 3. Real-time Intelligence

**Why deferred**: Real-time intelligence (live activity feeds, push-based recommendations,
session-aware context updates) requires concurrent users to be meaningful. With a single
developer testing the system, "real-time" is indistinguishable from "refresh the page."

**The problem**: `UserContextIntelligence.get_ready_to_work_on_today()` currently rebuilds context on every request. For 10+ daily active users, incremental updates (only recompute what changed) would meaningfully reduce Neo4j load. Real-time also enables "your colleague just completed the same KU" social signals.

**What to do**:

1. Verify daily active users: instrument `skuel_daily_active_users` Prometheus gauge — proceed when consistently ≥ 10.
2. Add WebSocket session tracking to `SessionBackend` (groundwork exists in `core/auth/`).
3. Replace full `build_rich()` calls with incremental delta queries for unchanged domains.

**Enable when**: 10+ daily active users sustained over 2+ weeks.
