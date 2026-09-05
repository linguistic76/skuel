---
updated: 2026-09-05
---

# Graceful Degradation Architecture

**Status:** Active
**Date:** 2026-03-07
**Related:** [ADR-043 Intelligence Tier Toggle](../decisions/ADR-043-intelligence-tier-toggle.md)

## Core Principle

**SKUEL runs at full capability without any LLM or embedding service.**

The app is architecturally split into two layers. The foundational layer — CRUD, graph queries, analytics, user context, search, ingestion — has zero AI dependencies. AI services are an enhancement layer that can be toggled on or off with a single environment variable.

## Why This Matters

1. **Development velocity.** Working on ingestion YAML, file uploads, curriculum structure, or any "analog" workflow should never require an OpenAI API key. You iterate on fundamentals without paying API costs or waiting for embedding generation.

2. **Cost control.** `INTELLIGENCE_TIER=core` costs $0. No AI API calls are made. No AI background workers spin up. This is the right mode for content authoring, schema changes, and structural work.

   > **Background workers in CORE tier:** The `EmbeddingBackgroundWorker` (AI) does not start. The `ProgressReportWorker` (graph analytics only) does start — it is a CORE-tier Analog worker: it runs hourly, checks for scheduled reports, and generates `ActivityReport` nodes from graph data without any LLM calls. No API cost. The **schema-change monitor** is separate from both and gated by its own `NEO4J_SCHEMA_MONITORING` flag (default **off**). See the neo4j-cypher-patterns skill § Schema-Change Monitoring.

3. **Deployment flexibility.** A fresh deployment works immediately. Embeddings and AI features are activated when the curriculum is mature enough to benefit from them — not as a prerequisite.

4. **Testing isolation.** Unit and integration tests run without mocking AI services. The test suite defaults to FULL tier but every service gracefully handles `None` dependencies.

## The Two Layers

### Layer 1: Core ($0, always available)

| Capability | What It Does | Dependencies |
|-----------|-------------|--------------|
| CRUD | Create, read, update, delete all 25 entity types | Neo4j only |
| Ingestion | Markdown/YAML → Neo4j pipeline | Neo4j only |
| Keyword Search | Text search across the 12 searchable domains — case-INSENSITIVE `CONTAINS` | Neo4j property scan (fulltext indexes are synced at bootstrap but read only by the FULL-tier hybrid rung) |
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
| Embeddings | 1024-dim vectors on every embeddable entity type (the `EMBEDDING_EVENT_TYPES` keys) | OpenAI `text-embedding-3-small` @1024 (ADR-068; BGE adapter staged) |
| Vector Search | Semantic similarity, hybrid search, RRF | Embeddings + Neo4j vector indexes |
| Askesis | Socratic AI companion, ZPD-aware | LLM (OpenAI) |
| Feedback Generation | AI assessment of submissions | LLM |
| Audio Transcription | Voice → text conversion | Deepgram (`DEEPGRAM_API_KEY`) |
| Journal Processing | Transcription + AI analysis of audio entries | Deepgram + LLM |
| Content Enrichment | AI-powered content analysis | LLM |
| 12 AI Services | Domain-specific `BaseAIService` instances | LLM + Embeddings |

## How to Toggle

### Turn off AI/Embeddings (Core mode)

```bash
# In .env
INTELLIGENCE_TIER=core
```

**What happens:**
- `EmbeddingsService` — not created
- `Neo4jVectorSearchService` — not created
- `EmbeddingBackgroundWorker` — not started
- `LLMService` — not created
- OpenAI / Anthropic chat adapters + the OpenAI embedding client (`adapters/external/`, behind `ChatCompletionPort` / `EmbeddingClientOperations`; HF/BGE adapter staged — ADR-068) — not constructed (no API keys read, no vendor SDK clients; W1 / ADR-063)
- `DeepgramAdapter` / `TranscriptionService` / `BatchTranscriptionService` — not created (`DEEPGRAM_API_KEY` not read)
- All 12 `BaseAIService` instances — not created
- Search falls back to keyword (`CONTAINS` — the hybrid fulltext rung is FULL-tier only)
- Askesis is **not created** (requires FULL tier — no degraded mode)
- Vector indexes **not created** (unnecessary without embeddings)
- Full-text indexes still synced (created in both tiers; CORE has no reader yet — D1(b) follow-on)
- `ProgressReportWorker` **does start** (CORE-tier Analog worker — graph analytics, no API calls)

### Turn on AI/Embeddings (Full mode)

```bash
# In .env
INTELLIGENCE_TIER=full
```

Requires `OPENAI_API_KEY` (covers both embeddings and LLM chat — ADR-068) and `DEEPGRAM_API_KEY` (audio transcription). The embedding background worker starts automatically and processes entity embeddings in batches every 30 seconds.

## How Graceful Degradation Works

### Pattern: None-Propagation

The bootstrap creates AI services conditionally. When `INTELLIGENCE_TIER=core`, they remain `None`. Downstream code checks before using:

```python
# Bootstrap (services_bootstrap/compose.py)
embeddings_service = None
if tier.ai_enabled:
    from adapters.external.embeddings import create_embedding_client
    from core.services.embeddings_service import EmbeddingsService
    embeddings_service = EmbeddingsService(
        backend=EmbeddingsBackend(executor=query_executor),
        embedding_client=create_embedding_client(),
    )

# Downstream — worker only starts if service exists
if embeddings_service:
    embedding_worker = EmbeddingBackgroundWorker(...)

# Service constructors accept None
class PsService:
    def __init__(self, embeddings_service=None, ...):
        self.embeddings = embeddings_service  # Can be None

# Ingestion never embeds inline (ADR-074) — it publishes post-persist
# embedding events instead, and its event_bus is tier-gated at compose:
ingestion_service = UnifiedIngestionService(
    event_bus=event_bus if tier.ai_enabled else None,  # CORE → no publishes
    ...
)
```

### Pattern: Event-Driven Embedding (Zero Latency)

When AI is enabled, every write path — in-app create, in-app update (gated on `changed_fields` touching embeddable text), and both ingest doors post-persist — publishes `*EmbeddingRequested` through the one chokepoint (`core/events/embedding_publisher.py`, ADR-074) and never blocks on it:

```
User creates Task → returns immediately (0ms embedding latency)
    ↓ (async event)
EmbeddingBackgroundWorker picks up event 30s later
    ↓ (batch API call)
Embedding stored on Neo4j node
```

When AI is disabled, no worker exists and ingestion publishes nothing (its `event_bus` is `None` — compose-gated); in-app service publishes go to a subscriber-less bus and are dropped. The entity is created identically — it just doesn't have an embedding property.

### Pattern: Search Fallback

```python
# SearchRouter dispatches to the same domain services regardless of tier
# The hybrid rung is additive — text search always works

# With embeddings (FULL), for Ku/PathStep/LearningPath:
#   Lucene fulltext + vector similarity, RRF-fused (the hybrid rung)

# Every other case — CORE tier, or any other domain:
#   case-INSENSITIVE CONTAINS (the fulltext indexes exist but have no reader here).
#   The rung adds relevance ranking and vector recall, NOT case-insensitivity.
#
# One exception, off every search surface: the BACKEND _SearchMixin.search is
# case-SENSITIVE. Its only production caller is PsAiService.search_by_semantic_query's
# embedding-failure fallback (FULL tier only — .ai is None in CORE), so it is reached
# by neither /search nor /api/search/unified.
```

## Five Gating Points

All in `services_bootstrap/compose.py`:

| Gate | What It Controls | Core Behavior |
|------|-----------------|---------------|
| Deepgram block | `DeepgramAdapter`, `TranscriptionService`, `BatchTranscriptionService` | Skipped; `DEEPGRAM_API_KEY` not read |
| Embeddings block | `EmbeddingsService`, `Neo4jVectorSearchService` (embedding client adapter not built) | Skipped |
| LLM block | `LLMService` (built on the multi-provider `UnifiedLLMCaller` — `chat_clients.caller` — at FULL; routes per call by model prefix: gpt*→OpenAI, claude*→Anthropic) | Skipped |
| Chat-adapter block | `OpenAIChatAdapter` (`ChatCompletionPort`, `adapters/external/llm/`) → `ContentEnrichmentService`, `UnifiedLLMCaller`, `ProgressReportGenerator` | Adapter not built; consumers receive `chat_port=None` and degrade |
| Ingestion event-bus gate | `UnifiedIngestionService` + `BatchChunkingService` get `event_bus=event_bus if tier.ai_enabled else None` (ADR-074) | Ingestion publishes no embedding events — no queue-with-no-listener; chunks still persist |

Everything downstream of these five blocks naturally degrades via None-propagation.

## Error Handling in Bootstrap

`compose_services()` separates programming errors from configuration errors:

- **Programming errors** (`TypeError`, `AttributeError`, `ImportError`, `NameError`) **propagate** — they indicate real bugs in service wiring and must not be masked.
- **Configuration/infrastructure errors** (missing API keys, Neo4j unavailable, etc.) are caught and returned as `Result.fail()` for the caller to handle.
- **Post-construction wiring** is validated at the end of bootstrap — 10 attributes that are set after service construction are checked for `None`. Missing wiring fails fast with a clear message.

## Switching Between Modes

Switching from CORE → FULL:
1. Set `INTELLIGENCE_TIER=full` in `.env`
2. Ensure `OPENAI_API_KEY` is set (covers embeddings + LLM — ADR-068)
3. Ensure `DEEPGRAM_API_KEY` is set (audio transcription)
4. Restart the app
5. Existing entities without embeddings will get them as they're updated (update paths publish through the ADR-074 chokepoint), or run `scripts/generate_embeddings_batch.py` for bulk backfill — add `--stale` to re-embed entities edited or re-synced while in CORE

Switching from FULL → CORE:
1. Set `INTELLIGENCE_TIER=core` in `.env`
2. Restart the app
3. Existing embeddings remain on nodes (not deleted) — they're just not used
4. No API costs from this point (`OPENAI_API_KEY` and `DEEPGRAM_API_KEY` are not read)

## Key Files

| File | Purpose |
|------|---------|
| `core/config/intelligence_tier.py` | `IntelligenceTier` enum, `from_env()` |
| `services_bootstrap/compose.py` | Bootstrap: index sync (tier-gated) + the 5 AI gating points |
| `adapters/persistence/neo4j/neo4j_schema_manager.py` | `sync_fulltext_indexes()` (always), `sync_vector_indexes()` (FULL only) |
| `core/services/intelligence_tier_service.py` | Per-user tier gate (`get_user_intelligence_tier`) consumed by the AI routes |
| `.env` | `INTELLIGENCE_TIER=core\|full` |
| `core/services/background/embedding_worker.py` | Only starts when embeddings service exists |
| `core/events/embedding_publisher.py` | The one `*EmbeddingRequested` publish chokepoint (ADR-074) — ingestion never embeds inline |
