# Technical Debt & TODO Roadmap

**Last Updated:** February 18, 2026
**Total Production Ruff Errors:** 0
**Active TODOs:** 7

## Philosophy

We track technical debt intentionally. Each TODO is categorized, each deferred feature has documented prerequisites. Dead TODOs are deleted, not left to rot.

**Categories:** `[PERFORMANCE]` `[FEATURE]` `[ENHANCEMENT]` `[CLEANUP]`

---

## Ruff Linting Status

**All production errors resolved.**

| Metric | Oct 2025 | Feb 2026 |
|--------|----------|----------|
| Total errors | 241 | **0** |
| Critical | 0 | 0 |
| Medium | 30 | **0** |
| Low | 106 | **0** |

Run: `poetry run ruff check core/ adapters/ routes/ ui/`

---

## Active TODOs (7 items)

### Performance (1)

| File | Line | Description |
|------|------|-------------|
| `core/services/tasks/tasks_ai_service.py` | 122 | Fetches ALL user tasks for similarity detection. Use vector similarity search or limit query for users with many tasks. |

### Features (3)

| File | Line | Description |
|------|------|-------------|
| `ui/profile/domain_views.py` | 436 | `is_this_week` hardcoded to `False`. Calculate from `task.due_date` using week boundaries. |
| `core/services/goals/goals_intelligence_service.py` | 212 | `_period_days` parameter accepted but unused. Filter goals by `created_at`/`updated_at` within period. |
| `core/services/analytics/analytics_life_path_service.py` | 450 | `get_alignment_trend()` returns placeholder data. Needs historical alignment score snapshots in Neo4j + rolling average calculation. |

### Enhancements (2)

| File | Line | Description |
|------|------|-------------|
| `core/services/user/user_context_service.py` | 478 | After task completion, record: knowledge application tracking, time investment, learning progress, context cache invalidation. |
| `core/services/query/faceted_query_builder.py` | 192 | Phase 2: Replace regex-based query parsing with `analyze_query_intent()` for semantic analysis of faceted queries. |

### Cleanup (1)

| File | Line | Description |
|------|------|-------------|
| `core/models/finance/finance_converters.py` | 267 | `BudgetDTO` missing `user_uid` field. Converter sets `user_uid=""` — service layer provides context as workaround. |

---

## Placeholder Routes (Not TODOs)

These routes exist with intentional 501 responses. They define the API contract; implementation is deferred.

| File | Lines | Route | Description |
|------|-------|-------|-------------|
| `adapters/inbound/learning_api.py` | 126 | `POST /api/learning/progress` | Progress tracking — requires progress service integration |
| `adapters/inbound/learning_api.py` | 143 | `GET /api/learning/progress/summary` | Progress summary — requires progress service integration |

---

## Shelved Intelligence Features

These are documented, scoped, and have clear prerequisites. Not active debt — intentionally deferred until prerequisites are met.

| Feature | Doc | Prerequisite | Effort |
|---------|-----|-------------|--------|
| Semantic Analysis | `docs/intelligence/SEMANTIC_ANALYSIS_ROADMAP.md` | 50+ KUs with rich text | 3-4 days |
| Discovery Analytics | `docs/intelligence/DISCOVERY_ANALYTICS_ROADMAP.md` | 1000+ search queries logged | 2-3 days |
| Real-time Intelligence | `docs/intelligence/REALTIME_INTELLIGENCE_ROADMAP.md` | 10+ daily active users | 3-4 days |

---

## Resolved Debt (Historical Summary)

**Oct 2025 - Feb 2026:** Major cleanup sprint.

- **241 ruff errors eliminated** (critical, medium, and low priority — all zero)
- **~20 stale TODOs resolved** across deleted/refactored services
- **5 dead service files deleted** (yaml_ingestion, markdown_sync, context_aware_intelligence, event_converters, tasks_analytics)
- **Journal model package deleted** (~1,400 lines of dead code)
- **Transcription three-tier models deleted** (~1,540 lines)
- **3 stale tracking files deleted** from `data/` directory
- **Unified Ku model (ADR-041)** consolidated 15 domain types into single Ku + per-domain DTOs (KuDTO deleted 2026-02-23)
- **ActivityStatus + GoalStatus consolidated** into KuStatus (14 values)
- **Sync renamed to Ingestion** across entire codebase (one-way pipeline, not bidirectional)
- **All ~72 Services dataclass fields typed** (zero `Any` remaining)

---

## Monitoring Strategy

### Quarterly Review
- Verify TODO count hasn't grown unchecked
- Check if any shelved features have met prerequisites
- Run `grep -rn "# TODO" core/ adapters/ routes/ ui/` to audit

### Before Major Releases
- Review all `[PERFORMANCE]` TODOs for production impact
- Verify placeholder routes are documented in API docs

---

**Last Reviewed:** February 18, 2026
**Next Review:** May 2026
