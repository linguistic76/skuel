# Technical Debt & Development Roadmap

**Last Updated:** March 4, 2026
**Total Production Ruff Errors:** 0
**Active TODOs:** 6

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
| **3 — Data-Dependent** | Require usage data to justify | After real usage | 6 |
| **Shelved** | Prerequisite-gated | When thresholds met | 3 |
| **Decision Points** | Billing/architecture choices | When business model clarifies | 1 |

---

## Tier 1: Foundation Fixes

✅ **All resolved** (March 2026)

---

## Tier 2: MVP Completions

✅ **All resolved** (March 2026)

---

## Tier 3: Data-Dependent Enhancements

These only make sense once there are real users generating real data. Building them now would be engineering without evidence.

| # | File | Line | Category | Why wait |
|---|------|------|----------|----------|
| 6 | `core/services/tasks/tasks_ai_service.py` | 121 | [PERFORMANCE] | Fetches ALL user tasks for similarity detection. Vector similarity or query limits needed — but only matters when users have 100+ tasks. |
| 7 | `core/services/goals/goals_intelligence_service.py` | 211 | [FEATURE] | `_period_days` parameter accepted but unused. Filter goals by time window. Needs real usage patterns to validate the right window defaults. |
| 8 | `core/services/analytics/analytics_life_path_service.py` | 450 | [FEATURE] | `get_alignment_trend()` returns placeholder data. Needs historical alignment score snapshots in Neo4j + rolling averages. Requires sustained user engagement to be meaningful. |
| 9 | `core/services/user/user_context_service.py` | 478 | [ENHANCEMENT] | After task completion, record knowledge application tracking, time investment, learning progress. Needs clear UX for what users see from this data. |
| 10 | `core/services/query/faceted_query_builder.py` | 192 | [ENHANCEMENT] | Replace regex-based query parsing with `analyze_query_intent()` for semantic analysis. Current regex works — semantic analysis is an optimization. |
| 11 | `core/services/adaptive_lp/adaptive_lp_core_service.py` | 104 | [FEATURE] | `_detect_learning_style()` always returns `'balanced'`. Detecting learning style from behavior patterns requires substantial user interaction history. |

---

## Shelved Intelligence Features

Documented, scoped, with clear prerequisites. Not active debt — intentionally deferred until thresholds are met.

| Feature | Doc | Prerequisite | Effort |
|---------|-----|-------------|--------|
| Semantic Analysis | `docs/intelligence/SEMANTIC_ANALYSIS_ROADMAP.md` | 50+ KUs with rich text | 3-4 days |
| Discovery Analytics | `docs/intelligence/DISCOVERY_ANALYTICS_ROADMAP.md` | 1000+ search queries logged | 2-3 days |
| Real-time Intelligence | `docs/intelligence/REALTIME_INTELLIGENCE_ROADMAP.md` | 10+ daily active users | 3-4 days |

---

## Decision Points (Not TODOs)

These are architectural choices that depend on business decisions, not code quality.

| Decision | Current State | What Triggers Action |
|----------|---------------|---------------------|
| **Per-user intelligence tier** | `intelligence_tier_service.py` exists but is not wired into routes (ADR-043). System-wide toggle works. | Billing model decision — when paid vs free tiers are defined, wire `get_user_intelligence_tier()` into route middleware. |
| **KnowledgeConfig validation** | `config/validation.py:199` returns empty list. | When `embedding_model` and `embedding_dimension` fields are added to `KnowledgeConfig`, add real validation. |

---

## Non-Production TODOs (tracked, low priority)

| File | Description |
|------|-------------|
| `tests/integration/test_async_embeddings.py:560-561` | Add end-to-end test with real Neo4j + performance benchmarking test. |
| `scripts/sync_cross_references.py:210` | Could update existing "Related Skills" sections instead of skipping files that already have one. |

---

## Ruff Linting Status

**All production errors resolved.**

| Metric | Oct 2025 | Mar 2026 |
|--------|----------|----------|
| Total errors | 241 | **0** |

Run: `poetry run ruff check core/ adapters/ ui/`

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
- **Reports domain renamed** to Submissions + Feedback (Feb 2026)
- **Feedback types split** — ActivityReport (user-owned) vs SubmissionFeedback (tied to submission)
- **universal_backend.py decomposed** — 4,214 lines into 6 focused mixins
- **unified_relationship_service.py decomposed** — into 6 mixins
- **Activity domain query layer refactored** — `get_filtered_context()` replaces 24 closure call sites
- **Password reset email implemented** — Resend integration via `EmailOperations` protocol + `ResendEmailService` adapter (March 2026)
- **Learning progress routes implemented** — `POST /api/learning/progress` and `GET /api/learning/progress/summary` connected to `UserProgressService` (March 2026)
- **`is_this_week` calculation fixed** — 6 hardcoded `False` values replaced with real week-boundary logic
- **`RichContextRequiredError` added** — replaces generic `ValueError` in `require_rich_context()`
- **`BudgetDTO.user_uid` added** — eliminates `user_uid=""` workaround in converters

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

**Last Reviewed:** March 4, 2026
**Next Review:** June 2026
