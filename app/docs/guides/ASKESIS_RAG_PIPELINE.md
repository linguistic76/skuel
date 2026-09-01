---
updated: 2026-08-31
---

# Askesis RAG Pipeline — Developer Guide

**Last Updated:** August 2026 (intent activation — PR-2)

**Audience:** Developers building, debugging, or extending Askesis's question-answering capabilities.

**Purpose:** This guide explains how content flows from upload through embedding to retrieval-augmented generation (RAG). It is the single document a developer needs to understand how Askesis answers questions using embedded content stored in Neo4j.

---

## The Pipeline at a Glance

```
UPLOAD ─→ INGEST ─→ EMBED ─→ STORE ─→ [user asks question] ─→ RETRIEVE ─→ GENERATE ─→ ANSWER
```

Each stage has a single responsible service. The entire pipeline is async.

---

## Stage 1: Ingestion — Content Enters the System

**Service:** `UnifiedIngestionService` (`core/services/ingestion/unified_ingestion_service.py`)

**Entry point:** `ingest_file(file_path, ...)` or the API at `POST /api/ingest/file`

**What happens:**

1. **Format detection** — Markdown or YAML
2. **Parsing** — Extract frontmatter/metadata + content body
3. **Entity type detection** — PathStep, KU, Exercise, etc.
4. **Field validation** — Required fields checked per entity type
5. **Data preparation** — `prepare_entity_data()` in `core/services/ingestion/preparer.py` (sync, one path for both ingest doors):
   - Generate/normalize UIDs
   - Extract content body
   - Handle relationships
   - Add timestamps
6. **Neo4j write** — Entity node created (PathStep `content` is popped pre-write; it lives on the `:Content` node, never the entity)
7. **Post-persist embedding publish** — the entity's `*EmbeddingRequested` event goes through the one chokepoint (`core/events/embedding_publisher.py`); the background worker embeds asynchronously (see Stage 2)

**Key detail (ADR-074):** Ingestion never embeds inline. The entity arrives in Neo4j immediately; its embedding lands within ~30s when the background worker processes the event (FULL tier only — in CORE, ingestion's `event_bus` is `None` and nothing publishes).

---

## Stage 2: Embedding — Content Becomes Searchable

**Service:** `EmbeddingsService` (`core/services/embeddings_service.py`)

**Model:** OpenAI `text-embedding-3-small` at 1024 dimensions via the API `dimensions` parameter (ADR-068; BGE/HuggingFace adapter staged as the long-term swap). The client lives behind `EmbeddingClientOperations` (`adapters/external/embeddings/`, factory `create_embedding_client()`).

**Two paths to embedding (ADR-074):**

| Path | When | Service |
|------|------|---------|
| **Event pipeline** | Every write path — in-app create, in-app update (`changed_fields` gate), and both ingest doors post-persist — publishes `*EmbeddingRequested`. One-shot script syncs (`./dev vault-sync`) ride the same path: they subscribe the worker pre-sync and `drain()` post-sync, in-process | `EmbeddingBackgroundWorker` in `core/services/background/embedding_worker.py` — app process: batches of 25 every 30s; script process: one-shot drain |
| **Backfill script** | Backstop for pre-existing gaps: missing embeddings (default) or stale ones (`--stale`: edited/re-synced after last embed — e.g. while in CORE tier — or version drift) | `scripts/generate_embeddings_batch.py` (service-mediated, same version metadata as the worker) |

### Text Extraction

Before embedding, the system extracts the right text fields per entity type. This is the single source of truth:

**File:** `core/utils/embedding_text_builder.py`
**Function:** `build_embedding_text(entity_type, source)`

```python
# Field mappings (subset — full list in EMBEDDING_FIELD_MAPS)
EntityType.PATH_STEP:  ("title", "intent", "description", "summary")  # NO "content" — body = CHUNK vectors
EntityType.KU:         ("title", "summary", "description")
EntityType.TASK:       ("title", "description")
EntityType.GOAL:       ("title", "description", "vision_statement")
EntityType.HABIT:      ("title", "description", "cue", "reward")
EntityType.EXERCISE:   ("title", "instructions", "description")
```

Curriculum types use `"\n\n"` between fields; activity types use `"\n"`. Every key of `EMBEDDING_FIELD_MAPS` is supported by the builder — the map is the list — but whether a type is actually *embedded* is decided by `EMBEDDING_EVENT_TYPES` (`core/events/embedding_publisher.py`); a map with no event class is hollow and registered in the bloat detector's `PLANNED_EMBEDDING_MAPS`.

**PathStep is deliberate (ADR-074):** the entity vector covers frontmatter fields only, on every trigger path. Body-content semantics live in the CHUNK embeddings (Stage 3).

### Embedding Storage

Each embedded entity gets five properties on its Neo4j node (written through `EmbeddingsService.store_embedding_with_metadata` — one write path for worker and backfill):

```
n.embedding             → list[float]  (1024 dimensions)
n.embedding_model       → "text-embedding-3-small"
n.embedding_version     → "v3"
n.embedding_updated_at  → datetime
n.embedding_text_hash   → sha256 of the embedded text (ADR-074 §8 — the
                          pre-generation skip signal; chunks keep raw
                          embedding_source_text instead)
```

### Retry Strategy

Embedding API calls use exponential backoff: up to 3 attempts with 2s → 4s → 8s delays (tenacity, in the adapter). Text is truncated to the client's `max_input_chars` (OpenAI adapter: 24000 chars ≈ 6k tokens) before sending.

### Version Tracking

Current version is `EMBEDDING_VERSION = "v3"` (`core/services/embeddings_service.py` — OpenAI @1024, ADR-068). The `embedding_version` property allows re-embedding outdated vectors: `scripts/generate_embeddings_batch.py --stale` re-embeds any node whose version mismatches or whose `updated_at` outran `embedding_updated_at` (ADR-074).

---

## Stage 3: Chunking — Long Content Gets Subdivided

**Service:** `EntityChunkingService` (`core/services/entity_chunking_service.py`)

**When:** Post-persist, for `chunks_body_content` entities (PathStep, Ku) — one shared step (`UnifiedIngestionService._chunk_entity_content`) for both ingest doors (ADR-074).

**What happens:**
1. The popped content body is split into semantic chunks
2. Chunk metadata generated (word count, complexity)
3. Persisted as `(PathStep)-[:HAS_CONTENT]->(:Content)-[:HAS_CHUNK]->(:ContentChunk)` nodes
4. One `ChunkEmbeddingRequested` publishes with every persisted chunk id — the worker embeds the chunks (FULL tier; in CORE, chunks persist unembedded)

A re-ingest with an emptied body takes the explicit clear path instead: the stale `:Content` subtree is deleted and `word_count` reset to 0.

**Why it matters for RAG:** Chunking enables fine-grained retrieval — the system can match against specific sections of a long article rather than the whole document.

---

## Stage 4: Retrieval — Finding Relevant Content

When a user asks Askesis a question, the system retrieves relevant content through multiple complementary strategies.

### 4a. Vector Search

**Service:** `Neo4jVectorSearchService` (`core/services/neo4j_vector_search_service.py`)

**Core mechanism:** Neo4j's native vector index with cosine similarity:

```cypher
CALL db.index.vector.queryNodes($index_name, $limit, $embedding)
YIELD node, score
WHERE score >= $min_score
RETURN node, score
ORDER BY score DESC
```

**Four search modes:**

| Mode | Method | Use Case |
|------|--------|----------|
| **Vector-only** | `find_similar_by_text()` | Pure semantic similarity |
| **Hybrid** | `hybrid_search()` | Vector + full-text via Reciprocal Rank Fusion |
| **Learning-aware** | `learning_aware_search()` | Boosts based on user's mastery state |
| **Semantic-enhanced** | `semantic_enhanced_search()` | Boosts based on graph relationships |

#### Hybrid Search (RRF)

Combines vector similarity and full-text keyword matching:

```
vector_rrf_score = vector_weight × (1 / (60 + rank))
text_rrf_score   = text_weight   × (1 / (60 + rank))
final_score      = Σ(all RRF contributions per UID)
```

Default weights: 70% vector, 30% full-text. The `rrf_k` parameter (default 60) controls how quickly rank diminishes score.

#### Learning-Aware Search

Adjusts scores based on the user's learning state:

| Learning State | Boost |
|---------------|-------|
| Mastered | -20% (already knows) |
| In Progress | +10% (actively learning) |
| Not Started | +15% (new content) |
| Viewed | 0% (neutral) |

### 4b. Graph-Based Retrieval

**Service:** `ContextRetriever` (`core/services/askesis/context_retriever.py`)

Traverses the Neo4j graph for structured context — prerequisites, learning paths, active tasks, related goals. The traversal strategy adapts to the classified intent (see Stage 5a).

### 4c. Chunk-Level Semantic Search Within Askesis

`ContextRetriever._find_similar_chunks()` retrieves the specific passages most
relevant to the question, not just the owning PathStep titles:

1. Embed the user's question.
2. Hit `contentchunk_embedding_idx` via
   `Neo4jVectorSearchService.find_similar_chunks_by_text()` — top-5 above the
   0.6 cosine threshold, through `SearchRouter.retrieve_scoped_chunks(request,
   user_uid=…)`. The asking user is the **audience** (ADR-085 G8): the backend
   admits published curriculum passages plus that user's own non-private
   UserEntry notes — never another user's, which the shared chunk index also
   holds (canon P3).
3. Optionally filter `chunk_types` based on intent (e.g. `PRACTICE` ⇒
   `["exercise", "example"]`, `PREREQUISITE` ⇒ `["definition", "explanation"]`).
   The filter carries persisted **`ContentChunkType` values (lowercase)** — the
   exact strings `Neo4jContentAdapter` writes to `chunk.chunk_type`. The backend
   test is a bare `chunk.chunk_type IN $chunk_types`, so a member NAME
   (`"EXERCISE"`) matches zero rows silently instead of erroring; the intent map
   holds enum members and emits `.value` for exactly this reason.
   ⚠️ **Measured 2026-08-30: this filter has never run.** Every question
   classifies as `SPECIFIC` (Step 5a), which is unmapped, so `chunk_types` is
   always `None` and the draw is always unfiltered. The starvation the map would
   cause if it did fire — an `EXPLORATORY` question eligible for 66 of 925
   chunks — is arithmetic with no production effect today. Reproduce with
   `./dev eval-askesis-draw`. **Ruled 2026-08-30: staged, not dead.** The
   classifier fix is scheduled
   (`docs/roadmap/askesis-intent-classification-activation.md`) but deliberately
   leaves this map OFF: it activates the two branches that shape the answer, not
   the draw. Switching this map on is separate, gated on the content-typing
   classifier, and would need a thin-draw fallback in the same change — over the
   live 925-chunk corpus it grants 85% of chunks to three intents and 7.1% to
   EXPLORATORY. `docs/roadmap/deferred-work.md` § "Per-Domain Chunking Knobs +
   Chunk-Type-Aware Retrieval", Named work 4.
4. Join `chunk → content → entity` so each hit carries the owning PathStep's
   `parent_uid` + `parent_title` for citation.

The result lands on `relevant_context["relevant_chunks"]`, which the LLM service
inlines verbatim (using `context_window` — the 100-word pre/post buffer designed
for grounding) so the model can quote the matched passage instead of
paraphrasing the parent's title.

---

## Stage 5: The RAG Orchestration — Question to Answer

**Service:** `QueryProcessor` (`core/services/askesis/query_processor.py`)

**Entry points:** `answer_user_question(user_uid, question, session_id=None, preferred_mode=None)` and `process_query_with_context(user_uid, query, depth)` — both run the same LP-scoped, GuidanceMode-aware pipeline. Each entry point wraps its pipeline body with `asyncio.wait_for()` (30-second timeout via `AskesisPipelineTimeout`). On timeout, the method returns `Result.fail()` rather than hanging. The pipeline logic lives in `_answer_user_question_pipeline()` and `_process_query_with_context_pipeline()` inner methods.

When `session_id` is provided, `answer_user_question` retrieves or creates a `ConversationSession` via `ConversationContext`, loads prior turns as conversation history (`session.to_llm_messages(max_tokens=2000)`), passes them to the LLM, and records the new user + assistant turns both on the in-memory session (context window) and durably in Neo4j via `user_service.add_conversation_message()` (`(User)-[:HAS_MESSAGE]->(ConversationMessage)`). The Neo4j writes run as a fire-and-forget `asyncio.create_task()` (`_persist_conversation_turns`) so persistence latency cannot consume the 30-second pipeline timeout. Failures are warned-logged but never propagated. Omitting `session_id` keeps fully stateless behavior; Neo4j persistence still runs.

The orchestrator runs 7 steps in sequence:

### Step 5a: Load User Context

```python
user_context = await user_service.get_rich_unified_context(user_uid)
```

Returns ~250 fields: active tasks, mastered knowledge, enrolled paths, at-risk habits, overdue items, and cross-domain state. This is the MEGA-QUERY — a single comprehensive Cypher query.

**Critical:** Askesis uses `get_rich_unified_context()` (not `get_user_context()`). The rich version populates `entities_rich` which intelligence mixins depend on. Using the standard version silently degrades answer quality.

### Step 5b: Classify Intent

**Service:** `IntentClassifier` (`core/services/askesis/intent_classifier.py`)

```python
intent = await intent_classifier.classify_intent(question)
```

**Algorithm:**
1. Generate embedding of the user's question
2. Compare (cosine similarity) to pre-embedded exemplars for each intent type
3. Return the intent whose exemplars have the highest average similarity
4. Gate: `IntelligenceThreshold.INTENT_CLASSIFICATION` = 0.35 (moved from the unreachable 0.65 — PR-2, 2026-08-31) — below this, the verdict is `QueryIntent.SPECIFIC`. An `AGGREGATION` verdict routes to the tool-selection branch (a vetted, user-scoped count tool, or an explicit decline — tool-selection first slice, 2026-08-31), never to ordinary generation

**Intent types:**

| Intent | Example Query |
|--------|--------------|
| `EXPLORATORY` | "What can I learn about?" |
| `SPECIFIC` | "Explain Python decorators" |
| `HIERARCHICAL` | "What should I learn next?" |
| `PREREQUISITE` | "What do I need before async?" |
| `PRACTICE` | "Give me exercises for Python" |
| `AGGREGATION` | "How many tasks do I have?" |
| `RELATIONSHIP` | "How are these topics connected?" |

The six exemplar intents above (`SPECIFIC` is the default fallback when no match clears the threshold) each have 8 exemplar sentences. Exemplar embeddings are lazily computed on first classification and cached.

⚠️ **The gate was unreachable until 2026-08-31 (PR-2).** At the previous value of 0.65 —
an *average* over 8 diverse short exemplars — real queries scored 0.078–0.291 and even a
verbatim exemplar reached only 0.43–0.56 against its own intent, so `SPECIFIC` was the only
outcome and every intent-conditioned branch downstream took its catch-all path. PR-2 kept the
mean aggregation (measured best of the three candidate arms at the zero-wrong-activation
frontier) and moved the gate to 0.35: 19 of the 45 ratified labelled queries now fire, none
wrongly (`./dev eval-intent-classification` re-measures; the standing acceptance is
`wrong_activations == 0` on the mean arm). The `AGGREGATION` carve-out PR-2 introduced was
lifted the same day by the tool-selection first slice (a tool now answers the covered count
shape; everything else declines), and the chunk-type filter stays hard-wired off. Contract:
`docs/roadmap/askesis-intent-classification-activation.md`.

**Error tolerance:** If the embeddings API is unavailable, intent classification defaults to `SPECIFIC` rather than crashing. Individual exemplar embedding failures are skipped rather than raising — but the load is then incomplete, and an incomplete load also answers `SPECIFIC` (2026-08-30): averaging over fewer exemplars *raises* the mean, so a degraded set produces confident-looking verdicts rather than uncertain ones.

That leniency makes an outage indistinguishable from a real low-confidence
verdict at the call site. Callers that must tell them apart — measurement,
diagnostics — use `classify_intent_scored()`, which returns
`Result[IntentClassification]` (intent + score + `confident`), converts raised
embedding failures into `Result.fail`, and additionally refuses a *partially
loaded* exemplar set, whose per-intent averages run over unequal denominators
and are no longer comparable across intents.

### Step 5c: Extract Entities

**Service:** `EntityExtractor` (`core/services/askesis/entity_extractor.py`)

```python
entities = await entity_extractor.extract_entities_from_query(question, user_context)
```

Finds entities mentioned in the question using fuzzy matching:
1. **Exact match** — title appears verbatim in query
2. **Partial word match** — significant words (>3 chars) from the title appear in query
3. **Acronym match** — "REST API" matches "rest"

Returns: `{"knowledge": [...], "tasks": [...], "goals": [...], "habits": [...], "events": [...]}`

**Error tolerance:** If entity extraction fails, the pipeline continues with empty matches. The LLM can still answer using context from other stages.

### Step 5d: Retrieve Context

**Service:** `ContextRetriever` (`core/services/askesis/context_retriever.py`)

```python
context = await context_retriever.retrieve_relevant_context(user_context, question, intent)
```

Combines graph traversal and semantic search. The retrieval strategy adapts to intent:

| Intent | Primary Retrieval |
|--------|-------------------|
| `PREREQUISITE` | Prerequisite chains, blocked knowledge |
| `PRACTICE` | Active/completed tasks |
| `HIERARCHICAL` | Enrolled paths, current position |
| `EXPLORATORY` | Overview counts across all domains |

All intents also include: MOC navigation context, at-risk habits, overdue tasks, and semantically similar knowledge (when relevant keywords detected).

### Step 5e: Build LLM Context

**Service:** `ResponseGenerator` (`core/services/askesis/response_generator.py`)

```python
llm_context = response_generator.build_llm_context(user_context, ps_bundle=ps_bundle)
```

Renders the user-state block for the LLM. The learner grounding is the
`ASKESIS_GROUNDING_FIELDS` projection (`render_askesis_grounding`,
`core/services/askesis/grounding_projection.py` — ADR-082 D2): identity,
skeleton-tolerant LifePath framing, learning-journey position (enrolled paths
with step progress, current steps, mastery counts), and light study-serving
goals. The explicit field list is enforced by a recording-context test — the
projection replaced the pre-ADR-082 intent-selected UserContext dump.

Always includes: workload/capacity and alerts (mechanics unchanged); appends the
PsBundle's `curriculum_context_text` when a bundle is present.

**Token truncation:** The output of `build_llm_context()` is truncated to `AskesisTokenBudget.MAX_LLM_CONTEXT_CHARS` (~3000 tokens). When an PsBundle is present, its `curriculum_context_text` is separately truncated to `AskesisTokenBudget.MAX_CURRICULUM_CHARS` (~2500 tokens). Constants in `core/constants.py`.

### Step 5f: Generate Answer via LLM

```python
answer = await llm_service.generate_context_aware_answer(
    query=question,
    user_context=llm_context,
    additional_context=relevant_context,
    intent=intent
)
```

The LLM receives the question, the retrieved context, and the user's state. The system prompt heads with the authored `askesis_stance` fragment (ADR-082 D1/D3); the user-state block is the ADR-082 grounding projection rendered by `ResponseGenerator.build_llm_context()`.

### Step 5g: Generate Suggested Actions

```python
actions = response_generator.generate_actions(user_context, intent, relevant_context)
```

Returns 3-5 prioritized next steps:
- **Critical:** Habit streaks at risk
- **High:** Overdue tasks, blocked progress
- **Medium:** Prerequisites to learn, goals to advance
- **Low:** Foundation building, exploration

### Final Output

All three paths return the same top-level shape:

```python
{
    "answer": str,                    # Natural language response
    "context_used": dict[str, Any],  # Entities that informed the response
    "suggested_actions": list[dict],  # Prioritized next steps
    "confidence": float,              # 0.0-1.0
    "mode": str,                      # "guided" | "llm_generated" | "enrollment_gate"
    "has_citations": bool,
    # Optional — present only when mode == "guided":
    "guidance_mode": str,             # "socratic" | "direct" | "exploratory" | "encouraging"
    "session_id": str,                # present when session_id was passed in
}
```

**Mode values:**
- `"guided"` — PS bundle loaded; ZPD evidence + GuidanceMode used to build a template-driven system prompt
- `"llm_generated"` — enrolled user, no active PS bundle; context-aware LLM call with UserContext
- `"enrollment_gate"` — user has no enrolled Learning Path; short-circuit response, no LLM call

**Confidence calculation** (`QueryProcessorConfidence` in `core/constants.py`):
- Base: 0.70
- +0.10 if context was retrieved
- +0.05 if citations are included
- +0.05 if entities were extracted from query
- Maximum: 0.95

---

## Service Architecture

```
AskesisService (Facade — zero business logic)
│
├── QueryProcessor (LP-scoped RAG orchestrator — THIS GUIDE)
│   ├── IntentClassifier      ← embeds question, matches to intent exemplars
│   │                           + determine_guidance_mode() for GuidanceMode selection
│   ├── EntityExtractor       ← fuzzy-matches entities in the question
│   │                           + extract_from_bundle() for PS-scoped extraction
│   ├── ContextRetriever      ← graph traversal + semantic search + PS bundle loading
│   └── ResponseGenerator     ← builds LLM context, guided system prompts, actions
│
├── UserStateAnalyzer         ← comprehensive state analysis
├── ActionRecommendationEngine ← "what should I do next?"
│
└── External dependencies (injected via AskesisDeps):
    ├── UserService            ← builds UserContext (~250 fields)
    ├── LLMService             ← generates natural language answers
    ├── EmbeddingsService ← creates embeddings
    ├── GraphIntelligenceService ← executes graph queries
    ├── ZPDService             ← targeted KU readiness assessment
    ├── Neo4jVectorSearchService ← vector similarity search
    └── Domain services (articles, tasks, goals, habits, events, kus, lps, principles)
```

### One Pipeline — LP-Scoped, GuidanceMode-Aware

Both `answer_user_question()` and `process_query_with_context()` run the same LP-scoped, ZPD-informed, GuidanceMode-aware pipeline. When an PS bundle is available, the pipeline loads ZPD evidence for target KUs, determines the GuidanceMode via `IntentClassifier.determine_guidance_mode()`, and builds a guided system prompt via `ResponseGenerator.build_guided_system_prompt()`. The guided pipeline activates even when no specific KUs are extracted from the question — `classify_pedagogical_intent()` handles this (returning OUT_OF_SCOPE or ENCOURAGE_PRACTICE). When no PS bundle is available (no active path step), both methods fall back to standard global RAG.

**Scope override (Scoped Ask):** when the caller passes an explicit facet `scope` (e.g. a `nous` topic from the Askesis composer), the guided pipeline is bypassed for that turn — the answer comes from the context-aware branch over the facet-scoped `:ContentChunk` passages, with no PS-bundle context. An explicit topic selection is treated as clear user intent that overrides auto-guidance.

See: `/docs/architecture/ASKESIS_SOCRATIC_ARCHITECTURE.md`

---

## Wiring and Bootstrap

**Factory:** `create_askesis_service()` in `core/services/askesis_factory.py`

**Gate:** Askesis is only created when `INTELLIGENCE_TIER=full`. In `core` tier, `services.askesis` is `None` and all Askesis routes return 404.

**Bootstrap order** (in `services_bootstrap.py`):
1. Activity services created (`_create_activity_services()`)
2. Learning services created (`_create_learning_services()`)
3. `UserContextIntelligenceFactory` created with all domain relationship services
4. `create_askesis_service()` called with the factory + all service dicts
5. `AskesisDeps` dataclass constructed — all dependencies required (fail-fast)

---

## Environment Requirements

| Variable | Required For | Consequence If Missing |
|----------|-------------|----------------------|
| `OPENAI_API_KEY` | Embedding generation | FULL-tier bootstrap fails fast (`create_embedding_client()` raises); in CORE the key is never read |
| `OPENAI_API_KEY` | LLM answer generation | `generate_context_aware_answer()` fails |
| `INTELLIGENCE_TIER=full` | Askesis creation | Askesis not instantiated; routes return 404 |
| Neo4j vector indexes | Vector search | `db.index.vector.queryNodes()` fails |

---

## Debugging the Pipeline

### "Askesis returns low-quality answers"

1. **Check embedding coverage:** How many entities have embeddings?
   ```cypher
   MATCH (n:Entity) WHERE n.embedding IS NOT NULL RETURN count(n)
   MATCH (n:Entity) RETURN count(n)
   ```
2. **Check embedding version:** Only `v3` (OpenAI @1024 — ADR-068) matches current queries; older versions used different models/dimensions. Re-embed with `scripts/generate_embeddings_batch.py --stale`.
   ```cypher
   MATCH (n:Entity) WHERE n.embedding_version <> 'v3' RETURN count(n)
   ```
3. **Check UserContext depth:** Confirm routes call `get_rich_unified_context()`, not `get_user_context()`. The latter leaves `entities_rich` empty.

### "Intent classification is wrong"

The classifier uses cosine similarity against exemplar sentences. Check:
- Is the question too far from any exemplar? (Gate: 0.35 — `IntelligenceThreshold.INTENT_CLASSIFICATION`)
- An `AGGREGATION` verdict answers deterministically (a real count with stated bounds, or a decline/unavailable) — tool-selection first slice, 2026-08-31; a declined count question is coverage, not a classification miss.
- Default fallback is `QueryIntent.SPECIFIC` — if you're seeing too many SPECIFIC classifications, the exemplars may need expansion.
- Exemplar embeddings are cached after first use — restart to pick up changes.

### "Vector search returns nothing"

1. Verify vector indexes exist:
   ```cypher
   SHOW INDEXES WHERE type = 'VECTOR'
   ```
2. Verify embeddings exist on target nodes (see above)
3. Check `min_score` threshold — default is label-specific

### "Entity extraction misses obvious matches"

The fuzzy matcher requires:
- Exact substring match, OR
- A word >3 characters from the title appearing in the query, OR
- An acronym match

Single-word titles under 4 characters won't match via partial word. Titles not in the user's active/owned entities won't be checked at all.

---

## Key Files

| File | Role |
|------|------|
| `core/services/askesis_service.py` | Facade — delegates everything |
| `core/services/askesis_factory.py` | Wiring — `create_askesis_service()` |
| `core/services/askesis/query_processor.py` | RAG orchestrator |
| `core/services/askesis/intent_classifier.py` | Intent classification via embeddings |
| `core/services/askesis/entity_extractor.py` | Entity extraction via fuzzy matching |
| `core/services/askesis/context_retriever.py` | Graph + semantic retrieval + PS bundle loading |
| `core/services/askesis/response_generator.py` | LLM context, guided system prompts (4 modes), action generation |
| `core/models/askesis/ps_bundle.py` | PsBundle frozen dataclass |
| `core/models/askesis/pedagogical_intent.py` | PedagogicalIntent enum (7 move types) |
| `core/models/askesis/learning_objective.py` | StructuredLearningObjective |
| `core/services/askesis/types.py` | Data classes (AskesisInsight, AskesisRecommendation, AskesisAnalysis) |
| `core/services/askesis/state_scoring.py` | Pure functions for state scoring |
| `core/utils/text_truncation.py` | Sentence-boundary-aware token truncation |
| `core/constants.py` (`AskesisTokenBudget`) | Token budget constants for LLM context |
| `core/services/embeddings_service.py` | Embedding generation + version metadata (provider-agnostic behind `EmbeddingClientOperations` — ADR-068) |
| `core/services/neo4j_vector_search_service.py` | Vector search (4 modes) |
| `core/utils/embedding_text_builder.py` | Text extraction per entity type |
| `core/services/entity_chunking_service.py` | PathStep content chunking |
| `core/services/background/embedding_worker.py` | Background embedding — the one consumer of `*EmbeddingRequested`/`ChunkEmbeddingRequested` |
| `core/events/embedding_publisher.py` | The one publish chokepoint for all write paths (ADR-074) |

---

## Related Documentation

- **How Askesis Works:** `/docs/architecture/ASKESIS_HOW_IT_WORKS.md` — plain-English explanation of both halves
- **Askesis Architecture:** `/docs/architecture/ASKESIS_ARCHITECTURE.md` — facade pattern, sub-services, dependency graph
- **Askesis Guided Pipeline:** `/docs/architecture/ASKESIS_SOCRATIC_ARCHITECTURE.md` — PS-scoped, ZPD-centered, GuidanceMode-aware pipeline
- **Askesis Pedagogy:** `/docs/architecture/ASKESIS_PEDAGOGICAL_ARCHITECTURE.md` — Socratic companion design, GuidanceMode detection
- **Search Architecture:** `/docs/architecture/SEARCH_ARCHITECTURE.md` — SearchRouter, domain search
- **UserContext:** `/docs/architecture/UNIFIED_USER_ARCHITECTURE.md` — the MEGA-QUERY and ~250 fields
- **Embeddings ADRs:** `/docs/decisions/ADR-068-openai-embeddings-now-bge-later.md` — provider + 1024 dims; `/docs/decisions/ADR-074-post-persist-embedding-events.md` — how embeddings get and stay fresh
- **Prompt Templates:** `/docs/patterns/PROMPT_TEMPLATES.md` — centralized LLM prompt registry
- **Analog/Digital Architecture:** `/docs/architecture/ANALOG_DIGITAL_ARCHITECTURE.md` — how intelligence tier toggle works
