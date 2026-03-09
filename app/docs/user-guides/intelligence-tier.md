# Intelligence Tier Guide

*Last updated: 2026-03-04*

## Overview

SKUEL has two layers of intelligence:

- **CORE** — Graph analytics, daily planning, UserContext, all CRUD operations. Pure Python + Cypher. No API costs.
- **FULL** — Everything in CORE, plus AI services (LLM chat, embeddings, vector search, content processing, feedback generation). Costs money per API call.

One environment variable controls which layer is active:

```bash
INTELLIGENCE_TIER=core   # Analytics only — $0
INTELLIGENCE_TIER=full   # Analytics + AI (default)
```

If unset, the tier defaults to `full` — existing deployments with API keys keep working with no changes.

---

## What Each Tier Provides

### CORE Tier (Free)

| Feature | Works? |
|---------|--------|
| Create, read, update, delete entities (all entity types) | Yes |
| 13 analytics intelligence services (BaseAnalyticsService) | Yes |
| UserContext (~240 fields, MEGA-QUERY) | Yes |
| Daily planning ("What should I work on today?") | Yes |
| Life path alignment scoring | Yes |
| Keyword search across all domains | Yes |
| Calendar aggregation | Yes |
| Graph relationships and traversals | Yes |
| Lateral relationships + Vis.js visualization | Yes |
| Prometheus metrics and monitoring | Yes |
| Groups + teacher-student management | Yes |

### FULL Tier (Requires API Key)

Everything in CORE, plus:

| Feature | Service |
|---------|---------|
| LLM-powered report generation | SubmissionReportService |
| AI content processing (journals, transcripts) | ContentEnrichmentService |
| Embedding generation for semantic search | Neo4jGenAIEmbeddingsService |
| Vector + hybrid search (70% vector, 30% keyword) | Neo4jVectorSearchService |
| Askesis RAG (question answering + suggestions) | AskesisService (LLM mode) |
| 12 AI intelligence services (BaseAIService) | Various |

---

## How to Configure

### For Development (Free)

Set one variable in your `.env`:

```bash
INTELLIGENCE_TIER=core
```

No OpenAI API key needed. The app starts without creating any AI services. All CRUD, analytics, daily planning, and search (keyword fallback) work normally.

### For Production (AI Enabled)

```bash
INTELLIGENCE_TIER=full
OPENAI_API_KEY=sk-...
```

Or simply set your API key — `full` is the default:

```bash
OPENAI_API_KEY=sk-...
```

### What Happens at Startup

The app logs which tier is active:

```
Intelligence tier: CORE (analytics only — no API costs)
```

or:

```
Intelligence tier: FULL (analytics + AI services)
```

Three service groups are gated:

1. **Embeddings** — `Neo4jGenAIEmbeddingsService` + `Neo4jVectorSearchService` — skipped in CORE
2. **LLM** — `LLMService` — skipped in CORE
3. **OpenAI** — `OpenAIService`, `SubmissionReportService`, `JournalOutputGenerator` — skipped in CORE

Services that depend on these (12 AI intelligence services, embedding background worker, etc.) are automatically skipped when their dependencies are `None`.

---

## How Features Degrade in CORE Mode

CORE mode is not broken FULL mode — it is a fully functional analytics-only system. Features that require AI return clear error messages rather than failing silently.

| Feature | FULL Behavior | CORE Behavior |
|---------|---------------|---------------|
| Search | Hybrid (vector + keyword) | Keyword only |
| Askesis chat | RAG-powered answers | 503 "requires FULL tier" |
| Feedback generation | LLM-generated analysis | Automatic markdown summary |
| Journal processing | AI content enrichment | Raw content stored, no enrichment |
| Life path service | AI-enhanced recommendations | Keyword extraction fallback |
| Content enrichment | Intelligent editing | Returns error with clear message |

---

## Per-User Tiers (Stub)

A per-user tier function exists for future billing integration:

```
System tier is the ceiling — no user exceeds it.
REGISTERED users always get CORE (free trial).
MEMBER and above get the system tier.
```

This is not wired into routes yet. It exists as a documented decision point for when paid subscriptions are introduced.

---

## Quick Reference

| Setting | Value | Effect |
|---------|-------|--------|
| `INTELLIGENCE_TIER=full` | Default | All services created, API key required |
| `INTELLIGENCE_TIER=core` | Free mode | Analytics only, no API calls |
| Unset | Same as `full` | Backward-compatible |
| Invalid value | Falls back to `full` | Logs warning |

## Reference Documentation

- `/docs/decisions/ADR-043-intelligence-tier-toggle.md` — Architecture decision record
- `/core/config/intelligence_tier.py` — Enum implementation
- `/services_bootstrap.py` — Three gating points
- `/adapters/inbound/ai_guard.py` — Route protection helpers
- `/core/services/intelligence_tier_service.py` — Per-user tier stub
