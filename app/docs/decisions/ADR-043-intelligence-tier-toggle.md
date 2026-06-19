# ADR-043: Intelligence Tier Toggle

**Status:** Accepted
**Date:** 2026-03-04
**Deciders:** Mike, Claude

> **SDK wiring superseded by [ADR-063](ADR-063-llm-embeddings-sdk-ports.md) (W1, 2026-05-26).** The tier-toggle decision below — CORE vs FULL and the gating points — is unchanged. Only the vendor-SDK services moved: `OpenAIService` no longer exists. The OpenAI/Anthropic chat clients now live behind `ChatCompletionPort` in `adapters/external/llm/`, and the HuggingFace embedding client behind `EmbeddingClientOperations` in `adapters/external/embeddings/`. Read `OpenAIService` below as "the OpenAI chat adapter + its consumers (`ContentEnrichmentService` / `UnifiedLLMCaller` / `ProgressReportGenerator`)".

## Context

SKUEL has an implicit two-layer intelligence split enforced architecturally:

- **Analytics layer** (`BaseAnalyticsService`): 13 intelligence services + `UserContextIntelligence` + `GraphIntelligenceService`. Pure Python + Cypher. No API costs. Structurally prevented from having LLM attributes.
- **AI layer** (`BaseAIService` + `OpenAIService` + `HuggingFaceEmbeddingsService`): 12 AI services, embeddings, LLM chat, content processing. Costs money per API call.

The split was implicit — controlled by whether `OPENAI_API_KEY` existed. `OpenAIService` was always created even with an invalid key. There was no deliberate system-level control and no per-user tier concept.

## Decision

Make the implicit explicit with a single environment variable `INTELLIGENCE_TIER`.

### Two Tiers

| Tier | Value | What's Enabled | Cost |
|------|-------|----------------|------|
| **CORE** | `core` | BaseAnalyticsService (13 services), UserContextIntelligence, GraphIntelligenceService, all CRUD, keyword search, UserContext, daily planning | $0 |
| **FULL** | `full` | Everything in CORE + 12 BaseAIService instances, OpenAIService, HuggingFaceEmbeddingsService, vector search, content processing, feedback generation | API costs |

### Gating Points (3)

All in `services_bootstrap.py`:

1. **Vector indexes** (`compose_services`): `sync_vector_indexes()` — skipped in CORE (full-text indexes always created)
2. **Embeddings** (`_create_learning_services`): `HuggingFaceEmbeddingsService` + `Neo4jVectorSearchService` — skipped in CORE
3. **LLM** (`compose_services`): `LLMService` — skipped in CORE
4. **OpenAI** (`compose_services`): `OpenAIService`, `ExerciseReportService`, `JournalOutputService` — skipped in CORE

### Downstream (No Changes Needed)

These blocks naturally skip when their dependencies are `None`:
- `if llm_service and embeddings_service:` — 12 AI services
- `if embeddings_service:` — EmbeddingBackgroundWorker
- `AskesisService` — degrades gracefully with `llm_service=None`
- `LifePathService` — falls back to keyword extraction
- `ProgressReportGenerator` — falls back to AUTOMATIC processor type
- `ContentEnrichmentService` — returns `Result.fail()` on AI methods

### Per-User Tier Stub

`get_user_intelligence_tier(system_tier, user_role)` in `core/services/intelligence_tier_service.py`:
- System tier is ceiling — no user exceeds it
- `REGISTERED` always gets CORE (free trial)
- `MEMBER+` gets system tier

Wired into `adapters/inbound/ai_routes.py:_ai_route` (June 2026): after the system-level 503 guard, `REGISTERED` users on a FULL-tier system receive a 403 with an upgrade prompt; `MEMBER+` receive the system tier.

### Route Protection

`adapters/inbound/ai_guard.py` provides `is_ai_available()` and `ai_unavailable_result()`. Defense-in-depth guards added on Askesis RAG and suggestions endpoints.

### Relationship to FeatureFlags

`IntelligenceTier` is the system gate (binary: does it cost API money?). `FeatureFlags` are granular knobs within FULL mode. They are complementary, not overlapping.

## Consequences

### Positive
- Single env var controls all AI costs
- Zero code changes for FULL mode (backward-compatible default)
- CORE mode works perfectly for development, testing, demos
- Per-user tier gate live in AI routes: REGISTERED→403, MEMBER+→system tier
- Bug fix: OpenAIService no longer created with invalid/missing keys

### Negative
- Content processing (journals, feedback) unavailable in CORE mode
- Vector/semantic search unavailable in CORE mode (keyword fallback works)

### Neutral
- Existing `FeatureFlags` unchanged
- Test suite defaults to FULL tier (no test changes needed)

## Key Files

| File | Purpose |
|------|---------|
| `core/config/intelligence_tier.py` | `IntelligenceTier` enum + `from_env()` |
| `core/config/unified_config.py` | `intelligence_tier` field on `UnifiedConfig` |
| `services_bootstrap.py` | 3 gating points + `Services.intelligence_tier` |
| `adapters/inbound/ai_guard.py` | Route-level guard helpers |
| `core/services/intelligence_tier_service.py` | Per-user tier stub |
