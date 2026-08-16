# Analog + Digital Architecture

**Status:** Active
**Date:** 2026-03-07

## The Idea

SKUEL is built on a deliberate separation between two architectural layers:

- **Analog** — the structural layer. Graph relationships, CRUD operations, content ingestion, keyword search, analytics, user context. This layer is complete on its own. It represents the curriculum, the student's work, and the relationships between them using Neo4j's native graph capabilities. No API keys, no external services, no per-query costs.

- **Digital** — the intelligence layer. Embeddings, vector search, LLM-powered feedback, semantic similarity, AI companions. This layer enhances the Analog layer with machine understanding. It requires an external API (OpenAI for both embeddings and LLM — ADR-068) and costs money per call.

The critical design decision: **the Analog layer is not a degraded version of the Digital layer.** It is the foundation. The app is fully functional — content can be authored, ingested, searched, organized, submitted, and reviewed — without any AI service running.

## Why This Separation Exists

### 1. Content comes first

SKUEL's value starts with curriculum structure. A teacher writes Articles, organizes Kus, builds Learning Paths, creates Exercises. A student submits work, receives feedback, revises. None of this requires embeddings or LLMs. The graph *is* the knowledge — relationships like `USES_KU`, `ORGANIZES`, `FULFILLS_EXERCISE`, and `SERVES_LIFE_PATH` encode meaning structurally.

Embeddings add a similarity dimension on top of this structure. They don't replace it.

### 2. Development phases are real

When building curriculum content — writing YAML front matter, adjusting ingestion pipelines, testing file uploads — embedding generation is noise. In FULL tier, every ingested file enqueues background embedding work (ADR-074) that costs API money and produces vectors for content that will change five more times. The Analog layer lets you iterate on fundamentals without that overhead.

When the content is stable and you want semantic search, recommendation, and AI feedback — switch to Digital.

### 3. Cost is a design constraint, not a bug

Running 16 entity types through `text-embedding-3-small` (ADR-068; BGE staged as the long-term swap) at scale is cheap but not free. More importantly, LLM calls for feedback generation, Askesis conversations, and content enrichment add up. The Analog layer gives you a $0 operating cost floor. You choose when to spend.

### 4. Testability

The test suite runs without any API mocking for AI services. Services accept `None` for their AI dependencies and behave correctly. This is not accidental — it's the architectural guarantee that the Analog layer is self-sufficient.

## What Each Layer Provides

### Analog Layer (always available)

| Domain | Capability |
|--------|-----------|
| **Curriculum** | Ku, Exercise, PathStep, LearningPath authoring and ingestion |
| **Activity** | Task, Goal, Habit, Event, Choice, Principle — full CRUD with status transitions |
| **Search** | Keyword search across the 12 searchable domains — case-sensitive `CONTAINS` (the fulltext indexes are created here but read only by the FULL-tier hybrid rung; CORE-tier fulltext is the D1(b) follow-on) |
| **User Context** | ~250-field UserContext built from MEGA-QUERY (standard + rich) |
| **Analytics** | 13 BaseAnalyticsService instances — graph traversal, no AI |
| **Intelligence** | UserContextIntelligence — daily planning, life path alignment, schedule-aware recommendations |
| **Relationships** | Lateral relationships, ORGANIZES hierarchy, SERVES_LIFE_PATH |
| **Ingestion** | Markdown/YAML -> Neo4j pipeline with chunking (chunks stored, not embedded) |
| **Learning Loop** | Exercise -> UserEntry -> EntryReport -> RevisedExercise (4 phases, manual feedback; PathStep anchors via HAS_EXERCISE) |
| **Calendar** | Schedule aggregation across Tasks, Events, Habits, Goals |

### Digital Layer (opt-in, requires `INTELLIGENCE_TIER=full`)

| Domain | Capability | What It Adds |
|--------|-----------|-------------|
| **Embeddings** | 1024-dim vectors on content-bearing entity types (OpenAI `text-embedding-3-small` @1024 — ADR-068; BGE adapter staged) | Semantic representation of content |
| **Vector Search** | Hybrid search (keyword + vector + RRF) | "Find similar" across domains |
| **Askesis** | Socratic AI companion, ZPD-aware | Personalized learning dialogue |
| **Reports** | AI-generated EntryReport | Automated assessment |
| **Journals** | Voice transcription + AI analysis | Audio-to-text processing |
| **Content Enrichment** | Quality analysis, complexity scoring | Automated content metadata |
| **12 AI Services** | Domain-specific BaseAIService instances | Per-domain AI capabilities |

**Staged (not yet a capability):** Neo4j **Graph Data Science (GDS/AuraDS)** — centrality, shortest-path over the prerequisite DAG, community detection, structural similarity — is another Digital-layer enhancer, deliberately deferred until the knowledge graph is dense enough to compute over (ADR-080). Like the rows above it *enhances* an Analog fallback (heuristic ZPD, hand-authored MOCs, text-vector similarity) rather than replacing the meaning layer; unlike them it is **density-gated**, not just tier-gated, and rides a **separate paid product line** (AuraDS ≠ AuraDB Free). **See:** [ADR-080](../decisions/ADR-080-auradb-three-horizon-strategy.md).

## The Toggle

One environment variable controls everything:

```bash
# Analog only ($0, no API calls)
INTELLIGENCE_TIER=core

# Analog + Digital (API costs)
INTELLIGENCE_TIER=full
```

At bootstrap, `services_bootstrap/compose.py` checks `IntelligenceTier.from_env()`:

- **Always created (both tiers):** Auth indexes, domain indexes (UID, user_uid, status, date, composite), and **full-text indexes** for 14 domain labels (the 12 searchable domains + FormTemplate/FormSubmission) via `Neo4jSchemaManager.sync_fulltext_indexes()`. This is the Cypher-first search foundation — created in both tiers, but read only by the FULL-tier SearchRouter hybrid rung (Ku/PathStep/LearningPath). CORE-tier text search is `CONTAINS`; giving CORE a fulltext-only path is the named D1(b) follow-on.
- **FULL tier only:** Vector indexes (1024-dim, cosine similarity) on Entity, ContentChunk, ReferenceChunk, Ku, PathStep and LearningPath via `sync_vector_indexes()`. AI services (embeddings, LLM, vector search) are created. Background embedding worker starts.
- **CORE tier:** Vector indexes and all AI services are skipped. All downstream code receives `None` and handles it through the None-propagation pattern.

**See:** [Graceful Degradation Architecture](/docs/architecture/GRACEFUL_DEGRADATION_ARCHITECTURE.md) for implementation details — the three gating points, None-propagation pattern, event-driven embedding architecture, and search fallback behavior.

## The Relationship Between Layers

The Digital layer is **additive, never replacing**:

- Keyword search works in both modes. Vector search adds similarity results on top.
- Manual teacher feedback works in both modes. AI feedback adds automated assessment on top.
- Graph-based analytics work in both modes. AI services add LLM-powered insights on top.
- Content chunks are created during ingestion in both modes and through both ingest doors — single-file and batch/directory share one PathStep chunk step (ADR-074). Embeddings add vectors to those chunks on top: in FULL, ingestion publishes `ChunkEmbeddingRequested` post-persist; in CORE, chunks persist unembedded.

When switching from Digital back to Analog, nothing is lost. Existing embeddings remain on nodes — they just aren't queried. Switching back to Digital reactivates them instantly.

## Switching Modes

**Analog -> Digital:**
1. Set `INTELLIGENCE_TIER=full` in `.env`
2. Ensure `OPENAI_API_KEY` is configured (covers embeddings + LLM — ADR-068)
3. Ensure `DEEPGRAM_API_KEY` is configured (audio transcription)
4. Restart the app
5. Run `scripts/generate_embeddings_batch.py` to backfill missing embeddings on existing entities, and `--stale` to re-embed entities that were edited or re-synced while Digital was off (ADR-074)

**Digital -> Analog:**
1. Set `INTELLIGENCE_TIER=core` in `.env`
2. Restart the app
3. Existing embeddings stay on nodes (zero cleanup needed)
4. `OPENAI_API_KEY` and `DEEPGRAM_API_KEY` are not read — no API costs from this point

## Key Files

| File | Role |
|------|------|
| `core/config/intelligence_tier.py` | `IntelligenceTier` enum — the toggle |
| `services_bootstrap/compose.py` | Bootstrap orchestration: index sync + tier-gated AI service creation |
| `adapters/persistence/neo4j/neo4j_schema_manager.py` | `sync_fulltext_indexes()` (always), `sync_vector_indexes()` (FULL only), `sync_domain_indexes()` (always) |
| `core/services/intelligence_tier_service.py` | Per-user tier gate consumed by the AI routes |
| `core/services/base_analytics_service.py` | Analog intelligence base (no AI deps) |
| `core/services/base_ai_service.py` | Digital intelligence base (requires LLM + embeddings) |
| `core/utils/embedding_text_builder.py` | Field mappings for 16 content-bearing entity types |
| `core/services/background/embedding_worker.py` | Event-driven embedding (only starts in Digital mode) |
