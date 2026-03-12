# Graceful Degradation Architecture

**Status:** Active
**Date:** 2026-03-07
**Related:** [ADR-043 Intelligence Tier Toggle](/docs/decisions/ADR-043-intelligence-tier-toggle.md)

## Core Principle

**SKUEL runs at full capability without any LLM or embedding service.**

The app is architecturally split into two layers. The foundational layer — CRUD, graph queries, analytics, user context, search, ingestion — has zero AI dependencies. AI services are an enhancement layer that can be toggled on or off with a single environment variable.

## Why This Matters

1. **Development velocity.** Working on ingestion YAML, file uploads, curriculum structure, or any "analog" workflow should never require a HuggingFace API token. You iterate on fundamentals without paying API costs or waiting for embedding generation.

2. **Cost control.** `INTELLIGENCE_TIER=core` costs $0. No API calls are made. No background workers spin up. This is the right mode for content authoring, schema changes, and structural work.

3. **Deployment flexibility.** A fresh deployment works immediately. Embeddings and AI features are activated when the curriculum is mature enough to benefit from them — not as a prerequisite.

4. **Testing isolation.** Unit and integration tests run without mocking AI services. The test suite defaults to FULL tier but every service gracefully handles `None` dependencies.

## The Two Layers

### Layer 1: Core ($0, always available)

| Capability | What It Does | Dependencies |
|-----------|-------------|--------------|
| CRUD | Create, read, update, delete all 18 entity types | Neo4j only |
| Ingestion | Markdown/YAML → Neo4j pipeline | Neo4j only |
| Keyword Search | Full-text search across 12 domains | Neo4j fulltext indexes |
| UserContext | ~250-field user state (standard + rich) | Neo4j MEGA-QUERY |
| Analytics | 13 `BaseAnalyticsService` instances | Neo4j + Python |
| UserContextIntelligence | Daily planning, life path alignment | Neo4j + Python |
| Calendar | Schedule aggregation across domains | Neo4j + Python |
| Activity DSL | Natural-language task/goal parsing | Pure Python |
| Content Chunking | Semantic chunking for RAG readiness | Pure Python |
| Lateral Relationships | Cross-domain graph relationships | Neo4j |

### Layer 2: AI (API costs, opt-in)

| Capability | What It Does | Dependencies |
|-----------|-------------|--------------|
| Embeddings | 1024-dim vectors on 13 entity types | HuggingFace Inference API (Python-side) |
| Vector Search | Semantic similarity, hybrid search, RRF | Embeddings + Neo4j vector indexes |
| Askesis | Socratic AI companion, ZPD-aware | LLM (OpenAI) |
| Feedback Generation | AI assessment of submissions | LLM |
| Journal Processing | Voice transcription + AI analysis | Deepgram + LLM |
| Content Enrichment | AI-powered content analysis | LLM |
| 12 AI Services | Domain-specific `BaseAIService` instances | LLM + Embeddings |

## How to Toggle

### Turn off AI/Embeddings (Core mode)

```bash
# In .env
INTELLIGENCE_TIER=core
```

**What happens:**
- `HuggingFaceEmbeddingsService` — not created
- `Neo4jVectorSearchService` — not created
- `EmbeddingBackgroundWorker` — not started
- `LLMService` — not created
- `OpenAIService` — not created
- All 12 `BaseAIService` instances — not created
- Search falls back to keyword (fulltext indexes)
- Askesis is **not created** (requires FULL tier — no degraded mode)
- Vector indexes still synced at bootstrap (idempotent, ready for when you switch back)

### Turn on AI/Embeddings (Full mode)

```bash
# In .env
INTELLIGENCE_TIER=full
```

Requires `HF_API_TOKEN` (for embeddings) and optionally `OPENAI_API_KEY` (for LLM features). The embedding background worker starts automatically and processes entity embeddings in batches every 30 seconds.

## How Graceful Degradation Works

### Pattern: None-Propagation

The bootstrap creates AI services conditionally. When `INTELLIGENCE_TIER=core`, they remain `None`. Downstream code checks before using:

```python
# Bootstrap (services_bootstrap.py)
embeddings_service = None
if tier.ai_enabled:
    from core.services.embeddings_service import HuggingFaceEmbeddingsService
    embeddings_service = HuggingFaceEmbeddingsService(executor=query_executor)

# Downstream — worker only starts if service exists
if embeddings_service:
    embedding_worker = EmbeddingBackgroundWorker(...)

# Service constructors accept None
class ArticleService:
    def __init__(self, embeddings_service=None, ...):
        self.embeddings = embeddings_service  # Can be None

# Ingestion works with or without
class UnifiedIngestionService:
    def __init__(self, embeddings_service=None, ...):
        if self.embeddings:
            logger.info("Embeddings available during ingestion")
        else:
            logger.warning("Ingestion works without embeddings")
```

### Pattern: Event-Driven Embedding (Zero Latency)

When AI is enabled, entity creation publishes embedding events but never blocks on them:

```
User creates Task → returns immediately (0ms embedding latency)
    ↓ (async event)
EmbeddingBackgroundWorker picks up event 30s later
    ↓ (batch API call)
Embedding stored on Neo4j node
```

When AI is disabled, no events are published and no worker exists. The entity is created identically — it just doesn't have an embedding property.

### Pattern: Search Fallback

```python
# SearchRouter dispatches to the same domain services regardless of tier
# Vector search is additive — keyword search always works

# With embeddings (FULL):
#   keyword results + vector similarity + RRF fusion

# Without embeddings (CORE):
#   keyword results only (Neo4j fulltext indexes)
```

## Three Gating Points

All in `services_bootstrap.py`:

| Gate | What It Controls | Core Behavior |
|------|-----------------|---------------|
| Embeddings block | `HuggingFaceEmbeddingsService`, `Neo4jVectorSearchService` | Skipped |
| LLM block | `LLMService` | Skipped |
| OpenAI block | `OpenAIService`, `SubmissionReportService`, `JournalOutputGenerator` | Skipped |

Everything downstream of these three blocks naturally degrades via None-propagation.

## Switching Between Modes

Switching from CORE → FULL:
1. Set `INTELLIGENCE_TIER=full` in `.env`
2. Ensure `HF_API_TOKEN` is set (and `OPENAI_API_KEY` for LLM features)
3. Restart the app
4. Existing entities without embeddings will get them as they're updated, or run `scripts/generate_embeddings_batch.py` for bulk backfill

Switching from FULL → CORE:
1. Set `INTELLIGENCE_TIER=core` in `.env`
2. Restart the app
3. Existing embeddings remain on nodes (not deleted) — they're just not used
4. No API costs from this point

## Key Files

| File | Purpose |
|------|---------|
| `core/config/intelligence_tier.py` | `IntelligenceTier` enum, `from_env()` |
| `services_bootstrap.py` | 3 gating points |
| `adapters/inbound/ai_guard.py` | Route-level guard (`is_ai_available()`) |
| `.env` | `INTELLIGENCE_TIER=core\|full` |
| `core/services/background/embedding_worker.py` | Only starts when embeddings service exists |
| `core/services/ingestion/preparer.py` | Generates embeddings only if service injected |
