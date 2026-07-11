# Technical Debt & Development Roadmap

**Last Updated:** July 4, 2026
**Total Production Ruff Errors:** 0
**Active TODOs:** 4

## Philosophy

We track technical debt intentionally. Each TODO is categorized, each deferred feature has documented prerequisites. Dead TODOs are deleted, not left to rot.

Development follows a calculated approach: features are built when they serve real users, not because they can be built. The codebase is well-established — protect what exists, extend deliberately.

**Categories:** `[PERFORMANCE]` `[FEATURE]` `[ENHANCEMENT]` `[CLEANUP]`

---

## Roadmap Overview

| Tier | Focus | When | Items |
|------|-------|------|-------|
| **1 — Foundation Fixes** | Strengthen what exists | ✅ Done | 0 |
| **2 — MVP Completions** | Working product gaps | ✅ Done | 0 |
| **3 — Data-Dependent** | Require usage data to justify | After real usage | 5 |
| **Shelved** | Prerequisite-gated | When thresholds met | 3 |
| **Decision Points** | Billing/architecture choices | When business model clarifies | 0 |

---

## Tier 1: Foundation Fixes

✅ **All resolved** (March 2026)

---

## Tier 2: MVP Completions

✅ **All resolved** (March 2026)

---

## Tier 3: Data-Dependent Enhancements

These only make sense once there are real users generating real data. Building them now would be engineering without evidence.

| # | File | Line | Category | Why wait | Trigger Metric |
|---|------|------|----------|----------|----------------|
| 6 | `core/services/tasks/tasks_ai_service.py` | 121 | [PERFORMANCE] | Fetches ALL user tasks for similarity detection. Vector similarity or query limits needed. | Median active user has **>100 tasks** |
| 8 | `core/services/analytics/analytics_life_path_service.py` | 450 | [FEATURE] | `get_alignment_trend()` needs historical depth. Snapshot write path now live (`ALIGNMENT_SNAPSHOT` rel on each `update_alignment_score`); trend query is real. Needs sustained engagement to be meaningful. | **30+ days** of daily alignment snapshots for at least one user |
| 9 | `core/services/user/user_context_service.py` | 526 | [ENHANCEMENT] | After task completion, record knowledge application tracking, time investment, learning progress. Needs clear UX for what users see from this data. | UX design decided + **10+ daily active users** generating completion data |
| 10 | `adapters/persistence/neo4j/query_builders/faceted_query_builder.py` | 210 | [ENHANCEMENT] | Replace string-split query parsing with `analyze_query_intent()` (already exists in `SearchIntelligenceService`). Current string split works for well-formed queries. | User-reported poor search results OR observed query mis-parse patterns in usage logs |
| 11 | `adapters/inbound/middleware.py` + `static/service-worker.js` | `StaticCacheHeadersMiddleware` / cache strategy | [PERFORMANCE] | **Static caching needs a deliberate design pass.** (a) Static assets use a blunt `Cache-Control: no-cache` (always-correct: forces revalidation so a stale broken asset can never be served — the fix for the infinite-loop `skuel.js` cache trap), but FastHTML's static route ignores `If-None-Match`, so every load re-downloads (~1MB) instead of returning 304. (b) The service worker caches `/static/*` **cache-first**, so app-asset updates are invisible to returning clients between `CACHE_VERSION` bumps. *(Resolved 2026-07-04, care arc: the SW-never-registers 404 is fixed — `scripts/dev/bootstrap.py` strips FastHTML's `{fname:path}` extension catch-all before mounting /static, so `/service-worker.js` and `/offline.html` now serve via `pwa_routes.py` and the SW registers; this also closed an exposure where any static-ext repo file, e.g. `/tailwind.config.js`, was publicly served.)* **Plan**: cache version-stamped vendor assets (lucide/alpine/htmx/chart.js/vis-network) as `immutable`+long-lived, content-hash app assets (skuel.js, output.css) for URL cache-busting, and make app assets SW network-first (or hashed). | Before production deploy / when serving real traffic |

---

## Shelved Intelligence Features

Documented, scoped, with clear prerequisites. Not active debt — intentionally deferred until thresholds are met.

| Feature | Doc | Prerequisite | Effort |
|---------|-----|-------------|--------|
| Semantic Analysis — SHIPPED #598–#600 (chips / prereq suggestions / ZPD feed); residue: ZPD semantic pool expansion | `docs/intelligence/SEMANTIC_ANALYSIS_ROADMAP.md` | Engagement edges exist (entry-enrichment arc) | small |
| Discovery Analytics Phases 2+ (Phase 1 logging + `/admin/analytics` gap surface shipped 2026-07-10) | `docs/intelligence/DISCOVERY_ANALYTICS_ROADMAP.md` | 1000+ `:SearchEvent` nodes (accumulating) | 2-3 days |
| Real-time Intelligence | `docs/intelligence/REALTIME_INTELLIGENCE_ROADMAP.md` | 10+ daily active users | 3-4 days |

---

## Decision Points (Not TODOs)

These are architectural choices that depend on business decisions, not code quality.

> **Per-user intelligence tier** resolved June 2026: `get_user_intelligence_tier()` is now wired
> into `adapters/inbound/ai_routes.py:_ai_route`. REGISTERED users receive a 403 on AI routes
> when the system tier is FULL; MEMBER+ receive the system tier. System tier remains the ceiling
> (ADR-043). No open decision points remain.

---

## Non-Production TODOs (tracked, low priority)

None currently tracked. (The former `tests/integration/test_async_embeddings.py` end-to-end TODO is covered by `test_end_to_end_neo4j_embedding_storage`.)

---

## Ruff Linting Status

**All production errors resolved.**

| Metric | Oct 2025 | Mar 2026 |
|--------|----------|----------|
| Total errors | 241 | **0** |

Run: `uv run ruff check core/ adapters/ ui/`

---

## Resolved Debt (Historical Summary)

**Oct 2025 - Mar 2026:**

- **241 ruff errors eliminated** (all zero)
- **~20 stale TODOs resolved** across deleted/refactored services
- **5 dead service files deleted** (yaml_ingestion, markdown_sync, context_aware_intelligence, event_converters, tasks_analytics)
- **Journal model package deleted** (~1,400 lines of dead code)
- **Transcription three-tier models deleted** (~1,540 lines)
- **3 stale tracking files deleted** from `data/`
- **Unified Ku model (ADR-041)** — 15 domain types into single hierarchy
- **ActivityStatus + GoalStatus consolidated** into EntityStatus (14 values)
- **Sync renamed to Ingestion** — one-way pipeline, not bidirectional
- **All ~72 Services dataclass fields typed** — zero `Any` remaining
- **Reports domain renamed** to Submissions + Reports (Feb 2026)
- **Report types split** — ActivityReport (user-owned) vs EntryReport (tied to submission)
- **universal_backend.py decomposed** — 4,214 lines into 6 focused mixins
- **unified_relationship_service.py decomposed** — into 6 mixins
- **Activity domain query layer refactored** — `get_filtered_context()` replaces 24 closure call sites
- **Password reset email implemented** — Resend integration via `EmailOperations` protocol + `ResendEmailService` adapter (March 2026)
- **Learning progress routes implemented** — `POST /api/learning/progress` and `GET /api/learning/progress/summary` connected to `UserProgressService` (March 2026)
- **`is_this_week` calculation fixed** — 6 hardcoded `False` values replaced with real week-boundary logic
- **`RichContextRequiredError` added** — replaces generic `ValueError` in the rich-context guard (now `_as_rich()`)
- **`BudgetDTO.user_uid` added** — eliminates `user_uid=""` workaround in converters
- **Event goal-alignment scoring wired** — `contributes_to_goal_uid` derived field + `enrich_events_with_goal_links` + `get_goal_links_for_events`; events now score the 0.25-weight goal-alignment component (June 2026)
- **Dead PHASE 3B stubs removed** — `_orchestration_mixin.py` `getattr(event_data, "supports_goal_uid")` / `getattr(event_data, "learning_path_uid")` always resolved to `None` and were silently ignored (June 2026)
- **Stale Tier 3 entries deleted** — item 7 (`_period_days` is used) and item 11 (`adaptive_lp_core_service.py` deleted in campaign #294) (June 2026)

---

## Monitoring Strategy

### Quarterly Review
- Verify TODO count hasn't grown unchecked
- Check if any shelved features have met prerequisites
- Run `grep -rn "# TODO" core/ adapters/ ui/` to audit

### Before Adding Features
- Does this feature serve a real user need, or does it just feel good to build?
- Will someone use this in the next 30 days?
- Does it strengthen an existing loop phase or improve transitions between phases?
- If the answer to all three is no, add it to Tier 3 or Shelved instead.

---

**Last Reviewed:** June 19, 2026
**Next Review:** September 2026
