# Askesis RAG Pipeline — Developer Guide

**Last Updated:** March 2026

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
3. **Entity type detection** — Article, KU, Exercise, etc.
4. **Field validation** — Required fields checked per entity type
5. **Data preparation** — `prepare_entity_data_async()` in `core/services/ingestion/preparer.py`:
   - Generate/normalize UIDs
   - Extract content body
   - Handle relationships
   - Add timestamps
   - **Generate embedding** (if `HF_API_TOKEN` is set — see Stage 2)
6. **Neo4j write** — Entity node created with all properties including the embedding vector

**Key detail:** Ingestion and embedding happen in the same transaction. The entity arrives in Neo4j already searchable by vector similarity.

---

## Stage 2: Embedding — Content Becomes Searchable

**Service:** `HuggingFaceEmbeddingsService` (`core/services/embeddings_service.py`)

**Model:** `BAAI/bge-large-en-v1.5` — produces 1024-dimensional vectors

**Two paths to embedding:**

| Path | When | Service |
|------|------|---------|
| **During ingestion** | `ingest_file()` calls `prepare_entity_data_async()` | `HuggingFaceEmbeddingsService.create_embedding()` |
| **Background worker** | Entities created via API (not ingestion) | `EmbeddingBackgroundWorker` in `core/services/background/embedding_worker.py` — batches of 25 every 30s |

### Text Extraction

Before embedding, the system extracts the right text fields per entity type. This is the single source of truth:

**File:** `core/utils/embedding_text_builder.py`
**Function:** `build_embedding_text(entity_type, source)`

```python
# Field mappings (subset — full list in EMBEDDING_FIELD_MAPS)
EntityType.ARTICLE:    ("title", "content", "summary")      # separator: "\n\n"
EntityType.KU:         ("title", "summary", "description")  # separator: "\n\n"
EntityType.TASK:       ("title", "description")              # separator: "\n"
EntityType.GOAL:       ("title", "description", "vision_statement")
EntityType.HABIT:      ("name", "title", "description", "cue", "reward")
EntityType.EXERCISE:   ("title", "instructions", "description")
```

Curriculum types use `"\n\n"` between fields; activity types use `"\n"`. All 19 content-bearing entity types are supported.

### Embedding Storage

Each embedded entity gets four properties on its Neo4j node:

```
n.embedding            → list[float]  (1024 dimensions)
n.embedding_model      → "BAAI/bge-large-en-v1.5"
n.embedding_version    → "v2"
n.embedding_updated_at → datetime
```

### Retry Strategy

HuggingFace API calls use exponential backoff: up to 3 attempts with 2s → 4s → 8s delays. Text is truncated to 2000 chars (~512 tokens) before sending.

### Version Tracking

Current version is `v2` (migrated from OpenAI `text-embedding-3-small` at 1536 dims). The `embedding_version` property allows re-embedding outdated vectors. `get_or_create_embedding()` checks the version before deciding whether to regenerate.

---

## Stage 3: Chunking — Long Content Gets Subdivided

**Service:** `EntityChunkingService` (`core/services/entity_chunking_service.py`)

**When:** Immediately after ingestion, for Article entities.

**What happens:**
1. Content is split into semantic chunks
2. Chunk metadata generated (word count, complexity)
3. Chunks stored as `:Content` nodes in Neo4j with parent relationships

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

### 4c. Semantic Search Within Askesis

`ContextRetriever._find_similar_knowledge()` performs a focused search:

1. Embed the user's question
2. Fetch entities with embeddings from Neo4j (`WHERE ku.embedding IS NOT NULL`)
3. Calculate cosine similarity in Python
4. Return top-5 above 0.6 threshold

This is separate from `Neo4jVectorSearchService` — it's a simpler, direct comparison used specifically within the Askesis pipeline.

---

## Stage 5: The RAG Orchestration — Question to Answer

**Service:** `QueryProcessor` (`core/services/askesis/query_processor.py`)

**Entry point:** `answer_user_question(user_uid, question)`

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
4. Threshold: 0.65 — below this, defaults to `QueryIntent.SPECIFIC`

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
| `GOAL_ACHIEVEMENT` | Goal-specific queries |
| `SCHEDULED_ACTION` | Schedule-related queries |

Each intent has 8 exemplar sentences. Exemplar embeddings are lazily computed on first classification and cached.

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
llm_context = response_generator.build_llm_context(user_context, question, intent)
```

Converts the UserContext into a natural-language summary for the LLM. Sections are included based on intent:

```python
INTENT_CONTEXT_SECTIONS = {
    QueryIntent.HIERARCHICAL: {"knowledge", "goals", "life_path"},
    QueryIntent.PREREQUISITE: {"knowledge"},
    QueryIntent.PRACTICE:     {"tasks", "knowledge"},
    QueryIntent.EXPLORATORY:  {"tasks", "knowledge", "goals", "habits", "events", "life_path"},
    # ...
}
```

Always includes: user identity, workload/capacity, and alerts.

### Step 5f: Generate Answer via LLM

```python
answer = await llm_service.generate_context_aware_answer(
    query=question,
    user_context=llm_context,
    additional_context=relevant_context,
    intent=intent
)
```

The LLM receives the question, the retrieved context, and the user's state. Context is assembled programmatically in `ResponseGenerator.build_llm_context()` — prompt templates in `PROMPT_REGISTRY` are planned but not yet used for Q&A.

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

```python
{
    "answer": str,                    # Natural language response
    "context_used": dict[str, Any],  # Entities that informed the response
    "suggested_actions": list[dict],  # Prioritized next steps
    "confidence": float,              # 0.0-1.0
    "mode": "llm_generated",
    "has_citations": bool,
}
```

**Confidence calculation:**
- Base: 0.70
- +0.10 if context was retrieved
- +0.05 if citations are included

---

## Service Architecture

```
AskesisService (Facade — zero business logic)
│
├── QueryProcessor (LP-scoped RAG orchestrator — THIS GUIDE)
│   ├── IntentClassifier      ← embeds question, matches to intent exemplars
│   │                           + determine_guidance_mode() for GuidanceMode selection
│   ├── EntityExtractor       ← fuzzy-matches entities in the question
│   │                           + extract_from_bundle() for LS-scoped extraction
│   ├── ContextRetriever      ← graph traversal + semantic search + LS bundle loading
│   └── ResponseGenerator     ← builds LLM context, guided system prompts, actions
│
├── UserStateAnalyzer         ← comprehensive state analysis
├── ActionRecommendationEngine ← "what should I do next?"
│
└── External dependencies (injected via AskesisDeps):
    ├── UserService            ← builds UserContext (~250 fields)
    ├── LLMService             ← generates natural language answers
    ├── HuggingFaceEmbeddingsService ← creates embeddings
    ├── GraphIntelligenceService ← executes graph queries
    ├── ZPDService             ← targeted KU readiness assessment
    ├── Neo4jVectorSearchService ← vector similarity search
    └── Domain services (articles, tasks, goals, habits, events, kus, lps, principles)
```

### One Pipeline — LP-Scoped, GuidanceMode-Aware

`answer_user_question()` runs a single pipeline that is LP-scoped (enrollment gate), ZPD-informed (targeted KU readiness), and GuidanceMode-aware (DIRECT/SOCRATIC/EXPLORATORY/ENCOURAGING). When an LS bundle is available, the pipeline loads ZPD evidence for target KUs, determines the GuidanceMode via `IntentClassifier.determine_guidance_mode()`, and builds a guided system prompt via `ResponseGenerator.build_guided_system_prompt()`. When no LS bundle is available (no active learning step), it falls back to standard global RAG.

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
| `HF_API_TOKEN` | Embedding generation | Ingestion works but without embeddings; vector search unavailable |
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
2. **Check embedding version:** Old v1 embeddings (1536-dim) won't match v2 queries (1024-dim).
   ```cypher
   MATCH (n:Entity) WHERE n.embedding_version = 'v1' RETURN count(n)
   ```
3. **Check UserContext depth:** Confirm routes call `get_rich_unified_context()`, not `get_user_context()`. The latter leaves `entities_rich` empty.

### "Intent classification is wrong"

The classifier uses cosine similarity against exemplar sentences. Check:
- Is the question too far from any exemplar? (Threshold: 0.65)
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
| `core/services/askesis/context_retriever.py` | Graph + semantic retrieval + LS bundle loading |
| `core/services/askesis/response_generator.py` | LLM context, guided system prompts (4 modes), action generation |
| `core/models/askesis/ls_bundle.py` | LSBundle frozen dataclass |
| `core/models/askesis/pedagogical_intent.py` | PedagogicalIntent enum (7 move types) |
| `core/models/askesis/learning_objective.py` | StructuredLearningObjective |
| `core/services/askesis/types.py` | Data classes (AskesisInsight, AskesisRecommendation, AskesisAnalysis) |
| `core/services/askesis/state_scoring.py` | Pure functions for state scoring |
| `core/services/embeddings_service.py` | HuggingFace embedding generation |
| `core/services/neo4j_vector_search_service.py` | Vector search (4 modes) |
| `core/utils/embedding_text_builder.py` | Text extraction per entity type |
| `core/services/entity_chunking_service.py` | Article chunking |
| `core/services/background/embedding_worker.py` | Background embedding for API-created entities |
| `core/services/ingestion/preparer.py` | Embedding generation during ingestion |

---

## Related Documentation

- **Askesis Architecture:** `/docs/architecture/ASKESIS_ARCHITECTURE.md` — facade pattern, sub-services, dependency graph
- **Askesis Guided Pipeline:** `/docs/architecture/ASKESIS_SOCRATIC_ARCHITECTURE.md` — LS-scoped, ZPD-centered, GuidanceMode-aware pipeline
- **Askesis Pedagogy:** `/docs/architecture/ASKESIS_PEDAGOGICAL_ARCHITECTURE.md` — Socratic companion design, GuidanceMode detection
- **Search Architecture:** `/docs/architecture/SEARCH_ARCHITECTURE.md` — SearchRouter, domain search
- **UserContext:** `/docs/architecture/UNIFIED_USER_ARCHITECTURE.md` — the MEGA-QUERY and ~250 fields
- **Embeddings ADR:** `/docs/decisions/ADR-049-huggingface-embeddings-migration.md` — why HuggingFace, why 1024 dims
- **Prompt Templates:** `/docs/patterns/PROMPT_TEMPLATES.md` — centralized LLM prompt registry
- **Analog/Digital Architecture:** `/docs/architecture/ANALOG_DIGITAL_ARCHITECTURE.md` — how intelligence tier toggle works
