# Analog + Digital Architecture

**Status:** Active
**Date:** 2026-03-07

## The Idea

SKUEL is built on a deliberate separation between two architectural layers:

- **Analog** — the structural layer. Graph relationships, CRUD operations, content ingestion, keyword search, analytics, user context. This layer is complete on its own. It represents the curriculum, the student's work, and the relationships between them using Neo4j's native graph capabilities. No API keys, no external services, no per-query costs.

- **Digital** — the intelligence layer. Embeddings, vector search, LLM-powered feedback, semantic similarity, AI companions. This layer enhances the Analog layer with machine understanding. It requires external APIs (OpenAI) and costs money per call.

The critical design decision: **the Analog layer is not a degraded version of the Digital layer.** It is the foundation. The app is fully functional — content can be authored, ingested, searched, organized, submitted, and reviewed — without any AI service running.

## Why This Separation Exists

### 1. Content comes first

SKUEL's value starts with curriculum structure. A teacher writes Articles, organizes Kus, builds Learning Paths, creates Exercises. A student submits work, receives feedback, revises. None of this requires embeddings or LLMs. The graph *is* the knowledge — relationships like `USES_KU`, `ORGANIZES`, `FULFILLS_EXERCISE`, and `SERVES_LIFE_PATH` encode meaning structurally.

Embeddings add a similarity dimension on top of this structure. They don't replace it.

### 2. Development phases are real

When building curriculum content — writing YAML front matter, adjusting ingestion pipelines, testing file uploads — embedding generation is noise. Every ingested file triggers API calls that cost money, add latency to logs, and produce vectors for content that will change five more times. The Analog layer lets you iterate on fundamentals without that overhead.

When the content is stable and you want semantic search, recommendation, and AI feedback — switch to Digital.

### 3. Cost is a design constraint, not a bug

Running 13 entity types through `text-embedding-3-small` at scale is cheap but not free. More importantly, LLM calls for feedback generation, Askesis conversations, and content enrichment add up. The Analog layer gives you a $0 operating cost floor. You choose when to spend.

### 4. Testability

The test suite runs 1966 tests without any API mocking for AI services. Services accept `None` for their AI dependencies and behave correctly. This is not accidental — it's the architectural guarantee that the Analog layer is self-sufficient.

## What Each Layer Provides

### Analog Layer (always available)

| Domain | Capability |
|--------|-----------|
| **Curriculum** | Article, Ku, Exercise, LearningStep, LearningPath authoring and ingestion |
| **Activity** | Task, Goal, Habit, Event, Choice, Principle — full CRUD with status transitions |
| **Search** | Keyword search across 12 domains via Neo4j fulltext indexes |
| **User Context** | ~250-field UserContext built from MEGA-QUERY (standard + rich) |
| **Analytics** | 13 BaseAnalyticsService instances — graph traversal, no AI |
| **Intelligence** | UserContextIntelligence — daily planning, life path alignment, schedule-aware recommendations |
| **Relationships** | Lateral relationships, ORGANIZES hierarchy, SERVES_LIFE_PATH |
| **Ingestion** | Markdown/YAML -> Neo4j pipeline with chunking (chunks stored, not embedded) |
| **Learning Loop** | Article -> Exercise -> Submission -> Feedback -> RevisedExercise (manual feedback) |
| **Calendar** | Schedule aggregation across Tasks, Events, Habits, Goals |

### Digital Layer (opt-in, requires `INTELLIGENCE_TIER=full`)

| Domain | Capability | What It Adds |
|--------|-----------|-------------|
| **Embeddings** | 1536-dim vectors on 13 entity types | Semantic representation of content |
| **Vector Search** | Hybrid search (keyword + vector + RRF) | "Find similar" across domains |
| **Askesis** | Socratic AI companion, ZPD-aware | Personalized learning dialogue |
| **Feedback** | AI-generated SubmissionFeedback | Automated assessment |
| **Journals** | Voice transcription + AI analysis | Audio-to-text processing |
| **Content Enrichment** | Quality analysis, complexity scoring | Automated content metadata |
| **12 AI Services** | Domain-specific BaseAIService instances | Per-domain AI capabilities |

## The Toggle

One environment variable controls everything:

```bash
# Analog only ($0, no API calls)
INTELLIGENCE_TIER=core

# Analog + Digital (API costs)
INTELLIGENCE_TIER=full
```

Three gating points in `services_bootstrap.py` check `IntelligenceTier.from_env()`. When `core`, the AI services are never created. All downstream code receives `None` and handles it through the None-propagation pattern.

**See:** [Graceful Degradation Architecture](/docs/architecture/GRACEFUL_DEGRADATION_ARCHITECTURE.md) for implementation details — the three gating points, None-propagation pattern, event-driven embedding architecture, and search fallback behavior.

## The Relationship Between Layers

The Digital layer is **additive, never replacing**:

- Keyword search works in both modes. Vector search adds similarity results on top.
- Manual teacher feedback works in both modes. AI feedback adds automated assessment on top.
- Graph-based analytics work in both modes. AI services add LLM-powered insights on top.
- Content chunks are created during ingestion in both modes. Embeddings add vectors to those chunks on top.

When switching from Digital back to Analog, nothing is lost. Existing embeddings remain on nodes — they just aren't queried. Switching back to Digital reactivates them instantly.

## Switching Modes

**Analog -> Digital:**
1. Set `INTELLIGENCE_TIER=full` in `.env`
2. Ensure `OPENAI_API_KEY` is configured
3. Restart the app
4. Run `scripts/generate_embeddings_batch.py` to backfill embeddings on existing entities

**Digital -> Analog:**
1. Set `INTELLIGENCE_TIER=core` in `.env`
2. Restart the app
3. Existing embeddings stay on nodes (zero cleanup needed)

## Key Files

| File | Role |
|------|------|
| `core/config/intelligence_tier.py` | `IntelligenceTier` enum — the toggle |
| `services_bootstrap.py` | Three gating points for AI service creation |
| `adapters/inbound/ai_guard.py` | Route-level guards for AI endpoints |
| `core/services/base_analytics_service.py` | Analog intelligence base (no AI deps) |
| `core/services/base_ai_service.py` | Digital intelligence base (requires LLM + embeddings) |
| `core/utils/embedding_text_builder.py` | Field mappings for 13 entity types |
| `core/services/background/embedding_worker.py` | Event-driven embedding (only starts in Digital mode) |
